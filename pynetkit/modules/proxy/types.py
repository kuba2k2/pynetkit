#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import re
from abc import ABC
from dataclasses import dataclass
from enum import Enum, auto
from socket import socket
from typing import IO, Optional

from pynetkit.util.misc import matches

URL_REGEX = re.compile(r"^(?:(raw|tcp|tls|https?)://)?([^:/]*?)(:\d+)?(/.*)?$")


class SocketIO(IO[bytes], ABC):
    buf: bytes = b""

    def __init__(self, s: socket):
        self.s = s
        self.pos = 0

    def read(self, n: int = ...) -> bytes:
        data = b""
        if self.buf:
            data += self.buf[:n]
            self.buf = self.buf[n:]
            n -= len(data)
            self.pos += len(data)
        if n:
            data += self.s.recv(n)
            self.pos += len(data)
        return data

    def peek(self, n: int) -> bytes:
        data = b""
        if self.buf:
            data += self.buf[:n]
            n -= len(data)
        if n:
            recv = self.s.recv(n)
            self.buf += recv
            data += recv
        return data

    def tell(self) -> int:
        return self.pos

    def read_until(self, sep: bytes) -> bytes:
        data = b""
        while True:
            data += self.s.recv(1)
            self.pos += len(data)
            if sep not in data:
                continue
            data, _, buf = data.partition(sep)
            self.buf = buf + self.buf
            self.pos -= len(buf)
            return data + sep


class ProxyProtocol(Enum):
    ANY = auto()
    RAW = auto()
    TLS = auto()
    HTTP = auto()


@dataclass
class ProxySource:
    host: str = ".*"
    port: int = 0
    protocol: ProxyProtocol = ProxyProtocol.ANY

    def __post_init__(self):
        if not self.port and ":" in self.host:
            self.host, _, self.port = self.host.rpartition(":")
            self.port = int(self.port)

    def matches(self, other: "ProxySource") -> bool:
        if self.port != 0 and self.port != other.port:
            return False
        if self.protocol != ProxyProtocol.ANY and self.protocol != other.protocol:
            return False
        return bool(matches(self.host, other.host))

    @staticmethod
    def parse(url: str) -> Optional["ProxySource"]:
        match = URL_REGEX.match(url)
        if not match:
            return None
        protocol_map = dict(
            raw=ProxyProtocol.RAW,
            tcp=ProxyProtocol.RAW,
            tls=ProxyProtocol.TLS,
            https=ProxyProtocol.TLS,
            http=ProxyProtocol.HTTP,
        )
        return ProxySource(
            host=match[2] or ".*",
            port=int(match[3]) if match[3] else 0,
            protocol=protocol_map[match[1]] if match[1] else ProxyProtocol.ANY,
        )

    def __str__(self) -> str:
        return f"{self.host}:{self.port or '*'} ({self.protocol.name})"


@dataclass
class ProxyTarget:
    host: str | None = None
    port: int = 0
    # TODO protocol change option (RAW->TLS, etc)
    # protocol: ProxyProtocol = ProxyProtocol.RAW
    http_proxy: tuple[str, int] = None

    def __post_init__(self):
        if not self.port and self.host and ":" in self.host:
            self.host, _, self.port = self.host.rpartition(":")
            self.port = int(self.port)

    @staticmethod
    def parse(url: str) -> Optional["ProxyTarget"]:
        match = URL_REGEX.match(url)
        if not match:
            return None
        if match[1]:
            raise ValueError("Protocol cannot be specified for proxy target")
        return ProxyTarget(
            host=match[2] or None,
            port=int(match[3]) if match[3] else 0,
        )

    def __str__(self) -> str:
        return f"{self.host or '*'}:{self.port or self.port or '*'}" + (
            self.http_proxy
            and f" (via {self.http_proxy[0]}:{self.http_proxy[1]})"
            or ""
        )
