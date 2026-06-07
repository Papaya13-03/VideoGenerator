"""Auth endpoints: register, login, and current-user info (self-hosted JWT)."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.controllers.v1.base import new_router
from app.db.models import User
from app.db.session import get_db
from app.models.exception import HttpException
from app.models.schema import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.utils import utils

router = new_router()


@router.post("/auth/register", response_model=TokenResponse, summary="Register a new user")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HttpException(task_id="", status_code=409, message="email already registered")
    user = User(
        id=utils.get_uuid(),
        email=email,
        password_hash=hash_password(body.password),
        plan="free",
    )
    db.add(user)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/auth/login", response_model=TokenResponse, summary="Login and get a JWT")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HttpException(task_id="", status_code=401, message="invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse, summary="Current user info")
def me(current_user: User = Depends(get_current_user)):
    return UserResponse(id=current_user.id, email=current_user.email, plan=current_user.plan)
