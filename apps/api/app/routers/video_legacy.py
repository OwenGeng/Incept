from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import shutil
import time
import uuid
from datetime import timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings as platform_settings
from app.incept.config import get_settings as get_deployment_settings
from app.incept.video_production_capabilities import configured_video_production_capabilities
from app.routers.video_runtime import ManagedMediaRequest, _chat_stream, generate_media
from app.services.auth import require_internal_key
from app.video_studio import store
from app.video_studio.agent import run_agent
from app.video_studio.models import AgentConversation, CanvasDocument, Position, ProjectCreate, ProjectUpdate, VideoEdge, VideoNode


router = APIRouter(
    prefix="/video-legacy/api",
    tags=["video-legacy"],
    dependencies=[Depends(require_internal_key)],
)


def current_user(x_user_email: str = Header(default="")) -> str:
    return x_user_email.strip().lower() or "local@linglonglab.internal"


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
    target.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and target.exists():
        raise FileExistsError(target.name)
    temporary = target.with_suffix(f"{target.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


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


def _sync_vue_canvas(email: str, project_id: str, payload: bytes) -> None:
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
        vue_type = str(item.get("type") or "").removeprefix("remote-")
        node_type = _VUE_NODE_TYPES.get(vue_type)
        if not node_type:
            continue
        position = item.get("position") if isinstance(item.get("position"), dict) else {}
        nodes.append(VideoNode(
            id=str(item["id"]),
            type=node_type,
            position=Position(x=float(position.get("x") or 0), y=float(position.get("y") or 0)),
            data=item.get("data") if isinstance(item.get("data"), dict) else {},
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
        ))
    viewport = value.get("viewport") if isinstance(value.get("viewport"), dict) else {"x": 0, "y": 0, "zoom": 1}
    store.save_canvas(email, project_id, CanvasDocument(nodes=nodes, edges=edges, viewport=viewport))


def _vue_canvas_snapshot(canvas: CanvasDocument) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": node.id,
                "type": _FASTAPI_NODE_TYPES.get(node.type, "remote-textNode"),
                "position": node.position.model_dump(),
                "data": node.data,
            }
            for node in canvas.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "sourceHandle": edge.source_handle,
                "targetHandle": edge.target_handle,
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
    directory: str = Query(),
    path: str = Query(),
    email: str = Depends(current_user),
):
    try:
        target = _workspace_path(email, directory, path)
        if not target.is_file():
            raise FileNotFoundError(path)
        range_header = request.headers.get("range")
        if not range_header:
            return FileResponse(target, media_type=store.asset_mime_type(target))
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
            headers={"Content-Range": f"bytes 0-{end}/{size}", "Accept-Ranges": "bytes"},
        )
    except (FileNotFoundError, ValueError) as error:
        raise fail(error) from error


