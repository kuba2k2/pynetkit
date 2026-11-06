#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import select
import socketserver
from ipaddress import IPv4Address
from socket import AF_INET, SOCK_STREAM, socket
from socketserver import BaseRequestHandler
from ssl import PROTOCOL_TLS_CLIENT, PROTOCOL_TLS_SERVER, SSLContext, VerifyMode

from pynetkit.modules.ssl import SslStoreEntry
from pynetkit.util.socketio import PeekingIO, SocketIO

from .events import ProxyEvent, ProxyHttpEvent
from .module import HTTP_METHODS, ProxyModule
from .structs import TlsExtension, TlsHandshake, TlsHandshakeHello, TlsRecord
from .types.address import ProxyAddress
from .types.enums import ProxyExternalProtocol, ProxyPortMode, ProxyProtocol
from .types.http import ProxyHttpRequest
from .types.socket import ProxySocket


class ProxyHandler(BaseRequestHandler):
    client: ProxySocket
    server: ProxySocket
    client_name: tuple[IPv4Address, int]
    server_name: tuple[IPv4Address, int]

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
        self.proxy.debug(f"Connection opened - {client_address}")
        try:
            super().__init__(request, client_address, server)
        except ConnectionResetError:
            self.proxy.warning(f"Connection reset - {client_address}")
        except Exception as e:
            # handle request exceptions here
            self.proxy.exception(f"Proxy handler raised exception", exc_info=e)
        self.proxy.debug(f"Connection closed - {client_address}")

    def fill_protocol(self, sock: ProxySocket) -> None:
        match self.mode:
            case ProxyPortMode.DETECT:
                peek = sock.io.peek(6)
                if peek[0:3] == b"\x16\x03\x01" and peek[5] == 0x01:
                    protocol = ProxyProtocol.TLS
                else:
                    protocol = ProxyProtocol.TCP
            case ProxyPortMode.TCP | ProxyPortMode.HTTP:
                protocol = ProxyProtocol.TCP
            case ProxyPortMode.TLS | ProxyPortMode.HTTPS:
                if sock.parent and sock.parent.address.protocol == ProxyProtocol.TLS:
                    protocol = ProxyProtocol.TCP
                else:
                    protocol = ProxyProtocol.TLS

        if sock.address.protocol is None:
            sock.address.protocol = protocol
        sock.protocol = protocol
        self.proxy.verbose(f"Found protocol: {protocol.name}")

    def fill_address(self, sock: ProxySocket) -> None:
        match sock.protocol:
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

                # peek the entire request header
                http = ProxyHttpRequest.read(sock=PeekingIO(sock.io))
                http_host, _, http_port = http.header(
                    key=b"host",
                    default=b"",
                ).partition(b":")

                host_str = http_host.decode("utf-8", errors="ignore").strip()
                port_str = http_port.decode("utf-8", errors="ignore").strip()
                path_str = http.path.decode("utf-8", errors="ignore").strip()
                if host_str:
                    sock.address.host = host_str
                if port_str.isnumeric():
                    sock.address.port = int(port_str)
                if path_str:
                    sock.address.path = path_str

            case ProxyProtocol.TLS:
                # peek the TLS handshake
                rec = TlsRecord.unpack(PeekingIO(sock.io))

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

        self.proxy.verbose(f"Found address: {sock.address}")

    def setup(self) -> None:
        self.client = ProxySocket(
            address=ProxyAddress(port=self.port),
            io=SocketIO(self.request),
        )
        self.server = ProxySocket(
            address=ProxyAddress(port=self.port),
            io=SocketIO(socket(AF_INET, SOCK_STREAM)),
        )
        addr, port = self.client.io.getpeername()
        self.client_name = (IPv4Address(addr), port)

    def handle(self) -> None:
        # detect if socket is TCP or TLS, based on the port matching mode
        self.fill_protocol(self.client)
        # try to read address fields if possible (plaintext HTTP or TLS w/ SNI)
        self.fill_address(self.client)

        # try enabling SSL MITM mode if the module is available
        ssl_entry: SslStoreEntry | None = None
        if self.client.protocol == ProxyProtocol.TLS and self.proxy.ssl:
            # try proxy IP address first - but don't generate, so if it's found
            # then it was explicitly enabled
            ssl_names = [str(self.proxy.address)]
            ssl_entry = self.proxy.ssl.get_for_subject(ssl_names[-1])
            message = "No certificate"
            # otherwise try the SNI domain, or empty string but don't generate then
            if not ssl_entry:
                ssl_names.append(self.client.address.host or "")
                ssl_entry = self.proxy.ssl.get_for_subject(
                    ssl_names[-1],
                    can_generate=bool(ssl_names[-1]),
                )
                if ssl_names[-1]:
                    message = "No certificate and/or CA assigned"
                else:
                    message = (
                        "No certificate assigned (and SNI is missing - can't generate)"
                    )
            # enable SSL MITM if the certificate is available
            if not ssl_entry:
                self.proxy.warning(
                    f"{message} for any of: {ssl_names} - check SSL module configuration"
                )
            else:
                chain_path = self.proxy.ssl.export_chain_tmp(ssl_entry)
                ctx = SSLContext(PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(chain_path)
                # noinspection bad-argument-type
                ssl_sock = ctx.wrap_socket(
                    sock=self.client.io,
                    server_side=True,
                    do_handshake_on_connect=False,
                )
                # handshake with the client
                try:
                    ssl_sock.do_handshake()
                    self.client = ProxySocket(
                        address=self.client.address,
                        io=SocketIO(ssl_sock),
                        parent=self.client,
                    )
                    # set as TCP, as this socket now carries unencrypted traffic
                    self.client.protocol = ProxyProtocol.TCP
                    # fill address fields if protocol is HTTP
                    self.fill_address(self.client)
                except Exception as e:
                    ProxyEvent(
                        status=ProxyEvent.Status.MITM_ERR,
                        client=self.client_name,
                        source=self.client.address,
                        error=e,
                        mitm=ssl_entry,
                    ).broadcast()
                    return

        # resolve configured target address
        self.server.address = self.proxy.resolve_target(self.client)
        self.server.protocol = self.server.address.protocol or self.server.protocol

        # check if:
        # - source host/port is the same as target host/port (no rewrite was performed)
        # - target port is a listening port of this proxy
        # - target host is a local address that (likely) points to this proxy
        # in this case, the proxy would just request itself recursively - stop it before it's too late
        if (
            self.client.address.host_port == self.server.address.host_port
            and self.server.address.port in self.proxy.ports
            and self.server.address.host in self.proxy.get_local_addresses()
        ):
            self.proxy.warning(
                "Target address and port resolved to self! Bailing out..."
            )
            return

        # connect to the target server
        try:
            self.server.connect()
            addr, port = self.server.io.getpeername()
            self.server_name = (IPv4Address(addr), port)
        except Exception as e:
            ProxyEvent(
                status=ProxyEvent.Status.SERVER_ERR,
                client=self.client_name,
                source=self.client.address,
                target=self.server.address,
                error=e,
                mitm=ssl_entry,
            ).broadcast()
            return

        # broadcast an event with details about what's happening
        ProxyEvent(
            status=ProxyEvent.Status.CONNECTED,
            client=self.client_name,
            source=self.client.address,
            target=self.server.address,
            server=self.server_name,
            mitm=ssl_entry,
        ).broadcast()

        match (self.client.protocol, self.server.protocol):
            case (ProxyProtocol.TLS, ProxyProtocol.TCP):
                self.proxy.error(
                    f"Cannot proxy TLS->TCP on {self.client.address}: make sure MITM "
                    f"mode is enabled and a certificate (or CA) is assigned"
                )
                return

            case (ProxyProtocol.TCP, ProxyProtocol.TLS):
                ctx = SSLContext(PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = VerifyMode.CERT_NONE
                # noinspection bad-argument-type
                ssl_sock = ctx.wrap_socket(
                    sock=self.server.io,
                    server_side=False,
                    do_handshake_on_connect=True,
                    server_hostname=self.server.address.host,
                )
                ssl_sock.do_handshake()
                self.server = ProxySocket(
                    address=self.server.address,
                    io=SocketIO(ssl_sock),
                    parent=self.server,
                )
                # set as TCP, as this socket now carries unencrypted traffic
                self.server.protocol = ProxyProtocol.TCP

        assert (
            self.client.protocol == self.server.protocol
        ), f"Client and server protocols differ: {self.client.protocol} != {self.server.protocol}"

        # if the client speaks plaintext (or decrypted) HTTP, patch the request headers
        if self.client.is_http:
            http_out = http_in = ProxyHttpRequest.read(self.client.io)

            # set 'Connection: close' to route all requests via proxy
            http_out = http_out.with_header(b"Connection", b"close")

            # find implicit port number
            default_port = {
                None: self.server.address.port,
                ProxyProtocol.TCP: 80,
                ProxyProtocol.TLS: 443,
            }[self.server.address.protocol]

            # patch request line if necessary
            if self.client.address.path != self.server.address.path:
                http_out = http_out.with_path(self.server.address.path or "")

            # change 'Host:' header if necessary
            if self.client.address.host_port != self.server.address.host_port:
                host = self.server.address.host or ""
                if self.server.address.port != default_port:
                    host = f"{host}:{self.server.address.port or 80}"
                http_out = http_out.with_header(b"Host", host)

            # include 'Host:' in request line if using plain HTTP with an external proxy
            if (
                self.server.address.via
                and self.server.address.via[0] == ProxyExternalProtocol.HTTP
                and self.server.address.protocol == ProxyProtocol.TCP
            ):
                host = http_out.header(b"Host", default=b"")
                http_out = http_out.with_path(b"http://" + host + http_out.path)

            # broadcast an event for the HTTP request
            ProxyHttpEvent(
                client=self.client_name,
                incoming=http_in,
                outgoing=http_out,
                server=self.server_name,
            ).broadcast()

            # send to the server
            self.server.io.sendall(http_out.raw)

        running = True
        client_io = self.client.io
        server_io = self.server.io
        while running:
            # no need for select() if SocketIO already has some pending data
            if client_io.pending():
                rsocks = [client_io]
            elif server_io.pending():
                rsocks = [server_io]
            else:
                # do a timed wait if no data is ready yet
                # noinspection bad-argument-type
                rsocks, _, xsocks = select.select(
                    [client_io, server_io],
                    [],
                    [client_io, server_io],
                    2.0,
                )
                if xsocks:
                    self.proxy.warning(f"Socket exception, closing")
                    break

            for rsock in rsocks:
                wsock = client_io if rsock == server_io else server_io
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

    def finish(self) -> None:
        self.client.io.close()
        if self.client.parent:
            self.client.parent.io.close()
        self.server.io.close()
        if self.server.parent:
            self.server.parent.io.close()
