#!/usr/bin/env python3
"""Generate RS256 key pair for local InsightIQ development."""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    print("export INSIGHTIQ_JWT__PRIVATE_KEY_PEM=$'" + private_pem + "'")
    print("export INSIGHTIQ_JWT__PUBLIC_KEY_PEM=$'" + public_pem + "'")


if __name__ == "__main__":
    main()
