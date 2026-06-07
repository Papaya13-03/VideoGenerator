"""Local-disk storage backend (dev / single box)."""

import os
import shutil

from loguru import logger

from app.storage.base import StorageBackend
from app.utils import utils


class LocalStorageBackend(StorageBackend):
    def __init__(self, root: str = "", public_base_url: str = ""):
        # Default: storage/objects/ inside the project.
        self.root = root or utils.storage_dir("objects", create=True)
        os.makedirs(self.root, exist_ok=True)
        # Public URL (e.g. served via API /api/v1/download/); if empty, return the file path.
        self.public_base_url = public_base_url.rstrip("/")

    def _path(self, key: str) -> str:
        # Normalize and block path traversal outside root.
        full = os.path.normpath(os.path.join(self.root, key))
        if not full.startswith(os.path.abspath(self.root)):
            raise ValueError(f"unsafe storage key: {key}")
        return full

    def upload_file(self, local_path: str, key: str) -> str:
        dst = self._path(key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(local_path) != os.path.abspath(dst):
            shutil.copy(local_path, dst)
        logger.debug(f"local storage: saved {key}")
        return key

    def download_file(self, key: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        shutil.copy(self._path(key), local_path)

    def url_for(self, key: str, expires: int = 3600) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        return self._path(key)

    def exists(self, key: str) -> bool:
        return os.path.exists(self._path(key))

    def delete(self, key: str) -> None:
        p = self._path(key)
        if os.path.exists(p):
            os.remove(p)
