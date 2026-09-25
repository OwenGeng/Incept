"""
Incept router — all Incept image-generation endpoints.

Mounted into the unified nbs-api at root level (no prefix), so the
Next.js proxy at /api/incept/[...path] can forward calls unchanged:
  browser  →  /api/incept/assets
  proxy    →  <API_BASE_URL>/assets          (Incept)
  browser  →  /api/v1/supply-smb/...         (InterSight — different prefix, no conflict)
"""

import io
import asyncio
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.incept.auth import get_current_user, require_role
from app.incept.config import get_settings
from app.incept.models import (
    AddTextRequest,
    Asset,
    CreativeThread,
    GenerationJob,
    GenerationRequest,
    GenerateGifRequest,
    ImageEditRequest,
    JobStatus,
    KakaoBizboardComposeRequest,
    KakaoCleanRequest,
    OutpaintRequest,
    PlayableProject,
    PlayableProjectSaveRequest,
    PlayableTemplate,
    PlayableTemplateCreateRequest,
    PlayableTemplateForkRequest,
    PromptReviewRequest,
    PromptReviewResponse,
    ProviderConfig,
    RemediationAnalysisRequest,
    RemediationAnalysisResponse,
    RemoveBGRequest,
    Role,
    Session,
    ThemeCreatePreset,
    ThemeCreatePresetCreateRequest,
    ThemeCreatePresetFromReportRequest,
    ThemeCreateStyleReport,
    ThemeCreateStyleReportCreateRequest,
    ThemeCreateStyleReportDraftRequest,
    ToolDefinition,
    ToolStatusUpdate,
    UsageEvent,
    User,
    VideoBudgetStatus,
    VideoGenerationMode,
    VideoGenerationRequest,
    VideoPlanRequest,
    VideoPlanResponse,
    VideoProduction,
    VideoProductionEvent,
    VideoProductionProviderCapabilities,
    VideoProductionAgentRequest,
    VideoProductionBridgeFrameRequest,
    VideoProductionCopilotRequest,
    VideoProductionCopilotResponse,
    VideoProductionCreateRequest,
    VideoProductionDesignSheetCreateRequest,
    VideoProductionDesignSheetSelectionRequest,
    VideoProductionDesignSheetUpdateRequest,
    VideoProductionSceneReframeRequest,
    VideoProductionShotCreateRequest,
    VideoProductionShotOrderRequest,
    VideoProductionRenderRequest,
    VideoProductionShotRenderRequest,
    VideoProductionShotUpdateRequest,
    VideoProductionUpdateRequest,
    Workspace,
)
from app.incept.store import (
    ASSETS,
    JOBS,
    SOURCE_ASSETS,
    create_add_text_job,
    create_edit_job,
    create_generate_gif_job,
    create_image_generation_job,
    create_kakao_bizboard_job,
    create_kakao_clean_job,
    create_theme_create_preset,
    create_theme_create_preset_from_report,
    create_theme_create_report,
    draft_theme_create_report,
    analyze_remediation_assets,
    assert_image_budget_available,
    build_asset_content_path,
    create_outpaint_job,
    create_remove_bg_job,
    delete_asset,
    guess_asset_extension,
    read_asset_bytes,
    get_job,
    list_assets,
    list_jobs,
    list_threads,
    list_theme_create_presets,
    list_theme_create_reports,
    list_usage_events,
    list_workspaces,
    run_add_text_background,
    run_edit_background,
    run_generate_gif_background,
    run_generation_background,
    run_kakao_bizboard_background,
    run_kakao_clean_background,
    run_outpaint_background,
    run_remove_bg_background,
    save_uploaded_asset,
    stream_asset_bytes,
)
from app.incept.prompt_reviewer import review_prompt
from app.incept import session_store, thread_store
from app.incept.tool_registry import get_tools, update_tool_status
from app.incept.playable_store import (
    create_template as create_playable_template,
    fork_template as fork_playable_template,
    get_project as get_playable_project,
    list_projects as list_playable_projects,
    list_templates as list_playable_templates,
    save_project as save_playable_project,
    toggle_template_favorite,
)
from app.incept.workflow_store import (
    cancel_run as cancel_workflow_run,
    create_run as create_workflow_run,
    create_workflow,
    delete_workflow,
    get_workflow,
    list_events as list_workflow_events,
    get_lineage as get_workflow_lineage,
    list_outputs as list_workflow_outputs,
    list_revisions as list_workflow_revisions,
    list_run_nodes as list_workflow_run_nodes,
    retry_run as retry_workflow_run,
    run_in_workspace,
    list_workflows as list_studio_workflows,
    update_workflow as update_studio_workflow,
    validate_workflow,
)
from app.incept.workflows import (
    Workflow,
    WorkflowCreateRequest,
    WorkflowEvent,
    WorkflowNodeDefinition,
    WorkflowOutput,
    WorkflowLineage,
    WorkflowRun,
    WorkflowRunNode,
    WorkflowRunRequest,
    WorkflowRevision,
    WorkflowUpdateRequest,
    WorkflowValidationResult,
    list_node_definitions,
)

router = APIRouter(tags=["incept"])
settings = get_settings()


def _scope_owner(scope: str, user: User) -> str | None:
    normalized = (scope or "mine").strip().lower()
    if normalized == "all":
        return None
    return user.id


def _require_owner_or_manager(owner_id: str | None, user: User, resource: str) -> None:
    """Keep workspace-wide browsing read-only for content not owned by the user."""
    if owner_id != user.id and user.role not in (Role.manager, Role.admin):
        raise HTTPException(status_code=403, detail=f"Only the owner can modify this {resource}.")


def _asset_response(asset: Asset) -> Asset:
    return asset.model_copy(update={"preview_url": build_asset_content_path(asset.id)})


