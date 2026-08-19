"""S3-compatible storage backend (MinIO in dev, S3/R2/Spaces in production)."""

from __future__ import annotations

import threading
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_lock = threading.Lock()


class S3Storage:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        # Presigning must use the host the *browser* can reach. Inside Docker
        # the API talks to http://minio:9000, which does not resolve in the
        # user's browser, so signed URLs are generated against the public host.
        self._signing_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
            ),
        )
        self.bucket = settings.s3_bucket

    # ------------------------------------------------------------------ io --
    def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata=metadata or {},
        )

    def get(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:  # already gone is not an error
            if exc.response.get("Error", {}).get("Code") != "NoSuchKey":
                raise

    def delete_many(self, keys: list[str]) -> None:
        # S3 caps a single delete request at 1000 objects.
        for i in range(0, len(keys), 1000):
            chunk = [{"Key": k} for k in keys[i : i + 1000]]
            if chunk:
                self._client.delete_objects(Bucket=self.bucket, Delete={"Objects": chunk})

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    # ------------------------------------------------------------- signing --
    def signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_filename: str | None = None,
    ) -> str:
        params: dict[str, str] = {"Bucket": self.bucket, "Key": key}
        if download_filename:
            safe = download_filename.replace('"', "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
        return self._signing_client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in or settings.signed_url_ttl_seconds,
        )

    # ----------------------------------------------------------- lifecycle --
    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            log.info("storage.creating_bucket", bucket=self.bucket)
            try:
                self._client.create_bucket(Bucket=self.bucket)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    raise


@lru_cache
def get_storage() -> S3Storage:
    with _lock:
        return S3Storage()
