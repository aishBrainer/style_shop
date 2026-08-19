"""Generation job creation and dispatch (§18, §92).

The one place that turns a validated request into a queued job. Routes call
this; workers never do. Nothing here runs AI — it charges credits, writes the
row, and hands the id to Celery.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models import GenerationJob, ModelProfile, Organization, Product
from app.models.enums import JobStatus, JobType
from app.queue.celery_app import queue_for
from app.queue.events import publish_job_event, queue_depth, queue_position
from app.schemas.jobs import JobOut
from app.services import assets as asset_service
from app.services import credits, feature_flags

log = get_logger(__name__)

#: §93 — rough per-type expectations used for the queue ETA. Refined at runtime
#: by the observed average, so these are only the cold-start estimate.
BASELINE_SECONDS: dict[JobType, int] = {
    JobType.VTON: 45,
    JobType.MODEL_SWAP: 60,
    JobType.POSE: 60,
    JobType.PRODUCT_PHOTOGRAPHY: 35,
    JobType.BACKGROUND_REPLACE: 35,
    JobType.BACKGROUND_REMOVE: 8,
    JobType.INPAINT: 30,
    JobType.OBJECT_REMOVE: 30,
    JobType.EXPAND: 40,
    JobType.UPSCALE: 25,
    JobType.ENHANCE: 3,
    JobType.VIDEO: 180,
    JobType.AD_CREATIVE: 10,
}

#: §69 — which flag gates which job type.
FLAG_FOR_JOB_TYPE: dict[JobType, str] = {
    JobType.VTON: "VTON_ENABLED",
    JobType.VIDEO: "VIDEO_ENABLED",
    JobType.UPSCALE: "UPSCALE_ENABLED",
    JobType.AD_CREATIVE: "ADS_ENABLED",
}


async def create_job(
    session: AsyncSession,
    *,
    job_type: JobType,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    params: dict[str, Any],
    project_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    model_profile_id: uuid.UUID | None = None,
    mask_asset_id: uuid.UUID | None = None,
    seed: int | None = None,
    hd: bool = False,
    num_images: int = 1,
    batch_id: uuid.UUID | None = None,
    dispatch: bool = True,
) -> GenerationJob:
    await feature_flags.require(session, FLAG_FOR_JOB_TYPE.get(job_type), organization_id)
    await _enforce_concurrency(session, organization_id)

    cost = credits.cost_for(job_type, hd=hd, num_images=num_images)
    # Checked before the row is written so a broke user gets 402 rather than a
    # queued job that dies on charge.
    await credits.ensure_balance(session, organization_id, cost)

    # §67 — always store a seed. "Random" means we pick one and record it, so
    # any generation can be reproduced.
    effective_seed = seed if seed is not None else random.randint(0, 2**31 - 1)

    job = GenerationJob(
        organization_id=organization_id,
        user_id=user_id,
        project_id=project_id,
        type=job_type,
        status=JobStatus.QUEUED,
        progress=0,
        batch_id=batch_id,
        product_id=product_id,
        model_profile_id=model_profile_id,
        mask_asset_id=mask_asset_id,
        params={**params, "hd": hd, "num_images": num_images},
        seed=effective_seed,
        credits_cost=cost,
        max_retries=2,
        queued_at=utcnow(),
    )
    session.add(job)
    await session.flush()

    await credits.charge(
        session,
        organization_id,
        cost,
        user_id=user_id,
        job_id=job.id,
        description=f"{job_type} generation",
    )

    if dispatch:
        await dispatch_job(session, job)

    return job


async def dispatch_job(session: AsyncSession, job: GenerationJob) -> None:
    """Hand the job to Celery.

    Committing before enqueueing matters: if the worker picks the job up before
    the transaction lands, it reads a row that does not exist yet.
    """
    from app.queue.tasks import TASK_FOR_JOB_TYPE

    task = TASK_FOR_JOB_TYPE.get(str(job.type))
    if task is None:
        raise ValidationError(f"No worker is registered for {job.type} jobs.")

    await session.commit()

    async_result = task.apply_async(args=[str(job.id)], queue=queue_for(job.type))
    job.celery_task_id = async_result.id
    await session.flush()

    publish_job_event(
        "job.created",
        job.id,
        user_id=job.user_id,
        payload={"status": JobStatus.QUEUED, "progress": 0, "type": job.type},
    )
    log.info("job.dispatched", job_id=str(job.id), type=str(job.type), task_id=async_result.id)


async def cancel_job(session: AsyncSession, job: GenerationJob) -> GenerationJob:
    if job.is_terminal:
        raise ValidationError(f"This job is already {job.status} and cannot be cancelled.")

    # Read before mutating: once status flips, "did this ever run?" is lost.
    never_started = job.started_at is None

    if job.celery_task_id:
        from app.queue.celery_app import celery

        # terminate=False: a running job is left to finish its current step
        # rather than being SIGKILLed mid-write, which could strand an asset.
        celery.control.revoke(job.celery_task_id, terminate=False)

    job.status = JobStatus.CANCELLED
    job.progress = 100
    job.completed_at = utcnow()

    # Only refund work that never consumed GPU time.
    if never_started:
        await _refund(session, job)

    await session.flush()
    publish_job_event(
        "job.cancelled", job.id, user_id=job.user_id,
        payload={"status": JobStatus.CANCELLED, "progress": 100},
    )
    return job


async def retry_job(session: AsyncSession, job: GenerationJob) -> GenerationJob:
    if not job.can_retry:
        raise ValidationError("This job cannot be retried.")

    cost = job.credits_cost
    if job.credits_refunded and cost > 0:
        await credits.ensure_balance(session, job.organization_id, cost)
        await credits.charge(
            session, job.organization_id, cost,
            user_id=job.user_id, job_id=job.id, description="Retry",
        )
        job.credits_refunded = False

    job.status = JobStatus.QUEUED
    job.progress = 0
    job.error_code = None
    job.error_message = None
    job.error_detail = None
    job.started_at = None
    job.completed_at = None
    job.retry_count += 1
    job.queued_at = utcnow()
    await session.flush()

    await dispatch_job(session, job)
    return job


async def _refund(session: AsyncSession, job: GenerationJob) -> None:
    from app.models import CreditTransaction
    from app.models.enums import CreditReason

    if job.credits_refunded or job.credits_cost <= 0:
        return

    org = await session.get(Organization, job.organization_id)
    if org is None:
        return

    org.credit_balance += job.credits_cost
    session.add(
        CreditTransaction(
            organization_id=org.id,
            user_id=job.user_id,
            generation_job_id=job.id,
            amount=job.credits_cost,
            balance_after=org.credit_balance,
            reason=CreditReason.REFUND_FAILED_JOB,
            description="Cancelled before processing",
        )
    )
    job.credits_refunded = True


async def _enforce_concurrency(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """§52 — an org cannot flood the queue past its plan's concurrency."""
    org = await session.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found.")

    active = int(
        await session.scalar(
            select(func.count(GenerationJob.id)).where(
                GenerationJob.organization_id == organization_id,
                GenerationJob.status.in_(
                    [
                        JobStatus.QUEUED,
                        JobStatus.VALIDATING,
                        JobStatus.PREPROCESSING,
                        JobStatus.PROCESSING,
                        JobStatus.POST_PROCESSING,
                        JobStatus.UPLOADING,
                    ]
                ),
            )
        )
        or 0
    )

    # Bulk generation (§39) is the whole point of the higher tiers, so the cap
    # is generous relative to the plan's concurrency rather than equal to it.
    ceiling = max(org.max_concurrent_jobs * 10, 20)
    if active >= ceiling:
        raise ForbiddenError(
            f"You already have {active} generations in progress. "
            f"Wait for some to finish before starting more.",
            code="TOO_MANY_ACTIVE_JOBS",
        )


