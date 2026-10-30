#  Copyright (c) Kuba Szczodrzyński 2026-10-27.

import re
from dataclasses import dataclass
from typing import Optional

from .enums import ProxyProtocol

URL_REGEX = re.compile(
    r"^(?:(\*|raw|tcp|tls|https?)://)?([^:/]*?)(?::(\d+|\*))?(/.*)?$"
)


@dataclass
class ProxyAddress:
    protocol: ProxyProtocol | None = None
    host: str | None = None
    port: int | None = None
    path: str | None = None
    via: tuple[str, int] | None = None

    def __post_init__(self):
        if self.host and not self.port and ":" in self.host:
            self.host, _, port = self.host.rpartition(":")
            self.port = int(port)

    def dump(self) -> dict:
        out = dict(
            protocol=self.protocol.name if self.protocol else None,
            host=self.host,
            port=self.port,
            path=self.path,
            via=(f"{self.via[0]}:{self.via[1]}" if self.via else None),
        )
        return {k: v for k, v in out.items() if v}

    @staticmethod
    def load(data: dict) -> str:
        return "".join(
            [
                data["protocol"].lower() + "://" if data.get("protocol") else "",
                data["host"] if data.get("host") else "",
                ":" + data["port"] if data.get("port") else "",
                data["path"] if data.get("path") else "",
            ]
        )

    @staticmethod
    def parse(url: str) -> Optional["ProxyAddress"]:
        match = URL_REGEX.match(url)
        if not match:
            return None
        protocol_map = dict(
            raw=ProxyProtocol.TCP,
            tcp=ProxyProtocol.TCP,
            tls=ProxyProtocol.TLS,
            http=ProxyProtocol.TCP,
            https=ProxyProtocol.TLS,
        )
        return ProxyAddress(
            protocol=protocol_map[match[1]] if match[1] and match[1] != "*" else None,
            host=match[2] if match[2] and match[2] not in (".*", "*", "") else None,
            port=int(match[3]) if match[3] and match[3] != "*" else None,
            path=match[4] or None,
        )

    def __str__(self) -> str:
        protocol = f"{self.protocol.name.lower()}://" if self.protocol else ""
        host = self.host or ""
        port = f":{self.port}" if self.port else ""
        path = self.path or ""
        return f"{protocol}{host}{port}{path}" or "(any)"
