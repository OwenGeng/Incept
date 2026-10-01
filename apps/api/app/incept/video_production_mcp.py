"""Authenticated MCP tools for LinglongLab Video Production.

This module exposes Project State through a separate automation transport.  It
does not duplicate the web API's business rules: every tool delegates to the
same store functions that power the workspace, so authorization, revisions,
approval gates, and recovery records stay identical whichever client acts.

The endpoint is intentionally opt-in.  A deployment must provide a public MCP
resource URL and explicit opaque bearer-token principals before it is mounted.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError

from app.incept.config import Settings, get_settings
from app.incept.models import (
    Role,
    User,
    VideoProductionAgentRequest,
    VideoProductionBridgeFrameRequest,
    VideoProductionCreateRequest,
    VideoProductionDesignSheetCreateRequest,
    VideoProductionDesignSheetSelectionRequest,
    VideoProductionDesignSheetUpdateRequest,
    VideoProductionRenderRequest,
    VideoProductionSceneReframeRequest,
    VideoProductionShotCreateRequest,
    VideoProductionShotOrderRequest,
    VideoProductionShotRenderRequest,
    VideoProductionShotUpdateRequest,
    VideoProductionUpdateRequest,
)
from app.incept.video_production_capabilities import configured_video_production_capabilities
from app.incept.video_production_store import (
    JOBS,
    approve_storyboard,
    archive_video_production,
    cancel_design_sheet_generation,
    create_custom_design_sheet,
    create_design_sheet_job,
    create_keyframe_job,
    create_production_audio_job,
    create_production_render_job,
    create_scene_reframe_job,
    create_shot_video_job,
    create_video_production,
    create_video_production_shot,
    delete_custom_design_sheet,
    extract_video_production_bridge_frame,
    fork_video_production,
    get_video_production,
    list_video_productions,
    lock_script_and_create_storyboard,
    reorder_video_production_shots,
    restore_video_production,
    run_audio_producer,
    run_creative_director,
    run_design_sheet_background,
    run_director_agent,
    run_edit_reviewer,
    run_keyframe_background,
    run_production_audio_background,
    run_production_designer,
    run_production_render_background,
    run_script_agent,
    run_scene_reframe_background,
    run_shot_video_background,
    select_design_sheet_panel,
    update_custom_design_sheet,
    update_video_production,
    update_video_production_shot,
)


MCP_SCOPE = "incept-video-production"
_PAID_CONFIRMATION_MESSAGE = (
    "Set confirm_spend=true only after the operator has approved this model or generation request."
)


class LinglongLabMCPTokenVerifier(TokenVerifier):
    """Verify only deployment-provisioned opaque automation credentials."""

    def __init__(self, principals: Mapping[str, Mapping[str, str]]) -> None:
        self._principals = {token: dict(principal) for token, principal in principals.items()}

    async def verify_token(self, token: str) -> AccessToken | None:
        principal = self._principals.get(token)
        if not principal:
            return None
        user_id = principal.get("id", "").strip()
        email = principal.get("email", "").strip().lower()
        role = principal.get("role", Role.user.value).strip().lower()
        if not user_id or not email or role not in {item.value for item in Role}:
            return None
        return AccessToken(
            token=token,
            client_id=user_id,
            subject=user_id,
            scopes=[MCP_SCOPE],
            claims={
                "id": user_id,
                "email": email,
                "name": principal.get("name", "").strip() or email,
                "team": principal.get("team", "Automation").strip() or "Automation",
                "role": role,
            },
        )


def _automation_user(settings: Settings) -> User:
    token = get_access_token()
    if token is None or not token.claims:
        raise ToolError("The MCP call has no authenticated automation principal.")
    claims = token.claims
    email = str(claims.get("email", "")).strip().lower()
    if not email or not email.endswith(f"@{settings.allowed_email_domain}"):
        raise ToolError("The MCP principal is not in the allowed LinglongLab email domain.")
    try:
        role = Role(str(claims.get("role", Role.user.value)))
    except ValueError as exc:
        raise ToolError("The MCP principal has an invalid role.") from exc
    user_id = str(claims.get("id", "")).strip()
    if not user_id:
        raise ToolError("The MCP principal is missing an id.")
    return User(
        id=user_id,
        email=email,
        name=str(claims.get("name", email)),
        team=str(claims.get("team", "Automation")),
        role=role,
    )


def _json(value: Any) -> Any:
    """Produce JSON-safe structured output without leaking internal objects."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    return value


