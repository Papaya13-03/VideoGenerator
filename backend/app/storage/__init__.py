"""Storage factory — selects the backend based on the [storage] section in config.toml."""

from functools import lru_cache

from loguru import logger

from app.config import config
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    cfg = getattr(config, "storage", None) or {}
    backend = (cfg.get("backend", "local") or "local").lower()

    if backend == "s3":
        from app.storage.s3 import S3StorageBackend

        logger.info("storage backend: s3")
        return S3StorageBackend(
            bucket=cfg.get("s3_bucket", "videogenerator"),
            endpoint_url=cfg.get("s3_endpoint_url", ""),
            access_key=cfg.get("s3_access_key", ""),
            secret_key=cfg.get("s3_secret_key", ""),
            region=cfg.get("s3_region", "us-east-1"),
            public_base_url=cfg.get("public_base_url", ""),
        )

    logger.info("storage backend: local")
    return LocalStorageBackend(public_base_url=cfg.get("public_base_url", ""))


__all__ = ["StorageBackend", "get_storage"]
