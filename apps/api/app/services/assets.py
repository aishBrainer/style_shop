"""Asset upload, listing and signed-URL hydration (§35, §42, §58, §59)."""

from __future__ import annotations

import uuid

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError, UploadRejectedError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models import Asset, Organization
from app.models.enums import AssetStatus, AssetType
from app.schemas.catalog import AssetOut
from app.services import imaging
from app.storage.keys import asset_key
from app.storage.s3 import get_storage

log = get_logger(__name__)

#: Read uploads in chunks so a huge file is rejected before it is fully in RAM.
CHUNK_SIZE = 1024 * 1024


async def upload_image(
    session: AsyncSession,
    *,
    file: UploadFile,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    asset_type: AssetType,
    project_id: uuid.UUID | None = None,
) -> Asset:
    """Validate, store and register an uploaded image.

    §58: the browser's filename and Content-Type are treated as hints only —
    what the file *is* comes from parsing its bytes.
    """
    data = await _read_bounded(file)

    # Decides format, dimensions and checksum from the actual bytes.
    info = imaging.sniff(data)
    if info.mime_type not in settings.allowed_image_mimes:
        raise UploadRejectedError(
            f"{info.mime_type} is not supported. Use JPG, PNG or WebP."
        )

    org = await session.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found.")

    quota_bytes = org.storage_quota_mb * 1024 * 1024
    if org.storage_used_bytes + info.size_bytes > quota_bytes:
        raise UploadRejectedError(
            "You have run out of storage. Delete some assets or upgrade your plan.",
            code="STORAGE_QUOTA_EXCEEDED",
        )

    # Identical bytes already uploaded — reuse rather than paying twice.
    existing = await session.scalar(
        select(Asset).where(
            Asset.organization_id == organization_id,
            Asset.checksum_sha256 == info.checksum_sha256,
            Asset.type == asset_type,
            Asset.deleted_at.is_(None),
        )
    )
    if existing is not None:
        log.info("asset.deduplicated", asset_id=str(existing.id))
        return existing

    preview, thumbnail = imaging.make_renditions(data)

    asset_id = uuid.uuid4()
    original_key = asset_key(organization_id, asset_type, asset_id, "original", info.mime_type)
    preview_key = asset_key(organization_id, asset_type, asset_id, "preview", "image/webp")
    thumb_key = asset_key(organization_id, asset_type, asset_id, "thumbnail", "image/webp")

    storage = get_storage()
    storage.put(original_key, data, info.mime_type)
    storage.put(preview_key, preview, "image/webp")
    storage.put(thumb_key, thumbnail, "image/webp")

    asset = Asset(
        id=asset_id,
        organization_id=organization_id,
        project_id=project_id,
        owner_id=owner_id,
        type=asset_type,
        status=AssetStatus.READY,
        filename=_safe_filename(file.filename, info.mime_type),
        mime_type=info.mime_type,
        size_bytes=info.size_bytes,
        width=info.width,
        height=info.height,
        storage_key=original_key,
        preview_key=preview_key,
        thumbnail_key=thumb_key,
        checksum_sha256=info.checksum_sha256,
    )
    session.add(asset)

    org.storage_used_bytes += info.size_bytes + len(preview) + len(thumbnail)
    await session.flush()

    log.info(
        "asset.uploaded",
        asset_id=str(asset.id),
        type=str(asset_type),
        size=info.size_bytes,
        organization_id=str(organization_id),
    )
    return asset


