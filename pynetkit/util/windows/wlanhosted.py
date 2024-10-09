#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import random
from dataclasses import dataclass
from typing import Any
from winreg import HKEY_LOCAL_MACHINE as HKLM
from winreg import KEY_WRITE, REG_BINARY, OpenKey, QueryValueEx, SetValueEx

from datastruct import DataStruct, datastruct
from datastruct.fields import align, built, bytestr, field, padding

from pynetkit.util.dpapi import Dpapi, DpapiBlob, DpapiKeyScope, DpapiKeyStore

from .wlanmisc import Dot11AuthAlgorithm, Dot11CipherAlgorithm


@dataclass
@datastruct(padding_pattern=b"\x00")
class HostedNetworkSettings(DataStruct):
    ssid_len: int = built("I", lambda ctx: len(ctx.ssid))
    ssid: bytes = bytestr(32)
    max_clients: int = field("I", default=10)
    auth: Dot11AuthAlgorithm = field("I", default=Dot11AuthAlgorithm.RSNA_PSK)
    cipher: Dot11CipherAlgorithm = field("I", default=Dot11CipherAlgorithm.CCMP)
    allowed: bool = field("?", default=True)
    _1: ... = padding(3)
    not_configured: bool = field("?", default=False)
    _2: ... = align(0xE0)


@dataclass
@datastruct(padding_pattern=b"\x00")
class HostedNetworkSecurity(DataStruct):
    system_key: bytes = bytestr(64)
    user_key_len: int = built("I", lambda ctx: len(ctx.user_key) + 1)
    user_key: bytes = bytestr(64)
    key_set: bool = built("?", lambda ctx: bool(ctx.user_key))
    _1: ... = padding(7)
    _2: ... = padding(4, pattern=b"\x04")


WLANSVC_KEY: str | None = None


def _get_wlansvc_key() -> str:
    global WLANSVC_KEY
    if not WLANSVC_KEY:
        with OpenKey(HKLM, "SYSTEM\\Select") as key:
            control_set, _ = QueryValueEx(key, "Current")
        WLANSVC_KEY = (
            f"SYSTEM\\ControlSet{control_set:03d}\\services\\"
            f"Wlansvc\\Parameters\\HostedNetworkSettings"
        )
    return WLANSVC_KEY


def read_settings() -> HostedNetworkSettings:
    with OpenKey(HKLM, _get_wlansvc_key()) as key:
        data, _ = QueryValueEx(key, "HostedNetworkSettings")
        return HostedNetworkSettings.unpack(data)


def write_settings(settings: HostedNetworkSettings) -> None:
    with OpenKey(HKLM, _get_wlansvc_key(), 0, KEY_WRITE) as key:
        data: Any = settings.pack()
        SetValueEx(key, "HostedNetworkSettings", 0, REG_BINARY, data)


def read_security(dpapi: Dpapi) -> HostedNetworkSecurity:
    key_store = DpapiKeyStore.get(DpapiKeyScope.LOCAL_SYSTEM, user=True)
    key_builder = dpapi.get_key_builder(key_store)

    with OpenKey(HKLM, _get_wlansvc_key()) as key:
        data, _ = QueryValueEx(key, "EncryptedSettings")
        blob = DpapiBlob.unpack(data, key_builder=key_builder)
        return HostedNetworkSecurity.unpack(blob.data)


def write_security(dpapi: Dpapi, security: HostedNetworkSecurity) -> None:
    store = DpapiKeyStore.get(DpapiKeyScope.LOCAL_SYSTEM, user=True)
    key_builder = dpapi.get_key_builder(store)
    preferred_key = dpapi.get_preferred_key(store)

    with OpenKey(HKLM, _get_wlansvc_key(), 0, KEY_WRITE) as key:
        blob = DpapiBlob(
            guid_master_key=preferred_key,
            salt=random.randbytes(32),
            hmac_key=random.randbytes(32),
            data=security.pack(),
        )
        data: Any = blob.pack(key_builder=key_builder)
        SetValueEx(key, "EncryptedSettings", 0, REG_BINARY, data)


def make_security_system_key() -> bytes:
    sets = [
        bytes(range(ord("A"), ord("Z") + 1)),
        bytes(range(ord("a"), ord("z") + 1)),
        bytes(range(ord("0"), ord("9") + 1)),
        b"!#*+-@~",
    ]
    return bytes(random.choices(b"".join(sets), k=63))
