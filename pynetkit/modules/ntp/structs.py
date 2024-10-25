#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address
from math import log2

from datastruct import NETWORK, Adapter, DataStruct, datastruct
from datastruct.adapters.network import ipv4_field
from datastruct.fields import adapter, bitfield, field, switch

log2_field = adapter(
    encode=lambda value, ctx: value and int(log2(value)) or 0,
    decode=lambda value, ctx: value and float(2**value) or 0.0,
)
float32_field = adapter(
    encode=lambda value, ctx: (
        int(value).to_bytes(2, "big", signed=False)
        + int(value % 1.0 * 2.0**16).to_bytes(2, "big", signed=False)
    ),
    decode=lambda value, ctx: float(
        int.from_bytes(value[0:2], "big", signed=False)
        + int.from_bytes(value[2:4], "big", signed=False) / 2.0**16
    ),
)


class DateTimeAdapter(Adapter):
    POSIX_TIME_DIFF = 2208988800.0

    def encode(self, value: datetime | None, ctx) -> bytes:
        if not value:
            return b"\x00" * 8
        timestamp = value.timestamp() + self.POSIX_TIME_DIFF
        if timestamp > 2.0**32:
            timestamp -= 2.0**32
        return int(timestamp).to_bytes(4, "big", signed=False) + int(
            timestamp % 1.0 * 2.0**32
        ).to_bytes(4, "big", signed=False)

    def decode(self, value: bytes, ctx) -> datetime | None:
        if not value or not any(value):
            return None
        timestamp = (
            int.from_bytes(value[0:4], "big", signed=False)
            + int.from_bytes(value[4:8], "big", signed=False) / 2.0**32
            - self.POSIX_TIME_DIFF
        )
        if timestamp < 0:
            timestamp += 2.0**32
        return datetime.fromtimestamp(timestamp)


@dataclass
@datastruct(endianness=NETWORK, padding_pattern=b"\x00")
class NtpPacket(DataStruct):
    @dataclass
    class Flags:
        li: int
        vn: int
        mode: int

    flags: Flags = bitfield("u2u3u3", Flags, default=0x1B)
    stratum: int = field("B", default=0)
    ppoll: float = log2_field(field("b", default=1024.0))
    precision: float = log2_field(field("b", default=0.0))
    rootdelay: float = float32_field(field(4, default=0.0))
    rootdispersion: float = float32_field(field(4, default=0.0))
    refid: bytes | IPv4Address = switch(lambda ctx: ctx.stratum)(
        _0=(bytes, field(4, default=b"\x00" * 4)),
        _1=(bytes, field(4, default=b"\x00" * 4)),
        default=(IPv4Address, ipv4_field(default=IPv4Address("0.0.0.0"))),
    )
    reftime: datetime | None = adapter(DateTimeAdapter())(field(8, default=None))
    org: datetime | None = adapter(DateTimeAdapter())(field(8, default=None))
    rec: datetime | None = adapter(DateTimeAdapter())(field(8, default=None))
    xmt: datetime | None = adapter(DateTimeAdapter())(field(8, default=None))
