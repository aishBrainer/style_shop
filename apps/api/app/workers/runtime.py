"""Worker runtime: job lifecycle, asset I/O and heartbeats.

Everything a Celery task needs that is *not* AI. Tasks in `app.queue.tasks`
stay thin — open a JobContext, call a pipeline, hand back images (§92: no
thousand-line endpoints, and no thousand-line tasks either).
"""

from __future__ import annotations

import traceback
import uuid
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.device import device_info, empty_cache
from app.ai.registry import loaded_engines
from app.core.errors import AIError, AppError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import worker_session
from app.models import (
    Asset,
    CreditTransaction,
    GenerationJob,
    Notification,
    Organization,
    WorkerHeartbeat,
)
from app.models.enums import (
    JOB_STATUS_LABEL,
    JOB_STATUS_PROGRESS,
    AssetStatus,
    AssetType,
    CreditReason,
    JobStatus,
    NotificationType,
)
from app.queue.events import publish_job_event
from app.services import imaging
from app.storage.keys import asset_key
from app.storage.s3 import get_storage

log = get_logger(__name__)


# --------------------------------------------------------------- heartbeat --

def register_heartbeat(worker_name: str, queues: list[str]) -> None:
    """§63 — one row per worker, upserted so the admin GPU page has live data."""
    import socket

    info = device_info()
    try:
        with worker_session() as session:
            row = session.scalar(
                select(WorkerHeartbeat).where(WorkerHeartbeat.worker_name == worker_name)
            )
            if row is None:
                row = WorkerHeartbeat(worker_name=worker_name)
                session.add(row)

            row.queues = queues
            row.hostname = socket.gethostname()
            row.device = info.device
            row.gpu_name = info.gpu_name
            row.vram_total_mb = info.vram_total_mb
            row.vram_used_mb = info.vram_used_mb
            row.gpu_utilization = info.utilization
            row.loaded_models = loaded_engines()
            row.last_seen_at = utcnow()
    except Exception as exc:  # noqa: BLE001 — monitoring never breaks work
        log.warning("worker.heartbeat_failed", error=str(exc))


def preload_engines(queues: list[str]) -> None:
    """§51 — pay the load cost at start-up so the first user does not.

    Failures are logged, not raised: a worker that cannot load its model should
    still start, report unhealthy, and let jobs fail with a clear error rather
    than crash-looping and taking the queue with it.
    """
    from app.ai.registry import get_engine
    from app.models.enums import AIModelType

    wanted: list[AIModelType] = []
    if "vton" in queues:
        wanted += [AIModelType.VTON, AIModelType.SEGMENTATION]
    if "image" in queues:
        wanted += [AIModelType.IMAGE_GENERATION, AIModelType.SEGMENTATION, AIModelType.UPSCALE]
    if "cpu" in queues:
        wanted += [AIModelType.SEGMENTATION]
    if "video" in queues:
        wanted += [AIModelType.VIDEO]

    for engine_type in dict.fromkeys(wanted):
        try:
            get_engine(engine_type)
        except Exception as exc:  # noqa: BLE001
            log.error("worker.preload_failed", engine=str(engine_type), error=str(exc))


# ------------------------------------------------------------ job lifecycle --

