#  Copyright (c) Kuba Szczodrzyński 2026-11-2.

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.x509 import Certificate, DNSName, ExtensionNotFound
from cryptography.x509.extensions import (
    AuthorityKeyIdentifier,
    BasicConstraints,
    SubjectAlternativeName,
    SubjectKeyIdentifier,
)


@dataclass
class SslStoreEntry:
    cert: Certificate
    key: PrivateKeyTypes | None = None
    paths: set[Path] = field(default_factory=set)
    usage: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.is_ca:
            for name in self.subject_names:
                self.usage.add(name)
                if name.startswith("*."):
                    self.usage.add(name[2:])

    @property
    def subject(self) -> dict[str, str]:
        return {
            k: v
            for k, _, v in [
                name.rfc4514_string().partition("=") for name in self.cert.subject.rdns
            ]
        }

    @property
    def issuer(self) -> dict[str, str]:
        return {
            k: v
            for k, _, v in [
                name.rfc4514_string().partition("=") for name in self.cert.issuer.rdns
            ]
        }

    @property
    def san(self) -> list[str]:
        try:
            san = self.cert.extensions.get_extension_for_class(SubjectAlternativeName)
            return san.value.get_values_for_type(DNSName)
        except ExtensionNotFound:
            return []

    @property
    def valid_from(self) -> datetime:
        return self.cert.not_valid_before_utc

    @property
    def valid_until(self) -> datetime:
        return self.cert.not_valid_after_utc

    @property
    def subject_cn(self) -> str:
        return self.subject.get("CN", "")

    @property
    def issuer_cn(self) -> str:
        return self.issuer.get("CN", "")

    @property
    def subject_names(self) -> list[str]:
        subject, san = self.subject_cn, self.san
        if subject in san:
            san.remove(subject)
        return [subject] + san

    @property
    def is_ca(self) -> bool:
        try:
            bc = self.cert.extensions.get_extension_for_class(BasicConstraints)
            return bc.value.ca
        except ExtensionNotFound:
            return False

    @property
    def subject_key_id(self) -> bytes | None:
        try:
            bc = self.cert.extensions.get_extension_for_class(SubjectKeyIdentifier)
            return bc.value.digest
        except ExtensionNotFound:
            return None

    @property
    def authority_key_id(self) -> bytes | None:
        try:
            bc = self.cert.extensions.get_extension_for_class(AuthorityKeyIdentifier)
            return bc.value.key_identifier
        except ExtensionNotFound:
            return None

    _fingerprint: bytes | None = None

    @property
    def fingerprint(self) -> bytes:
        if not self._fingerprint:
            self._fingerprint = self.cert.fingerprint(hashes.SHA1())
        return self._fingerprint
