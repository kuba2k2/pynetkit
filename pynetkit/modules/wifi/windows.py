#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import asyncio
from ctypes.wintypes import LPCWSTR

from macaddress import MAC
from win32wifi import Win32NativeWifiApi, Win32Wifi
from win32wifi.Win32NativeWifiApi import (
    WLAN_HOSTED_NETWORK_NOTIFICATION_CODE_ENUM as HNET,
)
from win32wifi.Win32NativeWifiApi import WLAN_NOTIFICATION_ACM_ENUM as ACM
from win32wifi.Win32NativeWifiApi import WLAN_NOTIFICATION_MSM_ENUM as MSM
from win32wifi.Win32Wifi import (
    ACMConnectionNotificationData,
    WirelessInterface,
    WlanEvent,
)

from pynetkit.modules.base import module_thread
from pynetkit.types import NetworkInterface, WifiNetwork
from pynetkit.util.dpapi import Dpapi
from pynetkit.util.windows import wlanapi, wlanhosted, wlanmisc
from pynetkit.util.windows.wlanapi import WlanHostedNetworkStatus
from pynetkit.util.windows.wlanhosted import (
    HostedNetworkSecurity,
    HostedNetworkSettings,
)

from .common import WifiCommon
from .events import (
    WifiAPClientConnectedEvent,
    WifiAPClientDisconnectedEvent,
    WifiAPStartedEvent,
    WifiAPStoppedEvent,
    WifiConnectedEvent,
    WifiDisconnectedEvent,
    WifiRawEvent,
    WifiScanCompleteEvent,
)

DOT11_AUTH_MAP = {
    "DOT11_AUTH_ALGO_80211_OPEN": None,
    "DOT11_AUTH_ALGO_80211_SHARED_KEY": WifiNetwork.Auth.SHARED_KEY,
    "DOT11_AUTH_ALGO_WPA": WifiNetwork.Auth.WPA_ENT,
    "DOT11_AUTH_ALGO_WPA_PSK": WifiNetwork.Auth.WPA_PSK,
    "DOT11_AUTH_ALGO_WPA_NONE": WifiNetwork.Auth.WPA_PSK,
    "DOT11_AUTH_ALGO_RSNA": WifiNetwork.Auth.WPA2_ENT,
    "DOT11_AUTH_ALGO_RSNA_PSK": WifiNetwork.Auth.WPA2_PSK,
}
DOT11_CIPHER_MAP = {
    "DOT11_CIPHER_ALGO_NONE": None,
    "DOT11_CIPHER_ALGO_WEP40": WifiNetwork.Cipher.WEP,
    "DOT11_CIPHER_ALGO_TKIP": WifiNetwork.Cipher.TKIP,
    "DOT11_CIPHER_ALGO_CCMP": WifiNetwork.Cipher.AES,
    "DOT11_CIPHER_ALGO_WEP104": WifiNetwork.Cipher.WEP,
    "DOT11_CIPHER_ALGO_WEP": WifiNetwork.Cipher.WEP,
}


def iface_by_guid(guid: str) -> WirelessInterface:
    for iface in Win32Wifi.getWirelessInterfaces():
        if iface.guid_string == guid:
            return iface
    raise ValueError(f"Interface with GUID {guid} wasn't found")


