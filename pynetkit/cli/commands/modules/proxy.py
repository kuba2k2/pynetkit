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
from pynetkit.modules.proxy import (
    ProxyAddress,
    ProxyModule,
    ProxyPortMode,
    ProxyProtocol,
    ProxySocket,
)

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
                ("", f":{port} ({mode.name})")
                for port, mode in sorted(proxy.ports.items())
            ),
            no_top=i > 0,
            color=True,
        )

        table = ColorTable(
            [" ", "Pattern", "Rewrite", "Via"],
            theme=Themes.OCEAN_DEEP,
        )
        table.title = "Configuration"
        table.align = "l"

        for idx, item in enumerate(proxy.proxy_db):
            if isinstance(item, tuple):
                # print simple records
                pattern: ProxyAddress = item[0]
                rewrite: ProxyAddress = item[1]
                via = f"{rewrite.via[0]}:{rewrite.via[1]}" if rewrite.via else ""
                table.add_row([idx + 1, str(pattern), str(rewrite), via])
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
    "mode",
    type=Choice([m.name for m in ProxyPortMode], case_sensitive=False),
    help="Port matching mode (DETECT/TCP/TLS/HTTP/HTTPS).",
)
def port_(proxy: ProxyModule, port: int, mode: str):
    mode = next(m for m in ProxyPortMode if m.name == mode)
    ports = dict(proxy.ports)
    ports[port] = mode
    proxy.ports = ports
    mce(f"§fPort §d{port}§f set with matching mode §d{mode}§r")


@cloup.command(help="Set a proxy target for the given source.", name="set")
@index_option(cls=ProxyModule, items=PROXY, name="proxy", title="proxy server")
@cloup.argument(
    "pattern",
    help='Source [proto://]host[:port][/path] (accepts RegEx). Use "" to match any.',
)
@cloup.argument(
    "rewrite",
    help='Target [proto://]host[:port][/path]. Use "" to leave source unchanged.',
)
@cloup.argument(
    "via",
    required=False,
    help="HTTP proxy for the request, optional (host:port).",
)
def set_(
    proxy: ProxyModule,
    pattern: str,
    rewrite: str,
    via: str | None,
):
    pattern = ProxyAddress.parse(pattern)
    if not pattern:
        error(f"Couldn't parse pattern string")
    rewrite = ProxyAddress.parse(rewrite)
    if not rewrite:
        error(f"Couldn't parse rewrite string")
        return
    if not pattern:
        return

    via_str = ""
    if via and ":" in via:
        via_host, _, via_port = via.rpartition(":")
        via_port = int(via_port)
        rewrite.via = via_host, via_port
        via_str = f" via §d{via_host}:{via_port}§r"

    # check some known bad usages
    if pattern.port and pattern.port not in proxy.ports:
        warning(f"Pattern port {pattern.port} is not configured as a proxy listen port")

    for i, item in enumerate(proxy.proxy_db):
        if not isinstance(item, tuple):
            continue
        prev_pattern: ProxyAddress = item[0]
        if prev_pattern != pattern:
            continue
        prev_rewrite: ProxyAddress = item[1]
        proxy.proxy_db[i] = pattern, rewrite
        mce(
            f"§fProxy record replaced"
            f" - pattern: §d{pattern}§f"
            f" - was: §d{prev_rewrite}§f"
            f" - now: §d{rewrite}§r{via_str}"
        )
        break
    else:
        proxy.proxy_db.append((pattern, rewrite))
        mce(
            f"§fNew proxy added"
            f" - pattern: §d{pattern}§f"
            f" - rewrite: §d{rewrite}§f{via_str}"
        )


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
    address = ProxyAddress.parse(request)
    if not address:
        error(f"Couldn't parse request URL: {request}")
        return
    if not address.host:
        error("Request host name missing")
        return

    if address.port and address.port not in proxy.ports:
        warning(f"Request port {address.port} is not configured as a proxy listen port")
    if not address.protocol:
        warning("Request protocol not specified, assuming TCP")
        address.protocol = ProxyProtocol.TCP

    if not address.port:
        if address.protocol == ProxyProtocol.TCP:
            address.port = 80
        elif address.protocol == ProxyProtocol.TLS:
            address.port = 443

    info(f"Request: {address}")
    # noinspection bad-argument-type
    target = proxy.resolve_target(ProxySocket(address, io=None))
    info(f"Rewrite: {target}")


class CommandModule(BaseCommandModule):
    CLI = cli

    @staticmethod
    def _config_get_proxy_db(proxy: ProxyModule) -> Generator[dict, None, None]:
        for idx, item in enumerate(proxy.proxy_db):
            if isinstance(item, tuple):
                pattern: ProxyAddress = item[0]
                rewrite: ProxyAddress = item[1]
                yield dict(
                    pattern=pattern.dump(),
                    rewrite=rewrite.dump(),
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
                        dict(port=port, mode=mode.name)
                        for port, mode in sorted(proxy.ports.items())
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
                    if "protocol" in record:
                        record["mode"] = dict(
                            ANY="DETECT", RAW="TCP", TLS="HTTPS", HTTP="HTTP"
                        )[record["protocol"]]
                    yield f"proxy port{index} {record['port']} {record['mode']}"
            if item.get("proxy_db"):
                yield f"proxy clear{index}"
                for record in item["proxy_db"]:
                    if "source" in record:
                        pattern = record["source"]
                        if pattern["protocol"] == "ANY":
                            pattern["protocol"] = None
                    else:
                        pattern = record["pattern"]
                    if "target" in record:
                        rewrite = record["target"]
                        rewrite["via"] = rewrite.get("http_proxy")
                    else:
                        rewrite = record["rewrite"]
                    pattern_str = ProxyAddress.load(pattern)
                    rewrite_str = ProxyAddress.load(rewrite)
                    yield (
                        f'proxy set{index} "{pattern_str}" "{rewrite_str}"'
                        f" {rewrite.get('via') or ''}"
                    )


cli.section("Module operation", start, stop, create, destroy)
cli.section("Proxy configuration", listen, port_)
cli.section("Record management", set_, delete, clear)
cli.section("Record priority & validation", move, test)
COMMAND = CommandModule()
