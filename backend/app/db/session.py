"""Database engine + session management.

DATABASE_URL is read from env (MPT_DATABASE_URL). Defaults to a local SQLite file for
dev/tests; docker-compose points it at Postgres.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.utils import utils


def get_database_url() -> str:
    url = os.getenv("MPT_DATABASE_URL")
    if url:
        return url
    # Dev/test default: SQLite file under storage/.
    db_path = os.path.join(utils.storage_dir("", create=True), "videogenerator.db")
    return f"sqlite:///{db_path}"


_DATABASE_URL = get_database_url()
# check_same_thread=False so the sync engine works across FastAPI threads (SQLite only).
_connect_args = {"check_same_thread": False} if _DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(_DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def init_db() -> None:
    """Create tables (dev convenience; production uses Alembic migrations)."""
    # Import models so they register on Base.metadata before create_all.
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency yielding a session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