class JobContext:
    """Owns one job's status transitions, progress events and failure mapping."""

    def __init__(self, session: Session, job: GenerationJob, worker_name: str | None) -> None:
        self.session = session
        self.job = job
        self.worker_name = worker_name
        self.storage = get_storage()

    # --- progress ---------------------------------------------------------
    def set_status(self, status: JobStatus, *, progress: int | None = None) -> None:
        self.job.status = status
        self.job.progress = (
            progress if progress is not None else JOB_STATUS_PROGRESS.get(status, 0)
        )
        self.job.stage_label = JOB_STATUS_LABEL.get(status)
        self.session.flush()
        self._publish(f"job.{status.value}")

    def progress(self, percent: int, label: str) -> None:
        """Called from deep inside the pipelines. Writes are cheap enough at
        this cadence, and the SSE stream is what the UI actually reads."""
        self.job.progress = max(0, min(99, percent))
        self.job.stage_label = label
        self.session.flush()
        self._publish("job.progress")

    def _publish(self, event: str) -> None:
        publish_job_event(
            event,
            self.job.id,
            user_id=self.job.user_id,
            payload={
                "status": self.job.status,
                "progress": self.job.progress,
                "stage": self.job.stage_label,
                "type": self.job.type,
                "project_id": str(self.job.project_id) if self.job.project_id else None,
            },
        )

    # --- inputs -----------------------------------------------------------
    def load_image(self, asset_id: uuid.UUID | str | None) -> Image.Image | None:
        if asset_id is None:
            return None
        asset = self.session.get(Asset, uuid.UUID(str(asset_id)))
        if asset is None:
            return None
        # §61: a worker must not read across tenants either, even though the
        # job row was authorised at creation time.
        if asset.organization_id != self.job.organization_id:
            log.error(
                "worker.cross_tenant_asset_blocked",
                job_id=str(self.job.id),
                asset_id=str(asset_id),
            )
            return None
        return imaging.load(self.storage.get(asset.storage_key))

    def require_image(self, asset_id: uuid.UUID | str | None, what: str) -> Image.Image:
        img = self.load_image(asset_id)
        if img is None:
            raise AIError(f"The {what} image is missing or unreadable.", code="INVALID_IMAGE")
        return img

    # --- outputs ----------------------------------------------------------
    def save_image(
        self,
        image: Image.Image,
        *,
        mime_type: str = "image/png",
        asset_type: AssetType = AssetType.GENERATED_IMAGE,
        filename: str | None = None,
        params: dict[str, Any] | None = None,
        watermark: bool = False,
    ) -> Asset:
        if watermark:
            image = imaging.apply_watermark(image)

        data = imaging.encode(image, mime_type)
        info = imaging.sniff(data)
        preview, thumbnail = imaging.make_renditions(data)

        asset_id = uuid.uuid4()
        org_id = self.job.organization_id
        original_key = asset_key(org_id, asset_type, asset_id, "original", mime_type)
        preview_key = asset_key(org_id, asset_type, asset_id, "preview", "image/webp")
        thumb_key = asset_key(org_id, asset_type, asset_id, "thumbnail", "image/webp")

        self.storage.put(original_key, data, mime_type, metadata={"job": str(self.job.id)})
        self.storage.put(preview_key, preview, "image/webp")
        self.storage.put(thumb_key, thumbnail, "image/webp")

        asset = Asset(
            id=asset_id,
            organization_id=org_id,
            project_id=self.job.project_id,
            owner_id=self.job.user_id,
            type=asset_type,
            status=AssetStatus.READY,
            filename=filename or f"{self.job.type}-{asset_id.hex[:8]}.{mime_type.split('/')[-1]}",
            mime_type=mime_type,
            size_bytes=info.size_bytes,
            width=info.width,
            height=info.height,
            storage_key=original_key,
            preview_key=preview_key,
            thumbnail_key=thumb_key,
            checksum_sha256=info.checksum_sha256,
            generation_job_id=self.job.id,
            ai_model_key=self.job.ai_model_key,
            generation_params=params or self.job.params,
            has_watermark=watermark,
        )
        self.session.add(asset)
        self.session.flush()

        org = self.session.get(Organization, org_id)
        if org is not None:
            org.storage_used_bytes += info.size_bytes + len(preview) + len(thumbnail)

        return asset

    def complete(self, assets: list[Asset], *, result_metadata: dict[str, Any] | None = None) -> None:
        self.job.output_asset_ids = [str(a.id) for a in assets]
        if assets:
            self.job.primary_output_asset_id = assets[0].id
        if result_metadata:
            self.job.quality_checks = result_metadata.get("quality_checks")
            gpu_seconds = result_metadata.get("gpu_seconds")
            if gpu_seconds is not None:
                self.job.gpu_seconds = gpu_seconds
            peak = result_metadata.get("peak_vram_mb")
            if peak is not None:
                self.job.peak_vram_mb = peak

        self.job.completed_at = utcnow()
        if self.job.started_at:
            delta = self.job.completed_at - self.job.started_at
            self.job.duration_ms = int(delta.total_seconds() * 1000)

        self.set_status(JobStatus.COMPLETED, progress=100)
        self._notify(
            NotificationType.GENERATION_COMPLETED,
            "Your image is ready",
            f"Your {self.job.type.replace('_', ' ')} generation finished.",
        )

    def fail(self, exc: Exception) -> None:
        code, message, retryable = _classify_error(exc)

        self.job.error_code = code
        self.job.error_message = message  # user-safe (§64)
        self.job.error_detail = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[:8000]
        self.job.completed_at = utcnow()
        if self.job.started_at:
            delta = self.job.completed_at - self.job.started_at
            self.job.duration_ms = int(delta.total_seconds() * 1000)

        self.set_status(JobStatus.FAILED, progress=100)

        # Refund and notify only once the job has genuinely given up. Refunding
        # on an attempt that Celery will retry would hand the credit back while
        # the work still runs — the user gets the image for free, and a flaky
        # model becomes a way to farm credits.
        if not self.job.can_retry:
            self.refund_credits()
            self._notify(
                NotificationType.GENERATION_FAILED,
                "Generation failed",
                message,
            )

        log.error(
            "job.failed",
            job_id=str(self.job.id),
            job_type=self.job.type,
            error_code=code,
            retryable=retryable,
            retry_count=self.job.retry_count,
        )

    def refund_credits(self) -> None:
        """§40 — a user is never charged for a generation they did not receive.

        The unique constraint on (generation_job_id, reason) makes this safe to
        call more than once.
        """
        if self.job.credits_refunded or self.job.credits_cost <= 0:
            return

        org = self.session.get(Organization, self.job.organization_id)
        if org is None:
            return

        org.credit_balance += self.job.credits_cost
        self.session.add(
            CreditTransaction(
                organization_id=org.id,
                user_id=self.job.user_id,
                generation_job_id=self.job.id,
                amount=self.job.credits_cost,
                balance_after=org.credit_balance,
                reason=CreditReason.REFUND_FAILED_JOB,
                description=f"Refund for failed {self.job.type} job",
            )
        )
        self.job.credits_refunded = True

    def _notify(self, type_: NotificationType, title: str, body: str) -> None:
        if self.job.user_id is None:
            return
        self.session.add(
            Notification(
                user_id=self.job.user_id,
                organization_id=self.job.organization_id,
                type=type_,
                title=title,
                body=body,
                link=f"/creations?job={self.job.id}",
                meta={"job_id": str(self.job.id)},
            )
        )


