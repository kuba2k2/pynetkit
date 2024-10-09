#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from enum import IntEnum

import xmltodict
from win32service import (
    SC_MANAGER_ALL_ACCESS,
    SERVICE_ALL_ACCESS,
    SERVICE_CONTROL_STOP,
    SERVICE_RUNNING,
    SERVICE_START_PENDING,
    SERVICE_STOP_PENDING,
    SERVICE_STOPPED,
    ControlService,
    OpenSCManager,
    OpenService,
    QueryServiceStatus,
    StartService,
)

from pynetkit.types import WifiNetwork

XML_AUTH_MAP = {
    None: "open",
    WifiNetwork.Auth.SHARED_KEY: "shared",
    WifiNetwork.Auth.WPA_PSK: "WPAPSK",
    WifiNetwork.Auth.WPA_ENT: "WPA",
    WifiNetwork.Auth.WPA2_PSK: "WPA2PSK",
    WifiNetwork.Auth.WPA2_ENT: "WPA2",
}
XML_CIPHER_MAP = {
    None: "none",
    WifiNetwork.Cipher.WEP: "WEP",
    WifiNetwork.Cipher.TKIP: "TKIP",
    WifiNetwork.Cipher.AES: "AES",
}


class Dot11AuthAlgorithm(IntEnum):
    OPEN = 1
    SHARED_KEY = 2
    WPA = 3
    WPA_PSK = 4
    WPA_NONE = 5
    RSNA = 6
    RSNA_PSK = 7
    WPA3 = 8
    WPA3_ENT_192 = WPA3
    WPA3_SAE = 9
    OWE = 10
    WPA3_ENT = 11


class Dot11CipherAlgorithm(IntEnum):
    NONE = 0x00
    WEP40 = 0x01
    TKIP = 0x02
    CCMP = 0x04
    WEP104 = 0x05
    WPA_USE_GROUP = 0x100
    RSN_USE_GROUP = 0x100
    WEP = 0x101


def make_xml_profile(network: WifiNetwork) -> str:
    if network.protected and not network.password:
        raise ValueError("Attempting to connect without password")

    if network.protected:
        wep = network.cipher == WifiNetwork.Cipher.WEP
        shared_key = {
            "keyType": "networkKey" if wep else "passPhrase",
            "protected": "false",
            "keyMaterial": (
                network.password.hex().upper() if wep else network.password.decode()
            ),
        }
    else:
        shared_key = None
    # noinspection HttpUrlsUsage
    profile = {
        "WLANProfile": {
            "@xmlns": "http://www.microsoft.com/networking/WLAN/profile/v1",
            "name": network.ssid,
            "SSIDConfig": {
                "SSID": {
                    "hex": network.ssid.encode("utf-8").hex().upper(),
                    "name": network.ssid,
                },
                "nonBroadcast": "false",
            },
            "connectionType": "IBSS" if network.ad_hoc else "ESS",
            "connectionMode": "manual",
            "autoSwitch": "false",
            "MSM": {
                "security": {
                    "authEncryption": {
                        "authentication": XML_AUTH_MAP[network.auth],
                        "encryption": XML_CIPHER_MAP[network.cipher],
                        "useOneX": "false",
                    },
                },
            },
        },
    }
    if shared_key:
        profile["WLANProfile"]["MSM"]["security"]["sharedKey"] = shared_key
    return xmltodict.unparse(profile, pretty=True)


def start_wlansvc() -> None:
    service_manager = OpenSCManager(None, None, SC_MANAGER_ALL_ACCESS)
    service = OpenService(service_manager, "Wlansvc", SERVICE_ALL_ACCESS)
    state = QueryServiceStatus(service)[1]
    if state not in [SERVICE_RUNNING, SERVICE_START_PENDING]:
        StartService(service, [])
        service = OpenService(service_manager, "Wlansvc", SERVICE_ALL_ACCESS)
        while True:
            state = QueryServiceStatus(service)[1]
            if state == SERVICE_RUNNING:
                break


def stop_wlansvc() -> None:
    service_manager = OpenSCManager(None, None, SC_MANAGER_ALL_ACCESS)
    service = OpenService(service_manager, "Wlansvc", SERVICE_ALL_ACCESS)
    state = QueryServiceStatus(service)[1]
    if state not in [SERVICE_STOPPED, SERVICE_STOP_PENDING]:
        ControlService(service, SERVICE_CONTROL_STOP)
        service = OpenService(service_manager, "Wlansvc", SERVICE_ALL_ACCESS)
        while True:
            state = QueryServiceStatus(service)[1]
            if state == SERVICE_STOPPED:
                break
