"""Import every model here so Alembic's autogenerate sees the full metadata."""

from app.db.base import Base
from app.models.billing import CreditTransaction, Subscription, UsageDaily
from app.models.branding import AdCreative, BrandKit, CreativeTemplate, Video
from app.models.catalog import Asset, ModelProfile, Product, Project
from app.models.enums import (
    AIModelType,
    AssetStatus,
    AssetType,
    ClothingStyle,
    CommercialUse,
    CreditReason,
    GarmentCategory,
    JobStatus,
    JobType,
    MembershipRole,
    ModelAgeGroup,
    ModelBodyType,
    ModelGender,
    ModelPose,
    NotificationType,
    PlanTier,
    SubscriptionStatus,
    UserRole,
)
from app.models.generation import AIModel, GenerationJob, PromptTemplate
from app.models.identity import Membership, Organization, RefreshSession, User
from app.models.system import (
    AuditLog,
    FeatureFlag,
    Notification,
    SystemSetting,
    WorkerHeartbeat,
)

__all__ = [
    "Base",
    # identity
    "User",
    "Organization",
    "Membership",
    "RefreshSession",
    # catalog
    "Project",
    "Asset",
    "Product",
    "ModelProfile",
    # generation
    "GenerationJob",
    "AIModel",
    "PromptTemplate",
    # billing
    "CreditTransaction",
    "Subscription",
    "UsageDaily",
    # branding
    "BrandKit",
    "CreativeTemplate",
    "AdCreative",
    "Video",
    # system
    "Notification",
    "AuditLog",
    "SystemSetting",
    "FeatureFlag",
    "WorkerHeartbeat",
    # enums
    "AIModelType",
    "AssetStatus",
    "AssetType",
    "ClothingStyle",
    "CommercialUse",
    "CreditReason",
    "GarmentCategory",
    "JobStatus",
    "JobType",
    "MembershipRole",
    "ModelAgeGroup",
    "ModelBodyType",
    "ModelGender",
    "ModelPose",
    "NotificationType",
    "PlanTier",
    "SubscriptionStatus",
    "UserRole",
]
