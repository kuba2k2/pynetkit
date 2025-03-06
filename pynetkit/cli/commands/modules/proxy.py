#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from ipaddress import IPv4Address
from logging import error, info, warning
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
    if proxy.is_started:
        mce(f"§fProxy module is already running§r")
        return
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
@cloup.argument(
    "source",
    help='Source [scheme://]host[:port][/path] (accepts RegEx). Use ".*" to match any.',
)
@cloup.argument(
    "target",
    help='Target host[:port][/path]. Use ".*" to leave source unchanged.',
)
@cloup.argument(
    "via",
    required=False,
    help="HTTP proxy for the request, optional (host:port).",
)
def set_(
    proxy: ProxyModule,
    source: str,
    target: str,
    via: str | None,
):
    source = ProxySource.parse(source)
    if not source:
        error(f"Couldn't parse source URL: {source}")
    target = ProxyTarget.parse(target)
    if not target:
        error(f"Couldn't parse target URL: {target}")
        return
    if not source:
        return

    if via and ":" in via:
        via_host, _, via_port = via.rpartition(":")
        via_port = int(via_port)
        target.http_proxy = via_host, via_port

    # check some known bad usages
    if target.host == ".*":
        target.host = None
    if source.port and source.port not in proxy.ports:
        warning(f"Source port {source.port} is not configured as a proxy listen port")
    if source.path and source.protocol != ProxyProtocol.HTTP:
        if source.protocol != ProxyProtocol.ANY:
            error("Source path can only be used for HTTP")
            return
        source.protocol = ProxyProtocol.HTTP

    for i, item in enumerate(proxy.proxy_db):
        if not isinstance(item, tuple):
            continue
        prev_source: ProxySource = item[0]
        if prev_source != source:
            continue
        prev_target: ProxyTarget = item[1]
        proxy.proxy_db[i] = source, target
        mce(
            f"§fProxy record replaced"
            f" - source: §d{source}§f"
            f" - was: §d{prev_target}§f"
            f" - now: §d{target}§r"
        )
        break
    else:
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


@cloup.command(help="Test proxy routing target for the given URL.")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@cloup.argument("request", help="Source request URL/hostname.")
def test(proxy: ProxyModule, request: str):
    request = ProxySource.parse(request)
    if not request:
        error(f"Couldn't parse request URL: {request}")
        return
    if not request.host or request.host == ".*":
        error("Request host name missing")
        return

    if request.port and request.port not in proxy.ports:
        warning(f"Request port {request.port} is not configured as a proxy listen port")
    if request.protocol == ProxyProtocol.ANY:
        warning("Request protocol not specified, assuming HTTP")
        request.protocol = ProxyProtocol.HTTP

    if request.path and request.protocol != ProxyProtocol.HTTP:
        if request.protocol != ProxyProtocol.ANY:
            error("Request path can only be used for HTTP")
            return
        request.protocol = ProxyProtocol.HTTP

    if not request.port:
        if request.protocol == ProxyProtocol.HTTP:
            request.port = 80
        elif request.protocol == ProxyProtocol.TLS:
            request.port = 443
        else:
            error("Request port is required for raw TCP")
            return

    info(f"Source: {request}")
    target = proxy.resolve_target(request, None)
    info(f"Target: {target}")


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
                        path=source.path,
                        protocol=source.protocol.name,
                    ),
                    target=dict(
                        host=target.host,
                        port=target.port,
                        path=target.path,
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
                yield f"proxy clear{index}"
                for record in item["proxy_db"]:
                    source = record["source"]
                    target = record["target"]
                    source_url = source["host"] or ".*"
                    target_url = target["host"] or ".*"
                    if source.get("port"):
                        source_url += f":{source['port']}"
                    if target.get("port"):
                        target_url += f":{target['port']}"
                    if source.get("path"):
                        source_url += source["path"]
                    if target.get("path"):
                        target_url += target["path"]
                    if source.get("protocol", "ANY") != "ANY":
                        source_url = source["protocol"].lower() + "://" + source_url
                    yield (
                        f'proxy set{index} "{source_url}" "{target_url}"'
                        f" {target['http_proxy'] or ''}"
                    )


cli.section("Module operation", start, stop, create, destroy)
cli.section("Proxy configuration", listen, port_)
cli.section("Record management", set_, delete, clear)
cli.section("Record priority & validation", move, test)
COMMAND = CommandModule()
