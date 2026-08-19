"""Object key layout.

Keys are prefixed by organization so that a bucket policy, lifecycle rule or
bulk delete can operate on exactly one tenant (§60).

    org/{organization_id}/{asset_type}/{yyyy}/{mm}/{asset_id}/{rendition}.{ext}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

MIME_EXTENSIONS: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/webm": "webm",
}

Rendition = str  # "original" | "preview" | "thumbnail"


def extension_for(mime_type: str) -> str:
    return MIME_EXTENSIONS.get(mime_type, "bin")


def asset_key(
    organization_id: uuid.UUID | str,
    asset_type: str,
    asset_id: uuid.UUID | str,
    rendition: Rendition,
    mime_type: str,
    *,
    at: datetime | None = None,
) -> str:
    at = at or datetime.now(timezone.utc)
    return (
        f"org/{organization_id}/{asset_type}/"
        f"{at:%Y}/{at:%m}/{asset_id}/{rendition}.{extension_for(mime_type)}"
    )


def organization_prefix(organization_id: uuid.UUID | str) -> str:
    return f"org/{organization_id}/"
