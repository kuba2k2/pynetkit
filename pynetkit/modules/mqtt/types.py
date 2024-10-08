#  Copyright (c) Kuba Szczodrzyński 2023-11-10.

from typing import Awaitable, Callable

MessageHandler = Callable[[str, bytes], Awaitable[None]]
