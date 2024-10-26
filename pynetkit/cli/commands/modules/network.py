#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from dataclasses import dataclass, field
from ipaddress import IPv4Interface
from typing import Generator

import click
import cloup
from click import Context
from prettytable.colortable import ColorTable, Themes

from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
    async_command,
)
from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import config_table, mce
from pynetkit.modules.network import NetworkModule
from pynetkit.types import NetworkAdapter


@dataclass
class NetworkConfig:
    index: int
    adapter: NetworkAdapter
    addresses: list[IPv4Interface] = field(default_factory=list)
    query: str = None
    keep: bool = False
    no_replace: bool = False


network = NetworkModule()
config_map: dict[int, NetworkConfig] = {}

TYPE_NAMES = {
    NetworkAdapter.Type.WIRED: "Wired",
    NetworkAdapter.Type.WIRELESS: "Wireless",
    NetworkAdapter.Type.WIRELESS_STA: "Wireless Station",
    NetworkAdapter.Type.WIRELESS_AP: "Wireless AP",
}


async def network_start():
    if not network.is_started:
        await network.start()


def adapter_to_config(adapter: NetworkAdapter) -> NetworkConfig | None:
    for i, config in config_map.items():
        if config.adapter.name == adapter.name:
            return config
    return None


@cloup.group(
    name="network",
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.pass_context
def cli(ctx: Context):
    if ctx.invoked_subcommand:
        return

    config_table(
        f"Network module",
        (
            "State",
            (f"§aActive§r ({network.thread.name})" if network.is_started else "§8Idle"),
        ),
        color=True,
    )

    if not config_map:
        mce(
            "\n§cAdapter mapping is not configured.\n"
            "§fChoose the network adapters you want to use with the "
            "§enetwork use §dindex §cadapter §fcommand.§r"
        )
        return
    table = ColorTable(
        [" ", "Name", "Type", "Configured addresses", "Keep in config (-k)?"],
        theme=Themes.OCEAN_DEEP,
    )
    table.title = "Adapter configuration / mapping"
    table.align = "l"
    for idx, config in sorted(config_map.items()):
        config: NetworkConfig
        keep = "No"
        if config.keep:
            keep = f"Yes / query: '{config.query}'"
            if config.no_replace:
                keep += " / don't replace (-n)"
            else:
                keep += " / replace if assigned"
        table.add_row(
            [
                idx,
                config.adapter.name,
                TYPE_NAMES[config.adapter.type],
                "\n".join(str(address) for address in sorted(config.addresses))
                or "None",
                keep,
            ]
        )
    click.echo(table.get_string())


@cloup.command(help="List available network adapters.", name="list")
@async_command
async def list_():
    await network_start()
    mce(f"§fListing network adapters...§r")
    table = ColorTable(
        ["Title", "Type", "Used as", "Actual addresses", "Configured addresses"],
        theme=Themes.OCEAN_DEEP,
    )
    table.align = "l"
    adapters = await network.list_adapters()
    for adapter in adapters:
        config = adapter_to_config(adapter)
        addresses = await network.get_adapter_addresses(adapter)
        table.add_row(
            [
                adapter.name,
                TYPE_NAMES[adapter.type],
                config and config.index or "",
                "\n".join(str(address) for address in sorted(addresses)) or "None",
                config
                and (
                    "\n".join(str(address) for address in sorted(config.addresses))
                    or "None"
                )
                or "",
            ]
        )
    click.echo(table.get_string())


@cloup.command(
    help="""
    Configure network adapter index map assignment.

    \b
    The QUERY argument (case-insensitive) can be either:
    - adapter title (or the beginning),
    - adapter type (wired/wireless/STA/AP), will match the first one found,
    - IP address of the adapter.
    """
)
@cloup.argument("index", type=int, help="Index to assign an adapter to.")
@cloup.argument("query", help="Text that identifies the adapter to assign (see above).")
@cloup.option("-k", "--keep", is_flag=True, help="Keep the assignment in saved config.")
@cloup.option("-n", "--no-replace", is_flag=True, help="Only assign if not already.")
@async_command
async def use(index: int, query: str, no_replace: bool, keep: bool):
    if index <= 0:
        mce("§cIndex must be at least 1.§r")
        return
    if not query:
        config_map.pop(index)
        mce(f"§fRemoved adapter assignment for index §d{index}§r.")
        return
    query = query.lower()
    type_query_map = {
        "wired": NetworkAdapter.Type.WIRED,
        "wireless": NetworkAdapter.Type.WIRELESS,
        "sta": NetworkAdapter.Type.WIRELESS_STA,
        "ap": NetworkAdapter.Type.WIRELESS_AP,
    }
    adapter: NetworkAdapter | None = None
    # search by adapter type
    if query in type_query_map:
        adapter = await network.get_adapter(type_query_map[query])
    if not adapter:
        adapters = await network.list_adapters()
        for adapter in adapters:
            # search by adapter title
            if adapter.name.lower().startswith(query):
                break
            if query.count(".") != 3:
                continue
            # search by IP address
            addresses = await network.get_adapter_addresses(adapter)
            for address in addresses:
                if query == str(address.ip):
                    break
            else:
                continue
            break
        else:
            adapter = None
    if not adapter:
        mce("§cNo adapter matching the query was found.§r")
        return
    config = config_map.get(index)
    if not config:
        config = NetworkConfig(index=index, adapter=adapter)
    # save the -k/-n flags
    config.keep = keep
    config.no_replace = no_replace
    # skip the actual assignment if -n specified
    if index in config_map and no_replace:
        mce(
            f"§8Skipping adapter §d{index}§8 mapping - "
            f"already assigned to §d{config_map[index].adapter.name}.§r"
        )
        return
    # save the query and config mapping
    config.query = query
    config_map[index] = config
    mce(f"§fAssigned adapter §d{adapter.name}§f to index §d{index}§r.")


@cloup.command(help="Manually stop the network module.")
@async_command
async def stop():
    await network.stop()
    mce(f"§fNetwork module stopped§r")


class CommandModule(BaseCommandModule):
    CLI = cli

    def config_get(self) -> Config.Module:
        return Config.Module(
            order=200,
            config=dict(
                adapters=[
                    dict(
                        index=idx,
                        query=config.query,
                        no_replace=config.no_replace,
                        addresses=config.addresses,
                    )
                    for idx, config in sorted(config_map.items())
                    if config.keep
                ]
            ),
            # unload script - remove all persistent entries from the config map
            scripts=dict(
                unload=[
                    f'network use {idx} ""'
                    for idx, config in config_map.items()
                    if config.keep
                ]
            ),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        for item in config.config.get("adapters", []):
            yield f'network use {item["index"]} "{item["query"]}" -k' + (
                " -n" if item["no_replace"] else ""
            )


cli.section("Network adapters", list_, use)
# cli.section("IP configuration", addr)
# cli.section("Utilities", ping)
cli.section("Miscellaneous", stop)
COMMAND = CommandModule()
