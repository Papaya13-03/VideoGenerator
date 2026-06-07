"""Arq job: render a video inside the worker process (separated from the API)."""

import asyncio
import os

from loguru import logger

from app.models.schema import VideoParams
from app.services import state as sm
from app.services import task as tm


def _upload_outputs(task_id: str, result: dict) -> None:
    """Upload outputs (final + combined) to object storage and save URLs to state."""
    from app.storage import get_storage

    storage = get_storage()
    storage_urls = {"videos": [], "combined_videos": []}
    for field in ("videos", "combined_videos"):
        for path in result.get(field) or []:
            if path and os.path.exists(path):
                key = f"tasks/{task_id}/{os.path.basename(path)}"
                try:
                    storage.upload_file(path, key)
                    storage_urls[field].append(storage.url_for(key))
                except Exception as e:
                    logger.error(f"failed to upload {path} -> {key}: {e}")
    sm.state.update_task(task_id, storage_urls=storage_urls)
    logger.success(
        f"uploaded {len(storage_urls['videos'])} final + "
        f"{len(storage_urls['combined_videos'])} combined for task {task_id}"
    )


async def render_job(ctx, task_id: str, params_dict: dict, stop_at: str = "video"):
    """Run the (synchronous) render pipeline in an executor so the worker event loop stays free."""
    logger.info(f"worker picked up render job: {task_id} (stop_at={stop_at})")
    params = VideoParams(**params_dict)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: tm.start(task_id, params, stop_at))
    if result and stop_at == "video":
        await loop.run_in_executor(None, lambda: _upload_outputs(task_id, result))
    return {"task_id": task_id, "ok": bool(result)}
