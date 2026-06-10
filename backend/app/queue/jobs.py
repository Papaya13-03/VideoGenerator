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
                # The API created this job; if the worker can't see it, the two are
                # using DIFFERENT databases (check MPT_DATABASE_URL matches the API's).
                logger.warning(
                    f"job {task_id} not found in worker DB — API and worker may use "
                    f"different databases (MPT_DATABASE_URL mismatch); status won't update"
                )
                return
            for k, v in fields.items():
                setattr(job, k, v)
            db.commit()
    except Exception as e:
        logger.error(f"failed to update job {task_id}: {e}")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _trim_audio(src_path: str, dst_path: str, start: float, end: float) -> None:
    """Write [start, end] of src_path to dst_path as mp3."""
    from moviepy import AudioFileClip

    clip = AudioFileClip(src_path)
    try:
        end = min(end, clip.duration) if end else clip.duration
        clip.subclipped(max(0.0, start), end).write_audiofile(dst_path, logger=None)
    finally:
        clip.close()


def _resolve_music_asset(params: "VideoParams", user_id: str) -> None:
    """If the job references a user-uploaded music asset, fetch it into resource/songs
    and point params.music_file at it (so the sandboxed get_bgm_file accepts it).

    Also applies the optional trim window [music_start, music_end] and shifts any
    user cut points into the trimmed timeline.
    """
    asset_id = getattr(params, "music_asset_id", None)
    if not asset_id:
        return
    try:
        from app.db.models import Asset
        from app.db.session import SessionLocal
        from app.storage import get_storage

        with SessionLocal() as db:
            asset = db.get(Asset, asset_id)
            if not asset or asset.user_id != user_id or asset.kind != "music":
                logger.warning(f"music asset {asset_id} not found/owned; ignoring")
                return
            song_dir = utils.song_dir()
            os.makedirs(song_dir, exist_ok=True)
            full_path = os.path.join(song_dir, f"user-{asset_id}.mp3")
            if not os.path.exists(full_path):
                get_storage().download_file(asset.storage_key, full_path)

            start = float(getattr(params, "music_start", 0) or 0)
            end = getattr(params, "music_end", None)
            end = float(end) if end else None
            # Trim if a non-trivial window is requested.
            if start > 0.05 or (end is not None and end > 0):
                tag = f"{round(start, 2)}-{round(end, 2) if end else 'end'}"
                trimmed = os.path.join(song_dir, f"user-{asset_id}-{tag}.mp3")
                if not os.path.exists(trimmed):
                    _trim_audio(full_path, trimmed, start, end or 0)
                params.music_file = os.path.basename(trimmed)
                # Shift cut points into the trimmed timeline; drop those outside it.
                if params.cut_points:
                    hi = end if end else float("inf")
                    params.cut_points = [
                        round(cp - start, 3)
                        for cp in params.cut_points
                        if start < cp < hi
                    ]
                logger.info(f"music asset {asset_id} trimmed to [{start}, {end}] -> {params.music_file}")
            else:
                params.music_file = os.path.basename(full_path)
                logger.info(f"resolved user music asset {asset_id} -> {params.music_file}")
    except Exception as e:
        logger.error(f"failed to resolve music asset {asset_id}: {e}")


def _run_pipeline(task_id: str, params: "VideoParams", stop_at: str, user_id: str):
    """Run the pipeline with the user's API keys layered over the global config."""
    from app.services import credentials

    _resolve_music_asset(params, user_id)
    overrides = credentials.load_user_overrides(user_id)
    token = credentials.set_overrides(overrides)
    try:
        return tm.start(task_id, params, stop_at)
    finally:
        credentials.reset_overrides(token)


async def render_job(ctx, task_id: str, params_dict: dict, stop_at: str = "video", user_id: str = ""):
    """Run the (synchronous) render pipeline in an executor so the worker event loop stays free."""
    logger.info(f"worker picked up render job: {task_id} (stop_at={stop_at}, user={user_id or '-'})")
    _update_job(task_id, status="processing", started_at=_now())
    params = VideoParams(**params_dict)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: _run_pipeline(task_id, params, stop_at, user_id)
        )
    except asyncio.CancelledError:
        # arq cancels the task when job_timeout is exceeded. The executor thread cannot
        # be killed and may still finish later, but mark the job failed so it isn't stuck
        # in "processing". Raise the worker timeout via MPT_JOB_TIMEOUT for slow renders.
        logger.error(f"render job {task_id} timed out / was cancelled")
        _update_job(task_id, status="failed", error="render timed out", finished_at=_now())
        raise
    except Exception as e:
        logger.error(f"render job {task_id} crashed: {e}")
        _update_job(task_id, status="failed", error=str(e), finished_at=_now())
        return {"task_id": task_id, "ok": False}

    if result and stop_at == "video":
        await loop.run_in_executor(None, lambda: _upload_outputs(task_id, user_id, result))
        import json as _json

        social = result.get("cross_post_results")
        _update_job(
            task_id,
            status="complete",
            progress=100,
            finished_at=_now(),
            social_results=_json.dumps(social) if social else "",
        )
    elif result:
        _update_job(task_id, status="complete", progress=100, finished_at=_now())
    else:
        _update_job(task_id, status="failed", error="render failed", finished_at=_now())
    return {"task_id": task_id, "ok": bool(result)}
