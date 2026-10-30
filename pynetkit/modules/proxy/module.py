#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import asyncio
import threading
from asyncio import Future
from functools import partial
from ipaddress import IPv4Address
from socket import gethostbyname_ex, gethostname
from socketserver import ThreadingTCPServer
from threading import Thread
from typing import Callable

from pynetkit.modules.base import ModuleBase

from .types.address import ProxyAddress
from .types.enums import ProxyPortMode
from .types.socket import ProxySocket

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
    ports: dict[int, ProxyPortMode]
    # runtime configuration
    proxy_db: list[
        tuple[ProxyAddress, ProxyAddress] | Callable[[ProxySocket], ProxyAddress]
    ] = None
    # server handle
    _threads: list[Thread] = None
    _servers: list[ThreadingTCPServer] = None

    def __init__(self):
        super().__init__()
        self.address = IPv4Address("0.0.0.0")
        self.ports = {
            80: ProxyPortMode.HTTP,
            443: ProxyPortMode.HTTPS,
        }
        self.proxy_db = [
            (ProxyAddress(), ProxyAddress()),
        ]
        self._threads = []
        self._servers = []

    async def start(self) -> None:
        if not self.ports:
            raise RuntimeError("Proxy listen ports not configured")

        futures = []
        for port, mode in self.ports.items():
            future = self.make_future()
            thread = Thread(
                target=self.proxy_entrypoint,
                args=[future, port, mode],
                daemon=True,
            )
            thread.start()
            futures.append(future)

        await asyncio.gather(*futures)

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
        mode: ProxyPortMode,
    ) -> None:
        from .handler import ProxyHandler

        self.resolve_future(future)
        self.info(f"Starting {mode.name} proxy on {self.address}:{port}")
        server = ThreadingTCPServer(
            server_address=(str(self.address), port),
            RequestHandlerClass=partial(
                ProxyHandler,
                proxy=self,
                port=port,
                mode=mode,
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

    def add_proxy(self, pattern: ProxyAddress, rewrite: ProxyAddress) -> None:
        self.proxy_db.append((pattern, rewrite))

    def clear_proxy_db(self) -> None:
        self.proxy_db = []

    def resolve_target(self, socket: ProxySocket) -> ProxyAddress:
        for handler in self.proxy_db:
            if callable(handler):
                address = handler(socket)
                if address:
                    return address
            else:
                pattern, rewrite = handler
                if socket.matches(pattern):
                    return socket.rewrite(pattern, rewrite)

        raise ValueError(f"No matching route for {socket.address}")

    def get_local_addresses(self) -> list[str]:
        addresses = gethostbyname_ex(gethostname())[2]
        addresses += ["127.0.0.1", "localhost", "::1"]
        addresses += [str(self.address)]
        return addresses
