#  Copyright (c) Kuba Szczodrzyński 2026-11-2.

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import Certificate, load_pem_x509_certificates

from pynetkit.modules.base import ModuleBase

from .types import SslStoreEntry


class SslModule(ModuleBase):
    # runtime configuration
    cert_db: list[SslStoreEntry]

    def __init__(self):
        super().__init__()
        self.cert_db = []

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
                if self.import_key(key, path):
                    key_count += 1
            except ValueError:
                pass

        return cert_count, key_count

    def import_certificate(self, cert: Certificate, path: Path | None = None) -> bool:
        entry = SslStoreEntry(cert=cert)
        if entry.fingerprint in [e.fingerprint for e in self.cert_db]:
            return False
        if path:
            entry.paths.add(path)
        entry.copy_usage()
        self.cert_db.append(entry)
        self.cert_db.sort(
            key=lambda e: (
                not e.is_ca,
                bool(e.key),
                e.subject_cn.lower(),
            ),
        )
        return True

    def import_key(self, key: PrivateKeyTypes, path: Path | None = None) -> bool:
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
        return added

    def get_issuer(self, entry: SslStoreEntry) -> SslStoreEntry | None:
        authority_id = entry.authority_key_id
        issuer_name = entry.issuer

        if entry.subject == issuer_name or entry.subject_key_id == authority_id:
            # most likely self-signed
            return entry

        for issuer in self.cert_db:
            if authority_id and authority_id == issuer.subject_key_id:
                return issuer
            # compare names if no authority key ID
            if not authority_id and issuer_name == issuer.subject:
                return issuer
        return None
