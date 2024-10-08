#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from dataclasses import dataclass
from ipaddress import IPv4Address

from macaddress import MAC

from pynetkit.modules.base import BaseEvent


@dataclass
class DhcpLeaseEvent(BaseEvent):
    client: MAC
    address: IPv4Address
    host_name: str | None
    vendor_cid: str | None
