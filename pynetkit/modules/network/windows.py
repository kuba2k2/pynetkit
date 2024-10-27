#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from ipaddress import IPv4Interface
from random import randint

from win32wifi import Win32Wifi

from pynetkit.modules.base import module_thread
from pynetkit.types import NetworkAdapter
from pynetkit.util.windows import iphlpapi, wlanapi

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

    @module_thread
    async def list_adapters(self) -> list[NetworkAdapter]:
        adapters = await super().list_adapters()
        # store adapter GUID in adapter.obj
        for adapter in adapters:
            adapter.obj = adapter.ifadapter.name
        # remove known virtual adapters
        for adapter in list(adapters):
            if any(s in adapter.title for s in IFACE_BLACKLIST):
                adapters.remove(adapter)
        # mark Wi-Fi Station adapters
        for iface in Win32Wifi.getWirelessInterfaces():
            for adapter in adapters:
                if adapter.obj == iface.guid_string:
                    adapter.type = NetworkAdapter.Type.WIRELESS_STA
        # mark Wi-Fi Access Point adapters
        status = wlanapi.WlanHostedNetworkQueryStatus()
        for adapter in adapters:
            if adapter.obj == f"{{{status.device_guid}}}".upper():
                adapter.type = NetworkAdapter.Type.WIRELESS_AP
        return adapters

    @module_thread
    async def set_adapter_addresses(
        self,
        adapter: NetworkAdapter,
        dhcp: bool,
        addresses: list[IPv4Interface],
    ) -> None:
        index = 0
        for i in range(1, iphlpapi.GetNumberOfInterfaces() + 1):
            if_row = iphlpapi.GetIfEntry(i)
            if adapter.obj not in if_row.wszName:
                continue
            index = i
            break
        if not index:
            raise ValueError("Network adapter not found")

        if dhcp and addresses:
            self.warning("Removing static addresses as DHCP is used")
            addresses = []

        self.debug(f"Checking DHCP state on '{adapter.name}'")
        prev_dhcp, prev_addresses = await self.get_adapter_addresses(adapter)
        _, out = self.command(f"netsh interface ipv4 show ipaddresses {index}")
        prev_dhcp = b"Dhcp" in out

        if dhcp and not prev_dhcp:
            self.info(f"Enabling DHCP address on '{adapter.name}'")
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
        elif dhcp:
            self.info(f"DHCP is already enabled on '{adapter.name}'")
            return
        elif not addresses:
            self.warning(f"No static address provided, using random link-local address")
            addresses = [
                IPv4Interface(f"169.254.{randint(1, 254)}.{randint(1, 254)}/16")
            ]

        remove = set(prev_addresses) - set(addresses)
        for i, address in enumerate(remove):
            self.info(f"Deleting static IP address {address} on '{adapter.name}'")
            self.command(
                "netsh",
                "interface",
                "ipv4",
                "delete",
                "address",
                f"name={index}",
                f"address={address.ip}",
                "store=active",
            )

        for i, address in enumerate(addresses):
            self.info(f"Setting static IP address {address} on '{adapter.name}'")
            self.command(
                "netsh",
                "interface",
                "ipv4",
                "set" if i == 0 else "add",
                "address",
                f"name={index}",
                "source=static" if i == 0 else "",
                f"address={address}",
                f"gateway=none",
                "store=active",
            )

        # while True:
        #     netsh = self.command(
        #         "netsh",
        #         "interface",
        #         "ipv4",
        #         "show",
        #         "addresses",
        #         f"name={index}",
        #     )
        #     if str(ipconfig.address).encode() in netsh:
        #         break
        #     self.debug("Waiting for IP configuration to apply")
        #     await asyncio.sleep(0.5)
