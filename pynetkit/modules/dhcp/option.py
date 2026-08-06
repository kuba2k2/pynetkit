#  Copyright (c) Kuba Szczodrzyński 2026-8-6.

import re
from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Any

from macaddress import MAC

from pynetkit.util.misc import parse_timedelta

from .enums import DhcpOptionType

# { format: (parser, writer) }
FORMATS = {
    "u8": (int, lambda v: v.to_bytes(1, "big")),
    "u16": (int, lambda v: v.to_bytes(2, "big")),
    "u24": (int, lambda v: v.to_bytes(3, "big")),
    "u32": (int, lambda v: v.to_bytes(4, "big")),
    "str": (str, lambda v: v.encode("utf-8")),
    "bool": (bool, lambda v: int(v).to_bytes(1, "big")),
    "tdsec": (parse_timedelta, lambda v: int(v.total_seconds()).to_bytes(4, "big")),
    "ipv4": (IPv4Address, lambda v: v.packed),
}
BUILTIN_FORMATS = {
    DhcpOptionType.MAXIMUM_MESSAGE_SIZE: "u16",
    DhcpOptionType.INTERFACE_MTU_SIZE: "u16",
    DhcpOptionType.NETBIOS_NODE_TYPE: "u8",
    # time values
    DhcpOptionType.IP_ADDRESS_LEASE_TIME: "tdsec",
    DhcpOptionType.RENEW_TIME_VALUE: "tdsec",
    DhcpOptionType.REBINDING_TIME_VALUE: "tdsec",
    # text options
    DhcpOptionType.VENDOR_CLASS_IDENTIFIER: "str",
    DhcpOptionType.HOST_NAME: "str",
    DhcpOptionType.DOMAIN_NAME: "str",
    # IP address options
    DhcpOptionType.REQUESTED_IP_ADDRESS: "ipv4",
    DhcpOptionType.SERVER_IDENTIFIER: "ipv4",
    DhcpOptionType.SUBNET_MASK: "ipv4",
    DhcpOptionType.BROADCAST_ADDRESS: "ipv4",
    DhcpOptionType.ROUTER: "ipv4",
    DhcpOptionType.DNS_SERVERS: "ipv4",
}


@dataclass
class DhcpServerOption:
    key: DhcpOptionType | int
    value: Any | None
    name: str | None = None
    format: str | None = None
    client: MAC | None = None

    def __post_init__(self) -> None:
        if self.name is None and not isinstance(self.key, DhcpOptionType):
            self.name = "custom"
        if self.format is None and self.key not in BUILTIN_FORMATS:
            raise ValueError("Format must be specified for custom options")

    @property
    def sort_key(self) -> tuple[int, int]:
        return 0 if self.client else 1, self.key

    def __str__(self) -> str:
        if isinstance(self.key, DhcpOptionType):
            return f"{self.key:3d}: {self.key.name} ({self.format or BUILTIN_FORMATS[self.key]})"
        return f"{self.key:3d}: {self.name} ({self.format})"

    def get_value(self) -> Any | None:
        if self.value is None or self.value is Ellipsis:
            return self.value
        if self.format:
            return FORMATS[self.format][1](self.value)
        return self.value

    def dump(self) -> tuple[str, str | int | bool]:
        if isinstance(self.key, DhcpOptionType):
            option = self.key.name
            if self.format:
                option += f"({self.format})"
        else:
            option = f"{self.key}:{self.name}({self.format})"

        match self.value:
            case None:
                data = ""
            case _ if self.value is Ellipsis:
                data = "..."
            case str() | int() | bool():
                data = self.value
            case _:
                data = str(self.value)

        return option, data

    @staticmethod
    def parse(
        option: str,
        data: str,
        client: MAC | None = None,
    ) -> "DhcpServerOption":
        match = re.match(r"^(\d+:)?([^()]+)(\(\w+\))?$", option)

        if not match:
            raise ValueError(f"Cannot parse option: {option}")
        if match[1] and not match[2]:
            raise ValueError(f"Custom option name missing: {option}")
        if match[1] and not match[3]:
            raise ValueError(f"Custom option format missing: {option}")

        if match[1]:
            key = int(match[1].rstrip(":"))
            name = match[2]
            format = match[3].strip("()")
        elif match[2] not in [o.name for o in DhcpOptionType]:
            raise ValueError(f"Unknown option '{match[2]}', use custom option syntax")
        else:
            key = next(o for o in DhcpOptionType if o.name == match[2])
            name = None
            format = match[3].strip("()") if match[3] else None

        if format and format not in FORMATS:
            raise ValueError(f"Unknown format '{format}'")
        elif not format and key not in BUILTIN_FORMATS:
            raise ValueError(f"Specify custom format for '{match[2]}'")

        match data:
            case None:
                value = None
            case "...":
                value = Ellipsis
            case _:
                parser = FORMATS[format or BUILTIN_FORMATS[key]][0]
                value = parser(data)

        return DhcpServerOption(key, value, name, format, client)
