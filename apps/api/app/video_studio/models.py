from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Position(BaseModel):
    x: float = 0
    y: float = 0


class VideoNode(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=80)
    position: Position = Field(default_factory=Position)
    data: dict[str, Any] = Field(default_factory=dict)


class VideoEdge(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    source_handle: str | None = Field(default=None, max_length=128)
    target_handle: str | None = Field(default=None, max_length=128)


class CanvasDocument(BaseModel):
    version: int = 1
    nodes: list[VideoNode] = Field(default_factory=list, max_length=2_000)
    edges: list[VideoEdge] = Field(default_factory=list, max_length=4_000)
    viewport: dict[str, float] = Field(
        default_factory=lambda: {"x": 0, "y": 0, "zoom": 1}
    )
    updated_at: datetime = Field(default_factory=utc_now)


class CanvasSummary(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
    name: str = Field(min_length=1, max_length=120)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CanvasCreate(BaseModel):
    name: str = Field(default="Canvas", min_length=1, max_length=120)


class CanvasUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    thumbnail_url: str | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)


class ProjectDetail(ProjectSummary):
    canvas: CanvasDocument
    canvases: list[CanvasSummary] = Field(default_factory=list)
    active_canvas_id: str = "main"


class AssetEntry(BaseModel):
    path: str
    name: str
    kind: Literal["file", "directory"]
    size: int = 0
    modified_at: datetime | None = None
    mime_type: str | None = None


class AssetMutation(BaseModel):
    path: str = Field(min_length=1, max_length=1_024)


class AssetRename(BaseModel):
    path: str = Field(min_length=1, max_length=1_024)
    target: str = Field(min_length=1, max_length=1_024)


class VideoStudioSettings(BaseModel):
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    theme: Literal["light"] = "light"
    default_image_ratio: str = "16:9"
    default_video_duration: int = Field(default=5, ge=1, le=60)
    agent_system_prompt: str = Field(default="", max_length=20_000)
    default_agent: str = Field(default="workflow", max_length=80)
    default_text_model: str = Field(default="deployment-default", max_length=120)
    privacy_mode: Literal["private"] = "private"


class ProjectDocument(BaseModel):
    content: str = Field(default="", max_length=500_000)
    updated_at: datetime = Field(default_factory=utc_now)


class SkillDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)
    instructions: str = Field(default="", max_length=100_000)
    enabled: bool = True
    builtin: bool = False
    order: int = Field(default=0, ge=0, le=10_000)


class ExtensionDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    category: Literal["node", "tool", "agent"]
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)
    enabled: bool = True
    builtin: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class CatalogSnapshot(BaseModel):
    skills: list[SkillDefinition]
    extensions: list[ExtensionDefinition]


class CatalogImport(BaseModel):
    skills: list[SkillDefinition] = Field(default_factory=list, max_length=100)
    extensions: list[ExtensionDefinition] = Field(default_factory=list, max_length=100)


class AgentMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class AgentConversation(BaseModel):
    id: str
    name: str
    provider_id: str | None = Field(default=None, max_length=96)
    model_id: str | None = Field(default=None, max_length=256)
    messages: list[AgentMessage] = Field(default_factory=list, max_length=1_000)
    research_history: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    conversation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    agent_id: str | None = Field(default=None, max_length=80)
    asset_paths: list[str] = Field(default_factory=list, max_length=20)


class ConversationRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ExportClip(BaseModel):
    asset_path: str = Field(min_length=1, max_length=1_024)
    duration: float | None = Field(default=None, gt=0, le=600)
    transition: Literal["cut", "crossfade"] = "cut"


class ExportRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    name: str = Field(default="video-export", min_length=1, max_length=120)
    clips: list[ExportClip] = Field(min_length=1, max_length=200)
    soundtrack_path: str | None = Field(default=None, max_length=1_024)
    width: int = Field(default=1920, ge=320, le=3840)
    height: int = Field(default=1080, ge=240, le=2160)
    fps: int = Field(default=30, ge=12, le=60)


class ExportResponse(BaseModel):
    asset_path: str
    mime_type: str = "video/mp4"
    size: int


