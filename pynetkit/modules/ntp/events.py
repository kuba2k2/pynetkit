#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address

from pynetkit.modules.base import BaseEvent


@dataclass
class NtpSyncEvent(BaseEvent):
    address: IPv4Address
    origin_timestamp: datetime | None
