"""S3-compatible storage backend (MinIO / Cloudflare R2 / AWS S3) via boto3."""

from loguru import logger

from app.storage.base import StorageBackend


class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        bucket: str,
        endpoint_url: str = "",
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
        public_base_url: str = "",
    ):
        import boto3
        from botocore.client import Config as BotoConfig

        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region,
            config=BotoConfig(signature_version="s3v4"),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self.bucket)
                logger.info(f"s3 storage: created bucket {self.bucket}")
            except Exception as e:  # bucket may already exist due to a race; ignore.
                logger.warning(f"s3 storage: ensure bucket failed: {e}")

    def upload_file(self, local_path: str, key: str) -> str:
        self._client.upload_file(local_path, self.bucket, key)
        logger.debug(f"s3 storage: uploaded {key}")
        return key

    def download_file(self, key: str, local_path: str) -> None:
        import os

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        self._client.download_file(self.bucket, key, local_path)

    def url_for(self, key: str, expires: int = 3600) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)
