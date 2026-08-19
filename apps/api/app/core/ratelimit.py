"""Redis-backed fixed-window rate limiting (§58).

Fixed window rather than sliding: it is one INCR plus one EXPIRE, which is
cheap enough to sit in front of every login and upload. The known cost is
burstiness at window boundaries — acceptable for abuse control, not for
billing-grade quotas.
"""

from __future__ import annotations

from collections.abc import Callable

import redis.asyncio as aioredis
from fastapi import Request

from app.core.config import settings
from app.core.errors import RateLimitError
from app.core.logging import get_logger

log = get_logger(__name__)

_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def hit(key: str, limit: int, window_seconds: int) -> None:
    """Raise RateLimitError when `key` exceeds `limit` within the window.

    A Redis outage must not take authentication down with it, so failures here
    are logged and allowed through.
    """
    try:
        client = _redis()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        count, _ = await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("ratelimit.unavailable", error=str(exc))
        return

    if int(count) > limit:
        raise RateLimitError(
            f"Too many requests. Try again in about {window_seconds} seconds."
        )


def limiter(name: str, spec: tuple[int, int]) -> Callable:
    """Dependency factory. Keys on user id when signed in, IP otherwise."""
    limit, window = spec

    async def dependency(request: Request) -> None:
        from app.core.deps import ACCESS_COOKIE, client_ip

        identity = request.cookies.get(ACCESS_COOKIE)
        # The token itself is the identity key — no need to decode it here, and
        # a rotated token simply starts a fresh window.
        subject = f"t:{identity[-32:]}" if identity else f"ip:{client_ip(request)}"
        await hit(f"rl:{name}:{subject}", limit, window)

    return dependency


auth_rate_limit = limiter("auth", settings.rate_limit_auth)
upload_rate_limit = limiter("upload", settings.rate_limit_upload)
generate_rate_limit = limiter("generate", settings.rate_limit_generate)
