#  Copyright (c) Kuba Szczodrzyński 2025-3-6.

from dataclasses import dataclass
from ipaddress import IPv4Address

from pynetkit.modules.base import BaseEvent

from .types.address import ProxyAddress


@dataclass
class ProxyEvent(BaseEvent):
    address: IPv4Address
    source: ProxyAddress
    target: ProxyAddress
