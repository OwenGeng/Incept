from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai_video.core.contracts.video_generation import VideoRatio


ReferenceMode = Literal["first", "last", "key", "first_last", "first_last_key", "text_only"]


class VideoBatchItemRequest(BaseModel):
    shot_id: str = Field(min_length=1, max_length=64)
    reference_mode: ReferenceMode
    prompt: str | None = None
    images: list[str] = Field(default_factory=list)
    ratio: VideoRatio
    model_id: str | None = Field(None, max_length=64)
    provider_params: dict[str, Any] = Field(default_factory=dict)


class VideoBatchCreate(BaseModel):
    items: list[VideoBatchItemRequest] = Field(min_length=1, max_length=100)
    confirm_cost: bool = False
    confirmed_by: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def unique_shots(self) -> "VideoBatchCreate":
        shot_ids = [item.shot_id for item in self.items]
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError("Each shot may appear only once in a batch")
        if self.confirm_cost:
            raise ValueError("Create a preflight batch first, then confirm its quote by batch ID")
        return self


class VideoBatchConfirm(BaseModel):
    quote_fingerprint: str = Field(min_length=64, max_length=64)
    confirmed_by: str = Field(min_length=1, max_length=255)


class GenerationBatchItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_id: str
    target_type: str
    target_id: str
    status: str
    task_id: str | None
    error_code: str | None
    error_message: str
    created_at: datetime
    updated_at: datetime


class GenerationBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    kind: str
    status: str
    requested_ids: list[str]
    admission: dict[str, Any]
    estimate: dict[str, Any]
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[GenerationBatchItemRead] = Field(default_factory=list)


class ProviderCheckpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    provider: str
    model_id: str | None
    state: str
    request_fingerprint: str
    external_job_id: str | None
    poll_attempts: int
    download_attempts: int
    next_poll_at: datetime | None
    provider_completed_at: datetime | None
    downloaded_at: datetime | None
    billing_settlement_key: str | None
    checkpoint: dict[str, Any]
    last_error_code: str | None
    last_error_message: str
    created_at: datetime
    updated_at: datetime


class UsageLedgerEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    task_id: str | None
    provider: str
    model_id: str | None
    operation: str
    status: str
    quantity: Decimal | None
    unit: str | None
    currency: str | None
    estimated_amount: Decimal | None
    actual_amount: Decimal | None
    request_summary: dict[str, Any]
    response_summary: dict[str, Any]
    error_code: str | None
    error_message: str
    settled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UsageSummaryRead(BaseModel):
    project_id: str
    by_currency: dict[str, dict[str, Decimal]]
    unpriced_entries: int
    total_entries: int
    budget: dict[str, Any] | None = None


__all__ = [
    "GenerationBatchItemRead",
    "GenerationBatchRead",
    "ProviderCheckpointRead",
    "UsageLedgerEntryRead",
    "UsageSummaryRead",
    "VideoBatchCreate",
    "VideoBatchConfirm",
    "VideoBatchItemRequest",
]
