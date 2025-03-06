#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import asyncio
import re
import select
import socketserver
import threading
from asyncio import Future
from functools import partial
from ipaddress import IPv4Address
from socket import AF_INET, SOCK_STREAM, socket
from socketserver import BaseRequestHandler, ThreadingTCPServer
from threading import Thread
from typing import Callable

from pynetkit.modules.base import ModuleBase

from .events import ProxyEvent
from .structs import TlsExtension, TlsHandshake, TlsHandshakeHello, TlsRecord
from .types import ProxyProtocol, ProxySource, ProxyTarget, SocketIO

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


class ProxyHandler(BaseRequestHandler):
    def __init__(
        self,
        request: socket | tuple[bytes, socket],
        client_address: tuple[str, int],
        server: socketserver.BaseServer,
        proxy: ProxyModule,
        port: int,
        protocol: ProxyProtocol,
    ) -> None:
        self.proxy = proxy
        self.port = port
        self.protocol = protocol
        try:
            super().__init__(request, client_address, server)
        except ConnectionResetError:
            self.proxy.debug(f"Connection closed - {self.request.getsockname()}")
        except Exception as e:
            # handle request exceptions here
            self.proxy.exception(f"Proxy handler raised exception", exc_info=e)

    def handle(self) -> None:
        client: socket = self.request
        io = SocketIO(client)
        source = ProxySource(
            host="",
            port=self.port,
            protocol=self.protocol,
            path="",
        )

        self.proxy.debug(f"Connection opened - {client.getsockname()}")

        # detect the protocol if auto matching is enabled
        if source.protocol == ProxyProtocol.ANY:
            peek = io.peek(6)
            for method in HTTP_METHODS:
                if method.startswith(peek[0 : len(method)]):
                    source.protocol = ProxyProtocol.HTTP
                    break
            else:
                if peek[0:3] == b"\x16\x03\x01" and peek[5] == 0x01:
                    source.protocol = ProxyProtocol.TLS
                else:
                    source.protocol = ProxyProtocol.RAW

        match source.protocol:
            case ProxyProtocol.RAW:
                initial_data = io.buf
            case ProxyProtocol.TLS:
                rec = TlsRecord.unpack(io)
                initial_data = rec.pack()
                handshake: TlsHandshake = rec.data
                hello: TlsHandshakeHello = handshake.data
                for extension in hello.extensions:
                    if extension.type != TlsExtension.Type.SERVER_NAME:
                        continue
                    # TODO support multiple server name
                    server_name: TlsExtension.ServerName = extension.data
                    source.host = (
                        server_name.names[0].value if server_name.names else ""
                    )
                    break
            case ProxyProtocol.HTTP:
                initial_data = io.read_until(b"\r\n\r\n")
                headers = [line.partition(b":") for line in initial_data.splitlines()]
                headers = {k.strip().lower(): v.strip().lower() for k, _, v in headers}
                source.host = headers.get(b"host", b"").decode()
                source.path = (
                    initial_data.partition(b" ")[2]
                    .partition(b" ")[0]
                    .decode("utf-8", errors="ignore")
                )
            case _:
                raise RuntimeError("Unknown protocol")

        target = self.proxy.resolve_target(source, io)

        proxy_path = (
            f"{self.client_address[0]}:{self.client_address[1]} "
            f"- {source.host}:{source.port}{source.path or ''} "
            f"-> {target.host}:{target.port}{target.path or ''}"
            + (
                f" (via {target.http_proxy[0]}:{target.http_proxy[1]})"
                if target.http_proxy
                else ""
            )
        )
        self.proxy.debug(f"Proxy {source.protocol.name}: {proxy_path}")
        ProxyEvent(
            address=IPv4Address(self.client_address[0]),
            source=source,
            target=target,
        ).broadcast()

        if (source.host, source.port) == (target.host, target.port) and target.host in [
            "localhost",
            "127.0.0.1",
        ]:
            self.proxy.warning(
                "Resolved target address same as source address! Bailing out..."
            )
            client.close()
            return

        # patch the request line if target path is specified
        if (
            source.protocol == ProxyProtocol.HTTP
            and source.path != target.path
            and target.path
        ):
            method, delimiter, request = initial_data.partition(b" ")
            if delimiter:
                source_path, _, request = request.partition(b" ")
                initial_data = method + b" " + target.path.encode() + b" " + request
            else:
                self.proxy.warning(
                    f"HTTP request line invalid - {str(initial_data)[0:50]} [...]"
                )

        server = socket(AF_INET, SOCK_STREAM)

        if not target.http_proxy:
            server.connect((target.host, target.port))
        else:
            server.connect(target.http_proxy)
            if source.protocol != ProxyProtocol.HTTP:  # TLS and RAW
                connect = f"CONNECT {target.host}:{target.port} HTTP/1.1"
                server.sendall(f"{connect}\r\n\r\n".encode())
                io = SocketIO(server)
                data = io.read_until(b"\r\n\r\n")
                status = data.partition(b"\r\n")[0]
                if b"200" in status:
                    self.proxy.debug(f"Connected to {source.protocol.name} proxy")
                else:
                    self.proxy.warning(f"Couldn't connect to HTTPS proxy: {status}")
                    client.sendall(data)
                    initial_data = b""
            else:
                self.proxy.debug("Connected to HTTP proxy")
                # patch the request line to include target host/port
                method, delimiter, request = initial_data.partition(b" /")
                if delimiter:
                    target_host = f"http://{target.host}"
                    if target.port != 80:
                        target_host += f":{target.port}"
                    initial_data = method + b" " + target_host.encode() + b"/" + request
                else:
                    self.proxy.warning(
                        f"HTTP request line invalid - {str(initial_data)[0:50]} [...]"
                    )

        if initial_data:
            server.sendall(initial_data)

        running = True
        while running:
            rsocks, _, xsocks = select.select(
                [client, server],
                [client, server],
                [client, server],
                2.0,
            )
            if xsocks:
                self.proxy.warning(f"Socket exception, closing")
                break
            for rsock in rsocks:
                wsock = client if rsock == server else server
                try:
                    data = rsock.recv(4096)
                except ConnectionError as e:
                    self.proxy.warning(f"Proxy read error: {e}")
                    running = False
                    break
                if len(data) == 0:
                    # select() returned a read socket, but recv() returned 0
                    # socket is closed
                    running = False
                    break
                try:
                    wsock.sendall(data)
                except ConnectionError as e:
                    self.proxy.warning(f"Proxy write error: {e}")
                    running = False
                    break

        self.proxy.debug(f"Connection closed - {proxy_path}")
        client.close()
        server.close()
