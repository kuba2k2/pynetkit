#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Interface
from typing import Generator, Iterable

import click
import cloup
from click import Context
from prettytable.colortable import ColorTable, Themes

from pynetkit.cli.command import run_command
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

    dhcp: bool = True
    addresses: list[IPv4Interface] = field(default_factory=list)

    query: str = None
    keep: bool = False
    no_replace: bool = False

    async def set_addresses(self) -> None:
        await network.set_adapter_addresses(self.adapter, self.dhcp, self.addresses)
        dhcp, addresses = await network.get_adapter_addresses(self.adapter)
        if addresses != self.addresses and not self.dhcp:
            mce(
                f"§cCouldn't apply address configuration to §d{self.adapter.name}§c:\n"
                f"Requested: §d{joinaddrs(self.dhcp, self.addresses)}§c\n"
                f"Assigned: §d{joinaddrs(dhcp, addresses)}§r"
            )
        else:
            mce(
                f"§fAdapter §d{self.adapter.name}§f configuration changed§r.\n"
                f"§8Assigned: §d{joinaddrs(dhcp, addresses)}§r"
            )


network = NetworkModule()
CONFIG: dict[int, NetworkConfig] = {}

TYPE_NAMES = {
    NetworkAdapter.Type.WIRED: "Wired",
    NetworkAdapter.Type.WIRELESS: "Wireless",
    NetworkAdapter.Type.WIRELESS_STA: "Wireless Station",
    NetworkAdapter.Type.WIRELESS_AP: "Wireless AP",
    NetworkAdapter.Type.VIRTUAL: "Virtual",
}


async def network_start():
    if not network.is_started:
        await network.start()


def adapter_to_config(adapter: NetworkAdapter) -> NetworkConfig | None:
    for i, config in CONFIG.items():
        if config.adapter.name == adapter.name:
            return config
    return None


def joinaddrs(
    dhcp: bool,
    addresses: Iterable[IPv4Interface] | None,
    sep: str = ", ",
) -> str:
    addrs = sep.join(str(address) for address in sorted(addresses))
    if dhcp and addrs:
        return f"{addrs} (DHCP)"
    if dhcp:
        return "DHCP"
    return addrs or "None"


def print_no_mapping():
    mce(
        "\n§cAdapter mapping is not configured.\n"
        "§fChoose the network adapters you want to use with the "
        "§enetwork use §dindex §cadapter §fcommand.§r"
    )


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

    if not CONFIG:
        print_no_mapping()
        return
    table = ColorTable(
        [" ", "Name", "Type", "Configured addresses", "Keep in config (-k)?"],
        theme=Themes.OCEAN_DEEP,
    )
    table.title = "Adapter configuration / mapping"
    table.align = "l"
    for idx, config in sorted(CONFIG.items()):
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
                joinaddrs(config.dhcp, config.addresses, "\n"),
                keep,
            ]
        )
    click.echo(table.get_string())


