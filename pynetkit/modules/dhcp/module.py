#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from datetime import timedelta
from ipaddress import IPv4Address, IPv4Interface
from socket import AF_INET, IPPROTO_UDP, SO_BROADCAST, SOCK_DGRAM, SOL_SOCKET, socket

from macaddress import MAC

from pynetkit.modules.base import ModuleBase
from pynetkit.util.misc import wake_udp_socket

from .enums import DhcpMessageType, DhcpOptionType, DhcpPacketType
from .events import DhcpLeaseEvent
from .structs import DhcpPacket


class DhcpModule(ModuleBase):
    PRE_RUN_CONFIG = ["address", "port"]
    # pre-run configuration
    address: IPv4Address
    port: int
    # runtime configuration
    interface: IPv4Interface | None = None
    range: tuple[IPv4Address, IPv4Address] | None = None
    dns: IPv4Address | None = None
    router: IPv4Address | None = None
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
        self.should_run = False
        await self.cleanup()
        await super().stop()

    async def cleanup(self) -> None:
        if self._sock:
            wake_udp_socket(self.address, self.port)
            self._sock.close()
        self._sock = None

    def _process_request(self) -> None:
        data, _ = self._sock.recvfrom(4096)
        if not self.should_run:
            return
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

        host_name = packet[DhcpOptionType.HOST_NAME]
        vendor_cid = packet[DhcpOptionType.VENDOR_CLASS_IDENTIFIER]
        param_list = packet[DhcpOptionType.PARAMETER_REQUEST_LIST] or []

        if self.interface is None:
            self.error(
                f"Cannot serve DHCP request from {packet.client_mac_address} "
                f"({host_name}) - no interface config set"
            )
            return

        self.verbose(
            f"Got BOOT_REQUEST({message_type.name}) "
            f"from {packet.client_mac_address} "
            f"(host_name={host_name}, vendor_cid={vendor_cid})"
        )

        address = self._choose_ip_address(packet.client_mac_address)
        network = self.interface.network

        packet.packet_type = DhcpPacketType.BOOT_REPLY
        packet.your_ip_address = address
        packet.server_ip_address = self.interface.ip
        if self.hostname:
            packet.server_host_name = self.hostname
        packet.options_clear()
        if message_type == DhcpMessageType.DISCOVER:
            action = "Offering"
            packet[DhcpOptionType.MESSAGE_TYPE] = DhcpMessageType.OFFER
        else:
            action = "ACK-ing"
            packet[DhcpOptionType.MESSAGE_TYPE] = DhcpMessageType.ACK
        packet[DhcpOptionType.SUBNET_MASK] = self.interface.netmask
        packet[DhcpOptionType.ROUTER] = self.router or self.interface.ip
        packet[DhcpOptionType.DNS_SERVERS] = self.dns or self.interface.ip
        packet[DhcpOptionType.DOMAIN_NAME] = "local"
        packet[DhcpOptionType.INTERFACE_MTU_SIZE] = 1500
        packet[DhcpOptionType.BROADCAST_ADDRESS] = network.broadcast_address
        packet[DhcpOptionType.NETBIOS_NODE_TYPE] = 8
        packet[DhcpOptionType.IP_ADDRESS_LEASE_TIME] = timedelta(days=7)
        packet[DhcpOptionType.SERVER_IDENTIFIER] = self.interface.ip
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
        if self.range:
            address, end = self.range
        else:
            network = self.interface.network
            address = network.network_address + 1
            end = network.broadcast_address - 1
        while address in self.hosts.values() or address == self.interface.ip:
            if address > end:
                raise RuntimeError("No more addresses to allocate")
            address += 1
        self.hosts[mac_address] = address
        return address
