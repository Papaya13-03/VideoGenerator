"""Multi-tenant render jobs API (auth required). Each job is owned by the current user."""

from fastapi import Depends, Path, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.controllers.v1.base import new_router
from app.db.models import Asset, Job, User
from app.db.session import get_db
from app.models.exception import HttpException
from app.models.schema import TaskVideoRequest
from app.services import state as sm
from app.utils import utils

router = new_router()


# Presigned URLs are signed fresh on every read (1 day) so they never serve an expired link.
_URL_TTL = 86400


def _job_to_dict(job: Job, db: Session) -> dict:
    data = {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "error": job.error,
        "params": job.params,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    # Build result URLs from the *persisted* Asset rows (storage_key is permanent), signing
    # them fresh here. This avoids the two bugs of reading URLs from ephemeral Redis state:
    # expired presigned links, and missing entries after a restart (only newest job showed).
    assets = (
        db.query(Asset)
        .filter(Asset.job_id == job.id, Asset.kind.in_(["final_video", "combined_video"]))
        .order_by(Asset.created_at.asc())
        .all()
    )
    if assets:
        from app.storage import get_storage

        storage = get_storage()
        urls = {"videos": [], "combined_videos": []}
        for a in assets:
            field = "videos" if a.kind == "final_video" else "combined_videos"
            try:
                urls[field].append(storage.url_for(a.storage_key, expires=_URL_TTL))
            except Exception:
                pass
        if urls["videos"] or urls["combined_videos"]:
            data["storage_urls"] = urls

    # Live progress for in-flight jobs (Redis), only while not yet complete.
    live = sm.state.get_task(job.id)
    if live and live.get("progress") is not None and job.status != "complete":
        data["progress"] = live.get("progress")
    return data


@router.post("/jobs", summary="Create a render job")
def create_job(
    body: TaskVideoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.queue.client import enqueue_render

    task_id = utils.get_uuid()
    job = Job(
        id=task_id,
        user_id=current_user.id,
        status="queued",
        params=body.model_dump(),
    )
    db.add(job)
    db.commit()

    sm.state.update_task(task_id)
    enqueue_render(task_id, body.model_dump(), "video", current_user.id)
    return utils.get_response(200, {"job_id": task_id})


@router.get("/jobs", summary="List the current user's jobs")
def list_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    q = db.query(Job).filter(Job.user_id == current_user.id).order_by(Job.created_at.desc())
    total = q.count()
    jobs = q.offset((page - 1) * page_size).limit(page_size).all()
    return utils.get_response(
        200,
        {
            "jobs": [_job_to_dict(j, db) for j in jobs],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


def _get_owned_job(db: Session, user: User, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HttpException(task_id=job_id, status_code=404, message="job not found")
    if job.user_id != user.id:
        # Do not leak existence of other users' jobs.
        raise HttpException(task_id=job_id, status_code=404, message="job not found")
    return job


@router.get("/jobs/{job_id}", summary="Get a job")
def get_job(
    job_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_owned_job(db, current_user, job_id)
    return utils.get_response(200, _job_to_dict(job, db))


@router.delete("/jobs/{job_id}", summary="Delete a job")
def delete_job(
    job_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_owned_job(db, current_user, job_id)
    db.delete(job)
    db.commit()
    sm.state.delete_task(job_id)
    return utils.get_response(200, {"id": job_id, "deleted": True})


@router.post("/jobs/{job_id}/recover", summary="Recover a stuck job from its on-disk output")
def recover_job(
    job_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Finalize a job whose render finished on disk but never got uploaded/marked complete
    (e.g. the worker timed out while the orphaned render thread kept running).
    Uploads existing final/combined files to storage and marks the job complete,
    or marks it failed if no output is found."""
    import glob
    import os

    from app.db.models import Asset
    from app.storage import get_storage

    job = _get_owned_job(db, current_user, job_id)
    task_dir = utils.task_dir(job_id)
    finals = sorted(glob.glob(os.path.join(task_dir, "final-*.mp4")))
    combined = sorted(glob.glob(os.path.join(task_dir, "combined-*.mp4")))

    if not finals:
        job.status = "failed"
        job.error = "no output found on disk to recover"
        db.commit()
        return utils.get_response(200, {"id": job_id, "recovered": False, "status": "failed"})

    storage = get_storage()
    storage_urls = {"videos": [], "combined_videos": []}
    for kind, paths, field in (
        ("final_video", finals, "videos"),
        ("combined_video", combined, "combined_videos"),
    ):
        for p in paths:
            key = f"users/{current_user.id}/tasks/{job_id}/{os.path.basename(p)}"
            try:
                storage.upload_file(p, key)
                url = storage.url_for(key)
                storage_urls[field].append(url)
                db.add(
                    Asset(
                        id=utils.get_uuid(),
                        user_id=current_user.id,
                        job_id=job_id,
                        kind=kind,
                        storage_key=key,
                        url=url,
                        size_bytes=os.path.getsize(p),
                    )
                )
            except Exception as e:
                raise HttpException(task_id=job_id, status_code=500, message=f"recover upload failed: {e}")

    job.status = "complete"
    job.progress = 100
    db.commit()
    sm.state.update_task(job_id, storage_urls=storage_urls)
    return utils.get_response(
        200, {"id": job_id, "recovered": True, "status": "complete", "storage_urls": storage_urls}
    )
