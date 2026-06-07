"""Integration tests for self-hosted auth + multi-tenant jobs ownership."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.asgi import app
from app.db.base import Base
from app.db.session import get_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Isolated SQLite DB per test, wired in via the get_db dependency override.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    # Don't actually enqueue to Redis during tests.
    monkeypatch.setattr("app.queue.client.enqueue_render", lambda *a, **k: None)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email, password="password123"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me(client):
    token = _register(client, "alice@example.com")
    me = client.get("/api/v1/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["plan"] == "free"

    # Login returns a working token too.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    assert client.get("/api/v1/me", headers=_auth(r.json()["access_token"])).status_code == 200


def test_duplicate_email_rejected(client):
    _register(client, "bob@example.com")
    r = client.post(
        "/api/v1/auth/register", json={"email": "bob@example.com", "password": "password123"}
    )
    assert r.status_code == 409


def test_wrong_password_rejected(client):
    _register(client, "carol@example.com")
    r = client.post(
        "/api/v1/auth/login", json={"email": "carol@example.com", "password": "wrong"}
    )
    assert r.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers=_auth("garbage")).status_code == 401


def test_create_and_list_jobs(client):
    token = _register(client, "dave@example.com")
    r = client.post(
        "/api/v1/jobs", headers=_auth(token), json={"video_subject": "ocean waves"}
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["data"]["job_id"]

    lst = client.get("/api/v1/jobs", headers=_auth(token))
    assert lst.status_code == 200
    data = lst.json()["data"]
    assert data["total"] == 1
    assert data["jobs"][0]["id"] == job_id
    assert data["jobs"][0]["status"] == "queued"


def test_jobs_are_isolated_per_user(client):
    token_a = _register(client, "eve@example.com")
    token_b = _register(client, "mallory@example.com")
    r = client.post(
        "/api/v1/jobs", headers=_auth(token_a), json={"video_subject": "secret topic"}
    )
    job_id = r.json()["data"]["job_id"]

    # User B cannot see user A's job (404, not 403, to avoid leaking existence).
    assert client.get(f"/api/v1/jobs/{job_id}", headers=_auth(token_b)).status_code == 404
    # User B's job list is empty.
    assert client.get("/api/v1/jobs", headers=_auth(token_b)).json()["data"]["total"] == 0
    # User A can see and delete their own job.
    assert client.get(f"/api/v1/jobs/{job_id}", headers=_auth(token_a)).status_code == 200
    assert client.delete(f"/api/v1/jobs/{job_id}", headers=_auth(token_a)).status_code == 200
    # User B cannot delete user A's job either.
    assert client.delete(f"/api/v1/jobs/{job_id}", headers=_auth(token_b)).status_code == 404


def test_jobs_require_auth(client):
    assert client.post("/api/v1/jobs", json={"video_subject": "x"}).status_code == 401
    assert client.get("/api/v1/jobs").status_code == 401
