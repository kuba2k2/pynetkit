#  Copyright (c) Kuba Szczodrzyński 2026-10-26.

from enum import Enum, auto


class ProxyPortMode(Enum):
    DETECT = auto()
    TCP = auto()
    TLS = auto()
    HTTP = auto()
    HTTPS = auto()


class ProxyProtocol(Enum):
    TCP = auto()
    TLS = auto()
