#  Copyright (c) Kuba Szczodrzyński 2024-10-25.

from datetime import datetime, timedelta
from ipaddress import IPv4Address
from socket import (
    AF_INET,
    IPPROTO_UDP,
    SO_BROADCAST,
    SO_REUSEADDR,
    SOCK_DGRAM,
    SOL_SOCKET,
    socket,
)

from pynetkit.modules.base import ModuleBase
from pynetkit.util.misc import wake_udp_socket

from .events import NtpSyncEvent
from .structs import NtpPacket


class NtpModule(ModuleBase):
    PRE_RUN_CONFIG = ["address", "port"]
    # pre-run configuration
    address: IPv4Address
    port: int
    # runtime configuration
    offset: dict[IPv4Address | None, timedelta] | None = None
    # server handle
    _sock: socket | None = None

    def __init__(self):
        super().__init__()
        self.address = IPv4Address("0.0.0.0")
        self.port = 123
        self.offset = {}

    async def run(self) -> None:
        self.info(f"Starting NTP server on {self.address}:{self.port}")
        self._sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        self._sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        self._sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
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
        request, addr = self._sock.recvfrom(4096)
        if not self.should_run:
            return
        address = IPv4Address(addr[0])
        try:
            packet = NtpPacket.unpack(request)
        except Exception as e:
            self.warning(f"Invalid NTP packet: {e}")
            return

        offset = timedelta()
        if None in self.offset:
            offset = self.offset[None]
        if address in self.offset:
            offset = self.offset[address]

        now = datetime.now() + offset
        packet = NtpPacket(
            flags=NtpPacket.Flags(li=0, vn=3, mode=4),
            stratum=1,
            ppoll=2.0,
            precision=0.0625,
            refid=b"NIST",
            reftime=now,
            org=packet.xmt,
            rec=now,
            xmt=now,
        )
        response = packet.pack()

        # copy the ntp.xmt timestamp to ntp.org at byte-level
        # some clients compare these two, but conversion to datetime() loses precision
        response = response[0:24] + request[40:48] + response[32:48]

        self.debug(f"NTP request from {address}")
        self._sock.sendto(response, addr)
        NtpSyncEvent(
            address=address,
            origin_timestamp=packet.org,
        ).broadcast()
