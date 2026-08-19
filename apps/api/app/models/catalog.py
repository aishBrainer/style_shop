"""Projects, products, model profiles and assets (§34, §35)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
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
from app.models.enums import (
    AssetStatus,
    AssetType,
    ClothingStyle,
    GarmentCategory,
    ModelAgeGroup,
    ModelBodyType,
    ModelGender,
    ModelPose,
)


class Project(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    """e.g. "Summer Collection 2026" (§34)."""

    __tablename__ = "projects"
    __table_args__ = (Index("ix_project_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # use_alter: projects ↔ assets reference each other, so this constraint is
    # added by a separate ALTER after both tables exist. Without it, create_all
    # cannot order the DDL and raises CircularDependencyError.
    cover_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL", use_alter=True, name="fk_project_cover_asset"),
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Asset(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    """Any binary the platform stores. §99: metadata here, bytes in object storage."""

    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_asset_org_type_created", "organization_id", "type", "created_at"),
        Index("ix_asset_project", "project_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[AssetType] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[AssetStatus] = mapped_column(
        String(32), default=AssetStatus.READY, nullable=False, index=True
    )

    filename: Mapped[str] = mapped_column(String(400), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Object storage keys. §98: three renditions so the gallery never loads
    # a 10 MB original.
    storage_key: Mapped[str] = mapped_column(String(700), nullable=False, unique=True)
    preview_key: Mapped[str | None] = mapped_column(String(700), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(700), nullable=True)

    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Provenance for generated assets. use_alter for the same reason as
    # projects.cover_asset_id — assets ↔ generation_jobs is a reference cycle.
    generation_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "generation_jobs.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_asset_generation_job",
        ),
        nullable=True,
        index=True,
    )
    ai_model_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    generation_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    is_favourite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_watermark: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Product(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    """An uploaded garment/product plus what analysis found in it (§10)."""

    __tablename__ = "products"
    __table_args__ = (Index("ix_product_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    image_asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    # Cached cut-out produced by the analysis pass, reused by every job.
    mask_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped[GarmentCategory | None] = mapped_column(
        String(40), nullable=True, index=True
    )
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # [x, y, w, h] in pixels of the original image.
    bounding_box: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class ModelProfile(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    """A person image used as the try-on target (§11, §12).

    `organization_id` NULL means a platform-provided library model visible to
    everyone; non-NULL means a customer's own upload.
    """

    __tablename__ = "model_profiles"
    __table_args__ = (
        Index("ix_model_org_active", "organization_id", "is_active"),
        Index("ix_model_filters", "gender", "age_group", "body_type"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    image_asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )

    # §11 filters. Deliberately no ethnicity column — the spec (§11) asks for
    # curated collections instead of hard-coded demographic profiling.
    gender: Mapped[ModelGender | None] = mapped_column(String(24), nullable=True)
    age_group: Mapped[ModelAgeGroup | None] = mapped_column(String(24), nullable=True)
    body_type: Mapped[ModelBodyType | None] = mapped_column(String(24), nullable=True)
    pose: Mapped[ModelPose | None] = mapped_column(String(24), nullable=True)
    style: Mapped[ClothingStyle | None] = mapped_column(String(24), nullable=True)
    collection: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(40)), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Populated by the §12 validation pass for custom uploads.
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
