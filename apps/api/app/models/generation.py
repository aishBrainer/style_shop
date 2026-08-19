"""Generation jobs, the AI model registry and prompt templates (§20, §50, §68)."""

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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.models.enums import AIModelType, CommercialUse, JobStatus, JobType


class GenerationJob(Base, UUIDPrimaryKey, Timestamped):
    """One unit of AI work. §18: never executed inside an HTTP request."""

    __tablename__ = "generation_jobs"
    __table_args__ = (
        # §96: the indexes the queue and gallery actually query on.
        Index("ix_job_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_job_user_created", "user_id", "created_at"),
        Index("ix_job_status_created", "status", "created_at"),
        Index("ix_job_project", "project_id", "created_at"),
        Index("ix_job_batch", "batch_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[JobType] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(
        String(32), default=JobStatus.QUEUED, nullable=False, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage_label: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Groups the N jobs produced by one bulk request (§39).
    batch_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    # Inputs. Kept as an explicit dict rather than FKs because job types take
    # different input shapes; the FK-ish fields below cover the common ones.
    input_asset_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    model_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("model_profiles.id", ondelete="SET NULL"), nullable=True
    )
    mask_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )

    # Outputs.
    output_asset_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    primary_output_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )

    # §66: every parameter, so a generation is reproducible.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)  # §67
    ai_model_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ai_model_version: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Execution bookkeeping (§20).
    celery_task_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    worker_name: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_vram_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # §64: failure handling.
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full traceback for operators only — never serialised to a user response.
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    credits_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_refunded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # §65: automated post-generation quality checks.
    quality_checks: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    @property
    def is_terminal(self) -> bool:
        return JobStatus(self.status).is_terminal

    @property
    def can_retry(self) -> bool:
        return self.status == JobStatus.FAILED and self.retry_count < self.max_retries


class AIModel(Base, UUIDPrimaryKey, Timestamped):
    """§50 registry. One row per installed engine implementation.

    The `key` is what job records and env vars refer to (e.g. "mock", "catvton",
    "sdxl-inpaint"). Swapping the enabled row for a given type is how a model
    upgrade ships (§50) — no application code changes.
    """

    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint("key", "type", "version", name="uq_ai_model_key_type_version"),
        Index("ix_ai_model_type_enabled", "type", "enabled", "priority"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[AIModelType] = mapped_column(String(40), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(60), default="1", nullable=False)

    # Import path of the provider class, resolved at worker start-up.
    provider_class: Mapped[str] = mapped_column(String(300), nullable=False)
    weights_path: Mapped[str | None] = mapped_column(String(700), nullable=True)
    framework: Mapped[str] = mapped_column(String(60), default="pytorch", nullable=False)
    vram_requirement_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # §72 — licensing is a first-class field, not a README footnote.
    license: Mapped[str] = mapped_column(String(120), default="unknown", nullable=False)
    license_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    commercial_use: Mapped[CommercialUse] = mapped_column(
        String(32), default=CommercialUse.UNREVIEWED, nullable=False, index=True
    )
    license_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    default_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # §78 benchmark dashboard, updated by the evaluation harness.
    avg_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_vram_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_deployable(self) -> bool:
        """§72: never auto-enable a checkpoint whose licence forbids commerce."""
        return self.enabled and self.commercial_use == CommercialUse.ALLOWED


class PromptTemplate(Base, UUIDPrimaryKey, Timestamped):
    """§68 — prompts live in the database, not scattered through the code."""

    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("key", name="uq_prompt_template_key"),)

    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="background", nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    default_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