def _tool_error(exc: Exception) -> ToolError:
    if isinstance(exc, ValidationError):
        return ToolError(f"Invalid request: {exc.errors(include_url=False)}")
    if isinstance(exc, PermissionError):
        return ToolError(f"Forbidden: {exc}")
    if isinstance(exc, KeyError):
        return ToolError(f"Not found: {exc}")
    if isinstance(exc, ValueError):
        return ToolError(f"Invalid request: {exc}")
    if isinstance(exc, RuntimeError):
        return ToolError(f"Operation unavailable: {exc}")
    return ToolError("The operation could not be completed. Inspect the retained project state and retry only if appropriate.")


def _require_cost_confirmation(confirm_spend: bool) -> None:
    if confirm_spend is not True:
        raise ToolError(_PAID_CONFIRMATION_MESSAGE)


def _project_job_status(production_id: str, user: User) -> dict[str, Any]:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    job_ids = {production.render_job_id, production.audio_plan.job_id}
    job_ids.update(sheet.job_id for sheet in production.design_bible.asset_packs)
    job_ids.update(shot.keyframe_job_id for shot in production.shots)
    job_ids.update(shot.video_job_id for shot in production.shots)
    jobs = [_json(JOBS[job_id]) for job_id in job_ids if job_id and job_id in JOBS]
    return {"production_id": production.production_id, "state_revision": production.state_revision, "jobs": jobs}


