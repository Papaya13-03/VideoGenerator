"""Symmetric encryption for secrets at rest (per-user API keys).

Uses Fernet with a key derived from MPT_SECRET_KEY (falls back to MPT_JWT_SECRET).
Set a strong MPT_SECRET_KEY in production.
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    secret = (
        os.getenv("MPT_SECRET_KEY")
        or os.getenv("MPT_JWT_SECRET")
        or "dev-insecure-secret-change-me"
    )
    # Derive a valid 32-byte urlsafe-base64 Fernet key from an arbitrary secret string.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
