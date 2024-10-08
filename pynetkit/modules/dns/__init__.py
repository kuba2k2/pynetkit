#  Copyright (c) Kuba Szczodrzyński 2023-9-11.

from .events import DnsQueryEvent
from .module import DnsModule

__all__ = [
    "DnsModule",
    "DnsQueryEvent",
]
