#  Copyright (c) Kuba Szczodrzyński 2026-11-2.

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import Certificate, load_pem_x509_certificates

from pynetkit.modules.base import ModuleBase
from pynetkit.util.misc import matches_wildcard

from .types import SslStoreEntry


class SslModule(ModuleBase):
    # runtime configuration
    cert_db: list[SslStoreEntry]

    def __init__(self):
        super().__init__()
        self.cert_db = []

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
        self.cert_db.append(entry)
        self.sort_db()
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

    def find_for_subject(self, name: str) -> SslStoreEntry | None:
        for entry in self.cert_db:
            if entry.is_ca or not entry.key:
                continue
            if any(matches_wildcard(p, name) for p in entry.subject_names):
                return entry
        return None

    def generate_for_subject(
        self,
        *names: str,
        no_import: bool = False,
    ) -> SslStoreEntry | None:
        # use first name as primary subject CN
        if not names:
            return None
        name = names[0]

        # find a CA that can generate for this subject
        for entry in self.cert_db:
            if not entry.is_ca or not entry.key:
                continue
            if any(matches_wildcard(p, name) for p in entry.usage):
                break
        else:
            return None
        ca_cert, ca_key = entry.cert, entry.key

        leaf_cert, leaf_key = ca_cert, ca_key

        if not no_import:
            self.import_certificate(leaf_cert)
            self.import_key(leaf_key)

        return SslStoreEntry(leaf_cert, leaf_key)
