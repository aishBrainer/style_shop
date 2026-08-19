"""Periodic maintenance run by celery beat."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update

from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import worker_session
from app.models import Asset, GenerationJob, Organization, UsageDaily
from app.models.enums import JobStatus
from app.queue.celery_app import celery
from app.queue.events import publish_job_event
from app.storage.s3 import get_storage

log = get_logger(__name__)

STALE_PROCESSING_MINUTES = 30
STALE_QUEUED_MINUTES = 120
DELETED_ASSET_RETENTION_DAYS = 30


@celery.task(name="app.queue.maintenance.reap_stale_jobs")
def reap_stale_jobs() -> dict[str, int]:
    """§64 — a worker killed mid-job leaves its row PROCESSING forever.

    Two cases: jobs that started and never finished, and jobs that never got
    picked up at all (no worker listening on that queue).
    """
    now = utcnow()
    active = [
        JobStatus.VALIDATING,
        JobStatus.PREPROCESSING,
        JobStatus.PROCESSING,
        JobStatus.POST_PROCESSING,
        JobStatus.UPLOADING,
    ]

    reaped = {"stalled": 0, "queue_timeout": 0}

    with worker_session() as session:
        stalled = session.scalars(
            select(GenerationJob).where(
                GenerationJob.status.in_(active),
                GenerationJob.started_at < now - timedelta(minutes=STALE_PROCESSING_MINUTES),
            )
        ).all()

        for job in stalled:
            job.status = JobStatus.FAILED
            job.error_code = "MODEL_TIMEOUT"
            job.error_message = "Generation stopped unexpectedly. Please try again."
            job.completed_at = now
            job.progress = 100
            _refund(session, job)
            publish_job_event(
                "job.failed", job.id, user_id=job.user_id,
                payload={"status": JobStatus.FAILED, "progress": 100},
            )
            reaped["stalled"] += 1

        abandoned = session.scalars(
            select(GenerationJob).where(
                GenerationJob.status == JobStatus.QUEUED,
                GenerationJob.created_at < now - timedelta(minutes=STALE_QUEUED_MINUTES),
            )
        ).all()

        for job in abandoned:
            job.status = JobStatus.FAILED
            job.error_code = "QUEUE_TIMEOUT"
            job.error_message = "The job waited too long in the queue and was cancelled."
            job.completed_at = now
            job.progress = 100
            _refund(session, job)
            publish_job_event(
                "job.failed", job.id, user_id=job.user_id,
                payload={"status": JobStatus.FAILED, "progress": 100},
            )
            reaped["queue_timeout"] += 1

    if reaped["stalled"] or reaped["queue_timeout"]:
        log.warning("maintenance.jobs_reaped", **reaped)
    return reaped


def _refund(session, job: GenerationJob) -> None:
    from app.models import CreditTransaction
    from app.models.enums import CreditReason

    if job.credits_refunded or job.credits_cost <= 0:
        return
    org = session.get(Organization, job.organization_id)
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
            description="Refund for reaped job",
        )
    )
    job.credits_refunded = True


@celery.task(name="app.queue.maintenance.rollup_usage")
def rollup_usage() -> dict[str, Any]:
    """§41 — aggregate today's activity per organization."""
    today = utcnow().date()
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    with worker_session() as session:
        rows = session.execute(
            select(
                GenerationJob.organization_id,
                func.count(GenerationJob.id),
                func.count(GenerationJob.id).filter(GenerationJob.status == JobStatus.COMPLETED),
                func.count(GenerationJob.id).filter(GenerationJob.status == JobStatus.FAILED),
                func.coalesce(func.sum(GenerationJob.credits_cost), 0),
                func.coalesce(func.sum(GenerationJob.gpu_seconds), 0.0),
                func.avg(GenerationJob.duration_ms),
            )
            .where(GenerationJob.created_at >= start)
            .group_by(GenerationJob.organization_id)
        ).all()

        for org_id, total, ok, failed, credits, gpu_s, avg_ms in rows:
            record = session.scalar(
                select(UsageDaily).where(
                    UsageDaily.organization_id == org_id, UsageDaily.day == today
                )
            )
            if record is None:
                record = UsageDaily(organization_id=org_id, day=today)
                session.add(record)

            org = session.get(Organization, org_id)
            record.generations_total = total
            record.generations_succeeded = ok
            record.generations_failed = failed
            record.credits_consumed = int(credits or 0)
            record.gpu_seconds = float(gpu_s or 0.0)
            record.avg_duration_ms = int(avg_ms) if avg_ms else None
            record.storage_bytes = org.storage_used_bytes if org else 0

        return {"organizations": len(rows), "day": str(today)}


@celery.task(name="app.queue.maintenance.purge_deleted_assets")
def purge_deleted_assets() -> dict[str, int]:
    """§102 — permanently remove soft-deleted assets past the retention window.

    Storage objects go first; the row is only dropped once its bytes are gone,
    so a failure here leaves a recoverable record rather than an orphan.
    """
    cutoff = utcnow() - timedelta(days=DELETED_ASSET_RETENTION_DAYS)
    storage = get_storage()
    purged = 0

    with worker_session() as session:
        assets = session.scalars(
            select(Asset).where(Asset.deleted_at.is_not(None), Asset.deleted_at < cutoff).limit(500)
        ).all()

        for asset in assets:
            keys = [k for k in (asset.storage_key, asset.preview_key, asset.thumbnail_key) if k]
            try:
                storage.delete_many(keys)
            except Exception as exc:  # noqa: BLE001
                log.warning("maintenance.purge_failed", asset_id=str(asset.id), error=str(exc))
                continue

            org = session.get(Organization, asset.organization_id)
            if org is not None:
                org.storage_used_bytes = max(0, org.storage_used_bytes - asset.size_bytes)

            session.delete(asset)
            purged += 1

    if purged:
        log.info("maintenance.assets_purged", count=purged)
    return {"purged": purged}


@celery.task(name="app.queue.maintenance.heartbeat")
def heartbeat(worker_name: str, queues: list[str]) -> None:
    from app.workers.runtime import register_heartbeat

    register_heartbeat(worker_name, queues)
