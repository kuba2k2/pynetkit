#  Copyright (c) Kuba Szczodrzyński 2026-10-28.

import re
import struct
from dataclasses import dataclass

from pynetkit.util.misc import matches
from pynetkit.util.socketio import SocketIO

from .address import ProxyAddress
from .enums import ProxyExternalProtocol, ProxyProtocol


@dataclass
class ProxySocket:
    address: ProxyAddress
    io: SocketIO
    protocol: ProxyProtocol = ProxyProtocol.TCP
    parent: "ProxySocket | None" = None

    def __post_init__(self) -> None:
        if self.address.protocol:
            self.protocol = self.address.protocol

    @property
    def is_http(self) -> bool:
        return self.protocol == ProxyProtocol.TCP and self.address.path is not None

    def connect(self) -> None:
        target_host, target_port = self.address.host_port
        if not target_host or not target_port:
            raise ValueError(f"Missing target host/port: {target_host}:{target_port}")

        match self.address.via:
            case None:
                self.io.connect((target_host, target_port))

            case (ProxyExternalProtocol.HTTP, host, port):
                self.io.connect((host, port))
                connect = f"CONNECT {target_host}:{target_port} HTTP/1.1"
                self.io.sendall(f"{connect}\r\n\r\n".encode())
                data = SocketIO.read_until(self.io, b"\r\n\r\n")
                status = data.partition(b"\r\n")[0]
                if b"200" not in status:
                    raise ConnectionError(
                        f"Couldn't connect to HTTP(s) proxy: {status}"
                    )

            case (ProxyExternalProtocol.SOCKS4, host, port):
                self.io.connect((host, port))
                request = struct.pack(
                    "!BBHI1s",
                    0x04,  # VER
                    0x01,  # CMD
                    target_port,  # DSTPORT
                    0xFF,  # DESTIP
                    b"\x00",  # ID
                )
                host = target_host.encode("ascii")
                request += host + b"\x00"
                self.io.sendall(request)
                response = self.io.recv(8)
                if response[1] != 0x5A:
                    raise ConnectionError(
                        f"Invalid SOCKS4 response: {response.hex(' ')}"
                    )

            case (ProxyExternalProtocol.SOCKS5, host, port):
                self.io.connect((host, port))
                request = struct.pack(
                    "!BBB",
                    0x05,  # VER
                    0x01,  # NAUTH
                    0x00,  # AUTH (No authentication)
                )
                self.io.sendall(request)
                response = self.io.recv(2)
                if response != b"\x05\x00":  # VER, CAUTH
                    raise ConnectionError(
                        f"Invalid SOCKS5 server choice: {response.hex(' ')}"
                    )
                request = b"\x04\x01\x00"  # VER, CMD, RSV
                request += b"\x03"  # TYPE (Domain name)
                request += len(target_host).to_bytes(1, "big")
                request += target_host.encode("ascii")
                request += target_port.to_bytes(2, "big")
                self.io.sendall(request)
                response = self.io.recv(4)
                if response[0:3] != b"\x05\x00\x00":  # VER, STATUS, RSV
                    raise ConnectionError(
                        f"Invalid SOCKS5 response: {response.hex(' ')}"
                    )
                # drop response packet
                if response[3] == 0x01:
                    self.io.recv(4)
                elif response[3] == 0x03:
                    name_len = self.io.recv(1)[0]
                    self.io.recv(name_len)
                elif response[3] == 0x04:
                    self.io.recv(16)
                self.io.recv(2)

            case (protocol, _, _):
                raise ValueError(f"Unsupported proxy protocol: {protocol}")

    def matches(self, pattern: ProxyAddress) -> bool:
        address = self.address
        # check protocol and port equality (if set in pattern)
        if pattern.protocol and pattern.protocol != address.protocol:
            return False
        if pattern.port and pattern.port != address.port:
            return False
        # check host/path - full match; use empty if not set in address
        if pattern.host and not matches(pattern.host, address.host or ""):
            return False
        if pattern.path and not matches(pattern.path, address.path or ""):
            return False
        return True

    def rewrite(self, pattern: ProxyAddress, rewrite: ProxyAddress) -> ProxyAddress:
        address = ProxyAddress(
            protocol=self.address.protocol,
            host=self.address.host,
            port=self.address.port,
            path=self.address.path,
            via=rewrite.via,
        )

        # protocol/port are simple fields - take value from 'rewrite', if set
        if rewrite.protocol:
            address.protocol = rewrite.protocol
        if rewrite.port:
            address.port = rewrite.port

        # perform RegEx replacement for host (or just copy value if not a RegEx)
        if rewrite.host:
            if pattern.host and "(" in pattern.host and "$" in rewrite.host:
                address.host = re.sub(
                    pattern.host,
                    rewrite.host.replace("$", "\\"),
                    address.host or "",
                )
            else:
                address.host = rewrite.host

        # same for path
        if rewrite.path:
            if pattern.path and "(" in pattern.path and "$" in rewrite.path:
                address.path = re.sub(
                    pattern.path,
                    rewrite.path.replace("$", "\\"),
                    address.path or "",
                )
            else:
                address.path = rewrite.path

        if not address.host:
            raise ValueError(f"Couldn't determine target hostname for {self.address}")

        return address

    def __str__(self) -> str:
        return (
            f"ProxySocket("
            f"address={self.address}, "
            f"io={self.io}, "
            f"protocol={self.protocol.name}"
            f")"
        )
