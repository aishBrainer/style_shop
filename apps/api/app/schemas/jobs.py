"""Generation job schemas (§56)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import GarmentCategory, JobStatus, JobType
from app.schemas.catalog import AssetOut
from app.schemas.common import ORMModel

MAX_STEPS = 60
MAX_IMAGES_PER_JOB = 4


class JobBase(BaseModel):
    project_id: uuid.UUID | None = None
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)  # §67


# --------------------------------------------------------------- try-on ----

class VTONJobCreate(JobBase):
    garment_asset_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None

    model_profile_id: uuid.UUID | None = None
    person_asset_id: uuid.UUID | None = None

    mask_asset_id: uuid.UUID | None = None
    # None means "use whatever product analysis detected" (§10). Only an
    # explicit value overrides it — a non-None default would silently discard
    # the detected category on every request.
    category: GarmentCategory | None = None

    steps: int = Field(default=30, ge=10, le=MAX_STEPS)
    guidance_scale: float = Field(default=2.0, ge=0.0, le=15.0)
    hd: bool = False
    num_images: int = Field(default=1, ge=1, le=MAX_IMAGES_PER_JOB)
    auto_mask: bool = True
    preserve_face: bool = True

    @model_validator(mode="after")
    def _need_one_of_each(self) -> "VTONJobCreate":
        if not (self.garment_asset_id or self.product_id):
            raise ValueError("Provide either garment_asset_id or product_id.")
        if not (self.model_profile_id or self.person_asset_id):
            raise ValueError("Provide either model_profile_id or person_asset_id.")
        return self


class BulkVTONJobCreate(JobBase):
    """§39 — one product across N models and M poses becomes N×M jobs."""

    product_id: uuid.UUID | None = None
    garment_asset_id: uuid.UUID | None = None
    model_profile_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    poses: list[str] = Field(default_factory=list, max_length=5)
    category: GarmentCategory = GarmentCategory.UPPER_BODY
    hd: bool = False
    steps: int = Field(default=30, ge=10, le=MAX_STEPS)

    @model_validator(mode="after")
    def _need_garment(self) -> "BulkVTONJobCreate":
        if not (self.garment_asset_id or self.product_id):
            raise ValueError("Provide either garment_asset_id or product_id.")
        return self

    @property
    def job_count(self) -> int:
        return len(self.model_profile_ids) * max(1, len(self.poses))


# --------------------------------------------------------- image studio ----

class BackgroundRemoveCreate(JobBase):
    image_asset_id: uuid.UUID
    background: str = Field(default="transparent", pattern="^(transparent|white|color)$")
    background_color: str = Field(default="#FFFFFF", pattern="^#[0-9A-Fa-f]{6}$")


class BackgroundReplaceCreate(JobBase):
    image_asset_id: uuid.UUID
    preset: str | None = None
    prompt: str | None = Field(default=None, max_length=1000)
    steps: int = Field(default=30, ge=10, le=MAX_STEPS)

    @model_validator(mode="after")
    def _need_preset_or_prompt(self) -> "BackgroundReplaceCreate":
        if not self.preset and not self.prompt:
            raise ValueError("Provide a preset or a prompt.")
        return self


class ProductPhotographyCreate(JobBase):
    image_asset_id: uuid.UUID
    background: str = "studio"
    lighting: str = "studio"
    camera: str = "medium"
    composition: str = "center"
    prompt: str | None = Field(default=None, max_length=1000)
    steps: int = Field(default=30, ge=10, le=MAX_STEPS)


class InpaintCreate(JobBase):
    image_asset_id: uuid.UUID
    mask_asset_id: uuid.UUID
    prompt: str = Field(min_length=1, max_length=1000)
    strength: float = Field(default=0.9, ge=0.1, le=1.0)
    steps: int = Field(default=30, ge=10, le=MAX_STEPS)


class ObjectRemoveCreate(JobBase):
    image_asset_id: uuid.UUID
    mask_asset_id: uuid.UUID
    steps: int = Field(default=30, ge=10, le=MAX_STEPS)


class ExpandCreate(JobBase):
    image_asset_id: uuid.UUID
    left: int = Field(default=0, ge=0, le=1024)
    right: int = Field(default=0, ge=0, le=1024)
    top: int = Field(default=0, ge=0, le=1024)
    bottom: int = Field(default=0, ge=0, le=1024)
    prompt: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _need_direction(self) -> "ExpandCreate":
        if max(self.left, self.right, self.top, self.bottom) == 0:
            raise ValueError("Specify at least one direction to expand.")
        return self


class UpscaleCreate(JobBase):
    image_asset_id: uuid.UUID
    scale: int = Field(default=2)

    @model_validator(mode="after")
    def _valid_scale(self) -> "UpscaleCreate":
        if self.scale not in (2, 4):
            raise ValueError("Scale must be 2 or 4.")
        return self


class EnhanceCreate(JobBase):
    image_asset_id: uuid.UUID
    auto: bool = False
    brightness: float = Field(default=1.0, ge=0.2, le=2.5)
    contrast: float = Field(default=1.0, ge=0.2, le=2.5)
    saturation: float = Field(default=1.0, ge=0.0, le=2.5)
    sharpness: float = Field(default=1.0, ge=0.0, le=3.0)
    blur: float = Field(default=0.0, ge=0.0, le=10.0)


# ------------------------------------------------------------- responses ----

class JobOut(ORMModel):
    id: uuid.UUID
    type: JobType
    status: JobStatus
    progress: int
    stage_label: str | None
    project_id: uuid.UUID | None
    batch_id: uuid.UUID | None

    params: dict
    seed: int | None
    ai_model_key: str | None

    output_asset_ids: list[str] | None
    primary_output_asset_id: uuid.UUID | None

    error_code: str | None
    error_message: str | None
    retry_count: int
    max_retries: int

    credits_cost: int
    duration_ms: int | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    # Filled in by the service layer.
    outputs: list[AssetOut] = []
    queue_position: int | None = None
    estimated_seconds: int | None = None

    # `error_detail` is intentionally absent — §64: no stack traces to users.


class JobCreatedOut(BaseModel):
    """§18 — POST returns immediately with an id, never a finished image."""

    job_id: uuid.UUID
    status: JobStatus
    queue_position: int | None = None
    estimated_seconds: int | None = None
    credits_cost: int
    credits_remaining: int


class BulkJobCreatedOut(BaseModel):
    batch_id: uuid.UUID
    job_ids: list[uuid.UUID]
    credits_cost: int
    credits_remaining: int


class JobFilterParams(BaseModel):
    type: JobType | None = None
    status: JobStatus | None = None
    project_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
