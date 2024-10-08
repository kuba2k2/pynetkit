#  Copyright (c) Kuba Szczodrzyński 2023-11-10.

from .types import MessageHandler


def subscribe(topic: str):
    def attach(func: MessageHandler) -> MessageHandler:
        if not hasattr(func, "__topics__"):
            setattr(func, "__topics__", [])
        if topic not in getattr(func, "__topics__"):
            getattr(func, "__topics__").append(topic)
        return func

    return attach
