#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from abc import ABC
from dataclasses import dataclass
from enum import Enum, auto
from socket import socket
from typing import IO

from pynetkit.util import matches


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


@dataclass
class ProxyTarget:
    host: str
    port: int = 0
    # TODO protocol change option (RAW->TLS, etc)
    # protocol: ProxyProtocol = ProxyProtocol.RAW
    http_proxy: tuple[str, int] = None

    def __post_init__(self):
        if not self.port and ":" in self.host:
            self.host, _, self.port = self.host.rpartition(":")
            self.port = int(self.port)
