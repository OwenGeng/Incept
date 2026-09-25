from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.ai_video.core.db import Base
from app.ai_video.models.base import TimestampMixin


class ProjectAgentSession(Base, TimestampMixin):
    __tablename__ = "project_agent_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New conversation")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")

    __table_args__ = (Index("ix_project_agent_sessions_project_updated", "project_id", "updated_at"),)


class ProjectAgentMessage(Base, TimestampMixin):
    __tablename__ = "project_agent_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (Index("ix_project_agent_messages_session_created", "session_id", "created_at"),)


__all__ = ["ProjectAgentMessage", "ProjectAgentSession"]
