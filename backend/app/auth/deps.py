"""FastAPI dependency that resolves the current user from a Bearer JWT."""

import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.auth.security import decode_token
from app.db.models import User
from app.db.session import get_db
from app.models.exception import HttpException


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User:
    if not authorization.lower().startswith("bearer "):
        raise HttpException(task_id="", status_code=401, message="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HttpException(task_id="", status_code=401, message="token expired")
    except jwt.PyJWTError:
        raise HttpException(task_id="", status_code=401, message="invalid token")

    user_id = payload.get("sub")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HttpException(task_id="", status_code=401, message="user not found")
    return user


def get_optional_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of raising when no/invalid token.

    Used by endpoints that work with a global fallback but prefer the caller's own keys.
    """
    if not authorization.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(authorization.split(" ", 1)[1].strip())
    except jwt.PyJWTError:
        return None
    user_id = payload.get("sub")
    return db.get(User, user_id) if user_id else None