def _guess_response_media_type(asset: Asset) -> str:
    if asset.type == "playable":
        return "text/html; charset=utf-8"
    if asset.type == "gif":
        return "image/gif"
    if asset.type == "video":
        suffix = guess_asset_extension(asset).lower()
        if suffix == ".webm":
            return "video/webm"
        if suffix == ".mov":
            return "video/quicktime"
        return "video/mp4"
    suffix = guess_asset_extension(asset).lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"

# Ensure static dirs exist (idempotent — safe to call every startup)
_static_root = Path(__file__).parent.parent.parent / "static"
(_static_root / "generated").mkdir(parents=True, exist_ok=True)
(_static_root / "uploads").mkdir(parents=True, exist_ok=True)

# Placeholder image for mock assets
_placeholder = _static_root / "placeholder.png"
if not _placeholder.exists():
    import base64
    _PNG1X1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    _placeholder.write_bytes(_PNG1X1)


# ── User / config endpoints ───────────────────────────────────────────────────

@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/provider-config", response_model=ProviderConfig)
def provider_config(user: User = Depends(get_current_user)) -> ProviderConfig:
    require_role(user, Role.manager)
    return ProviderConfig(
        default_image_provider=settings.default_image_provider,
        openai_image_model=settings.openai_image_model,
        vertex_imagen_model=settings.vertex_imagen_model,
        vertex_veo_fast_model=settings.vertex_veo_fast_model or None,
        vertex_veo_model=settings.vertex_veo_model or None,
        vertex_ai_enabled=settings.vertex_ai_enabled,
        gcp_project_id=settings.gcp_project_id,
        gcp_location=settings.gcp_location,
        asset_bucket=settings.incept_asset_bucket,
        max_image_variants=settings.max_image_variants,
        max_output_sizes=settings.max_output_sizes,
    )


@router.get("/tools", response_model=list[ToolDefinition])
def list_tools() -> list[ToolDefinition]:
    return get_tools()


@router.patch("/tools/{tool_id}", response_model=ToolDefinition)
def patch_tool_status(
    tool_id: str,
    update: ToolStatusUpdate,
    user: User = Depends(get_current_user),
) -> ToolDefinition:
    require_role(user, Role.admin)
    tool = update_tool_status(tool_id, update.status)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


# ── Workspaces / jobs / assets / threads / usage ─────────────────────────────

@router.get("/workspaces", response_model=list[Workspace])
def workspaces(user: User = Depends(get_current_user)) -> list[Workspace]:
    return list_workspaces()


@router.get("/jobs", response_model=list[GenerationJob])
def jobs(
    workspace_id: str | None = None,
    scope: str = "mine",
    user: User = Depends(get_current_user),
) -> list[GenerationJob]:
    return list_jobs(workspace_id=workspace_id, created_by=_scope_owner(scope, user))


@router.get("/jobs/{job_id}", response_model=GenerationJob)
def job_detail(job_id: str, user: User = Depends(get_current_user)) -> GenerationJob:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=GenerationJob)
def cancel_job(job_id: str, user: User = Depends(get_current_user)) -> GenerationJob:
    """Mark a running job as cancelled."""
    from app.incept.db import upsert_job

    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (job.status.running, job.status.queued):
        job.status = JobStatus.failed
        job.message = "Cancelled by user"
        job.progress = 0
        job.updated_at = datetime.utcnow()
        upsert_job(job)
    return job


@router.get("/assets", response_model=list[Asset])
def assets(
    workspace_id: str | None = None,
    scope: str = "mine",
    user: User = Depends(get_current_user),
) -> list[Asset]:
    return [_asset_response(asset) for asset in list_assets(workspace_id, created_by=_scope_owner(scope, user))]


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset_endpoint(
    asset_id: str,
    user: User = Depends(get_current_user),
) -> None:
    asset = ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    _require_owner_or_manager(asset.created_by, user, "asset")
    found = delete_asset(asset_id)
    if not found:
        raise HTTPException(status_code=404, detail="Asset not found")


@router.post("/assets/upload", response_model=Asset)
async def upload_asset(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    asset_role: str = Form(default="source"),
    thread_id: str | None = Form(default=None),
    user: User = Depends(get_current_user),
) -> Asset:
    content = await file.read()
    try:
        asset = save_uploaded_asset(
            workspace_id=workspace_id,
            filename=file.filename or "upload.png",
            content=content,
            asset_role=asset_role,
            user_id=user.id,
            thread_id=thread_id,
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _asset_response(asset)


@router.get("/assets/{asset_id}/content", response_model=None)
def asset_content(asset_id: str, request: Request, user: User = Depends(get_current_user)) -> StreamingResponse | Response:
    asset = ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = _guess_response_media_type(asset)
    # Browser video elements request byte ranges to read MP4 metadata and seek
    # before loading the full file. StreamingResponse alone returns a chunked
    # 200 response, which leaves Chrome/Safari with a black preview for many
    # GCS-backed Veo files. Serve video as a standards-compliant byte resource.
    if asset.type == "video":
        content = read_asset_bytes(asset)
        if content is None:
            raise HTTPException(status_code=404, detail="Asset content not found")
        total = len(content)
        common_headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        range_header = request.headers.get("range", "").strip()
        if not range_header:
            return Response(
                content=content,
                media_type=media_type,
                headers={**common_headers, "Content-Length": str(total)},
            )
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match:
            raise HTTPException(status_code=416, detail="Invalid video byte range", headers={"Content-Range": f"bytes */{total}"})
        start_text, end_text = match.groups()
        if not start_text and not end_text:
            raise HTTPException(status_code=416, detail="Invalid video byte range", headers={"Content-Range": f"bytes */{total}"})
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else total - 1
        else:
            suffix_length = int(end_text)
            start = max(total - suffix_length, 0)
            end = total - 1
        if start >= total or start < 0 or end < start:
            raise HTTPException(status_code=416, detail="Video byte range is outside the asset", headers={"Content-Range": f"bytes */{total}"})
        end = min(end, total - 1)
        body = content[start:end + 1]
        return Response(
            content=body,
            status_code=206,
            media_type=media_type,
            headers={
                **common_headers,
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Content-Length": str(len(body)),
            },
        )
    return StreamingResponse(
        stream_asset_bytes(asset),
        media_type=media_type,
    )


class DownloadZipRequest(BaseModel):
    asset_ids: list[str]


@router.post("/assets/download-zip")
async def download_assets_zip(
    body: DownloadZipRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Package requested assets as a zip file using each asset's own title."""

    buf = io.BytesIO()
    filename_count: dict[str, int] = {}
    added = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset_id in body.asset_ids:
            asset = ASSETS.get(asset_id)
            if not asset:
                continue
            ext = guess_asset_extension(asset).lstrip(".") or ("gif" if asset.type == "gif" else "png")
            base_name = Path(asset.title or asset.id).stem.strip() or asset.id
            filename_count[base_name] = filename_count.get(base_name, 0) + 1
            variant_index = filename_count[base_name]
            filename = (
                f"{base_name}.{ext}"
                if variant_index == 1
                else f"{base_name}_v{variant_index}.{ext}"
            )
            content = read_asset_bytes(asset)
            if content is None:
                continue
            zf.writestr(filename, content)
            added += 1

    if added == 0:
        raise HTTPException(status_code=404, detail="No downloadable files found for the given asset IDs.")

    buf.seek(0)
    zip_bytes = buf.read()
    download_name = "assets.zip"
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; filename="assets.zip"; '
                f"filename*=UTF-8''{quote(download_name)}"
            ),
            "Content-Length": str(len(zip_bytes)),
        },
    )


