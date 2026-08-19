"""Registration, login, sessions and account lifecycle (§7).

Deviation from §7 worth stating: the spec suggests Better Auth / Auth.js on the
Next.js side. This implementation keeps auth in FastAPI instead, because FastAPI
owns every row the session authorises. Splitting session ownership across two
runtimes means two places to check organization scoping (§61) — the exact class
of bug multi-tenancy least tolerates. Next.js holds the httpOnly cookie and
proxies; it never mints identity.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import timedelta

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    new_opaque_token,
    verify_password,
)
from app.db.base import utcnow
from app.models import Membership, Organization, RefreshSession, User
from app.models.enums import CreditReason, MembershipRole, PlanTier, UserRole
from app.services import credits

log = get_logger(__name__)


# --------------------------------------------------------------- registration --

async def register(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
) -> tuple[User, Organization]:
    email = email.strip().lower()

    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ConflictError("An account with that email already exists.")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=UserRole.USER,
    )
    session.add(user)
    await session.flush()

    org = await create_personal_organization(session, user, full_name or email)
    user.default_organization_id = org.id
    await session.flush()

    log.info("auth.registered", user_id=str(user.id))
    return user, org


async def create_personal_organization(
    session: AsyncSession, user: User, label: str
) -> Organization:
    """§60 — every user gets an org immediately, so nothing is ever unscoped."""
    limits = credits.PLAN_LIMITS[PlanTier.FREE]
    org = Organization(
        name=_display_name(label),
        slug=await _unique_slug(session, label),
        is_personal=True,
        plan=PlanTier.FREE,
        credit_balance=0,
        **limits,
    )
    session.add(org)
    await session.flush()

    session.add(
        Membership(
            user_id=user.id,
            organization_id=org.id,
            role=MembershipRole.OWNER,
            accepted_at=utcnow(),
        )
    )
    await session.flush()

    await credits.grant(
        session,
        org.id,
        credits.SIGNUP_GRANT,
        reason=CreditReason.SIGNUP_GRANT,
        user_id=user.id,
        description="Welcome credits",
    )
    return org


# ---------------------------------------------------------------------- login --

async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    email = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == email))

    # Hash even when the user does not exist, so response timing does not
    # reveal which emails are registered.
    if user is None or not user.hashed_password:
        hash_password(password)
        raise UnauthorizedError("Incorrect email or password.")

    if not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Incorrect email or password.")

    _assert_usable(user)

    user.last_login_at = utcnow()
    await session.flush()
    return user


async def authenticate_google(
    session: AsyncSession, *, google_sub: str, email: str, name: str | None, picture: str | None
) -> tuple[User, Organization | None]:
    email = email.strip().lower()

    user = await session.scalar(select(User).where(User.google_sub == google_sub))
    org: Organization | None = None

    if user is None:
        # Link to an existing password account with the same address. Safe
        # because Google has already verified ownership of that address.
        user = await session.scalar(select(User).where(User.email == email))
        if user is not None:
            user.google_sub = google_sub
        else:
            user = User(
                email=email,
                google_sub=google_sub,
                full_name=name,
                avatar_url=picture,
                email_verified_at=utcnow(),
                role=UserRole.USER,
            )
            session.add(user)
            await session.flush()
            org = await create_personal_organization(session, user, name or email)
            user.default_organization_id = org.id

    _assert_usable(user)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    user.last_login_at = utcnow()
    await session.flush()
    return user, org


def _assert_usable(user: User) -> None:
    if user.deleted_at is not None:
        raise UnauthorizedError("Incorrect email or password.")
    if user.is_blocked:
        raise ForbiddenError(
            user.blocked_reason or "This account has been suspended.",
            code="ACCOUNT_BLOCKED",
        )
    if not user.is_active:
        raise ForbiddenError("This account is not active.", code="ACCOUNT_INACTIVE")


# ------------------------------------------------------------------- sessions --

async def issue_tokens(
    session: AsyncSession,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """Returns (access_token, refresh_token).

    Only a hash of the refresh token is persisted, so a database leak does not
    hand out live sessions.
    """
    access = create_token(str(user.id), "access", extra={"role": user.role})

    raw_refresh = new_opaque_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            token_hash=_hash_token(raw_refresh),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:400] or None,
            ip_address=(ip_address or "")[:64] or None,
        )
    )
    await session.flush()
    return access, raw_refresh


async def rotate_refresh_token(
    session: AsyncSession,
    raw_refresh: str,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[User, str, str]:
    """Exchange a refresh token for a new pair, revoking the old one.

    Rotation means a stolen token is usable at most once — and the legitimate
    holder's next refresh fails loudly rather than silently sharing a session.
    """
    record = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == _hash_token(raw_refresh))
    )
    if record is None or not record.is_active:
        raise UnauthorizedError("Your session has expired. Please sign in again.")

    user = await session.get(User, record.user_id)
    if user is None:
        raise UnauthorizedError("Your session has expired. Please sign in again.")
    _assert_usable(user)

    record.revoked_at = utcnow()
    access, new_refresh = await issue_tokens(
        session, user, user_agent=user_agent, ip_address=ip_address
    )
    return user, access, new_refresh


async def revoke_refresh_token(session: AsyncSession, raw_refresh: str) -> None:
    record = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == _hash_token(raw_refresh))
    )
    if record is not None and record.revoked_at is None:
        record.revoked_at = utcnow()
        await session.flush()


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    rows = await session.scalars(
        select(RefreshSession).where(
            RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None)
        )
    )
    count = 0
    for row in rows:
        row.revoked_at = utcnow()
        count += 1
    await session.flush()
    return count


async def resolve_access_token(session: AsyncSession, token: str) -> User:
    try:
        payload = decode_token(token, "access")
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Your session has expired.", code="TOKEN_EXPIRED") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid authentication token.") from exc

    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise UnauthorizedError("Invalid authentication token.")
    _assert_usable(user)
    return user


# -------------------------------------------------- email verify / password --

def make_email_verify_token(user: User) -> str:
    return create_token(str(user.id), "verify_email", extra={"email": user.email})


async def confirm_email(session: AsyncSession, token: str) -> User:
    try:
        payload = decode_token(token, "verify_email")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("That verification link is invalid or has expired.") from exc

    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise UnauthorizedError("That verification link is invalid or has expired.")

    # Address changed since the link was sent — the token no longer proves
    # ownership of the current address.
    if payload.get("email") != user.email:
        raise UnauthorizedError("That verification link is no longer valid.")

    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        await session.flush()
    return user


def make_password_reset_token(user: User) -> str:
    # Binding the token to the current password hash makes it single-use: once
    # the password changes, the hash changes and any outstanding token dies.
    fingerprint = hashlib.sha256((user.hashed_password or "").encode()).hexdigest()[:16]
    return create_token(str(user.id), "reset_password", extra={"fp": fingerprint})


async def reset_password(session: AsyncSession, token: str, new_password: str) -> User:
    try:
        payload = decode_token(token, "reset_password")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("That reset link is invalid or has expired.") from exc

    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise UnauthorizedError("That reset link is invalid or has expired.")

    fingerprint = hashlib.sha256((user.hashed_password or "").encode()).hexdigest()[:16]
    if not secrets.compare_digest(payload.get("fp", ""), fingerprint):
        raise UnauthorizedError("That reset link has already been used.")

    user.hashed_password = hash_password(new_password)
    await session.flush()
    await revoke_all_sessions(session, user.id)  # force re-login everywhere
    return user


async def change_password(
    session: AsyncSession, user: User, current: str, new: str
) -> None:
    if not user.hashed_password or not verify_password(current, user.hashed_password):
        raise UnauthorizedError("Your current password is incorrect.")
    user.hashed_password = hash_password(new)
    await session.flush()
    await revoke_all_sessions(session, user.id)


# ------------------------------------------------------------------ deletion --

async def delete_account(session: AsyncSession, user: User) -> None:
    """§102 — soft delete plus session revocation.

    Bytes are removed by the retention sweep, which gives a window to reverse an
    accidental deletion. The email is scrambled immediately so the address can
    be reused for a new signup.
    """
    now = utcnow()
    user.deleted_at = now
    user.is_active = False
    user.email = f"deleted+{user.id.hex[:12]}@deleted.invalid"
    user.hashed_password = None
    user.google_sub = None
    user.full_name = None
    user.avatar_url = None

    memberships = await session.scalars(
        select(Membership).where(Membership.user_id == user.id)
    )
    for membership in memberships:
        org = await session.get(Organization, membership.organization_id)
        # Only tear down personal orgs. A shared org belongs to its other
        # members and must outlive any one of them leaving.
        if org is not None and org.is_personal:
            org.deleted_at = now

    await revoke_all_sessions(session, user.id)
    await session.flush()
    log.info("auth.account_deleted", user_id=str(user.id))


# ---------------------------------------------------------------- internals --

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _display_name(label: str) -> str:
    base = label.split("@")[0].replace(".", " ").replace("_", " ").strip()
    return f"{base.title()}'s Studio" if base else "My Studio"


async def _unique_slug(session: AsyncSession, label: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", label.split("@")[0].lower()).strip("-")[:40] or "studio"
    for _ in range(8):
        candidate = f"{base}-{secrets.token_hex(3)}"
        exists = await session.scalar(select(Organization.id).where(Organization.slug == candidate))
        if exists is None:
            return candidate
    return f"studio-{uuid.uuid4().hex[:12]}"
