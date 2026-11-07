#  Copyright (c) Kuba Szczodrzyński 2026-11-2.

from collections import defaultdict
from io import BytesIO
from ipaddress import IPv4Address
from pathlib import Path
from tempfile import gettempdir
from typing import IO, Any

from cryptography.hazmat.primitives.asymmetric.dsa import DSAPublicKey
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.asymmetric.types import (
    CertificateIssuerPrivateKeyTypes,
)
from cryptography.hazmat.primitives.hashes import MD5, SHA256, Hash
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from cryptography.x509 import Certificate, load_pem_x509_certificates

from pynetkit.modules.base import BaseEvent, ModuleBase, subscribe
from pynetkit.util.misc import matches_wildcard

from .types import SslStoreEntry


class SslModule(ModuleBase):
    # runtime configuration
    cert_db: list[SslStoreEntry]
    # runtime status
    # { fingerprint: { client: { error|None: count } } }
    trust_db: dict[bytes, dict[IPv4Address, dict[str | None, int]]]

    def __init__(self):
        super().__init__()
        self.cert_db = []
        self.trust_db = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(int),
            )
        )
        self.tmp_dir = Path(gettempdir()).resolve() / "pynetkit" / "ssl"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    @subscribe(BaseEvent)
    async def on_proxy_event(self, e: BaseEvent) -> None:
        from ssl import SSLError

        from pynetkit.modules.proxy import ProxyEvent

        if not isinstance(e, ProxyEvent):
            return
        if not e.mitm:
            return

        fingerprint = e.mitm.fingerprint
        client = e.client[0]
        error = None
        match e.error:
            case SSLError():
                error = e.error.reason
            case ConnectionResetError():
                error = "connection reset"
            case _ if e.error:
                error = type(e.error).__name__
        self.trust_db[fingerprint][client][error] += 1

    def sort_db(self) -> None:
        def key(e: SslStoreEntry):
            return (
                # CA before non-CA
                not e.is_ca,
                # chain-only before entries with private keys
                bool(e.key),
                # imported/exported entries before temporary/generated ones
                not bool(e.paths),
                # specific hosts before wildcards
                e.subject_cn.startswith("*."),
                # otherwise subject CN decides order
                e.subject_cn.lower(),
                # same CN? perhaps issuer differs
                e.issuer_cn.lower(),
                # okay, try fingerprint as last resort
                e.fingerprint.hex(),
            )

        self.cert_db.sort(key=key)

    def import_files(self, *paths: Path) -> tuple[int, int]:
        cert_count = 0
        key_count = 0

        pem_files = []

        def load_file(pem_path: Path):
            if not pem_path.is_file():
                self.warning(f"Not a file: {pem_path}")
                return
            if pem_path.stat().st_size > 10 * 1024:
                self.warning(f"File too long: {pem_path}")
                return
            pem_bytes = pem_path.read_bytes()
            if pem_bytes[0:10] != b"-----BEGIN":
                self.warning(f"Not a PEM file: {pem_path}")
                return
            pem_files.append((pem_path, pem_bytes))

        for path in paths:
            if path.is_dir():
                for subpath in path.glob("*.pem"):
                    load_file(subpath)
            else:
                load_file(path)

        # load certificates first
        for path, pem in pem_files:
            try:
                certs = load_pem_x509_certificates(pem)
                for cert in certs:
                    if self.import_certificate(cert, path):
                        cert_count += 1
            except ValueError:
                pass

        # assign private keys to certificates
        for path, pem in pem_files:
            try:
                key = load_pem_private_key(pem, password=None)
                # noinspection bad-argument-type
                if self.import_key(key, path):
                    key_count += 1
            except ValueError:
                pass

        return cert_count, key_count

    def import_certificate(
        self,
        cert: Certificate,
        path: Path | None = None,
    ) -> bool:
        entry = SslStoreEntry(cert=cert)
        if entry.fingerprint in [e.fingerprint for e in self.cert_db]:
            return False
        if path:
            entry.paths.add(path)
        self.cert_db.append(entry)
        self.sort_db()
        return True

    def import_key(
        self,
        key: CertificateIssuerPrivateKeyTypes,
        path: Path | None = None,
    ) -> bool:
        public_key = key.public_key()
        matched, added = False, False
        for entry in self.cert_db:
            if public_key != entry.cert.public_key():
                continue
            matched = True
            if entry.key is None:
                if path:
                    entry.paths.add(path)
                entry.key = key
                added = True

        if not matched:
            path_str = f" '{path.name}'" if path else ""
            self.warning(f"Private key{path_str} doesn't match any certificates")
        self.sort_db()
        return added

    def get_entry(self, query: str) -> SslStoreEntry | None:
        if not query:
            return None
        # check if query is an index
        if query.isnumeric():
            index = int(query)
            if 1 <= index <= len(self.cert_db):
                return self.cert_db[index - 1]
        # convert AA:12:BB:34 to aa12bb34
        query_hex = query.lower().replace(":", "")
        for entry in self.cert_db:
            if entry.subject_cn == query:
                return entry
            if entry.fingerprint.hex() == query_hex:
                return entry
        return None

    def get_issuer(self, entry: SslStoreEntry) -> SslStoreEntry | None:
        signature = entry.cert.signature
        data = entry.cert.tbs_certificate_bytes
        algorithm: Any = entry.cert.signature_hash_algorithm
        params: Any = entry.cert.signature_algorithm_parameters

        # there's 'verify_directly_issued_by()', but it doesn't work for
        # self-signed certificates for some reason
        for issuer in self.cert_db:
            if entry.cert.issuer != issuer.cert.subject:
                continue
            try:
                match key := issuer.cert.public_key():
                    case DSAPublicKey():
                        key.verify(signature, data, algorithm)
                    case RSAPublicKey():
                        key.verify(signature, data, params, algorithm)
                    case EllipticCurvePublicKey():
                        key.verify(signature, data, params)
                    case _:
                        key.verify(signature, data)
                return issuer
            except:
                pass
        return None

    def export_chain(
        self,
        entry: SslStoreEntry,
        file: IO[bytes] | None,
    ) -> list[SslStoreEntry]:
        # rebuild the chain
        chain = [entry]
        while True:
            issuer = self.get_issuer(chain[-1])
            if issuer in (chain[-1], None):
                break
            chain.append(issuer)
        if not file:
            return chain

        # save as PEM
        for i, entry in enumerate(chain):
            file.write(entry.cert.public_bytes(Encoding.PEM))
            # private key after 1st certificate, and only for this one
            if i == 0 and entry.key:
                private_bytes = entry.key.private_bytes(
                    encoding=Encoding.PEM,
                    format=PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=NoEncryption(),
                )
                file.write(private_bytes)
        return chain

    def export_chain_tmp(self, entry: SslStoreEntry) -> Path:
        # if successful, export as temporary PEM file
        pem_io = BytesIO()
        self.export_chain(entry, file=pem_io)
        # hash full chain PEM bytes
        digest = Hash(MD5())
        digest.update(pem_io.getvalue())
        digest_hex = digest.finalize().hex()
        # build a filename based on that hash, write if it doesn't exist yet
        tmp_path = self.tmp_dir / f"md5-{digest_hex}.pem"
        if not tmp_path.is_file():
            tmp_path.write_bytes(pem_io.getvalue())
        return tmp_path

    def get_for_subject(
        self,
        *names: str,
        ca: bool = False,
        can_generate: bool = False,
    ) -> SslStoreEntry | None:
        if ca and can_generate:
            raise ValueError("Only one of 'ca' and 'can_generate' may be True")
        for entry in self.cert_db:
            if entry.is_ca != ca or not entry.key:
                continue
            if any(matches_wildcard(p, n) for p in entry.usage for n in names):
                return entry
        if not ca and can_generate:
            return self.generate_for_subject(*names)
        return None

    def generate_for_subject(
        self,
        *names: str,
        no_import: bool = False,
    ) -> SslStoreEntry | None:
        if not names:
            return None

        # find a CA that can generate for this subject
        # use first name as primary subject CN
        entry = self.get_for_subject(names[0], ca=True)
        if not entry:
            return None
        ca_cert, ca_key = entry.cert, entry.key

        from .certgen import build_certificate, generate_key_pair

        leaf_key = generate_key_pair("")
        leaf_cert = build_certificate(
            issuer_cert=ca_cert,
            subject_key=leaf_key.public_key(),
            names=names,
        ).sign(private_key=ca_key, algorithm=SHA256())

        if not no_import:
            self.import_certificate(leaf_cert)
            self.import_key(leaf_key)

        return SslStoreEntry(leaf_cert, leaf_key)
