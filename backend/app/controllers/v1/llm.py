from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import get_optional_user
from app.controllers.v1.base import new_router
from app.db.models import User
from app.db.session import get_db
from app.models.schema import (
    VideoScriptRequest,
    VideoScriptResponse,
    VideoSocialMetadataRequest,
    VideoSocialMetadataResponse,
    VideoTermsRequest,
    VideoTermsResponse,
)
from app.services import credentials, llm
from app.utils import utils

# authentication dependency
# router = new_router(dependencies=[Depends(base.verify_token)])
router = new_router()


def _user_id(user: User | None) -> str:
    return user.id if user else ""


@router.post(
    "/scripts",
    response_model=VideoScriptResponse,
    summary="Create a script for the video",
)
def generate_video_script(
    request: Request,
    body: VideoScriptRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    # Use the caller's own LLM key when authenticated; otherwise fall back to global config.
    with credentials.user_credentials(_user_id(current_user), db=db):
        video_script = llm.generate_script(
            video_subject=body.video_subject,
            language=body.video_language,
            paragraph_number=body.paragraph_number,
            video_script_prompt=body.video_script_prompt,
            custom_system_prompt=body.custom_system_prompt,
        )
    response = {"video_script": video_script}
    return utils.get_response(200, response)


@router.post(
    "/terms",
    response_model=VideoTermsResponse,
    summary="Generate video terms based on the video script",
)
def generate_video_terms(
    request: Request,
    body: VideoTermsRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    with credentials.user_credentials(_user_id(current_user), db=db):
        video_terms = llm.generate_terms(
            video_subject=body.video_subject,
            video_script=body.video_script,
            amount=body.amount,
        )
    response = {"video_terms": video_terms}
    return utils.get_response(200, response)


@router.post(
    "/social-metadata",
    response_model=VideoSocialMetadataResponse,
    summary="Generate social publishing metadata",
)
def generate_video_social_metadata(
    request: Request,
    body: VideoSocialMetadataRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    with credentials.user_credentials(_user_id(current_user), db=db):
        metadata = llm.generate_social_metadata(
            video_subject=body.video_subject,
            video_script=body.video_script,
            language=body.language,
            platform=body.platform,
        )
    return utils.get_response(200, metadata)
