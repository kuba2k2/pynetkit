#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from dataclasses import dataclass

from macaddress import MAC

from pynetkit.modules.base import BaseEvent
from pynetkit.types import WifiNetwork


@dataclass
class WifiRawEvent(BaseEvent):
    code: str
    data: object


@dataclass
class WifiScanCompleteEvent(BaseEvent):
    networks: list[WifiNetwork]


@dataclass
class WifiConnectedEvent(BaseEvent):
    ssid: str


@dataclass
class WifiDisconnectedEvent(BaseEvent):
    ssid: str


@dataclass
class WifiAPStartedEvent(BaseEvent):
    pass


@dataclass
class WifiAPStoppedEvent(BaseEvent):
    pass


@dataclass
class WifiAPClientConnectedEvent(BaseEvent):
    client: MAC


@dataclass
class WifiAPClientDisconnectedEvent(BaseEvent):
    client: MAC
