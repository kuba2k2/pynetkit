#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import asyncio
import re
import threading
from asyncio import Future
from functools import partial
from ipaddress import IPv4Address
from socket import gethostbyname_ex, gethostname
from socketserver import ThreadingTCPServer
from threading import Thread
from typing import Callable

from pynetkit.modules.base import ModuleBase
from pynetkit.util.socketio import SocketIO

from .types import ProxyProtocol, ProxySource, ProxyTarget

HTTP_METHODS = [
    b"GET",
    b"POST",
    b"PUT",
    b"PATCH",
    b"HEAD",
    b"OPTIONS",
    b"DELETE",
]


class ProxyModule(ModuleBase):
    PRE_RUN_CONFIG = ["address", "ports"]
    # pre-run configuration
    address: IPv4Address
    ports: dict[int, ProxyProtocol]
    # runtime configuration
    proxy_db: list[
        tuple[ProxySource, ProxyTarget] | Callable[[ProxySource, SocketIO], ProxyTarget]
    ] = None
    # server handle
    _threads: list[Thread] = None
    _servers: list[ThreadingTCPServer] = None

    def __init__(self):
        super().__init__()
        self.address = IPv4Address("0.0.0.0")
        self.ports = {
            80: ProxyProtocol.HTTP,
            443: ProxyProtocol.TLS,
        }
        self.proxy_db = [
            (ProxySource(), ProxyTarget()),
        ]
        self._threads = []
        self._servers = []

    # noinspection DuplicatedCode
    async def start(self) -> None:
        if not self.ports:
            raise RuntimeError("Proxy listen ports not configured")

        futures = []
        for port, protocol in self.ports.items():
            future = self.make_future()
            thread = Thread(
                target=self.proxy_entrypoint,
                args=[future, port, protocol],
                daemon=True,
            )
            thread.start()
            futures.append(future)

        await asyncio.gather(*futures)

    # noinspection DuplicatedCode
    async def stop(self) -> None:
        self.should_run = False
        for server in list(self._servers):
            server.shutdown()
            server.server_close()
        for thread in list(self._threads):
            thread.join()

    @property
    def is_started(self) -> bool:
        return bool(self._threads)

    def proxy_entrypoint(
        self,
        future: Future,
        port: int,
        protocol: ProxyProtocol,
    ) -> None:
        from .handler import ProxyHandler

        self.resolve_future(future)
        self.info(f"Starting {protocol.name} proxy on {self.address}:{port}")
        server = ThreadingTCPServer(
            server_address=(str(self.address), port),
            RequestHandlerClass=partial(
                ProxyHandler,
                proxy=self,
                port=port,
                protocol=protocol,
            ),
        )
        self._threads.append(threading.current_thread())
        self._servers.append(server)
        try:
            server.daemon_threads = True
            server.serve_forever()
        except Exception as e:
            raise e
        finally:
            self._threads.remove(threading.current_thread())
            self._servers.remove(server)

    def add_proxy(self, source: ProxySource, target: ProxyTarget) -> None:
        self.proxy_db.append((source, target))

    def add_simple_proxy(
        self,
        source_host: str,
        target_host: str,
        source_port: int = 0,
        target_port: int = 0,
        source_protocol: ProxyProtocol = ProxyProtocol.ANY,
    ) -> ProxyTarget:
        source = ProxySource(
            host=source_host,
            port=source_port,
            protocol=source_protocol,
        )
        target = ProxyTarget(
            host=target_host,
            port=target_port,
        )
        self.proxy_db.append((source, target))
        return target

    def clear_proxy_db(self) -> None:
        self.proxy_db = []

    def resolve_target(self, source: ProxySource, io: SocketIO | None) -> ProxyTarget:
        source_match: ProxySource | None = None
        for handler in self.proxy_db:
            if callable(handler):
                target = handler(source, io)
                if target:
                    break
            else:
                source_match, target = handler
                if source_match.matches(source):
                    break
        else:
            raise ValueError(f"No matching route for {source}")

        target = ProxyTarget(target.host, target.port, target.path, target.http_proxy)
        if not target.host:
            target.host = source.host
        if target.port == 0:
            target.port = source.port
        if not target.path:
            target.path = source.path
        if not target.host:
            raise ValueError(f"Couldn't determine target hostname for {source}")

        # perform RegEx replacements, if needed
        if source_match:
            if source.host and "$" in target.host and "(" in source_match.host:
                target.host = re.sub(
                    source_match.host,
                    target.host.replace("$", "\\"),
                    source.host,
                )
            if source.path and "$" in target.path and "(" in source_match.path:
                target.path = re.sub(
                    source_match.path,
                    target.path.replace("$", "\\"),
                    source.path,
                )

        return target

    def get_local_addresses(self) -> list[str]:
        addresses = gethostbyname_ex(gethostname())[2]
        addresses += ["127.0.0.1", "localhost", "::1"]
        addresses += [str(self.address)]
        return addresses
