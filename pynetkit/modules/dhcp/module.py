#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from datetime import timedelta
from ipaddress import IPv4Address, IPv4Network
from socket import AF_INET, IPPROTO_UDP, SO_BROADCAST, SOCK_DGRAM, SOL_SOCKET, socket

from macaddress import MAC

from pynetkit.modules.base import ModuleBase
from pynetkit.types import Ip4Config

from .enums import DhcpMessageType, DhcpOptionType, DhcpPacketType
from .events import DhcpLeaseEvent
from .structs import DhcpPacket


class DhcpModule(ModuleBase):
    PRE_RUN_CONFIG = ["address", "port"]
    # pre-run configuration
    address: IPv4Address
    port: int
    # runtime configuration
    ipconfig: Ip4Config | None = None
    range: tuple[IPv4Address, IPv4Address] | None = None
    dns: IPv4Address | None = None
    hostname: str | None = None
    hosts: dict[MAC, IPv4Address] | None = None
    # server handle
    _sock: socket | None = None

    def __init__(self):
        super().__init__()
        self.address = IPv4Address("0.0.0.0")
        self.port = 67
        self.hostname = "pynetkit"
        self.hosts = {}

    async def run(self) -> None:
        self.info(f"Starting DHCP server on {self.address}:{self.port}")
        self._sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        self._sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        self._sock.bind((str(self.address), self.port))
        while self.should_run and self._sock is not None:
            self._process_request()

    async def stop(self) -> None:
        await self.cleanup()
        await super().stop()

    async def cleanup(self) -> None:
        if self._sock:
            self._sock.close()
        self._sock = None

    def _process_request(self) -> None:
        data, _ = self._sock.recvfrom(4096)
        try:
            packet = DhcpPacket.unpack(data)
        except Exception as e:
            self.warning(f"Invalid DHCP packet: {e}")
            return
        if packet.packet_type != DhcpPacketType.BOOT_REQUEST:
            return
        message_type: DhcpMessageType = packet[DhcpOptionType.MESSAGE_TYPE]
        if message_type not in [
            DhcpMessageType.DISCOVER,
            DhcpMessageType.REQUEST,
            DhcpMessageType.INFORM,
        ]:
            self.warning(f"Unhandled message type: {message_type}")
            return

        if self.ipconfig is None:
            self.error(f"Cannot serve DHCP request - no IP config set")
            return
        if self.range is None:
            self.error(f"Cannot serve DHCP request - no lease address range set")
            return

        host_name = packet[DhcpOptionType.HOST_NAME]
        vendor_cid = packet[DhcpOptionType.VENDOR_CLASS_IDENTIFIER]
        param_list = packet[DhcpOptionType.PARAMETER_REQUEST_LIST]
        self.verbose(
            f"Got BOOT_REQUEST({message_type.name}) "
            f"from {packet.client_mac_address} "
            f"(host_name={host_name}, vendor_cid={vendor_cid})"
        )

        address = self._choose_ip_address(packet.client_mac_address)
        network = IPv4Network(
            address=(self.ipconfig.address, str(self.ipconfig.netmask)),
            strict=False,
        )

        packet.packet_type = DhcpPacketType.BOOT_REPLY
        packet.your_ip_address = address
        packet.server_ip_address = self.ipconfig.address
        if self.hostname:
            packet.server_host_name = self.hostname
        packet.options_clear()
        if message_type == DhcpMessageType.DISCOVER:
            action = "Offering"
            packet[DhcpOptionType.MESSAGE_TYPE] = DhcpMessageType.OFFER
        else:
            action = "ACK-ing"
            packet[DhcpOptionType.MESSAGE_TYPE] = DhcpMessageType.ACK
        packet[DhcpOptionType.SUBNET_MASK] = self.ipconfig.netmask
        packet[DhcpOptionType.ROUTER] = self.ipconfig.gateway
        if self.dns:
            packet[DhcpOptionType.DNS_SERVERS] = self.dns
            packet[DhcpOptionType.DOMAIN_NAME] = "local"
        packet[DhcpOptionType.INTERFACE_MTU_SIZE] = 1500
        packet[DhcpOptionType.BROADCAST_ADDRESS] = network.broadcast_address
        packet[DhcpOptionType.NETBIOS_NODE_TYPE] = 8
        packet[DhcpOptionType.IP_ADDRESS_LEASE_TIME] = timedelta(days=7)
        packet[DhcpOptionType.SERVER_IDENTIFIER] = self.ipconfig.address
        packet[DhcpOptionType.RENEW_TIME_VALUE] = timedelta(hours=12)
        packet[DhcpOptionType.REBINDING_TIME_VALUE] = timedelta(days=7)

        for option in param_list:
            if option in packet:
                continue
            self.warning(f"Requested DHCP option {option} not populated")

        self.debug(f"{action} {address} to {packet.client_mac_address} ({host_name})")
        self._sock.sendto(packet.pack(), ("255.255.255.255", 68))

        if message_type != DhcpMessageType.DISCOVER:
            DhcpLeaseEvent(
                client=packet.client_mac_address,
                address=address,
                host_name=host_name,
                vendor_cid=vendor_cid,
            ).broadcast()

    def _choose_ip_address(self, mac_address: MAC) -> IPv4Address:
        if mac_address in self.hosts:
            return self.hosts[mac_address]
        address, end = self.range
        while address in self.hosts.values():
            if address >= end:
                raise RuntimeError("No more addresses to allocate")
            address += 1
        self.hosts[mac_address] = address
        return address
