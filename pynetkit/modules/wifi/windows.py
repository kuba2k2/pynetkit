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
from pynetkit.types import NetworkAdapter, WifiNetwork
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
    access_point: WifiNetwork | None = None
    use_dpapi: bool = False

    async def start(self) -> None:
        await super().start()
        self._register()
        self.ap_clients = set()

    async def stop(self) -> None:
        self._unregister()
        await super().stop()

    def _make_dpapi(self):
        if self.dpapi is None or self.dpapi.key_cache is None:
            self.dpapi = Dpapi()
            self.dpapi.load_credentials()

    def _register(self):
        try:
            self.command("net", "start", "Wlansvc", silent=True)
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
                self.call_coroutine(self.get_access_point_clients(adapter=None))

            case _ if code not in (e.name for e in MSM):
                WifiRawEvent(code=code, data=data).broadcast()

    @module_thread
    async def scan_networks(
        self,
        adapter: NetworkAdapter,
    ) -> list[WifiNetwork]:
        adapter.ensure_wifi_sta()
        iface = iface_by_guid(adapter.obj)
        handle = Win32NativeWifiApi.WlanOpenHandle()
        Win32NativeWifiApi.WlanScan(handle, iface.guid)
        Win32NativeWifiApi.WlanCloseHandle(handle)
        return (await WifiScanCompleteEvent.any()).networks

    @module_thread
    async def start_station(
        self,
        adapter: NetworkAdapter,
        network: WifiNetwork,
    ) -> None:
        adapter.ensure_wifi_sta()
        iface = iface_by_guid(adapter.obj)
        xml = wlanmisc.make_xml_profile(network)
        if await self.get_station_state(adapter):
            await self.stop_station(adapter)
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
        adapter: NetworkAdapter,
    ) -> None:
        adapter.ensure_wifi_sta()
        iface = iface_by_guid(adapter.obj)
        _, state = Win32Wifi.queryInterface(iface, "interface_state")
        Win32Wifi.disconnect(iface)
        if await self.get_station_state(adapter):
            await WifiDisconnectedEvent.any()

    @module_thread
    async def get_station_state(
        self,
        adapter: NetworkAdapter,
    ) -> WifiNetwork | None:
        adapter.ensure_wifi_sta()
        iface = iface_by_guid(adapter.obj)
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

    def _read_hosted_network(
        self,
    ) -> tuple[HostedNetworkSettings | None, HostedNetworkSecurity | None]:
        try:
            settings = wlanhosted.read_settings()
        except FileNotFoundError:
            settings = None
        if self.use_dpapi:
            try:
                self._make_dpapi()
                security = wlanhosted.read_security(self.dpapi)
            except FileNotFoundError:
                security = None
        else:
            security = None
        return settings, security

    @module_thread
    async def start_access_point(
        self,
        adapter: NetworkAdapter,
        network: WifiNetwork,
    ) -> None:
        adapter.ensure_wifi_ap()
        config_changed = False

        self.use_dpapi = not network.password

        self.info("Configuring Hosted Network...")
        if self.use_dpapi:
            old_settings, old_security = self._read_hosted_network()
            if old_settings and (
                not old_settings.allowed or old_settings.not_configured
            ):
                old_settings = None

            system_key = (
                old_security
                and old_security.system_key
                or wlanhosted.make_security_system_key()
            )
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
                await self.stop_access_point(adapter)
                self._unregister(stop_wlansvc=True)
                await asyncio.sleep(2)

                self.debug("Writing Hosted Network settings")
                wlanhosted.write_settings(new_settings)

                self.debug("Writing Hosted Network security settings")
                self._make_dpapi()
                wlanhosted.write_security(self.dpapi, new_security)

                self._register()
                await WifiRawEvent(
                    code="wlan_notification_acm_interface_arrival",
                    data=None,
                )
        else:
            # command line-based implementation
            await self.stop_access_point(adapter)
            await asyncio.sleep(2)
            self.command(
                "netsh",
                "wlan",
                "set",
                "hostednetwork",
                "mode=allow",
                f"ssid={network.ssid}",
                f"key={(network.password or b'').decode('utf-8')}",
            )

        self.access_point = network
        if not await self.get_access_point_state(adapter):
            self.info(f"Starting Hosted Network '{network.ssid}'")
            future = WifiAPStartedEvent.any()
            self.command("netsh", "wlan", "start", "hostednetwork")
            await future
        else:
            self.info(f"Hosted Network '{network.ssid}' is already running")
            WifiAPStartedEvent().broadcast()

        await self.get_access_point_clients(adapter)

    @module_thread
    async def stop_access_point(
        self,
        adapter: NetworkAdapter,
    ) -> None:
        adapter.ensure_wifi_ap()
        if await self.get_access_point_state(adapter):
            self.info("Stopping Hosted Network")
            future = WifiAPStoppedEvent.any()
            self.command("netsh", "wlan", "stop", "hostednetwork")
            await future

    @module_thread
    async def get_access_point_state(
        self,
        adapter: NetworkAdapter,
    ) -> WifiNetwork | None:
        adapter.ensure_wifi_ap()
        status = wlanapi.WlanHostedNetworkQueryStatus()
        if status.state != WlanHostedNetworkStatus.State.ACTIVE:
            return None
        if self.access_point is None:
            # read settings from registry if started outside of WifiModule
            settings, security = self._read_hosted_network()
            if settings and security:
                self.access_point = WifiNetwork(
                    ssid=settings.ssid.decode(),
                    password=security.user_key,
                )
            elif settings:
                self.access_point = WifiNetwork(
                    ssid=settings.ssid.decode(),
                    password=b"(unknown)",
                )
        return self.access_point

    @module_thread
    async def get_access_point_clients(
        self,
        adapter: NetworkAdapter | None,
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
