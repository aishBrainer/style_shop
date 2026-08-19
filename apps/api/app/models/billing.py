"""Credits and subscriptions (§40, §41).

The credit ledger exists from day one even though billing is inactive, so
turning monetisation on later is a config change rather than a schema change.
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.models.enums import CreditReason, PlanTier, SubscriptionStatus


class CreditTransaction(Base, UUIDPrimaryKey, Timestamped):
    """Append-only ledger. `amount` is positive for grants, negative for spend."""

    __tablename__ = "credit_transactions"
    __table_args__ = (
        Index("ix_credit_org_created", "organization_id", "created_at"),
        # One debit per job — makes the charge idempotent under worker retries.
        UniqueConstraint("generation_job_id", "reason", name="uq_credit_job_reason"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    generation_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True
    )

    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[CreditReason] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(400), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Subscription(Base, UUIDPrimaryKey, Timestamped):
    """Placeholder for a future payment provider (§87). Nothing charges yet."""

    __tablename__ = "subscriptions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True, unique=True,
    )
    plan: Mapped[PlanTier] = mapped_column(String(32), default=PlanTier.FREE, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        String(32), default=SubscriptionStatus.ACTIVE, nullable=False, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class UsageDaily(Base, UUIDPrimaryKey, Timestamped):
    """§41 rollup, written by the nightly beat task. Keeps analytics queries
    off the generation_jobs hot path."""

    __tablename__ = "usage_daily"
    __table_args__ = (
        UniqueConstraint("organization_id", "day", name="uq_usage_org_day"),
        Index("ix_usage_day", "day"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)

    generations_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generations_succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generations_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gpu_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    downloads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
