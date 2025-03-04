#  Copyright (c) Kuba Szczodrzyński 2023-9-7.

from dataclasses import dataclass
from enum import Enum, Flag, auto


@dataclass
class WifiNetwork:
    ssid: str
    password: bytes | None
    auth: "Auth" = None
    cipher: "Cipher" = None
    rssi: float = None
    ad_hoc: bool = False

    class Auth(Flag):
        SHARED_KEY = auto()
        WPA_PSK = auto()
        WPA_ENT = auto()
        WPA2_PSK = auto()
        WPA2_ENT = auto()
        WPA3_PSK = auto()
        WPA3_ENT = auto()

    class Cipher(Enum):
        WEP = auto()
        TKIP = auto()
        AES = auto()

    @property
    def protected(self) -> bool:
        return self.auth is not None or self.cipher is not None
