"""Notifications, audit logs, settings, feature flags and worker heartbeats."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.models.enums import NotificationType


class Notification(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_user_read", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[NotificationType] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(700), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class AuditLog(Base, UUIDPrimaryKey, Timestamped):
    """§58. Append-only; never updated or deleted by application code."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_org_created", "organization_id", "created_at"),
        Index("ix_audit_actor_created", "actor_id", "created_at"),
        Index("ix_audit_action", "action", "created_at"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class SystemSetting(Base, UUIDPrimaryKey, Timestamped):
    """Runtime-editable configuration the admin panel can change without a deploy."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FeatureFlag(Base, UUIDPrimaryKey, Timestamped):
    """§69 — gradual rollout without redeploying."""

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Plan tiers the flag is on for, e.g. ["pro", "business"]. Empty = all tiers.
    enabled_plans: Mapped[list[str] | None] = mapped_column(ARRAY(String(32)), nullable=True)
    # Specific orgs allow-listed regardless of plan.
    enabled_organization_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


class WorkerHeartbeat(Base, UUIDPrimaryKey, Timestamped):
    """§63 GPU monitoring. Workers upsert a row on a timer; the admin GPU page
    reads it. Rows older than a few minutes mean the worker is gone."""

    __tablename__ = "worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    queues: Mapped[list[str] | None] = mapped_column(ARRAY(String(40)), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(200), nullable=True)
    device: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gpu_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vram_total_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vram_used_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_utilization: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loaded_models: Mapped[list[str] | None] = mapped_column(ARRAY(String(120)), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
