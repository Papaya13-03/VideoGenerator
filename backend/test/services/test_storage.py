"""Unit tests for the storage abstraction (local backend; s3 needs MinIO, tested in docker)."""

import os

import pytest

from app.storage.local import LocalStorageBackend


@pytest.fixture()
def backend(tmp_path):
    return LocalStorageBackend(root=str(tmp_path / "objects"))


def test_upload_download_roundtrip(backend, tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"video-bytes")
    key = backend.upload_file(str(src), "users/u1/tasks/t1/final-1.mp4")
    assert key == "users/u1/tasks/t1/final-1.mp4"
    assert backend.exists(key)

    out = tmp_path / "out.bin"
    backend.download_file(key, str(out))
    assert out.read_bytes() == b"video-bytes"


def test_url_for_returns_path_without_public_base(backend, tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    key = backend.upload_file(str(src), "a.txt")
    assert backend.url_for(key).endswith("/objects/a.txt")


def test_url_for_uses_public_base_url(tmp_path):
    b = LocalStorageBackend(
        root=str(tmp_path / "objects"), public_base_url="https://cdn.example.com/"
    )
    src = tmp_path / "a.txt"
    src.write_text("x")
    b.upload_file(str(src), "users/u1/a.txt")
    assert b.url_for("users/u1/a.txt") == "https://cdn.example.com/users/u1/a.txt"


def test_delete(backend, tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    key = backend.upload_file(str(src), "a.txt")
    backend.delete(key)
    assert not backend.exists(key)


def test_path_traversal_blocked(backend, tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    with pytest.raises(ValueError):
        backend.upload_file(str(src), "../../escape.txt")