# ------------------------------------------------------------- resolution ---

async def resolve_garment_asset(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    garment_asset_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
) -> tuple[uuid.UUID, uuid.UUID | None, Product | None]:
    """Returns (image_asset_id, cached_mask_asset_id, product)."""
    if product_id is not None:
        product = await session.get(Product, product_id)
        if product is None or product.organization_id != organization_id:
            raise NotFoundError("Product not found.")
        return product.image_asset_id, product.mask_asset_id, product

    if garment_asset_id is None:
        raise ValidationError("Provide either garment_asset_id or product_id.")

    asset = await asset_service.get_owned(session, garment_asset_id, organization_id)
    return asset.id, None, None


async def resolve_person_asset(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    person_asset_id: uuid.UUID | None,
    model_profile_id: uuid.UUID | None,
) -> tuple[uuid.UUID, ModelProfile | None]:
    if model_profile_id is not None:
        profile = await session.get(ModelProfile, model_profile_id)
        # A library model has organization_id NULL and is visible to everyone;
        # a custom model is visible only to the org that uploaded it (§61).
        if profile is None or (
            profile.organization_id is not None
            and profile.organization_id != organization_id
        ):
            raise NotFoundError("Model not found.")
        if not profile.is_active:
            reasons = (profile.validation or {}).get("reasons") or []
            raise ValidationError(
                reasons[0] if reasons else "That model image cannot be used for try-on."
            )
        return profile.image_asset_id, profile

    if person_asset_id is None:
        raise ValidationError("Provide either person_asset_id or model_profile_id.")

    asset = await asset_service.get_owned(session, person_asset_id, organization_id)
    return asset.id, None


# ------------------------------------------------------------ presentation --

async def to_out(session: AsyncSession, job: GenerationJob, *, with_outputs: bool = True) -> JobOut:
    out = JobOut.model_validate(job)

    if with_outputs and job.output_asset_ids:
        from app.models import Asset

        rows = await session.scalars(
            select(Asset).where(
                Asset.id.in_([uuid.UUID(i) for i in job.output_asset_ids]),
                Asset.deleted_at.is_(None),
            )
        )
        # Preserve the order the worker produced them in.
        by_id = {str(a.id): a for a in rows}
        out.outputs = [
            asset_service.to_out(by_id[i]) for i in job.output_asset_ids if i in by_id
        ]

    if job.status == JobStatus.QUEUED:
        queue = queue_for(job.type)
        position = queue_position(job.id, queue) or (queue_depth(queue) or None)
        out.queue_position = position
        baseline = BASELINE_SECONDS.get(JobType(job.type), 45)
        out.estimated_seconds = baseline * (position or 1)
    elif not job.is_terminal:
        out.estimated_seconds = BASELINE_SECONDS.get(JobType(job.type), 45)

    return out
