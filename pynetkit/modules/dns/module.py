#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from ipaddress import IPv4Address
from typing import Callable

from dnslib import QTYPE, RCODE, RDMAP, RR, DNSQuestion, DNSRecord
from dnslib.proxy import ProxyResolver
from dnslib.server import BaseResolver, DNSHandler, DNSServer

from pynetkit.modules.base import ModuleBase
from pynetkit.utils import matches

from .events import DnsQueryEvent


class DnsModule(ModuleBase, BaseResolver):
    # pre-run configuration
    _address: IPv4Address = None
    _port: int = None
    _upstream: IPv4Address = None
    # runtime configuration
    dns_db: list[
        tuple[str, str, list[str | RR]] | Callable[[str, str], list[str | RR]]
    ] = None
    # server handle
    _dns: DNSServer | None = None
    _proxy: ProxyResolver | None = None

    def __init__(self):
        super().__init__()
        self._address = IPv4Address("0.0.0.0")
        self._port = 53
        self.dns_db = []

    def configure(
        self,
        address: IPv4Address,
        port: int = 53,
    ) -> None:
        if self._dns is not None:
            raise RuntimeError("Server already running, stop to reconfigure")
        self._address = address
        self._port = port

    async def start(self) -> None:
        self.info(f"Starting DNS server on {self._address}:{self._port}")
        self._dns = DNSServer(
            resolver=self,
            address=str(self._address),
            port=self._port,
        )
        self._dns.start_thread()
        # disable dnslib logging
        self._dns.server.logger.logf = lambda *_: None

        if self._upstream:
            self._proxy = ProxyResolver(
                address=str(self._upstream),
                port=53,
            )

    async def stop(self) -> None:
        if self._dns:
            self._dns.stop()
            self._dns.server.server_close()
            self._dns = None
        self._proxy = None

    def resolve(self, request: DNSRecord, handler: DNSHandler):
        reply: DNSRecord = request.reply()
        for q in request.questions:
            q: DNSQuestion

            # resolve the question
            qname = str(q.qname).rstrip(".")
            qtype = QTYPE[q.qtype]
            if qname.endswith(".local") or qname.endswith(".mshome.net"):
                continue
            for handler in self.dns_db:
                if callable(handler):
                    rdata = handler(qname, qtype)
                    if rdata:
                        break
                else:
                    rname, rtype, rdata = handler
                    if matches(rname, qname) and matches(rtype, qtype):
                        break
            else:
                self.warning(f"No DNS zone for {qtype} {qname}")
                DnsQueryEvent(qname=qname, qtype=qtype, rdata=[]).broadcast()
                continue
            self.debug(f"Answering DNS request {qtype} {qname}")
            DnsQueryEvent(qname=qname, qtype=qtype, rdata=rdata).broadcast()

            # send a reply
            for rr in rdata:
                if not isinstance(rr, RR):
                    rr = RR(
                        rname=q.qname,
                        rtype=q.qtype,
                        rdata=RDMAP[qtype](rr),
                    )
                reply.add_answer(rr)
        if not reply.rr:
            reply.header.rcode = RCODE.NXDOMAIN
        return reply

    @staticmethod
    def resolve_upstream(
        upstream: IPv4Address,
        qname: str,
        qtype: str,
    ) -> list[RR]:
        question = DNSRecord.question(qname, qtype)
        reply_bytes = question.send(str(upstream), port=53, tcp=False, timeout=2.0)
        reply = DNSRecord.parse(reply_bytes)
        return reply.rr

    def add_record(
        self,
        name: str,
        type: str,
        answer: str | IPv4Address,
    ) -> None:
        self.dns_db.append((name, type, [str(answer)]))

    def add_upstream(
        self,
        upstream: IPv4Address,
        rname: str = ".*",
        rtype: str = ".*",
    ) -> None:
        def handler(qname: str, qtype: str) -> list[RR]:
            if matches(rname, qname) and matches(rtype, qtype):
                return self.resolve_upstream(upstream, qname, qtype)
            return []

        self.dns_db.append(handler)

    def clear_records(self) -> None:
        self.dns_db = []
