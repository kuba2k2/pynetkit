#  Copyright (c) Kuba Szczodrzyński 2026-10-26.

from socket import MSG_PEEK, socket
from ssl import SSLSocket
from typing import BinaryIO


class SocketIO:
    buf: bytes = b""

    def __init__(self, s: socket | SSLSocket):
        self.s = s
        self.can_peek = not isinstance(s, SSLSocket)

    def __getattr__(self, name):
        return getattr(self.s, name)

    def recv(self, n: int, flags: int = 0, /) -> bytes:
        if self.can_peek:
            # using native peek implementation, so peek buffer not used
            return self.s.recv(n, flags)

        data = b""
        if self.buf:
            data += self.buf[:n]
            if not (flags & MSG_PEEK):
                self.buf = self.buf[n:]
            n -= len(data)

        if n:
            recv = self.s.recv(n)
            if flags & MSG_PEEK:
                self.buf += recv
            data += recv
        return data

    def read(self, n: int, /) -> bytes:
        return self.recv(n)

    def peek(self, n: int, /) -> bytes:
        return self.recv(n, MSG_PEEK)

    def pending(self) -> int:
        return len(self.buf) + (
            self.s.pending() if isinstance(self.s, SSLSocket) else 0
        )


class PeekingIO(BinaryIO):
    def __init__(self, io: SocketIO) -> None:
        self.io = io
        self.pos = 0

    def read(self, n: int = -1, /) -> bytes:
        pos = self.pos
        data = self.io.peek(pos + n)
        self.pos += len(data) - pos
        return data[pos:]

    def tell(self) -> int:
        return self.pos

    def seekable(self) -> bool:
        return False
