#  Copyright (c) Kuba Szczodrzyński 2024-10-27.

from typing import Generator

import click
import cloup
from click import Context
from prettytable.colortable import ColorTable, Themes

from pynetkit.cli.command import get_module
from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
    async_command,
)
from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import config_table, mce
from pynetkit.modules.wifi import WifiModule
from pynetkit.types import NetworkAdapter, WifiNetwork

from .network import NetworkConfig, print_no_mapping

wifi = WifiModule()
# noinspection PyUnresolvedReferences
CONFIG: dict[int, NetworkConfig] = get_module("network").CONFIG
SCAN: dict[str, WifiNetwork] = {}
STACONFIG: dict[int, WifiNetwork] = {}
APCONFIG: dict[int, WifiNetwork] = {}

MODE_NAMES = {
    NetworkAdapter.Type.WIRELESS: "STA+AP",
    NetworkAdapter.Type.WIRELESS_STA: "STA",
    NetworkAdapter.Type.WIRELESS_AP: "AP",
}


async def wifi_start():
    if not wifi.is_started:
        await wifi.start()


async def get_adapter(index: int, ap: bool) -> tuple[int, NetworkAdapter | None]:
    await wifi_start()
    types = [NetworkAdapter.Type.WIRELESS]
    if ap:
        types.append(NetworkAdapter.Type.WIRELESS_AP)
    else:
        types.append(NetworkAdapter.Type.WIRELESS_STA)
    typestr = ", ".join(t.name for t in types)
    if not CONFIG:
        print_no_mapping()
        return index, None
    if index:
        if index not in CONFIG:
            mce(f"§cAdapter index §d{index}§c is not mapped.§r")
            return index, None
        adapter = CONFIG[index].adapter
        if adapter.type not in types:
            mce(f"§cAdapter §d{adapter.name}§c is not of type(s) §d{typestr}§r.")
            return index, None
        return index, adapter
    mce(f"§8Selecting first available adapter of type(s) §d{typestr}§r.")
    for idx, config in CONFIG.items():
        if config.adapter.type in types:
            return idx, config.adapter
    mce(f"§cNo adapter of type(s) §d{typestr}§c is mapped.§r")
    return index, None


