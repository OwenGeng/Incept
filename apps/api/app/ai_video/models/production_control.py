from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.ai_video.core.db import Base
from app.ai_video.models.base import TimestampMixin


class ProductionRevision(Base, TimestampMixin):
    """Immutable production input revision.

    One table intentionally covers script, shot-plan, keyframe, prompt and edit
    revisions so approval, lineage and workflow planning share one contract.
    """

    __tablename__ = "production_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(String(24), nullable=False, default="project")
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    parent_revision_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("production_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "scope_type",
            "scope_id",
            "kind",
            "revision_number",
            name="uq_production_revision_scope_number",
        ),
        Index(
            "ix_production_revision_lookup",
            "project_id",
            "kind",
            "scope_type",
            "scope_id",
            "state",
        ),
    )


class ProductionArtifact(Base, TimestampMixin):
    """A durable generated or uploaded artifact with lifecycle and currency."""

    __tablename__ = "production_artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shot_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("shots.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_revision_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("production_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    generation_task_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("generation_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="current")
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    selected_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_production_artifact_scope",
            "project_id",
            "shot_id",
            "artifact_type",
            "lifecycle",
        ),
        Index("ix_production_artifact_currency", "project_id", "currency"),
    )


class ProductionQAReport(Base, TimestampMixin):
    __tablename__ = "production_qa_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edit_revision_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("production_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    waivers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    run_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (Index("ix_production_qa_project_created", "project_id", "created_at"),)


class ProductionDelivery(Base, TimestampMixin):
    __tablename__ = "production_deliveries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edit_revision_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("production_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qa_report_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("production_qa_reports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    delivery_type: Mapped[str] = mapped_column(String(16), nullable=False, default="preview")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    file_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    delivered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (Index("ix_production_delivery_project_created", "project_id", "created_at"),)


class ProductionAuditEvent(Base):
    __tablename__ = "production_audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_production_audit_project_created", "project_id", "created_at"),)


__all__ = [
    "ProductionArtifact",
    "ProductionAuditEvent",
    "ProductionDelivery",
    "ProductionQAReport",
    "ProductionRevision",
]