class ExportJob(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    project_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    result: ExportResponse | None = None
    request: ExportRequest
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MediaJobCreate(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    media_type: Literal["image", "video", "audio"]
    provider_id: str = Field(min_length=1, max_length=96)
    model_id: str = Field(min_length=1, max_length=256)
    prompt: str = Field(min_length=1, max_length=12_000)
    ratio: str | None = Field(default=None, max_length=20)
    size: str | None = Field(default=None, max_length=40)
    duration: int | None = Field(default=None, ge=1, le=60)
    first_frame_path: str | None = Field(default=None, max_length=1_024)
    last_frame_path: str | None = Field(default=None, max_length=1_024)
    output_directory: str = Field(default="generated", min_length=1, max_length=1_024)
    resolution: str | None = Field(default=None, max_length=40)
    generate_audio: bool | None = None
    voice: str | None = Field(default=None, max_length=256)
    speed: float | None = Field(default=None, gt=0, le=4)
    format: str | None = Field(default=None, max_length=40)


class MediaJob(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    project_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    provider: str = "vertex"
    model: str = ""
    location: str = ""
    request: MediaJobCreate
    result_asset_path: str | None = None
    result_mime_type: str | None = None
    result_size: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DirectorVector(BaseModel):
    x: float = 0
    y: float = 0
    z: float = 0


class DirectorObject(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    shape: Literal["cube", "sphere", "cylinder", "mannequin"] = "cube"
    position: DirectorVector = Field(default_factory=DirectorVector)
    scale: DirectorVector = Field(default_factory=lambda: DirectorVector(x=1, y=1, z=1))
    color: str = Field(default="#8b5cf6", pattern=r"^#[0-9a-fA-F]{6}$")


class DirectorCamera(BaseModel):
    position: DirectorVector = Field(default_factory=lambda: DirectorVector(x=6, y=4, z=8))
    target: DirectorVector = Field(default_factory=DirectorVector)
    focal_length: float = Field(default=35, ge=6, le=110)


class DirectorScene(BaseModel):
    objects: list[DirectorObject] = Field(default_factory=list, max_length=60)
    camera: DirectorCamera = Field(default_factory=DirectorCamera)
    background: str = Field(default="#edf2ff", pattern=r"^#[0-9a-fA-F]{6}$")


class DirectorPlanRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12_000)


class DirectorPlanResponse(BaseModel):
    scene: DirectorScene


class ProductionTake(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
    asset_path: str = Field(min_length=1, max_length=1_024)
    source_job_id: str | None = Field(default=None, max_length=128)
    label: str = Field(default="Take", max_length=120)
    created_at: datetime = Field(default_factory=utc_now)


class ProductionKeyframe(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
    asset_path: str = Field(min_length=1, max_length=1_024)
    source_job_id: str | None = Field(default=None, max_length=128)
    label: str = Field(default="Keyframe", max_length=120)
    prompt: str = Field(default="", max_length=12_000)
    status: Literal["draft", "approved", "rejected"] = "draft"
    created_at: datetime = Field(default_factory=utc_now)


class ProductionShot(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=2_000)
    duration: float = Field(default=3, gt=0, le=600)
    status: Literal["draft", "approved", "changes_requested"] = "draft"
    notes: str = Field(default="", max_length=5_000)
    keyframe_prompt: str = Field(default="", max_length=12_000)
    video_prompt: str = Field(default="", max_length=12_000)
    camera: str = Field(default="", max_length=2_000)
    continuity: str = Field(default="", max_length=5_000)
    audio_cue: str = Field(default="", max_length=2_000)
    keyframes: list[ProductionKeyframe] = Field(default_factory=list, max_length=50)
    selected_keyframe_id: str | None = Field(default=None, max_length=128)
    takes: list[ProductionTake] = Field(default_factory=list, max_length=50)
    selected_take_id: str | None = Field(default=None, max_length=128)
    active_generation_job_id: str | None = Field(default=None, max_length=128)


class TimelineClip(BaseModel):
    shot_id: str = Field(min_length=1, max_length=128)
    duration: float = Field(default=3, gt=0, le=600)
    transition: Literal["cut", "crossfade"] = "cut"
    included: bool = True


class TimelineRevision(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    revision: int = Field(ge=1)
    label: str = Field(default="Timeline", max_length=120)
    clips: list[TimelineClip] = Field(default_factory=list, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class QAReport(BaseModel):
    status: Literal["not_run", "pass", "warning", "blocked"] = "not_run"
    issues: list[str] = Field(default_factory=list, max_length=200)
    checked_at: datetime | None = None


class DeliveryManifest(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    asset_path: str = Field(min_length=1, max_length=1_024)
    mime_type: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    timeline_revision: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)


class ScriptRevision(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    revision: int = Field(ge=1)
    content: str = Field(max_length=500_000)
    created_at: datetime = Field(default_factory=utc_now)


class ProductionAuditEvent(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    kind: str = Field(min_length=1, max_length=80)
    detail: str = Field(default="", max_length=2_000)
    created_at: datetime = Field(default_factory=utc_now)


class ProductionState(BaseModel):
    revision: int = Field(default=0, ge=0)
    script_locked: bool = False
    script_revision: int = Field(default=0, ge=0)
    script_revisions: list[ScriptRevision] = Field(default_factory=list, max_length=100)
    shots: list[ProductionShot] = Field(default_factory=list, max_length=200)
    timeline: list[TimelineClip] = Field(default_factory=list, max_length=200)
    timeline_revisions: list[TimelineRevision] = Field(default_factory=list, max_length=100)
    qa: QAReport = Field(default_factory=QAReport)
    deliveries: list[DeliveryManifest] = Field(default_factory=list, max_length=100)
    audit_events: list[ProductionAuditEvent] = Field(default_factory=list, max_length=1_000)
    updated_at: datetime = Field(default_factory=utc_now)


class TimelineCommit(BaseModel):
    label: str = Field(default="Timeline", min_length=1, max_length=120)


class ScriptCommit(BaseModel):
    content: str = Field(min_length=1, max_length=500_000)


class DeliveryCreate(BaseModel):
    asset_path: str = Field(min_length=1, max_length=1_024)