@cloup.group(
    name="wifi",
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.pass_context
def cli(ctx: Context):
    if ctx.invoked_subcommand:
        return

    config_table(
        f"Wi-Fi module",
        (
            "State",
            (f"§aActive§r ({wifi.thread.name})" if wifi.is_started else "§8Idle"),
        ),
        color=True,
    )

    if not CONFIG:
        print_no_mapping()
        return
    table = ColorTable(
        [" ", "Name", "Mode(s)", "Configured as", "Config SSID", "Config password"],
        theme=Themes.OCEAN_DEEP,
    )
    table.title = "Wi-Fi adapter configuration"
    table.align = "l"
    for idx, config in sorted(CONFIG.items()):
        config: NetworkConfig
        if config.adapter.type not in MODE_NAMES:
            continue
        network = STACONFIG.get(idx) or APCONFIG.get(idx)
        table.add_row(
            [
                idx,
                config.adapter.name,
                MODE_NAMES[config.adapter.type],
                "STA" if idx in STACONFIG else "AP" if idx in APCONFIG else "None",
                network and network.ssid or "",
                network
                and network.password
                and network.password.decode("utf-8", "replace")
                or "",
            ]
        )
    click.echo(table.get_string())


@cloup.command(help="Show the current status of the Wi-Fi adapters.")
@async_command
async def show():
    await wifi_start()
    if not CONFIG:
        print_no_mapping()
        return
    for idx, config in sorted(CONFIG.items()):
        config: NetworkConfig
        if config.adapter.type not in MODE_NAMES:
            continue
        mce(f"§3---- Adapter {idx} - §d{config.adapter.name}§3 ----")
        if config.adapter.type in (
            NetworkAdapter.Type.WIRELESS,
            NetworkAdapter.Type.WIRELESS_STA,
        ):
            state = await wifi.get_station_state(config.adapter)
            if state:
                mce(f"§fStation - §aConnected to §d{state.ssid}§r")
            else:
                mce(f"§fStation - §8Not connected§r")
        if config.adapter.type in (
            NetworkAdapter.Type.WIRELESS,
            NetworkAdapter.Type.WIRELESS_AP,
        ):
            state = await wifi.get_access_point_state(config.adapter)
            if state:
                mce(f"§fAccess Point - §aStarted with SSID §d{state.ssid}§r")
                clients = await wifi.get_access_point_clients(config.adapter)
                if clients:
                    mce(
                        "§fConnected clients:\n - §d"
                        + "§f\n - §d".join(str(mac) for mac in clients)
                        + "§r"
                    )
                else:
                    mce("§fNo connected clients§r")
            else:
                mce(f"§fAccess Point - §8Not started§r")
        mce("")


@cloup.command(help="Scan for Wi-Fi networks.")
@click.option("-@", "--index", type=int, required=False, help="Adapter index.")
@async_command
async def scan(index: int):
    index, adapter = await get_adapter(index, ap=False)
    if not adapter:
        return
    networks = await wifi.scan_networks(adapter)
    networks = sorted(networks, key=lambda n: (-n.rssi, n.ssid))
    table = ColorTable(
        ["SSID", "Auth", "Cipher", "RSSI", "Ad-hoc"],
        theme=Themes.OCEAN_DEEP,
    )
    table.title = "Available Wi-Fi networks"
    table.align = "l"
    for network in networks:
        SCAN[network.ssid] = network
        auth = network.auth and network.auth.name or "Open"
        auth = auth.replace("|", ", ").replace("_", " ")
        auth = auth.replace(" PSK", "").replace(" ENT", " Enterprise")
        table.add_row(
            [
                network.ssid,
                auth,
                network.cipher and network.cipher.name or "",
                f"{network.rssi} dBm",
                network.ad_hoc and "Yes" or "",
            ]
        )
    click.echo(table.get_string())


@cloup.command(help="Connect to a Wi-Fi network.")
@cloup.argument("ssid", help="Network SSID.")
@cloup.argument("password", required=False, help="Network password (if protected).")
@click.option("-@", "--index", type=int, required=False, help="Adapter index.")
@async_command
async def connect(index: int, ssid: str, password: str):
    index, adapter = await get_adapter(index, ap=False)
    if not adapter:
        return
    state = await wifi.get_station_state(adapter)
    # cache the connected network
    if state:
        SCAN[state.ssid] = state
    # scan if SSID not cached
    if ssid not in SCAN:
        mce("§fScanning for Wi-Fi networks...§r")
        networks = await wifi.scan_networks(adapter)
        for network in networks:
            SCAN[network.ssid] = network
    # bail out if not found in scanning
    if ssid not in SCAN:
        mce(f"§cNetwork with SSID §d{ssid}§c is not found.§r")
        return
    # get the network object and fill it with the password
    network = SCAN[ssid]
    network.password = password and password.encode("utf-8") or None
    # fail if a password is needed
    if network.protected and not network.password:
        mce(f"§cNetwork with SSID §d{ssid}§c is password-protected.§r")
        return
    # exit successfully if already connected
    if state and ssid == state.ssid:
        mce(f"§fAlready connected to §d{state.ssid}§r.")
        STACONFIG[index] = network
        APCONFIG.pop(index, None)
        return
    # try to connect
    mce(f"§fConnecting to §d{network.ssid}§r...")
    await wifi.start_station(adapter, network)
    # check the connection result
    state = await wifi.get_station_state(adapter)
    if not state:
        mce(f"§cCouldn't connect to the network - wrong password?§r")
        return
    if network.ssid != state.ssid:
        mce(
            f"§cConnected to a different network §d({state.ssid})§c "
            f"than requested §d({network.ssid})§r."
        )
        return
    # success
    mce(f"§fConnected to Wi-Fi network §d{state.ssid}§r.")
    STACONFIG[index] = network
    APCONFIG.pop(index, None)


@cloup.command(help="Disconnect the adapter from Wi-Fi.")
@click.option("-@", "--index", type=int, required=False, help="Adapter index.")
@async_command
async def disconnect(index: int):
    index, adapter = await get_adapter(index, ap=False)
    if not adapter:
        return
    state = await wifi.get_station_state(adapter)
    if not state:
        mce(f"§eNot connected to any network§r.")
        STACONFIG.pop(index, None)
        return
    await wifi.stop_station(adapter)
    state2 = await wifi.get_station_state(adapter)
    if state2:
        mce(f"§cCouldn't disconnect from §d{state.ssid}§r.")
        return
    mce(f"§fDisconnected from §d{state.ssid}§r.")
    STACONFIG.pop(index, None)


@cloup.command(help="Start a Wi-Fi access point.")
@cloup.argument("ssid", help="Network SSID.")
@cloup.argument("password", required=False, help="Network password (optional).")
@click.option("-@", "--index", type=int, required=False, help="Adapter index.")
@async_command
async def ap(index: int, ssid: str, password: str):
    index, adapter = await get_adapter(index, ap=True)
    if not adapter:
        return
    # create the network object
    network = WifiNetwork(ssid, password and password.encode("utf-8") or None)
    # exit successfully if already running
    state = await wifi.get_access_point_state(adapter)
    if state and network.ssid == state.ssid and network.password == state.password:
        mce(f"§fAlready running with SSID §d{state.ssid}§f and this password.§r")
        APCONFIG[index] = network
        STACONFIG.pop(index, None)
        return
    # try to start the AP
    mce(f"§fStarting access point with SSID §d{network.ssid}§r...")
    await wifi.start_access_point(adapter, network)
    # check the result
    state = await wifi.get_access_point_state(adapter)
    if not state:
        mce(f"§cCouldn't start the access point§r")
        return
    if network.ssid != state.ssid or network.password != state.password:
        mce(
            f"§cStarted a different access point §d({state.ssid})§c "
            f"than requested §d({network.ssid})§r."
        )
        return
    # success
    mce(f"§fStarted an access point with SSID §d{state.ssid}§r.")
    APCONFIG[index] = network
    STACONFIG.pop(index, None)


@cloup.command(help="Stop a Wi-Fi access point.")
@click.option("-@", "--index", type=int, required=False, help="Adapter index.")
@async_command
async def apstop(index: int):
    index, adapter = await get_adapter(index, ap=True)
    if not adapter:
        return
    state = await wifi.get_access_point_state(adapter)
    if not state:
        mce(f"§eAccess point is not started§r.")
        APCONFIG.pop(index, None)
        return
    await wifi.stop_access_point(adapter)
    state2 = await wifi.get_access_point_state(adapter)
    if state2:
        mce(f"§cCouldn't stop access point §d{state.ssid}§r.")
        return
    mce(f"§fAccess point with SSID §d{state.ssid}§f is stopped.§r")
    APCONFIG.pop(index, None)


class CommandModule(BaseCommandModule):
    CLI = cli

    @staticmethod
    def _network_to_dict(network: WifiNetwork | None) -> dict | None:
        if network:
            return dict(ssid=network.ssid, password=network.password.decode())
        return None

    def config_get(self) -> Config.Module:
        return Config.Module(
            order=100,
            config=dict(
                adapters=[
                    dict(
                        index=idx,
                        sta=self._network_to_dict(STACONFIG.get(idx)),
                        ap=self._network_to_dict(APCONFIG.get(idx)),
                    )
                    for idx, config in sorted(CONFIG.items())
                ]
            ),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        for item in config.config.get("adapters", []):
            item: dict
            index = item["index"]
            sta: dict = item.get("sta")
            ap_: dict = item.get("ap")
            if sta:
                yield f'wifi connect -@{index} "{sta["ssid"]}" "{sta["password"]}"'
            if ap_:
                yield f'wifi ap -@{index} "{ap_["ssid"]}" "{ap_["password"]}"'


cli.section("Primary commands", show, scan)
cli.section("Wi-Fi station", connect, disconnect)
cli.section("Wi-Fi access point", ap, apstop)
COMMAND = CommandModule()
