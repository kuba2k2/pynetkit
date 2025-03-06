#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from datetime import timedelta
from ipaddress import IPv4Address
from logging import error, warning
from typing import Generator

import click
import cloup
import pytimeparse as pytimeparse
from click import Context

from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
    async_command,
    index_option,
)
from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import config_table, mce
from pynetkit.modules.ntp import NtpModule

NTP: list[NtpModule] = [NtpModule()]


@cloup.group(
    name="ntp",
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@index_option(
    cls=NtpModule,
    items=NTP,
    name="ntp",
    title="NTP server",
    required=False,
)
@click.pass_context
def cli(ctx: Context, ntp: NtpModule | None):
    if ctx.invoked_subcommand:
        return
    if not NTP:
        warning("No NTP servers are created")
        return
    servers = [ntp] if ntp else NTP

    for i, ntp in enumerate(servers):
        config_table(
            f"NTP server #{NTP.index(ntp) + 1}",
            (
                "State",
                f"§aStarted§r ({ntp.thread.name})" if ntp.is_started else "§8Stopped",
            ),
            ("Listen address", f"{ntp.address}:{ntp.port}"),
            no_top=i > 0,
            color=True,
        )


@cloup.command(help="Create new NTP server(s).")
@cloup.argument("total", default=0, help="Total number of NTP server instances.")
def create(total: int = 0):
    if not total:
        ntp = NtpModule()
        NTP.append(ntp)
        return
    while total > len(NTP):
        ntp = NtpModule()
        NTP.append(ntp)
    mce(f"§fNTP module(s) created, total: {len(NTP)}§r")


@cloup.command(help="Remove a NTP server.")
@index_option(cls=NtpModule, items=NTP, name="ntp", title="NTP server")
@async_command
async def destroy(ntp: NtpModule):
    await ntp.stop()
    NTP.remove(ntp)
    mce(f"§fNTP module removed, total: {len(NTP)}§r")


@cloup.command(help="Start the NTP server, optionally supplying configuration.")
@index_option(cls=NtpModule, items=NTP, name="ntp", title="NTP server")
@click.argument("address", type=IPv4Address, required=False)
@click.argument("port", type=int, required=False)
@async_command
async def start(
    ntp: NtpModule,
    address: IPv4Address | None,
    port: int | None,
):
    if ntp.is_started:
        mce(f"§fNTP module is already running§r")
        return
    if address is not None:
        ntp.address = address
    if port is not None:
        ntp.port = port
    await ntp.start()
    mce(f"§fNTP module started§r")


@cloup.command(help="Stop the NTP server.")
@index_option(cls=NtpModule, items=NTP, name="ntp", title="NTP server")
@async_command
async def stop(ntp: NtpModule):
    await ntp.stop()
    mce(f"§fNTP module stopped§r")


@cloup.command(help="Set server listen address without starting.")
@index_option(cls=NtpModule, items=NTP, name="ntp", title="NTP server")
@cloup.argument("address", type=IPv4Address, help="Listen IP address.")
@cloup.argument("port", type=int, required=False, help="Listen port, default 67.")
def listen(ntp: NtpModule, address: IPv4Address, port: int | None):
    ntp.address = address
    if port is not None:
        ntp.port = port
    mce(f"§fListen address set to: §d{ntp.address}:{ntp.port}§r")


@cloup.command(
    help="Set time offset for a particular host.",
    context_settings={"ignore_unknown_options": True},
)
@index_option(cls=NtpModule, items=NTP, name="ntp", title="NTP server")
@cloup.argument("address", type=IPv4Address, help="Target host address.")
@cloup.argument(
    "time_offset",
    type=str,
    nargs=-1,
    help="Time offset to apply (like '5h', '-1 day', etc). Empty (\"\") to disable.",
)
def offset(ntp: NtpModule, address: IPv4Address, time_offset: tuple[str]):
    time_offset = " ".join(time_offset)
    if not time_offset:
        mce(f"§fTime offset for host §d{address}§f disabled§r")
        ntp.offset.pop(address, None)
        return
    sign = "+"
    if time_offset.startswith("-"):
        sign = "-"
        time_offset = time_offset[1:]
    seconds = pytimeparse.parse(time_offset)
    if seconds is None:
        error("Couldn't parse the supplied time offset")
        return
    delta = timedelta(seconds=seconds)
    mce(f"§fTime offset for host §d{address}§f set to §d{sign}{delta}§r")
    if sign == "-":
        delta = -delta
    ntp.offset[address] = delta


class CommandModule(BaseCommandModule):
    CLI = cli

    def config_get(self) -> Config.Module:
        if not NTP:
            load = []
            unload = []
        elif len(NTP) == 1:
            load = ["ntp start"] if NTP[0].is_started else []
            unload = ["ntp stop", "ntp destroy", "ntp create"]
        else:
            load = [
                ntp.is_started and f"ntp start -@ {i + 1}" for i, ntp in enumerate(NTP)
            ]
            unload = (
                [f"ntp stop -@ {i + 1}" for i in range(len(NTP))]
                + [f"ntp destroy -@ 1" for _ in range(len(NTP))]
                + ["ntp create 1"]
            )
        return Config.Module(
            order=300,
            config=[
                dict(
                    address=ntp.address,
                    port=ntp.port,
                    offset={
                        str(address): int(delta.total_seconds())
                        for address, delta in ntp.offset.items()
                    },
                )
                for ntp in NTP
            ],
            scripts=dict(load=load, unload=unload),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        yield f"ntp create {len(config.config)}"
        for i, item in enumerate(config.config):
            item: dict
            index = f" -@ {i + 1}" if len(config.config) > 1 else ""
            if item.get("address") != "0.0.0.0" or item.get("port") != 123:
                if item.get("port") != 123:
                    yield f"ntp listen{index} {item['address']} {item['port']}"
                else:
                    yield f"ntp listen{index} {item['address']}"
            for address, seconds in item.get("offset", {}).items():
                yield f"ntp offset{index} {address} {seconds} sec"


cli.section("Module operation", start, stop, create, destroy)
cli.section("Primary options", listen, offset)
COMMAND = CommandModule()
