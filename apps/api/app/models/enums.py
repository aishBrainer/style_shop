"""Enumerations shared by the ORM, the API schemas and the workers.

These values are persisted as strings, so renaming a member is a migration.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class PlanTier(StrEnum):
    """§4. Drives credit grants, size limits and watermarking."""

    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class AssetType(StrEnum):
    """§35."""

    PRODUCT = "product"
    MODEL = "model"
    GENERATED_IMAGE = "generated_image"
    GENERATED_VIDEO = "generated_video"
    LOGO = "logo"
    BRAND_ASSET = "brand_asset"
    MASK = "mask"
    THUMBNAIL = "thumbnail"


class AssetStatus(StrEnum):
    UPLOADING = "uploading"
    READY = "ready"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class GarmentCategory(StrEnum):
    """§10 step 2."""

    UPPER_BODY = "upper_body"
    LOWER_BODY = "lower_body"
    FULL_BODY = "full_body"
    OUTERWEAR = "outerwear"
    DRESS = "dress"
    JUMPSUIT = "jumpsuit"
    # Future (§10): shoes, jewelry, watches, bags, hats, eyewear.
    OTHER = "other"


class JobType(StrEnum):
    VTON = "vton"
    BACKGROUND_REMOVE = "background_remove"
    BACKGROUND_REPLACE = "background_replace"
    PRODUCT_PHOTOGRAPHY = "product_photography"
    UPSCALE = "upscale"
    INPAINT = "inpaint"
    OBJECT_REMOVE = "object_remove"
    EXPAND = "expand"
    ENHANCE = "enhance"
    MODEL_SWAP = "model_swap"
    POSE = "pose"
    VIDEO = "video"
    AD_CREATIVE = "ad_creative"


class JobStatus(StrEnum):
    """§20. Ordered from submission to terminal state."""

    QUEUED = "queued"
    VALIDATING = "validating"
    PREPROCESSING = "preprocessing"
    PROCESSING = "processing"
    POST_PROCESSING = "post_processing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


#: Rough progress percentage per state, for the UI's live progress bar (§46).
JOB_STATUS_PROGRESS: dict[JobStatus, int] = {
    JobStatus.QUEUED: 0,
    JobStatus.VALIDATING: 5,
    JobStatus.PREPROCESSING: 20,
    JobStatus.PROCESSING: 45,
    JobStatus.POST_PROCESSING: 80,
    JobStatus.UPLOADING: 92,
    JobStatus.COMPLETED: 100,
    JobStatus.FAILED: 100,
    JobStatus.CANCELLED: 100,
}

#: Human-readable stage copy shown during generation (§46).
JOB_STATUS_LABEL: dict[JobStatus, str] = {
    JobStatus.QUEUED: "Waiting in queue",
    JobStatus.VALIDATING: "Checking your images",
    JobStatus.PREPROCESSING: "Analysing garment",
    JobStatus.PROCESSING: "Mapping body and applying garment",
    JobStatus.POST_PROCESSING: "Rendering fabric",
    JobStatus.UPLOADING: "Finishing image",
    JobStatus.COMPLETED: "Done",
    JobStatus.FAILED: "Failed",
    JobStatus.CANCELLED: "Cancelled",
}


class AIModelType(StrEnum):
    """§50 — one row per engine kind in the model registry."""

    VTON = "vton"
    IMAGE_GENERATION = "image_generation"
    SEGMENTATION = "segmentation"
    UPSCALE = "upscale"
    INPAINT = "inpaint"
    POSE = "pose"
    HUMAN_PARSING = "human_parsing"
    VIDEO = "video"


class CommercialUse(StrEnum):
    """§72. Blocks a checkpoint from being enabled by accident."""

    ALLOWED = "allowed"
    NOT_ALLOWED = "not_allowed"
    UNREVIEWED = "unreviewed"


class CreditReason(StrEnum):
    SIGNUP_GRANT = "signup_grant"
    MONTHLY_GRANT = "monthly_grant"
    PURCHASE = "purchase"
    GENERATION = "generation"
    REFUND_FAILED_JOB = "refund_failed_job"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class ModelGender(StrEnum):
    FEMALE = "female"
    MALE = "male"
    UNISEX = "unisex"


class ModelAgeGroup(StrEnum):
    YOUNG_ADULT = "young_adult"
    ADULT = "adult"
    MATURE = "mature"


class ModelBodyType(StrEnum):
    SLIM = "slim"
    ATHLETIC = "athletic"
    AVERAGE = "average"
    PLUS_SIZE = "plus_size"


class ModelPose(StrEnum):
    FRONT = "front"
    THREE_QUARTER = "three_quarter"
    SIDE = "side"
    STANDING = "standing"
    WALKING = "walking"
    CASUAL = "casual"


class ClothingStyle(StrEnum):
    FASHION = "fashion"
    CASUAL = "casual"
    LUXURY = "luxury"
    SPORTS = "sports"
    TRADITIONAL = "traditional"
    STREETWEAR = "streetwear"


class NotificationType(StrEnum):
    GENERATION_COMPLETED = "generation_completed"
    GENERATION_FAILED = "generation_failed"
    CREDITS_LOW = "credits_low"
    SYSTEM = "system"
