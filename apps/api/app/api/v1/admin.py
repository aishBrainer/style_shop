"""Admin panel endpoints (§63).

Platform administrators only. Every route is scoped by `AdminUser`, which
checks `users.role`, not workspace membership.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.deps import AdminUser, DbSession
from app.core.errors import NotFoundError, ValidationError
from app.db.base import utcnow
from app.models import (
    AIModel,
    Asset,
    AuditLog,
    FeatureFlag,
    GenerationJob,
    Organization,
    User,
    WorkerHeartbeat,
)
from app.models.enums import CommercialUse, CreditReason, JobStatus, PlanTier, UserRole
from app.queue.events import queue_depth
from app.schemas.common import Message, ORMModel, Page
from app.services import audit, credits

router = APIRouter(prefix="/admin", tags=["admin"])

#: How long a heartbeat stays trustworthy before a worker counts as offline.
WORKER_STALE_SECONDS = 180


# ------------------------------------------------------------- dashboard ---

class AdminStats(BaseModel):
    users_total: int
    users_active_30d: int
    organizations_total: int
    jobs_total: int
    jobs_today: int
    jobs_failed_today: int
    jobs_in_progress: int
    success_rate: float
    avg_duration_ms: int | None
    storage_bytes: int
    credits_consumed_today: int
    queue_depths: dict[str, int]


@router.get("/stats", response_model=AdminStats)
async def stats(session: DbSession, _: AdminUser) -> AdminStats:
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_ago = now - timedelta(days=30)

    active_statuses = [
        JobStatus.QUEUED, JobStatus.VALIDATING, JobStatus.PREPROCESSING,
        JobStatus.PROCESSING, JobStatus.POST_PROCESSING, JobStatus.UPLOADING,
    ]

    async def count(model, *conditions) -> int:
        return int(await session.scalar(select(func.count(model.id)).where(*conditions)) or 0)

    jobs_total = await count(GenerationJob)
    jobs_completed = await count(GenerationJob, GenerationJob.status == JobStatus.COMPLETED)
    jobs_today = await count(GenerationJob, GenerationJob.created_at >= today)

    avg_ms = await session.scalar(
        select(func.avg(GenerationJob.duration_ms)).where(
            GenerationJob.status == JobStatus.COMPLETED
        )
    )
    storage = await session.scalar(select(func.sum(Organization.storage_used_bytes)))
    spent_today = await session.scalar(
        select(func.sum(GenerationJob.credits_cost)).where(GenerationJob.created_at >= today)
    )

    return AdminStats(
        users_total=await count(User, User.deleted_at.is_(None)),
        users_active_30d=await count(User, User.last_login_at >= month_ago),
        organizations_total=await count(Organization, Organization.deleted_at.is_(None)),
        jobs_total=jobs_total,
        jobs_today=jobs_today,
        jobs_failed_today=await count(
            GenerationJob,
            GenerationJob.created_at >= today,
            GenerationJob.status == JobStatus.FAILED,
        ),
        jobs_in_progress=await count(GenerationJob, GenerationJob.status.in_(active_statuses)),
        success_rate=round(jobs_completed / jobs_total, 4) if jobs_total else 0.0,
        avg_duration_ms=int(avg_ms) if avg_ms else None,
        storage_bytes=int(storage or 0),
        credits_consumed_today=int(spent_today or 0),
        queue_depths={q: queue_depth(q) for q in ("vton", "image", "cpu", "video")},
    )


# ----------------------------------------------------------------- users ---

class AdminUserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    is_blocked: bool
    blocked_reason: str | None
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    default_organization_id: uuid.UUID | None


@router.get("/users", response_model=Page[AdminUserOut])
async def list_users(
    session: DbSession,
    _: AdminUser,
    search: str | None = None,
    blocked_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> Page[AdminUserOut]:
    conditions = [User.deleted_at.is_(None)]
    if search:
        conditions.append(User.email.ilike(f"%{search.strip()}%"))
    if blocked_only:
        conditions.append(User.is_blocked.is_(True))

    total = int(await session.scalar(select(func.count(User.id)).where(*conditions)) or 0)
    rows = await session.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[AdminUserOut](
        items=[AdminUserOut.model_validate(u) for u in rows],
        total=total, page=page, page_size=page_size,
    )


class BlockUserRequest(BaseModel):
    blocked: bool
    reason: str | None = Field(default=None, max_length=500)


@router.post("/users/{user_id}/block", response_model=AdminUserOut)
async def block_user(
    user_id: uuid.UUID, payload: BlockUserRequest, session: DbSession, admin: AdminUser
) -> AdminUserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if user.id == admin.id:
        raise ValidationError("You cannot block your own account.")

    user.is_blocked = payload.blocked
    user.blocked_reason = payload.reason if payload.blocked else None

    if payload.blocked:
        # Blocking must take effect now, not when the access token expires.
        from app.services import auth_service

        await auth_service.revoke_all_sessions(session, user.id)

    await audit.record(
        session,
        action="admin.user_blocked" if payload.blocked else "admin.user_unblocked",
        actor=admin,
        resource_type="user",
        resource_id=user.id,
        data={"reason": payload.reason},
    )
    await session.flush()
    return AdminUserOut.model_validate(user)


class GrantCreditsRequest(BaseModel):
    organization_id: uuid.UUID
    amount: int = Field(ge=-100000, le=100000)
    description: str | None = Field(default=None, max_length=400)


@router.post("/credits/grant", response_model=Message)
async def grant_credits(
    payload: GrantCreditsRequest, session: DbSession, admin: AdminUser
) -> Message:
    balance = await credits.grant(
        session,
        payload.organization_id,
        payload.amount,
        reason=CreditReason.ADMIN_ADJUSTMENT,
        user_id=admin.id,
        description=payload.description or "Manual adjustment",
    )
    await audit.record(
        session,
        action="admin.credits_adjusted",
        actor=admin,
        organization_id=payload.organization_id,
        data={"amount": payload.amount},
    )
    return Message(message=f"Balance is now {balance} credits.")


# --------------------------------------------------------- organizations ---

class AdminOrgOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: PlanTier
    credit_balance: int
    storage_used_bytes: int
    storage_quota_mb: int
    is_personal: bool
    created_at: datetime


@router.get("/organizations", response_model=Page[AdminOrgOut])
async def list_organizations(
    session: DbSession,
    _: AdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> Page[AdminOrgOut]:
    conditions = [Organization.deleted_at.is_(None)]
    total = int(
        await session.scalar(select(func.count(Organization.id)).where(*conditions)) or 0
    )
    rows = await session.scalars(
        select(Organization)
        .where(*conditions)
        .order_by(Organization.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[AdminOrgOut](
        items=[AdminOrgOut.model_validate(o) for o in rows],
        total=total, page=page, page_size=page_size,
    )


class SetPlanRequest(BaseModel):
    plan: PlanTier


@router.post("/organizations/{org_id}/plan", response_model=AdminOrgOut)
async def set_plan(
    org_id: uuid.UUID, payload: SetPlanRequest, session: DbSession, admin: AdminUser
) -> AdminOrgOut:
    org = await session.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found.")

    org.plan = payload.plan
    for field, value in credits.PLAN_LIMITS[payload.plan].items():
        setattr(org, field, value)

    await audit.record(
        session, action="admin.plan_changed", actor=admin,
        organization_id=org_id, data={"plan": str(payload.plan)},
    )
    await session.flush()
    return AdminOrgOut.model_validate(org)


# ------------------------------------------------------------------ jobs ---

class AdminJobOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    type: str
    status: JobStatus
    progress: int
    ai_model_key: str | None
    worker_name: str | None
    error_code: str | None
    error_message: str | None
    retry_count: int
    duration_ms: int | None
    gpu_seconds: float | None
    peak_vram_mb: int | None
    credits_cost: int
    created_at: datetime
    completed_at: datetime | None


@router.get("/jobs", response_model=Page[AdminJobOut])
async def list_all_jobs(
    session: DbSession,
    _: AdminUser,
    status: JobStatus | None = None,
    failed_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> Page[AdminJobOut]:
    conditions = []
    if failed_only:
        conditions.append(GenerationJob.status == JobStatus.FAILED)
    elif status is not None:
        conditions.append(GenerationJob.status == status)

    total = int(
        await session.scalar(select(func.count(GenerationJob.id)).where(*conditions)) or 0
    )
    rows = await session.scalars(
        select(GenerationJob)
        .where(*conditions)
        .order_by(GenerationJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[AdminJobOut](
        items=[AdminJobOut.model_validate(j) for j in rows],
        total=total, page=page, page_size=page_size,
    )


class JobDetailOut(AdminJobOut):
    params: dict
    error_detail: str | None  # admins only — never exposed on the user API (§64)


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
async def job_detail(job_id: uuid.UUID, session: DbSession, _: AdminUser) -> JobDetailOut:
    job = await session.get(GenerationJob, job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    return JobDetailOut.model_validate(job)


# --------------------------------------------------------------- workers ---

class WorkerOut(ORMModel):
    worker_name: str
    queues: list[str] | None
    hostname: str | None
    device: str | None
    gpu_name: str | None
    vram_total_mb: int | None
    vram_used_mb: int | None
    gpu_utilization: float | None
    active_jobs: int
    loaded_models: list[str] | None
    last_seen_at: datetime
    online: bool = True


@router.get("/workers", response_model=list[WorkerOut])
async def list_workers(session: DbSession, _: AdminUser) -> list[WorkerOut]:
    """§63 GPU monitoring."""
    rows = await session.scalars(select(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_name))
    cutoff = utcnow() - timedelta(seconds=WORKER_STALE_SECONDS)

    result = []
    for row in rows:
        out = WorkerOut.model_validate(row)
        out.online = row.last_seen_at >= cutoff
        result.append(out)
    return result


# --------------------------------------------------------- model registry ---

class AIModelOut(ORMModel):
    id: uuid.UUID
    key: str
    name: str
    type: str
    version: str
    provider_class: str
    framework: str
    vram_requirement_mb: int | None
    license: str
    license_url: str | None
    commercial_use: CommercialUse
    license_notes: str | None
    enabled: bool
    priority: int
    avg_duration_ms: int | None
    avg_vram_mb: int | None
    quality_score: float | None


@router.get("/models", response_model=list[AIModelOut])
async def list_ai_models(session: DbSession, _: AdminUser) -> list[AIModelOut]:
    """§50 registry + §78 benchmark numbers."""
    rows = await session.scalars(select(AIModel).order_by(AIModel.type, AIModel.priority))
    return [AIModelOut.model_validate(m) for m in rows]


class ToggleModelRequest(BaseModel):
    enabled: bool


@router.post("/models/{model_id}/toggle", response_model=AIModelOut)
async def toggle_ai_model(
    model_id: uuid.UUID, payload: ToggleModelRequest, session: DbSession, admin: AdminUser
) -> AIModelOut:
    model = await session.get(AIModel, model_id)
    if model is None:
        raise NotFoundError("Model not found.")

    # §72 — the guard that stops a non-commercial checkpoint being switched on
    # by a click in the admin panel.
    if payload.enabled and model.commercial_use != CommercialUse.ALLOWED:
        raise ValidationError(
            f"{model.name} is licensed {model.license}, which does not clearly "
            f"permit commercial use. Complete a licence review and update the "
            f"registry entry before enabling it. See MODEL_LICENSE.md."
        )

    model.enabled = payload.enabled
    await audit.record(
        session, action="admin.model_toggled", actor=admin,
        resource_type="ai_model", resource_id=model.id,
        data={"enabled": payload.enabled, "key": model.key},
    )
    await session.flush()
    return AIModelOut.model_validate(model)


# --------------------------------------------------------- feature flags ---

class FeatureFlagOut(ORMModel):
    id: uuid.UUID
    key: str
    description: str | None
    enabled: bool
    enabled_plans: list[str] | None
    rollout_percentage: int


class FeatureFlagUpdate(BaseModel):
    enabled: bool | None = None
    enabled_plans: list[str] | None = None
    rollout_percentage: int | None = Field(default=None, ge=0, le=100)


@router.get("/feature-flags", response_model=list[FeatureFlagOut])
async def list_flags(session: DbSession, _: AdminUser) -> list[FeatureFlagOut]:
    rows = await session.scalars(select(FeatureFlag).order_by(FeatureFlag.key))
    return [FeatureFlagOut.model_validate(f) for f in rows]


@router.patch("/feature-flags/{key}", response_model=FeatureFlagOut)
async def update_flag(
    key: str, payload: FeatureFlagUpdate, session: DbSession, admin: AdminUser
) -> FeatureFlagOut:
    flag = await session.scalar(select(FeatureFlag).where(FeatureFlag.key == key))
    if flag is None:
        raise NotFoundError("Feature flag not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(flag, field, value)

    await audit.record(
        session, action="admin.flag_updated", actor=admin,
        resource_type="feature_flag", resource_id=flag.key,
        data=payload.model_dump(exclude_unset=True),
    )
    await session.flush()
    return FeatureFlagOut.model_validate(flag)


# ------------------------------------------------------------ audit logs ---

class AuditLogOut(ORMModel):
    id: uuid.UUID
    actor_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    data: dict | None
    created_at: datetime


@router.get("/audit-logs", response_model=Page[AuditLogOut])
async def list_audit_logs(
    session: DbSession,
    _: AdminUser,
    action: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> Page[AuditLogOut]:
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)

    total = int(await session.scalar(select(func.count(AuditLog.id)).where(*conditions)) or 0)
    rows = await session.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(a) for a in rows],
        total=total, page=page, page_size=page_size,
    )

