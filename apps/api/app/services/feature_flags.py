"""Feature flags (§69)."""

from __future__ import annotations

import uuid
import zlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FeatureDisabledError
from app.models import FeatureFlag, Organization

#: Shipped defaults, seeded on first boot. A missing flag defaults to *on* so a
#: forgotten seed does not silently disable the product.
DEFAULT_FLAGS: dict[str, tuple[str, bool]] = {
    "VTON_ENABLED": ("Virtual try-on generation", True),
    "BACKGROUND_ENABLED": ("Background removal and replacement", True),
    "PHOTOGRAPHY_ENABLED": ("AI product photography", True),
    "EDITOR_ENABLED": ("Image editor and generative fill", True),
    "UPSCALE_ENABLED": ("AI upscaling", True),
    "BULK_GENERATION_ENABLED": ("Bulk generation", True),
    "MODEL_SWAP_ENABLED": ("Model swap", False),
    "POSE_ENABLED": ("Pose generator", False),
    "VIDEO_ENABLED": ("Image to video", False),
    "ADS_ENABLED": ("Ad creative studio", False),
    "BRAND_KIT_ENABLED": ("Brand kits", True),
}


async def is_enabled(
    session: AsyncSession, key: str | None, organization_id: uuid.UUID | None = None
) -> bool:
    if not key:
        return True

    flag = await session.scalar(select(FeatureFlag).where(FeatureFlag.key == key))
    if flag is None:
        return DEFAULT_FLAGS.get(key, ("", True))[1]
    if not flag.enabled:
        return False

    if organization_id is None:
        return True

    # Explicit allow-list wins over plan and percentage.
    if flag.enabled_organization_ids and str(organization_id) in flag.enabled_organization_ids:
        return True

    if flag.enabled_plans:
        org = await session.get(Organization, organization_id)
        if org is None or str(org.plan) not in flag.enabled_plans:
            return False

    if flag.rollout_percentage < 100:
        # Hash the org id so a given org's bucket is stable across requests —
        # a flag that flickers per call is worse than no flag.
        bucket = zlib.crc32(f"{key}:{organization_id}".encode()) % 100
        if bucket >= flag.rollout_percentage:
            return False

    return True


async def require(
    session: AsyncSession, key: str | None, organization_id: uuid.UUID | None = None
) -> None:
    if not await is_enabled(session, key, organization_id):
        raise FeatureDisabledError("This feature is not available yet.")


async def all_for(
    session: AsyncSession, organization_id: uuid.UUID | None = None
) -> dict[str, bool]:
    """What the frontend reads to decide which studio tools to show."""
    return {key: await is_enabled(session, key, organization_id) for key in DEFAULT_FLAGS}
