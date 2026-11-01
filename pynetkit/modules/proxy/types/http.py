#  Copyright (c) Kuba Szczodrzyński 2026-11-1.

from dataclasses import dataclass

from pynetkit.util.socketio import SocketIO


@dataclass
class ProxyHttpRequest:
    raw: bytes
    method: bytes
    path: bytes
    ver: bytes
    headers: dict[bytes, bytes]

    @staticmethod
    def read(sock) -> "ProxyHttpRequest":
        raw = SocketIO.read_until(sock, b"\r\n\r\n")
        lines = raw.splitlines()
        method, _, path = lines[0].partition(b" ")
        path, _, ver = path.partition(b" ")
        headers = {
            k.strip(): v.strip()
            for k, _, v in [line.partition(b": ") for line in lines[1:]]
            if k
        }
        return ProxyHttpRequest(raw, method, path, ver, headers)

    def header(self, key: bytes, default=None) -> bytes:
        key = key.lower()
        for cur_k, cur_v in self.headers.items():
            if cur_k.lower() != key:
                continue
            return cur_v
        return default

    def with_path(self, path: bytes) -> "ProxyHttpRequest":
        old = self.method + b" " + self.path
        new = self.method + b" " + path
        return ProxyHttpRequest(
            raw=self.raw.replace(old, new, 1),
            method=self.method,
            path=path,
            ver=self.ver,
            headers=dict(self.headers),
        )

    def with_header(self, key: bytes, value: bytes) -> "ProxyHttpRequest":
        key = key.lower()
        for cur_k, cur_v in self.headers.items():
            if cur_k.lower() != key:
                continue
            old_header = cur_k + b": " + cur_v
            new_header = cur_k + b": " + value
            headers = dict(self.headers)
            headers[cur_k] = value
            return ProxyHttpRequest(
                raw=self.raw.replace(old_header, new_header, 1),
                method=self.method,
                path=self.path,
                ver=self.ver,
                headers=headers,
            )

        old = b"\r\n"
        new = b"\r\n" + key + b": " + value + b"\r\n"
        headers = dict(self.headers)
        headers[key] = value
        return ProxyHttpRequest(
            raw=self.raw.replace(old, new, 1),
            method=self.method,
            path=self.path,
            ver=self.ver,
            headers=headers,
        )
