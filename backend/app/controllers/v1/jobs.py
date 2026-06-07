"""Multi-tenant render jobs API (auth required). Each job is owned by the current user."""

from fastapi import Depends, Path, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.controllers.v1.base import new_router
from app.db.models import Job, User
from app.db.session import get_db
from app.models.exception import HttpException
from app.models.schema import TaskVideoRequest
from app.services import state as sm
from app.utils import utils

router = new_router()


def _job_to_dict(job: Job) -> dict:
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
    # Merge live progress/results from the render state (Redis) keyed by task_id.
    live = sm.state.get_task(job.id)
    if live:
        if live.get("progress") is not None and job.status != "complete":
            data["progress"] = live.get("progress")
        if live.get("storage_urls"):
            data["storage_urls"] = live.get("storage_urls")
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
            "jobs": [_job_to_dict(j) for j in jobs],
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
    return utils.get_response(200, _job_to_dict(job))


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
