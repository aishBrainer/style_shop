"""Job event bus (§57).

Workers publish to Redis pub/sub; the API's SSE endpoint subscribes and relays
to the browser. Redis is the fan-out point precisely because the worker and the
API are different processes on potentially different machines.

Events (§57):
    job.created  job.queued  job.processing  job.progress
    job.completed  job.failed  job.cancelled
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import redis
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

#: Per-user channel. One subscription serves every job that user owns, so the
#: studio does not need a socket per generation.
USER_CHANNEL = "events:user:{user_id}"
JOB_CHANNEL = "events:job:{job_id}"

_sync_client: redis.Redis | None = None


def _client() -> redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _sync_client


def publish_job_event(
    event: str,
    job_id: uuid.UUID | str,
    *,
    user_id: uuid.UUID | str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget. A failed publish must never fail the job — the client
    falls back to polling GET /jobs/{id}."""
    message = json.dumps(
        {"event": event, "job_id": str(job_id), "data": payload or {}},
        default=str,
    )
    try:
        client = _client()
        client.publish(JOB_CHANNEL.format(job_id=job_id), message)
        if user_id:
            client.publish(USER_CHANNEL.format(user_id=user_id), message)
    except Exception as exc:  # noqa: BLE001
        log.warning("events.publish_failed", event=event, job_id=str(job_id), error=str(exc))


async def subscribe(channel: str):
    """Async generator of decoded messages for the SSE endpoint."""
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for raw in pubsub.listen():
            if raw.get("type") != "message":
                continue
            try:
                yield json.loads(raw["data"])
            except (json.JSONDecodeError, TypeError):
                continue
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()


# ------------------------------------------------------------ queue depth ---

def queue_position(job_id: uuid.UUID | str, queue_name: str) -> int | None:
    """Approximate position in the Celery list (§93: "Position #3").

    Celery stores a queue as a Redis list of serialised messages, so this is a
    scan rather than a lookup. Capped at 200 entries — beyond that the exact
    number stops being useful to a user anyway.
    """
    try:
        client = _client()
        entries = client.lrange(queue_name, 0, 199)
    except Exception as exc:  # noqa: BLE001
        log.warning("events.queue_position_failed", error=str(exc))
        return None

    needle = str(job_id)
    for index, entry in enumerate(entries):
        if needle in entry:
            return index + 1
    return None


def queue_depth(queue_name: str) -> int:
    try:
        return int(_client().llen(queue_name))
    except Exception:  # noqa: BLE001
        return 0
