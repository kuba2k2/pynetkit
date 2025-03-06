#  Copyright (c) Kuba Szczodrzyński 2025-3-6.

from pynetkit.modules.base import BaseEvent

from .util.mce import mce


def event_log_handler(e: BaseEvent):
    # compare class names to avoid importing all modules by default
    match type(e).__name__:
        case "DhcpLeaseEvent":
            from pynetkit.modules.dhcp import DhcpLeaseEvent

            e: DhcpLeaseEvent
            mce(
                f"§2DHCP§f: lease of §d{e.address}§f offered to §d{e.client}§f"
                + (e.host_name and f" (§d{e.host_name}§f)" or "")
                + (e.vendor_cid and f" (vendor: §d{e.vendor_cid}§f)" or "")
                + "§r"
            )

        case "DnsQueryEvent":
            from pynetkit.modules.dns import DnsQueryEvent

            e: DnsQueryEvent
            mce(f"§2DNS§f: query - §d{e.qname} {e.qtype}§r")

        case "NtpSyncEvent":
            from pynetkit.modules.ntp import NtpSyncEvent

            e: NtpSyncEvent
            mce(
                f"§2NTP§f: request from §d{e.address}§f "
                f"(origin timestamp: "
                f"§d{e.origin_timestamp.strftime('%Y-%m-%d %H:%M:%S')}§f"
                f")§r"
            )

        case "ProxyEvent":
            from pynetkit.modules.proxy import ProxyEvent

            e: ProxyEvent
            mce(f"§2Proxy§f: {e.address} - §5{e.source}§f -> §d{e.target}§r")

        case "WifiConnectedEvent":
            from pynetkit.modules.wifi import WifiConnectedEvent

            e: WifiConnectedEvent
            mce(f"§2Wi-Fi§f: connected to §d{e.ssid}§r")

        case "WifiDisconnectedEvent":
            from pynetkit.modules.wifi import WifiDisconnectedEvent

            e: WifiDisconnectedEvent
            mce(f"§2Wi-Fi§f: disconnected from §d{e.ssid}§r")

        case "WifiAPClientConnectedEvent":
            from pynetkit.modules.wifi import WifiAPClientConnectedEvent

            e: WifiAPClientConnectedEvent
            mce(f"§2Wi-Fi§f: client connected to AP - §d{e.client}§r")

        case "WifiAPClientDisconnectedEvent":
            from pynetkit.modules.wifi import WifiAPClientDisconnectedEvent

            e: WifiAPClientDisconnectedEvent
            mce(f"§2Wi-Fi§f: client disconnected from AP - §d{e.client}§r")


def event_log_subscribe():
    BaseEvent.subscribe_all(event_log_handler)


def event_log_unsubscribe():
    BaseEvent.unsubscribe(event_log_handler)
