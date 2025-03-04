#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import asyncio
import json
import re
import socketserver
from asyncio import Future
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address
from pathlib import Path
from ssl import PROTOCOL_TLS, SSLContext, SSLSocket
from threading import Thread
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

# noinspection PyProtectedMember
from sslpsk3.sslpsk3 import _ssl_set_psk_server_callback

from pynetkit.modules.base import ModuleBase
from pynetkit.util.misc import matches

from .events import HttpRequestEvent, HttpResponseEvent
from .types import Request, RequestHandler

SSLCertType = tuple[str, str] | Callable[[str], tuple[str, str]]
SSLPSKType = bytes | Callable[[bytes], bytes]


class HttpModule(ModuleBase):
    # pre-run configuration
    _address: IPv4Address = None
    _http_port: int = None
    _https_port: int = None
    _https_protocol: int = None
    _https_ciphers: str = None
    _https_psk_hint: bytes = None
    # runtime configuration
    handlers: list[tuple[Request, RequestHandler]] = None
    ssl_cert_db: list[tuple[str, SSLCertType]] = None
    ssl_psk_db: list[tuple[bytes, SSLPSKType]] = None
    # server handle
    _http_thread: Thread | None = None
    _https_thread: Thread | None = None
    _http: ThreadingHTTPServer | None = None
    _https: ThreadingHTTPServer | None = None

    def __init__(self):
        super().__init__()
        self.handlers = []
        self.ssl_cert_db = []
        self.ssl_psk_db = []

    def configure(
        self,
        address: IPv4Address,
        http: int = 80,
        https: int = 443,
        https_protocol: int = PROTOCOL_TLS,
        https_ciphers: str = "ALL:!ADH:!LOW:!EXP:!MD5:@STRENGTH",
        https_psk_hint: bytes = None,
    ) -> None:
        if self._http is not None or self._https is not None:
            raise RuntimeError("Server already running, stop to reconfigure")
        self._address = address
        self._http_port = http
        self._https_port = https
        self._https_protocol = https_protocol
        self._https_ciphers = https_ciphers
        self._https_psk_hint = https_psk_hint

    async def start(self) -> None:
        if not self._address:
            raise RuntimeError("Server not configured")

        for request, func in self.handlers:
            name = re.match(r".+?function ([\w_.]+)", str(func)).group(1)
            self.debug(f"Found handler '{name}' for {request.format()}")

        http_future = self.make_future()
        self._http_thread = Thread(
            target=self.http_entrypoint,
            args=[http_future],
            daemon=True,
        )
        self._http_thread.start()

        https_future = self.make_future()
        self._https_thread = Thread(
            target=self.https_entrypoint,
            args=[https_future],
            daemon=True,
        )
        self._https_thread.start()

        await asyncio.gather(http_future, https_future)

    async def stop(self) -> None:
        self.should_run = False
        if self._http:
            self._http.shutdown()
            self._http_thread.join()
            self._http = self._http_thread = None
        if self._https:
            self._https.shutdown()
            self._https_thread.join()
            self._https = self._https_thread = None

    def http_entrypoint(self, future: Future) -> None:
        self.resolve_future(future)
        if not self._http_port:
            return
        self.info(f"Starting HTTP server on {self._address}:{self._http_port}")
        self._http = ThreadingHTTPServer(
            server_address=(str(self._address), self._http_port),
            RequestHandlerClass=partial(HttpRequestHandler, http=self),
        )
        self._http.serve_forever()

    def https_entrypoint(self, future: Future) -> None:
        self.resolve_future(future)
        if not self._https_port:
            return
        self.info(f"Starting HTTPS server on {self._address}:{self._https_port}")
        self._https = ThreadingHTTPServer(
            server_address=(str(self._address), self._https_port),
            RequestHandlerClass=partial(HttpRequestHandler, http=self),
        )
        ctx = SSLContext(protocol=self._https_protocol)
        ctx.set_ciphers(self._https_ciphers)
        ctx.sni_callback = self._ssl_sni_callback
        self._https.socket = ctx.wrap_socket(
            self._https.socket,
            server_side=True,
            do_handshake_on_connect=False,
        )
        real_accept = self._https.socket.accept

        def accept():
            sock, addr = real_accept()
            _ssl_set_psk_server_callback(
                sock=sock,
                psk_cb=lambda identity: self._ssl_psk_callback(identity),
                hint=self._https_psk_hint,
            )
            sock.do_handshake()
            return sock, addr

        self._https.socket.accept = accept
        self._https.serve_forever()

    def _ssl_sni_callback(self, sock: SSLSocket, sni: str, ctx: SSLContext) -> None:
        sni = sni or ""
        for pattern, value in self.ssl_cert_db:
            if not matches(pattern, sni):
                continue
            if callable(value):
                value = value(sni)
            if value is None:
                continue
            cert, key = value
            # TODO fix it properly
            # it applies to the *next* request instead of this one
            ctx.load_cert_chain(certfile=cert, keyfile=key)
            sock.context = ctx
            return
        self.warning(f"Unknown SNI name '{sni}'")

    def _ssl_psk_callback(self, identity: bytes) -> bytes:
        self.verbose(f"Connection with PSK identity {identity.hex()}")
        for pattern, psk in self.ssl_psk_db:
            if not matches(pattern, identity):
                continue
            if callable(psk):
                try:
                    psk = psk(identity)
                except ValueError:
                    psk = None
            if psk is None:
                continue
            return psk
        self.warning(f"Unknown PSK identity '{identity.hex()}'")
        return b""  # NoneType is not a valid return value

    def add_handler(
        self,
        func: RequestHandler,
        method: str,
        path: str,
        *,
        host: str = None,
        query: dict = None,
        headers: dict = None,
    ) -> None:
        model = Request(method, path, host, query, headers)
        self.handlers.append((model, func))

    def add_handlers(self, obj: object) -> None:
        def scan_type(scan_cls):
            scan_types = [scan_cls]
            for base in scan_cls.__bases__:
                scan_types += scan_type(base)
            return scan_types

        types = scan_type(type(obj))
        for cls in types:
            for func in cls.__dict__.values():
                if not hasattr(func, "__requests__"):
                    continue
                # decorated function is not bound to instance
                bound_func = partial(func, obj)
                for model in getattr(func, "__requests__"):
                    self.handlers.append((model, bound_func))

    def clear_handlers(self) -> None:
        self.handlers = []

    def add_ssl_cert(self, cert: str, key: str, sni: str = ".*") -> None:
        self.ssl_cert_db.append((sni, (cert, key)))

    def clear_ssl_certs(self) -> None:
        self.ssl_cert_db = []

    def add_ssl_psk(self, psk: SSLPSKType, identity: bytes = b".*") -> None:
        self.ssl_psk_db.append((identity, psk))

    def clear_ssl_psk(self) -> None:
        self.ssl_psk_db = []


