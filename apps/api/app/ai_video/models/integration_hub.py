from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.ai_video.core.db import Base
from app.ai_video.models.base import TimestampMixin


class CustomEndpoint(Base, TimestampMixin):
    __tablename__ = "custom_endpoints"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    auth_header: Mapped[str] = mapped_column(String(128), nullable=False, default="Authorization")
    credential_env: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_contract: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    response_contract: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    polling_contract: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_market_entry_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_test_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (Index("ix_custom_endpoints_category_status", "category", "status"),)


class EndpointMarketEntry(Base, TimestampMixin):
    __tablename__ = "endpoint_market_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    publisher: Mapped[str] = mapped_column(String(255), nullable=False, default="Local")
    trust_level: Mapped[str] = mapped_column(String(16), nullable=False, default="local")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    template: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    credential_destination: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    __table_args__ = (Index("ix_endpoint_market_status_trust", "status", "trust_level"),)


class ComfyWorkflow(Base, TimestampMixin):
    __tablename__ = "comfy_workflows"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    endpoint_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("custom_endpoints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workflow: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    bindings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")


class AutomationApiKey(Base, TimestampMixin):
    __tablename__ = "automation_api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectMemory(Base, TimestampMixin):
    __tablename__ = "project_memories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_key: Mapped[str] = mapped_column(String(128), nullable=False, default="local-user", index=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="project")
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="fact")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="manual")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    __table_args__ = (Index("ix_project_memories_lookup", "project_id", "scope", "status", "pinned"),)


__all__ = [
    "AutomationApiKey",
    "ComfyWorkflow",
    "CustomEndpoint",
    "EndpointMarketEntry",
    "ProjectMemory",
]
