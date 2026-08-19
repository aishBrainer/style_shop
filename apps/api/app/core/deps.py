"""FastAPI dependencies: authentication, tenancy and rate limiting."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.db.session import get_db
from app.models import Membership, Organization, User
from app.models.enums import MembershipRole
from app.services import auth_service

ACCESS_COOKIE = "afs_access"
REFRESH_COOKIE = "afs_refresh"

DbSession = Annotated[AsyncSession, Depends(get_db)]


@dataclass(slots=True)
class Principal:
    """The authenticated caller plus the tenant they are acting in."""

    user: User
    organization: Organization
    membership: Membership | None

    @property
    def organization_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def can_write(self) -> bool:
        return self.user.is_admin or (self.membership is not None and self.membership.can_write)

    @property
    def can_manage(self) -> bool:
        return self.user.is_admin or (self.membership is not None and self.membership.can_manage)


async def get_current_user(
    session: DbSession,
    access_cookie: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Cookie first (browser), bearer header second (API clients, tests)."""
    token = access_cookie
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if not token:
        raise UnauthorizedError("You need to sign in to do that.")

    return await auth_service.resolve_access_token(session, token)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_principal(
    session: DbSession,
    user: CurrentUser,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> Principal:
    """Resolve the active organization and verify membership (§61).

    The client may request an org via header; membership is always re-checked
    server-side. Frontend filtering is never the authorization boundary.
    """
    requested: uuid.UUID | None = None
    if x_organization_id:
        try:
            requested = uuid.UUID(x_organization_id)
        except ValueError as exc:
            raise ForbiddenError("Invalid organization.") from exc

    target = requested or user.default_organization_id
    if target is None:
        raise ForbiddenError("Your account is not attached to a workspace.")

    membership = await session.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.organization_id == target
        )
    )

    # Platform admins can inspect any org; everyone else needs a membership.
    if membership is None and not user.is_admin:
        raise ForbiddenError("You do not have access to that workspace.")

    org = await session.get(Organization, target)
    if org is None or org.deleted_at is not None:
        raise NotFoundError("Workspace not found.")

    return Principal(user=user, organization=org, membership=membership)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def require_write(principal: CurrentPrincipal) -> Principal:
    if not principal.can_write:
        raise ForbiddenError("Your role is read-only in this workspace.")
    return principal


WritePrincipal = Annotated[Principal, Depends(require_write)]


async def require_manager(principal: CurrentPrincipal) -> Principal:
    if not principal.can_manage:
        raise ForbiddenError("Only workspace owners and admins can do that.")
    return principal


ManagerPrincipal = Annotated[Principal, Depends(require_manager)]


async def require_admin(user: CurrentUser) -> User:
    """Platform administrator (§4.5), not workspace admin."""
    if not user.is_admin:
        raise ForbiddenError("Administrator access required.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    """Behind Cloudflare/nginx the socket peer is the proxy.

    Only trusted when a proxy is actually in front — otherwise a client can set
    X-Forwarded-For to anything and defeat per-IP rate limiting.
    """
    from app.core.config import settings

    if settings.is_production:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
