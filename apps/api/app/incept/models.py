from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Role(str, Enum):
    user = "user"
    manager = "manager"
    admin = "admin"


class ToolStatus(str, Enum):
    enabled = "enabled"
    mock = "mock"
    disabled = "disabled"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    pending = "pending"
    needs_clarification = "needs_clarification"


class AssetRole(str, Enum):
    upload = "upload"
    working = "working"
    reference_ad = "reference_ad"
    client_character = "client_character"
    client_logo = "client_logo"
    client_product = "client_product"
    client_background = "client_background"
    brand_element = "brand_element"
    generated = "generated"


class GenerationMode(str, Enum):
    free_create = "free_create"
    style_match = "style_match"
    theme_create = "theme_create"
    resize = "resize"


class ThreadMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    asset_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CreativeThread(BaseModel):
    thread_id: str
    workspace_id: str
    title: str
    generation_mode: GenerationMode = GenerationMode.free_create
    created_by: str = ""
    origin_asset_id: str | None = None
    cover_asset_id: str | None = None
    latest_asset_id: str | None = None
    latest_job_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    reference_asset_ids: list[str] = Field(default_factory=list)
    messages: list[ThreadMessage] = Field(default_factory=list)
    preview_url: str | None = None
    asset_count: int = 0
    job_count: int = 0


class User(BaseModel):
    id: str
    name: str
    email: str
    role: Role
    team: str


class ProviderConfig(BaseModel):
    default_image_provider: str
    openai_image_model: str
    vertex_imagen_model: str
    vertex_ai_enabled: bool
    gcp_project_id: str | None
    gcp_location: str
    asset_bucket: str
    max_image_variants: int
    max_output_sizes: int


class ToolDefinition(BaseModel):
    id: str
    name: str
    category: str
    status: ToolStatus
    provider: str
    owner: str
    description: str


class ToolStatusUpdate(BaseModel):
    status: ToolStatus


class Workspace(BaseModel):
    id: str
    title: str
    description: str
    owner_user_id: str
    team: str
    status: JobStatus
    updated_at: datetime


class Asset(BaseModel):
    id: str
    title: str
    type: Literal["image", "video", "gif", "report"]
    gcs_uri: str
    preview_url: str
    provider: str
    model: str
    workspace_id: str
    job_id: str
    prompt_hash: str
    created_by: str
    created_at: datetime
    width: int | None = None
    height: int | None = None
    theme: str | None = None
    asset_role: AssetRole = AssetRole.generated
    analysis: dict[str, Any] | None = None
    thread_id: str | None = None
    parent_asset_id: str | None = None
    root_asset_id: str | None = None


class GenerationRequest(BaseModel):
    workspace_id: str = Field(..., examples=["wsp_q2"])
    prompt: str
    provider: Literal["openai", "gemini"] = "gemini"
    model: str = "imagen-4.0-generate-001"
    variants: int = Field(default=1, ge=1, le=3)
    aspect_ratio: str = "1:1"
    created_by: str = "usr_jane"
    source_asset_ids: list[str] = Field(default_factory=list)
    theme: str = "World Cup"
    output_sizes: list[str] = Field(default_factory=lambda: ["300x250", "320x480", "1200x628"])
    output_format: Literal["image", "gif", "image_and_gif"] = "image"
    reference_asset_ids: list[str] = Field(default_factory=list)
    preserve_layout: bool = False
    use_reference_style: bool = True
    client_asset_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    thread_id: str | None = None
    source_asset_id: str | None = None
    generation_mode: GenerationMode = GenerationMode.free_create
    clarification_note: str | None = None
    include_gif: bool = False  # generate animated GIF for supported banner sizes
    # output_sizes length is validated in the endpoint against settings.max_output_sizes


# ── Session / conversation models ─────────────────────────────────────────────

class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    asset_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    session_id: str
    workspace_id: str
    reference_asset_ids: list[str] = Field(default_factory=list)
    messages: list[SessionMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Inpainting / image-edit ───────────────────────────────────────────────────

class ImageEditRequest(BaseModel):
    workspace_id: str
    asset_id: str                    # original image asset to edit (the "working image")
    extra_asset_ids: list[str] = Field(default_factory=list)  # logos / reference images
    mask_data: str | None = None     # base64-encoded PNG; transparent pixels = edit area
    prompt: str
    model: str = "gpt-image-2"
    variants: int = Field(default=1, ge=1, le=3)
    created_by: str = "usr_jane"
    theme: str | None = None
    session_id: str | None = None
    thread_id: str | None = None
    output_sizes: list[str] = Field(default_factory=list)
    clarification_note: str | None = None


class GenerationJob(BaseModel):
    job_id: str
    workspace_id: str
    status: JobStatus
    progress: int
    lineage_key: str
    message: str
    tool_id: str = "openai-image-2"
    title: str = "Image generation"
    output_asset_ids: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    source_asset_id: str | None = None
    clarification_question: str | None = None
    clarification_reason: str | None = None
    clarification_options: list[dict[str, Any]] = Field(default_factory=list)
    clarification_manifest: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Outpainting ───────────────────────────────────────────────────────────────

class OutpaintRequest(BaseModel):
    workspace_id: str
    asset_id: str
    direction: Literal["left", "right", "top", "bottom", "all"] = "all"
    ratio: float = Field(default=0.3, ge=0.1, le=0.8)
    prompt: str = ""
    model: str = "gpt-image-2"
    created_by: str = "usr_jane"
    session_id: str | None = None
    thread_id: str | None = None
    output_sizes: list[str] = Field(default_factory=list)
    clarification_note: str | None = None


# ── Background removal ────────────────────────────────────────────────────────

class RemoveBGRequest(BaseModel):
    workspace_id: str
    asset_id: str
    replacement_prompt: str = ""   # if empty → transparent BG; if set → replace with this
    model: str = "gpt-image-2"
    created_by: str = "usr_jane"
    session_id: str | None = None
    thread_id: str | None = None
    output_sizes: list[str] = Field(default_factory=list)
    clarification_note: str | None = None


# ── Text overlay ──────────────────────────────────────────────────────────────

class AddTextRequest(BaseModel):
    workspace_id: str
    asset_id: str
    text: str
    position: Literal["top", "center", "bottom"] = "bottom"
    font_size_ratio: float = Field(default=0.06, ge=0.02, le=0.2)
    created_by: str = "usr_jane"
    session_id: str | None = None
    thread_id: str | None = None
    output_sizes: list[str] = Field(default_factory=list)
    clarification_note: str | None = None


class RoleAssignment(BaseModel):
    user_id: str
    role: Role
    team: str


class UsageEvent(BaseModel):
    id: str
    job_id: str
    workspace_id: str
    user_id: str
    user_email: str
    provider: str
    model: str
    operation: str
    prompt_hash: str
    variants: int
    output_size_count: int
    output_format: str
    estimated_provider_generations: int
    output_asset_count: int
    estimated_cost_usd: float
    actual_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
