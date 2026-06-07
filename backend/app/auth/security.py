"""Password hashing (bcrypt) and JWT issue/verify for self-hosted auth."""

import datetime
import os

import bcrypt
import jwt
from loguru import logger

from app.config import config

_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("MPT_JWT_EXPIRE_MINUTES", config.app.get("jwt_expire_minutes", 60 * 24 * 7))
)


def _jwt_secret() -> str:
    secret = os.getenv("MPT_JWT_SECRET") or config.app.get("jwt_secret", "")
    if not secret:
        # Dev fallback; MUST be overridden in production via MPT_JWT_SECRET.
        logger.warning("MPT_JWT_SECRET not set, using an insecure dev secret")
        secret = "dev-insecure-secret-change-me"
    return secret


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; truncate to avoid backend errors.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Return the decoded payload, or raise jwt exceptions on invalid/expired tokens."""
    return jwt.decode(token, _jwt_secret(), algorithms=[_ALGORITHM])