@contextmanager
def run_job(job_id: str, worker_name: str | None = None):
    """Open a job for processing.

    Handles: cancellation checks, status transitions, error mapping, credit
    refunds and VRAM cleanup. The task body only has to produce images.

    Yields None when there is nothing to do (job missing, or cancelled while it
    waited in the queue). Callers must check — a context manager that returned
    without yielding would raise RuntimeError instead.
    """
    with worker_session() as session:
        job = session.get(GenerationJob, uuid.UUID(str(job_id)))
        if job is None:
            # Do not raise: retrying cannot conjure a deleted row, and a failed
            # task here would just churn the queue.
            log.error("job.not_found", job_id=job_id)
            yield None
            return

        # A user may have cancelled while the job sat in the queue.
        if job.status == JobStatus.CANCELLED:
            log.info("job.skipped_cancelled", job_id=job_id)
            yield None
            return

        job.worker_name = worker_name
        job.started_at = utcnow()
        job.max_retries = job.max_retries or 2

        ctx = JobContext(session, job, worker_name)
        ctx.set_status(JobStatus.VALIDATING)

        try:
            yield ctx
        except Exception as exc:  # noqa: BLE001 — every failure mode is a job failure
            ctx.fail(exc)
            raise
        finally:
            empty_cache()  # §52


def _classify_error(exc: Exception) -> tuple[str, str, bool]:
    """Map an exception to (error_code, user-safe message, retryable) — §64."""
    if isinstance(exc, AIError):
        return exc.code, exc.message, exc.retryable
    if isinstance(exc, AppError):
        return exc.code, exc.message, False

    name = type(exc).__name__
    text = str(exc).lower()

    if "out of memory" in text or name == "OutOfMemoryError":
        return (
            "GPU_OUT_OF_MEMORY",
            "The server ran out of GPU memory. Try a smaller output size.",
            True,
        )
    if "SoftTimeLimitExceeded" in name or "TimeLimitExceeded" in name:
        return "MODEL_TIMEOUT", "Generation took too long and was stopped.", True

    return (
        "UNKNOWN_MODEL_ERROR",
        "Something went wrong during generation. Please try again.",
        True,
    )


def stale_cutoff(minutes: int = 30):
    return utcnow() - timedelta(minutes=minutes)
