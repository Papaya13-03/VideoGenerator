"""Database engine + session management.

DATABASE_URL is read from env (MPT_DATABASE_URL). Defaults to a local SQLite file for
dev/tests; docker-compose points it at Postgres.
"""

import os

from loguru import logger
from sqlalchemy import create_engine, inspect, text
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


# Columns added after a table may already have been created by an earlier create_all.
# create_all never ALTERs existing tables, so reconcile these idempotently on startup.
# (Production should use Alembic migrations; this keeps dev DBs from drifting.)
_ENSURE_COLUMNS = [
    ("assets", "name", "VARCHAR(255) NOT NULL DEFAULT ''"),
    ("jobs", "social_results", "TEXT NOT NULL DEFAULT ''"),
]


def _ensure_columns() -> None:
    insp = inspect(engine)
    for table, column, ddl in _ENSURE_COLUMNS:
        if not insp.has_table(table):
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        if column not in existing:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
            logger.info(f"db: added missing column {table}.{column}")


def init_db() -> None:
    """Create tables + reconcile new columns (dev convenience; prod uses Alembic)."""
    # Import models so they register on Base.metadata before create_all.
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def get_db():
    """FastAPI dependency yielding a session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
