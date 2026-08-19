"""Assets, projects, products and model profiles."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

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
from app.schemas.common import ORMModel


# ------------------------------------------------------------------ assets --

class AssetOut(ORMModel):
    id: uuid.UUID
    type: AssetType
    status: AssetStatus
    filename: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    project_id: uuid.UUID | None
    is_favourite: bool
    has_watermark: bool
    ai_model_key: str | None
    generation_job_id: uuid.UUID | None
    generation_params: dict | None
    created_at: datetime

    # §59: populated per-response with short-lived signed URLs. Never a
    # permanent public link.
    url: str | None = None
    preview_url: str | None = None
    thumbnail_url: str | None = None


class AssetUpdate(BaseModel):
    is_favourite: bool | None = None
    project_id: uuid.UUID | None = None
    filename: str | None = Field(default=None, max_length=400)


class DownloadRequest(BaseModel):
    # §38
    variant: str = Field(default="original", pattern="^(original|preview|thumbnail)$")
    format: str | None = Field(default=None, pattern="^(jpg|jpeg|png|webp)$")


# ---------------------------------------------------------------- projects --

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    is_archived: bool | None = None
    cover_asset_id: uuid.UUID | None = None


class ProjectOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_archived: bool
    cover_asset_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    cover_url: str | None = None
    asset_count: int = 0
    generation_count: int = 0


# ---------------------------------------------------------------- products --

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    image_asset_id: uuid.UUID
    project_id: uuid.UUID | None = None
    sku: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    category: GarmentCategory | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    category: GarmentCategory | None = None
    project_id: uuid.UUID | None = None


class ProductOut(ORMModel):
    id: uuid.UUID
    name: str
    sku: str | None
    description: str | None
    category: GarmentCategory | None
    category_confidence: float | None
    bounding_box: list[int] | None
    project_id: uuid.UUID | None
    image_asset_id: uuid.UUID
    mask_asset_id: uuid.UUID | None
    analysis: dict | None
    created_at: datetime

    image: AssetOut | None = None


# ----------------------------------------------------------- model profiles --

class ModelProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    image_asset_id: uuid.UUID
    gender: ModelGender | None = None
    age_group: ModelAgeGroup | None = None
    body_type: ModelBodyType | None = None
    pose: ModelPose | None = None
    style: ClothingStyle | None = None


class ModelProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    gender: ModelGender | None = None
    age_group: ModelAgeGroup | None = None
    body_type: ModelBodyType | None = None
    pose: ModelPose | None = None
    style: ClothingStyle | None = None
    is_active: bool | None = None


class ModelProfileOut(ORMModel):
    id: uuid.UUID
    name: str
    organization_id: uuid.UUID | None
    image_asset_id: uuid.UUID
    gender: ModelGender | None
    age_group: ModelAgeGroup | None
    body_type: ModelBodyType | None
    pose: ModelPose | None
    style: ClothingStyle | None
    collection: str | None
    tags: list[str] | None
    is_active: bool
    is_builtin: bool
    validation: dict | None
    created_at: datetime

    image: AssetOut | None = None

    @property
    def is_custom(self) -> bool:
        return self.organization_id is not None


class ModelFilterParams(BaseModel):
    """§11 library filters."""

    gender: ModelGender | None = None
    age_group: ModelAgeGroup | None = None
    body_type: ModelBodyType | None = None
    pose: ModelPose | None = None
    style: ClothingStyle | None = None
    collection: str | None = None
    custom_only: bool = False


# ------------------------------------------------------------- brand kits ---

class BrandKitUpsert(BaseModel):
    name: str = Field(default="Default", max_length=160)
    logo_asset_id: uuid.UUID | None = None
    primary_color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    secondary_color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    accent_color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    heading_font: str | None = Field(default=None, max_length=120)
    body_font: str | None = Field(default=None, max_length=120)
    brand_tone: str | None = Field(default=None, max_length=200)
    cta_style: str | None = Field(default=None, max_length=120)
    product_positioning: str | None = Field(default=None, max_length=2000)


class BrandKitOut(ORMModel):
    id: uuid.UUID
    name: str
    is_default: bool
    logo_asset_id: uuid.UUID | None
    primary_color: str | None
    secondary_color: str | None
    accent_color: str | None
    heading_font: str | None
    body_font: str | None
    brand_tone: str | None
    cta_style: str | None
    product_positioning: str | None
    created_at: datetime

    logo_url: str | None = None
