#  Copyright (c) Kuba Szczodrzyński 2024-6-16.

import re


def matches(pattern: str | bytes, value: str | bytes) -> bool:
    return bool(re.fullmatch(pattern, value))
