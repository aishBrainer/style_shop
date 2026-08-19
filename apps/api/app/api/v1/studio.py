"""Studio metadata: presets, feature flags, credits and usage.

Everything the studio UI needs to render its option panels without hard-coding
lists that also live in the backend.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.ai.pipelines.image_ops import (
    BACKGROUND_PRESETS,
    CAMERA_MODIFIERS,
    COMPOSITION_MODIFIERS,
    LIGHTING_MODIFIERS,
)
from app.core.deps import CurrentPrincipal, DbSession
from app.db.base import utcnow
from app.models import CreditTransaction, GenerationJob, PromptTemplate
from app.models.enums import (
    ClothingStyle,
    GarmentCategory,
    JobStatus,
    JobType,
    ModelAgeGroup,
    ModelBodyType,
    ModelGender,
    ModelPose,
)
from app.schemas.common import ORMModel, Page
from app.services import credits, feature_flags

router = APIRouter(tags=["studio"])


class PresetOut(BaseModel):
    key: str
    label: str
    prompt: str | None = None
    preview_url: str | None = None


class StudioOptions(BaseModel):
    """One call the studio makes on load. Everything the option panels need."""

    garment_categories: list[PresetOut]
    background_presets: list[PresetOut]
    lighting: list[PresetOut]
    camera: list[PresetOut]
    composition: list[PresetOut]
    model_filters: dict[str, list[str]]
    poses: list[PresetOut]
    credit_costs: dict[str, int]
    features: dict[str, bool]


#: §29 pose presets.
POSE_PRESETS: dict[str, str] = {
    "standing": "standing straight, relaxed arms",
    "walking": "walking forward, natural stride",
    "sitting": "seated, relaxed posture",
    "hands_on_waist": "hands on waist, confident stance",
    "crossed_arms": "arms crossed",
    "side": "side profile view",
    "fashion": "editorial fashion pose",
}


def _humanise(key: str) -> str:
    return key.replace("_", " ").title()


@router.get("/studio/options", response_model=StudioOptions)
async def studio_options(session: DbSession, principal: CurrentPrincipal) -> StudioOptions:
    prompts = (
        await session.scalars(
            select(PromptTemplate)
            .where(PromptTemplate.is_active.is_(True))
            .order_by(PromptTemplate.sort_order)
        )
    ).all()
    # Database templates (§68) override the shipped defaults where they exist.
    db_backgrounds = {p.key: p for p in prompts if p.category == "background"}

    backgrounds = [
        PresetOut(
            key=key,
            label=db_backgrounds[key].label if key in db_backgrounds else _humanise(key),
            prompt=db_backgrounds[key].prompt if key in db_backgrounds else prompt,
            preview_url=db_backgrounds[key].preview_url if key in db_backgrounds else None,
        )
        for key, prompt in BACKGROUND_PRESETS.items()
    ]

    return StudioOptions(
        garment_categories=[
            PresetOut(key=str(c), label=_humanise(str(c))) for c in GarmentCategory
        ],
        background_presets=backgrounds,
        lighting=[PresetOut(key=k, label=_humanise(k), prompt=v)
                  for k, v in LIGHTING_MODIFIERS.items()],
        camera=[PresetOut(key=k, label=_humanise(k), prompt=v)
                for k, v in CAMERA_MODIFIERS.items()],
        composition=[PresetOut(key=k, label=_humanise(k), prompt=v)
                     for k, v in COMPOSITION_MODIFIERS.items()],
        model_filters={
            "gender": [str(v) for v in ModelGender],
            "age_group": [str(v) for v in ModelAgeGroup],
            "body_type": [str(v) for v in ModelBodyType],
            "pose": [str(v) for v in ModelPose],
            "style": [str(v) for v in ClothingStyle],
        },
        poses=[PresetOut(key=k, label=_humanise(k), prompt=v) for k, v in POSE_PRESETS.items()],
        credit_costs={str(k): v for k, v in credits.CREDIT_COSTS.items()},
        features=await feature_flags.all_for(session, principal.organization_id),
    )


# ---------------------------------------------------------------- credits ---

class CreditTransactionOut(ORMModel):
    id: uuid.UUID
    amount: int
    balance_after: int
    reason: str
    description: str | None
    created_at: datetime


class CreditSummary(BaseModel):
    balance: int
    plan: str
    consumed_30d: int
    granted_30d: int
    transactions: list[CreditTransactionOut]


@router.get("/credits", response_model=CreditSummary)
async def credit_summary(
    session: DbSession,
    principal: CurrentPrincipal,
    limit: int = Query(default=20, ge=1, le=100),
) -> CreditSummary:
    since = utcnow() - timedelta(days=30)

    consumed = await session.scalar(
        select(func.sum(CreditTransaction.amount)).where(
            CreditTransaction.organization_id == principal.organization_id,
            CreditTransaction.amount < 0,
            CreditTransaction.created_at >= since,
        )
    )
    granted = await session.scalar(
        select(func.sum(CreditTransaction.amount)).where(
            CreditTransaction.organization_id == principal.organization_id,
            CreditTransaction.amount > 0,
            CreditTransaction.created_at >= since,
        )
    )
    rows = await session.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.organization_id == principal.organization_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
    )

    return CreditSummary(
        balance=principal.organization.credit_balance,
        plan=str(principal.organization.plan),
        consumed_30d=abs(int(consumed or 0)),
        granted_30d=int(granted or 0),
        transactions=[CreditTransactionOut.model_validate(t) for t in rows],
    )


# ------------------------------------------------------------------ usage ---

class UsageSummary(BaseModel):
    """§41 / §105 — what the dashboard header and billing page show."""

    generations_total: int
    generations_succeeded: int
    generations_failed: int
    success_rate: float
    avg_duration_ms: int | None
    gpu_seconds: float
    storage_used_bytes: int
    storage_quota_bytes: int
    credits_balance: int
    by_type: dict[str, int]


@router.get("/usage", response_model=UsageSummary)
async def usage_summary(
    session: DbSession,
    principal: CurrentPrincipal,
    days: int = Query(default=30, ge=1, le=365),
) -> UsageSummary:
    since = utcnow() - timedelta(days=days)
    scope = [
        GenerationJob.organization_id == principal.organization_id,
        GenerationJob.created_at >= since,
    ]

    total = int(await session.scalar(select(func.count(GenerationJob.id)).where(*scope)) or 0)
    ok = int(
        await session.scalar(
            select(func.count(GenerationJob.id)).where(
                *scope, GenerationJob.status == JobStatus.COMPLETED
            )
        )
        or 0
    )
    failed = int(
        await session.scalar(
            select(func.count(GenerationJob.id)).where(
                *scope, GenerationJob.status == JobStatus.FAILED
            )
        )
        or 0
    )
    avg_ms = await session.scalar(
        select(func.avg(GenerationJob.duration_ms)).where(
            *scope, GenerationJob.status == JobStatus.COMPLETED
        )
    )
    gpu_s = await session.scalar(select(func.sum(GenerationJob.gpu_seconds)).where(*scope))

    by_type_rows = await session.execute(
        select(GenerationJob.type, func.count(GenerationJob.id))
        .where(*scope)
        .group_by(GenerationJob.type)
    )

    return UsageSummary(
        generations_total=total,
        generations_succeeded=ok,
        generations_failed=failed,
        success_rate=round(ok / total, 4) if total else 0.0,
        avg_duration_ms=int(avg_ms) if avg_ms else None,
        gpu_seconds=float(gpu_s or 0.0),
        storage_used_bytes=principal.organization.storage_used_bytes,
        storage_quota_bytes=principal.organization.storage_quota_mb * 1024 * 1024,
        credits_balance=principal.organization.credit_balance,
        by_type={str(t): c for t, c in by_type_rows},
    )


# ---------------------------------------------------------- notifications ---

class NotificationOut(ORMModel):
    id: uuid.UUID
    type: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


@router.get("/notifications", response_model=Page[NotificationOut])
async def list_notifications(
    session: DbSession,
    principal: CurrentPrincipal,
    unread_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[NotificationOut]:
    from app.models import Notification

    conditions = [Notification.user_id == principal.user_id]
    if unread_only:
        conditions.append(Notification.read_at.is_(None))

    total = int(
        await session.scalar(select(func.count(Notification.id)).where(*conditions)) or 0
    )
    rows = await session.scalars(
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[NotificationOut](
        items=[NotificationOut.model_validate(n) for n in rows],
        total=total, page=page, page_size=page_size,
    )


@router.post("/notifications/read-all")
async def mark_all_read(session: DbSession, principal: CurrentPrincipal) -> dict[str, int]:
    from app.models import Notification

    rows = await session.scalars(
        select(Notification).where(
            Notification.user_id == principal.user_id, Notification.read_at.is_(None)
        )
    )
    now = utcnow()
    count = 0
    for row in rows:
        row.read_at = now
        count += 1
    return {"marked": count}

