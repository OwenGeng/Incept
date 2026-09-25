from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.ai_video.core.db import Base
from app.ai_video.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.ai_video.models.studio_projects import Project


class ProjectResearch(Base, TimestampMixin):
    """Project-scoped advertising research and its approved direction."""

    __tablename__ = "project_research"

    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    entry_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="research")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    brief: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    creative_directions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    approved_direction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="research")


__all__ = ["ProjectResearch"]
