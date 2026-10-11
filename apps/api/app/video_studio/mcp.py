"""Opt-in authenticated MCP surface for the React/FastAPI Video workspace."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from app.incept.config import get_settings
from app.routers.video_runtime import ManagedMediaRequest, generate_media

from . import store
from .pi_agent import run_agent
from .models import CanvasDocument, ExportRequest, ProjectCreate, ProjectDocument
from .render import export_project


MCP_SCOPE = "linglonglab-video"


class VideoStudioTokenVerifier(TokenVerifier):
    def __init__(self, principals: Mapping[str, Mapping[str, str]]) -> None:
        self._principals = {token: dict(value) for token, value in principals.items()}

    async def verify_token(self, token: str) -> AccessToken | None:
        principal = self._principals.get(token)
        if not principal:
            return None
        email = principal.get("email", "").strip().lower()
        principal_id = principal.get("id", "").strip()
        if not email or not principal_id:
            return None
        return AccessToken(
            token=token,
            client_id=principal_id,
            subject=principal_id,
            scopes=[MCP_SCOPE],
            claims={"id": principal_id, "email": email},
        )


def _user_email() -> str:
    token = get_access_token()
    email = str(token.claims.get("email", "")).strip().lower() if token and token.claims else ""
    if not email:
        raise ToolError("The MCP principal is missing an email address.")
    return email


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    return value


def _tool_error(error: Exception) -> ToolError:
    if isinstance(error, (FileNotFoundError, KeyError)):
        return ToolError(f"Not found: {error}")
    if isinstance(error, ValueError):
        return ToolError(f"Invalid request: {error}")
    return ToolError(f"Video workspace operation failed: {error}")


def _require_spend_confirmation(confirm_spend: bool) -> None:
    if confirm_spend is not True:
        raise ToolError("Set confirm_spend=true only after the operator approves this billable model request.")


def build_video_studio_mcp_server(
    *,
    public_url: str,
    principals: Mapping[str, Mapping[str, str]],
) -> FastMCP:
    parsed = urlparse(public_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("VIDEO_STUDIO_MCP_PUBLIC_URL must be an absolute HTTPS URL.")
    if not principals:
        raise ValueError("VIDEO_STUDIO_MCP_PRINCIPALS must contain at least one principal.")

    server = FastMCP(
        "LinglongLab Video",
        instructions=(
            "Use the authenticated user's LinglongLab Video projects. Read current state before writing. "
            "Media and model calls require confirm_spend=true after explicit operator approval."
        ),
        token_verifier=VideoStudioTokenVerifier(principals),
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=public_url,
            required_scopes=[MCP_SCOPE],
            validate_token_resource=False,
        ),
        stateless_http=True,
        streamable_http_path="/",
        json_response=False,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[parsed.netloc],
            allowed_origins=[f"{parsed.scheme}://{parsed.netloc}"],
        ),
    )

    @server.tool(name="list_video_projects", structured_output=True)
    async def list_video_projects() -> list[dict[str, Any]]:
        return _json(store.list_projects(_user_email()))

    @server.tool(name="create_video_project", structured_output=True)
    async def create_video_project(name: str, description: str = "") -> dict[str, Any]:
        try:
            return _json(store.create_project(_user_email(), ProjectCreate(name=name, description=description)))
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="read_video_project", structured_output=True)
    async def read_video_project(project_id: str) -> dict[str, Any]:
        try:
            return _json(store.get_project(_user_email(), project_id))
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="write_video_canvas", structured_output=True)
    async def write_video_canvas(project_id: str, canvas: dict[str, Any]) -> dict[str, Any]:
        try:
            return _json(store.save_canvas(_user_email(), project_id, CanvasDocument.model_validate(canvas)))
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="read_video_document", structured_output=True)
    async def read_video_document(project_id: str) -> dict[str, Any]:
        try:
            return _json(store.get_document(_user_email(), project_id))
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="write_video_document", structured_output=True)
    async def write_video_document(project_id: str, content: str) -> dict[str, Any]:
        try:
            return _json(store.save_document(_user_email(), project_id, ProjectDocument(content=content)))
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="list_video_assets", structured_output=True)
    async def list_video_assets(project_id: str, path: str = "") -> list[dict[str, Any]]:
        try:
            root = store.assets_root(_user_email(), project_id)
            target = store.safe_asset_path(root, path, allow_root=True)
            if not target.is_dir():
                raise FileNotFoundError(path)
            return [
                {
                    "path": item.relative_to(root).as_posix(),
                    "name": item.name,
                    "kind": "directory" if item.is_dir() else "file",
                    "size": 0 if item.is_dir() else item.stat().st_size,
                    "mime_type": None if item.is_dir() else store.asset_mime_type(item),
                }
                for item in sorted(target.iterdir(), key=lambda value: value.name.lower())
            ]
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="run_video_agent", structured_output=True)
    async def run_video_agent(
        project_id: str,
        prompt: str,
        conversation_id: str | None = None,
        agent_id: str = "workflow",
        confirm_spend: bool = False,
    ) -> dict[str, Any]:
        _require_spend_confirmation(confirm_spend)
        try:
            conversation, canvas, message = await asyncio.to_thread(
                run_agent,
                email=_user_email(),
                project_id=project_id,
                prompt=prompt,
                conversation_id=conversation_id,
                agent_id=agent_id,
            )
            return {"conversation": _json(conversation), "canvas": _json(canvas), "message": message}
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="generate_video_asset", structured_output=True)
    async def generate_video_asset(
        project_id: str,
        media_type: str,
        prompt: str,
        output_path: str,
        ratio: str = "16:9",
        duration: int = 5,
        confirm_spend: bool = False,
    ) -> dict[str, Any]:
        _require_spend_confirmation(confirm_spend)
        try:
            deployment = get_settings()
            provider_id = "google-vertex-ai"
            model_id = deployment.vertex_gemini_image_model if media_type == "image" else deployment.vertex_veo_fast_model
            response = await generate_media(
                ManagedMediaRequest(
                    media_type=media_type,
                    provider_id=provider_id,
                    model_id=model_id,
                    prompt=prompt,
                    ratio=ratio,
                    duration=duration if media_type == "video" else None,
                )
            )
            root = store.assets_root(_user_email(), project_id)
            target = store.safe_asset_path(root, output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(response.data, validate=True))
            return {"path": target.relative_to(root).as_posix(), "mime_type": response.mime_type, "size": target.stat().st_size}
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="export_video_project", structured_output=True)
    async def export_video_project(project_id: str, request: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(
                export_project,
                _user_email(),
                project_id,
                ExportRequest.model_validate(request),
            )
            return _json(result)
        except Exception as error:
            raise _tool_error(error) from error

    @server.tool(name="get_video_extension_catalog", structured_output=True)
    async def get_video_extension_catalog() -> dict[str, Any]:
        return _json(store.get_catalog(_user_email()))

    return server


def _configured_principals() -> dict[str, dict[str, str]]:
    raw = os.getenv("VIDEO_STUDIO_MCP_PRINCIPALS", "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        str(token): {str(key): str(item) for key, item in principal.items()}
        for token, principal in value.items()
        if isinstance(token, str) and isinstance(principal, dict)
    }


def configured_video_studio_mcp_app():
    public_url = os.getenv("VIDEO_STUDIO_MCP_PUBLIC_URL", "").strip()
    principals = _configured_principals()
    if not public_url or not principals:
        return None
    return build_video_studio_mcp_server(public_url=public_url, principals=principals).streamable_http_app()
