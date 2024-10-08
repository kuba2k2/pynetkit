#  Copyright (c) Kuba Szczodrzyński 2023-9-9.

from ctypes import POINTER, Structure, byref, windll
from ctypes.wintypes import BYTE, CHAR, DWORD, LPWSTR, ULONG, WCHAR

from winerror import ERROR_SUCCESS

iphlpapi = windll.LoadLibrary("iphlpapi.dll")


class MIB_IFROW(Structure):
    _fields_ = [
        ("wszName", WCHAR * 256),
        ("dwIndex", DWORD),
        ("dwType", DWORD),
        ("dwMtu", DWORD),
        ("dwSpeed", DWORD),
        ("dwPhysAddrLen", DWORD),
        ("bPhysAddr", BYTE * 8),
        ("dwAdminStatus", DWORD),
        ("dwOperStatus", DWORD),
        ("dwLastChange", DWORD),
        ("dwInOctets", DWORD),
        ("dwInUcastPkts", DWORD),
        ("dwInNUcastPkts", DWORD),
        ("dwInDiscards", DWORD),
        ("dwInErrors", DWORD),
        ("dwInUnknownProtos", DWORD),
        ("dwOutOctets", DWORD),
        ("dwOutUcastPkts", DWORD),
        ("dwOutNUcastPkts", DWORD),
        ("dwOutDiscards", DWORD),
        ("dwOutErrors", DWORD),
        ("dwOutQLen", DWORD),
        ("dwDescrLen", DWORD),
        ("bDescr", CHAR * 256),
    ]


# noinspection PyPep8Naming
def GetAdapterIndex(AdapterName) -> int:
    func_ref = iphlpapi.GetAdapterIndex
    func_ref.argtypes = [
        LPWSTR,
        POINTER(ULONG),
    ]
    func_ref.restype = DWORD
    if_index = ULONG()
    result = func_ref(AdapterName, byref(if_index))
    if result != ERROR_SUCCESS:
        raise Exception(f"GetAdapterIndex failed ({result})")
    return if_index.value


# noinspection PyPep8Naming
def GetNumberOfInterfaces() -> int:
    func_ref = iphlpapi.GetNumberOfInterfaces
    func_ref.argtypes = [
        POINTER(DWORD),
    ]
    func_ref.restype = DWORD
    num_if = DWORD()
    result = func_ref(byref(num_if))
    if result != ERROR_SUCCESS:
        raise Exception(f"GetNumberOfInterfaces failed ({result})")
    return num_if.value


# noinspection PyPep8Naming
def GetIfEntry(index) -> MIB_IFROW:
    func_ref = iphlpapi.GetIfEntry
    func_ref.argtypes = [
        POINTER(MIB_IFROW),
    ]
    func_ref.restype = DWORD
    if_row = MIB_IFROW()
    if_row.dwIndex = index
    result = func_ref(byref(if_row))
    if result != ERROR_SUCCESS:
        raise Exception(f"GetIfEntry failed ({result})")
    return if_row
