#  Copyright (c) Kuba Szczodrzyński 2025-3-6.

from dataclasses import dataclass
from enum import Enum, auto
from ipaddress import IPv4Address

from pynetkit.modules.base import BaseEvent
from pynetkit.modules.ssl import SslStoreEntry

from .types.address import ProxyAddress
from .types.http import ProxyHttpRequest


@dataclass
class ProxyEvent(BaseEvent):
    class Status(Enum):
        MITM_ERR = auto()
        SERVER_ERR = auto()
        CONNECTED = auto()

    status: Status
    client: tuple[IPv4Address, int]
    source: ProxyAddress
    target: ProxyAddress | None = None
    server: tuple[IPv4Address, int] | None = None
    error: Exception | None = None
    mitm: SslStoreEntry | None = None


@dataclass
class ProxyHttpEvent(BaseEvent):
    client: tuple[IPv4Address, int]
    incoming: ProxyHttpRequest
    outgoing: ProxyHttpRequest
    server: tuple[IPv4Address, int]