def build_video_production_mcp_server(
    *,
    settings: Settings | None = None,
    principals: Mapping[str, Mapping[str, str]] | None = None,
    public_url: str | None = None,
) -> FastMCP:
    """Build a stateless Streamable HTTP MCP host from deployment-owned config."""
    active_settings = settings or get_settings()
    active_principals = principals if principals is not None else active_settings.video_production_mcp_api_keys
    resource_url = public_url or active_settings.video_production_mcp_public_url
    if not resource_url or not active_principals:
        raise ValueError("MCP requires INCEPT_VIDEO_MCP_PUBLIC_URL and INCEPT_VIDEO_MCP_API_KEYS.")
    parsed_resource_url = urlparse(resource_url)
    if parsed_resource_url.scheme != "https" or not parsed_resource_url.netloc:
        raise ValueError("INCEPT_VIDEO_MCP_PUBLIC_URL must be an absolute HTTPS URL.")

    server = FastMCP(
        "LinglongLab Video Production",
        instructions=(
            "Use these tools only for authorized LinglongLab Video Production work. "
            "Read Project State before changing it. Preserve state_revision on updates. "
            "Tools that can incur model or generation cost require confirm_spend=true."
        ),
        token_verifier=LinglongLabMCPTokenVerifier(active_principals),
        auth=AuthSettings(
            issuer_url=resource_url,
            resource_server_url=resource_url,
            required_scopes=[MCP_SCOPE],
            validate_token_resource=False,
        ),
        stateless_http=True,
        streamable_http_path="/",
        json_response=False,
        # Keep DNS-rebinding protection on. The deployment-owned public URL is
        # the only accepted Host/Origin, rather than disabling host checks for
        # a reverse proxy as a convenience.
        transport_security=TransportSecuritySettings(
            allowed_hosts=[parsed_resource_url.netloc],
            allowed_origins=[f"{parsed_resource_url.scheme}://{parsed_resource_url.netloc}"],
        ),
    )

    def user() -> User:
        return _automation_user(active_settings)

    @server.tool(name="list_video_projects", structured_output=True)
    async def list_video_projects(
        workspace_id: str,
        include_archived: bool = False,
        scope: str = "mine",
    ) -> list[dict[str, Any]]:
        """List only Video Production projects accessible to the authenticated principal."""
        try:
            return _json(list_video_productions(workspace_id, user(), scope=scope, include_archived=include_archived))
        except Exception as exc:  # guarded conversion keeps MCP responses actionable
            raise _tool_error(exc) from exc

    @server.tool(name="read_video_project", structured_output=True)
    async def read_video_project(production_id: str) -> dict[str, Any]:
        """Read the complete durable Project State for one production."""
        try:
            production = get_video_production(production_id, user())
            if not production:
                raise KeyError("Video production not found")
            return _json(production)
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="get_video_project_operations", structured_output=True)
    async def get_video_project_operations(production_id: str) -> dict[str, Any]:
        """Poll durable job status for a project after any generation submission."""
        try:
            return _project_job_status(production_id, user())
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="get_video_model_capabilities", structured_output=True)
    async def get_video_model_capabilities() -> dict[str, Any]:
        """Read the safe, server-configured provider/model catalog; secrets are never returned."""
        _ = user()
        return _json(configured_video_production_capabilities(active_settings))

    @server.tool(name="create_video_project", structured_output=True)
    async def create_video_project(request: dict[str, Any]) -> dict[str, Any]:
        """Create a new ad-video project with its full intake and model selection."""
        try:
            return _json(create_video_production(VideoProductionCreateRequest.model_validate(request), user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="update_video_project", structured_output=True)
    async def update_video_project(production_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Update Project State. Include expected_revision to prevent accidental overwrite."""
        try:
            return _json(update_video_production(production_id, VideoProductionUpdateRequest.model_validate(patch), user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="fork_video_project", structured_output=True)
    async def fork_video_project(production_id: str, label: str = "Variant") -> dict[str, Any]:
        """Create a non-destructive project variant that retains lineage to its source."""
        try:
            return _json(fork_video_production(production_id, label, user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="archive_video_project", structured_output=True)
    async def archive_video_project(production_id: str) -> dict[str, Any]:
        """Archive a project without deleting production history or assets."""
        try:
            return _json(archive_video_production(production_id, user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="restore_video_project", structured_output=True)
    async def restore_video_project(production_id: str) -> dict[str, Any]:
        """Restore an archived project into the regular project library."""
        try:
            return _json(restore_video_production(production_id, user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="lock_script_and_create_storyboard", structured_output=True)
    async def lock_script_and_create_storyboard_tool(production_id: str) -> dict[str, Any]:
        """Lock the structured script after validation and materialize the storyboard state."""
        try:
            return _json(lock_script_and_create_storyboard(production_id, user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="approve_storyboard", structured_output=True)
    async def approve_storyboard_tool(production_id: str) -> dict[str, Any]:
        """Approve the current storyboard revision before paid keyframe or video work."""
        try:
            return _json(approve_storyboard(production_id, user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="create_storyboard_shot", structured_output=True)
    async def create_storyboard_shot(production_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Add a controlled storyboard shot to an existing project."""
        try:
            return _json(create_video_production_shot(production_id, VideoProductionShotCreateRequest.model_validate(request), user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="update_storyboard_shot", structured_output=True)
    async def update_storyboard_shot(production_id: str, shot_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch one shot's prompt, timing, continuity, or selected-take state."""
        try:
            return _json(update_video_production_shot(production_id, shot_id, VideoProductionShotUpdateRequest.model_validate(patch), user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="reorder_storyboard_shots", structured_output=True)
    async def reorder_storyboard_shots(production_id: str, shot_ids: list[str]) -> dict[str, Any]:
        """Persist an explicit shot order; omitted or duplicate shot ids are rejected."""
        try:
            request = VideoProductionShotOrderRequest(shot_ids=shot_ids)
            return _json(reorder_video_production_shots(production_id, request, user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="create_design_pack", structured_output=True)
    async def create_design_pack(production_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Create an editable reusable Design Pack before image generation is submitted."""
        try:
            return _json(create_custom_design_sheet(production_id, VideoProductionDesignSheetCreateRequest.model_validate(request), user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="update_design_pack", structured_output=True)
    async def update_design_pack(production_id: str, sheet_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Edit a Design Pack's controlled prompt and source references."""
        try:
            return _json(update_custom_design_sheet(production_id, sheet_id, VideoProductionDesignSheetUpdateRequest.model_validate(patch), user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="select_design_pack_panel", structured_output=True)
    async def select_design_pack_panel(production_id: str, sheet_id: str, panel: int) -> dict[str, Any]:
        """Promote one reviewable contact-sheet panel as the reusable selected state."""
        try:
            return _json(await select_design_sheet_panel(
                production_id,
                sheet_id,
                VideoProductionDesignSheetSelectionRequest(panel=panel).panel,
                user(),
            ))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="cancel_design_pack_generation", structured_output=True)
    async def cancel_design_pack_generation(production_id: str, sheet_id: str) -> dict[str, Any]:
        """Cancel a queued Design Pack generation without deleting its editable prompt."""
        try:
            return _json(cancel_design_sheet_generation(production_id, sheet_id, user()))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="delete_design_pack", structured_output=True)
    async def delete_design_pack(production_id: str, sheet_id: str) -> dict[str, str]:
        """Remove one unused Design Pack; Project State validates dependent references first."""
        try:
            delete_custom_design_sheet(production_id, sheet_id, user())
            return {"production_id": production_id, "deleted_design_pack_id": sheet_id}
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="extract_bridge_frame", structured_output=True)
    async def extract_bridge_frame(production_id: str, shot_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Promote a reviewed frame from a prior take as a controlled continuity input."""
        try:
            return _json(extract_video_production_bridge_frame(
                production_id, shot_id, VideoProductionBridgeFrameRequest.model_validate(request), user()
            ))
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="run_production_agent", structured_output=True)
    async def run_production_agent(
        production_id: str,
        operation: str,
        request: dict[str, Any] | None = None,
        confirm_spend: bool = False,
    ) -> dict[str, Any]:
        """Run a named planning agent after explicit cost approval; it never bypasses lifecycle gates."""
        _require_cost_confirmation(confirm_spend)
        runners = {
            "script": run_script_agent,
            "creative_direction": run_creative_director,
            "design": run_production_designer,
            "storyboard": run_director_agent,
            "edit_review": run_edit_reviewer,
            "audio_plan": run_audio_producer,
        }
        runner = runners.get(operation)
        if runner is None:
            raise ToolError("operation must be one of: script, creative_direction, design, storyboard, edit_review, audio_plan.")
        try:
            result = await asyncio.to_thread(
                runner,
                production_id,
                VideoProductionAgentRequest.model_validate(request or {}),
                user(),
            )
            return _json(result)
        except Exception as exc:
            raise _tool_error(exc) from exc

    @server.tool(name="submit_video_generation", structured_output=True)
    async def submit_video_generation(
        production_id: str,
        operation: str,
        confirm_spend: bool = False,
        shot_id: str | None = None,
        design_pack_id: str | None = None,
        request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit one durable async generation. Poll get_video_project_operations until terminal status."""
        _require_cost_confirmation(confirm_spend)
        current_user = user()
        try:
            if operation == "keyframe":
                if not shot_id:
                    raise ValueError("shot_id is required for keyframe generation")
                job = create_keyframe_job(production_id, shot_id, current_user)
                asyncio.create_task(run_keyframe_background(production_id, shot_id, job.job_id, current_user))
            elif operation == "design_pack":
                if not design_pack_id:
                    raise ValueError("design_pack_id is required for design-pack generation")
                job = create_design_sheet_job(production_id, design_pack_id, current_user)
                asyncio.create_task(run_design_sheet_background(production_id, design_pack_id, job.job_id, current_user))
            elif operation == "scene_reframe":
                reframe = VideoProductionSceneReframeRequest.model_validate(request or {})
                job, sheet = create_scene_reframe_job(production_id, reframe, current_user)
                asyncio.create_task(run_scene_reframe_background(production_id, sheet.id, job.job_id, current_user))
            elif operation == "shot_video":
                if not shot_id:
                    raise ValueError("shot_id is required for shot-video generation")
                render = VideoProductionShotRenderRequest.model_validate(request or {})
                job = create_shot_video_job(production_id, shot_id, current_user, variants=render.variants)
                asyncio.create_task(run_shot_video_background(production_id, shot_id, job.job_id, current_user))
            elif operation == "soundtrack":
                job = create_production_audio_job(production_id, current_user)
                asyncio.create_task(run_production_audio_background(production_id, job.job_id, current_user))
            elif operation == "render":
                render = VideoProductionRenderRequest.model_validate(request or {})
                job = create_production_render_job(production_id, current_user, include_audio=render.include_audio)
                asyncio.create_task(run_production_render_background(
                    production_id, job.job_id, current_user, render.include_audio
                ))
            else:
                raise ValueError("operation must be one of: keyframe, design_pack, scene_reframe, shot_video, soundtrack, render.")
            return {
                "generation_job": _json(job),
                "poll_tool": "get_video_project_operations",
                "production_id": production_id,
            }
        except Exception as exc:
            raise _tool_error(exc) from exc

    return server


def configured_video_production_mcp_server(settings: Settings | None = None) -> FastMCP | None:
    """Return the configured host, or ``None`` when automation is disabled."""
    active_settings = settings or get_settings()
    if not active_settings.video_production_mcp_public_url or not active_settings.video_production_mcp_api_keys:
        return None
    return build_video_production_mcp_server(settings=active_settings)


def configured_video_production_mcp_app(settings: Settings | None = None):
    """Return the ASGI MCP app only when explicit production auth is configured."""
    server = configured_video_production_mcp_server(settings)
    return server.streamable_http_app() if server is not None else None
