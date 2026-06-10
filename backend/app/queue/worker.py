"""Arq WorkerSettings — run with: `arq app.queue.worker.WorkerSettings`.

The worker is a separate process (render microservice) that pulls jobs from Redis
and runs the pipeline.
"""

from loguru import logger

from app.config import config
from app.queue.jobs import render_job
from app.queue.settings import get_redis_settings


def _runtime_summary() -> str:
    from app.db.session import get_database_url

    url = get_database_url()
    # Mask any password in the DB URL.
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, host = rest.split("@", 1)
            user = creds.split(":", 1)[0]
            url = f"{scheme}://{user}:***@{host}"
    backend = (getattr(config, "storage", {}) or {}).get("backend", "local")
    redis = f"{config.app.get('redis_host')}:{config.app.get('redis_port')}"
    return f"db={url} | storage={backend} | redis={redis}"


async def startup(ctx):
    logger.info(f"arq worker started | {_runtime_summary()}")
    logger.info(
        "👉 The API must use the SAME db + storage + redis as above, "
        "or jobs stay 'queued' and outputs won't reach object storage."
    )


async def shutdown(ctx):
    logger.info("arq worker stopped")


class WorkerSettings:
    functions = [render_job]
    redis_settings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    # Concurrent render jobs per worker (rendering is CPU/ffmpeg heavy -> keep low).
    max_jobs = int(config.app.get("max_concurrent_tasks", 2))
    # Rendering is slow: allow up to 1 hour per job.
    job_timeout = int(config.app.get("job_timeout", 3600))
    # Do not auto-retry a whole render (expensive); let it fail and handle manually.
    max_tries = 1
