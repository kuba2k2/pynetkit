#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import socketserver
from socket import socket
from socketserver import BaseRequestHandler

from pynetkit.util.socketio import SocketIO

from .module import HTTP_METHODS, ProxyModule
from .structs import TlsExtension, TlsHandshake, TlsHandshakeHello, TlsRecord
from .types.address import ProxyAddress
from .types.enums import ProxyPortMode, ProxyProtocol
from .types.socket import ProxySocket


class ProxyHandler(BaseRequestHandler):
    def __init__(
        self,
        request: socket,
        client_address: tuple[str, int],
        server: socketserver.BaseServer,
        proxy: ProxyModule,
        port: int,
        mode: ProxyPortMode,
    ) -> None:
        self.proxy = proxy
        self.port = port
        self.mode = mode
        try:
            self.proxy.debug(f"Connection opened - {request.getsockname()}")
            super().__init__(request, client_address, server)
        except ConnectionResetError:
            self.proxy.debug(f"Connection closed - {self.request.getsockname()}")
        except Exception as e:
            # handle request exceptions here
            self.proxy.exception(f"Proxy handler raised exception", exc_info=e)

    def detect_protocol(self, sock: ProxySocket) -> ProxyProtocol:
        match self.mode:
            case ProxyPortMode.DETECT:
                peek = sock.io.peek(6)
                if peek[0:3] == b"\x16\x03\x01" and peek[5] == 0x01:
                    return ProxyProtocol.TLS
                return ProxyProtocol.TCP
            case ProxyPortMode.TCP | ProxyPortMode.HTTP:
                return ProxyProtocol.TCP
            case ProxyPortMode.TLS | ProxyPortMode.HTTPS:
                if sock.parent and sock.parent.address.protocol == ProxyProtocol.TLS:
                    return ProxyProtocol.TCP
                return ProxyProtocol.TLS

    def fill_address(self, sock: ProxySocket) -> None:
        match sock.address.protocol:
            case None:
                raise ValueError("Protocol is not set")

            case ProxyProtocol.TCP if self.mode in (
                ProxyPortMode.DETECT,
                ProxyPortMode.HTTP,
                ProxyPortMode.HTTPS,
            ):
                if self.mode is ProxyPortMode.DETECT:
                    # accept only valid HTTP methods in DETECT mode
                    peek = sock.io.peek(6)
                    for method in HTTP_METHODS:
                        if method.startswith(peek[0 : len(method)]):
                            break
                    else:
                        return

                # read the entire request header and put it back
                request = sock.io.read_until(b"\r\n\r\n")
                sock.io.poke(request)

                lines = request.splitlines()
                http_method, _, http_path = lines[0].partition(b" ")
                http_path, _, http_ver = http_path.partition(b" ")
                http_headers = {
                    k.strip().lower(): v.strip().lower()
                    for k, _, v in [line.partition(b": ") for line in lines[1:]]
                    if k
                }
                http_host, _, http_port = http_headers.get(b"host", b"").partition(b":")

                host_str = http_host.decode("utf-8", errors="ignore").strip()
                port_str = http_port.decode("utf-8", errors="ignore").strip()
                path_str = http_path.decode("utf-8", errors="ignore").strip()
                if host_str:
                    sock.address.host = host_str
                if port_str.isnumeric():
                    sock.address.port = int(port_str)
                if path_str:
                    sock.address.path = path_str

            case ProxyProtocol.TLS:
                # read the TLS handshake and put it back
                # noinspection bad-argument-type
                rec = TlsRecord.unpack(sock.io)
                sock.io.poke(rec.pack())

                handshake: TlsHandshake = rec.data
                hello: TlsHandshakeHello = handshake.data
                for extension in hello.extensions:
                    if extension.type != TlsExtension.Type.SERVER_NAME:
                        self.proxy.debug(f"{extension}")
                        continue
                    # TODO support multiple server name
                    server_name: TlsExtension.ServerName = extension.data
                    sock.address.host = (
                        server_name.names[0].value if server_name.names else ""
                    )
                    break

    def handle(self) -> None:
        client = ProxySocket(
            address=ProxyAddress(
                port=self.port,
            ),
            io=SocketIO(self.request),
        )

        # detect if socket is TCP or TLS, based on the port matching mode
        client.address.protocol = self.detect_protocol(client)
        # try to read address fields if possible (plaintext HTTP or TLS w/ SNI)
        self.fill_address(client)

        target = self.proxy.resolve_target(client)
        self.proxy.debug(f"Proxy {client.address} -> {target}")
