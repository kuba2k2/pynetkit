#  Copyright (c) Kuba Szczodrzyński 2024-10-18.

from ipaddress import IPv4Address, IPv4Interface
from logging import warning
from typing import Generator

import click
import cloup
from click import Context

from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
    async_command,
    index_option,
)
from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import config_table, mce
from pynetkit.modules.dhcp import DhcpModule

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
        if dhcp.hosts:
            leases = [("Active leases", "")]
            leases += [("", f"{mac} - {ip}") for mac, ip in dhcp.hosts.items()]
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
            ("DNS address", dhcp.dns or "Same as server"),
            ("Router address", dhcp.router or "Same as server"),
            ("Host name", dhcp.hostname or "Not set"),
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


@cloup.command(help="Set DNS address.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@cloup.argument(
    "address",
    type=IPv4Address,
    help="DNS server address (or 0.0.0.0 to use server address).",
)
def dns(dhcp: DhcpModule, address: IPv4Address):
    if int(address) == 0:
        address = None
    dhcp.dns = address
    mce(f"§fDNS address set to: §d{dhcp.dns or '(server address)'}§r")


@cloup.command(help="Set router address.")
@index_option(cls=DhcpModule, items=DHCP, name="dhcp", title="DHCP server")
@cloup.argument(
    "address",
    type=IPv4Address,
    help="Router address (or 0.0.0.0 to use server address).",
)
def router(dhcp: DhcpModule, address: IPv4Address):
    if int(address) == 0:
        address = None
    dhcp.router = address
    mce(f"§fRouter address set to: §d{dhcp.router or '(server address)'}§r")


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
                    dns=dhcp.dns,
                    router=dhcp.router,
                    hostname=dhcp.hostname,
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
            if item.get("dns"):
                yield f"dhcp dns{index} {item['dns']}"
            if item.get("router"):
                yield f"dhcp router{index} {item['router']}"
            if item.get("hostname") != "pynetkit":
                yield f"dhcp hostname{index} " + (item["hostname"] or '""')


cli.section("Module operation", start, stop, create, destroy)
cli.section("Primary options", listen, interface, range_)
cli.section("Additional options", dns, router, hostname)
COMMAND = CommandModule()
