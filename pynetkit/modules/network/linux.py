#  Copyright (c) Kuba Szczodrzyński 2024-10-28.

from ipaddress import IPv4Interface

from pynetkit.modules.base import module_thread
from pynetkit.types import NetworkAdapter

from .common import NetworkCommon


class NetworkLinux(NetworkCommon):
    IFACE_BLACKLIST_NAMES = ["lo"]
    IFACE_VIRTUAL_WORDS = ["vpn", "docker", "veth"]

    @module_thread
    async def list_adapters(self) -> list[NetworkAdapter]:
        adapters = await super().list_adapters()
        # mark Wi-Fi adapters
        for adapter in adapters:
            if adapter.name.startswith("wl"):
                adapter.type = NetworkAdapter.Type.WIRELESS
        return adapters

    @module_thread
    async def set_adapter_addresses(
        self,
        adapter: NetworkAdapter,
        dhcp: bool,
        addresses: list[IPv4Interface],
    ) -> None:
        prev_dhcp, prev_addresses = await self.get_adapter_addresses(adapter)
        if dhcp:
            if not prev_dhcp:
                self.error("DHCP support is not yet available on Linux")
            return

        remove = set(prev_addresses) - set(addresses)
        for address in remove:
            self.info(f"Deleting static IP address {address} on '{adapter.name}'")
            self.command(f"ip addr del {address} dev {adapter.name}")

        for address in addresses:
            self.info(f"Setting static IP address {address} on '{adapter.name}'")
            self.command(f"ip addr add {address} dev {adapter.name}")