@cloup.command(help="List available network adapters.", name="list")
@cloup.option("-a", "--all", is_flag=True, help="Also list virtual adapters.")
@async_command
async def list_(all: bool):
    await network_start()
    mce(f"§fListing network adapters...§r")
    table = ColorTable(
        ["Title", "Type", "Used as", "Actual addresses", "Configured addresses"],
        theme=Themes.OCEAN_DEEP,
    )
    table.align = "l"
    adapters = await network.list_adapters()
    for adapter in adapters:
        if adapter.type == NetworkAdapter.Type.VIRTUAL and not all:
            continue
        config = adapter_to_config(adapter)
        dhcp, addresses = await network.get_adapter_addresses(adapter)
        table.add_row(
            [
                adapter.name,
                TYPE_NAMES[adapter.type],
                config and config.index or "",
                joinaddrs(dhcp, addresses, "\n"),
                config and joinaddrs(config.dhcp, config.addresses, "\n") or "",
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
    await network_start()
    if index <= 0:
        mce("§cIndex must be at least 1.§r")
        return
    if not query:
        CONFIG.pop(index)
        mce(f"§fRemoved adapter assignment for index §d{index}§r.")
        return
    query = query.lower()
    type_query_map = {
        "wired": (NetworkAdapter.Type.WIRED,),
        "wireless": (NetworkAdapter.Type.WIRELESS,),
        "wifi": (NetworkAdapter.Type.WIRELESS, NetworkAdapter.Type.WIRELESS_STA),
        "sta": (NetworkAdapter.Type.WIRELESS_STA, NetworkAdapter.Type.WIRELESS),
        "ap": (NetworkAdapter.Type.WIRELESS_AP, NetworkAdapter.Type.WIRELESS),
        "virtual": (NetworkAdapter.Type.VIRTUAL),
    }
    adapter: NetworkAdapter | None = None
    # search by adapter type
    if query in type_query_map:
        adapter = await network.get_adapter(*type_query_map[query])
    if not adapter:
        adapters = await network.list_adapters()
        for adapter in adapters:
            # search by adapter title
            if adapter.name.lower().startswith(query):
                break
            if query.count(".") != 3:
                continue
            # search by IP address
            dhcp, addresses = await network.get_adapter_addresses(adapter)
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
    config = CONFIG.get(index)
    if not config:
        config = NetworkConfig(index=index, adapter=adapter)
    # save the -k/-n flags
    config.keep = keep
    config.no_replace = no_replace
    # skip the actual assignment if -n specified
    if index in CONFIG and no_replace:
        mce(
            f"§8Skipping adapter §d{index}§8 mapping - "
            f"already assigned to §d{CONFIG[index].adapter.name}.§r"
        )
        return
    # save the query and config mapping
    config.adapter = adapter
    config.query = query
    # fetch currently assigned addresses
    config.dhcp, config.addresses = await network.get_adapter_addresses(config.adapter)
    if config.dhcp:
        config.addresses = []
    CONFIG[index] = config
    mce(f"§fAssigned adapter §d{adapter.name}§f to index §d{index}§r.")


@cloup.group(
    help="Manage adapter IP address configuration.",
    invoke_without_command=True,
)
@cloup.argument("index", type=int, help="Adapter index to configure.")
@click.pass_context
def addr(ctx: Context, index: int):
    if index not in CONFIG:
        mce(
            f"§cNo adapter is configured at index §d{index}§r.\n"
            "§fChoose the network adapters you want to use with the "
            "§enetwork use §dindex §cadapter §fcommand.§r"
        )
        return
    ctx.obj = CONFIG[index]


@addr.command(help="Add an IP address to the adapter's config.", name="add")
@cloup.argument(
    "addresses",
    type=IPv4Interface,
    required=True,
    nargs=-1,
    help="Interface address(es) with CIDR mask.",
)
@click.pass_obj
@async_command
async def addr_add(config: NetworkConfig, addresses: tuple[IPv4Interface]):
    await network_start()
    if config.dhcp is None:
        mce(f"§eAdapter §d{config.adapter.name}§e uses DHCP, will be disabled.§r")
    changed = config.dhcp
    for address in addresses:
        if address not in config.addresses:
            config.addresses.append(address)
            changed = True
            continue
        mce(f"§eAddress §d{address}§e already assigned to §d{config.adapter.name}§r.")
    if changed:
        config.dhcp = False
        config.addresses.sort()
        await config.set_addresses()


@addr.command(help="Delete an IP address from the adapter's config.", name="del")
@cloup.argument(
    "addresses",
    type=IPv4Interface,
    required=True,
    nargs=-1,
    help="Interface address(es) with CIDR mask.",
)
@click.pass_obj
@async_command
async def addr_del(config: NetworkConfig, addresses: tuple[IPv4Interface]):
    await network_start()
    if config.dhcp:
        mce(f"§eAdapter §d{config.adapter.name}§e uses DHCP, not deleting address.§r")
        return
    changed = False
    for address in addresses:
        if address in config.addresses:
            config.addresses.remove(address)
            changed = True
            continue
        mce(f"§eAddress §d{address}§e not assigned to §d{config.adapter.name}§r.")
    if changed:
        await config.set_addresses()


@addr.command(help="Set an IP address for the adapter (flush and add).", name="set")
@cloup.argument(
    "addresses",
    type=IPv4Interface,
    required=True,
    nargs=-1,
    help="Interface address(es) with CIDR mask.",
)
@click.pass_obj
@async_command
async def addr_set(config: NetworkConfig, addresses: tuple[IPv4Interface]):
    await network_start()
    if config.dhcp:
        mce(f"§eAdapter §d{config.adapter.name}§e uses DHCP, will be disabled.§r")
    if set(addresses) == set(config.addresses) and not config.dhcp:
        mce(
            f"§eAddress(es) §d{joinaddrs(False, addresses)}§e "
            f"already set for §d{config.adapter.name}§r."
        )
        return
    config.dhcp = False
    config.addresses = sorted(addresses)
    await config.set_addresses()


@addr.command(help="Enable DHCP and remove static IP addresses.", name="dhcp")
@click.pass_obj
@async_command
async def addr_dhcp(config: NetworkConfig):
    await network_start()
    if config.dhcp:
        mce(f"§eAdapter §d{config.adapter.name}§e already uses DHCP.§r")
        return
    config.dhcp = True
    config.addresses = []
    await config.set_addresses()


@addr.command(help="Flush the IP addresses of the adapter (delete all).", name="flush")
@click.pass_obj
@async_command
async def addr_flush(config: NetworkConfig):
    await network_start()
    if config.dhcp:
        mce(f"§eAdapter §d{config.adapter.name}§e uses DHCP, will be disabled.§r")
    config.dhcp = False
    config.addresses = []
    await config.set_addresses()


@addr.command(help="Save the assigned IP addresses to the config.", name="save")
@click.pass_obj
@async_command
async def addr_save(config: NetworkConfig):
    await network_start()
    config.dhcp, config.addresses = await network.get_adapter_addresses(config.adapter)
    if config.dhcp:
        config.addresses = []
    mce(f"§fAdapter §d{config.adapter.name}§f configuration saved§r.")
    mce(f"§fConfigured: §d{joinaddrs(config.dhcp, config.addresses)}§r")


@addr.command(help="Apply the configured IP addresses to the adapter.", name="restore")
@click.pass_obj
@async_command
async def addr_restore(config: NetworkConfig):
    await network_start()
    await config.set_addresses()


@cloup.command(help="Ping a host to see if it's alive.")
@cloup.argument("address", type=IPv4Address, help="IP address of the host to ping.")
@cloup.argument("count", type=int, default=4, help="How many pings (default: 4).")
@cloup.argument("interval", type=float, default=0.2, help="Interval (default: 0.2 s).")
@cloup.argument("timeout", type=float, default=1.0, help="Timeout (default: 1.0 s).")
@async_command
async def ping(address: IPv4Address, count: int, interval: float, timeout: float):
    await network_start()
    await network.ping(
        address,
        count,
        interval,
        timeout,
        log=lambda msg: mce((f"§a" if "alive" in msg else "§c") + msg + "§r"),
    )


@cloup.command(help="Manually stop the network module.")
@async_command
async def stop():
    await network.stop()
    mce(f"§fNetwork module stopped§r")


class CommandModule(BaseCommandModule):
    CLI = cli
    CONFIG = CONFIG

    def on_load(self) -> None:
        mce("§8Network module loaded, assigning default adapter mappings...§r")
        mce("§8Ignore any errors here.§r")
        run_command("network use 1 wired")
        run_command("network use 2 sta")
        run_command("network use 3 ap")

    def config_get(self) -> Config.Module:
        return Config.Module(
            order=200,
            config=dict(
                adapters=[
                    dict(
                        index=idx,
                        query=config.keep and config.query or None,
                        no_replace=config.no_replace,
                        dhcp=config.dhcp,
                        addresses=None if config.dhcp else (config.addresses or []),
                    )
                    for idx, config in sorted(CONFIG.items())
                    if config.keep or config.addresses
                ]
            ),
            # unload script - remove all persistent entries from the config map
            scripts=dict(
                unload=[
                    f'network use {idx} ""'
                    for idx, config in CONFIG.items()
                    if config.keep
                ]
            ),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        for item in config.config.get("adapters", []):
            item: dict
            if item.get("query"):
                yield f'network use {item["index"]} "{item["query"]}" -k' + (
                    " -n" if item["no_replace"] else ""
                )
            addresses = item.get("addresses", None)
            if item.get("dhcp"):
                yield f"network addr {item['index']} dhcp"
            elif not addresses:
                yield f"network addr {item['index']} flush"
            else:
                yield f"network addr {item['index']} set " + " ".join(
                    str(address) for address in sorted(addresses)
                )


cli.section("Network adapters", list_, use)
cli.section("IP configuration", addr)
cli.section("Utilities", ping)
cli.section("Miscellaneous", stop)
COMMAND = CommandModule()
