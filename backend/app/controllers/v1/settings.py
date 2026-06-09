"""Per-user API key management (Pexels/Pixabay/LLM/TTS), stored encrypted."""

import json

from fastapi import Body, Depends, Path
from sqlalchemy.orm import Session

from app.auth.crypto import decrypt, encrypt
from app.auth.deps import get_current_user
from app.controllers.v1.base import new_router
from app.db.models import ProviderCredential, User
from app.db.session import get_db
from app.models.exception import HttpException
from app.utils import utils

router = new_router()

SUPPORTED_PROVIDERS = {"pexels", "pixabay", "llm", "tts", "social"}
# Field names treated as secrets -> masked when read back.
_SECRET_FIELDS = ("api_key", "api_keys", "secret", "secret_key")


def _mask_value(name: str, value):
    if not isinstance(value, str) or not value:
        return value
    is_secret = any(s in name.lower() for s in ("key", "secret", "token"))
    if not is_secret:
        return value
    tail = value[-4:] if len(value) > 4 else ""
    return f"••••{tail}"


def _masked(data: dict) -> dict:
    return {k: _mask_value(k, v) for k, v in data.items()}


@router.get("/settings/keys", summary="List configured provider keys (masked)")
def list_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ProviderCredential)
        .filter(ProviderCredential.user_id == current_user.id)
        .all()
    )
    providers = {}
    for row in rows:
        try:
            data = json.loads(decrypt(row.data_enc))
        except Exception:
            data = {}
        providers[row.provider] = {"configured": True, "fields": _masked(data)}
    for p in SUPPORTED_PROVIDERS:
        providers.setdefault(p, {"configured": False, "fields": {}})
    return utils.get_response(200, {"providers": providers})


@router.put("/settings/keys/{provider}", summary="Create/update a provider's keys")
def upsert_keys(
    provider: str = Path(...),
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HttpException(task_id="", status_code=400, message=f"unknown provider: {provider}")
    # Drop empty values and masked placeholders so a blank field doesn't overwrite a secret.
    clean = {
        k: v
        for k, v in body.items()
        if isinstance(v, str) and v.strip() and not v.startswith("••••")
    }
    row = (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.user_id == current_user.id,
            ProviderCredential.provider == provider,
        )
        .first()
    )
    # Merge with existing so partial updates keep untouched secrets.
    existing = {}
    if row:
        try:
            existing = json.loads(decrypt(row.data_enc))
        except Exception:
            existing = {}
    merged = {**existing, **clean}
    enc = encrypt(json.dumps(merged))
    if row:
        row.data_enc = enc
    else:
        db.add(
            ProviderCredential(
                id=utils.get_uuid(),
                user_id=current_user.id,
                provider=provider,
                data_enc=enc,
            )
        )
    db.commit()
    return utils.get_response(200, {"provider": provider, "fields": _masked(merged)})


@router.delete("/settings/keys/{provider}", summary="Delete a provider's keys")
def delete_keys(
    provider: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.user_id == current_user.id,
            ProviderCredential.provider == provider,
        )
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return utils.get_response(200, {"provider": provider, "deleted": True})
