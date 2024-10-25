#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from .events import NtpSyncEvent
from .module import NtpModule

__all__ = [
    "NtpModule",
    "NtpSyncEvent",
]
