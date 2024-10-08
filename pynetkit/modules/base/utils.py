#  Copyright (c) Kuba Szczodrzyński 2023-9-9.

from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")
E = TypeVar("E")
EventHandler = Callable[[E], Awaitable[None]]


def make_attr_dict(obj: object, name: str) -> dict:
    if not hasattr(obj, name):
        setattr(obj, name, dict())
    return getattr(obj, name, dict())
