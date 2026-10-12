from __future__ import annotations

import asyncio
import base64
import json
import re
import mimetypes
import shutil
import time
import uuid
import threading
import hashlib
from datetime import timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.incept.config import get_settings as get_deployment_settings
from app.routers.video_runtime import (
    ManagedMediaRequest,
    _chat_stream,
    configured_media_models,
    configured_text_models,
    generate_media,
    validate_media_model,
)
from app.services.auth import require_internal_key
from app.video_studio import store, pi_http
from app.video_studio.pi_runs import RunJournal, control_target, answer as answer_pi_question
from app.video_studio.pi_capabilities import capabilities, validate_thinking
from app.video_studio.pi_business import BusinessTools
from app.video_studio.pi_agent import run_agent
from app.video_studio.agent_turns import AgentBusy, prepare_turn, cancel_turn, agent_error_message
from app.video_studio.media_jobs import cancel_media_job, create_media_job, ensure_media_job_running
from app.video_studio.models import AgentConversation, CanvasDocument, MediaJobCreate, Position, ProjectCreate, ProjectUpdate, VideoEdge, VideoNode
from app.video_studio.workspace_documents import DocumentConflict, TextEncoding, text_snapshot, write_document, document_lock, MAX_TEXT_BYTES
from app.video_studio.workspace_uploads import read_bounded, write_stream
from app.video_studio.workspace_copy import copy_workspace_file
from app.video_studio.image_edits import MaskedEditRequest, masked_image_edit
from app.video_studio.website_assets import (
    WebsiteDiscoverRequest, WebsiteImportRequest, discover_website_assets,
    import_website_assets, list_website_assets,
)
from app.video_studio.creative_specs import moloco_ctv_profile, validate_moloco_ctv_video


router = APIRouter(
    prefix="/video-legacy/api",
    tags=["video-legacy"],
    dependencies=[Depends(require_internal_key)],
)


def current_user(x_user_email: str = Header(default="")) -> str:
    email = x_user_email.strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail={"message": "Authenticated LinglongLab user required"})
    return email


def success(data: Any = None, message: str = "") -> dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def fail(error: Exception) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=404, detail={"code": "ENOENT", "message": "项目或文件不存在"})
    if isinstance(error, FileExistsError):
        return HTTPException(status_code=409, detail={"code": "EEXIST", "message": "已存在同名文件或目录"})
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail={"code": "EINVAL", "message": str(error)})
    return HTTPException(status_code=500, detail={"code": "EIO", "message": "视频工作区操作失败"})


def _project_id(directory: str) -> str:
    value = directory.strip()
    if len(value) != 32 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("无效的云端项目 ID")
    return value


def _workspace_root(email: str, directory: str) -> Path:
    return store.assets_root(email, _project_id(directory))


def _workspace_path(email: str, directory: str, path: str, *, allow_root: bool = False) -> Path:
    return store.safe_asset_path(_workspace_root(email, directory), path, allow_root=allow_root)


def _write_bytes(target: Path, payload: bytes, *, exclusive: bool = False) -> None:
    write_document(target, payload, exclusive=exclusive)