@router.put("/workspaces/files/write")
async def write_workspace_file(
    request: Request,
    directory: str = Query(),
    path: str = Query(),
    exclusive: bool = Query(default=False),
    email: str = Depends(current_user),
) -> dict[str, Any]:
    try:
        payload = await request.body()
        if len(payload) > 500 * 1024 * 1024:
            raise HTTPException(status_code=413, detail={"message": "文件不能超过 500 MB"})
        target = _workspace_path(email, directory, path)
        _write_bytes(target, payload, exclusive=exclusive)
        if path.lower().endswith(".json"):
            _sync_vue_canvas(email, _project_id(directory), payload)
        return success()
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
    model = platform_settings.gemini_model
    return {
        "ui": {"theme": "light", "primaryColor": "#6750A4", "fontScale": 100, "radius": 8, "startupAnimation": True},
        "general": {"canvasCompositingEnabled": False, "canvasEdgeAnimationEnabled": True},
        "privacy": {"dataCollectionEnabled": False},
        "customProviders": [{
            "id": "linglonglab-vertex",
            "label": "LinglongLab Vertex AI",
            "apiUrl": "managed://vertex-ai",
            "apiKey": "",
            "protocol": "openai-completions",
            "models": [{"id": model, "label": model, "contextWindow": 262144, "maxOutputTokens": 32768}],
        }],
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
    model = platform_settings.gemini_model
    return success([{
        "providerId": "linglonglab-vertex",
        "providerLabel": "LinglongLab Vertex AI",
        "modelId": model,
        "label": model,
        "protocol": "openai-completions",
        "contextWindow": 262144,
        "maxOutputTokens": 32768,
    }])


@router.get("/ai/media/models")
def media_models() -> dict[str, Any]:
    capabilities = configured_video_production_capabilities()
    deployment = get_deployment_settings()
    image_model = deployment.vertex_gemini_image_model
    video_model = deployment.vertex_veo_model or deployment.vertex_veo_fast_model
    values: list[dict[str, Any]] = []
    for option in capabilities.image:
        if option.model != image_model:
            continue
        values.append({
            "providerId": option.provider,
            "providerLabel": "LinglongLab Vertex AI",
            "modelId": option.model,
            "label": option.label,
            "type": "image",
            "imageSizes": ["1K", "2K"],
            "imageRatios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        })
    for option in capabilities.video:
        if option.model != video_model:
            continue
        values.append({
            "providerId": option.provider,
            "providerLabel": "LinglongLab Vertex AI",
            "modelId": option.model,
            "label": option.label,
            "type": "video",
            "mode": ["text", "singleImage", "endFrameOptional"],
            "durationResolutionMap": [{"duration": [5, 8], "resolution": ["720p", "1080p"]}],
            "audio": "optional",
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


@router.post("/ai/generate")
def generate_text(body: dict[str, Any]) -> StreamingResponse:
    model = platform_settings.gemini_model
    if body.get("providerId") != "linglonglab-vertex" or body.get("modelId") != model:
        raise HTTPException(status_code=400, detail={"message": "所选文本模型未由当前部署启用"})
    context = body.get("context") if isinstance(body.get("context"), dict) else {}
    messages, tools = _openai_context(context)

    def events():
        text_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        stop_reason = "stop"
        try:
            for raw in _chat_stream({"messages": messages, "tools": tools, "stream": True}):
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
            content = ([{"type": "text", "text": "".join(text_parts)}] if text_parts else []) + [tool_calls[index] for index in sorted(tool_calls)]
            message = {
                "role": "assistant",
                "content": content,
                "api": "openai-completions",
                "provider": "linglonglab-vertex",
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
    if media_type not in {"image", "video"}:
        raise HTTPException(status_code=400, detail={"message": "不支持的媒体类型"})
    deployment = get_deployment_settings()
    expected_model = deployment.vertex_gemini_image_model if media_type == "image" else (deployment.vertex_veo_model or deployment.vertex_veo_fast_model)
    if body.get("providerId") != "google-vertex-ai" or body.get("modelId") != expected_model:
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
        prompt=str(body.get("prompt") or ""),
        ratio=body.get("ratio"),
        size=body.get("size"),
        duration=body.get("duration"),
        first_frame=frame(first_path),
        last_frame=frame(last_path),
    ))
    extension = {"image/png": ".png", "image/jpeg": ".jpg", "video/mp4": ".mp4"}.get(result.mime_type) or mimetypes.guess_extension(result.mime_type) or ".bin"
    output_directory = str(body.get("outputDirectory") or "generated")
    relative = f"{output_directory.strip('/')}/{media_type}-{uuid.uuid4().hex}{extension}"
    target = store.safe_asset_path(root, relative)
    _write_bytes(target, base64.b64decode(result.data, validate=True))
    return success([{"path": relative, "mimeType": result.mime_type, "mediaType": media_type}])


def _conversation_file(value: AgentConversation) -> str:
    return f"{value.id}.jsonl"


def _conversation_id(session_file: str | None) -> str | None:
    if not session_file:
        return None
    value = session_file.removesuffix(".jsonl")
    return _project_id(value)


def _legacy_conversation(value: AgentConversation) -> dict[str, Any]:
    return {
        "file": _conversation_file(value),
        "name": value.name,
        "messages": [
            {
                "id": message.id,
                "entryId": message.id if message.role == "user" else None,
                "role": message.role,
                "content": message.content,
                "parts": [{"id": message.id, "type": "text", "content": message.content}] if message.role == "assistant" else [],
            }
            for message in value.messages
        ],
        "providerId": "linglonglab-vertex",
        "modelId": platform_settings.gemini_model,
        "subAgents": [],
        "running": False,
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
    value = store.get_conversation(email, _project_id(directory), _conversation_id(sessionFile) or "")
    return success(_legacy_conversation(value))


@router.patch("/agent/rename")
def rename_agent_conversation(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    project_id = _project_id(str(body.get("directory") or ""))
    conversation_id = _conversation_id(str(body.get("sessionFile") or "")) or ""
    value = store.get_conversation(email, project_id, conversation_id)
    value.name = str(body.get("name") or "").strip()[:120]
    if not value.name:
        raise HTTPException(status_code=400, detail={"message": "对话名称不能为空"})
    store.save_conversation(email, project_id, value)
    return success({"name": value.name})


@router.delete("/agent/message")
def delete_agent_message(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    project_id = _project_id(str(body.get("directory") or ""))
    conversation_id = _conversation_id(str(body.get("sessionFile") or "")) or ""
    value = store.get_conversation(email, project_id, conversation_id)
    ids = {str(item) for item in body.get("entryIds") or []}
    reply_to = body.get("replyTo")
    if reply_to:
        ids.add(str(reply_to))
    value.messages = [message for message in value.messages if message.id not in ids]
    store.save_conversation(email, project_id, value)
    return success(_legacy_conversation(value))


@router.delete("/agent/conversation")
def delete_agent_conversation(body: dict[str, Any], email: str = Depends(current_user)) -> dict[str, Any]:
    project_id = _project_id(str(body.get("directory") or ""))
    conversation_id = _conversation_id(str(body.get("sessionFile") or "")) or ""
    store.delete_conversation(email, project_id, conversation_id)
    return success()


@router.post("/agent/canvasResult")
def accept_canvas_result() -> dict[str, Any]:
    return success()


@router.post("/agent/answer")
def accept_agent_answer() -> dict[str, Any]:
    return success()


@router.post("/agent")
async def legacy_agent(body: dict[str, Any], email: str = Depends(current_user)) -> StreamingResponse:
    project_id = _project_id(str(body.get("directory") or ""))
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail={"message": "请输入消息"})
    session_file = body.get("sessionFile")
    conversation_id = _conversation_id(str(session_file)) if session_file else None
    attachments = body.get("attachments") if isinstance(body.get("attachments"), list) else []
    asset_paths = [str(item.get("path")) for item in attachments if isinstance(item, dict) and item.get("path")]

    async def events():
        user_id = uuid.uuid4().hex
        yield json.dumps({"type": "userMessage", "id": user_id, "content": prompt}, ensure_ascii=False) + "\n"
        try:
            conversation, canvas, message = await asyncio.to_thread(
                run_agent,
                email=email,
                project_id=project_id,
                prompt=prompt,
                conversation_id=conversation_id,
                asset_paths=asset_paths,
            )
            yield json.dumps({"type": "session", "file": _conversation_file(conversation)}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "canvasCall", "callId": uuid.uuid4().hex, "name": "replaceCanvas", "args": _vue_canvas_snapshot(canvas)}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "text", "blockId": uuid.uuid4().hex, "content": message, "done": True}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"
        except Exception as error:
            yield json.dumps({"type": "error", "message": str(error)}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
