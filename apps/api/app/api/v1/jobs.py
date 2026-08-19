"""Generation endpoints (§56).

Every route here does the same three things: validate, create a job, return a
job id (§18). None of them wait for an image.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.core.deps import CurrentPrincipal, DbSession, WritePrincipal, get_current_user
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.ratelimit import generate_rate_limit
from app.models import GenerationJob
from app.models.enums import GarmentCategory, JobStatus, JobType
from app.queue.events import USER_CHANNEL, subscribe
from app.schemas.common import Message, Page
from app.schemas.jobs import (
    BackgroundRemoveCreate,
    BackgroundReplaceCreate,
    BulkJobCreatedOut,
    BulkVTONJobCreate,
    EnhanceCreate,
    ExpandCreate,
    InpaintCreate,
    JobCreatedOut,
    JobOut,
    ObjectRemoveCreate,
    ProductPhotographyCreate,
    UpscaleCreate,
    VTONJobCreate,
)
from app.services import assets as asset_service
from app.services import credits, generation_service

log = get_logger(__name__)
router = APIRouter(tags=["generation"])

Limited = Depends(generate_rate_limit)


def _created(job: GenerationJob, balance: int) -> JobCreatedOut:
    return JobCreatedOut(
        job_id=job.id,
        status=JobStatus(job.status),
        credits_cost=job.credits_cost,
        credits_remaining=balance,
    )


# ------------------------------------------------------------------- VTON ---

@router.post("/vton/jobs", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def create_vton_job(
    payload: VTONJobCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    garment_id, cached_mask_id, product = await generation_service.resolve_garment_asset(
        session,
        principal.organization_id,
        garment_asset_id=payload.garment_asset_id,
        product_id=payload.product_id,
    )
    person_id, profile = await generation_service.resolve_person_asset(
        session,
        principal.organization_id,
        person_asset_id=payload.person_asset_id,
        model_profile_id=payload.model_profile_id,
    )

    # A mask the user drew wins; otherwise fall back to the one analysis cached
    # for this product, and only then to auto-masking inside the pipeline.
    mask_id = payload.mask_asset_id or cached_mask_id
    if payload.mask_asset_id:
        await asset_service.get_owned(
            session, payload.mask_asset_id, principal.organization_id
        )

    # Precedence: what the user explicitly picked, then what analysis detected
    # for this product, then a safe default.
    category = payload.category
    if category is None and product is not None:
        category = product.category
    if category is None:
        category = GarmentCategory.UPPER_BODY

    job = await generation_service.create_job(
        session,
        job_type=JobType.VTON,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        product_id=payload.product_id,
        model_profile_id=payload.model_profile_id,
        mask_asset_id=mask_id,
        seed=payload.seed,
        hd=payload.hd,
        num_images=payload.num_images,
        params={
            "garment_asset_id": str(garment_id),
            "person_asset_id": str(person_id),
            "category": str(category),
            "steps": payload.steps,
            "guidance_scale": payload.guidance_scale,
            "auto_mask": payload.auto_mask,
            "preserve_face": payload.preserve_face,
        },
    )
    return _created(job, principal.organization.credit_balance)


@router.post("/vton/bulk", response_model=BulkJobCreatedOut, status_code=202,
             dependencies=[Limited])
async def create_bulk_vton(
    payload: BulkVTONJobCreate, session: DbSession, principal: WritePrincipal
) -> BulkJobCreatedOut:
    """§39 — product × models × poses fans out into individual jobs."""
    from app.services import feature_flags

    await feature_flags.require(
        session, "BULK_GENERATION_ENABLED", principal.organization_id
    )

    garment_id, cached_mask_id, product = await generation_service.resolve_garment_asset(
        session,
        principal.organization_id,
        garment_asset_id=payload.garment_asset_id,
        product_id=payload.product_id,
    )

    poses = payload.poses or [""]
    total_cost = credits.cost_for(JobType.VTON, hd=payload.hd) * len(
        payload.model_profile_ids
    ) * len(poses)
    # Check the whole batch up front — a partially-created batch that runs out
    # of credits halfway is worse than a clean rejection.
    await credits.ensure_balance(session, principal.organization_id, total_cost)

    batch_id = uuid.uuid4()
    jobs: list[GenerationJob] = []

    for model_profile_id in payload.model_profile_ids:
        person_id, _ = await generation_service.resolve_person_asset(
            session,
            principal.organization_id,
            person_asset_id=None,
            model_profile_id=model_profile_id,
        )
        for pose in poses:
            job = await generation_service.create_job(
                session,
                job_type=JobType.VTON,
                organization_id=principal.organization_id,
                user_id=principal.user_id,
                project_id=payload.project_id,
                product_id=payload.product_id,
                model_profile_id=model_profile_id,
                mask_asset_id=cached_mask_id,
                seed=payload.seed,
                hd=payload.hd,
                batch_id=batch_id,
                params={
                    "garment_asset_id": str(garment_id),
                    "person_asset_id": str(person_id),
                    "category": str(payload.category),
                    "steps": payload.steps,
                    "pose": pose or None,
                },
            )
            jobs.append(job)

    return BulkJobCreatedOut(
        batch_id=batch_id,
        job_ids=[j.id for j in jobs],
        credits_cost=sum(j.credits_cost for j in jobs),
        credits_remaining=principal.organization.credit_balance,
    )


# ----------------------------------------------------------- image studio ---

@router.post("/background/remove", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def remove_background(
    payload: BackgroundRemoveCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    await asset_service.get_owned(session, payload.image_asset_id, principal.organization_id)
    job = await generation_service.create_job(
        session,
        job_type=JobType.BACKGROUND_REMOVE,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        params={
            "image_asset_id": str(payload.image_asset_id),
            "background": payload.background,
            "background_color": payload.background_color,
        },
    )
    return _created(job, principal.organization.credit_balance)


@router.post("/background/replace", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def replace_background(
    payload: BackgroundReplaceCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    await asset_service.get_owned(session, payload.image_asset_id, principal.organization_id)
    job = await generation_service.create_job(
        session,
        job_type=JobType.BACKGROUND_REPLACE,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        seed=payload.seed,
        params={
            "image_asset_id": str(payload.image_asset_id),
            "preset": payload.preset,
            "prompt": payload.prompt,
            "steps": payload.steps,
        },
    )
    return _created(job, principal.organization.credit_balance)


@router.post("/photography/jobs", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def product_photography(
    payload: ProductPhotographyCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    await asset_service.get_owned(session, payload.image_asset_id, principal.organization_id)
    job = await generation_service.create_job(
        session,
        job_type=JobType.PRODUCT_PHOTOGRAPHY,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        seed=payload.seed,
        params={
            "image_asset_id": str(payload.image_asset_id),
            "background": payload.background,
            "lighting": payload.lighting,
            "camera": payload.camera,
            "composition": payload.composition,
            "prompt": payload.prompt,
            "steps": payload.steps,
        },
    )
    return _created(job, principal.organization.credit_balance)


@router.post("/edit/inpaint", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def generative_fill(
    payload: InpaintCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    await asset_service.get_owned(session, payload.image_asset_id, principal.organization_id)
    await asset_service.get_owned(session, payload.mask_asset_id, principal.organization_id)

    job = await generation_service.create_job(
        session,
        job_type=JobType.INPAINT,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        mask_asset_id=payload.mask_asset_id,
        seed=payload.seed,
        params={
            "image_asset_id": str(payload.image_asset_id),
            "prompt": payload.prompt,
            "strength": payload.strength,
            "steps": payload.steps,
        },
    )
    return _created(job, principal.organization.credit_balance)


@router.post("/edit/remove-object", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def remove_object(
    payload: ObjectRemoveCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    await asset_service.get_owned(session, payload.image_asset_id, principal.organization_id)
    await asset_service.get_owned(session, payload.mask_asset_id, principal.organization_id)

    job = await generation_service.create_job(
        session,
        job_type=JobType.OBJECT_REMOVE,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        mask_asset_id=payload.mask_asset_id,
        seed=payload.seed,
        params={"image_asset_id": str(payload.image_asset_id), "steps": payload.steps},
    )
    return _created(job, principal.organization.credit_balance)


@router.post("/edit/expand", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def expand_image(
    payload: ExpandCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    await asset_service.get_owned(session, payload.image_asset_id, principal.organization_id)
    job = await generation_service.create_job(
        session,
        job_type=JobType.EXPAND,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        seed=payload.seed,
        params={
            "image_asset_id": str(payload.image_asset_id),
            "left": payload.left,
            "right": payload.right,
            "top": payload.top,
            "bottom": payload.bottom,
            "prompt": payload.prompt,
        },
    )
    return _created(job, principal.organization.credit_balance)


@router.post("/upscale/jobs", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def upscale_image(
    payload: UpscaleCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    await asset_service.get_owned(session, payload.image_asset_id, principal.organization_id)
    job = await generation_service.create_job(
        session,
        job_type=JobType.UPSCALE,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        params={"image_asset_id": str(payload.image_asset_id), "scale": payload.scale},
    )
    return _created(job, principal.organization.credit_balance)


@router.post("/edit/enhance", response_model=JobCreatedOut, status_code=202,
             dependencies=[Limited])
async def enhance_image(
    payload: EnhanceCreate, session: DbSession, principal: WritePrincipal
) -> JobCreatedOut:
    await asset_service.get_owned(session, payload.image_asset_id, principal.organization_id)
    job = await generation_service.create_job(
        session,
        job_type=JobType.ENHANCE,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        project_id=payload.project_id,
        params={
            "image_asset_id": str(payload.image_asset_id),
            "auto": payload.auto,
            "brightness": payload.brightness,
            "contrast": payload.contrast,
            "saturation": payload.saturation,
            "sharpness": payload.sharpness,
            "blur": payload.blur,
        },
    )
    return _created(job, principal.organization.credit_balance)


# --------------------------------------------------------------- job reads --

@router.get("/jobs", response_model=Page[JobOut])
async def list_jobs(
    session: DbSession,
    principal: CurrentPrincipal,
    type: JobType | None = None,
    status: JobStatus | None = None,
    project_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> Page[JobOut]:
    conditions = [GenerationJob.organization_id == principal.organization_id]
    for column, value in (
        (GenerationJob.type, type),
        (GenerationJob.status, status),
        (GenerationJob.project_id, project_id),
        (GenerationJob.batch_id, batch_id),
    ):
        if value is not None:
            conditions.append(column == value)

    total = int(
        await session.scalar(select(func.count(GenerationJob.id)).where(*conditions)) or 0
    )
    rows = (
        await session.scalars(
            select(GenerationJob)
            .where(*conditions)
            .order_by(GenerationJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return Page[JobOut](
        items=[await generation_service.to_out(session, job) for job in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> JobOut:
    job = await _owned_job(session, job_id, principal.organization_id)
    return await generation_service.to_out(session, job)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: uuid.UUID, session: DbSession, principal: WritePrincipal
) -> JobOut:
    job = await _owned_job(session, job_id, principal.organization_id)
    job = await generation_service.cancel_job(session, job)
    return await generation_service.to_out(session, job)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(
    job_id: uuid.UUID, session: DbSession, principal: WritePrincipal
) -> JobOut:
    job = await _owned_job(session, job_id, principal.organization_id)
    job = await generation_service.retry_job(session, job)
    return await generation_service.to_out(session, job)


@router.get("/creations", response_model=Page[JobOut])
async def list_creations(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> Page[JobOut]:
    """§36 gallery — completed generations only."""
    conditions = [
        GenerationJob.organization_id == principal.organization_id,
        GenerationJob.status == JobStatus.COMPLETED,
    ]
    if project_id is not None:
        conditions.append(GenerationJob.project_id == project_id)

    total = int(
        await session.scalar(select(func.count(GenerationJob.id)).where(*conditions)) or 0
    )
    rows = (
        await session.scalars(
            select(GenerationJob)
            .where(*conditions)
            .order_by(GenerationJob.completed_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return Page[JobOut](
        items=[await generation_service.to_out(session, job) for job in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _owned_job(session, job_id: uuid.UUID, organization_id: uuid.UUID) -> GenerationJob:
    job = await session.get(GenerationJob, job_id)
    if job is None or job.organization_id != organization_id:
        raise NotFoundError("Job not found.")
    return job


# ---------------------------------------------------------------- SSE (§57) --

@router.get("/events")
async def job_events(request: Request, session: DbSession) -> StreamingResponse:
    """Server-sent events for live job progress.

    One stream per user covers every job they own. Auth is resolved manually
    because EventSource cannot set headers — it sends cookies, which is exactly
    what get_current_user reads first.
    """
    user = await get_current_user(session, request.cookies.get("afs_access"), None)
    channel = USER_CHANNEL.format(user_id=user.id)

    async def stream() -> AsyncGenerator[str, None]:
        # Tell the client to back off if it reconnects, and prove the stream is
        # alive immediately so the UI can drop its "connecting" state.
        yield "retry: 3000\n\n"
        yield f"event: connected\ndata: {json.dumps({'user_id': str(user.id)})}\n\n"

        try:
            async for message in subscribe(channel):
                if await request.is_disconnected():
                    break
                yield f"event: {message['event']}\ndata: {json.dumps(message)}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("sse.stream_error", error=str(exc))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx buffers responses by default, which would hold every event
            # until the stream closes.
            "X-Accel-Buffering": "no",
        },
    )
