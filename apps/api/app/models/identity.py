"""Users, organizations, memberships and sessions (§60 multi-tenancy)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDelete, Timestamped, UUIDPrimaryKey
from app.models.enums import MembershipRole, PlanTier, UserRole


class User(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        String(32), default=UserRole.USER, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # OAuth (§7). Null for password accounts.
    google_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # The org created for this user at signup. Every user has exactly one
    # personal org so that all data is org-scoped from day one (§60).
    default_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )

    # No ORM relationships anywhere in this schema. Under an async session a
    # lazily-loaded relationship raises MissingGreenlet the moment anything
    # touches it — including Pydantic's from_attributes walk. Every read here
    # loads what it needs explicitly, and ON DELETE CASCADE on the foreign keys
    # gives the same integrity guarantees at the database level.

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None


class Organization(Base, UUIDPrimaryKey, Timestamped, SoftDelete):
    """The tenant boundary. Every scoped table carries `organization_id` (§61)."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    is_personal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    plan: Mapped[PlanTier] = mapped_column(
        String(32), default=PlanTier.FREE, nullable=False, index=True
    )

    # Denormalised running balance. The authoritative history is the
    # credit_transactions ledger; this column is the cached sum (§40).
    credit_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Quotas, resolved from the plan at creation time so a plan change is an
    # explicit action rather than a silent retroactive one.
    storage_quota_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    # BigInteger: a 4-byte column tops out at ~2.1 GB, which a single active
    # organization will exceed.
    storage_used_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    max_projects: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_concurrent_jobs: Mapped[int] = mapped_column(Integer, default=1, nullable=False)



class Membership(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
        Index("ix_membership_org_role", "organization_id", "role"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[MembershipRole] = mapped_column(
        String(32), default=MembershipRole.MEMBER, nullable=False
    )
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def can_write(self) -> bool:
        return self.role != MembershipRole.VIEWER

    @property
    def can_manage(self) -> bool:
        return self.role in {MembershipRole.OWNER, MembershipRole.ADMIN}


class RefreshSession(Base, UUIDPrimaryKey, Timestamped):
    """Server-side record of an issued refresh token, so logout can revoke it.

    Stores only a hash — a leaked table dump must not yield usable tokens.
    """

    __tablename__ = "refresh_sessions"
    __table_args__ = (Index("ix_refresh_user_active", "user_id", "revoked_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    @property
    def is_active(self) -> bool:
        from app.db.base import utcnow

        return self.revoked_at is None and self.expires_at > utcnow()
