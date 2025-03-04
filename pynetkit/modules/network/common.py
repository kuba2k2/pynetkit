#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from ipaddress import IPv4Address, IPv4Interface
from typing import Callable

import ifaddr
from icmplib import async_ping

from pynetkit.modules.base import ModuleBase, module_thread
from pynetkit.types import NetworkAdapter


class NetworkCommon(ModuleBase):
    IFACE_BLACKLIST_NAMES = []
    IFACE_BLACKLIST_WORDS = []
    IFACE_VIRTUAL_NAMES = []
    IFACE_VIRTUAL_WORDS = []

    @module_thread
    async def list_adapters(self) -> list[NetworkAdapter]:
        adapters = []
        for ifadapter in ifaddr.get_adapters(include_unconfigured=True):
            adapter = NetworkAdapter(
                ifadapter=ifadapter,
                name=ifadapter.nice_name,
                type=NetworkAdapter.Type.WIRED,
            )
            # assign hardware name if available (e.g. on Windows)
            if ifadapter.ips:
                nice_name = ifadapter.ips[0].nice_name
                if nice_name != ifadapter.nice_name:
                    adapter.name = nice_name
                    adapter.hardware = ifadapter.nice_name
            # ignore known virtual adapters
            if adapter.name in self.IFACE_BLACKLIST_NAMES:
                continue
            if any(s in adapter.title for s in self.IFACE_BLACKLIST_WORDS):
                continue
            adapters.append(adapter)
        # mark known virtual adapters (those not already ignored)
        for adapter in adapters:
            if adapter.name in self.IFACE_VIRTUAL_NAMES:
                adapter.type = NetworkAdapter.Type.VIRTUAL
            elif any(s in adapter.title for s in self.IFACE_VIRTUAL_WORDS):
                adapter.type = NetworkAdapter.Type.VIRTUAL
        # sort adapters by their name
        adapters = sorted(adapters, key=lambda a: a.name)
        return adapters

    @module_thread
    async def get_adapter_addresses(
        self,
        adapter: NetworkAdapter,
    ) -> tuple[bool, list[IPv4Interface]]:
        addresses = []
        # always retrieve current IP address information
        for ifadapter in ifaddr.get_adapters(include_unconfigured=True):
            if ifadapter.name != adapter.ifadapter.name:
                continue
            for ip in ifadapter.ips:
                if not ip.is_IPv4:
                    continue
                addresses.append(IPv4Interface(f"{ip.ip}/{ip.network_prefix}"))
            break
        else:
            raise ValueError("Network adapter not found")
        addresses = sorted(addr for addr in addresses if not addr.is_link_local)
        return False, addresses

    async def set_adapter_addresses(
        self,
        adapter: NetworkAdapter,
        dhcp: bool,
        addresses: list[IPv4Interface],
    ) -> None:
        raise NotImplementedError()

    async def get_adapter(
        self,
        *adapter_type: NetworkAdapter.Type,
    ) -> NetworkAdapter | None:
        adapters = await self.list_adapters()
        try:
            return next(a for a in adapters if a.type in adapter_type)
        except StopIteration:
            return None

    async def ping(
        self,
        address: IPv4Address,
        count: int = 4,
        interval: float = 0.2,
        timeout: float = 2.0,
        log: Callable[[str], None] = None,
    ) -> float | None:
        if not log:
            log = self.debug
        host = await async_ping(str(address), count, interval, timeout)
        if not host.is_alive:
            log(f"Host {address} is dead")
            return None
        log(f"Host {address} is alive, RTT {host.avg_rtt} ms")
        return host.avg_rtt
