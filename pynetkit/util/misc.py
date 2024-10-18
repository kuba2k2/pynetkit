#  Copyright (c) Kuba Szczodrzyński 2024-6-16.

import re
from pathlib import Path


def matches(pattern: str | bytes, value: str | bytes) -> bool:
    return bool(re.fullmatch(pattern, value))


def import_module(filename: str) -> dict:
    ns = {}
    fn = Path(__file__).parents[2] / filename
    mp = filename.rpartition("/")[0].replace("/", ".")
    mn = fn.stem
    with open(fn) as f:
        code = compile(f.read(), fn, "exec")
        ns["__file__"] = fn
        ns["__name__"] = f"{mp}.{mn}"
        eval(code, ns, ns)
    return ns


def stringify_values(obj):
    if isinstance(obj, (str, int, bool, float, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: stringify_values(v) for k, v in obj.items()}
    if isinstance(obj, (list, set)):
        return [stringify_values(v) for v in obj]
    return str(obj)
