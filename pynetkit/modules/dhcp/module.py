#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from collections import defaultdict
from datetime import timedelta
from ipaddress import IPv4Address, IPv4Interface
from socket import AF_INET, IPPROTO_UDP, SO_BROADCAST, SOCK_DGRAM, SOL_SOCKET, socket
from typing import Any

from macaddress import MAC

from pynetkit.modules.base import ModuleBase
from pynetkit.util.misc import wake_udp_socket

from .enums import DhcpMessageType, DhcpOptionType, DhcpPacketType
from .events import DhcpLeaseEvent, DhcpReleaseEvent
from .option import DhcpServerOption
from .structs import DhcpPacket


class DhcpModule(ModuleBase):
    PRE_RUN_CONFIG = ["address", "port"]
    # pre-run configuration
    address: IPv4Address
    port: int
    # runtime configuration
    interface: IPv4Interface | None = None
    range: tuple[IPv4Address, IPv4Address] | None = None
    hostname: str | None = None
    options: list[DhcpServerOption] = None
    # runtime status
    hosts: dict[MAC, IPv4Address] | None = None
    hosts_names: dict[MAC, str] | None = None
    hosts_vendor_cid: dict[MAC, str] | None = None
    # server handle
    _sock: socket | None = None

    def __init__(self):
        super().__init__()
        self.address = IPv4Address("0.0.0.0")
        self.port = 67
        self.hostname = "pynetkit"
        self.options = [
            DhcpServerOption(DhcpOptionType.SUBNET_MASK, ...),
            DhcpServerOption(DhcpOptionType.ROUTER, ...),
            DhcpServerOption(DhcpOptionType.DNS_SERVERS, ...),
            DhcpServerOption(DhcpOptionType.DOMAIN_NAME, "local"),
            DhcpServerOption(DhcpOptionType.INTERFACE_MTU_SIZE, 1500),
            DhcpServerOption(DhcpOptionType.BROADCAST_ADDRESS, ...),
            DhcpServerOption(DhcpOptionType.NETBIOS_NODE_TYPE, 8),
            DhcpServerOption(DhcpOptionType.IP_ADDRESS_LEASE_TIME, timedelta(days=7)),
            DhcpServerOption(DhcpOptionType.SERVER_IDENTIFIER, ...),
            DhcpServerOption(DhcpOptionType.RENEW_TIME_VALUE, timedelta(hours=12)),
            DhcpServerOption(DhcpOptionType.REBINDING_TIME_VALUE, timedelta(days=7)),
        ]
        self.hosts = {}
        self.hosts_names = {}
        self.hosts_vendor_cid = {}
        self.sort_options()

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

    def add_option(self, opt: DhcpServerOption) -> None:
        self.del_option(opt)
        self.options.append(opt)
        self.sort_options()

    def del_option(self, opt: DhcpServerOption) -> None:
        self.options = [
            o
            for o in self.options
            if (int(o.key), o.client) != (int(opt.key), opt.client)
        ]

    def sort_options(self) -> None:
        self.options = sorted(self.options, key=lambda o: o.sort_key)

    def get_options(self, client: MAC) -> list[DhcpServerOption]:
        return list(
            {
                o.key: o for o in self.options if o.client is None or o.client == client
            }.values()
        )

    def dump_options(self) -> dict[MAC | None, dict[str, str | int | bool]]:
        out = defaultdict(dict)
        for opt in self.options:
            option, data = opt.dump()
            out[opt.client][option] = data
        return out

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
        if message_type is None:
            # return on bogus message types
            return
        if message_type not in [
            DhcpMessageType.DISCOVER,
            DhcpMessageType.REQUEST,
            DhcpMessageType.INFORM,
            DhcpMessageType.RELEASE,
        ]:
            self.warning(f"Unhandled message type: {message_type.name}")
            return

        host_name: str | None = packet[DhcpOptionType.HOST_NAME]
        vendor_cid: str | None = packet[DhcpOptionType.VENDOR_CLASS_IDENTIFIER]
        param_list: list[DhcpOptionType] = packet[DhcpOptionType.PARAMETER_REQUEST_LIST]

        if message_type == DhcpMessageType.RELEASE:
            self.debug(
                f"Releasing address of {packet.client_mac_address} ({host_name})"
            )
            DhcpReleaseEvent(
                client=packet.client_mac_address,
                host_name=host_name,
                vendor_cid=vendor_cid,
            ).broadcast()
            return

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
        self.hosts_names[packet.client_mac_address] = host_name
        self.hosts_vendor_cid[packet.client_mac_address] = vendor_cid

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

        auto_options: dict[int, Any] = {
            DhcpOptionType.SUBNET_MASK: self.interface.netmask,
            DhcpOptionType.ROUTER: self.interface.ip,
            DhcpOptionType.DNS_SERVERS: self.interface.ip,
            DhcpOptionType.BROADCAST_ADDRESS: self.interface.network.broadcast_address,
            DhcpOptionType.SERVER_IDENTIFIER: self.interface.ip,
        }

        for opt in self.get_options(packet.client_mac_address):
            key, value = opt.key, opt.get_value()
            if value is Ellipsis:
                value = auto_options.get(key)
            if value is None:
                continue
            packet[key] = value

        for option in param_list or []:
            if option in packet:
                continue
            self.warning(f"Requested DHCP option {option.name} not populated")

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
