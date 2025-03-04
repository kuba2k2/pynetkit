#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from ipaddress import IPv4Address
from logging import error, warning
from types import FunctionType
from typing import Generator

import click
import cloup
from click import Choice, Context
from prettytable.colortable import ColorTable, Themes

from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
    async_command,
    index_option,
)
from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import config_table, mce
from pynetkit.modules.proxy import ProxyModule, ProxyProtocol, ProxySource, ProxyTarget

PROXY: list[ProxyModule] = [ProxyModule()]


@cloup.group(
    name="proxy",
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@index_option(
    cls=ProxyModule,
    items=PROXY,
    name="proxy",
    title="proxy server",
    required=False,
)
@click.pass_context
def cli(ctx: Context, proxy: ProxyModule | None):
    if ctx.invoked_subcommand:
        return
    if not PROXY:
        warning("No proxy servers are created")
        return
    servers = [proxy] if proxy else PROXY

    for i, proxy in enumerate(servers):
        config_table(
            f"Proxy server #{PROXY.index(proxy) + 1}",
            (
                "State",
                (f"§aStarted§r" if proxy.is_started else "§8Stopped"),
            ),
            ("Listen address", proxy.address),
            *(
                ("", f":{port} ({protocol.name})")
                for port, protocol in sorted(proxy.ports.items())
            ),
            no_top=i > 0,
            color=True,
        )
        table = ColorTable(
            [" ", "Source", "Target"],
            theme=Themes.OCEAN_DEEP,
        )
        table.title = "Configuration"
        table.align = "l"
        for idx, item in enumerate(proxy.proxy_db):
            if isinstance(item, tuple):
                # print simple records
                source: ProxySource = item[0]
                target: ProxyTarget = item[1]
                table.add_row([idx + 1, str(source), str(target)])
            elif isinstance(item, FunctionType):
                # for now, ignore handlers since they aren't added via CLI
                continue
        result = table.get_string()
        _, _, result = result.partition("\n")
        result = result.strip()
        click.echo(result)


@cloup.command(help="Create new proxy server(s).")
@cloup.argument("total", default=0, help="Total number of proxy server instances.")
def create(total: int = 0):
    if not total:
        proxy = ProxyModule()
        PROXY.append(proxy)
        return
    while total > len(PROXY):
        proxy = ProxyModule()
        PROXY.append(proxy)
    mce(f"§fProxy module(s) created, total: {len(PROXY)}§r")


@cloup.command(help="Remove a PROXY server.")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@async_command
async def destroy(proxy: ProxyModule):
    await proxy.stop()
    PROXY.remove(proxy)
    mce(f"§fProxy module removed, total: {len(PROXY)}§r")


@cloup.command(help="Start the proxy server.")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@async_command
async def start(proxy: ProxyModule):
    await proxy.start()
    mce(f"§fProxy module started§r")


@cloup.command(help="Stop the proxy server.")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@async_command
async def stop(proxy: ProxyModule):
    await proxy.stop()
    mce(f"§fProxy module stopped§r")


@cloup.command(help="Set server listen address without starting.")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@cloup.argument("address", type=IPv4Address, help="Listen IP address.")
def listen(proxy: ProxyModule, address: IPv4Address):
    proxy.address = address
    mce(f"§fListen address set to: §d{proxy.address}§r")


@cloup.command(help="Set protocol association for the given port number.", name="port")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@cloup.argument("port", type=int, help="Listen port number.")
@cloup.argument(
    "protocol",
    type=Choice([p.name for p in ProxyProtocol], case_sensitive=False),
    help="Accepted protocol type (RAW/TLS/HTTP/ANY).",
)
def port_(proxy: ProxyModule, port: int, protocol: str):
    protocol = next(p for p in ProxyProtocol if p.name == protocol)
    ports = dict(proxy.ports)
    ports[port] = protocol
    proxy.ports = ports
    mce(f"§fPort §d{port}§f set to protocol §d{protocol}§r")


@cloup.command(help="Set a proxy target for the given source.", name="set")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@cloup.argument("shost", help='Source host name (RegEx, i.e. ".*").')
@cloup.argument("sport", type=int, help="Source port number (0 to match any).")
@cloup.argument(
    "sproto",
    type=Choice([p.name for p in ProxyProtocol], case_sensitive=False),
    help="Source protocol type (RAW/TLS/HTTP/ANY).",
)
@cloup.argument("thost", help='Target host name ("" means same as source).')
@cloup.argument("tport", type=int, help="Target port number (0 means same as source).")
@cloup.argument("via", required=False, help="HTTP proxy for the request (host:port).")
def set_(
    proxy: ProxyModule,
    shost: str,
    sport: int,
    sproto: str,
    thost: str,
    tport: int,
    via: str | None,
):
    sproto = next(p for p in ProxyProtocol if p.name == sproto)
    thost = thost or None
    if thost == ".*":
        thost = None
    if via and ":" in via:
        via_host, _, via_port = via.rpartition(":")
        via_port = int(via_port)
        via = via_host, via_port
    if sport and sport not in proxy.ports:
        warning(f"Source port {sport} is not configured as a proxy listen port")
    if via and (thost or tport) and sproto != ProxyProtocol.TLS:
        warning("If an HTTP proxy is used, target host/port is only applicable to TLS")
    for i, item in enumerate(proxy.proxy_db):
        if not isinstance(item, tuple):
            continue
        source: ProxySource = item[0]
        if shost != source.host or sport != source.port or sproto != source.protocol:
            continue
        target: ProxyTarget = item[1]
        proxy.proxy_db[i] = source, ProxyTarget(thost, tport, http_proxy=via)
        mce(
            f"§fProxy record replaced"
            f" - source: §d{source}§f"
            f" - was: §d{target}§f"
            f" - now: §d{proxy.proxy_db[i][1]}§r"
        )
        break
    else:
        source = ProxySource(shost, sport, sproto)
        target = ProxyTarget(thost, tport, http_proxy=via)
        proxy.proxy_db.append((source, target))
        mce(f"§fNew proxy added" f" - source: §d{source}§f" f" - now: §d{target}§f")


@cloup.command(help="Delete a proxy record from the database.")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@cloup.argument("index", type=int, help="What to delete.")
def delete(proxy: ProxyModule, index: int):
    index -= 1
    if index not in range(len(proxy.proxy_db)):
        error(f"Index not within allowed range (1..{len(proxy.proxy_db)})")
        return
    proxy.proxy_db.pop(index)
    mce(f"§fProxy record §d{index + 1}§f deleted§r.")


@cloup.command(help="Delete all proxy records from the database.")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
def clear(proxy: ProxyModule):
    num = len(proxy.proxy_db)
    proxy.proxy_db.clear()
    mce(f"§fProxy record database cleared (§d{num}§f record(s) deleted)§r.")


@cloup.command(help="Move a proxy record to a different position (order).")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@cloup.argument("index1", type=int, help="What to move.")
@cloup.argument("index2", type=int, help="Where to move it.")
def move(proxy: ProxyModule, index1: int, index2: int):
    index1 -= 1
    index2 -= 1
    if index1 not in range(len(proxy.proxy_db)):
        error(f"Index 1 not within allowed range (1..{len(proxy.proxy_db)})")
        return
    if index2 not in range(len(proxy.proxy_db)):
        error(f"Index 2 not within allowed range (1..{len(proxy.proxy_db)})")
        return
    item1 = proxy.proxy_db.pop(index1)
    proxy.proxy_db.insert(index2, item1)
    mce(f"§fProxy record §d{index1 + 1}§f moved to position §d{index2 + 1}§r.")


class CommandModule(BaseCommandModule):
    CLI = cli

    @staticmethod
    def _config_get_proxy_db(proxy: ProxyModule) -> Generator[dict, None, None]:
        for idx, item in enumerate(proxy.proxy_db):
            if isinstance(item, tuple):
                source: ProxySource = item[0]
                target: ProxyTarget = item[1]
                yield dict(
                    source=dict(
                        host=source.host,
                        port=source.port,
                        protocol=source.protocol.name,
                    ),
                    target=dict(
                        host=target.host,
                        port=target.port,
                        http_proxy=target.http_proxy
                        and f"{target.http_proxy[0]}:{target.http_proxy[1]}"
                        or None,
                    ),
                )
            elif isinstance(item, FunctionType):
                # for now, ignore handlers since they aren't added via CLI
                continue

    def config_get(self) -> Config.Module:
        if not PROXY:
            load = []
            unload = []
        elif len(PROXY) == 1:
            load = ["proxy start"] if PROXY[0].is_started else []
            unload = ["proxy stop", "proxy destroy", "proxy create"]
        else:
            load = [
                proxy.is_started and f"proxy start -@ {i + 1}"
                for i, proxy in enumerate(PROXY)
            ]
            unload = (
                [f"proxy stop -@ {i + 1}" for i in range(len(PROXY))]
                + [f"proxy destroy -@ 1" for _ in range(len(PROXY))]
                + ["proxy create 1"]
            )
        return Config.Module(
            order=300,
            config=[
                dict(
                    address=proxy.address,
                    ports=[
                        dict(port=port, protocol=protocol.name)
                        for port, protocol in sorted(proxy.ports.items())
                    ],
                    proxy_db=list(self._config_get_proxy_db(proxy)),
                )
                for proxy in PROXY
            ],
            scripts=dict(load=load, unload=unload),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        yield f"proxy create {len(config.config)}"
        for i, item in enumerate(config.config):
            item: dict
            index = f" -@ {i + 1}" if len(config.config) > 1 else ""
            if item.get("address") != "0.0.0.0":
                yield f"proxy listen{index} {item['address']}"
            if item.get("ports"):
                for record in item["ports"]:
                    yield f"proxy port{index} {record['port']} {record['protocol']}"
            if item.get("proxy_db"):
                for record in item["proxy_db"]:
                    source = record["source"]
                    target = record["target"]
                    yield (
                        f"proxy set{index} "
                        + (source["host"] or '""')
                        + f" {source['port']} {source['protocol']} "
                        + (target["host"] or '""')
                        + f" {target['port']} "
                        f"{target['http_proxy'] or ''}"
                    )


cli.section("Module operation", start, stop, create, destroy)
cli.section("Proxy configuration", listen, port_)
cli.section("Record management", set_, move, delete, clear)
COMMAND = CommandModule()
