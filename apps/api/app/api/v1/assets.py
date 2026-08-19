"""Asset upload, listing and download (§35, §38, §59)."""

from __future__ import annotations

import base64
import binascii
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.deps import CurrentPrincipal, DbSession, WritePrincipal
from app.core.errors import UploadRejectedError, ValidationError
from app.core.ratelimit import upload_rate_limit
from app.models import Asset
from app.models.enums import AssetType
from app.schemas.catalog import AssetOut, AssetUpdate
from app.schemas.common import Message, Page
from app.services import assets as asset_service

router = APIRouter(prefix="/assets", tags=["assets"])

#: Which asset types a client is allowed to create directly. Generated outputs
#: are written by workers, never uploaded.
UPLOADABLE = {AssetType.PRODUCT, AssetType.MODEL, AssetType.LOGO, AssetType.BRAND_ASSET}


@router.post("", response_model=AssetOut, status_code=201,
             dependencies=[Depends(upload_rate_limit)])
async def upload_asset(
    session: DbSession,
    principal: WritePrincipal,
    file: Annotated[UploadFile, File()],
    type: Annotated[AssetType, Form()] = AssetType.PRODUCT,
    project_id: Annotated[uuid.UUID | None, Form()] = None,
) -> AssetOut:
    if type not in UPLOADABLE:
        raise ValidationError(f"You cannot upload assets of type {type}.")

    asset = await asset_service.upload_image(
        session,
        file=file,
        organization_id=principal.organization_id,
        owner_id=principal.user_id,
        asset_type=type,
        project_id=project_id,
    )
    return asset_service.to_out(asset)


class MaskUpload(BaseModel):
    """The mask editor posts a data URL from its canvas (§13)."""

    image_base64: str = Field(min_length=32)
    project_id: uuid.UUID | None = None


@router.post("/mask", response_model=AssetOut, status_code=201,
             dependencies=[Depends(upload_rate_limit)])
async def upload_mask(
    payload: MaskUpload, session: DbSession, principal: WritePrincipal
) -> AssetOut:
    raw = payload.image_base64
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")

    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UploadRejectedError("The mask image could not be decoded.") from exc

    from app.core.config import settings

    if len(data) > settings.max_upload_bytes:
        raise UploadRejectedError("The mask image is too large.")

    asset = await asset_service.upload_bytes(
        session,
        data=data,
        filename=f"mask-{uuid.uuid4().hex[:8]}.png",
        organization_id=principal.organization_id,
        owner_id=principal.user_id,
        asset_type=AssetType.MASK,
        project_id=payload.project_id,
        mime_type="image/png",
    )
    return asset_service.to_out(asset)


@router.get("", response_model=Page[AssetOut])
async def list_assets(
    session: DbSession,
    principal: CurrentPrincipal,
    type: AssetType | None = None,
    project_id: uuid.UUID | None = None,
    favourites_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> Page[AssetOut]:
    # §61: organization_id is on every query, not applied in the frontend.
    conditions = [
        Asset.organization_id == principal.organization_id,
        Asset.deleted_at.is_(None),
    ]
    if type is not None:
        conditions.append(Asset.type == type)
    if project_id is not None:
        conditions.append(Asset.project_id == project_id)
    if favourites_only:
        conditions.append(Asset.is_favourite.is_(True))

    total = int(await session.scalar(select(func.count(Asset.id)).where(*conditions)) or 0)
    rows = await session.scalars(
        select(Asset)
        .where(*conditions)
        .order_by(Asset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return Page[AssetOut](
        items=[asset_service.to_out(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> AssetOut:
    asset = await asset_service.get_owned(session, asset_id, principal.organization_id)
    return asset_service.to_out(asset)


@router.patch("/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: uuid.UUID, payload: AssetUpdate, session: DbSession, principal: WritePrincipal
) -> AssetOut:
    asset = await asset_service.get_owned(session, asset_id, principal.organization_id)

    if payload.is_favourite is not None:
        asset.is_favourite = payload.is_favourite
    if payload.filename is not None:
        asset.filename = payload.filename
    if payload.project_id is not None:
        asset.project_id = payload.project_id

    await session.flush()
    return asset_service.to_out(asset)


class DownloadOut(BaseModel):
    url: str
    filename: str
    expires_in: int


@router.get("/{asset_id}/download", response_model=DownloadOut)
async def download_asset(
    asset_id: uuid.UUID,
    session: DbSession,
    principal: CurrentPrincipal,
    variant: str = Query(default="original", pattern="^(original|preview|thumbnail)$"),
) -> DownloadOut:
    """§97 — hand back a signed URL. Large images never stream through FastAPI."""
    from app.core.config import settings

    asset = await asset_service.get_owned(session, asset_id, principal.organization_id)
    return DownloadOut(
        url=asset_service.download_url(asset, variant=variant),
        filename=asset.filename,
        expires_in=settings.signed_url_ttl_seconds,
    )


@router.delete("/{asset_id}", response_model=Message)
async def delete_asset(
    asset_id: uuid.UUID, session: DbSession, principal: WritePrincipal
) -> Message:
    await asset_service.soft_delete(session, asset_id, principal.organization_id)
    return Message(message="Asset deleted.")
