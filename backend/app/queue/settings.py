"""Redis settings for Arq (shared between the worker and the enqueue client)."""

from arq.connections import RedisSettings

from app.config import config


def get_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=config.app.get("redis_host", "localhost"),
        port=int(config.app.get("redis_port", 6379)),
        database=int(config.app.get("redis_db", 0)),
        password=config.app.get("redis_password") or None,
    )
