from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import metadata_repository

from .models import (
    AgentConversation,
    CanvasCreate,
    CanvasDocument,
    CanvasSummary,
    CanvasUpdate,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
    VideoStudioSettings,
    ProjectDocument,
    SkillDefinition,
    ExtensionDefinition,
    CatalogImport,
    CatalogSnapshot,
    ExportJob,
    MediaJob,
    ProductionAuditEvent,
    ProductionState,
    ScriptCommit,
    ScriptRevision,
    TimelineCommit,
    TimelineRevision,
    QAReport,
    DeliveryCreate,
    DeliveryManifest,
)


_PROJECT_ID = re.compile(r"^[a-f0-9]{32}$")
_CANVAS_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
_lock = threading.RLock()


def _root() -> Path:
    configured = os.getenv("VIDEO_STUDIO_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "data" / "video-studio"


def _user_key(email: str) -> str:
    identity = email.strip().lower() or "local"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _user_root(email: str) -> Path:
    path = _root() / "users" / _user_key(email)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _project_root(email: str, project_id: str) -> Path:
    if not _PROJECT_ID.fullmatch(project_id):
        raise ValueError("Invalid project id")
    return _user_root(email) / "projects" / project_id


def _read_json(path: Path, default: Any) -> Any:
    path_key = _metadata_path_key(path)
    if path_key:
        value = metadata_repository.read(path_key)
        if value is not None:
            # Keep a disposable local cache for libraries that require Paths
            # (FFmpeg, archive export, and the restored Vue workspace).  The
            # database remains authoritative when configured.
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                temporary = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
                temporary.write_text(
                    json.dumps(value, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                temporary.replace(path)
            return value
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if path_key:
            metadata_repository.write(path_key, value)
        return value
    except FileNotFoundError:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)
    path_key = _metadata_path_key(path)
    if path_key:
        metadata_repository.write(path_key, value)


def _metadata_path_key(path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(_root())
    except ValueError:
        return None
    if path.suffix != ".json":
        return None
    return relative.as_posix()


def _delete_json(path: Path) -> None:
    path.unlink(missing_ok=True)
    path_key = _metadata_path_key(path)
    if path_key:
        metadata_repository.delete(path_key)


def _canvas_path(project_root: Path, canvas_id: str) -> Path:
    if not _CANVAS_ID.fullmatch(canvas_id):
        raise ValueError("Invalid canvas id")
    return project_root / "canvases" / f"{canvas_id}.json"


def _ensure_canvas_manifest(project_root: Path, metadata: dict[str, Any]) -> tuple[dict[str, Any], list[CanvasSummary]]:
    raw = metadata.get("canvases")
    if isinstance(raw, list) and raw:
        canvases = [CanvasSummary.model_validate(item) for item in raw]
        active_id = str(metadata.get("active_canvas_id") or canvases[0].id)
        if not any(item.id == active_id for item in canvases):
            active_id = canvases[0].id
            metadata["active_canvas_id"] = active_id
        return metadata, canvases

    legacy = CanvasDocument.model_validate(_read_json(project_root / "canvas.json", {}))
    now = legacy.updated_at
    summary = CanvasSummary(id="main", name="Canvas 1", created_at=now, updated_at=now)
    metadata["active_canvas_id"] = summary.id
    metadata["canvases"] = [summary.model_dump(mode="json")]
    _write_json(_canvas_path(project_root, summary.id), legacy.model_dump(mode="json"))
    _write_json(project_root / "project.json", metadata)
    return metadata, [summary]


def _project_canvas_state(project_root: Path, metadata: dict[str, Any]) -> tuple[dict[str, Any], list[CanvasSummary], CanvasDocument]:
    metadata, canvases = _ensure_canvas_manifest(project_root, metadata)
    active_id = str(metadata["active_canvas_id"])
    active = CanvasDocument.model_validate(_read_json(_canvas_path(project_root, active_id), {}))
    return metadata, canvases, active


def _summary(project_root: Path) -> ProjectSummary:
    metadata = _read_json(project_root / "project.json", {})
    canvas = _read_json(project_root / "canvas.json", {})
    return ProjectSummary(
        **metadata,
        node_count=len(canvas.get("nodes", [])),
    )


def list_projects(email: str) -> list[ProjectSummary]:
    projects_root = _user_root(email) / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    prefix = projects_root.resolve().relative_to(_root()).as_posix()
    for path_key, value in metadata_repository.list_prefix(prefix):
        relative = Path(path_key).relative_to(prefix)
        if len(relative.parts) != 2 or relative.parts[1] != "project.json":
            continue
        project_id = relative.parts[0]
        if not _PROJECT_ID.fullmatch(project_id):
            continue
        project_path = projects_root / project_id / "project.json"
        project_path.parent.mkdir(parents=True, exist_ok=True)
        if not project_path.exists():
            project_path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
    projects = [
        _summary(path)
        for path in projects_root.iterdir()
        if path.is_dir() and _PROJECT_ID.fullmatch(path.name) and (path / "project.json").is_file()
    ]
    return sorted(projects, key=lambda item: item.updated_at, reverse=True)


def create_project(email: str, body: ProjectCreate) -> ProjectDetail:
    with _lock:
        project_id = uuid.uuid4().hex
        project_root = _project_root(email, project_id)
        project_root.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        canvas_summary = CanvasSummary(id="main", name="Canvas 1", created_at=now, updated_at=now)
        metadata = {
            "id": project_id,
            "name": body.name.strip(),
            "description": body.description.strip(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "thumbnail_url": None,
            "active_canvas_id": canvas_summary.id,
            "canvases": [canvas_summary.model_dump(mode="json")],
        }
        canvas = CanvasDocument(updated_at=now)
        _write_json(project_root / "project.json", metadata)
        _write_json(project_root / "canvas.json", canvas.model_dump(mode="json"))
        _write_json(_canvas_path(project_root, canvas_summary.id), canvas.model_dump(mode="json"))
        (project_root / "assets").mkdir()
        return ProjectDetail(**metadata, node_count=0, canvas=canvas)


def get_project(email: str, project_id: str) -> ProjectDetail:
    project_root = _project_root(email, project_id)
    metadata = _read_json(project_root / "project.json", None)
    if metadata is None:
        raise FileNotFoundError(project_id)
    metadata, canvases, canvas = _project_canvas_state(project_root, metadata)
    return ProjectDetail(**metadata, node_count=len(canvas.nodes), canvas=canvas)


def update_project(email: str, project_id: str, body: ProjectUpdate) -> ProjectDetail:
    with _lock:
        project_root = _project_root(email, project_id)
        metadata = _read_json(project_root / "project.json", None)
        if metadata is None:
            raise FileNotFoundError(project_id)
        if body.name is not None:
            metadata["name"] = body.name.strip()
        if body.description is not None:
            metadata["description"] = body.description.strip()
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(project_root / "project.json", metadata)
        return get_project(email, project_id)


def delete_project(email: str, project_id: str) -> None:
    with _lock:
        project_root = _project_root(email, project_id)
        if _read_json(project_root / "project.json", None) is None:
            raise FileNotFoundError(project_id)
        project_key = project_root.resolve().relative_to(_root()).as_posix()
        metadata_repository.delete_prefix(project_key)
        shutil.rmtree(project_root, ignore_errors=True)


def export_project_archive(email: str, project_id: str, target: Path) -> Path:
    project_root = _project_root(email, project_id)
    if not (project_root / "project.json").is_file():
        raise FileNotFoundError(project_id)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in project_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(project_root).as_posix())
    return target


def import_project_archive(email: str, source: Path) -> ProjectDetail:
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > 10_000:
            raise ValueError("Project archive contains too many files")
        total_size = sum(member.file_size for member in members)
        if total_size > 2 * 1024 * 1024 * 1024:
            raise ValueError("Expanded project archive exceeds 2 GB")
        names = {member.filename for member in members}
        if "project.json" not in names or "canvas.json" not in names:
            raise ValueError("Project archive is missing project.json or canvas.json")
        for member in members:
            candidate = Path(member.filename)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError("Project archive contains an unsafe path")

        project_id = uuid.uuid4().hex
        project_root = _project_root(email, project_id)
        project_root.mkdir(parents=True)
        try:
            archive.extractall(project_root)
            metadata = _read_json(project_root / "project.json", {})
            now = datetime.now(timezone.utc).isoformat()
            metadata.update({"id": project_id, "updated_at": now})
            metadata.setdefault("created_at", now)
            metadata.setdefault("name", "Imported project")
            metadata.setdefault("description", "")
            metadata.setdefault("thumbnail_url", None)
            CanvasDocument.model_validate(_read_json(project_root / "canvas.json", {}))
            _write_json(project_root / "project.json", metadata)
            (project_root / "assets").mkdir(exist_ok=True)
            return get_project(email, project_id)
        except Exception:
            shutil.rmtree(project_root, ignore_errors=True)
            raise


def save_canvas(email: str, project_id: str, canvas: CanvasDocument) -> CanvasDocument:
    with _lock:
        project_root = _project_root(email, project_id)
        metadata = _read_json(project_root / "project.json", None)
        if metadata is None:
            raise FileNotFoundError(project_id)
        metadata, canvases, _ = _project_canvas_state(project_root, metadata)
        active_id = str(metadata["active_canvas_id"])
        saved = canvas.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        _write_json(_canvas_path(project_root, active_id), saved.model_dump(mode="json"))
        _write_json(project_root / "canvas.json", saved.model_dump(mode="json"))
        metadata["canvases"] = [
            item.model_copy(update={"updated_at": saved.updated_at}).model_dump(mode="json")
            if item.id == active_id else item.model_dump(mode="json")
            for item in canvases
        ]
        metadata["updated_at"] = saved.updated_at.isoformat()
        _write_json(project_root / "project.json", metadata)
        return saved


def list_canvases(email: str, project_id: str) -> list[CanvasSummary]:
    project_root = _project_root(email, project_id)
    metadata = _read_json(project_root / "project.json", None)
    if metadata is None:
        raise FileNotFoundError(project_id)
    _, canvases = _ensure_canvas_manifest(project_root, metadata)
    return canvases


def get_project_canvas(email: str, project_id: str, canvas_id: str) -> CanvasDocument:
    project_root = _project_root(email, project_id)
    if _read_json(project_root / "project.json", None) is None:
        raise FileNotFoundError(project_id)
    value = _read_json(_canvas_path(project_root, canvas_id), None)
    if value is None:
        raise FileNotFoundError(canvas_id)
    return CanvasDocument.model_validate(value)


def create_canvas(email: str, project_id: str, body: CanvasCreate) -> ProjectDetail:
    with _lock:
        project_root = _project_root(email, project_id)
        metadata = _read_json(project_root / "project.json", None)
        if metadata is None:
            raise FileNotFoundError(project_id)
        metadata, canvases = _ensure_canvas_manifest(project_root, metadata)
        now = datetime.now(timezone.utc)
        summary = CanvasSummary(id=uuid.uuid4().hex, name=body.name.strip(), created_at=now, updated_at=now)
        canvas = CanvasDocument(updated_at=now)
        _write_json(_canvas_path(project_root, summary.id), canvas.model_dump(mode="json"))
        metadata["active_canvas_id"] = summary.id
        metadata["canvases"] = [*([item.model_dump(mode="json") for item in canvases]), summary.model_dump(mode="json")]
        metadata["updated_at"] = now.isoformat()
        _write_json(project_root / "canvas.json", canvas.model_dump(mode="json"))
        _write_json(project_root / "project.json", metadata)
        return get_project(email, project_id)


def save_project_canvas(email: str, project_id: str, canvas_id: str, canvas: CanvasDocument) -> CanvasDocument:
    with _lock:
        project_root = _project_root(email, project_id)
        metadata = _read_json(project_root / "project.json", None)
        if metadata is None:
            raise FileNotFoundError(project_id)
        metadata, canvases = _ensure_canvas_manifest(project_root, metadata)
        if not any(item.id == canvas_id for item in canvases):
            raise FileNotFoundError(canvas_id)
        saved = canvas.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        _write_json(_canvas_path(project_root, canvas_id), saved.model_dump(mode="json"))
        if metadata["active_canvas_id"] == canvas_id:
            _write_json(project_root / "canvas.json", saved.model_dump(mode="json"))
        metadata["canvases"] = [
            item.model_copy(update={"updated_at": saved.updated_at}).model_dump(mode="json")
            if item.id == canvas_id else item.model_dump(mode="json")
            for item in canvases
        ]
        metadata["updated_at"] = saved.updated_at.isoformat()
        _write_json(project_root / "project.json", metadata)
        return saved


def activate_canvas(email: str, project_id: str, canvas_id: str) -> ProjectDetail:
    with _lock:
        project_root = _project_root(email, project_id)
        metadata = _read_json(project_root / "project.json", None)
        if metadata is None:
            raise FileNotFoundError(project_id)
        metadata, canvases = _ensure_canvas_manifest(project_root, metadata)
        if not any(item.id == canvas_id for item in canvases):
            raise FileNotFoundError(canvas_id)
        canvas = get_project_canvas(email, project_id, canvas_id)
        metadata["active_canvas_id"] = canvas_id
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(project_root / "canvas.json", canvas.model_dump(mode="json"))
        _write_json(project_root / "project.json", metadata)
        return get_project(email, project_id)


def update_canvas(email: str, project_id: str, canvas_id: str, body: CanvasUpdate) -> list[CanvasSummary]:
    with _lock:
        project_root = _project_root(email, project_id)
        metadata = _read_json(project_root / "project.json", None)
        if metadata is None:
            raise FileNotFoundError(project_id)
        metadata, canvases = _ensure_canvas_manifest(project_root, metadata)
        if not any(item.id == canvas_id for item in canvases):
            raise FileNotFoundError(canvas_id)
        metadata["canvases"] = [
            item.model_copy(update={"name": body.name.strip()}).model_dump(mode="json")
            if item.id == canvas_id else item.model_dump(mode="json")
            for item in canvases
        ]
        _write_json(project_root / "project.json", metadata)
        return [CanvasSummary.model_validate(item) for item in metadata["canvases"]]


def delete_canvas(email: str, project_id: str, canvas_id: str) -> ProjectDetail:
    with _lock:
        project_root = _project_root(email, project_id)
        metadata = _read_json(project_root / "project.json", None)
        if metadata is None:
            raise FileNotFoundError(project_id)
        metadata, canvases = _ensure_canvas_manifest(project_root, metadata)
        if len(canvases) == 1:
            raise ValueError("A project must keep at least one canvas")
        if not any(item.id == canvas_id for item in canvases):
            raise FileNotFoundError(canvas_id)
        remaining = [item for item in canvases if item.id != canvas_id]
        _delete_json(_canvas_path(project_root, canvas_id))
        if metadata["active_canvas_id"] == canvas_id:
            metadata["active_canvas_id"] = remaining[0].id
            active = get_project_canvas(email, project_id, remaining[0].id)
            _write_json(project_root / "canvas.json", active.model_dump(mode="json"))
        metadata["canvases"] = [item.model_dump(mode="json") for item in remaining]
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(project_root / "project.json", metadata)
        return get_project(email, project_id)


def assets_root(email: str, project_id: str) -> Path:
    project_root = _project_root(email, project_id)
    if _read_json(project_root / "project.json", None) is None:
        raise FileNotFoundError(project_id)
    path = project_root / "assets"
    path.mkdir(exist_ok=True)
    return path.resolve()


def safe_asset_path(root: Path, relative_path: str, *, allow_root: bool = False) -> Path:
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized and not allow_root:
        raise ValueError("Asset path is required")
    target = (root / normalized).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Asset path escapes the project")
    return target


def asset_mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def get_settings(email: str) -> VideoStudioSettings:
    value = _read_json(_user_root(email) / "settings.json", {})
    return VideoStudioSettings.model_validate(value)


def save_settings(email: str, value: VideoStudioSettings) -> VideoStudioSettings:
    with _lock:
        _write_json(_user_root(email) / "settings.json", value.model_dump(mode="json"))
    return value


_BUILTIN_SKILLS = [
    SkillDefinition(
        id="canvas",
        name="Canvas workflow",
        description="Plan and edit a node-based video workflow.",
        instructions="Use text, media, generation and director nodes. Preserve useful existing work and connect dependent steps.",
        builtin=True,
        order=0,
    ),
    SkillDefinition(
        id="storyboard",
        name="Storyboard",
        description="Turn an approved story and constraints into a reviewable shot plan.",
        instructions="For every shot specify purpose, visible action, composition, camera movement, sound and estimated duration. Mark missing facts as questions.",
        builtin=True,
        order=1,
    ),
    SkillDefinition(
        id="continuity",
        name="Continuity review",
        description="Check characters, props, space, movement and sound across shots.",
        instructions="Report concrete continuity problems with the affected shot and the smallest safe correction. Never claim to inspect media that does not exist.",
        builtin=True,
        order=2,
    ),
    SkillDefinition(
        id="ctv-reference-research",
        name="CTV reference research",
        description="Build a small, traceable reference set before selecting a video direction.",
        instructions="""Confirm the product, market, delivery surface and conversion goal. Search YouTube, Meta Ads Library or Instagram, and TikTok first; use other sources only for a documented gap. Start with five samples total, not five per platform. Save the result to research/video-sample-table.md with direct URL, access date, platform and format, observable hook, product proof, CTA, public signals, CTV-fit notes, and what may be abstracted without copying. A search title or snippet is discovery evidence only: never claim a first-two-second hook or frame-level observation unless the media or screenshots were actually attached and inspected. Do not combine unlike platform metrics into a cross-platform performance ranking. Stop at five when they support a clear decision; expand only for a documented decision gap or an explicit full-audit request.""",
        builtin=True,
        order=3,
    ),
    SkillDefinition(
        id="brand-product-intake",
        name="Brand and product intake",
        description="Collect source-backed brand, product, claim and asset facts from an authorized public site.",
        instructions="""Confirm the market, channel, conversion goal and the client's authorization scope. Read only public pages the user is authorized to use; never bypass login, paywalls, robots controls or download protection. Review brand, FAQ, support and policy pages, then create a three-to-five SKU candidate pool using an explicit rule. Do not rename review count as sales. For the chosen product, record every usable claim with its first-party URL, access date and status; label price, inventory, promotion and review counts as volatile. Record asset source and rights status separately from technical availability. Save the Brand/Product Asset Manifest to intake/brand-product-asset-manifest.md and supporting URLs to intake/source-log.md. State unresolved rights, claims and missing-media questions rather than inventing them.""",
        builtin=True,
        order=4,
    ),
    SkillDefinition(
        id="ctv-creative-strategy",
        name="CTV creative strategy",
        description="Turn approved research and first-party product facts into a production-ready creative system.",
        instructions="""Read research/video-sample-table.md and intake/brand-product-asset-manifest.md before proposing a direction. Convert observations into reusable mechanisms, never a competitor's wording, visual identity, shot sequence, music or unsupported claim. Save recurring hooks, proof patterns, format distribution, unresolved objections and evidence-backed recommendations to research/creative-synthesis.md. Recommend distinct jobs for a 16:9 CTV master, 6/15-second proof cutdowns and creator-native variants; use narrative only when a real human tension adds value. Before scripts, storyboards or generation nodes, write production/approved-brief.md with target, verified facts and URLs, tension, promise, visible proof, 0-2 second opening, structure, CTA, exclusions and variants. If the hook, authoritative claim sources, producible proof, large-screen readability, CTA, rights status or approval is missing, stop and ask for it instead of starting generation.""",
        builtin=True,
        order=5,
    ),
]

_BUILTIN_EXTENSIONS = [
    *[
        ExtensionDefinition(id=f"node-{kind.lower()}", category="node", name=name, description=description, builtin=True)
        for kind, name, description in [
            ("text", "Text", "Scripts, briefs and notes."),
            ("image", "Image", "Uploaded or generated image media."),
            ("video", "Video", "Uploaded or generated video media."),
            ("audio", "Audio", "Soundtrack and voice media."),
            ("imageGeneration", "Image generation", "Vertex image generation request."),
            ("videoGeneration", "Video generation", "Vertex video generation request."),
            ("director3d", "3D director", "Camera and blocking direction."),
        ]
    ],
    *[
        ExtensionDefinition(id=f"tool-{tool}", category="tool", name=name, description=description, builtin=True)
        for tool, name, description in [
            ("canvas", "Canvas", "Read and update the current workflow."),
            ("workspace", "Workspace", "Read and manage project assets."),
            ("media-generation", "Media generation", "Use deployment-managed Vertex media generation."),
            ("web-fetch", "Web fetch", "Fetch an explicitly supplied reference URL."),
            ("web-search", "Web search", "Search external references when the host enables it."),
            ("ask-user", "Ask user", "Request missing production constraints."),
        ]
    ],
    ExtensionDefinition(id="agent-workflow", category="agent", name="Workflow agent", description="Plans and edits the canvas.", builtin=True),
    ExtensionDefinition(id="agent-storyboard", category="agent", name="Storyboard team", description="Director, writer and continuity reviewer roles.", builtin=True),
]


def get_document(email: str, project_id: str) -> ProjectDocument:
    project_root = _project_root(email, project_id)
    if not (project_root / "project.json").is_file():
        raise FileNotFoundError(project_id)
    return ProjectDocument.model_validate(_read_json(project_root / "document.json", {}))


def save_document(email: str, project_id: str, value: ProjectDocument) -> ProjectDocument:
    with _lock:
        project_root = _project_root(email, project_id)
        if not (project_root / "project.json").is_file():
            raise FileNotFoundError(project_id)
        saved = value.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        _write_json(project_root / "document.json", saved.model_dump(mode="json"))
        return saved


def _custom_catalog(email: str) -> CatalogImport:
    return CatalogImport.model_validate(_read_json(_user_root(email) / "catalog.json", {}))


def get_catalog(email: str) -> CatalogSnapshot:
    custom = _custom_catalog(email)
    skill_overrides = {item.id: item for item in custom.skills}
    extension_overrides = {item.id: item for item in custom.extensions}
    skills = [skill_overrides.pop(item.id, item) for item in _BUILTIN_SKILLS]
    skills.extend(skill_overrides.values())
    extensions = [extension_overrides.pop(item.id, item) for item in _BUILTIN_EXTENSIONS]
    extensions.extend(extension_overrides.values())
    return CatalogSnapshot(
        skills=sorted(skills, key=lambda item: (item.order, item.name.lower())),
        extensions=sorted(extensions, key=lambda item: (item.category, item.name.lower())),
    )


def save_catalog(email: str, value: CatalogImport) -> CatalogSnapshot:
    builtin_skill_ids = {item.id for item in _BUILTIN_SKILLS}
    builtin_extension_ids = {item.id for item in _BUILTIN_EXTENSIONS}
    normalized = CatalogImport(
        skills=[
            item.model_copy(update={"builtin": item.id in builtin_skill_ids})
            for item in value.skills
        ],
        extensions=[
            item.model_copy(update={"builtin": item.id in builtin_extension_ids})
            for item in value.extensions
        ],
    )
    with _lock:
        _write_json(_user_root(email) / "catalog.json", normalized.model_dump(mode="json"))
    return get_catalog(email)


def _conversation_path(email: str, project_id: str, conversation_id: str) -> Path:
    if not _PROJECT_ID.fullmatch(conversation_id):
        raise ValueError("Invalid conversation id")
    project_root = _project_root(email, project_id)
    if not (project_root / "project.json").is_file():
        raise FileNotFoundError(project_id)
    return project_root / "conversations" / f"{conversation_id}.json"


def list_conversations(email: str, project_id: str) -> list[AgentConversation]:
    project_root = _project_root(email, project_id)
    if not (project_root / "project.json").is_file():
        raise FileNotFoundError(project_id)
    root = project_root / "conversations"
    if not root.exists():
        return []
    conversations = [
        AgentConversation.model_validate(_read_json(path, {}))
        for path in root.glob("*.json")
        if _PROJECT_ID.fullmatch(path.stem)
    ]
    return sorted(conversations, key=lambda item: item.updated_at, reverse=True)


def get_conversation(email: str, project_id: str, conversation_id: str) -> AgentConversation:
    value = _read_json(_conversation_path(email, project_id, conversation_id), None)
    if value is None:
        raise FileNotFoundError(conversation_id)
    return AgentConversation.model_validate(value)


def save_conversation(email: str, project_id: str, value: AgentConversation) -> AgentConversation:
    with _lock:
        value.updated_at = datetime.now(timezone.utc)
        _write_json(
            _conversation_path(email, project_id, value.id),
            value.model_dump(mode="json"),
        )
    return value


def delete_conversation(email: str, project_id: str, conversation_id: str) -> None:
    with _lock:
        path = _conversation_path(email, project_id, conversation_id)
        if not path.is_file():
            raise FileNotFoundError(conversation_id)
        _delete_json(path)


def _export_job_path(email: str, project_id: str, job_id: str) -> Path:
    if not _PROJECT_ID.fullmatch(job_id):
        raise ValueError("Invalid export job id")
    project_root = _project_root(email, project_id)
    if not (project_root / "project.json").is_file():
        raise FileNotFoundError(project_id)
    return project_root / "export-jobs" / f"{job_id}.json"


def save_export_job(email: str, value: ExportJob) -> ExportJob:
    with _lock:
        saved = value.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        _write_json(
            _export_job_path(email, value.project_id, value.id),
            saved.model_dump(mode="json"),
        )
        return saved


def get_export_job(email: str, project_id: str, job_id: str) -> ExportJob:
    value = _read_json(_export_job_path(email, project_id, job_id), None)
    if value is None:
        raise FileNotFoundError(job_id)
    return ExportJob.model_validate(value)


def list_export_jobs(email: str, project_id: str) -> list[ExportJob]:
    project_root = _project_root(email, project_id)
    if not (project_root / "project.json").is_file():
        raise FileNotFoundError(project_id)
    root = project_root / "export-jobs"
    if not root.exists():
        return []
    values = [ExportJob.model_validate(_read_json(path, {})) for path in root.glob("*.json")]
    return sorted(values, key=lambda item: item.created_at, reverse=True)


def _media_job_path(email: str, project_id: str, job_id: str) -> Path:
    if not _PROJECT_ID.fullmatch(job_id):
        raise ValueError("Invalid media job id")
    project_root = _project_root(email, project_id)
    if not (project_root / "project.json").is_file():
        raise FileNotFoundError(project_id)
    return project_root / "media-jobs" / f"{job_id}.json"


def save_media_job(email: str, value: MediaJob) -> MediaJob:
    with _lock:
        saved = value.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        _write_json(
            _media_job_path(email, value.project_id, value.id),
            saved.model_dump(mode="json"),
        )
        return saved


def get_media_job(email: str, project_id: str, job_id: str) -> MediaJob:
    value = _read_json(_media_job_path(email, project_id, job_id), None)
    if value is None:
        raise FileNotFoundError(job_id)
    return MediaJob.model_validate(value)


def list_media_jobs(email: str, project_id: str) -> list[MediaJob]:
    project_root = _project_root(email, project_id)
    if not (project_root / "project.json").is_file():
        raise FileNotFoundError(project_id)
    root = project_root / "media-jobs"
    if not root.exists():
        return []
    values = [MediaJob.model_validate(_read_json(path, {})) for path in root.glob("*.json")]
    return sorted(values, key=lambda item: item.created_at, reverse=True)


def get_production_state(email: str, project_id: str) -> ProductionState:
    project_root = _project_root(email, project_id)
    if _read_json(project_root / "project.json", None) is None:
        raise FileNotFoundError(project_id)
    return ProductionState.model_validate(_read_json(project_root / "production.json", {}))


def save_production_state(email: str, project_id: str, value: ProductionState) -> ProductionState:
    with _lock:
        project_root = _project_root(email, project_id)
        if _read_json(project_root / "project.json", None) is None:
            raise FileNotFoundError(project_id)
        shot_ids = {shot.id for shot in value.shots}
        if len(shot_ids) != len(value.shots):
            raise ValueError("Production shot ids must be unique")
        for shot in value.shots:
            keyframe_ids = {keyframe.id for keyframe in shot.keyframes}
            if len(keyframe_ids) != len(shot.keyframes):
                raise ValueError(f"Production keyframe ids must be unique: {shot.id}")
            if shot.selected_keyframe_id and shot.selected_keyframe_id not in keyframe_ids:
                raise ValueError(f"Selected keyframe does not belong to shot: {shot.id}")
            take_ids = {take.id for take in shot.takes}
            if shot.selected_take_id and shot.selected_take_id not in take_ids:
                raise ValueError(f"Selected take does not belong to shot: {shot.id}")
        for clip in value.timeline:
            if clip.shot_id not in shot_ids:
                raise ValueError(f"Timeline references an unknown shot: {clip.shot_id}")
        saved = value.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        _write_json(project_root / "production.json", saved.model_dump(mode="json"))
        return saved


def commit_script(email: str, project_id: str, body: ScriptCommit) -> ProductionState:
    with _lock:
        state = get_production_state(email, project_id)
        revision = state.script_revision + 1
        snapshot = ScriptRevision(
            id=uuid.uuid4().hex,
            revision=revision,
            content=body.content,
        )
        event = ProductionAuditEvent(
            id=uuid.uuid4().hex,
            kind="script_locked",
            detail=f"Locked script revision {revision}",
        )
        return save_production_state(
            email,
            project_id,
            state.model_copy(
                update={
                    "script_locked": True,
                    "script_revision": revision,
                    "script_revisions": [*state.script_revisions[-99:], snapshot],
                    "audit_events": [event, *state.audit_events][:1_000],
                    "qa": QAReport(),
                }
            ),
        )


def unlock_script(email: str, project_id: str) -> ProductionState:
    with _lock:
        state = get_production_state(email, project_id)
        if not state.script_locked:
            return state
        event = ProductionAuditEvent(
            id=uuid.uuid4().hex,
            kind="script_unlocked",
            detail=f"Unlocked script revision {state.script_revision}",
        )
        return save_production_state(
            email,
            project_id,
            state.model_copy(
                update={
                    "script_locked": False,
                    "audit_events": [event, *state.audit_events][:1_000],
                    "qa": QAReport(),
                }
            ),
        )


def commit_timeline(email: str, project_id: str, body: TimelineCommit) -> ProductionState:
    with _lock:
        state = get_production_state(email, project_id)
        revision = state.revision + 1
        checkpoint = TimelineRevision(
            id=uuid.uuid4().hex,
            revision=revision,
            label=body.label.strip(),
            clips=state.timeline,
        )
        event = ProductionAuditEvent(
            id=uuid.uuid4().hex,
            kind="timeline_committed",
            detail=f"Committed timeline revision {revision}: {checkpoint.label}",
        )
        return save_production_state(
            email,
            project_id,
            state.model_copy(
                update={
                    "revision": revision,
                    "timeline_revisions": [*state.timeline_revisions[-99:], checkpoint],
                    "audit_events": [event, *state.audit_events][:1_000],
                }
            ),
        )


def run_production_qa(email: str, project_id: str) -> ProductionState:
    state = get_production_state(email, project_id)
    root = assets_root(email, project_id)
    shots = {shot.id: shot for shot in state.shots}
    blockers: list[str] = []
    warnings: list[str] = []
    included = [clip for clip in state.timeline if clip.included]
    if not state.script_locked or state.script_revision < 1:
        blockers.append("Script has not been locked")
    if state.revision < 1:
        blockers.append("Timeline has not been committed")
    if not included:
        blockers.append("Timeline has no included clips")
    for clip in included:
        shot = shots.get(clip.shot_id)
        if not shot:
            blockers.append(f"Unknown shot in timeline: {clip.shot_id}")
            continue
        take = next((item for item in shot.takes if item.id == shot.selected_take_id), None)
        if not take:
            blockers.append(f"{shot.title}: no selected take")
            continue
        keyframe = next(
            (item for item in shot.keyframes if item.id == shot.selected_keyframe_id),
            None,
        )
        if not keyframe or keyframe.status != "approved":
            blockers.append(f"{shot.title}: no approved keyframe")
        else:
            try:
                keyframe_asset = safe_asset_path(root, keyframe.asset_path)
            except ValueError:
                blockers.append(f"{shot.title}: unsafe keyframe path")
            else:
                if not keyframe_asset.is_file():
                    blockers.append(f"{shot.title}: approved keyframe is missing")
        try:
            asset = safe_asset_path(root, take.asset_path)
        except ValueError:
            blockers.append(f"{shot.title}: unsafe asset path")
            continue
        if not asset.is_file():
            blockers.append(f"{shot.title}: selected asset is missing")
        if shot.status != "approved":
            warnings.append(f"{shot.title}: shot is not approved")
    total_duration = sum(clip.duration for clip in included)
    if total_duration <= 0:
        blockers.append("Timeline duration must be greater than zero")
    issues = [*blockers, *warnings]
    status = "blocked" if blockers else "warning" if warnings else "pass"
    event = ProductionAuditEvent(
        id=uuid.uuid4().hex,
        kind="qa_completed",
        detail=f"QA {status}: {len(issues)} issue(s)",
    )
    return save_production_state(
        email,
        project_id,
        state.model_copy(
            update={
                "qa": QAReport(
                    status=status,
                    issues=issues,
                    checked_at=datetime.now(timezone.utc),
                ),
                "audit_events": [event, *state.audit_events][:1_000],
            }
        ),
    )


def record_delivery(email: str, project_id: str, body: DeliveryCreate) -> ProductionState:
    with _lock:
        state = get_production_state(email, project_id)
        root = assets_root(email, project_id)
        target = safe_asset_path(root, body.asset_path)
        if not target.is_file():
            raise FileNotFoundError(body.asset_path)
        payload = target.read_bytes()
        delivery = DeliveryManifest(
            id=uuid.uuid4().hex,
            asset_path=body.asset_path,
            mime_type=asset_mime_type(target),
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            timeline_revision=state.revision,
        )
        event = ProductionAuditEvent(
            id=uuid.uuid4().hex,
            kind="delivery_recorded",
            detail=f"Recorded delivery {body.asset_path}",
        )
        return save_production_state(
            email,
            project_id,
            state.model_copy(
                update={
                    "deliveries": [delivery, *state.deliveries][:100],
                    "audit_events": [event, *state.audit_events][:1_000],
                }
            ),
        )
