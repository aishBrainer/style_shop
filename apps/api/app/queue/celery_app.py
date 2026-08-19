"""Celery application (§19).

Queue-per-engine routing (§49) so a slow video job cannot starve the try-on
queue and each worker type scales independently.
"""

from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_shutdown, worker_ready

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.models.enums import JobType

configure_logging(settings.log_level, json_output=settings.environment != "development")
log = get_logger(__name__)

celery = Celery(
    "ai_fashion_studio",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.queue.tasks", "app.queue.maintenance"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Acknowledge only after completion so a killed worker's job is redelivered
    # rather than silently lost.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # One job at a time per process: a GPU worker holding two diffusion jobs
    # concurrently is how you OOM a card (§52).
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,  # bounds any slow VRAM/host-memory leak
    task_time_limit=settings.job_timeout_seconds + 120,
    task_soft_time_limit=settings.job_timeout_seconds,
    result_expires=86400,
    broker_connection_retry_on_startup=True,
    task_default_queue="cpu",
)

#: Job type → queue. Anything unlisted lands on "cpu".
QUEUE_FOR_JOB_TYPE: dict[JobType, str] = {
    JobType.VTON: "vton",
    JobType.MODEL_SWAP: "vton",
    JobType.POSE: "vton",
    JobType.BACKGROUND_REPLACE: "image",
    JobType.PRODUCT_PHOTOGRAPHY: "image",
    JobType.INPAINT: "image",
    JobType.OBJECT_REMOVE: "image",
    JobType.EXPAND: "image",
    JobType.UPSCALE: "image",
    JobType.VIDEO: "video",
    JobType.BACKGROUND_REMOVE: "cpu",
    JobType.ENHANCE: "cpu",
    JobType.AD_CREATIVE: "cpu",
}


def queue_for(job_type: JobType | str) -> str:
    try:
        return QUEUE_FOR_JOB_TYPE.get(JobType(job_type), "cpu")
    except ValueError:
        return "cpu"


celery.conf.beat_schedule = {
    # §64: a worker that dies mid-job leaves the row PROCESSING forever.
    "reap-stale-jobs": {
        "task": "app.queue.maintenance.reap_stale_jobs",
        "schedule": 120.0,
    },
    # §41 rollup for the analytics pages.
    "rollup-usage": {
        "task": "app.queue.maintenance.rollup_usage",
        "schedule": 3600.0,
    },
    # §102 retention sweep for soft-deleted assets.
    "purge-deleted-assets": {
        "task": "app.queue.maintenance.purge_deleted_assets",
        "schedule": 86400.0,
    },
}


def _consumed_queues(sender) -> list[str]:
    """Which queues this worker was started with.

    Celery exposes this in more than one place depending on version and
    transport, so probe rather than assume, and fall back to the default queue
    instead of failing start-up over a monitoring detail.
    """
    for path in ("consumer.task_consumer.queues", "app.amqp.queues"):
        node = sender
        for part in path.split("."):
            node = getattr(node, part, None)
            if node is None:
                break
        if node:
            try:
                names = []
                for q in node:
                    names.append(q.name if hasattr(q, "name") else str(q))
                return sorted(set(names))
            except TypeError:
                return sorted(node)
    return ["cpu"]


@worker_ready.connect
def _on_worker_ready(sender=None, **_kwargs):
    """§51 — load weights at start-up, not on the first request."""
    from app.workers.runtime import preload_engines, register_heartbeat

    queues = _consumed_queues(sender)
    log.info("worker.ready", worker=sender.hostname, queues=queues)
    register_heartbeat(sender.hostname, queues)
    preload_engines(queues)


@worker_process_shutdown.connect
def _on_worker_shutdown(**_kwargs):
    """§52 — free VRAM deterministically instead of relying on process exit."""
    from app.ai.registry import unload_all

    log.info("worker.shutdown")
    unload_all()
