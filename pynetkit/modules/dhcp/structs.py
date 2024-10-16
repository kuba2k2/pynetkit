#  Copyright (c) Kuba Szczodrzyński 2023-9-10.

from dataclasses import dataclass
from datetime import timedelta
from ipaddress import IPv4Address
from random import randint
from typing import Any

from datastruct import NETWORK, DataStruct, datastruct
from datastruct.adapters.network import ipv4_field, mac_field
from datastruct.adapters.time import timedelta_field
from datastruct.fields import (
    built,
    cond,
    const,
    field,
    padding,
    repeat,
    subfield,
    switch,
    text,
    varlist,
    vartext,
)
from macaddress import MAC

from .enums import DhcpBootpFlags, DhcpMessageType, DhcpOptionType, DhcpPacketType


@dataclass
class DhcpClientIdentifier(DataStruct):
    hardware_type: int = const(1)(field("B"))
    mac_address: MAC = mac_field()


@dataclass
@datastruct(endianness=NETWORK, padding_pattern=b"\x00")
class DhcpOption(DataStruct):
    option: DhcpOptionType = field("B")
    length: int = cond(lambda ctx: ctx.option != 255, if_not=0)(
        built("B", lambda ctx: ctx.sizeof("data"))
    )
    data: Any = cond(lambda ctx: ctx.option != 255, if_not=None)(
        switch(lambda ctx: ctx.option)(
            MESSAGE_TYPE=(DhcpMessageType, field("B")),
            CLIENT_IDENTIFIER=(DhcpClientIdentifier, subfield()),
            MAXIMUM_MESSAGE_SIZE=(int, field("H")),
            INTERFACE_MTU_SIZE=(int, field("H")),
            NETBIOS_NODE_TYPE=(int, field("B")),
            # time values
            IP_ADDRESS_LEASE_TIME=(timedelta, timedelta_field()),
            RENEW_TIME_VALUE=(timedelta, timedelta_field()),
            REBINDING_TIME_VALUE=(timedelta, timedelta_field()),
            # text options
            VENDOR_CLASS_IDENTIFIER=(str, vartext(lambda ctx: ctx.length)),
            HOST_NAME=(str, vartext(lambda ctx: ctx.length)),
            DOMAIN_NAME=(str, vartext(lambda ctx: ctx.length)),
            # IP address options
            REQUESTED_IP_ADDRESS=(IPv4Address, ipv4_field()),
            SERVER_IDENTIFIER=(IPv4Address, ipv4_field()),
            SUBNET_MASK=(IPv4Address, ipv4_field()),
            BROADCAST_ADDRESS=(IPv4Address, ipv4_field()),
            ROUTER=(IPv4Address, ipv4_field()),
            DNS_SERVERS=(IPv4Address, ipv4_field()),
            # other options
            PARAMETER_REQUEST_LIST=(
                list[DhcpOptionType],
                varlist(lambda ctx: ctx.length)(field("B")),
            ),
            default=(bytes, field(lambda ctx: ctx.length)),
        )
    )


@dataclass
@datastruct(endianness=NETWORK, padding_pattern=b"\x00")
class DhcpPacket(DataStruct):
    packet_type: DhcpPacketType = field("B")
    hardware_type: int = const(1)(field("B"))
    hardware_alen: int = const(6)(field("B"))
    hops: int = field("b", default=0)
    transaction_id: int = field("I", default_factory=lambda: randint(0, 0xFFFFFFFF))
    seconds_elapsed: timedelta = timedelta_field("H", default=timedelta(0))
    bootp_flags: DhcpBootpFlags = field("H", default=0)
    client_ip_address: IPv4Address = ipv4_field(default=IPv4Address(0))
    your_ip_address: IPv4Address = ipv4_field(default=IPv4Address(0))
    server_ip_address: IPv4Address = ipv4_field(default=IPv4Address(0))
    gateway_ip_address: IPv4Address = ipv4_field(default=IPv4Address(0))
    client_mac_address: MAC = mac_field()
    _1: ... = padding(10)
    server_host_name: str = text(64, default="")
    boot_file_name: str = text(128, default="")
    magic_cookie: bytes = const(b"\x63\x82\x53\x63")(field(4))
    options: list[DhcpOption] = repeat(
        last=lambda ctx: ctx.P.item.option == 255,
        default_factory=lambda: [DhcpOption(DhcpOptionType.END)],
    )(subfield())

    def __contains__(self, type: DhcpOptionType) -> bool:
        for option in self.options:
            if option.option == type:
                return True
        return False

    def __getitem__(self, type: DhcpOptionType) -> Any:
        return self.option(type).data

    def __setitem__(self, type: DhcpOptionType, data: Any) -> None:
        self.option(type).data = data

    def option(self, type: DhcpOptionType) -> DhcpOption:
        for option in self.options:
            if option.option == type:
                return option
        option = DhcpOption(option=type, length=0, data=None)
        self.options.insert(-1, option)
        return option

    def options_clear(self) -> None:
        self.options.clear()
        self.options.append(DhcpOption(DhcpOptionType.END))
