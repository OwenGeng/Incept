"""
Incept router — all Incept image-generation endpoints.

Mounted into the unified nbs-api at root level (no prefix), so the
Next.js proxy at /api/incept/[...path] can forward calls unchanged:
  browser  →  /api/incept/assets
  proxy    →  <API_BASE_URL>/assets          (Incept)
  browser  →  /api/v1/supply-smb/...         (InterSight — different prefix, no conflict)
"""

import io
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
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
    ImageEditRequest,
    JobStatus,
    OutpaintRequest,
    ProviderConfig,
    RemoveBGRequest,
    Role,
    Session,
    ToolDefinition,
    ToolStatusUpdate,
    UsageEvent,
    User,
    Workspace,
)
from app.incept.store import (
    ASSETS,
    JOBS,
    SOURCE_ASSETS,
    STATIC_DIR,
    UPLOAD_DIR,
    create_add_text_job,
    create_edit_job,
    create_image_generation_job,
    create_outpaint_job,
    create_remove_bg_job,
    delete_asset,
    get_job,
    list_assets,
    list_jobs,
    list_threads,
    list_usage_events,
    list_workspaces,
    run_add_text_background,
    run_edit_background,
    run_generation_background,
    run_outpaint_background,
    run_remove_bg_background,
    save_uploaded_asset,
    split_saved_contact_sheet_asset,
)
from app.incept import session_store, thread_store
from app.incept.tool_registry import get_tools, update_tool_status

router = APIRouter(tags=["incept"])
settings = get_settings()

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
def jobs(user: User = Depends(get_current_user)) -> list[GenerationJob]:
    return list_jobs()


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
def assets(workspace_id: str | None = None, user: User = Depends(get_current_user)) -> list[Asset]:
    return list_assets(workspace_id)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset_endpoint(
    asset_id: str,
    user: User = Depends(get_current_user),
) -> None:
    found = delete_asset(asset_id)
    if not found:
        raise HTTPException(status_code=404, detail="Asset not found")


@router.post("/assets/upload", response_model=Asset)
async def upload_asset(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    asset_role: str = Form(default="source"),
    user: User = Depends(get_current_user),
) -> Asset:
    content = await file.read()
    return save_uploaded_asset(
        workspace_id=workspace_id,
        filename=file.filename or "upload.png",
        content=content,
        asset_role=asset_role,
        user_id=user.id,
    )


class DownloadZipRequest(BaseModel):
    asset_ids: list[str]
    prefix: str = "incept"


class ContactSheetSplitResponse(BaseModel):
    asset_ids: list[str]
    count: int


@router.post("/assets/download-zip")
async def download_assets_zip(
    body: DownloadZipRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Package requested assets as a zip file with dimension-based naming."""
    prefix = (body.prefix.strip().replace(" ", "_") or "incept")[:64]

    buf = io.BytesIO()
    size_count: dict[str, int] = {}
    added = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset_id in body.asset_ids:
            asset = ASSETS.get(asset_id)
            if not asset:
                continue
            if asset.width and asset.height:
                size_key = f"{asset.width}x{asset.height}"
            else:
                size_key = "unknown"
            size_count[size_key] = size_count.get(size_key, 0) + 1
            n = size_count[size_key]
            ext = "gif" if asset.type == "gif" else "png"
            filename = (
                f"{prefix}_{size_key}.{ext}" if n == 1 else f"{prefix}_{size_key}_v{n}.{ext}"
            )
            url = asset.preview_url
            if url.startswith("/static/generated/"):
                file_path = STATIC_DIR / url[len("/static/generated/"):]
            elif url.startswith("/static/uploads/"):
                file_path = UPLOAD_DIR / url[len("/static/uploads/"):]
            else:
                continue
            if file_path.exists():
                zf.write(str(file_path), filename)
                added += 1

    if added == 0:
        raise HTTPException(status_code=404, detail="No downloadable files found for the given asset IDs.")

    buf.seek(0)
    zip_bytes = buf.read()
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{prefix}_assets.zip"',
            "Content-Length": str(len(zip_bytes)),
        },
    )


@router.post("/assets/{asset_id}/split-contact-sheet", response_model=ContactSheetSplitResponse)
async def split_contact_sheet_endpoint(
    asset_id: str,
    user: User = Depends(get_current_user),
) -> ContactSheetSplitResponse:
    try:
        assets = await split_saved_contact_sheet_asset(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unexpected split failure: {type(exc).__name__}: {exc}",
        ) from exc
    return ContactSheetSplitResponse(asset_ids=[asset.id for asset in assets], count=len(assets))


@router.get("/threads", response_model=list[CreativeThread])
def threads(workspace_id: str | None = None, user: User = Depends(get_current_user)) -> list[CreativeThread]:
    return list_threads(workspace_id)


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread_endpoint(thread_id: str, user: User = Depends(get_current_user)) -> None:
    from app.incept import thread_store as ts
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


# ── Workflow endpoints ────────────────────────────────────────────────────────

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
    if len(request.output_sizes) > settings.max_output_sizes:
        raise HTTPException(
            status_code=400,
            detail=f"output_sizes cannot exceed {settings.max_output_sizes}",
        )
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
