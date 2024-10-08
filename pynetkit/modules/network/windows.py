#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import asyncio

from win32wifi import Win32Wifi

from pynetkit.modules.base import module_thread
from pynetkit.types import Ip4Config, NetworkInterface
from pynetkit.utils.windows import iphlpapi, wlanapi

from .common import NetworkCommon

IFACE_BLACKLIST = [
    "VMware",
    "VirtualBox",
    "ISATAP",
    "Loopback",
    "Wintun",
    "Bluetooth",
]


class NetworkWindows(NetworkCommon):
    async def _fill_interfaces(self, interfaces: list[NetworkInterface]) -> None:
        # remove known virtual interfaces
        for interface in list(interfaces):
            if any(s in interface.title for s in IFACE_BLACKLIST):
                interfaces.remove(interface)
        # mark Wi-Fi Station interfaces
        for iface in Win32Wifi.getWirelessInterfaces():
            for interface in interfaces:
                if interface.name == iface.guid_string:
                    interface.type = NetworkInterface.Type.WIRELESS_STA
        # mark Wi-Fi Access Point interfaces
        status = wlanapi.WlanHostedNetworkQueryStatus()
        for interface in interfaces:
            if interface.name == f"{{{status.device_guid}}}".upper():
                interface.type = NetworkInterface.Type.WIRELESS_AP

    @module_thread
    async def set_ip4config(
        self,
        interface: NetworkInterface,
        ipconfig: Ip4Config | None,
    ) -> None:
        index = 0
        for i in range(1, iphlpapi.GetNumberOfInterfaces() + 1):
            if_row = iphlpapi.GetIfEntry(i)
            if interface.name not in if_row.wszName:
                continue
            index = i
            break
        if not index:
            raise Exception("Interface not found")

        if not ipconfig:
            self.info(f"Enabling DHCP address on '{interface.title}'")
            self.command(
                "netsh",
                "interface",
                "ipv4",
                "set",
                "address",
                f"name={index}",
                "source=dhcp",
                "store=active",
            )
            return

        self.info(f"Setting static IP {ipconfig.address} on '{interface.title}'")
        self.command(
            "netsh",
            "interface",
            "ipv4",
            "set",
            "address",
            f"name={index}",
            "source=static",
            f"address={ipconfig.address}",
            f"mask={ipconfig.netmask}",
            f"gateway={ipconfig.gateway}".lower(),
            "store=active",
        )

        while True:
            netsh = self.command(
                "netsh",
                "interface",
                "ipv4",
                "show",
                "addresses",
                f"name={index}",
            )
            if str(ipconfig.address).encode() in netsh:
                break
            self.debug("Waiting for IP configuration to apply")
            await asyncio.sleep(0.5)