def _legacy_canvas() -> dict[str, Any]:
    return {
        "linglonglabVideoCanvas": True,
        "nodes": [],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


_VUE_NODE_TYPES = {
    "audioNode": "audio",
    "director3dNode": "director3d",
    "imageNode": "image",
    "imageGenerationNode": "imageGeneration",
    "textNode": "text",
    "videoNode": "video",
    "videoGenerationNode": "videoGeneration",
}
_FASTAPI_NODE_TYPES = {value: f"remote-{key}" for key, value in _VUE_NODE_TYPES.items()}


def _vue_canvas_document(payload: bytes) -> CanvasDocument | None:
    """Decode a Vue snapshot without selecting a project or writing its canvas."""
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(value, dict) or value.get("linglonglabVideoCanvas") is not True:
        return
    nodes: list[VideoNode] = []
    for item in (value.get("nodes") if isinstance(value.get("nodes"), list) else []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        original_type = str(item.get("type") or "")
        vue_type = original_type.removeprefix("remote-")
        node_type = _VUE_NODE_TYPES.get(vue_type, original_type)
        if not node_type:
            continue
        position = item.get("position") if isinstance(item.get("position"), dict) else {}
        nodes.append(VideoNode(
            id=str(item["id"]),
            type=node_type,
            position=Position(x=float(position.get("x") or 0), y=float(position.get("y") or 0)),
            data=item.get("data") if isinstance(item.get("data"), dict) else {},
            vue_type=original_type,
            vue_attributes={key: value for key, value in item.items() if key not in {"id", "type", "position", "data"}},
        ))
    node_ids = {node.id for node in nodes}
    edges: list[VideoEdge] = []
    for item in (value.get("edges") if isinstance(value.get("edges"), list) else []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        source, target = str(item.get("source") or ""), str(item.get("target") or "")
        if source not in node_ids or target not in node_ids:
            continue
        edges.append(VideoEdge(
            id=str(item["id"]),
            source=source,
            target=target,
            source_handle=item.get("sourceHandle"),
            target_handle=item.get("targetHandle"),
            vue_attributes={key: value for key, value in item.items() if key not in {"id", "source", "target"}},
        ))
    viewport = value.get("viewport") if isinstance(value.get("viewport"), dict) else {"x": 0, "y": 0, "zoom": 1}
    return CanvasDocument(nodes=nodes, edges=edges, viewport=viewport)


def _sync_vue_canvas(email: str, project_id: str, payload: bytes, *, canvas_id: str | None = None) -> None:
    canvas = _vue_canvas_document(payload)
    if canvas is None:
        return
    if canvas_id is None:
        store.save_canvas(email, project_id, canvas)
    else:
        store.save_project_canvas(email, project_id, canvas_id, canvas)


def _vue_canvas_snapshot(canvas: CanvasDocument) -> dict[str, Any]:
    return {
        "nodes": [
            {
                **node.vue_attributes,
                "id": node.id,
                "type": node.vue_type or _FASTAPI_NODE_TYPES.get(node.type, node.type),
                "position": node.position.model_dump(),
                "data": node.data,
            }
            for node in canvas.nodes
        ],
        "edges": [
            {
                **edge.vue_attributes,
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                **({"sourceHandle": edge.source_handle} if edge.source_handle is not None or "sourceHandle" in edge.vue_attributes else {}),
                **({"targetHandle": edge.target_handle} if edge.target_handle is not None or "targetHandle" in edge.vue_attributes else {}),
            }
            for edge in canvas.edges
        ],
        "viewport": canvas.viewport,
    }


class WorkspaceCreate(BaseModel):
    name: str = Field(default="未命名项目", min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)


class WorkspaceRename(BaseModel):
    directory: str
    name: str = Field(min_length=1, max_length=120)


class WorkspaceMutation(BaseModel):
    directory: str
    path: str


class WorkspaceRenameFile(WorkspaceMutation):
    target: str


class WorkspaceRemove(WorkspaceMutation):
    recursive: bool = False


class SettingsBody(BaseModel):
    settings: dict[str, Any]


def _project_payload(project: Any) -> dict[str, Any]:
    return {
        "directory": project.id,
        "name": project.name,
        "lastOpenedAt": int(project.updated_at.timestamp() * 1000),
    }


@router.get("/workspaces/projects")
def list_workspace_projects(email: str = Depends(current_user)) -> dict[str, Any]:
    return success([_project_payload(project) for project in store.list_projects(email)])


@router.post("/workspaces/create")
def create_workspace(body: WorkspaceCreate, email: str = Depends(current_user)) -> dict[str, Any]:
    project = store.create_project(email, ProjectCreate(name=body.name, description=body.description))
    _write_bytes(store.assets_root(email, project.id) / "画布1.json", (json.dumps(_legacy_canvas(), ensure_ascii=False, indent=2) + "\n").encode())
    return success(_project_payload(project))


@router.patch("/workspaces/project")
def rename_workspace(body: WorkspaceRename, email: str = Depends(current_user)) -> dict[str, Any]:
    project = store.update_project(email, _project_id(body.directory), ProjectUpdate(name=body.name))
    return success(_project_payload(project))


@router.delete("/workspaces/project")
def delete_workspace(directory: str = Query(), email: str = Depends(current_user)) -> dict[str, Any]:
    project_id = _project_id(directory)
    store.delete_project(email, project_id)
    return success()


@router.get("/workspaces/check")
def check_workspace(directory: str = Query(), email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        project = store.get_project(email, _project_id(directory))
        return success({"directory": project.id})
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.get("/workspaces/list")
def list_workspaces(path: str = Query(default=""), email: str = Depends(current_user)) -> dict[str, Any]:
    del path
    projects = [_project_payload(project) for project in store.list_projects(email)]
    return success({"directory": "", "native": False, "empty": not projects, "entries": projects})


@router.post("/workspaces/selectDirectory")
def select_workspace() -> dict[str, Any]:
    return success({"native": False, "directory": None}, "浏览器版本使用云端项目，不选择本地文件夹")


@router.get("/workspaces/files/list")
def list_workspace_files(
    directory: str = Query(),
    path: str = Query(default=""),
    email: str = Depends(current_user),
) -> dict[str, Any]:
    try:
        root = _workspace_root(email, directory)
        target = store.safe_asset_path(root, path, allow_root=True)
        if not target.is_dir():
            raise FileNotFoundError(path)
        entries = [
            {
                "name": entry.name,
                "path": entry.relative_to(root).as_posix(),
                "type": "directory" if entry.is_dir() else "file",
            }
            for entry in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
            if entry.is_dir() or entry.is_file()
        ]
        return success({"directory": directory, "empty": not entries, "entries": entries})
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.get("/workspaces/files/read")
def read_workspace_file(
    request: Request,
    response: Response,
    directory: str = Query(),
    path: str = Query(),
    snapshot: bool = Query(default=False),
    maxBytes: int = Query(default=5 * 1024 * 1024, ge=1, le=5 * 1024 * 1024),
    email: str = Depends(current_user),
):
    response.headers['Cache-Control'] = 'no-store'
    try:
        target = _workspace_path(email, directory, path)
        if not target.is_file():
            raise FileNotFoundError(path)
        if snapshot:
            return success(text_snapshot(target, maxBytes))
        range_header = request.headers.get("range")
        if not range_header:
            return FileResponse(target, media_type=store.asset_mime_type(target), headers={'Cache-Control': 'no-store'})
        size = target.stat().st_size
        if not range_header.startswith("bytes=0-"):
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        end_text = range_header.removeprefix("bytes=0-")
        end = min(int(end_text), max(0, size - 1))
        if size == 0:
            return Response(status_code=416, headers={"Content-Range": "bytes */0"})
        payload = target.read_bytes()[: end + 1]
        return Response(
            payload,
            status_code=206,
            media_type=store.asset_mime_type(target),
            headers={"Content-Range": f"bytes 0-{end}/{size}", "Accept-Ranges": "bytes", "Cache-Control": "no-store"},
        )
    except OverflowError as error:
        raise HTTPException(status_code=413, detail={"message": str(error)}) from error
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.put("/workspaces/files/write")
async def write_workspace_file(
    request: Request,
    directory: str = Query(),
    path: str = Query(),
    exclusive: bool = Query(default=False),
    expectedRevision: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$"),
    encoding: TextEncoding | None = Query(default=None),
    email: str = Depends(current_user),
) -> dict[str, Any]:
    try:
        target = _workspace_path(email, directory, path)
        revision = None
        if expectedRevision or encoding:
            payload = await read_bounded(request.stream(), MAX_TEXT_BYTES)
            revision = write_document(target, payload, exclusive=exclusive, expected_revision=expectedRevision, encoding=encoding)
        else:
            await write_stream(target, request.stream(), exclusive=exclusive)
        if path.lower().endswith(".json") and target.stat().st_size <= MAX_TEXT_BYTES:
            _sync_vue_canvas(email, _project_id(directory), target.read_bytes())
        return success({"revision": revision} if expectedRevision else None)
    except DocumentConflict as error:
        raise HTTPException(status_code=409, detail={"code": "ESTALE", "message": str(error)}) from error
    except OverflowError as error:
        raise HTTPException(status_code=413, detail={"message": str(error)}) from error
    except HTTPException:
        raise
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.post("/workspaces/files/mkdir")
def make_workspace_directory(body: WorkspaceMutation, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        target = _workspace_path(email, body.directory, body.path)
        if target.is_dir():
            return success()
        target.mkdir(parents=True, exist_ok=False)
        return success()
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.post("/workspaces/files/rename")
def rename_workspace_file(body: WorkspaceRenameFile, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        source = _workspace_path(email, body.directory, body.path)
        target = _workspace_path(email, body.directory, body.target)
        if not source.exists():
            raise FileNotFoundError(body.path)
        if target.exists():
            raise FileExistsError(body.target)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        return success()
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.post("/workspaces/files/copy")
def copy_workspace_entry(body: WorkspaceRenameFile, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        copy_workspace_file(_workspace_root(email, body.directory), body.path, body.target)
        return success()
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.delete("/workspaces/files/remove")
def remove_workspace_file(body: WorkspaceRemove, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        target = _workspace_path(email, body.directory, body.path)
        if target.is_dir():
            if body.recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()
        elif target.is_file():
            target.unlink()
        else:
            raise FileNotFoundError(body.path)
        return success()
    except (FileNotFoundError, OSError, ValueError) as error:
        raise fail(error) from error


def _legacy_settings_path(email: str) -> Path:
    return store._user_root(email) / "legacy-settings.json"  # noqa: SLF001 - same storage boundary


def _asset_library_root(email: str, directory: str) -> Path:
    root = _workspace_root(email, directory) / "library"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _asset_library_path(email: str, directory: str, path: str, *, allow_root: bool = False) -> Path:
    return store.safe_asset_path(_asset_library_root(email, directory), path, allow_root=allow_root)


def _asset_entries(root: Path, current: Path) -> list[dict[str, Any]]:
    return [
        {
            "name": entry.name,
            "path": entry.relative_to(root).as_posix(),
            "type": "directory" if entry.is_dir() else "file",
            **({"children": _asset_entries(root, entry)} if entry.is_dir() else {}),
        }
        for entry in sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        if entry.is_dir() or entry.is_file()
    ]


@router.get("/assets/list")
def list_asset_library(directory: str = Query(), email: str = Depends(current_user)) -> dict[str, Any]:
    root = _asset_library_root(email, directory)
    return success({"entries": _asset_entries(root, root)})


@router.get("/assets/creative-profile")
def creative_profile(email: str = Depends(current_user)) -> dict[str, Any]:
    return success(moloco_ctv_profile())


class CreativeCheckRequest(BaseModel):
    directory: str
    path: str = Field(min_length=1, max_length=1000)


@router.post("/assets/creative-check")
def check_creative_video(body: CreativeCheckRequest, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        return success(validate_moloco_ctv_video(email, _project_id(body.directory), body.path))
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.get("/assets/website")
def website_asset_catalog(directory: str = Query(), offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200), email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        assets = list_website_assets(email, _project_id(directory))
        return success({"assets": assets[offset:offset + limit], "total": len(assets)})
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.post("/assets/website/discover")
def discover_client_assets(body: WebsiteDiscoverRequest, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        return success(discover_website_assets(email, _project_id(body.directory), body.url))
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.post("/assets/website/import")
def import_client_assets(body: WebsiteImportRequest, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        return success(import_website_assets(email, _project_id(body.directory), body.asset_ids))
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.get("/assets/read")
def read_asset_library(
    directory: str = Query(),
    path: str = Query(),
    download: bool = Query(default=False),
    email: str = Depends(current_user),
):
    try:
        target = _asset_library_path(email, directory, path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return FileResponse(target, media_type=store.asset_mime_type(target), filename=target.name if download else None)
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.put("/assets/save")
async def save_asset_library(
    request: Request,
    directory: str = Query(),
    path: str = Query(),
    email: str = Depends(current_user),
) -> dict[str, Any]:
    try:
        target = _asset_library_path(email, directory, path)
        payload = await request.body()
        _write_bytes(target, payload, exclusive=True)
        return success()
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.post("/assets/mkdir")
def make_asset_library_directory(body: WorkspaceMutation, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        target = _asset_library_path(email, body.directory, body.path)
        if not target.is_dir():
            target.mkdir(parents=True, exist_ok=False)
        return success()
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.post("/assets/rename")
def rename_asset_library(body: WorkspaceRenameFile, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        source = _asset_library_path(email, body.directory, body.path)
        target = _asset_library_path(email, body.directory, body.target)
        if not source.exists():
            raise FileNotFoundError(body.path)
        if target.exists():
            raise FileExistsError(body.target)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        return success()
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.delete("/assets/remove")
def remove_asset_library(body: WorkspaceMutation, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        target = _asset_library_path(email, body.directory, body.path)
        if target.is_dir():
            target.rmdir()
        elif target.is_file():
            target.unlink()
        else:
            raise FileNotFoundError(body.path)
        return success()
    except (FileNotFoundError, OSError, ValueError) as error:
        raise fail(error) from error


def _default_legacy_settings() -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for model in configured_text_models():
        key = (model["providerId"], model["providerLabel"], model["protocol"])
        grouped.setdefault(key, []).append({
            "id": model["modelId"],
            "label": model["label"],
            "contextWindow": model.get("contextWindow", 262144),
            "maxOutputTokens": model.get("maxOutputTokens", 32768),
            "isDefault": model.get("isDefault", False),
        })
    return {
        "ui": {"theme": "light", "primaryColor": "#6750A4", "fontScale": 100, "radius": 8, "startupAnimation": True, "language": "en"},
        "general": {"canvasCompositingEnabled": False, "canvasEdgeAnimationEnabled": True},
        "privacy": {"dataCollectionEnabled": False},
        "customProviders": [
            {"id": provider_id, "label": label, "apiUrl": "managed://linglonglab", "apiKey": "", "protocol": protocol, "models": models}
            for (provider_id, label, protocol), models in grouped.items()
        ],
        "mediaProviderConfigs": {},
        "stores": {},
    }


@router.get("/settings/get")
def get_legacy_settings(email: str = Depends(current_user)) -> dict[str, Any]:
    stored = store._read_json(_legacy_settings_path(email), {})  # noqa: SLF001
    defaults = _default_legacy_settings()
    value = {**defaults, **stored}
    value["customProviders"] = defaults["customProviders"]
    value["privacy"] = {"dataCollectionEnabled": False}
    return success(value)


@router.put("/settings/save")
def save_legacy_settings(body: SettingsBody, email: str = Depends(current_user)) -> dict[str, Any]:
    defaults = _default_legacy_settings()
    value = {**body.settings, "customProviders": defaults["customProviders"], "privacy": {"dataCollectionEnabled": False}}
    store._write_json(_legacy_settings_path(email), value)  # noqa: SLF001
    return success(value)


_NODE_LABELS = {
    "audioNode": ("音频", "node-audio"),
    "director3dNode": ("3D 导演", "node-director3d"),
    "imageNode": ("图片", "node-image"),
    "imageGenerationNode": ("图片生成", "node-imagegeneration"),
    "textNode": ("文本", "node-text"),
    "videoNode": ("视频", "node-video"),
    "videoGenerationNode": ("视频生成", "node-videogeneration"),
}


@router.get("/nodes/get")
def get_nodes(email: str = Depends(current_user)) -> dict[str, Any]:
    enabled = {item.id for item in store.get_catalog(email).extensions if item.enabled}
    nodes = [
        {
            "name": name,
            "displayName": metadata[0],
            "url": f"/video-app/nodes/{name}.umd.js",
            "enabled": metadata[1] in enabled,
            "canConfigure": False,
            "config": {},
            "version": "2.0.0-incept",
            "author": "LinglongLab",
            "readme": "由 LinglongLab 部署统一管理。",
            "github": "",
            "configRules": [],
        }
        for name, metadata in _NODE_LABELS.items()
    ]
    return success(nodes)


@router.get("/tools/get")
def get_tools(email: str = Depends(current_user)) -> dict[str, Any]:
    catalog = store.get_catalog(email)
    tool_names = {
        "tool-ask-user": "askUser",
        "tool-canvas": "canvas",
        "tool-media-generation": "mediaGeneration",
        "tool-web-fetch": "webFetch",
        "tool-web-search": "webSearch",
        "tool-video-transcript": "videoTranscriptFetch",
        "tool-workspace": "workspace",
    }
    tools = [
        {
            "name": tool_names.get(item.id, item.id.removeprefix("tool-")),
            "displayName": item.name,
            "description": item.description,
            "enabled": item.enabled,
            "canConfigure": False,
            "config": item.config,
            "components": [],
            "version": "2.0.0-incept",
            "author": "LinglongLab",
            "readme": "由 LinglongLab FastAPI 后端提供。",
            "github": "",
            "configRules": [],
        }
        for item in catalog.extensions
        if item.category == "tool"
    ]
    return success({"tools": tools, "canManage": False})


@router.get("/tools/renderers")
def tool_renderers() -> dict[str, Any]:
    return success([])


@router.get("/ai/models")
def language_models() -> dict[str, Any]:
    return success([
        {**model, "contextWindow": 262144, "maxOutputTokens": 32768}
        for model in configured_text_models()
    ])


@router.get("/ai/media/models")
def media_models() -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for option in configured_media_models():
        provider = option["providerId"]
        model = option["modelId"]
        media_type = option["type"]
        provider_label = {
            "google-vertex-ai": "Google Vertex AI",
            "google-cloud-tts": "Google Cloud Text-to-Speech",
            "openai": "OpenAI",
        }[provider]
        if media_type == "image":
            values.append({
                "providerId": provider,
                "providerLabel": provider_label,
                "modelId": model,
                "label": model,
                "type": "image",
                "isDefault": option.get("isDefault", False),
                "imageSizes": ["1024x1024", "1536x1024", "1024x1536"] if provider == "openai" else ["1K", "2K"],
                "imageRatios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
            })
        elif media_type == "video":
            values.append({
                "providerId": provider,
                "providerLabel": provider_label,
                "modelId": model,
                "label": model,
                "type": "video",
                "isDefault": option.get("isDefault", False),
                "mode": ["text"],
                "durationResolutionMap": [{"duration": list(range(3, 11)), "resolution": ["360p", "720p", "1080p", "4k"]}],
                "audio": False,
            })
        else:
            values.append({
                "providerId": provider,
                "providerLabel": provider_label,
                "modelId": model,
                "label": model,
                "type": "audio",
                "isDefault": option.get("isDefault", False),
                "voices": ([{"title": "Alloy", "voice": "alloy"}] if provider == "openai" else [{"title": "Kore", "voice": "Kore"}, {"title": "Puck", "voice": "Puck"}]),
            })
    return success(values)


def _openai_context(context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    messages: list[dict[str, Any]] = []
    system_prompt = context.get("systemPrompt")
    if isinstance(system_prompt, str) and system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for item in (context.get("messages") if isinstance(context.get("messages"), list) else []):
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role == "user":
            messages.append({"role": "user", "content": content})
        elif role == "assistant":
            text = "".join(
                str(part.get("text") or "")
                for part in content if isinstance(content, list) and isinstance(part, dict) and part.get("type") == "text"
            )
            calls = [
                {
                    "id": str(part.get("id") or uuid.uuid4().hex),
                    "type": "function",
                    "function": {
                        "name": str(part.get("name") or "tool"),
                        "arguments": json.dumps(part.get("arguments") or {}, ensure_ascii=False),
                    },
                }
                for part in content if isinstance(content, list) and isinstance(part, dict) and part.get("type") == "toolCall"
            ]
            messages.append({"role": "assistant", "content": text, **({"tool_calls": calls} if calls else {})})
        elif role == "toolResult":
            text = "\n".join(
                str(part.get("text") or "")
                for part in content if isinstance(content, list) and isinstance(part, dict) and part.get("type") == "text"
            )
            messages.append({"role": "tool", "tool_call_id": str(item.get("toolCallId") or ""), "content": text})
    tools = [
        {
            "type": "function",
            "function": {
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                "parameters": item.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for item in (context.get("tools") if isinstance(context.get("tools"), list) else []) if isinstance(item, dict) and item.get("name")
    ]
    return messages, tools


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        str(item.get("text") or item.get("content") or "")
        for item in content if isinstance(content, list) and isinstance(item, dict) and item.get("type") in {"text", "input_text"}
    )


def _responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role in {"user", "assistant"}:
            text = _content_text(message.get("content"))
            if text:
                values.append({"role": role, "content": text})
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                if isinstance(function, dict):
                    values.append({
                        "type": "function_call",
                        "call_id": str(call.get("id") or f"call_{uuid.uuid4().hex}"),
                        "name": str(function.get("name") or "tool"),
                        "arguments": str(function.get("arguments") or "{}"),
                    })
        elif role == "tool":
            values.append({
                "type": "function_call_output",
                "call_id": str(message.get("tool_call_id") or ""),
                "output": _content_text(message.get("content")),
            })
    return values


def _anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "tool":
            values.append({"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": str(message.get("tool_call_id") or ""),
                "content": _content_text(message.get("content")),
            }]})
            continue
        if role not in {"user", "assistant"}:
            continue
        content: list[dict[str, Any]] = []
        text = _content_text(message.get("content"))
        if text:
            content.append({"type": "text", "text": text})
        for call in message.get("tool_calls") or []:
            function = call.get("function") if isinstance(call, dict) else None
            if not isinstance(function, dict):
                continue
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            content.append({
                "type": "tool_use",
                "id": str(call.get("id") or f"call_{uuid.uuid4().hex}"),
                "name": str(function.get("name") or "tool"),
                "input": arguments,
            })
        if content:
            values.append({"role": role, "content": content})
    return values


@router.post("/ai/generate")
def generate_text(body: dict[str, Any]) -> StreamingResponse:
    provider = str(body.get("providerId") or "")
    model = str(body.get("modelId") or "")
    configured = next(
        (item for item in configured_text_models() if item["providerId"] == provider and item["modelId"] == model),
        None,
    )
    if not configured:
        raise HTTPException(status_code=400, detail={"message": "所选文本模型未由当前部署启用"})
    context = body.get("context") if isinstance(body.get("context"), dict) else {}
    messages, tools = _openai_context(context)

    def events():
        text_parts: list[str] = []
        completed_calls: list[dict[str, Any]] = []
        stop_reason = "stop"
        try:
            if provider == "google-vertex-ai":
                tool_calls: dict[int, dict[str, Any]] = {}
                for raw in _chat_stream({"messages": messages, "tools": tools, "stream": True}, model_id=model):
                    if raw.strip() == "data: [DONE]":
                        break
                    payload = raw.removeprefix("data: ").strip()
                    if not payload:
                        continue
                    chunk = json.loads(payload)
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    if isinstance(delta.get("content"), str) and delta["content"]:
                        text_parts.append(delta["content"])
                        yield f"data: {json.dumps({'type': 'text', 'delta': delta['content']}, ensure_ascii=False)}\n\n"
                    for call in delta.get("tool_calls") or []:
                        index = int(call.get("index") or 0)
                        function = call.get("function") or {}
                        tool_calls[index] = {
                            "type": "toolCall",
                            "id": str(call.get("id") or f"call_{uuid.uuid4().hex}"),
                            "name": str(function.get("name") or "tool"),
                            "arguments": json.loads(function.get("arguments") or "{}"),
                        }
                    if choice.get("finish_reason") == "tool_calls":
                        stop_reason = "toolUse"
                completed_calls = [tool_calls[index] for index in sorted(tool_calls)]
            elif provider == "openai":
                deployment = get_deployment_settings()
                if not deployment.openai_api_key:
                    raise RuntimeError("OPENAI_API_KEY is not configured")
                from openai import OpenAI

                system = "\n\n".join(str(item["content"]) for item in messages if item.get("role") == "system")
                response = OpenAI(api_key=deployment.openai_api_key).responses.create(
                    model=model,
                    input=_responses_input(messages),
                    instructions=system or None,
                    tools=[{
                        "type": "function",
                        "name": tool["function"]["name"],
                        "description": tool["function"].get("description", ""),
                        "parameters": tool["function"].get("parameters", {"type": "object", "properties": {}}),
                    } for tool in tools] or None,
                    store=False,
                )
                if response.output_text:
                    text_parts.append(response.output_text)
                    yield f"data: {json.dumps({'type': 'text', 'delta': response.output_text}, ensure_ascii=False)}\n\n"
                for item in response.output:
                    if getattr(item, "type", "") != "function_call":
                        continue
                    completed_calls.append({
                        "type": "toolCall",
                        "id": str(getattr(item, "call_id", "") or f"call_{uuid.uuid4().hex}"),
                        "name": str(getattr(item, "name", "") or "tool"),
                        "arguments": json.loads(getattr(item, "arguments", "{}") or "{}"),
                    })
                stop_reason = "toolUse" if completed_calls else "stop"
            elif provider == "anthropic":
                deployment = get_deployment_settings()
                if not deployment.anthropic_api_key:
                    raise RuntimeError("ANTHROPIC_API_KEY is not configured")
                from anthropic import Anthropic

                system = "\n\n".join(str(item["content"]) for item in messages if item.get("role") == "system")
                response = Anthropic(api_key=deployment.anthropic_api_key).messages.create(
                    model=model,
                    max_tokens=32768,
                    system=system,
                    messages=_anthropic_messages(messages),
                    tools=[{
                        "name": tool["function"]["name"],
                        "description": tool["function"].get("description", ""),
                        "input_schema": tool["function"].get("parameters", {"type": "object", "properties": {}}),
                    } for tool in tools],
                )
                for block in response.content:
                    if getattr(block, "type", "") == "text":
                        value = str(getattr(block, "text", ""))
                        text_parts.append(value)
                        yield f"data: {json.dumps({'type': 'text', 'delta': value}, ensure_ascii=False)}\n\n"
                    elif getattr(block, "type", "") == "tool_use":
                        completed_calls.append({"type": "toolCall", "id": block.id, "name": block.name, "arguments": block.input})
                stop_reason = "toolUse" if completed_calls else "stop"
            content = ([{"type": "text", "text": "".join(text_parts)}] if text_parts else []) + completed_calls
            message = {
                "role": "assistant",
                "content": content,
                "api": configured["protocol"],
                "provider": provider,
                "model": model,
                "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0}},
                "stopReason": stop_reason,
                "timestamp": int(time.time() * 1000),
            }
            yield f"data: {json.dumps({'type': 'done', 'message': message}, ensure_ascii=False)}\n\n"
        except Exception as error:
            yield f"data: {json.dumps({'type': 'error', 'message': str(error)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ai/media/generate")
async def generate_managed_media(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    project_id = _project_id(str(body.get("directory") or ""))
    media_type = str(body.get("mediaType") or "")
    if media_type not in {"image", "audio"}:
        raise HTTPException(status_code=400, detail={"message": "不支持的媒体类型"})
    try:
        validate_media_model(media_type, str(body.get("providerId") or ""), str(body.get("modelId") or ""))
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"message": "所选媒体模型未由当前部署启用"})

    root = store.assets_root(email, project_id)

    def frame(path: Any) -> str | None:
        if not isinstance(path, str) or not path:
            return None
        target = store.safe_asset_path(root, path)
        if not target.is_file() or not store.asset_mime_type(target).startswith("image/"):
            raise ValueError("参考帧必须是项目中的图片")
        return base64.b64encode(target.read_bytes()).decode("ascii")

    images = body.get("images") if isinstance(body.get("images"), list) else []
    first_path = body.get("firstFrame") or (images[0].get("path") if images and isinstance(images[0], dict) else None)
    last_path = body.get("lastFrame")
    result = await generate_media(ManagedMediaRequest(
        media_type=media_type,
        provider_id=str(body.get("providerId") or ""),
        model_id=str(body.get("modelId") or ""),
        prompt=str(body.get("prompt") or ""),
        ratio=body.get("ratio"),
        size=body.get("size"),
        duration=body.get("duration"),
        first_frame=frame(first_path),
        last_frame=frame(last_path),
        voice=body.get("voice"),
        speed=body.get("speed"),
        format=body.get("format"),
    ))
    extension = {"image/png": ".png", "image/jpeg": ".jpg", "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/ogg": ".ogg"}.get(result.mime_type) or mimetypes.guess_extension(result.mime_type) or ".bin"
    output_directory = str(body.get("outputDirectory") or "generated")
    relative = f"{output_directory.strip('/')}/{media_type}-{uuid.uuid4().hex}{extension}"
    target = store.safe_asset_path(root, relative)
    _write_bytes(target, base64.b64decode(result.data, validate=True))
    return success([{"path": relative, "mimeType": result.mime_type, "mediaType": media_type}])


@router.post("/ai/media/inpaint")
async def inpaint_managed_image(body: MaskedEditRequest, email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        root = _workspace_root(email, body.directory)
        return success([await masked_image_edit(root, body)])
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


def _media_job_request(body: dict[str, Any]) -> tuple[str, MediaJobCreate]:
    project_id = _project_id(str(body.get("directory") or ""))
    first = body.get("firstFrame")
    last = body.get("lastFrame")
    images = body.get("images") if isinstance(body.get("images"), list) else []
    first_path = first.get("path") if isinstance(first, dict) else None
    if not first_path and images and isinstance(images[0], dict):
        first_path = images[0].get("path")
    last_path = last.get("path") if isinstance(last, dict) else None
    return project_id, MediaJobCreate(
        idempotency_key=str(body.get("idempotencyKey") or "") or None,
        media_type="video",
        provider_id=str(body.get("providerId") or ""),
        model_id=str(body.get("modelId") or ""),
        prompt=str(body.get("prompt") or ""),
        ratio=body.get("ratio"),
        duration=body.get("duration"),
        first_frame_path=first_path,
        last_frame_path=last_path,
        output_directory=str(body.get("outputDirectory") or "generated"),
        resolution=body.get("resolution"),
        generate_audio=body.get("generateAudio"),
    )


@router.post("/ai/media/jobs", status_code=202)
async def submit_legacy_media_job(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        project_id, request = _media_job_request(body)
        return success(create_media_job(email, project_id, request).model_dump(mode="json"))
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.get("/ai/media/jobs/{job_id}")
async def legacy_media_job(job_id: str, directory: str = Query(), email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        job = ensure_media_job_running(email, _project_id(directory), job_id)
        return success(job.model_dump(mode="json"))
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.delete("/ai/media/jobs/{job_id}")
async def cancel_legacy_media_job(job_id: str, directory: str = Query(), email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        job = cancel_media_job(email, _project_id(directory), job_id)
        return success(job.model_dump(mode="json"))
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


def _conversation_file(value: AgentConversation) -> str:
    return f"agent/{value.id}.json"


def _conversation_id(session_file: str | None) -> str | None:
    if not session_file:
        return None
    value = session_file.removeprefix('agent/').removesuffix('.json').removesuffix(".jsonl")
    return _project_id(value)


def _legacy_conversation(value: AgentConversation) -> dict[str, Any]:
    models = configured_text_models()
    default_model = next((model for model in models if model.get("isDefault")), models[0])
    selected_model = next(
        (model for model in models if model["providerId"] == value.provider_id and model["modelId"] == value.model_id),
        default_model,
    )
    return {
        "file": _conversation_file(value),
        "name": value.name,
        "messages": [
            {
                "id": message.id,
                "entryId": message.id if message.role == "user" else None,
                "role": message.role,
                "content": message.content,
                "attachments": message.attachments,
                "replyTo": next((item.id for item in reversed(value.messages[:index]) if item.role == 'user'), None) if message.role == 'assistant' else None,
                "parts": message.parts or ([{"id": message.id, "type": "text", "content": message.content}] if message.role == "assistant" else []),
                "report": message.report,
            }
            for index, message in enumerate(value.messages)
        ],
        "providerId": selected_model["providerId"],
        "modelId": selected_model["modelId"],
        "subAgents": value.sub_agents,
        "thinkingLevel": value.thinking_level,
        "stats": value.stats,
        "contextUsage": value.context_usage,
        "parentFile": value.parent_file,
        "running": value.run_status == 'running',
        "runId": value.run_id,
        "runStatus": value.run_status,
        "runError": value.run_error,
        "researchQuestion": value.research_question,
    }


@router.get("/agent/skills")
def list_agent_skills(directory: str = Query(), email: str = Depends(current_user)) -> dict[str, Any]:
    store.get_project(email, _project_id(directory))
    catalog = store.get_catalog(email)
    return success([
        {"name": skill.name, "description": skill.description}
        for skill in catalog.skills
        if skill.enabled
    ])


@router.post("/agent/create")
def create_conversation(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    project_id = _project_id(str(body.get("directory") or ""))
    store.get_project(email, project_id)
    conversation = AgentConversation(id=uuid.uuid4().hex, name="新对话")
    store.save_conversation(email, project_id, conversation)
    return success(_legacy_conversation(conversation))


@router.get("/agent/list")
def list_agent_history(directory: str = Query(), email: str = Depends(current_user)) -> dict[str, Any]:
    conversations = store.list_conversations(email, _project_id(directory))
    return success([
        {
            "file": _conversation_file(item),
            "name": item.name,
            "modified": item.updated_at.isoformat(),
            "messageCount": len(item.messages),
        }
        for item in conversations
    ])


@router.get("/agent/get")
def get_agent_conversation(
    directory: str = Query(),
    sessionFile: str = Query(),
    email: str = Depends(current_user),
) -> dict[str, Any]:
    try: value = store.get_conversation(email, _project_id(directory), _conversation_id(sessionFile) or "")
    except (FileNotFoundError,ValueError) as error: raise fail(error) from error
    base=_legacy_conversation(value)
    if value.run_id:
        try:
            base=pi_http.project_snapshot(RunJournal(email,_project_id(directory),value.id,value.run_id),base)
        except FileNotFoundError:
            pass
    return success(base)


@router.patch("/agent/rename")
def rename_agent_conversation(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        project_id = _project_id(str(body.get("directory") or ""))
        conversation_id = _conversation_id(str(body.get("sessionFile") or "")) or ""
        name = str(body.get("name") or "").strip()[:120]
        if not name:
            raise ValueError("对话名称不能为空")
        with document_lock(store._conversation_path(email, project_id, conversation_id)):
            value = store.get_conversation(email, project_id, conversation_id)
            if value.run_status == "running":
                raise HTTPException(status_code=409, detail={"message": "会话仍在处理中，请先停止或等待完成再修改。"})
            value.name = name
            store.save_conversation(email, project_id, value)
        return success({"name": value.name})
    except (ValueError, FileNotFoundError) as error:
        raise fail(error) from error


@router.delete("/agent/message")
def delete_agent_message(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        project_id = _project_id(str(body.get("directory") or ""))
        conversation_id = _conversation_id(str(body.get("sessionFile") or "")) or ""
        entry_ids = body.get("entryIds") or []
        if not isinstance(entry_ids, list) or not all(isinstance(item, str) and item for item in entry_ids):
            raise ValueError("消息 ID 必须为非空字符串数组")
        ids = set(entry_ids)
        reply_to = body.get("replyTo")
        if reply_to:
            if not isinstance(reply_to, str):
                raise ValueError("原消息 ID 无效")
            ids.add(reply_to)
        with document_lock(store._conversation_path(email, project_id, conversation_id)):
            value = store.get_conversation(email, project_id, conversation_id)
            if value.run_status == "running":
                raise HTTPException(status_code=409, detail={"message": "会话仍在处理中，请先停止或等待完成再删除消息。"})
            if not ids.issubset({message.id for message in value.messages}):
                raise ValueError("消息已不存在，请重新载入会话")
            retained = []
            last_user_id = None
            for message in value.messages:
                if message.role == "user":
                    last_user_id = message.id
                if message.id not in ids and not (message.role == "assistant" and last_user_id in ids):
                    retained.append(message)
            if ids:
                value.pi_deleted_entries.extend(message.pi_entry_id for message in value.messages
                    if message not in retained and message.pi_entry_id)
                value.messages = retained
                value.task_state = {}
                value.research_history = []
                value.research_question = None
                value.research_decisions = []
                store.save_conversation(email, project_id, value)
        return success(_legacy_conversation(value))
    except (ValueError, FileNotFoundError) as error:
        raise fail(error) from error


@router.delete("/agent/conversation")
def delete_agent_conversation(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        project_id = _project_id(str(body.get("directory") or ""))
        conversation_id = _conversation_id(str(body.get("sessionFile") or "")) or ""
        with document_lock(store._conversation_path(email, project_id, conversation_id)):
            value = store.get_conversation(email, project_id, conversation_id)
            if value.run_status == "running":
                raise HTTPException(status_code=409, detail={"message": "会话仍在处理中，请先停止或等待完成再删除。"})
            store.delete_conversation(email, project_id, conversation_id)
        return success()
    except (ValueError, FileNotFoundError) as error:
        raise fail(error) from error


@router.post("/agent/canvasResult")
def accept_canvas_result() -> dict[str, Any]:
    return success()


@router.post("/agent/answer")
def accept_agent_answer(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    from app.video_studio.reference_research import answer_research_question
    try:
        if body.get('answer') is not None or body.get('values') is not None or not body.get('sessionFile'):
            return success(answer_pi_question(email,_project_id(str(body.get('directory') or '')),str(body.get('callId') or ''),body))
        # A current Pi question also accepts a skip with conversation identity.
        question_path=store._project_root(email,_project_id(str(body.get('directory') or '')))/'.agent'/'questions'/f"{body.get('callId','')}.json"
        if re.fullmatch(r'[a-f0-9]{32}',str(body.get('callId',''))) and store._read_json(question_path,None):
            return success(answer_pi_question(email,_project_id(str(body.get('directory') or '')),body['callId'],body))
        if body.get('cancelled'):
            raise ValueError('关闭或取消不会自动同意调研；问题仍等待明确选择。')
        skipped = body.get('skipped') is True
        return success(answer_research_question(email=email, project_id=_project_id(str(body.get('directory') or '')),
            conversation_id=_conversation_id(str(body.get('sessionFile') or '')) or '',
            question_id=str(body.get('callId') or ''), choice='off' if skipped else str(body.get('choice') or ''), skipped=skipped,
            notes=body.get('notes', '')))
    except (ValueError, FileNotFoundError) as error:
        raise fail(error) from error


@router.post("/agent")
async def legacy_agent(body: dict[str, Any], request: Request, email: str = Depends(current_user)) -> StreamingResponse:
    project_id = _project_id(str(body.get("directory") or ""))
    prompt = str(body.get("prompt") or "").strip()
    session_file = body.get("sessionFile")
    conversation_id = _conversation_id(str(session_file)) if session_file else None
    attachments = body.get("attachments") if isinstance(body.get("attachments"), list) else []
    asset_paths = [str(item.get("path")) for item in attachments if isinstance(item, dict) and item.get("path")]
    if not prompt and asset_paths:
        prompt = '请分析我上传的客户素材，说明可用于视频制作的内容与限制；不要自动生成或修改画布。'
    if not prompt:
        raise HTTPException(status_code=400, detail={"message": "请输入消息或添加附件"})
    canvas_context = body.get('canvas') if isinstance(body.get('canvas'), dict) else {}
    canvas_name = str(canvas_context.get('id') or '')
    canvas_document = None
    canvas_revision = None
    canvas_path = None
    if canvas_name:
        canvas_path = _workspace_path(email, project_id, canvas_name)
        if not canvas_path.is_file():
            raise HTTPException(status_code=404, detail={'message':'目标画布不存在，请重新打开画布。'})
        if canvas_path.stat().st_size > MAX_TEXT_BYTES:
            raise HTTPException(status_code=413, detail={'message':'画布文件不能超过 5 MiB，请精简后重新发送。'})
        with canvas_path.open('rb') as source:
            payload = source.read(MAX_TEXT_BYTES + 1)
        if len(payload) > MAX_TEXT_BYTES:
            raise HTTPException(status_code=413, detail={'message':'画布文件不能超过 5 MiB，请精简后重新发送。'})
        canvas_document = _vue_canvas_document(payload)
        if canvas_document is None:
            raise HTTPException(status_code=400, detail={'message':'目标文件不是有效画布。'})
        canvas_revision = hashlib.sha256(payload).hexdigest()
    if conversation_id:
        try: existing=store.get_conversation(email,project_id,conversation_id)
        except (FileNotFoundError,ValueError) as error: raise fail(error) from error
        if existing.run_status=='running':
            journal,child_file=control_target(email,project_id,existing)
            try:
                journal.enqueue(body.get('streamingBehavior','steer'),prompt,child_file)
            except FileNotFoundError as error:
                raise HTTPException(status_code=409,detail={'message':'该会话仍在处理中，请先停止或等待完成。'}) from error
            except ValueError as error:
                raise fail(error) from error
            async def accepted():
                yield json.dumps({'type':'accepted'})+'\n'
                yield json.dumps({'type':'done'})+'\n'
            return StreamingResponse(accepted(),media_type='application/x-ndjson')
    selected=next((m for m in configured_text_models() if m['providerId']==body.get('providerId') and m['modelId']==body.get('modelId')),None)
    if not selected: selected=next((m for m in configured_text_models() if m.get('isDefault')),None)
    if selected:
        try: validate_thinking(selected,body.get('thinkingLevel') or (existing.thinking_level if conversation_id else 'off'))
        except ValueError as error: raise fail(error) from error
    try:
        prepared = await asyncio.to_thread(prepare_turn, email=email, project_id=project_id, prompt=prompt,
            conversation_id=conversation_id, asset_paths=asset_paths, resend_from=body.get('resendFrom'),
            research_question_id=body.get('researchQuestionId'))
        prompt = prepared.messages[-1].content  # Resume only the server-owned original task.
    except AgentBusy as error:
        raise HTTPException(status_code=409, detail={'message':str(error)}) from error
    except (ValueError, FileNotFoundError) as error:
        raise fail(error) from error

    journal=RunJournal(email,project_id,prepared.id,prepared.run_id)
    journal.create()
    journal.emit({'type':'session','file':_conversation_file(prepared),'runId':prepared.run_id})
    user=prepared.messages[-1]
    journal.emit({'type':'userMessage','id':user.id,'content':prompt,'attachments':user.attachments})
    cancel_event=threading.Event()
    loop=asyncio.get_running_loop()
    committed=False
    target_id=store.get_project(email,project_id).active_canvas_id
    initial_canvas=canvas_document or store.get_project_canvas(email,project_id,target_id)
    def commit(canvas,expected):
        nonlocal committed
        if cancel_event.is_set(): raise ValueError('已取消，不保存画布修改。')
        if canvas_path is not None:
            write_document(canvas_path,json.dumps({'linglonglabVideoCanvas':True,**_vue_canvas_snapshot(canvas)},ensure_ascii=False).encode(),expected_revision=canvas_revision)
            saved=canvas
        else:
            saved=store.save_project_canvas(email,project_id,target_id,canvas,expected_canvas=expected)
        committed=True
        return saved
    async def worker():
        return await asyncio.to_thread(run_agent,email=email,project_id=project_id,prompt=prompt,
            conversation_id=prepared.id,asset_paths=asset_paths,provider_id=body.get('providerId'),model_id=body.get('modelId'),
            prepared_conversation=prepared,cancel_event=cancel_event,progress=journal.emit,
            canvas_document=initial_canvas,canvas_commit=commit if canvas_path is not None else None,
            thinking_level=body.get('thinkingLevel'),journal=journal,
            invoke_async=lambda coro: asyncio.run_coroutine_threadsafe(coro,loop).result(timeout=120))
    def finalized(result):
        conversation,canvas,message=result
        if canvas!=initial_canvas:
            yield {'type':'canvasCall','callId':uuid.uuid4().hex,'name':'replaceCanvas','args':_vue_canvas_snapshot(canvas)}
    pi_http.launch(journal,worker,finalized)
    return StreamingResponse(pi_http.events(journal,request),media_type='application/x-ndjson',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})



@router.post('/agent/cancel')
def cancel_agent(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    try:
        run_id = body.get('runId')
        if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise ValueError('停止请求必须包含当前轮次的有效 runId，请重新载入会话。')
        pid=_project_id(str(body.get('directory') or ''))
        cid=_conversation_id(str(body.get('sessionFile') or '')) or ''
        value=store.get_conversation(email,pid,cid)
        journal,child_file=control_target(email,pid,value)
        if child_file and value.run_status=='running':
            if value.run_id!=run_id: raise ValueError('Child run identity changed')
            journal.abort_child(child_file)
        else:
            cancel_turn(email,pid,cid,run_id)
        return success()
    except (ValueError, FileNotFoundError) as error:
        raise fail(error) from error


@router.get('/agent/events')
async def observe_agent(request: Request, directory: str=Query(), sessionFile: str=Query(),
                        runId: str=Query(), after: int=Query(default=0,ge=0), email: str=Depends(current_user)):
    try:
        pid=_project_id(directory)
        value=store.get_conversation(email,pid,_conversation_id(sessionFile) or '')
        if value.run_id!=runId: raise ValueError('Run identity changed; reload the conversation')
        journal=RunJournal(email,pid,value.id,runId)
        journal.state()
    except (ValueError,FileNotFoundError) as error: raise fail(error) from error
    return StreamingResponse(pi_http.events(journal,request,after,replay=True),media_type='application/x-ndjson',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.post('/agent/control')
def control_agent(body:dict[str,Any],email:str=Depends(current_user)):
    try:
        pid=_project_id(str(body.get('directory') or ''))
        value=store.get_conversation(email,pid,_conversation_id(str(body.get('sessionFile') or '')) or '')
        if value.run_id!=body.get('runId') or value.run_status!='running': raise ValueError('Run identity changed or run ended')
        journal,child_file=control_target(email,pid,value)
        command=journal.enqueue(body.get('action'),body.get('prompt'),child_file)
        return success({'accepted':True,'controlId':command['controlId']})
    except (ValueError,FileNotFoundError) as error: raise fail(error) from error


@router.get('/agent/capabilities')
def agent_capabilities(email:str=Depends(current_user)):
    return success(capabilities())


def _resource_tools(email,pid):
    from app.video_studio.pi_tools import CanvasTools,NODE_TYPES
    return BusinessTools(email,pid,'',None,CanvasTools(store.get_project(email,pid).canvas,NODE_TYPES))


@router.get('/agent/resources')
def agent_resource(directory:str=Query(),resource:str=Query(),scope:str=Query(default='project'),email:str=Depends(current_user)):
    try: return success(_resource_tools(email,_project_id(directory)).resource_read(resource,scope))
    except (ValueError,FileNotFoundError) as error: raise fail(error) from error


@router.patch('/agent/resources')
def edit_agent_resource(body:dict[str,Any],email:str=Depends(current_user)):
    try:
        return success(_resource_tools(email,_project_id(str(body.get('directory') or ''))).resource_write(
            body.get('resource'),body.get('content'),body.get('expectedRevision'),body.get('enabled',True),body.get('scope','project')))
    except DocumentConflict as error: raise HTTPException(status_code=409,detail={'message':str(error)}) from error
    except (ValueError,FileNotFoundError) as error: raise fail(error) from error