class WifiWindows(WifiCommon):
    notification: Win32Wifi.NotificationObject | None = None
    dpapi: Dpapi | None = None
    ap_clients: set[MAC] = None

    async def start(self) -> None:
        await super().start()
        self._register()
        if self.dpapi is None:
            self.dpapi = Dpapi()
            self.dpapi.load_credentials()
        self.ap_clients = set()

    async def stop(self) -> None:
        self._unregister()
        await super().stop()

    def _register(self):
        try:
            self.command("net", "start", "Wlansvc")
            self.info("Started Wlansvc")
        except RuntimeError:
            pass
        if self.notification is None:
            self.notification = Win32Wifi.registerNotification(self.on_notification)

    def _unregister(self, stop_wlansvc: bool = False) -> None:
        if self.notification is not None:
            Win32Wifi.unregisterNotification(self.notification)
            self.notification = None
        if stop_wlansvc:
            self.command("net", "stop", "Wlansvc")
            self.info("Stopped Wlansvc")

    def on_notification(self, event: WlanEvent) -> None:
        code = event.notificationCode
        guid = str(event.interfaceGuid)
        data = event.data
        match code:
            case ACM.wlan_notification_acm_scan_complete.name:
                networks = []
                iface = iface_by_guid(guid)
                for network in Win32Wifi.getWirelessAvailableNetworkList(iface):
                    if network.auth not in DOT11_AUTH_MAP:
                        continue
                    if network.cipher not in DOT11_CIPHER_MAP:
                        continue
                    networks.append(
                        WifiNetwork(
                            ssid=network.ssid.decode(),
                            password=None,
                            auth=DOT11_AUTH_MAP[network.auth],
                            cipher=DOT11_CIPHER_MAP[network.cipher],
                            rssi=network.signal_quality / 2 - 100,
                            ad_hoc=network.bss_type == "dot11_BSS_type_independent",
                        )
                    )
                WifiScanCompleteEvent(networks=networks).broadcast()

            case ACM.wlan_notification_acm_network_available.name:
                pass

            case ACM.wlan_notification_acm_connection_complete.name:
                data: ACMConnectionNotificationData
                WifiConnectedEvent(ssid=data.ssid.decode()).broadcast()

            case ACM.wlan_notification_acm_disconnected.name:
                data: ACMConnectionNotificationData
                WifiDisconnectedEvent(ssid=data.ssid.decode()).broadcast()

            case HNET.wlan_hosted_network_state_change.name:
                status = wlanapi.WlanHostedNetworkQueryStatus()
                match status.state:
                    case WlanHostedNetworkStatus.State.UNAVAILABLE:
                        pass
                    case WlanHostedNetworkStatus.State.IDLE:
                        WifiAPStoppedEvent().broadcast()
                    case WlanHostedNetworkStatus.State.ACTIVE:
                        WifiAPStartedEvent().broadcast()

            case HNET.wlan_hosted_network_peer_state_change.name:
                self.call_coroutine(self.get_access_point_clients(interface=None))

            case _ if code not in (e.name for e in MSM):
                WifiRawEvent(code=code, data=data).broadcast()

    @module_thread
    async def scan_networks(
        self,
        interface: NetworkInterface,
    ) -> list[WifiNetwork]:
        interface.ensure_wifi_sta()
        iface = iface_by_guid(interface.name)
        handle = Win32NativeWifiApi.WlanOpenHandle()
        Win32NativeWifiApi.WlanScan(handle, iface.guid)
        Win32NativeWifiApi.WlanCloseHandle(handle)
        return (await WifiScanCompleteEvent.any()).networks

    @module_thread
    async def start_station(
        self,
        interface: NetworkInterface,
        network: WifiNetwork,
    ) -> None:
        interface.ensure_wifi_sta()
        iface = iface_by_guid(interface.name)
        xml = wlanmisc.make_xml_profile(network)
        if await self.get_station_state(interface):
            await self.stop_station()
        handle = Win32NativeWifiApi.WlanOpenHandle()
        params = Win32NativeWifiApi.WLAN_CONNECTION_PARAMETERS()
        params.wlanConnectionMode = Win32NativeWifiApi.WLAN_CONNECTION_MODE(
            Win32NativeWifiApi.WLAN_CONNECTION_MODE_VK[
                "wlan_connection_mode_temporary_profile"
            ]
        )
        params.strProfile = LPCWSTR(xml)
        params.pDot11Ssid = None
        params.pDesiredBssidList = None
        params.dot11BssType = Win32NativeWifiApi.DOT11_BSS_TYPE(
            Win32NativeWifiApi.DOT11_BSS_TYPE_DICT_VK[
                (
                    "dot11_BSS_type_independent"
                    if network.ad_hoc
                    else "dot11_BSS_type_infrastructure"
                )
            ]
        )
        params.dwFlags = 0
        Win32NativeWifiApi.WlanConnect(handle, iface.guid, params)
        Win32NativeWifiApi.WlanCloseHandle(handle)
        await WifiConnectedEvent(ssid=network.ssid)

    @module_thread
    async def stop_station(
        self,
        interface: NetworkInterface,
    ) -> None:
        interface.ensure_wifi_sta()
        iface = iface_by_guid(interface.name)
        _, state = Win32Wifi.queryInterface(iface, "interface_state")
        Win32Wifi.disconnect(iface)
        if await self.get_station_state(interface):
            await WifiDisconnectedEvent.any()

    @module_thread
    async def get_station_state(
        self,
        interface: NetworkInterface,
    ) -> WifiNetwork | None:
        interface.ensure_wifi_sta()
        iface = iface_by_guid(interface.name)
        _, state = Win32Wifi.queryInterface(iface, "interface_state")
        if state == "wlan_interface_state_connected":
            _, conn = Win32Wifi.queryInterface(iface, "current_connection")
            assoc = conn["wlanAssociationAttributes"]
            security = conn["wlanSecurityAttributes"]
            return WifiNetwork(
                ssid=assoc["dot11Ssid"].decode(),
                password=None,
                auth=DOT11_AUTH_MAP[security["dot11AuthAlgorithm"]],
                cipher=DOT11_CIPHER_MAP[security["dot11CipherAlgorithm"]],
                rssi=assoc["wlanSignalQuality"] / 2 - 100,
                ad_hoc=assoc["dot11BssType"] == "dot11_BSS_type_independent",
            )
        return None

    @module_thread
    async def start_access_point(
        self,
        interface: NetworkInterface,
        network: WifiNetwork,
    ) -> None:
        interface.ensure_wifi_ap()
        config_changed = False

        self.info("Configuring Hosted Network...")
        try:
            old_settings = wlanhosted.read_settings()
            if not old_settings.allowed or old_settings.not_configured:
                old_settings = None
        except FileNotFoundError:
            old_settings = None
        try:
            old_security = wlanhosted.read_security(self.dpapi)
            system_key = old_security.system_key
        except FileNotFoundError:
            old_security = None
            system_key = wlanhosted.make_security_system_key()

        new_settings = HostedNetworkSettings(
            ssid=network.ssid.encode(),
        )
        new_security = HostedNetworkSecurity(
            system_key=system_key,
            user_key=network.password,
        )

        if old_settings is None or old_settings.ssid != new_settings.ssid:
            self.debug(f"Settings changed: {old_settings} vs {new_settings}")
            config_changed = True
        if old_security is None or old_security.user_key != new_security.user_key:
            self.debug(f"Security changed: {old_security} vs {new_security}")
            config_changed = True

        if config_changed:
            await self.stop_access_point(interface)
            self._unregister(stop_wlansvc=True)
            await asyncio.sleep(2)

            self.debug("Writing Hosted Network settings")
            wlanhosted.write_settings(new_settings)

            self.debug("Writing Hosted Network security settings")
            wlanhosted.write_security(self.dpapi, new_security)

            self._register()
            await WifiRawEvent(
                code="wlan_notification_acm_interface_arrival",
                data=None,
            )

        if not await self.get_access_point_state(interface):
            self.info(f"Starting Hosted Network '{network.ssid}'")
            future = WifiAPStartedEvent.any()
            self.command("netsh", "wlan", "start", "hostednetwork")
            await future
        else:
            self.info(f"Hosted Network '{network.ssid}' is already running")
            WifiAPStartedEvent().broadcast()

        await self.get_access_point_clients(interface)

    @module_thread
    async def stop_access_point(
        self,
        interface: NetworkInterface,
    ) -> None:
        interface.ensure_wifi_ap()
        if await self.get_access_point_state(interface):
            self.info("Stopping Hosted Network")
            future = WifiAPStoppedEvent.any()
            self.command("netsh", "wlan", "stop", "hostednetwork")
            await future

    @module_thread
    async def get_access_point_state(
        self,
        interface: NetworkInterface,
    ) -> bool:
        interface.ensure_wifi_ap()
        status = wlanapi.WlanHostedNetworkQueryStatus()
        return status.state == WlanHostedNetworkStatus.State.ACTIVE

    @module_thread
    async def get_access_point_clients(
        self,
        interface: NetworkInterface | None,
    ) -> set[MAC]:
        clients = set()
        status = wlanapi.WlanHostedNetworkQueryStatus()
        for peer in status.peer_list:
            clients.add(peer.mac_address)
        for client in self.ap_clients - clients:
            WifiAPClientDisconnectedEvent(client=client).broadcast()
        for client in clients - self.ap_clients:
            WifiAPClientConnectedEvent(client=client).broadcast()
        self.ap_clients = set(clients)
        return clients
