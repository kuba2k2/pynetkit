#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from dataclasses import dataclass

from dnslib import RR

from pynetkit.modules.base import BaseEvent


@dataclass
class DnsQueryEvent(BaseEvent):
    qname: str
    qtype: str
    rdata: list[str | RR]
