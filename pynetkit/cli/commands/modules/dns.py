#  Copyright (c) Kuba Szczodrzyński 2024-10-21.

from ipaddress import IPv4Address
from logging import error, warning
from types import FunctionType
from typing import Any, Generator

import click
import cloup
from click import Context
from dnslib import QTYPE, DNSQuestion, DNSRecord
from prettytable.colortable import ColorTable, Themes

from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
    async_command,
    index_option,
)
from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import config_table, mc, mce
from pynetkit.modules.dns import DnsModule

DNS: list[DnsModule] = [DnsModule()]
upstream_handlers: dict[Any, tuple[IPv4Address, str, str]] = {}


@cloup.group(
    name="dns",
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@index_option(
    cls=DnsModule,
    items=DNS,
    name="dns",
    title="DNS server",
    required=False,
)
@click.pass_context
def cli(ctx: Context, dns: DnsModule | None):
    if ctx.invoked_subcommand:
        return
    if not DNS:
        warning("No DNS servers are created")
        return
    servers = [dns] if dns else DNS

    for i, dns in enumerate(servers):
        config_table(
            f"DNS server #{DNS.index(dns) + 1}",
            (
                "State",
                f"§aStarted§r ({dns.thread.name})" if dns.is_started else "§8Stopped",
            ),
            ("Listen address", f"{dns.address}:{dns.port}"),
            no_top=i > 0,
            color=True,
        )
        table = ColorTable(
            [" ", "Name", "Type", "Answer(s)"],
            theme=Themes.OCEAN_DEEP,
        )
        table.title = "Records"
        table.align = "l"
        for idx, item in enumerate(dns.dns_db):
            if isinstance(item, tuple):
                # print simple records
                name, type, answer = item
                table.add_row([idx + 1, name, type, "\n".join(str(r) for r in answer)])
            elif isinstance(item, FunctionType):
                # print handlers added via CLI
                record = upstream_handlers.get(item)
                if not record:
                    continue
                address, name, type = record
                table.add_row([idx + 1, name, type, mc(f"§8Upstream: §b{address}")])
        result = table.get_string()
        _, _, result = result.partition("\n")
        result = result.strip()
        click.echo(result)


@cloup.command(help="Create new DNS server(s).")
@cloup.argument("total", default=0, help="Total number of DNS server instances.")
def create(total: int = 0):
    if not total:
        dns = DnsModule()
        DNS.append(dns)
        return
    while total > len(DNS):
        dns = DnsModule()
        DNS.append(dns)
    mce(f"§fDNS module(s) created, total: {len(DNS)}§r")


@cloup.command(help="Remove a DNS server.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@async_command
async def destroy(dns: DnsModule):
    await dns.stop()
    DNS.remove(dns)
    mce(f"§fDNS module removed, total: {len(DNS)}§r")


@cloup.command(help="Start the DNS server, optionally supplying configuration.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@click.argument("address", type=IPv4Address, required=False)
@click.argument("port", type=int, required=False)
@async_command
async def start(
    dns: DnsModule,
    address: IPv4Address | None,
    port: int | None,
):
    if dns.is_started:
        mce(f"§fDNS module is already running§r")
        return
    if address is not None:
        dns.address = address
    if port is not None:
        dns.port = port
    await dns.start()
    mce(f"§fDNS module started§r")


@cloup.command(help="Stop the DNS server.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@async_command
async def stop(dns: DnsModule):
    await dns.stop()
    mce(f"§fDNS module stopped§r")


@cloup.command(help="Set server listen address without starting.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@cloup.argument("address", type=IPv4Address, help="Listen IP address.")
@cloup.argument("port", type=int, required=False, help="Listen port, default 53.")
def listen(dns: DnsModule, address: IPv4Address, port: int | None):
    dns.address = address
    if port is not None:
        dns.port = port
    mce(f"§fListen address set to: §d{dns.address}:{dns.port}§r")


@cloup.command(help="Set an answer for a DNS query.", name="set")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@cloup.argument("name", help='Name of the query (RegEx, i.e. ".*").')
@cloup.argument("type", help='Type of the query (RegEx, i.e. "A|CNAME").')
@cloup.argument(
    "answer",
    required=True,
    nargs=-1,
    help='Answer(s) for the query (i.e. IP address). Empty "" means NXDOMAIN.',
)
def set_(dns: DnsModule, name: str, type: str, answer: tuple[str]):
    answer = list(answer)
    if answer and answer[0] == "":
        answer = []
    for i, record in enumerate(dns.dns_db):
        if not isinstance(record, tuple):
            continue
        if name == record[0] and type == record[1]:
            dns.dns_db[i] = (name, type, answer)
            mce(
                f"§fRecord replaced"
                f" - name: §d{name}§f / type: §d{type}§f"
                f" - was: §d{', '.join(str(r) for r in record[2])}§f"
                f" - now: §d{', '.join(answer)}§r"
            )
            break
    else:
        dns.dns_db.append((name, type, answer))
        mce(
            f"§fNew record added"
            f" - name: §d{name}§f / type: §d{type}§f"
            f" - now: §d{', '.join(answer)}§r"
        )


@cloup.command(help="Forward a query to an upstream server.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@cloup.argument("address", type=IPv4Address, help="Upstream server name (IP address).")
@cloup.argument("name", help='Name of the query (RegEx, default: ".*").', default=".*")
@cloup.argument("type", help='Type of the query (RegEx, default: ".*").', default=".*")
def upstream(dns: DnsModule, address: IPv4Address, name: str, type: str):
    for i, handler in enumerate(dns.dns_db):
        if not isinstance(handler, FunctionType):
            continue
        record = upstream_handlers.get(handler)
        if not record:
            continue
        if name == record[1] and type == record[2]:
            # add a new handler and immediately pop it
            dns.add_upstream(address, name, type)
            new_handler = dns.dns_db.pop()
            # replace the old handler with the new one
            upstream_handlers.pop(handler)
            upstream_handlers[new_handler] = (address, name, type)
            # move it to the previous position
            dns.dns_db.insert(i, new_handler)
            mce(
                f"§fProxy replaced"
                f" - upstream was: §d{record[0]}§f"
                f" - upstream now: §d{upstream}§f"
                f" - name: §d{name}§f / type: §d{type}§f"
            )
            break
    else:
        new_handler = dns.add_upstream(address, name, type)
        upstream_handlers[new_handler] = (address, name, type)
        mce(
            f"§fNew proxy added"
            f" - upstream now: §d{address}§f"
            f" - name: §d{name}§f / type: §d{type}§f"
        )


@cloup.command(help="Delete a record from the database.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@cloup.argument("index", type=int, help="What to delete.")
def delete(dns: DnsModule, index: int):
    index -= 1
    if index not in range(len(dns.dns_db)):
        error(f"Index not within allowed range (1..{len(dns.dns_db)})")
        return
    dns.dns_db.pop(index)
    mce(f"§fRecord §d{index + 1}§f deleted§r.")


@cloup.command(help="Delete all records from the database.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
def clear(dns: DnsModule):
    num = len(dns.dns_db)
    dns.dns_db.clear()
    mce(f"§fRecord database cleared (§d{num}§f record(s) deleted)§r.")


@cloup.command(help="Move a record to a different position (order).")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@cloup.argument("index1", type=int, help="What to move.")
@cloup.argument("index2", type=int, help="Where to move it.")
def move(dns: DnsModule, index1: int, index2: int):
    index1 -= 1
    index2 -= 1
    if index1 not in range(len(dns.dns_db)):
        error(f"Index 1 not within allowed range (1..{len(dns.dns_db)})")
        return
    if index2 not in range(len(dns.dns_db)):
        error(f"Index 2 not within allowed range (1..{len(dns.dns_db)})")
        return
    item1 = dns.dns_db.pop(index1)
    dns.dns_db.insert(index2, item1)
    mce(f"§fRecord §d{index1 + 1}§f moved to position §d{index2 + 1}§r.")


@cloup.command(help="Move all upstream entries below local entries.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
def sort(dns: DnsModule):
    dns.dns_db = sorted(dns.dns_db, key=lambda r: 1 if isinstance(r, tuple) else 2)
    mce(f"§fRecord database sorted§r.")


@cloup.command(help="Try to resolve a query using the DNS module.")
@index_option(cls=DnsModule, items=DNS, name="dns", title="DNS server")
@cloup.argument("name", help="Query to resolve (i.e. domain name).")
@cloup.argument("type", help='Type of the query (default: "A").', default="A")
def query(dns: DnsModule, name: str, type: str):
    q = DNSRecord()
    q.add_question(DNSQuestion(name, getattr(QTYPE, type.upper())))
    r = dns.resolve(q, None)
    print(r)


class CommandModule(BaseCommandModule):
    CLI = cli

    @staticmethod
    def _config_get_dns_db(dns: DnsModule) -> Generator[dict, None, None]:
        for idx, item in enumerate(dns.dns_db):
            if isinstance(item, tuple):
                name, type, answer = item
                yield dict(name=name, type=type, answer=answer)
            elif isinstance(item, FunctionType):
                record = upstream_handlers.get(item)
                if not record:
                    continue
                address, name, type = record
                yield dict(upstream=address, name=name, type=type)

    def config_get(self) -> Config.Module:
        if not DNS:
            load = []
            unload = []
        elif len(DNS) == 1:
            load = ["dns start"] if DNS[0].is_started else []
            unload = ["dns stop", "dns destroy", "dns create"]
        else:
            load = [
                dns.is_started and f"dns start -@ {i + 1}" for i, dns in enumerate(DNS)
            ]
            unload = (
                [f"dns stop -@ {i + 1}" for i in range(len(DNS))]
                + [f"dns destroy -@ 1" for _ in range(len(DNS))]
                + ["dns create 1"]
            )
        return Config.Module(
            order=300,
            config=[
                dict(
                    address=dns.address,
                    port=dns.port,
                    dns_db=list(self._config_get_dns_db(dns)),
                )
                for dns in DNS
            ],
            scripts=dict(load=load, unload=unload),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        yield f"dns create {len(config.config)}"
        for i, item in enumerate(config.config):
            item: dict
            index = f" -@ {i + 1}" if len(config.config) > 1 else ""
            if item.get("address") != "0.0.0.0" or item.get("port") != 53:
                if item.get("port") != 53:
                    yield f"dns listen{index} {item['address']} {item['port']}"
                else:
                    yield f"dns listen{index} {item['address']}"
            if item.get("dns_db"):
                for record in item["dns_db"]:
                    if "answer" in record:
                        yield (
                            f"dns set{index} {record['name']} "
                            f"{record['type']} " + (" ".join(record["answer"]) or '""')
                        )
                    elif "upstream" in record:
                        yield (
                            f"dns upstream{index} {record['upstream']} "
                            f"{record['name']} {record['type']}"
                        )


cli.section("Module operation", start, stop, create, destroy)
cli.section("Server configuration", listen)
cli.section("Record management", set_, upstream, delete, clear)
cli.section("Record priority & validation", move, sort, query)
COMMAND = CommandModule()
