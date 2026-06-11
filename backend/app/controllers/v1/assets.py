"""Per-user uploaded assets — currently music tracks for beat-sync."""

import os
import tempfile

from fastapi import Body, Depends, File, Path, Query, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.controllers.v1.base import new_router
from app.db.models import Asset, User
from app.db.session import get_db
from app.models.exception import HttpException
from app.storage import get_storage
from app.utils import utils

router = new_router()

_ALLOWED_MUSIC_EXT = (".mp3",)


def _asset_dict(a: Asset) -> dict:
    return {"id": a.id, "name": a.name, "url": a.url, "kind": a.kind}


@router.get("/assets/music", summary="List the current user's uploaded music")
def list_music(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Asset)
        .filter(Asset.user_id == current_user.id, Asset.kind == "music")
        .order_by(Asset.created_at.desc())
        .all()
    )
    return utils.get_response(200, {"music": [_asset_dict(a) for a in rows]})


@router.post("/assets/music", summary="Upload a music track")
async def upload_music(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = (file.filename or "track.mp3").replace("\\", "/").split("/")[-1].strip()
    ext = os.path.splitext(name)[1].lower()
    if ext not in _ALLOWED_MUSIC_EXT:
        raise HttpException(task_id="", status_code=400, message="only .mp3 is supported")

    # Read via the async API: it reliably returns the full content regardless of the
    # underlying spooled-file position (sync .file.read() can return empty after parsing).
    content = await file.read()
    if not content:
        raise HttpException(task_id="", status_code=400, message="uploaded file is empty")

    asset_id = utils.get_uuid()
    key = f"users/{current_user.id}/music/{asset_id}.mp3"

    # Buffer to a temp file, then hand off to the storage backend.
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        size = os.path.getsize(tmp.name)
        storage = get_storage()
        storage.upload_file(tmp.name, key)
        url = storage.url_for(key)
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass

    asset = Asset(
        id=asset_id,
        user_id=current_user.id,
        job_id=None,
        kind="music",
        name=name,
        storage_key=key,
        url=url,
        size_bytes=size,
    )
    db.add(asset)
    db.commit()
    return utils.get_response(200, _asset_dict(asset))


def _owned_music(db, user, asset_id):
    asset = db.get(Asset, asset_id)
    if asset is None or asset.user_id != user.id or asset.kind != "music":
        raise HttpException(task_id=asset_id, status_code=404, message="music not found")
    return asset


@router.get("/assets/music/{asset_id}/beats", summary="Analyze a track's beats / cut points")
def analyze_music_beats(
    asset_id: str = Path(...),
    beats_per_segment: int = Query(4, ge=1, le=16),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import json

    asset = _owned_music(db, current_user, asset_id)

    from app.services import audio_analysis

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        get_storage().download_file(asset.storage_key, tmp.name)
        result = audio_analysis.analyze_music(tmp.name, beats_per_segment=beats_per_segment)
    except Exception as e:
        raise HttpException(task_id=asset_id, status_code=500, message=f"analyze failed: {e}")
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass

    # Include the user's previously saved beat config (cut points + trim), if any.
    result["saved"] = None
    if asset.beat_config:
        try:
            result["saved"] = json.loads(asset.beat_config)
        except Exception:
            pass
    return utils.get_response(200, result)


@router.put("/assets/music/{asset_id}/beats", summary="Save the edited beats / trim for a track")
def save_music_beats(
    asset_id: str = Path(...),
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import json

    asset = _owned_music(db, current_user, asset_id)
    config = {
        "cut_points": [float(c) for c in (body.get("cut_points") or [])],
        "music_start": float(body.get("music_start") or 0),
        "music_end": float(body.get("music_end") or 0),
        "beats_per_segment": int(body.get("beats_per_segment") or 4),
    }
    asset.beat_config = json.dumps(config)
    db.commit()
    return utils.get_response(200, {"id": asset_id, "saved": config})


@router.delete("/assets/{asset_id}", summary="Delete an uploaded asset")
def delete_asset(
    asset_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.get(Asset, asset_id)
    if asset is None or asset.user_id != current_user.id:
        raise HttpException(task_id=asset_id, status_code=404, message="asset not found")
    try:
        get_storage().delete(asset.storage_key)
    except Exception:
        pass
    db.delete(asset)
    db.commit()
    return utils.get_response(200, {"id": asset_id, "deleted": True})
