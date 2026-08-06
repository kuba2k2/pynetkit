#  Copyright (c) Kuba Szczodrzyński 2024-10-18.

from ipaddress import IPv4Address, IPv4Interface
from logging import warning
from typing import Generator

import click
import cloup
from click import Context
from macaddress import MAC

from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
    async_command,
    index_option,
)
from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import config_table, mce
from pynetkit.modules.dhcp import DhcpModule, DhcpServerOption

DHCP: list[DhcpModule] = [DhcpModule()]


@cloup.group(
    name="dhcp",
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@index_option(
    cls=DhcpModule,
    items=DHCP,
    name="dhcp",
    title="DHCP server",
    required=False,
)
@click.pass_context
def cli(ctx: Context, dhcp: DhcpModule | None):
    if ctx.invoked_subcommand:
        return
    if not DHCP:
        warning("No DHCP servers are created")
        return
    servers = [dhcp] if dhcp else DHCP

    for i, dhcp in enumerate(servers):
        if dhcp.options:
            options = [("Extra options", "")]
            for opt in dhcp.options:
                value_str = "§8Dynamic" if opt.value is Ellipsis else str(opt.value)
                client_str = opt.client and f" (§d{opt.client}§r)" or ""
                options += [(f" - {opt}", value_str + client_str)]
        else:
            options = [("Extra options", "(empty)")]

        if dhcp.hosts:
            leases = [("Active leases", "")]
            for mac, ip in dhcp.hosts.items():
                host_name = dhcp.hosts_names.get(mac)
                vendor_cid = dhcp.hosts_vendor_cid.get(mac)
                info = (
                    f"{mac} - {ip}"
                    + (host_name and f" (§d{host_name}§r)" or "")
                    + (vendor_cid and f" (vendor: §d{vendor_cid}§r)" or "")
                )
                leases += [("", info)]
        else:
            leases = [("Active leases", "(empty)")]

        config_table(
            f"DHCP server #{DHCP.index(dhcp) + 1}",
            (
                "State",
                f"§aStarted§r ({dhcp.thread.name})" if dhcp.is_started else "§8Stopped",
            ),
            ("Listen address", f"{dhcp.address}:{dhcp.port}"),
            ("Interface", dhcp.interface or "§cNot set"),
            ("Lease range", dhcp.range and dhcp.range[0] or "Using entire network"),
            ("", dhcp.range and dhcp.range[1] or ""),
            ("Host name", dhcp.hostname or "Not set"),
            *options,
            *leases,
            no_top=i > 0,
            color=True,
        )


@cloup.command(help="Create new DHCP server(s).")
@cloup.argument("total", default=0, help="Total number of DHCP server instances.")
def create(total: int = 0):
    if not total:
        dhcp = DhcpModule()
        DHCP.append(dhcp)
        return
    while total > len(DHCP):
        dhcp = DhcpModule()
        DHCP.append(dhcp)
    mce(f"§fDHCP module(s) created, total: {len(DHCP)}§r")


@cloup.command(help="Remove a DHCP server.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@async_command
async def destroy(dhcp: DhcpModule):
    await dhcp.stop()
    DHCP.remove(dhcp)
    mce(f"§fDHCP module removed, total: {len(DHCP)}§r")


@cloup.command(help="Start the DHCP server, optionally supplying configuration.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@click.argument("address", type=IPv4Address, required=False)
@click.argument("port", type=int, required=False)
@click.argument("iface", type=IPv4Interface, required=False)
@async_command
async def start(
    dhcp: DhcpModule,
    address: IPv4Address | None,
    port: int | None,
    iface: IPv4Interface | None,
):
    if dhcp.is_started:
        mce(f"§fDHCP module is already running§r")
        return
    if address is not None:
        dhcp.address = address
    if port is not None:
        dhcp.port = port
    if iface is not None:
        dhcp.interface = iface
    await dhcp.start()
    mce(f"§fDHCP module started§r")


@cloup.command(help="Stop the DHCP server.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@async_command
async def stop(dhcp: DhcpModule):
    await dhcp.stop()
    mce(f"§fDHCP module stopped§r")


@cloup.command(help="Set server listen address without starting.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@cloup.argument("address", type=IPv4Address, help="Listen IP address.")
@cloup.argument("port", type=int, required=False, help="Listen port, default 67.")
def listen(dhcp: DhcpModule, address: IPv4Address, port: int | None):
    dhcp.address = address
    if port is not None:
        dhcp.port = port
    mce(f"§fListen address set to: §d{dhcp.address}:{dhcp.port}§r")
    if dhcp.interface is None and int(address) != 0:
        dhcp.interface = IPv4Interface(f"{dhcp.address}/24")
        mce(f"§fServer interface is now set to: §d{dhcp.interface}§r")


@cloup.command(help="REQUIRED: Set server interface configuration.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@cloup.argument("iface", type=IPv4Interface, help="Interface address with CIDR mask.")
def interface(dhcp: DhcpModule, iface: IPv4Interface):
    dhcp.interface = iface
    mce(f"§fServer interface set to: §d{dhcp.interface}§r")


@cloup.command(help="Set lease address range.", name="range")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@cloup.argument("first", type=IPv4Address, help="First address to offer.")
@cloup.argument("last", type=IPv4Address, help="Last address to offer (incl.).")
def range_(dhcp: DhcpModule, first: IPv4Address, last: IPv4Address):
    dhcp.range = (first, last)
    mce(f"§fLease address range set to: §d{dhcp.range[0]} - {dhcp.range[1]}§r")


@cloup.command(help="Set reported hostname.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@cloup.argument(
    "name",
    type=str,
    help='Reported hostname (or "" to disable reporting).',
)
def hostname(dhcp: DhcpModule, name: str | None):
    dhcp.hostname = name or None
    mce(f"§fHostname set to: §d{dhcp.hostname or '(not set)'}§r")


@cloup.command(help="Add/remove DHCP options for clients.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@cloup.argument(
    "option",
    type=str,
    help="Option specifier - num:name(format) - only 'name' is required.",
)
@cloup.argument(
    "data",
    type=str,
    help='Option data (or "" to remove).',
)
@cloup.argument(
    "client",
    type=MAC,
    required=False,
    help="Target client's MAC address (defaults to all).",
)
def option(dhcp: DhcpModule, option: str, data: str, client: MAC | None):
    client_str = f"§f for client §d{client}§r" if client else "§r"
    opt = DhcpServerOption.parse(option, data, client)
    if not data:
        dhcp.del_option(opt)
        mce(f"§fOption removed: §d{str(opt).strip()}{client_str}")
    else:
        dhcp.add_option(opt)
        mce(f"§fOption added: §d{str(opt).strip()}§f = §d{opt.value}{client_str}")


class CommandModule(BaseCommandModule):
    CLI = cli

    def config_get(self) -> Config.Module:
        if not DHCP:
            load = []
            unload = []
        elif len(DHCP) == 1:
            load = ["dhcp start"] if DHCP[0].is_started else []
            unload = ["dhcp stop", "dhcp destroy", "dhcp create"]
        else:
            load = [
                dhcp.is_started and f"dhcp start -@ {i + 1}"
                for i, dhcp in enumerate(DHCP)
            ]
            unload = (
                [f"dhcp stop -@ {i + 1}" for i in range(len(DHCP))]
                + [f"dhcp destroy -@ 1" for _ in range(len(DHCP))]
                + ["dhcp create 1"]
            )
        return Config.Module(
            order=300,
            config=[
                dict(
                    address=dhcp.address,
                    port=dhcp.port,
                    interface=dhcp.interface,
                    range=dhcp.range and dict(first=dhcp.range[0], last=dhcp.range[1]),
                    hostname=dhcp.hostname,
                    options={
                        str(k or "all"): v for k, v in dhcp.dump_options().items()
                    },
                    # hosts=dhcp.hosts,
                )
                for dhcp in DHCP
            ],
            scripts=dict(load=load, unload=unload),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        yield f"dhcp create {len(config.config)}"
        for i, item in enumerate(config.config):
            item: dict
            index = f" -@ {i + 1}" if len(config.config) > 1 else ""
            if item.get("address") != "0.0.0.0" or item.get("port") != 67:
                if item.get("port") != 67:
                    yield f"dhcp listen{index} {item['address']} {item['port']}"
                else:
                    yield f"dhcp listen{index} {item['address']}"
            if item.get("interface"):
                yield f"dhcp interface{index} {item['interface']}"
            if item.get("range"):
                yield (
                    f"dhcp range{index} {item['range'].get('first')} "
                    f"{item['range'].get('last')}"
                )
            if item.get("hostname") != "pynetkit":
                yield f"dhcp hostname{index} " + (item["hostname"] or '""')
            if isinstance(item.get("options"), dict):
                for client, options in item["options"].items():
                    client_arg = f" {client}" if client != "all" else ""
                    for option, data in options.items():
                        yield f'dhcp option{index} {option} "{data}"{client_arg}'


cli.section("Module operation", start, stop, create, destroy)
cli.section("Primary options", listen, interface, range_)
cli.section("Additional options", hostname, option)
COMMAND = CommandModule()
