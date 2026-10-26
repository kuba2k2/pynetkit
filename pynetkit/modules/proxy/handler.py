#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import select
import socketserver
from ipaddress import IPv4Address
from socket import AF_INET, SOCK_STREAM, socket
from socketserver import BaseRequestHandler

from pynetkit.util.socketio import SocketIO

from .events import ProxyEvent
from .module import HTTP_METHODS, ProxyModule, ProxyProtocol, ProxySource
from .structs import TlsExtension, TlsHandshake, TlsHandshakeHello, TlsRecord


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

        http_method: str = ""
        http_headers: list[tuple[bytes, bytes]] = []
        http_headers_dict: dict[bytes, bytes] = {}

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

                http_method, _, _ = initial_data.partition(b" ")
                http_headers = [
                    (k, v)
                    for k, _, v in [
                        line.partition(b": ") for line in initial_data.split(b"\r\n")
                    ]
                ]
                http_headers_dict = {
                    k.strip().lower(): v.strip().lower() for k, v in http_headers
                }

                # get host name and strip port number
                source.host = (
                    http_headers_dict.get(b"host", b"").decode().partition(":")[0]
                )
                # get request path
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

        # check if:
        # - source host/port is the same as target host/port (no rewrite was performed)
        # - target port is a listening port of this proxy
        # - target host is a local address that (likely) points to this proxy
        # in this case, the proxy would just request itself recursively - stop it before it's too late
        if (
            (source.host, source.port) == (target.host, target.port)
            and target.port in self.proxy.ports
            and target.host in self.proxy.get_local_addresses()
        ):
            self.proxy.warning(
                "Target address and port resolved to self! Bailing out..."
            )
            client.close()
            return

        if source.protocol == ProxyProtocol.HTTP:

            def replace_http_header(name: bytes, new_value: bytes) -> bool:
                nonlocal initial_data
                for key, value in http_headers:
                    if key.strip().lower() != name:
                        continue
                    old_header = key + b": " + value
                    new_header = key + b": " + new_value
                    initial_data = initial_data.replace(old_header, new_header, 1)
                    return True
                return False

            # patch the request line if target path is specified
            if source.path != target.path and target.path:
                method, delimiter, request = initial_data.partition(b" ")
                if delimiter:
                    source_path, _, request = request.partition(b" ")
                    initial_data = method + b" " + target.path.encode() + b" " + request
                else:
                    self.proxy.warning(
                        f"HTTP request line invalid - {str(initial_data)[0:50]} [...]"
                    )

            # patch the host header if target host is specified
            if (source.host != target.host or source.port != target.port) and (
                target.host or target.port
            ):
                new_host = (
                    target.host if target.port == 80 else f"{target.host}:{target.port}"
                )
                replace_http_header(b"host", new_host.encode())

            # replace/add a Connection: close header to route all requests via proxy
            if not replace_http_header(b"connection", b"close"):
                # no Connection header, add one
                initial_data = initial_data.replace(
                    b"\r\n", b"\r\nConnection: close\r\n"
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
