#  Copyright (c) Kuba Szczodrzyński 2024-6-16.

import re
from ipaddress import IPv4Address
from pathlib import Path
from socket import AF_INET, IPPROTO_UDP, SOCK_DGRAM, socket
from typing import Iterable


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


def filter_dict(obj: dict, keys: Iterable) -> dict:
    if keys:
        for key in list(obj):
            if key not in keys:
                obj.pop(key)
    return obj


def wake_udp_socket(address: IPv4Address, port: int):
    # send an empty datagram to break out of recvfrom()
    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
    if int(address) == 0:  # 0.0.0.0
        address = "127.0.0.1"
    sock.sendto(b"", (str(address), port))
    sock.close()
