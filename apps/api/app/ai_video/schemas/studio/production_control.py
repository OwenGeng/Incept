from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProductionRevisionKind = Literal["script", "shot_plan", "keyframe", "motion_prompt", "edit"]
ProductionScopeType = Literal["project", "chapter", "shot"]
ProductionRevisionState = Literal["draft", "approved", "superseded"]
ArtifactCurrency = Literal["current", "stale", "missing", "blocked"]
ArtifactLifecycle = Literal["candidate", "selected", "rejected"]


class ProductionRevisionCreate(BaseModel):
    kind: ProductionRevisionKind
    scope_type: ProductionScopeType = "project"
    scope_id: str | None = Field(None, max_length=64)
    parent_revision_id: str | None = Field(None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def validate_scope(self) -> "ProductionRevisionCreate":
        if self.scope_type != "project" and not (self.scope_id and self.scope_id.strip()):
            raise ValueError("Non-project revisions require scope_id")
        if self.kind in {"keyframe", "motion_prompt"} and self.scope_type != "shot":
            raise ValueError(f"{self.kind} revisions must use shot scope")
        return self


class ProductionRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    scope_type: str
    scope_id: str
    kind: str
    revision_number: int
    state: str
    parent_revision_id: str | None
    payload: dict[str, Any]
    input_fingerprint: str
    created_by: str | None
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProductionRevisionApprovalRequest(BaseModel):
    approved_by: str | None = Field(None, max_length=255)


class ShotPlanSnapshotRequest(BaseModel):
    created_by: str | None = Field(None, max_length=255)


class ProductionArtifactCreate(BaseModel):
    shot_id: str | None = Field(None, max_length=64)
    artifact_type: str = Field(min_length=1, max_length=32)
    file_id: str | None = Field(None, max_length=64)
    source_revision_id: str | None = Field(None, max_length=64)
    generation_task_id: str | None = Field(None, max_length=64)
    input_fingerprint: str = Field(default="", max_length=64)
    currency: ArtifactCurrency = "current"
    lifecycle: ArtifactLifecycle = "candidate"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    shot_id: str | None
    artifact_type: str
    file_id: str | None
    source_revision_id: str | None
    generation_task_id: str | None
    input_fingerprint: str
    currency: str
    lifecycle: str
    metadata_json: dict[str, Any]
    selected_by: str | None
    selected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProductionArtifactSelectRequest(BaseModel):
    selected_by: str | None = Field(None, max_length=255)


class WorkflowProblem(BaseModel):
    code: str
    message: str
    target_type: str | None = None
    target_id: str | None = None
    severity: Literal["info", "warning", "blocking"] = "blocking"


class WorkflowArtifactSummary(BaseModel):
    artifact_type: str
    total: int = 0
    current: int = 0
    stale: int = 0
    missing: int = 0
    blocked: int = 0
    selected: int = 0


class WorkflowNextAction(BaseModel):
    type: str
    reason: str
    args: dict[str, Any] = Field(default_factory=dict)
    requested_ids: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False


class ProductionWorkflowPlanRead(BaseModel):
    project_id: str
    current_step: str
    steps: list[dict[str, Any]]
    blockers: list[WorkflowProblem]
    gates: list[dict[str, Any]]
    artifacts: list[WorkflowArtifactSummary]
    next_action: WorkflowNextAction


class ProductionQARunRequest(BaseModel):
    edit_revision_id: str = Field(min_length=1, max_length=64)
    run_by: str | None = Field(None, max_length=255)


class ProductionQAReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    edit_revision_id: str
    status: str
    checks: list[dict[str, Any]]
    waivers: list[dict[str, Any]]
    run_by: str | None
    created_at: datetime
    updated_at: datetime


class ProductionDeliveryCreate(BaseModel):
    edit_revision_id: str = Field(min_length=1, max_length=64)
    qa_report_id: str = Field(min_length=1, max_length=64)
    delivery_type: Literal["preview", "final"] = "final"
    file_ids: list[str] = Field(min_length=1)
    delivered_by: str | None = Field(None, max_length=255)


class ProductionDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    edit_revision_id: str
    qa_report_id: str
    delivery_type: str
    status: str
    file_ids: list[str]
    manifest: dict[str, Any]
    delivered_by: str | None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ProductionArtifactCreate",
    "ProductionArtifactRead",
    "ProductionArtifactSelectRequest",
    "ProductionDeliveryCreate",
    "ProductionDeliveryRead",
    "ProductionQAReportRead",
    "ProductionQARunRequest",
    "ProductionRevisionApprovalRequest",
    "ProductionRevisionCreate",
    "ProductionRevisionRead",
    "ProductionWorkflowPlanRead",
    "ShotPlanSnapshotRequest",
]
