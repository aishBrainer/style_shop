"""Storage interface (§42, §59).

Everything the app does with binaries goes through this protocol, so MinIO in
development and any S3-compatible service in production are interchangeable.
Objects are private; the only way a browser reads one is a signed URL.
"""

from __future__ import annotations

from typing import Protocol


class ObjectStorage(Protocol):
    def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_filename: str | None = None,
    ) -> str: ...

    def ensure_bucket(self) -> None: ...
