#  Copyright (c) Kuba Szczodrzyński 2026-10-28.

import re
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
        match self.address.via:
            case None:
                self.io.connect(self.address.host_port)

            case (ProxyExternalProtocol.HTTP, host, port):
                self.io.connect((host, port))
                connect = f"CONNECT {self.address.host}:{self.address.port} HTTP/1.1"
                self.io.sendall(f"{connect}\r\n\r\n".encode())
                data = SocketIO.read_until(self.io, b"\r\n\r\n")
                status = data.partition(b"\r\n")[0]
                if b"200" not in status:
                    raise ConnectionError(
                        f"Couldn't connect to HTTP(s) proxy: {status}"
                    )

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
