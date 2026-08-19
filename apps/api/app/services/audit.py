"""Audit logging (§58)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


async def record(
    session: AsyncSession,
    *,
    action: str,
    actor: User | None = None,
    organization_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | uuid.UUID | None = None,
    request: Request | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Append-only. The actor's email is denormalised so the trail survives the
    account being deleted (§102)."""
    from app.core.deps import client_ip

    session.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            ip_address=client_ip(request) if request else None,
            user_agent=(request.headers.get("user-agent") or "")[:400] if request else None,
            data=data,
        )
    )
