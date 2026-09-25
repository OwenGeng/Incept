from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectAgentSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectAgentMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    message_metadata: dict = Field(default_factory=dict)
    created_at: datetime


class ProjectAgentChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    session_id: str | None = None


class ProjectAgentChatRead(BaseModel):
    session: ProjectAgentSessionRead
    user_message: ProjectAgentMessageRead
    assistant_message: ProjectAgentMessageRead


__all__ = [
    "ProjectAgentChatRead",
    "ProjectAgentChatRequest",
    "ProjectAgentMessageRead",
    "ProjectAgentSessionRead",
]
