#  Copyright (c) Kuba Szczodrzyński 2026-11-5.

from datetime import datetime
from typing import Sequence

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.types import (
    CertificateIssuerPrivateKeyTypes,
    CertificatePublicKeyTypes,
)
from cryptography.x509 import (
    AuthorityKeyIdentifier,
    BasicConstraints,
    Certificate,
    CertificateBuilder,
    DNSName,
    ExtendedKeyUsage,
    ExtendedKeyUsageOID,
    KeyUsage,
    Name,
    NameAttribute,
    NameOID,
    SubjectAlternativeName,
    SubjectKeyIdentifier,
    random_serial_number,
)

NOT_VALID_BEFORE = datetime(1970, 1, 1)
NOT_VALID_AFTER = datetime(2050, 1, 1)


def generate_key_pair(algorithm: str) -> CertificateIssuerPrivateKeyTypes:
    return rsa.generate_private_key(public_exponent=0x10001, key_size=2048)


def build_certificate(
    issuer_cert: Certificate,
    subject_key: CertificatePublicKeyTypes,
    names: Sequence[str],
    name_attributes: list[NameAttribute] | None = None,
    serial_number: int = random_serial_number(),
    not_valid_before: datetime = NOT_VALID_BEFORE,
    not_valid_after: datetime = NOT_VALID_AFTER,
) -> CertificateBuilder:
    if not names:
        raise ValueError("Missing names")

    subject_name = Name(
        [
            *(name_attributes or []),
            NameAttribute(NameOID.COMMON_NAME, names[0]),
        ]
    )
    subject_alternative_names = [DNSName(name) for name in names]

    return (
        CertificateBuilder()
        .subject_name(subject_name)
        .issuer_name(issuer_cert.subject)
        .public_key(subject_key)
        .serial_number(serial_number)
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_after)
        .add_extension(
            BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            SubjectAlternativeName(subject_alternative_names),
            critical=False,
        )
        .add_extension(
            SubjectKeyIdentifier.from_public_key(subject_key),
            critical=False,
        )
        .add_extension(
            AuthorityKeyIdentifier.from_issuer_public_key(issuer_cert.public_key()),
            critical=False,
        )
    )
