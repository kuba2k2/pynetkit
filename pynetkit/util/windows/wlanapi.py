#  Copyright (c) Kuba Szczodrzyński 2023-9-9.

from ctypes import byref, c_void_p
from ctypes.wintypes import DWORD, HANDLE
from dataclasses import dataclass
from enum import IntEnum
from uuid import UUID

from datastruct import DataStruct
from datastruct.adapters.misc import uuid_le_field
from datastruct.adapters.network import mac_field
from datastruct.fields import align, field, repeat, subfield
from datastruct.utils.misc import MemoryIO
from macaddress import MAC
from win32wifi import Win32NativeWifiApi
from winerror import ERROR_SUCCESS


@dataclass
class WlanHostedNetworkPeerState(DataStruct):
    class AuthState(IntEnum):
        INVALID = 0
        AUTHENTICATED = 1

    mac_address: MAC = mac_field()
    _1: ... = align(4)
    auth_state: AuthState = field("I")


@dataclass
class WlanHostedNetworkStatus(DataStruct):
    class State(IntEnum):
        UNAVAILABLE = 0
        IDLE = 1
        ACTIVE = 2

    state: State = field("I")
    device_guid: UUID = uuid_le_field()
    bssid: MAC = mac_field()
    _1: ... = align(4)
    phy_type: int = field("I")
    channel_frequency: int = field("L")
    peer_count: int = field("I")
    peer_list: list[WlanHostedNetworkPeerState] = repeat(
        count=lambda ctx: ctx.peer_count,
    )(subfield())


# noinspection PyPep8Naming
def WlanHostedNetworkQueryStatus():
    handle = Win32NativeWifiApi.WlanOpenHandle()
    func_ref = Win32NativeWifiApi.wlanapi.WlanHostedNetworkQueryStatus
    func_ref.argtypes = [
        HANDLE,
        c_void_p,
        c_void_p,
    ]
    func_ref.restype = DWORD
    ptr = c_void_p()
    result = func_ref(handle, byref(ptr), None)
    if result != ERROR_SUCCESS:
        raise Exception(f"WlanHostedNetworkQueryStatus failed ({result})")
    status = WlanHostedNetworkStatus.unpack(MemoryIO(ptr.value))
    Win32NativeWifiApi.WlanFreeMemory(ptr)
    Win32NativeWifiApi.WlanCloseHandle(handle)
    return status
