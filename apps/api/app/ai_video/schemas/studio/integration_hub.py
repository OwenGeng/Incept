from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


EndpointCategory = Literal["text", "image", "video", "speech", "music", "workflow"]


class CustomEndpointWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: EndpointCategory
    base_url: HttpUrl
    status: Literal["draft", "testing", "active", "disabled"] = "draft"
    auth_type: Literal["none", "bearer", "header"] = "none"
    auth_header: str = Field("Authorization", min_length=1, max_length=128)
    credential_env: str | None = Field(None, max_length=255, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    request_contract: dict[str, Any]
    response_contract: dict[str, Any]
    polling_contract: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_contract(self) -> "CustomEndpointWrite":
        method = str(self.request_contract.get("method") or "").upper()
        path = str(self.request_contract.get("path") or "")
        if method not in {"GET", "POST", "PUT", "PATCH"}:
            raise ValueError("request_contract.method must be GET, POST, PUT, or PATCH")
        if not path.startswith("/") or "://" in path:
            raise ValueError("request_contract.path must be an absolute path on base_url")
        if self.auth_type != "none" and not self.credential_env:
            raise ValueError("credential_env is required when auth is enabled")
        if not self.response_contract.get("output_path") and not self.response_contract.get("job_id_path"):
            raise ValueError("response_contract requires output_path or job_id_path")
        if self.polling_contract:
            poll_method = str(self.polling_contract.get("method") or "").upper()
            poll_path = str(self.polling_contract.get("path") or "")
            poll_response = self.polling_contract.get("response_contract")
            if poll_method not in {"GET", "POST", "PUT", "PATCH"}:
                raise ValueError("polling_contract.method must be GET, POST, PUT, or PATCH")
            if not poll_path.startswith("/") or "://" in poll_path:
                raise ValueError("polling_contract.path must be an absolute path on base_url")
            if not isinstance(poll_response, dict) or not any(poll_response.get(key) for key in ("output_path", "job_id_path", "status_path", "error_path")):
                raise ValueError("polling_contract.response_contract requires a response mapping")
        return self


class CustomEndpointCreate(CustomEndpointWrite):
    id: str | None = Field(None, max_length=64)


class CustomEndpointRead(CustomEndpointWrite):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_market_entry_id: str | None
    config_version: int
    last_test_status: str | None
    last_tested_at: datetime | None
    last_test_detail: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class EndpointValidateRequest(BaseModel):
    sample_response: dict[str, Any]


class EndpointExecuteRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    confirm_external_call: bool = False
    wait_for_result: bool = False


class EndpointExecutionRead(BaseModel):
    request_preview: dict[str, Any]
    status: str
    output: Any = None
    job_id: Any = None
    error: Any = None
    response_preview: dict[str, Any] = Field(default_factory=dict)


class EndpointMarketEntryWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    publisher: str = Field("Local", min_length=1, max_length=255)
    trust_level: Literal["local", "reviewed", "unverified"] = "local"
    status: Literal["draft", "published", "deprecated"] = "draft"
    version: str = Field("1.0.0", min_length=1, max_length=32)
    categories: list[EndpointCategory] = Field(default_factory=list)
    template: dict[str, Any]
    credential_destination: str = Field(min_length=1)
    source_url: HttpUrl | None = None


class EndpointMarketEntryCreate(EndpointMarketEntryWrite):
    id: str | None = Field(None, max_length=64)


class EndpointMarketEntryRead(EndpointMarketEntryWrite):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class MarketInstallRequest(BaseModel):
    endpoint_name: str | None = Field(None, max_length=255)
    credential_env: str | None = Field(None, max_length=255, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class ComfyWorkflowCreate(BaseModel):
    id: str | None = Field(None, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    endpoint_id: str | None = Field(None, max_length=64)
    workflow: dict[str, Any]
    input_schema: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "ready", "disabled"] = "draft"


class ComfyWorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    endpoint_id: str | None
    workflow: dict[str, Any]
    input_schema: dict[str, Any]
    bindings: dict[str, Any]
    capabilities: dict[str, Any]
    version: int
    status: str
    created_at: datetime
    updated_at: datetime


class ComfyWorkflowExecuteRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    confirm_external_call: bool = False
    wait_for_result: bool = True
    persist_output: bool = False
    project_id: str | None = Field(None, max_length=64)
    shot_id: str | None = Field(None, max_length=64)
    artifact_type: str | None = Field(None, max_length=32)

    @model_validator(mode="after")
    def validate_persistence_target(self) -> "ComfyWorkflowExecuteRequest":
        if self.persist_output and not self.project_id:
            raise ValueError("project_id is required when persist_output is true")
        if self.persist_output and not self.confirm_external_call:
            raise ValueError("confirm_external_call must be true when persist_output is true")
        return self


class ComfyWorkflowExecutionRead(BaseModel):
    endpoint_result: EndpointExecutionRead
    bound_workflow: dict[str, Any]
    file_id: str | None = None
    artifact_id: str | None = None
    persistence_status: Literal["not_requested", "persisted", "output_pending", "unsupported_output"] = "not_requested"


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[Literal["read:production", "write:production", "read:memory", "write:memory"]] = Field(min_length=1)


class ApiKeyCreated(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    token: str


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    status: str
    last_used_at: datetime | None
    created_at: datetime


class MemoryCreate(BaseModel):
    scope: Literal["project", "user"] = "project"
    kind: Literal["preference", "fact", "decision", "summary"] = "fact"
    content: str = Field(min_length=1, max_length=20_000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    source: str = Field("manual", max_length=255)
    pinned: bool = False
    confidence: float = Field(1.0, ge=0, le=1)


class MemoryRead(MemoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str | None
    owner_key: str
    status: str
    created_at: datetime
    updated_at: datetime


__all__ = [name for name in globals() if not name.startswith("_")]
