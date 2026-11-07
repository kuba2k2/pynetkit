#  Copyright (c) Kuba Szczodrzyński 2025-3-6.

from logging import exception

from pynetkit.modules.base import BaseEvent
from pynetkit.util.misc import ellipsize

from .util.mce import mce


def event_log_print(e: BaseEvent):
    # compare class names to avoid importing all modules by default
    match type(e).__name__:
        case "DhcpLeaseEvent":
            from pynetkit.modules.dhcp import DhcpLeaseEvent

            e: DhcpLeaseEvent
            mce(
                f"§2DHCP§f: §1{e.client}§f - offered lease of §d{e.address}§f"
                + (e.host_name and f" (§d{e.host_name}§f)" or "")
                + (e.vendor_cid and f" (vendor: §d{e.vendor_cid}§f)" or "")
                + "§r"
            )

        case "DhcpReleaseEvent":
            from pynetkit.modules.dhcp import DhcpReleaseEvent

            e: DhcpReleaseEvent
            mce(
                f"§2DHCP§f: §1{e.client}§f - address released"
                + (e.host_name and f" (§d{e.host_name}§f)" or "")
                + (e.vendor_cid and f" (vendor: §d{e.vendor_cid}§f)" or "")
                + "§r"
            )

        case "DnsQueryEvent":
            from pynetkit.modules.dns import DnsQueryEvent

            e: DnsQueryEvent
            mce(
                f"§2DNS§f: §1{e.address or '(unknown address)'}§f - "
                f"§5{e.qname} {e.qtype}§f -> "
                + (", ".join(f"§d{rr}§f" for rr in e.rdata) or "(no response)")
                + "§r"
            )

        case "NtpSyncEvent":
            from pynetkit.modules.ntp import NtpSyncEvent

            e: NtpSyncEvent
            origin_timestamp = (
                e.origin_timestamp
                and e.origin_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                or "none"
            )
            server_timestamp = (
                e.server_timestamp
                and e.server_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                or "none"
            )
            mce(
                f"§2NTP§f: §1{e.address}§f - "
                f"origin timestamp: §d{origin_timestamp}§f, "
                f"server timestamp: §d{server_timestamp}§r"
            )

        case "ProxyEvent":
            from ssl import SSLEOFError, SSLError

            from pynetkit.modules.proxy import ProxyEvent

            e: ProxyEvent
            mitm_err = e.status == ProxyEvent.Status.MITM_ERR
            server_err = e.status == ProxyEvent.Status.SERVER_ERR
            no_err = e.status == ProxyEvent.Status.CONNECTED
            err = str(e.error) if e.error else "unknown error"
            match e.error:
                case SSLEOFError():
                    err = "EOF"
                case SSLError():
                    err = e.error.reason or err
                case ConnectionResetError():
                    err = "connection reset"
            mce(
                f"§2Proxy§f: "
                f"§1{e.client[0]}:{e.client[1]}§f - "
                f"§5{ellipsize(e.source, 50)}§f"
                + (mitm_err and f" -> §cMITM handshake failed ({err})§f" or "")
                + (e.mitm and no_err and f" -> §aSSL MITM§f" or "")
                + (e.target and f" -> §d{ellipsize(e.target, 50)}§f" or "")
                + (server_err and f" -> §cserver connection failed ({err})§f" or "")
                + (e.server and f" (§d{e.server[0]}:{e.server[1]}§f)" or "")
                + "§r"
            )

        case "ProxyHttpEvent":
            from pynetkit.modules.proxy import ProxyHttpEvent

            e: ProxyHttpEvent
            mce(
                f"§2Proxy§f: "
                f"§1{e.client[0]}:{e.client[1]}§f - "
                f"§5{ellipsize(e.incoming, 50)}§f -> §d{ellipsize(e.outgoing, 50)}§f "
                f"(§d{e.server[0]}:{e.server[1]}§f)§r"
            )

        case "WifiConnectedEvent":
            from pynetkit.modules.wifi import WifiConnectedEvent

            e: WifiConnectedEvent
            mce(f"§2Wi-Fi§f: §1{e.ssid}§f - connected to network§r")

        case "WifiDisconnectedEvent":
            from pynetkit.modules.wifi import WifiDisconnectedEvent

            e: WifiDisconnectedEvent
            mce(f"§2Wi-Fi§f: §1{e.ssid}§f - disconnected from network§r")

        case "WifiAPClientConnectedEvent":
            from pynetkit.modules.wifi import WifiAPClientConnectedEvent

            e: WifiAPClientConnectedEvent
            mce(f"§2Wi-Fi§f: §1{e.client}§f - client connected to AP§r")

        case "WifiAPClientDisconnectedEvent":
            from pynetkit.modules.wifi import WifiAPClientDisconnectedEvent

            e: WifiAPClientDisconnectedEvent
            mce(f"§2Wi-Fi§f: §1{e.client}§f - client disconnected from AP§r")


def event_log_handler(e: BaseEvent):
    try:
        event_log_print(e)
    except Exception as e:
        exception("Logging handler raised an exception", exc_info=e)


def event_log_subscribe():
    BaseEvent.subscribe_all(event_log_handler)


def event_log_unsubscribe():
    BaseEvent.unsubscribe(event_log_handler)
