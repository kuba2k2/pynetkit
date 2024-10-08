#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from dataclasses import dataclass

from pynetkit.modules.base import BaseEvent

from .types import Request, Response


@dataclass
class HttpRequestEvent(BaseEvent):
    request: Request


@dataclass
class HttpResponseEvent(BaseEvent):
    request: Request
    response: Response
