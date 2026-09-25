from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.ai_video.core.db import Base
from app.ai_video.models.base import TimestampMixin


class GenerationIdempotencyRecord(Base, TimestampMixin):
    __tablename__ = "generation_idempotency_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "scope_type",
            "scope_id",
            "operation",
            "idempotency_key",
            name="uq_generation_idempotency_scope_key",
        ),
        Index("ix_generation_idempotency_task", "task_id"),
    )


class GenerationBatch(Base, TimestampMixin):
    __tablename__ = "generation_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="admission_pending")
    requested_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    admission: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    estimate: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["GenerationBatchItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GenerationBatchItem.created_at",
    )

    __table_args__ = (Index("ix_generation_batch_project_status", "project_id", "status", "created_at"),)


class GenerationBatchItem(Base, TimestampMixin):
    __tablename__ = "generation_batch_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("generation_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="admitted")
    task_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("generation_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    batch: Mapped["GenerationBatch"] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("batch_id", "target_type", "target_id", name="uq_generation_batch_target"),
        Index("ix_generation_batch_item_status", "batch_id", "status"),
    )


class ProviderExecutionCheckpoint(Base, TimestampMixin):
    __tablename__ = "provider_execution_checkpoints"

    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("generation_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="not_submitted")
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    external_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    poll_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    download_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_settlement_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (Index("ix_provider_checkpoint_resume", "state", "next_poll_at"),)


class UsageLedgerEntry(Base, TimestampMixin):
    __tablename__ = "usage_ledger_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("generation_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="estimated")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    estimated_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    request_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    response_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_usage_ledger_project_created", "project_id", "created_at"),
        Index("ix_usage_ledger_status", "status", "created_at"),
    )


__all__ = [
    "GenerationBatch",
    "GenerationBatchItem",
    "GenerationIdempotencyRecord",
    "ProviderExecutionCheckpoint",
    "UsageLedgerEntry",
]
