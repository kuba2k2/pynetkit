#  Copyright (c) Kuba Szczodrzyński 2026-10-26.

from socket import socket
from typing import AnyStr


class SocketIO:
    buf: bytes = b""

    def __init__(self, s: socket):
        self.s = s
        self.pos = 0

    ### socket API ###

    def close(self) -> None:
        self.s.close()

    def shutdown(self, how: int, /) -> None:
        self.s.shutdown(how)

    def fileno(self) -> int:
        return self.s.fileno()

    def recv(self, n: int, flags: int = 0, /) -> bytes:
        data = b""
        if self.buf:
            data += self.buf[:n]
            self.buf = self.buf[n:]
            n -= len(data)
            self.pos += len(data)
        if n:
            data += self.s.recv(n, flags)
            self.pos += len(data)
        return data

    def send(self, data: bytes, flags: int = 0, /) -> int:
        return self.s.send(data, flags)

    def sendall(self, data: bytes, flags: int = 0, /) -> None:
        self.s.sendall(data, flags)

    ### BinaryIO API (read-only) ###

    def read(self, n: int = -1, /) -> AnyStr:
        return self.recv(n)

    def tell(self) -> int:
        return self.pos

    def seekable(self) -> bool:
        return False

    ### Custom extended API ###

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

    def poke(self, data: bytes) -> None:
        self.buf = data + self.buf
        self.pos -= len(data)

    def read_until(self, sep: bytes) -> bytes:
        data = b""
        while True:
            recv = self.recv(1)
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
