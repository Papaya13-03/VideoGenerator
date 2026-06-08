"""Per-job credential overrides (per-user API keys) layered over the global config.

The worker sets the current user's keys into a contextvar for the duration of a render;
the engine reads keys through `cfg()`, which prefers the override then falls back to
the global config. Contextvar isolation keeps concurrent jobs from leaking keys.
"""

import contextvars
import json
from contextlib import contextmanager

from loguru import logger

from app.config import config

# Shape: {"app": {key: value}, "azure": {key: value}}
_overrides: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "cred_overrides", default={}
)


def set_overrides(overrides: dict):
    return _overrides.set(overrides or {})


def reset_overrides(token) -> None:
    _overrides.reset(token)


def _section(name: str) -> dict:
    return getattr(config, name, {}) or {}


def cfg(key: str, default=None, section: str = "app"):
    """Read a config value, preferring the per-job override for the current user."""
    ov = _overrides.get().get(section, {})
    if key in ov and ov[key] not in (None, "", []):
        return ov[key]
    return _section(section).get(key, default)


def _split_keys(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [k.strip() for k in value.split(",") if k.strip()]
    return []


def overrides_from_credentials(rows) -> dict:
    """Build the override dict from a user's ProviderCredential rows.

    Each row.data_enc is decrypted JSON. Maps provider configs to global config keys.
    """
    from app.auth.crypto import decrypt

    app_ov: dict = {}
    azure_ov: dict = {}
    for row in rows:
        try:
            data = json.loads(decrypt(row.data_enc))
        except Exception as e:
            logger.warning(f"could not decrypt credential {row.provider}: {e}")
            continue

        if row.provider == "pexels":
            keys = _split_keys(data.get("api_keys") or data.get("api_key"))
            if keys:
                app_ov["pexels_api_keys"] = keys
        elif row.provider == "pixabay":
            keys = _split_keys(data.get("api_keys") or data.get("api_key"))
            if keys:
                app_ov["pixabay_api_keys"] = keys
        elif row.provider == "llm":
            provider = data.get("provider")
            if provider:
                app_ov["llm_provider"] = provider
                if data.get("api_key"):
                    app_ov[f"{provider}_api_key"] = data["api_key"]
                if data.get("base_url"):
                    app_ov[f"{provider}_base_url"] = data["base_url"]
                if data.get("model_name"):
                    app_ov[f"{provider}_model_name"] = data["model_name"]
        elif row.provider == "tts":
            # Only Azure speech needs keys; Edge TTS (default) needs none.
            if data.get("api_key"):
                azure_ov["speech_key"] = data["api_key"]
            if data.get("region"):
                azure_ov["speech_region"] = data["region"]

    result = {}
    if app_ov:
        result["app"] = app_ov
    if azure_ov:
        result["azure"] = azure_ov
    return result


@contextmanager
def user_credentials(user_id: str, db=None):
    """Context manager that applies a user's API-key overrides for the duration of a call.

    Used by synchronous API endpoints (e.g. /scripts, /terms) that run in the API process.
    Pass the request's `db` session so it reads the same database as the rest of the request.
    """
    token = set_overrides(load_user_overrides(user_id, db=db))
    try:
        yield
    finally:
        reset_overrides(token)


def _query_overrides(db, user_id: str) -> dict:
    from app.db.models import ProviderCredential

    rows = (
        db.query(ProviderCredential)
        .filter(ProviderCredential.user_id == user_id)
        .all()
    )
    return overrides_from_credentials(rows)


def load_user_overrides(user_id: str, db=None) -> dict:
    """Load + build overrides for a user from the DB (best-effort).

    Uses the provided session if given (request scope); otherwise opens its own
    (worker scope, real engine).
    """
    if not user_id:
        return {}
    try:
        if db is not None:
            return _query_overrides(db, user_id)
        from app.db.session import SessionLocal

        with SessionLocal() as own_db:
            return _query_overrides(own_db, user_id)
    except Exception as e:
        logger.warning(f"failed to load user overrides for {user_id}: {e}")
        return {}
