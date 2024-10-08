#  Copyright (c) Kuba Szczodrzyński 2023-9-11.

from dataclasses import dataclass
from ipaddress import IPv4Address
from pathlib import Path
from typing import Awaitable, Callable

HttpBody = str | bytes | dict | Path
Response = HttpBody | int | None


@dataclass
class Request:
    method: str
    path: str
    host: str | None
    query: dict | None
    headers: dict | None
    body: HttpBody | None = None
    address: IPv4Address | None = None

    def __post_init__(self) -> None:
        if self.method.upper() != self.method:
            raise ValueError("Method must be uppercase")
        if not self.path.startswith("/"):
            raise ValueError("Path must begin with /")
        if self.query:
            self.query = {k.lower(): v for k, v in self.query.items()}
        if self.headers:
            self.headers = {k.lower(): v for k, v in self.headers.items()}

    def format(self) -> str:
        # noinspection HttpUrlsUsage
        result = f"{self.method} http://{self.host or '.*'}{self.path}"
        if self.query:
            result += "?" + "&".join(f"{k}={v}" for k, v in self.query.items())
        return result


RequestHandler = Callable[[Request], Awaitable[Response]]
