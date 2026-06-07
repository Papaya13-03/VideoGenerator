"""Storage backend interface — decouples output storage from local disk for multi-instance runs.

LocalStorageBackend is for dev / single box; S3StorageBackend (boto3, compatible with
MinIO / R2 / S3) is for multi-worker deployments. Backend is selected via the
[storage] section in config.toml.
"""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def upload_file(self, local_path: str, key: str) -> str:
        """Upload a local file to storage under `key`. Returns the stored key."""

    @abstractmethod
    def download_file(self, key: str, local_path: str) -> None:
        """Download object `key` to `local_path`."""

    @abstractmethod
    def url_for(self, key: str, expires: int = 3600) -> str:
        """Return an access URL (presigned for S3, path/endpoint for local)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...
