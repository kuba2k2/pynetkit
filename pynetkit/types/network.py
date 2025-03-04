#  Copyright (c) Kuba Szczodrzyński 2023-9-7.

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import ifaddr


@dataclass
class NetworkAdapter:
    class Type(Enum):
        WIRED = auto()
        WIRELESS = auto()
        WIRELESS_STA = auto()
        WIRELESS_AP = auto()
        VIRTUAL = auto()

    ifadapter: ifaddr.Adapter
    name: str
    type: Type
    hardware: str | None = None
    obj: Any | None = None

    @property
    def title(self):
        if not self.hardware:
            return self.name
        return f"{self.name} ({self.hardware})"

    def ensure_wifi_sta(self) -> None:
        if self.type not in [
            NetworkAdapter.Type.WIRELESS,
            NetworkAdapter.Type.WIRELESS_STA,
        ]:
            raise ValueError("Interface doesn't support Wi-Fi Station")

    def ensure_wifi_ap(self) -> None:
        if self.type not in [
            NetworkAdapter.Type.WIRELESS,
            NetworkAdapter.Type.WIRELESS_AP,
        ]:
            raise ValueError("Interface doesn't support Wi-Fi Access Point")
