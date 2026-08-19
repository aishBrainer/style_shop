"""Brand kits, creative templates, ad creatives and videos (§32, §33, §31, §30)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDelete, Timestamped, UUIDPrimaryKey


class BrandKit(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    """§32 — reused by every generated creative."""

    __tablename__ = "brand_kits"
    __table_args__ = (Index("ix_brandkit_org", "organization_id", "is_default"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(160), default="Default", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    logo_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    primary_color: Mapped[str | None] = mapped_column(String(9), nullable=True)
    secondary_color: Mapped[str | None] = mapped_column(String(9), nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(9), nullable=True)
    heading_font: Mapped[str | None] = mapped_column(String(120), nullable=True)
    body_font: Mapped[str | None] = mapped_column(String(120), nullable=True)

    brand_tone: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cta_style: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_positioning: Mapped[str | None] = mapped_column(Text, nullable=True)


class CreativeTemplate(Base, UUIDPrimaryKey, Timestamped):
    """§33. `layout` holds the canvas description the renderer walks; `variables`
    lists the {{placeholders}} the template expects."""

    __tablename__ = "templates"

    # NULL organization_id = platform-provided template.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="general", nullable=False, index=True)

    aspect_ratio: Mapped[str] = mapped_column(String(20), default="1:1", nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)

    layout: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    variables: Mapped[list[str] | None] = mapped_column(ARRAY(String(60)), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AdCreative(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    """§31 — a rendered ad in one social format."""

    __tablename__ = "ad_creatives"
    __table_args__ = (Index("ix_ad_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    brand_kit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brand_kits.id", ondelete="SET NULL"), nullable=True
    )
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    output_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )

    campaign_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    format: Mapped[str] = mapped_column(String(60), default="square", nullable=False, index=True)
    headline: Mapped[str | None] = mapped_column(String(300), nullable=True)
    offer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cta: Mapped[str | None] = mapped_column(String(120), nullable=True)
    variables: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Video(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    """§30 — image-to-video output metadata."""

    __tablename__ = "videos"
    __table_args__ = (Index("ix_video_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    output_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    generation_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True
    )

    motion_preset: Mapped[str | None] = mapped_column(String(60), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
