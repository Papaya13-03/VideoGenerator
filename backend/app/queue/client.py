"""Sync helper for the API process to enqueue render jobs onto Arq/Redis."""

import asyncio

from arq import create_pool
from loguru import logger

from app.queue.settings import get_redis_settings


async def _enqueue(task_id: str, params_dict: dict, stop_at: str, user_id: str) -> None:
    pool = await create_pool(get_redis_settings())
    try:
        # _job_id = task_id makes enqueue idempotent (no duplicate job per task).
        await pool.enqueue_job(
            "render_job", task_id, params_dict, stop_at, user_id, _job_id=task_id
        )
    finally:
        await pool.close()


def enqueue_render(
    task_id: str, params_dict: dict, stop_at: str = "video", user_id: str = ""
) -> None:
    """Blocking enqueue, safe to call from the synchronous FastAPI handler."""
    asyncio.run(_enqueue(task_id, params_dict, stop_at, user_id))
    logger.info(f"enqueued render job to arq: {task_id} (stop_at={stop_at})")
