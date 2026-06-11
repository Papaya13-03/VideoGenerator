"""Tests for per-user music upload/list/delete."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.asgi import app
from app.db.base import Base
from app.db.session import get_db


@pytest.fixture()
def client(tmp_path):
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
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _token(client, email="m@e.com"):
    return client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    ).json()["access_token"]


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_music_requires_auth(client):
    assert client.get("/api/v1/assets/music").status_code == 401


def test_upload_list_delete_music(client):
    t = _token(client)
    files = {"file": ("mysong.mp3", b"ID3fake-mp3-bytes", "audio/mpeg")}
    r = client.post("/api/v1/assets/music", headers=_auth(t), files=files)
    assert r.status_code == 200, r.text
    asset = r.json()["data"]
    assert asset["name"] == "mysong.mp3"
    assert asset["kind"] == "music"

    lst = client.get("/api/v1/assets/music", headers=_auth(t)).json()["data"]["music"]
    assert len(lst) == 1 and lst[0]["id"] == asset["id"]

    assert client.delete(f"/api/v1/assets/{asset['id']}", headers=_auth(t)).status_code == 200
    assert client.get("/api/v1/assets/music", headers=_auth(t)).json()["data"]["music"] == []


def test_analyze_beats(client, monkeypatch):
    t = _token(client, "beat@e.com")
    files = {"file": ("song.mp3", b"fake-mp3-bytes", "audio/mpeg")}
    aid = client.post("/api/v1/assets/music", headers=_auth(t), files=files).json()["data"]["id"]

    # Stub analysis so the test doesn't need a real audio decoder.
    from app.services import audio_analysis

    monkeypatch.setattr(
        audio_analysis,
        "analyze_music",
        lambda path, beats_per_segment=4: {
            "duration": 8.0,
            "tempo": 120.0,
            "beats": [0.5, 1.0, 1.5],
            "cut_points": [2.0, 4.0, 6.0],
            "used_beats": True,
        },
    )
    r = client.get(f"/api/v1/assets/music/{aid}/beats?beats_per_segment=4", headers=_auth(t))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["duration"] == 8.0
    assert data["cut_points"] == [2.0, 4.0, 6.0]
    assert data["used_beats"] is True


def test_save_and_load_beats(client, monkeypatch):
    t = _token(client, "save@e.com")
    files = {"file": ("s.mp3", b"x", "audio/mpeg")}
    aid = client.post("/api/v1/assets/music", headers=_auth(t), files=files).json()["data"]["id"]

    # Save edited beats + trim.
    r = client.put(
        f"/api/v1/assets/music/{aid}/beats",
        headers=_auth(t),
        json={"cut_points": [2.0, 4.0], "music_start": 1.0, "music_end": 10.0, "beats_per_segment": 8},
    )
    assert r.status_code == 200, r.text

    # GET returns the saved config alongside analysis.
    from app.services import audio_analysis

    monkeypatch.setattr(
        audio_analysis,
        "analyze_music",
        lambda path, beats_per_segment=4: {
            "duration": 12.0, "tempo": 100.0, "beats": [], "cut_points": [3.0], "used_beats": True
        },
    )
    g = client.get(f"/api/v1/assets/music/{aid}/beats", headers=_auth(t)).json()["data"]
    assert g["saved"]["cut_points"] == [2.0, 4.0]
    assert g["saved"]["music_start"] == 1.0
    assert g["saved"]["music_end"] == 10.0
    assert g["saved"]["beats_per_segment"] == 8


def test_analyze_beats_other_user_404(client):
    ta = _token(client, "o1@e.com")
    tb = _token(client, "o2@e.com")
    files = {"file": ("s.mp3", b"x", "audio/mpeg")}
    aid = client.post("/api/v1/assets/music", headers=_auth(ta), files=files).json()["data"]["id"]
    assert client.get(f"/api/v1/assets/music/{aid}/beats", headers=_auth(tb)).status_code == 404


def test_reject_non_mp3(client):
    t = _token(client)
    files = {"file": ("evil.wav", b"x", "audio/wav")}
    assert client.post("/api/v1/assets/music", headers=_auth(t), files=files).status_code == 400


def test_music_isolated_per_user(client):
    ta = _token(client, "a2@e.com")
    tb = _token(client, "b2@e.com")
    files = {"file": ("a.mp3", b"x", "audio/mpeg")}
    aid = client.post("/api/v1/assets/music", headers=_auth(ta), files=files).json()["data"]["id"]
    # B cannot see or delete A's track.
    assert client.get("/api/v1/assets/music", headers=_auth(tb)).json()["data"]["music"] == []
    assert client.delete(f"/api/v1/assets/{aid}", headers=_auth(tb)).status_code == 404