@router.get("/threads", response_model=list[CreativeThread])
def threads(
    workspace_id: str | None = None,
    scope: str = "mine",
    user: User = Depends(get_current_user),
) -> list[CreativeThread]:
    items = list_threads(workspace_id, created_by=_scope_owner(scope, user))
    return [
        thread.model_copy(
            update={
                "preview_url": build_asset_content_path(thread.cover_asset_id)
                if thread.cover_asset_id
                else thread.preview_url
            }
        )
        for thread in items
    ]


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread_endpoint(thread_id: str, user: User = Depends(get_current_user)) -> None:
    from app.incept import thread_store as ts
    thread = ts.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_owner_or_manager(thread.created_by, user, "thread")
    if not ts.delete_thread(thread_id):
        raise HTTPException(status_code=404, detail="Thread not found")


class RenameThreadRequest(BaseModel):
    title: str


@router.patch("/threads/{thread_id}", response_model=CreativeThread)
def rename_thread_endpoint(
    thread_id: str,
    body: RenameThreadRequest,
    user: User = Depends(get_current_user),
) -> CreativeThread:
    from app.incept import thread_store as ts
    existing = ts.get_thread(thread_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_owner_or_manager(existing.created_by, user, "thread")
    thread = ts.rename_thread(thread_id, body.title)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.delete("/threads", status_code=200)
def cleanup_empty_threads(user: User = Depends(get_current_user)) -> dict:
    """Delete all threads with 0 assets and 0 jobs."""
    from app.incept import thread_store as ts
    count = ts.delete_empty_threads()
    return {"deleted": count}


@router.get("/usage", response_model=list[UsageEvent])
def usage(
    workspace_id: str | None = None,
    user: User = Depends(get_current_user),
) -> list[UsageEvent]:
    require_role(user, Role.manager)
    return list_usage_events(workspace_id)


@router.get("/usage-summary")
def usage_summary(user: User = Depends(get_current_user)) -> dict:
    """Return personal Studio usage; admins additionally receive all-user totals."""
    from collections import defaultdict

    def summarize(events: list[UsageEvent], email: str = "") -> dict:
        summary = {
            "email": email,
            "generation_count": 0,
            "asset_count": 0,
            "estimated_cost_usd": 0.0,
            "image_generation_count": 0,
            "image_asset_count": 0,
            "image_estimated_cost_usd": 0.0,
            "video_generation_count": 0,
            "video_asset_count": 0,
            "video_estimated_cost_usd": 0.0,
        }
        for event in events:
            cost = event.actual_cost_usd if event.actual_cost_usd is not None else event.estimated_cost_usd
            summary["generation_count"] += 1
            summary["asset_count"] += event.output_asset_count
            summary["estimated_cost_usd"] += cost
            if event.operation == "video_generation":
                summary["video_generation_count"] += 1
                summary["video_asset_count"] += event.output_asset_count
                summary["video_estimated_cost_usd"] += cost
            elif event.operation == "image_generation":
                summary["image_generation_count"] += 1
                summary["image_asset_count"] += event.output_asset_count
                summary["image_estimated_cost_usd"] += cost
        for key in ("estimated_cost_usd", "image_estimated_cost_usd", "video_estimated_cost_usd"):
            summary[key] = round(float(summary[key]), 4)
        return summary

    events = list_usage_events()
    mine = [event for event in events if event.user_id == user.id]
    summaries: list[dict] = []
    if user.role == Role.admin:
        grouped: dict[str, list[UsageEvent]] = defaultdict(list)
        for event in events:
            grouped[event.user_email or event.user_id].append(event)
        summaries = [summarize(group, email) for email, group in grouped.items()]

    return {
        "budget_usd": max(0.0, settings.studio_user_budget_usd),
        "my_summary": summarize(mine, user.email),
        "user_summaries": summaries,
    }


# ── Independent Video Production Workspace ───────────────────────────────────

@router.post("/prompt-reviewer", response_model=PromptReviewResponse)
def prompt_reviewer_endpoint(
    request: PromptReviewRequest,
    user: User = Depends(get_current_user),
) -> PromptReviewResponse:
    """Run the internal reviewer without exposing it to any production context."""
    try:
        return review_prompt(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Prompt Reviewer failed: {exc}") from exc


# ── GamingPlayable projects and templates ────────────────────────────────────

@router.get("/playable-projects", response_model=list[PlayableProject])
def playable_projects_endpoint(
    workspace_id: str = "wsp_q2",
    user: User = Depends(get_current_user),
) -> list[PlayableProject]:
    return list_playable_projects(workspace_id, user)


@router.get("/playable-projects/{project_id}", response_model=PlayableProject)
def playable_project_endpoint(
    project_id: str,
    user: User = Depends(get_current_user),
) -> PlayableProject:
    try:
        return get_playable_project(project_id, user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.post("/playable-projects", response_model=PlayableProject)
def save_playable_project_endpoint(
    request: PlayableProjectSaveRequest,
    user: User = Depends(get_current_user),
) -> PlayableProject:
    try:
        return save_playable_project(request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/playable-templates", response_model=list[PlayableTemplate])
def playable_templates_endpoint(
    workspace_id: str = "wsp_q2",
    user: User = Depends(get_current_user),
) -> list[PlayableTemplate]:
    return list_playable_templates(workspace_id, user)


@router.post("/playable-templates", response_model=PlayableTemplate)
def create_playable_template_endpoint(
    request: PlayableTemplateCreateRequest,
    user: User = Depends(get_current_user),
) -> PlayableTemplate:
    try:
        return create_playable_template(request, user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/playable-templates/{template_id}/favorite", response_model=PlayableTemplate)
def toggle_playable_template_favorite_endpoint(
    template_id: str,
    user: User = Depends(get_current_user),
) -> PlayableTemplate:
    try:
        return toggle_template_favorite(template_id, user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/playable-templates/{template_id}/fork", response_model=PlayableProject)
def fork_playable_template_endpoint(
    template_id: str,
    request: PlayableTemplateForkRequest,
    user: User = Depends(get_current_user),
) -> PlayableProject:
    try:
        return fork_playable_template(template_id, user, request.title)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

'''Legacy Video Production routes were removed in favour of VideoProduction.'''
'''
@router.get("/video-productions", response_model=list[VideoProduction])
def video_productions(
    workspace_id: str,
    scope: str = "mine",
    include_archived: bool = False,
    user: User = Depends(get_current_user),
) -> list[VideoProduction]:
    try:
        return list_video_productions(workspace_id, user, scope=scope, include_archived=include_archived)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/video-production-capabilities", response_model=VideoProductionProviderCapabilities)
def video_production_capabilities(user: User = Depends(get_current_user)) -> VideoProductionProviderCapabilities:
    """Safe catalogue for project-scoped choices; never exposes deployment secrets."""
    return configured_video_production_capabilities()


@router.post("/video-productions", response_model=VideoProduction)
def create_video_production_endpoint(
    request: VideoProductionCreateRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return create_video_production(request, user)
    except ValueError as exc:
        # Model/provider choices are validated against the server catalogue;
        # make a stale or tampered form actionable without exposing a 500.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/fork", response_model=VideoProduction)
def fork_video_production_endpoint(
    production_id: str,
    payload: dict[str, str],
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return fork_video_production(production_id, payload.get("label", "Variant"), user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/video-productions/{production_id}", response_model=VideoProduction)
def video_production(
    production_id: str,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        production = get_video_production(production_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not production:
        raise HTTPException(status_code=404, detail="Video production not found")
    return production


@router.get("/video-productions/{production_id}/events", response_model=list[VideoProductionEvent])
def video_production_events(
    production_id: str,
    limit: int = 40,
    user: User = Depends(get_current_user),
) -> list[VideoProductionEvent]:
    try:
        return list_video_production_events(production_id, user, limit=limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/video-productions/{production_id}/events/stream")
async def video_production_events_stream(
    production_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream a snapshot plus newly persisted activity receipts.

    This is deliberately a read-model stream, not a second write path. A
    deployment without a shared event bus still observes cross-instance saves
    because each poll reads the durable database. Clients receive a snapshot on
    connect, so reconnecting after an overflow or proxy restart is safe.
    """
    try:
        initial = list_video_production_events(production_id, user, limit=200)
        production = get_video_production(production_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not production:
        raise HTTPException(status_code=404, detail="Video production not found")

    def encode(event: str, payload: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    async def stream():
        seen = {entry.event_id for entry in initial}
        yield encode("snapshot", {
            "production_id": production_id,
            "state_revision": production.state_revision,
            "latest_event_id": initial[0].event_id if initial else None,
        })
        # Heartbeats make a proxy-held but silent connection observable to the
        # browser. Polling durable storage is intentionally conservative until
        # a deployment-owned broker/worker lease is introduced.
        while not await request.is_disconnected():
            await asyncio.sleep(4)
            try:
                current = list_video_production_events(production_id, user, limit=200)
            except (PermissionError, KeyError):
                yield encode("access_revoked", {"production_id": production_id})
                return
            new_events = [event for event in reversed(current) if event.event_id not in seen]
            for event in new_events:
                seen.add(event.event_id)
                yield encode("activity", event.model_dump(mode="json"))
            if len(seen) > 400:
                seen = {entry.event_id for entry in current}
            yield ": keepalive\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.patch("/video-productions/{production_id}", response_model=VideoProduction)
def update_video_production_endpoint(
    production_id: str,
    request: VideoProductionUpdateRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return update_video_production(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/video-productions/{production_id}", status_code=204)
def delete_video_production_endpoint(
    production_id: str,
    user: User = Depends(get_current_user),
) -> None:
    try:
        delete_video_production(production_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/archive", response_model=VideoProduction)
def archive_video_production_endpoint(
    production_id: str,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return archive_video_production(production_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/restore", response_model=VideoProduction)
def restore_video_production_endpoint(
    production_id: str,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return restore_video_production(production_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/script-revisions/{revision_id}/restore", response_model=VideoProduction)
def restore_video_production_script_revision_endpoint(
    production_id: str,
    revision_id: str,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return restore_video_production_script_revision(production_id, revision_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/script-agent", response_model=VideoProduction)
def video_production_script_agent(
    production_id: str,
    request: VideoProductionAgentRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return run_script_agent(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # Validation failures are expected for an incomplete model draft; they
        # must be visible to the UI without presenting an opaque server error.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/copilot", response_model=VideoProductionCopilotResponse)
def video_production_copilot(
    production_id: str,
    request: VideoProductionCopilotRequest,
    user: User = Depends(get_current_user),
) -> VideoProductionCopilotResponse:
    try:
        return run_production_copilot(production_id, request, user)
    except CopilotQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/copilot/cancel", status_code=204)
def cancel_video_production_copilot(
    production_id: str,
    user: User = Depends(get_current_user),
) -> None:
    try:
        cancel_production_copilot(production_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/creative-director", response_model=VideoProduction)
def video_production_creative_director(
    production_id: str,
    request: VideoProductionAgentRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return run_creative_director(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Preserve the production's last good Direction and give the client a
        # recoverable provider/analysis error instead of an opaque 500.
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/production-designer", response_model=VideoProduction)
def video_production_designer(
    production_id: str,
    request: VideoProductionAgentRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return run_production_designer(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/director", response_model=VideoProduction)
def video_production_director(
    production_id: str,
    request: VideoProductionAgentRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return run_director_agent(production_id, request, user)
    except ValueError as exc:
        # A malformed model response is a recoverable request-validation
        # failure, not an unhandled 500. Existing prompts remain untouched.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/edit-review", response_model=VideoProduction)
def video_production_edit_review(
    production_id: str,
    request: VideoProductionAgentRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return run_edit_reviewer(production_id, request, user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/lock-script", response_model=VideoProduction)
def lock_video_production_script(
    production_id: str,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return lock_script_and_create_storyboard(production_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/approve-storyboard", response_model=VideoProduction)
def approve_video_production_storyboard(
    production_id: str,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return approve_storyboard(production_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/video-productions/{production_id}/shots/{shot_id}", response_model=VideoProduction)
def update_video_production_shot_endpoint(
    production_id: str,
    shot_id: str,
    request: VideoProductionShotUpdateRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return update_video_production_shot(production_id, shot_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/shots", response_model=VideoProduction)
def create_video_production_shot_endpoint(
    production_id: str,
    request: VideoProductionShotCreateRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return create_video_production_shot(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/video-productions/{production_id}/shots/{shot_id}", response_model=VideoProduction)
def delete_video_production_shot_endpoint(
    production_id: str,
    shot_id: str,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return delete_video_production_shot(production_id, shot_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/shots/reorder", response_model=VideoProduction)
def reorder_video_production_shots_endpoint(
    production_id: str,
    request: VideoProductionShotOrderRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return reorder_video_production_shots(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/shots/{shot_id}/keyframe", response_model=GenerationJob)
def generate_video_production_keyframe(
    production_id: str,
    shot_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    try:
        job = create_keyframe_job(production_id, shot_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_keyframe_background, production_id, shot_id, job.job_id, user)
    return job


@router.post("/video-productions/{production_id}/design-sheets/{sheet_id}/generate", response_model=GenerationJob)
def generate_video_production_design_sheet(
    production_id: str,
    sheet_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    try:
        job = create_design_sheet_job(production_id, sheet_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_design_sheet_background, production_id, sheet_id, job.job_id, user)
    return job


@router.post("/video-productions/{production_id}/design-sheets/{sheet_id}/cancel", response_model=VideoProduction)
def cancel_video_production_design_sheet(
    production_id: str,
    sheet_id: str,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return cancel_design_sheet_generation(production_id, sheet_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/scene-reframes", response_model=GenerationJob)
def reframe_video_production_scene(
    production_id: str,
    request: VideoProductionSceneReframeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    try:
        job, sheet = create_scene_reframe_job(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(
        run_scene_reframe_background,
        production_id,
        sheet.id,
        job.job_id,
        user,
    )
    return job


@router.post("/video-productions/{production_id}/design-sheets", response_model=VideoProduction)
def create_video_production_design_sheet(
    production_id: str,
    request: VideoProductionDesignSheetCreateRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return create_custom_design_sheet(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/video-productions/{production_id}/design-sheets/{sheet_id}", response_model=VideoProduction)
def update_video_production_design_sheet(
    production_id: str,
    sheet_id: str,
    request: VideoProductionDesignSheetUpdateRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return update_custom_design_sheet(production_id, sheet_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/video-productions/{production_id}/design-sheets/{sheet_id}", status_code=204)
def delete_video_production_design_sheet(
    production_id: str,
    sheet_id: str,
    user: User = Depends(get_current_user),
) -> None:
    try:
        delete_custom_design_sheet(production_id, sheet_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/design-sheets/{sheet_id}/select", response_model=VideoProduction)
async def select_video_production_design_sheet_panel(
    production_id: str,
    sheet_id: str,
    request: VideoProductionDesignSheetSelectionRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return await select_design_sheet_panel(production_id, sheet_id, request.panel, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/shots/{shot_id}/generate", response_model=GenerationJob)
def generate_video_production_shot(
    production_id: str,
    shot_id: str,
    background_tasks: BackgroundTasks,
    _request: VideoProductionShotRenderRequest,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    try:
        job = create_shot_video_job(production_id, shot_id, user, variants=_request.variants)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_shot_video_background, production_id, shot_id, job.job_id, user)
    return job


@router.post("/video-productions/{production_id}/shots/{shot_id}/bridge-frame", response_model=VideoProduction)
def extract_video_production_bridge_frame_endpoint(
    production_id: str,
    shot_id: str,
    request: VideoProductionBridgeFrameRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return extract_video_production_bridge_frame(production_id, shot_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/audio-producer", response_model=VideoProduction)
def run_video_production_audio_producer_endpoint(
    production_id: str,
    request: VideoProductionAgentRequest,
    user: User = Depends(get_current_user),
) -> VideoProduction:
    try:
        return run_audio_producer(production_id, request, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/video-productions/{production_id}/audio/generate", response_model=GenerationJob)
def generate_video_production_soundtrack(
    production_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    try:
        job = create_production_audio_job(production_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_production_audio_background, production_id, job.job_id, user)
    return job


@router.post("/video-productions/{production_id}/render", response_model=GenerationJob)
def render_video_production_first_cut(
    production_id: str,
    background_tasks: BackgroundTasks,
    _request: VideoProductionRenderRequest,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    try:
        job = create_production_render_job(production_id, user, include_audio=_request.include_audio)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_production_render_background, production_id, job.job_id, user, _request.include_audio)
    return job


'''
@router.get("/theme-create/reports", response_model=list[ThemeCreateStyleReport])
def theme_create_reports(
    workspace_id: str | None = None,
    mode: str | None = None,
    user: User = Depends(get_current_user),
) -> list[ThemeCreateStyleReport]:
    require_role(user, Role.manager)
    return list_theme_create_reports(workspace_id, mode)


@router.post("/theme-create/reports", response_model=ThemeCreateStyleReport)
def create_theme_create_report_endpoint(
    body: ThemeCreateStyleReportCreateRequest,
    user: User = Depends(get_current_user),
) -> ThemeCreateStyleReport:
    require_role(user, Role.manager)
    payload = body.model_copy(update={"created_by": user.id})
    return create_theme_create_report(payload)


@router.post("/theme-create/reports/draft", response_model=ThemeCreateStyleReportCreateRequest)
def draft_theme_create_report_endpoint(
    body: ThemeCreateStyleReportDraftRequest,
    user: User = Depends(get_current_user),
) -> ThemeCreateStyleReportCreateRequest:
    require_role(user, Role.manager)
    return draft_theme_create_report(body, user.id)


@router.get("/theme-create/presets", response_model=list[ThemeCreatePreset])
def theme_create_presets(
    workspace_id: str | None = None,
    mode: str | None = None,
    user: User = Depends(get_current_user),
) -> list[ThemeCreatePreset]:
    require_role(user, Role.manager)
    return list_theme_create_presets(workspace_id, mode)


@router.post("/theme-create/presets", response_model=ThemeCreatePreset)
def create_theme_create_preset_endpoint(
    body: ThemeCreatePresetCreateRequest,
    user: User = Depends(get_current_user),
) -> ThemeCreatePreset:
    require_role(user, Role.manager)
    payload = body.model_copy(update={"created_by": user.id})
    return create_theme_create_preset(payload)


@router.post("/theme-create/reports/{report_id}/save-as-preset", response_model=ThemeCreatePreset)
def save_theme_create_report_as_preset(
    report_id: str,
    body: ThemeCreatePresetFromReportRequest,
    user: User = Depends(get_current_user),
) -> ThemeCreatePreset:
    require_role(user, Role.manager)
    preset = create_theme_create_preset_from_report(report_id, body, user.id)
    if not preset:
        raise HTTPException(status_code=404, detail="Theme create report not found")
    return preset


# ── Workflow endpoints ────────────────────────────────────────────────────────

@router.get("/studio-workflow-node-definitions", response_model=list[WorkflowNodeDefinition])
def list_studio_workflow_node_definitions_endpoint(
    user: User = Depends(get_current_user),
) -> list[WorkflowNodeDefinition]:
    """Catalog is server-owned so browser graphs cannot invent unsafe node types."""
    return list_node_definitions()

@router.get("/studio-workflows", response_model=list[Workflow])
def list_studio_workflows_endpoint(
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> list[Workflow]:
    return list_studio_workflows(workspace_id)


@router.post("/studio-workflows", response_model=Workflow)
def create_studio_workflow_endpoint(
    request: WorkflowCreateRequest,
    user: User = Depends(get_current_user),
) -> Workflow:
    return create_workflow(request, user.id)


@router.get("/studio-workflows/{workflow_id}", response_model=Workflow)
def get_studio_workflow_endpoint(
    workflow_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> Workflow:
    workflow = get_workflow(workflow_id, workspace_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.get("/studio-workflows/{workflow_id}/revisions", response_model=list[WorkflowRevision])
def list_studio_workflow_revisions_endpoint(
    workflow_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> list[WorkflowRevision]:
    try:
        return list_workflow_revisions(workflow_id, workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/studio-workflows/{workflow_id}/outputs", response_model=list[WorkflowOutput])
def list_studio_workflow_outputs_endpoint(
    workflow_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> list[WorkflowOutput]:
    if get_workflow(workflow_id, workspace_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return list_workflow_outputs(workflow_id, workspace_id)


@router.get("/studio-workflows/{workflow_id}/lineage", response_model=WorkflowLineage)
def get_studio_workflow_lineage_endpoint(
    workflow_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> WorkflowLineage:
    try:
        return get_workflow_lineage(workflow_id, workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/studio-workflows/{workflow_id}", response_model=Workflow)
def update_studio_workflow_endpoint(
    workflow_id: str,
    request: WorkflowUpdateRequest,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> Workflow:
    try:
        return update_studio_workflow(workflow_id, request, workspace_id, user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/studio-workflows/{workflow_id}", status_code=204)
def delete_studio_workflow_endpoint(
    workflow_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> None:
    if not delete_workflow(workflow_id, workspace_id):
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post("/studio-workflows/{workflow_id}/validate", response_model=WorkflowValidationResult)
def validate_studio_workflow_endpoint(
    workflow_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> WorkflowValidationResult:
    try:
        return validate_workflow(workflow_id, workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/studio-workflows/{workflow_id}/runs", response_model=WorkflowRun)
def create_studio_workflow_run_endpoint(
    workflow_id: str,
    request: WorkflowRunRequest,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> WorkflowRun:
    try:
        return create_workflow_run(workflow_id, workspace_id, request, user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/studio-workflow-runs/{run_id}/events", response_model=list[WorkflowEvent])
def list_studio_workflow_events_endpoint(
    run_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> list[WorkflowEvent]:
    if not run_in_workspace(run_id, workspace_id):
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return list_workflow_events(run_id)


@router.get("/studio-workflow-runs/{run_id}/events/stream")
async def stream_studio_workflow_events_endpoint(
    run_id: str,
    after_event_id: str | None = None,
    workspace_id: str = "",
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE feed backed by durable event rows; safe to reconnect after a tab sleep."""
    if not run_in_workspace(run_id, workspace_id):
        raise HTTPException(status_code=404, detail="Workflow run not found")
    async def event_stream():
        cursor = after_event_id
        idle_cycles = 0
        while idle_cycles < 120:
            events = list_workflow_events(run_id)
            if cursor:
                try:
                    start = next(index + 1 for index, event in enumerate(events) if event.event_id == cursor)
                    events = events[start:]
                except StopIteration:
                    pass
            if events:
                idle_cycles = 0
                for event in events:
                    cursor = event.event_id
                    yield f"id: {event.event_id}\nevent: {event.type}\ndata: {json.dumps(event.model_dump(mode='json'))}\n\n"
            else:
                idle_cycles += 1
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/studio-workflow-runs/{run_id}/nodes", response_model=list[WorkflowRunNode])
def list_studio_workflow_run_nodes_endpoint(
    run_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> list[WorkflowRunNode]:
    if not run_in_workspace(run_id, workspace_id):
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return list_workflow_run_nodes(run_id)


@router.post("/studio-workflow-runs/{run_id}/cancel", response_model=WorkflowRun)
def cancel_studio_workflow_run_endpoint(
    run_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> WorkflowRun:
    run = cancel_workflow_run(run_id, workspace_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return run


@router.post("/studio-workflow-runs/{run_id}/retry", response_model=WorkflowRun)
def retry_studio_workflow_run_endpoint(
    run_id: str,
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> WorkflowRun:
    try:
        return retry_workflow_run(run_id, workspace_id, user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/workflows/image-generation", response_model=GenerationJob)
async def create_image_generation_job_endpoint(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.variants > settings.max_image_variants:
        raise HTTPException(
            status_code=400,
            detail=f"variants cannot exceed {settings.max_image_variants}",
        )
    try:
        assert_image_budget_available(request, user)
    except RuntimeError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    job = create_image_generation_job(request, user)
    if job.status.value == "running":
        background_tasks.add_task(run_generation_background, job.job_id, request, user)
    if job.thread_id:
        thread_store.add_user_message(
            job.thread_id,
            text=request.prompt,
            reference_asset_ids=request.reference_asset_ids + request.client_asset_ids + request.source_asset_ids,
        )
    return job


@router.post("/workflows/remediation-analyze", response_model=RemediationAnalysisResponse)
def remediation_analyze_endpoint(
    request: RemediationAnalysisRequest,
    user: User = Depends(get_current_user),
) -> RemediationAnalysisResponse:
    require_role(user, Role.manager)
    return analyze_remediation_assets(request, user.id)


'''Legacy AI Video workflow routes were removed in favour of VideoProduction.'''
'''
@router.post("/workflows/video-generation", response_model=GenerationJob)
async def create_video_generation_job_endpoint(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.video_generation_mode in {
        VideoGenerationMode.image_to_video,
        VideoGenerationMode.competitor_style_transfer,
    } and request.duration_seconds not in {4, 6, 8, 15, 30, 60}:
        raise HTTPException(status_code=400, detail="Veo supports 4, 6, or 8 second shots; longer targets are assembled through Veo Extend.")
    request = request.model_copy(update={"include_audio": False})
    try:
        request = confirm_video_generation_plan_for_request(request, user)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    reference_asset_ids = [
        asset_id
        for asset_id in [request.source_asset_id, request.end_frame_asset_id, *request.reference_asset_ids]
        if asset_id
    ]
    for asset_id in reference_asset_ids:
        if asset_id not in ASSETS and asset_id not in SOURCE_ASSETS:
            raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    try:
        assert_video_budget_available(request, user)
    except RuntimeError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    job = create_video_generation_job(request, user)
    background_tasks.add_task(run_video_generation_background, job.job_id, request, user)
    if job.thread_id and not request.plan_id:
        thread_store.add_user_message(
            job.thread_id,
            text=request.prompt or f"[Video] {request.video_generation_mode.value}",
            reference_asset_ids=reference_asset_ids,
        )
    elif job.thread_id:
        thread_store.add_assistant_message(
            job.thread_id,
            text="Starting video generation from the agreed plan.",
            asset_ids=[],
            job_id=job.job_id,
        )
    return job


@router.post("/workflows/video-plan", response_model=VideoPlanResponse)
def video_plan_endpoint(
    request: VideoPlanRequest,
    user: User = Depends(get_current_user),
) -> VideoPlanResponse:
    try:
        return create_or_update_video_plan(request, user)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workflows/video-plan", response_model=list[VideoPlanResponse])
def list_video_plan_endpoint(
    thread_id: str,
    user: User = Depends(get_current_user),
) -> list[VideoPlanResponse]:
    return [VideoPlanResponse(plan=plan) for plan in list_video_generation_plans(thread_id, user)]


'''
@router.post("/workflows/image-edit", response_model=GenerationJob)
async def image_edit_endpoint(
    request: ImageEditRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.asset_id not in ASSETS and request.asset_id not in SOURCE_ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {request.asset_id} not found")
    job = create_edit_job(request, user)
    background_tasks.add_task(run_edit_background, job.job_id, request, user)
    if job.thread_id:
        thread_store.add_user_message(
            job.thread_id,
            text=f"[Edit] {request.prompt}",
            reference_asset_ids=[request.asset_id, *request.extra_asset_ids],
        )
    return job


@router.post("/workflows/generate-gif", response_model=GenerationJob)
async def generate_gif_endpoint(
    request: GenerateGifRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.asset_id not in ASSETS and request.asset_id not in SOURCE_ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {request.asset_id} not found")
    job = create_generate_gif_job(request, user)
    background_tasks.add_task(run_generate_gif_background, job.job_id, request, user)
    if job.thread_id:
        thread_store.add_user_message(
            job.thread_id,
            text="[Generate GIF] CTA pulse animation",
            reference_asset_ids=[request.asset_id],
        )
    return job


@router.post("/workflows/kakao-clean", response_model=GenerationJob)
async def kakao_clean_endpoint(
    request: KakaoCleanRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.asset_id not in ASSETS and request.asset_id not in SOURCE_ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {request.asset_id} not found")
    job = create_kakao_clean_job(request, user)
    background_tasks.add_task(run_kakao_clean_background, job.job_id, request, user)
    if job.thread_id:
        thread_store.add_user_message(
            job.thread_id,
            text="[Kakao Clean] Remove logo and text",
            reference_asset_ids=[request.asset_id],
        )
    return job


@router.post("/workflows/kakao-bizboard", response_model=GenerationJob)
async def kakao_bizboard_endpoint(
    request: KakaoBizboardComposeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.cleaned_asset_id not in ASSETS and request.cleaned_asset_id not in SOURCE_ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {request.cleaned_asset_id} not found")
    if request.composed_asset_id not in ASSETS and request.composed_asset_id not in SOURCE_ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {request.composed_asset_id} not found")
    job = create_kakao_bizboard_job(request, user)
    background_tasks.add_task(run_kakao_bizboard_background, job.job_id, request, user)
    if job.thread_id:
        thread_store.add_user_message(
            job.thread_id,
            text=f"[Kakao Bizboard] {request.main_copy}",
            reference_asset_ids=[request.cleaned_asset_id],
        )
    return job


@router.post("/workflows/outpaint", response_model=GenerationJob)
async def outpaint_endpoint(
    request: OutpaintRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.asset_id not in ASSETS and request.asset_id not in SOURCE_ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {request.asset_id} not found")
    job = create_outpaint_job(request, user)
    if job.thread_id:
        thread_store.add_user_message(
            job.thread_id,
            text=f"[Outpaint] {request.direction}",
            reference_asset_ids=[request.asset_id],
        )
    background_tasks.add_task(run_outpaint_background, job.job_id, request, user)
    return job


@router.post("/workflows/remove-background", response_model=GenerationJob)
async def remove_bg_endpoint(
    request: RemoveBGRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.asset_id not in ASSETS and request.asset_id not in SOURCE_ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {request.asset_id} not found")
    job = create_remove_bg_job(request, user)
    if job.thread_id:
        thread_store.add_user_message(
            job.thread_id,
            text=f"[Remove background] {request.replacement_prompt or 'transparent background'}",
            reference_asset_ids=[request.asset_id],
        )
    background_tasks.add_task(run_remove_bg_background, job.job_id, request, user)
    return job


@router.post("/workflows/add-text", response_model=GenerationJob)
async def add_text_endpoint(
    request: AddTextRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> GenerationJob:
    if request.asset_id not in ASSETS and request.asset_id not in SOURCE_ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {request.asset_id} not found")
    job = create_add_text_job(request, user)
    if job.thread_id:
        thread_store.add_user_message(
            job.thread_id,
            text=f"[Add text] {request.text}",
            reference_asset_ids=[request.asset_id],
        )
    background_tasks.add_task(run_add_text_background, job.job_id, request, user)
    return job


# ── Admin usage endpoint ──────────────────────────────────────────────────────

@router.get("/admin/usage")
def get_admin_usage(user: User = Depends(get_current_user)) -> dict:
    """Return per-user generation stats and recent generated assets. Admin only."""
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Admin role required")

    from collections import defaultdict
    stats: dict[str, dict] = defaultdict(lambda: {
        "email": "",
        "generation_count": 0,
        "asset_count": 0,
        "estimated_cost_usd": 0.0,
    })
    for event in list_usage_events():
        s = stats[event.user_email]
        s["email"] = event.user_email
        s["generation_count"] += 1
        s["asset_count"] += event.output_asset_count
        s["estimated_cost_usd"] = round(s["estimated_cost_usd"] + event.estimated_cost_usd, 4)

    recent_assets = sorted(
        [a for a in ASSETS.values()],
        key=lambda a: a.created_at,
        reverse=True,
    )[:300]

    return {
        "user_summaries": list(stats.values()),
        "recent_assets": [_asset_response(a) for a in recent_assets],
    }


# ── Session endpoints ─────────────────────────────────────────────────────────

@router.post("/sessions", response_model=Session)
def create_session_endpoint(
    workspace_id: str,
    user: User = Depends(get_current_user),
) -> Session:
    return session_store.create_session(workspace_id)


@router.get("/sessions/{session_id}", response_model=Session)
def get_session_endpoint(
    session_id: str,
    user: User = Depends(get_current_user),
) -> Session:
    s = session_store.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s
