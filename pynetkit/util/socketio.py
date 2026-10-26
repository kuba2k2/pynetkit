#  Copyright (c) Kuba Szczodrzyński 2026-10-26.

from abc import ABC
from socket import socket
from typing import IO


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
            recv = self.s.recv(1)
            if len(recv) == 0:
                raise ConnectionResetError("Socket closed")
            data += recv
            self.pos += len(data)
            if sep not in data:
                continue
            data, _, buf = data.partition(sep)
            self.buf = buf + self.buf
            self.pos -= len(buf)
            return data + sep
