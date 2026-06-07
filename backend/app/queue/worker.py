"""Arq WorkerSettings — run with: `arq app.queue.worker.WorkerSettings`.

The worker is a separate process (render microservice) that pulls jobs from Redis
and runs the pipeline.
"""

from loguru import logger

from app.config import config
from app.queue.jobs import render_job
from app.queue.settings import get_redis_settings


async def startup(ctx):
    logger.info("arq worker started")


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
