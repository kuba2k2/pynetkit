#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from macaddress import MAC

from pynetkit.modules.base import ModuleBase
from pynetkit.types import NetworkAdapter, WifiNetwork


class WifiCommon(ModuleBase):
    async def scan_networks(
        self,
        adapter: NetworkAdapter,
    ) -> list[WifiNetwork]:
        raise NotImplementedError()

    async def start_station(
        self,
        adapter: NetworkAdapter,
        network: WifiNetwork,
    ) -> None:
        raise NotImplementedError()

    async def stop_station(
        self,
        adapter: NetworkAdapter,
    ) -> None:
        raise NotImplementedError()

    async def get_station_state(
        self,
        adapter: NetworkAdapter,
    ) -> WifiNetwork | None:
        raise NotImplementedError()

    async def start_access_point(
        self,
        adapter: NetworkAdapter,
        network: WifiNetwork,
    ) -> None:
        raise NotImplementedError()

    async def stop_access_point(
        self,
        adapter: NetworkAdapter,
    ) -> None:
        raise NotImplementedError()

    async def get_access_point_state(
        self,
        adapter: NetworkAdapter,
    ) -> WifiNetwork | None:
        raise NotImplementedError()

    async def get_access_point_clients(
        self,
        adapter: NetworkAdapter,
    ) -> set[MAC]:
        raise NotImplementedError()
