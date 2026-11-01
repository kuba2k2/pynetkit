#  Copyright (c) Kuba Szczodrzyński 2025-3-6.

from dataclasses import dataclass
from ipaddress import IPv4Address

from pynetkit.modules.base import BaseEvent

from .types.address import ProxyAddress
from .types.enums import ProxyProtocol


@dataclass
class ProxyEvent(BaseEvent):
    client: tuple[IPv4Address, int]
    source: ProxyAddress
    target: ProxyAddress
    server: tuple[IPv4Address, int]
    protocol: ProxyProtocol