async def upload_bytes(
    session: AsyncSession,
    *,
    data: bytes,
    filename: str,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    asset_type: AssetType,
    project_id: uuid.UUID | None = None,
    mime_type: str = "image/png",
) -> Asset:
    """Register bytes the API produced itself — e.g. a mask drawn in the editor."""
    info = imaging.sniff(data)
    preview, thumbnail = imaging.make_renditions(data)

    asset_id = uuid.uuid4()
    original_key = asset_key(organization_id, asset_type, asset_id, "original", info.mime_type)
    preview_key = asset_key(organization_id, asset_type, asset_id, "preview", "image/webp")
    thumb_key = asset_key(organization_id, asset_type, asset_id, "thumbnail", "image/webp")

    storage = get_storage()
    storage.put(original_key, data, info.mime_type)
    storage.put(preview_key, preview, "image/webp")
    storage.put(thumb_key, thumbnail, "image/webp")

    asset = Asset(
        id=asset_id,
        organization_id=organization_id,
        project_id=project_id,
        owner_id=owner_id,
        type=asset_type,
        status=AssetStatus.READY,
        filename=filename,
        mime_type=info.mime_type,
        size_bytes=info.size_bytes,
        width=info.width,
        height=info.height,
        storage_key=original_key,
        preview_key=preview_key,
        thumbnail_key=thumb_key,
        checksum_sha256=info.checksum_sha256,
    )
    session.add(asset)

    org = await session.get(Organization, organization_id)
    if org is not None:
        org.storage_used_bytes += info.size_bytes + len(preview) + len(thumbnail)

    await session.flush()
    return asset


async def get_owned(
    session: AsyncSession, asset_id: uuid.UUID, organization_id: uuid.UUID
) -> Asset:
    """§61 — every lookup is scoped by organization, server-side."""
    asset = await session.get(Asset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise NotFoundError("Asset not found.")
    if asset.organization_id != organization_id:
        # Deliberately 404, not 403: a 403 confirms the id exists.
        raise NotFoundError("Asset not found.")
    return asset


async def soft_delete(
    session: AsyncSession, asset_id: uuid.UUID, organization_id: uuid.UUID
) -> None:
    asset = await get_owned(session, asset_id, organization_id)
    asset.deleted_at = utcnow()
    await session.flush()


async def count_for_project(session: AsyncSession, project_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count(Asset.id)).where(
                Asset.project_id == project_id, Asset.deleted_at.is_(None)
            )
        )
        or 0
    )


# ------------------------------------------------------------ presentation --

def to_out(asset: Asset, *, with_urls: bool = True) -> AssetOut:
    """Attach short-lived signed URLs (§59). Never store or cache these."""
    out = AssetOut.model_validate(asset)
    if not with_urls:
        return out

    storage = get_storage()
    out.url = storage.signed_url(asset.storage_key)
    if asset.preview_key:
        out.preview_url = storage.signed_url(asset.preview_key)
    if asset.thumbnail_key:
        out.thumbnail_url = storage.signed_url(asset.thumbnail_key)
    return out


def download_url(asset: Asset, *, variant: str = "original") -> str:
    key = {
        "original": asset.storage_key,
        "preview": asset.preview_key or asset.storage_key,
        "thumbnail": asset.thumbnail_key or asset.storage_key,
    }.get(variant, asset.storage_key)
    return get_storage().signed_url(key, download_filename=asset.filename)


# ---------------------------------------------------------------- internals --

async def _read_bounded(file: UploadFile) -> bytes:
    """Read at most MAX_UPLOAD_MB, rejecting anything larger.

    A Content-Length header is trivially forged, so the limit is enforced on
    bytes actually read rather than on what the client claims.
    """
    limit = settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0

    while chunk := await file.read(CHUNK_SIZE):
        total += len(chunk)
        if total > limit:
            raise UploadRejectedError(
                f"File is larger than the {settings.max_upload_mb} MB limit."
            )
        chunks.append(chunk)

    if total == 0:
        raise UploadRejectedError("The uploaded file is empty.")

    return b"".join(chunks)


def _safe_filename(raw: str | None, mime_type: str) -> str:
    """Never trust a browser-supplied filename (§58) — it can contain path
    traversal or control characters. Keep a readable stem, drop everything else.
    """
    from pathlib import PurePosixPath

    from app.storage.keys import extension_for

    ext = extension_for(mime_type)
    if not raw:
        return f"upload.{ext}"

    stem = PurePosixPath(raw.replace("\\", "/")).stem
    cleaned = "".join(c for c in stem if c.isalnum() or c in "-_ ").strip()[:120]
    return f"{cleaned or 'upload'}.{ext}"
