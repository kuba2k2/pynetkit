#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from macaddress import MAC

from pynetkit.modules.base import ModuleBase
from pynetkit.types import NetworkAdapter, WifiNetwork


class WifiCommon(ModuleBase):
    async def scan_networks(
        self,
        interface: NetworkAdapter,
    ) -> list[WifiNetwork]:
        raise NotImplementedError()

    async def start_station(
        self,
        interface: NetworkAdapter,
        network: WifiNetwork,
    ) -> None:
        raise NotImplementedError()

    async def stop_station(
        self,
        interface: NetworkAdapter,
    ) -> None:
        raise NotImplementedError()

    async def get_station_state(
        self,
        interface: NetworkAdapter,
    ) -> WifiNetwork | None:
        raise NotImplementedError()

    async def start_access_point(
        self,
        interface: NetworkAdapter,
        network: WifiNetwork,
    ) -> None:
        raise NotImplementedError()

    async def stop_access_point(
        self,
        interface: NetworkAdapter,
    ) -> None:
        raise NotImplementedError()

    async def get_access_point_state(
        self,
        interface: NetworkAdapter,
    ) -> bool:
        raise NotImplementedError()

    async def get_access_point_clients(
        self,
        interface: NetworkAdapter,
    ) -> set[MAC]:
        raise NotImplementedError()