# noinspection PyPep8Naming
class HttpRequestHandler(BaseHTTPRequestHandler):
    def __init__(
        self,
        request: bytes,
        client_address: tuple[str, int],
        server: socketserver.BaseServer,
        http: HttpModule,
    ) -> None:
        self.http = http
        try:
            super().__init__(request, client_address, server)
        except Exception as e:
            # handle request exceptions here
            self.http.exception(f"Request handler raised exception", exc_info=e)

    def log_request(self, code: int | str = ..., size: int | str = ...) -> None:
        self.http.info(f"{self.address_string()}: {self.command} {self.path} -> {code}")

    def log_error(self, msg: str, *args: Any) -> None:
        self.http.error(msg, *args)

    def do_GET(self) -> None:
        self.do_request()

    def do_POST(self) -> None:
        self.do_request()

    def do_request(self) -> None:
        try:
            self.handle_request()
        except Exception as e:
            self.http.exception(f"Exception in {self.command} {self.path}", exc_info=e)
            data = str(e)
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data.encode())

    def handle_request(self) -> None:
        address = IPv4Address(self.client_address[0])
        method = self.command
        url = urlparse(self.path)
        path = url.path
        query = parse_qs(url.query, keep_blank_values=True)
        query = {k.lower(): v[0] for k, v in query.items()}
        headers = {k.lower(): v for k, v in self.headers.items()}
        host = headers.get("host", "")

        if length := int(headers.get("content-length", 0)):
            body = self.rfile.read(length)
            match headers.get("content-type", "").partition(";")[0]:
                case "text/plain":
                    body = body.decode("utf-8")
                case "application/json":
                    body = json.loads(body.decode("utf-8"))
                case "application/x-www-form-urlencoded":
                    body = parse_qs(body.decode("utf-8"), keep_blank_values=True)
                    body = {k.lower(): v[0] for k, v in body.items()}
                case _:
                    try:
                        body = body.decode("utf-8")
                    except UnicodeDecodeError:
                        pass
        else:
            body = None

        request = Request(method, path, host, query, headers, body, address)
        HttpRequestEvent(request).broadcast()

        for model, func in self.http.handlers:
            if not matches(model.method, method):
                continue
            if not matches(model.path, path):
                continue
            if model.host and not matches(model.host, host):
                continue
            if model.query:
                if not all(
                    k in query and matches(v, query[k]) for k, v in model.query.items()
                ):
                    continue
            if model.headers:
                if not all(
                    k in headers and matches(v, headers[k])
                    for k, v in model.headers.items()
                ):
                    continue
            # execute the request handler to get a response
            try:
                coro = func(request)
                response = asyncio.new_event_loop().run_until_complete(coro)
            except Exception as e:
                self.http.exception("Request handler raised exception", exc_info=e)
                response = 500
            # finish if a response was returned
            if response is not None:
                break
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Connection", "close")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        HttpResponseEvent(request, response).broadcast()

        if isinstance(response, int):
            self.send_response(response)
            self.send_header("Connection", "close")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        match response:
            case str():
                content_type = "text/plain"
                body = response.encode("utf-8")
            case bytes():
                content_type = "application/octet-stream"
                body = response
            case Path():
                content_type = "application/octet-stream"
                body = response.read_bytes()
            case dict() | list():
                content_type = "application/json"
                body = json.dumps(response).encode("utf-8")
            case _:
                self.send_response(500)
                self.send_header("Connection", "close")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

        self.send_response(HTTPStatus.OK)
        self.send_header("Connection", "close")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
