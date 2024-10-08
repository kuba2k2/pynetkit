#  Copyright (c) Kuba Szczodrzyński 2023-9-7.

from dataclasses import dataclass
from enum import Enum, auto
from ipaddress import IPv4Address, IPv4Network
from typing import Any


@dataclass
class NetworkInterface:
    name: str
    title: str
    type: "NetworkInterface.Type"
    obj: Any

    class Type(Enum):
        WIRED = auto()
        WIRELESS = auto()
        WIRELESS_STA = auto()
        WIRELESS_AP = auto()

    def ensure_wifi_sta(self) -> None:
        if self.type not in [
            NetworkInterface.Type.WIRELESS,
            NetworkInterface.Type.WIRELESS_STA,
        ]:
            raise ValueError("Interface doesn't support Wi-Fi Station")

    def ensure_wifi_ap(self) -> None:
        if self.type not in [
            NetworkInterface.Type.WIRELESS,
            NetworkInterface.Type.WIRELESS_AP,
        ]:
            raise ValueError("Interface doesn't support Wi-Fi Access Point")


@dataclass
class Ip4Config:
    address: IPv4Address
    netmask: IPv4Address
    gateway: IPv4Address | None

    @property
    def network(self) -> IPv4Network:
        return IPv4Network(f"{self.address}/{self.netmask}", strict=False)

    @property
    def first(self) -> IPv4Address:
        return next(self.network.hosts())
