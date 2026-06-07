"""Arq job: render a video inside the worker process (separated from the API)."""

import asyncio
import datetime
import os

from loguru import logger

from app.models.schema import VideoParams
from app.services import state as sm
from app.services import task as tm
from app.utils import utils


def _storage_prefix(task_id: str, user_id: str) -> str:
    if user_id:
        return f"users/{user_id}/tasks/{task_id}"
    return f"tasks/{task_id}"


def _kind_for(field: str) -> str:
    return "final_video" if field == "videos" else "combined_video"


def _upload_outputs(task_id: str, user_id: str, result: dict) -> dict:
    """Upload outputs to object storage, return {videos, combined_videos} of URLs."""
    from app.storage import get_storage

    storage = get_storage()
    prefix = _storage_prefix(task_id, user_id)
    storage_urls = {"videos": [], "combined_videos": []}
    uploaded = []  # (kind, key, url, size)
    for field in ("videos", "combined_videos"):
        for path in result.get(field) or []:
            if path and os.path.exists(path):
                key = f"{prefix}/{os.path.basename(path)}"
                try:
                    storage.upload_file(path, key)
                    url = storage.url_for(key)
                    storage_urls[field].append(url)
                    uploaded.append((_kind_for(field), key, url, os.path.getsize(path)))
                except Exception as e:
                    logger.error(f"failed to upload {path} -> {key}: {e}")
    sm.state.update_task(task_id, storage_urls=storage_urls)
    _record_assets(task_id, user_id, uploaded)
    return storage_urls


def _record_assets(task_id: str, user_id: str, uploaded: list) -> None:
    """Persist uploaded outputs as Asset rows (best-effort; skip if no user/DB)."""
    if not user_id:
        return
    try:
        from app.db.models import Asset
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            for kind, key, url, size in uploaded:
                db.add(
                    Asset(
                        id=utils.get_uuid(),
                        user_id=user_id,
                        job_id=task_id,
                        kind=kind,
                        storage_key=key,
                        url=url,
                        size_bytes=size,
                    )
                )
            db.commit()
    except Exception as e:
        logger.error(f"failed to record assets for {task_id}: {e}")


def _update_job(task_id: str, **fields) -> None:
    """Best-effort update of the Job row in Postgres (no-op if job/DB absent)."""
    try:
        from app.db.models import Job
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            job = db.get(Job, task_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            db.commit()
    except Exception as e:
        logger.error(f"failed to update job {task_id}: {e}")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


async def render_job(ctx, task_id: str, params_dict: dict, stop_at: str = "video", user_id: str = ""):
    """Run the (synchronous) render pipeline in an executor so the worker event loop stays free."""
    logger.info(f"worker picked up render job: {task_id} (stop_at={stop_at}, user={user_id or '-'})")
    _update_job(task_id, status="processing", started_at=_now())
    params = VideoParams(**params_dict)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: tm.start(task_id, params, stop_at))
    except Exception as e:
        logger.error(f"render job {task_id} crashed: {e}")
        _update_job(task_id, status="failed", error=str(e), finished_at=_now())
        return {"task_id": task_id, "ok": False}

    if result and stop_at == "video":
        await loop.run_in_executor(None, lambda: _upload_outputs(task_id, user_id, result))
        _update_job(task_id, status="complete", progress=100, finished_at=_now())
    elif result:
        _update_job(task_id, status="complete", progress=100, finished_at=_now())
    else:
        _update_job(task_id, status="failed", error="render failed", finished_at=_now())
    return {"task_id": task_id, "ok": bool(result)}
