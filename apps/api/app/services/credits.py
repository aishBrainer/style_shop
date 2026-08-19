"""Credit accounting (§40).

Billing is inactive, but the ledger runs from day one so switching monetisation
on is a config change, not a migration and a refactor.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InsufficientCreditsError
from app.models import CreditTransaction, Organization
from app.models.enums import CreditReason, JobType, PlanTier

#: §40 pricing. HD and multi-image cost more because they cost more to produce.
CREDIT_COSTS: dict[JobType, int] = {
    JobType.VTON: 1,
    JobType.MODEL_SWAP: 2,
    JobType.POSE: 2,
    JobType.PRODUCT_PHOTOGRAPHY: 1,
    JobType.BACKGROUND_REPLACE: 1,
    JobType.BACKGROUND_REMOVE: 0,  # CPU-only; not worth charging for
    JobType.INPAINT: 1,
    JobType.OBJECT_REMOVE: 1,
    JobType.EXPAND: 1,
    JobType.UPSCALE: 1,
    JobType.ENHANCE: 0,
    JobType.VIDEO: 5,
    JobType.AD_CREATIVE: 1,
}

HD_SURCHARGE = 1

#: Credits granted on signup, and monthly per plan.
SIGNUP_GRANT = 25
MONTHLY_GRANT: dict[PlanTier, int] = {
    PlanTier.FREE: 25,
    PlanTier.PRO: 500,
    PlanTier.BUSINESS: 2000,
}

#: Plan limits applied to an organization at creation (§4).
PLAN_LIMITS: dict[PlanTier, dict[str, int]] = {
    PlanTier.FREE: {
        "storage_quota_mb": 1024,
        "max_projects": 3,
        "max_concurrent_jobs": 1,
    },
    PlanTier.PRO: {
        "storage_quota_mb": 20480,
        "max_projects": 50,
        "max_concurrent_jobs": 3,
    },
    PlanTier.BUSINESS: {
        "storage_quota_mb": 204800,
        "max_projects": 500,
        "max_concurrent_jobs": 8,
    },
}


def cost_for(job_type: JobType, *, hd: bool = False, num_images: int = 1) -> int:
    base = CREDIT_COSTS.get(job_type, 1)
    if base == 0:
        return 0
    return (base + (HD_SURCHARGE if hd else 0)) * max(1, num_images)


async def ensure_balance(session: AsyncSession, organization_id: uuid.UUID, amount: int) -> Organization:
    """Raise if the org cannot afford `amount`. Returns the locked org row."""
    org = await _lock_organization(session, organization_id)
    if amount > 0 and org.credit_balance < amount:
        raise InsufficientCreditsError(
            f"This generation costs {amount} credit{'s' if amount != 1 else ''}, "
            f"but you have {org.credit_balance}."
        )
    return org


async def charge(
    session: AsyncSession,
    organization_id: uuid.UUID,
    amount: int,
    *,
    user_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    reason: CreditReason = CreditReason.GENERATION,
    description: str | None = None,
) -> int:
    """Debit and record. Returns the new balance.

    The row is locked FOR UPDATE first, so two concurrent generations cannot
    both read the same balance and overdraw it.
    """
    if amount <= 0:
        org = await _lock_organization(session, organization_id)
        return org.credit_balance

    org = await ensure_balance(session, organization_id, amount)
    org.credit_balance -= amount

    session.add(
        CreditTransaction(
            organization_id=organization_id,
            user_id=user_id,
            generation_job_id=job_id,
            amount=-amount,
            balance_after=org.credit_balance,
            reason=reason,
            description=description,
        )
    )
    await session.flush()
    return org.credit_balance


async def grant(
    session: AsyncSession,
    organization_id: uuid.UUID,
    amount: int,
    *,
    reason: CreditReason = CreditReason.MONTHLY_GRANT,
    user_id: uuid.UUID | None = None,
    description: str | None = None,
) -> int:
    org = await _lock_organization(session, organization_id)
    org.credit_balance += amount

    session.add(
        CreditTransaction(
            organization_id=organization_id,
            user_id=user_id,
            amount=amount,
            balance_after=org.credit_balance,
            reason=reason,
            description=description,
        )
    )
    await session.flush()
    return org.credit_balance


async def _lock_organization(session: AsyncSession, organization_id: uuid.UUID) -> Organization:
    org = await session.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if org is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Organization not found.")
    return org
