from __future__ import annotations

import asyncio
import json
import threading
import shutil
import uuid
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.services.auth import require_internal_key
from app.video_studio import store, pi_http
from app.video_studio.pi_runs import RunJournal, control_target, answer as answer_pi_question
from app.video_studio.pi_capabilities import validate_thinking
from app.video_studio.pi_agent import select_model
from app.video_studio.pi_agent import run_agent
from app.video_studio.agent_turns import AgentBusy, prepare_turn, cancel_turn, agent_error_message
from app.video_studio.workspace_documents import document_lock
from app.video_studio.workspace_uploads import write_stream
from app.video_studio.render import export_project, probe_asset
from app.video_studio.jobs import (
    cancel_export_job,
    create_export_job,
    ensure_export_job_running,
)
from app.video_studio.media_jobs import (
    cancel_media_job,
    create_media_job,
    ensure_media_job_running,
)
from app.video_studio.director import generate_director_plan
from app.video_studio.models import (
    AgentConversation,
    AgentRequest,
    AssetEntry,
    AssetMutation,
    AssetRename,
    CanvasCreate,
    CanvasDocument,
    CanvasSummary,
    CanvasUpdate,
    ConversationRename,
    ExportRequest,
    ExportResponse,
    ExportJob,
    MediaJob,
    MediaJobCreate,
    DirectorPlanRequest,
    DirectorPlanResponse,
    ProductionState,
    ScriptCommit,
    TimelineCommit,
    DeliveryCreate,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
    VideoStudioSettings,
    ProjectDocument,
    CatalogImport,
    CatalogSnapshot,
)


router = APIRouter(
    prefix="/video-studio",
    tags=["video-studio"],
    dependencies=[Depends(require_internal_key)],
)


def current_user(x_user_email: str = Header(default="")) -> str:
    return x_user_email.strip().lower() or "local@linglonglab.internal"


def _translate_file_error(error: Exception) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=404, detail="Project or asset not found")
    if isinstance(error, FileExistsError):
        return HTTPException(status_code=409, detail="An item already exists at that path")
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=500, detail="Video Studio storage operation failed")


@router.get("/projects", response_model=list[ProjectSummary])
def projects(email: str = Depends(current_user)) -> list[ProjectSummary]:
    return store.list_projects(email)


@router.post("/projects", response_model=ProjectDetail, status_code=201)
def create_project(body: ProjectCreate, email: str = Depends(current_user)) -> ProjectDetail:
    return store.create_project(email, body)


@router.post("/projects/import", response_model=ProjectDetail, status_code=201)
async def import_project(
    file: UploadFile = File(...),
    email: str = Depends(current_user),
) -> ProjectDetail:
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Project import requires a .zip archive")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            total = 0
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > 500 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Project archive exceeds 500 MB")
                temporary.write(chunk)
        return store.import_project_archive(email, temporary_path)
    except HTTPException:
        raise
    except (ValueError, zipfile.BadZipFile) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await file.close()
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def project(project_id: str, email: str = Depends(current_user)) -> ProjectDetail:
    try:
        return store.get_project(email, project_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/projects/{project_id}/archive")
def download_project_archive(project_id: str, email: str = Depends(current_user)):
    try:
        project = store.get_project(email, project_id)
        temporary = Path(tempfile.mkdtemp(prefix="linglong-video-archive-")) / f"{project_id}.zip"
        store.export_project_archive(email, project_id, temporary)
        safe_name = "".join(character if character.isalnum() or character in "-_." else "-" for character in project.name)
        return FileResponse(
            temporary,
            media_type="application/zip",
            filename=f"{safe_name or 'video-project'}.zip",
            background=BackgroundTask(lambda: shutil.rmtree(temporary.parent, ignore_errors=True)),
        )
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.patch("/projects/{project_id}", response_model=ProjectDetail)
def update_project(
    project_id: str,
    body: ProjectUpdate,
    email: str = Depends(current_user),
) -> ProjectDetail:
    try:
        return store.update_project(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, email: str = Depends(current_user)) -> None:
    try:
        store.delete_project(email, project_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.put("/projects/{project_id}/canvas", response_model=CanvasDocument)
def save_canvas(
    project_id: str,
    body: CanvasDocument,
    email: str = Depends(current_user),
) -> CanvasDocument:
    try:
        return store.save_canvas(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/projects/{project_id}/canvases", response_model=list[CanvasSummary])
def project_canvases(project_id: str, email: str = Depends(current_user)) -> list[CanvasSummary]:
    try:
        return store.list_canvases(email, project_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/canvases", response_model=ProjectDetail, status_code=201)
def create_project_canvas(
    project_id: str,
    body: CanvasCreate,
    email: str = Depends(current_user),
) -> ProjectDetail:
    try:
        return store.create_canvas(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/projects/{project_id}/canvases/{canvas_id}", response_model=CanvasDocument)
def project_canvas(
    project_id: str,
    canvas_id: str,
    email: str = Depends(current_user),
) -> CanvasDocument:
    try:
        return store.get_project_canvas(email, project_id, canvas_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.put("/projects/{project_id}/canvases/{canvas_id}", response_model=CanvasDocument)
def save_project_canvas(
    project_id: str,
    canvas_id: str,
    body: CanvasDocument,
    email: str = Depends(current_user),
) -> CanvasDocument:
    try:
        return store.save_project_canvas(email, project_id, canvas_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.patch("/projects/{project_id}/canvases/{canvas_id}", response_model=list[CanvasSummary])
def rename_project_canvas(
    project_id: str,
    canvas_id: str,
    body: CanvasUpdate,
    email: str = Depends(current_user),
) -> list[CanvasSummary]:
    try:
        return store.update_canvas(email, project_id, canvas_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/canvases/{canvas_id}/activate", response_model=ProjectDetail)
def activate_project_canvas(
    project_id: str,
    canvas_id: str,
    email: str = Depends(current_user),
) -> ProjectDetail:
    try:
        return store.activate_canvas(email, project_id, canvas_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.delete("/projects/{project_id}/canvases/{canvas_id}", response_model=ProjectDetail)
def delete_project_canvas(
    project_id: str,
    canvas_id: str,
    email: str = Depends(current_user),
) -> ProjectDetail:
    try:
        return store.delete_canvas(email, project_id, canvas_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/projects/{project_id}/assets", response_model=list[AssetEntry])
def list_assets(
    project_id: str,
    path: str = Query(default="", max_length=1_024),
    email: str = Depends(current_user),
) -> list[AssetEntry]:
    try:
        root = store.assets_root(email, project_id)
        target = store.safe_asset_path(root, path, allow_root=True)
        if not target.is_dir():
            raise FileNotFoundError(path)
        entries: list[AssetEntry] = []
        for entry in target.iterdir():
            stat = entry.stat()
            entries.append(
                AssetEntry(
                    path=entry.relative_to(root).as_posix(),
                    name=entry.name,
                    kind="directory" if entry.is_dir() else "file",
                    size=0 if entry.is_dir() else stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                    mime_type=None if entry.is_dir() else store.asset_mime_type(entry),
                )
            )
        return sorted(entries, key=lambda item: (item.kind != "directory", item.name.lower()))
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/assets/upload", response_model=AssetEntry)
async def upload_asset(
    project_id: str,
    file: UploadFile = File(...),
    path: str = Query(default="", max_length=1_024),
    email: str = Depends(current_user),
) -> AssetEntry:
    try:
        root = store.assets_root(email, project_id)
        filename = Path(file.filename or "upload.bin").name
        relative = "/".join(part for part in [path.strip("/"), filename] if part)
        target = store.safe_asset_path(root, relative)
        async def chunks():
            while chunk := await file.read(1024 * 1024):
                yield chunk
        await write_stream(target, chunks())
        return AssetEntry(
            path=target.relative_to(root).as_posix(),
            name=target.name,
            kind="file",
            size=target.stat().st_size,
            modified_at=datetime.now(timezone.utc),
            mime_type=file.content_type or store.asset_mime_type(target),
        )
    except OverflowError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except HTTPException:
        raise
    except (FileNotFoundError, FileExistsError, ValueError) as error:
        raise _translate_file_error(error) from error
    finally:
        await file.close()


@router.get("/projects/{project_id}/assets/file")
def read_asset(
    project_id: str,
    path: str = Query(min_length=1, max_length=1_024),
    download: bool = False,
    email: str = Depends(current_user),
):
    try:
        root = store.assets_root(email, project_id)
        target = store.safe_asset_path(root, path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return FileResponse(
            target,
            media_type=store.asset_mime_type(target),
            filename=target.name if download else None,
        )
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/assets/directory", status_code=201)
def create_asset_directory(
    project_id: str,
    body: AssetMutation,
    email: str = Depends(current_user),
) -> dict[str, str]:
    try:
        root = store.assets_root(email, project_id)
        target = store.safe_asset_path(root, body.path)
        target.mkdir(parents=True, exist_ok=False)
        return {"path": target.relative_to(root).as_posix()}
    except (FileNotFoundError, FileExistsError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/assets/rename")
def rename_asset(
    project_id: str,
    body: AssetRename,
    email: str = Depends(current_user),
) -> dict[str, str]:
    try:
        root = store.assets_root(email, project_id)
        source = store.safe_asset_path(root, body.path)
        target = store.safe_asset_path(root, body.target)
        if not source.exists():
            raise FileNotFoundError(body.path)
        if target.exists():
            raise FileExistsError(body.target)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        return {"path": target.relative_to(root).as_posix()}
    except (FileNotFoundError, FileExistsError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.delete("/projects/{project_id}/assets", status_code=204)
def delete_asset(
    project_id: str,
    path: str = Query(min_length=1, max_length=1_024),
    email: str = Depends(current_user),
) -> None:
    try:
        root = store.assets_root(email, project_id)
        target = store.safe_asset_path(root, path)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()
        else:
            raise FileNotFoundError(path)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/settings", response_model=VideoStudioSettings)
def settings(email: str = Depends(current_user)) -> VideoStudioSettings:
    return store.get_settings(email)


@router.put("/settings", response_model=VideoStudioSettings)
def save_settings(
    body: VideoStudioSettings,
    email: str = Depends(current_user),
) -> VideoStudioSettings:
    return store.save_settings(email, body)


@router.get("/projects/{project_id}/document", response_model=ProjectDocument)
def project_document(project_id: str, email: str = Depends(current_user)) -> ProjectDocument:
    try:
        return store.get_document(email, project_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.put("/projects/{project_id}/document", response_model=ProjectDocument)
def save_project_document(
    project_id: str,
    body: ProjectDocument,
    email: str = Depends(current_user),
) -> ProjectDocument:
    try:
        return store.save_document(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/catalog", response_model=CatalogSnapshot)
def catalog(email: str = Depends(current_user)) -> CatalogSnapshot:
    return store.get_catalog(email)


@router.put("/catalog", response_model=CatalogSnapshot)
def save_catalog(body: CatalogImport, email: str = Depends(current_user)) -> CatalogSnapshot:
    return store.save_catalog(email, body)


@router.get(
    "/projects/{project_id}/conversations",
    response_model=list[AgentConversation],
)
def conversations(
    project_id: str,
    email: str = Depends(current_user),
) -> list[AgentConversation]:
    try:
        return store.list_conversations(email, project_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.patch(
    "/projects/{project_id}/conversations/{conversation_id}",
    response_model=AgentConversation,
)
def rename_conversation(
    project_id: str,
    conversation_id: str,
    body: ConversationRename,
    email: str = Depends(current_user),
) -> AgentConversation:
    try:
        with document_lock(store._conversation_path(email, project_id, conversation_id)):
            conversation = store.get_conversation(email, project_id, conversation_id)
            if conversation.run_status == "running":
                raise HTTPException(status_code=409, detail="会话仍在处理中，请先停止或等待完成再修改。")
            conversation.name = body.name.strip()
            if not conversation.name:
                raise ValueError("对话名称不能为空")
            return store.save_conversation(email, project_id, conversation)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.delete(
    "/projects/{project_id}/conversations/{conversation_id}",
    status_code=204,
)
def delete_conversation(
    project_id: str,
    conversation_id: str,
    email: str = Depends(current_user),
) -> None:
    try:
        with document_lock(store._conversation_path(email, project_id, conversation_id)):
            conversation = store.get_conversation(email, project_id, conversation_id)
            if conversation.run_status == "running":
                raise HTTPException(status_code=409, detail="会话仍在处理中，请先停止或等待完成再删除。")
            store.delete_conversation(email, project_id, conversation_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


class AgentCancelRequest(BaseModel):
    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")


@router.post("/projects/{project_id}/conversations/{conversation_id}/cancel", status_code=204)
def cancel_conversation_run(project_id: str, conversation_id: str, body: AgentCancelRequest,
                            email: str = Depends(current_user)) -> None:
    try:
        store.get_project(email, project_id)
        value=store.get_conversation(email,project_id,conversation_id)
        journal,child_file=control_target(email,project_id,value)
        if child_file and value.run_id==body.run_id:
            journal.abort_child(child_file)
        else: cancel_turn(email, project_id, conversation_id, body.run_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


class AgentControlRequest(AgentCancelRequest):
    action: str
    prompt: str = Field(min_length=1,max_length=20000)


@router.get('/projects/{project_id}/conversations/{conversation_id}/events')
async def conversation_events(project_id:str,conversation_id:str,request:Request,
                              run_id:str=Query(),after:int=Query(default=0,ge=0),email:str=Depends(current_user)):
    try:
        value=store.get_conversation(email,project_id,conversation_id)
        if value.run_id!=run_id: raise ValueError('Run identity changed; reload the conversation')
        journal=RunJournal(email,project_id,conversation_id,run_id)
        journal.state()
    except (ValueError,FileNotFoundError) as error: raise _translate_file_error(error) from error
    return StreamingResponse(pi_http.events(journal,request,after,replay=True),media_type='application/x-ndjson',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


def _enqueue_instruction(email,project_id,value,action,prompt):
    journal,child_file=control_target(email,project_id,value)
    return journal.enqueue(action,prompt,child_file)


@router.post('/projects/{project_id}/conversations/{conversation_id}/control')
def conversation_control(project_id:str,conversation_id:str,body:AgentControlRequest,email:str=Depends(current_user)):
    try:
        value=store.get_conversation(email,project_id,conversation_id)
        if value.run_id!=body.run_id or value.run_status!='running': raise ValueError('Run identity changed or run ended')
        command=_enqueue_instruction(email,project_id,value,body.action,body.prompt)
        return {'accepted':True,'controlId':command['controlId']}
    except (ValueError,FileNotFoundError) as error: raise _translate_file_error(error) from error


@router.post('/projects/{project_id}/conversations/{conversation_id}/answer')
def conversation_answer(project_id:str,conversation_id:str,body:dict,email:str=Depends(current_user)):
    try:
        value=store.get_conversation(email,project_id,conversation_id)
        return answer_pi_question(email,project_id,body.get('callId'),{**body,'sessionFile':f'agent/{value.id}.json','runId':value.run_id})
    except (ValueError,FileNotFoundError) as error: raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/agent")
async def agent(
    project_id: str,
    body: AgentRequest,
    request: Request,
    email: str = Depends(current_user),
) -> StreamingResponse:
    try:
        project = store.get_project(email, project_id)
        target_canvas_id = project.active_canvas_id
        initial_canvas = store.get_project_canvas(email, project_id, target_canvas_id).model_copy(deep=True)
        if body.conversation_id:
            value=store.get_conversation(email,project_id,body.conversation_id)
            if value.run_status=='running':
                try: command=_enqueue_instruction(email,project_id,value,body.streaming_behavior,body.prompt)
                except FileNotFoundError as error: raise AgentBusy('该会话仍在处理中，请先停止或等待完成。') from error
                async def accepted():
                    yield json.dumps({'type':'accepted','controlId':command['controlId']})+'\n'
                    yield json.dumps({'type':'done'})+'\n'
                return StreamingResponse(accepted(),media_type='application/x-ndjson')
        validate_thinking(select_model(None,None),body.thinking_level)
        prepared = await asyncio.to_thread(prepare_turn, email=email, project_id=project_id,
            prompt=body.prompt, conversation_id=body.conversation_id, asset_paths=body.asset_paths,
            research_question_id=body.research_question_id)
    except AgentBusy as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ValueError, FileNotFoundError) as error:
        raise _translate_file_error(error) from error
    journal=RunJournal(email,project_id,prepared.id,prepared.run_id)
    journal.create()
    journal.emit({'type':'session','conversation_id':prepared.id,'run_id':prepared.run_id,'file':f'agent/{prepared.id}.json','runId':prepared.run_id})
    journal.emit({'type':'userMessage','id':prepared.messages[-1].id,'content':prepared.messages[-1].content})
    loop=asyncio.get_running_loop()
    async def worker():
        return await asyncio.to_thread(run_agent,email=email,project_id=project_id,prompt=prepared.messages[-1].content,
            conversation_id=prepared.id,agent_id=body.agent_id,asset_paths=body.asset_paths,
            prepared_conversation=prepared,canvas_document=initial_canvas,canvas_id=target_canvas_id,
            progress=journal.emit,thinking_level=body.thinking_level,journal=journal,
            invoke_async=lambda coro:asyncio.run_coroutine_threadsafe(coro,loop).result(timeout=120))
    def finalized(result):
        conversation,canvas,message=result
        if canvas!=initial_canvas:
            yield {'type':'canvas','canvas_id':target_canvas_id,'canvas':canvas.model_dump(mode='json')}
        yield {'type':'message','conversation_id':conversation.id,'message':message}
    pi_http.launch(journal,worker,finalized)
    return StreamingResponse(pi_http.events(journal,request),media_type='application/x-ndjson',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})



@router.get("/projects/{project_id}/ffmpeg/probe")
async def probe(
    project_id: str,
    path: str = Query(min_length=1, max_length=1_024),
    email: str = Depends(current_user),
) -> dict:
    try:
        return await asyncio.to_thread(probe_asset, email, project_id, path)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/projects/{project_id}/exports",
    response_model=ExportResponse,
    status_code=201,
)
async def create_export(
    project_id: str,
    body: ExportRequest,
    email: str = Depends(current_user),
) -> ExportResponse:
    try:
        return await asyncio.to_thread(export_project, email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/projects/{project_id}/export-jobs", response_model=list[ExportJob])
async def export_jobs(project_id: str, email: str = Depends(current_user)) -> list[ExportJob]:
    try:
        jobs = store.list_export_jobs(email, project_id)
        for job in jobs:
            if job.status in {"queued", "running"}:
                ensure_export_job_running(email, project_id, job.id)
        return jobs
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/export-jobs", response_model=ExportJob, status_code=202)
async def submit_export_job(
    project_id: str,
    body: ExportRequest,
    email: str = Depends(current_user),
) -> ExportJob:
    try:
        return create_export_job(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/projects/{project_id}/export-jobs/{job_id}", response_model=ExportJob)
async def export_job(project_id: str, job_id: str, email: str = Depends(current_user)) -> ExportJob:
    try:
        return ensure_export_job_running(email, project_id, job_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/export-jobs/{job_id}/cancel", response_model=ExportJob)
def cancel_export(
    project_id: str,
    job_id: str,
    email: str = Depends(current_user),
) -> ExportJob:
    try:
        return cancel_export_job(email, project_id, job_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/projects/{project_id}/media-jobs", response_model=list[MediaJob])
async def media_jobs(project_id: str, email: str = Depends(current_user)) -> list[MediaJob]:
    try:
        jobs = store.list_media_jobs(email, project_id)
        for job in jobs:
            if job.status in {"queued", "running"}:
                ensure_media_job_running(email, project_id, job.id)
        return jobs
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/media-jobs", response_model=MediaJob, status_code=202)
async def submit_media_job(
    project_id: str,
    body: MediaJobCreate,
    email: str = Depends(current_user),
) -> MediaJob:
    try:
        return create_media_job(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.get("/projects/{project_id}/media-jobs/{job_id}", response_model=MediaJob)
async def media_job(
    project_id: str,
    job_id: str,
    email: str = Depends(current_user),
) -> MediaJob:
    try:
        return ensure_media_job_running(email, project_id, job_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/media-jobs/{job_id}/cancel", response_model=MediaJob)
async def cancel_media(
    project_id: str,
    job_id: str,
    email: str = Depends(current_user),
) -> MediaJob:
    try:
        return cancel_media_job(email, project_id, job_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/director/plan", response_model=DirectorPlanResponse)
async def plan_director_scene(
    project_id: str,
    body: DirectorPlanRequest,
    email: str = Depends(current_user),
) -> DirectorPlanResponse:
    try:
        store.get_project(email, project_id)
        catalog = store.get_catalog(email)
        enabled = {item.id for item in catalog.extensions if item.enabled}
        if "node-director3d" not in enabled:
            raise ValueError("3D director extension is disabled")
        return await asyncio.to_thread(generate_director_plan, body.prompt)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        raise _translate_file_error(error) from error


@router.get("/projects/{project_id}/production", response_model=ProductionState)
def production_state(project_id: str, email: str = Depends(current_user)) -> ProductionState:
    try:
        return store.get_production_state(email, project_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.put("/projects/{project_id}/production", response_model=ProductionState)
def save_production_state(
    project_id: str,
    body: ProductionState,
    email: str = Depends(current_user),
) -> ProductionState:
    try:
        return store.save_production_state(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/production/script/lock", response_model=ProductionState)
def lock_production_script(
    project_id: str,
    body: ScriptCommit,
    email: str = Depends(current_user),
) -> ProductionState:
    try:
        return store.commit_script(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/production/script/unlock", response_model=ProductionState)
def unlock_production_script(
    project_id: str,
    email: str = Depends(current_user),
) -> ProductionState:
    try:
        return store.unlock_script(email, project_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/production/timeline/commit", response_model=ProductionState)
def commit_production_timeline(
    project_id: str,
    body: TimelineCommit,
    email: str = Depends(current_user),
) -> ProductionState:
    try:
        return store.commit_timeline(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/production/qa", response_model=ProductionState)
def run_production_qa(project_id: str, email: str = Depends(current_user)) -> ProductionState:
    try:
        return store.run_production_qa(email, project_id)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error


@router.post("/projects/{project_id}/production/deliveries", response_model=ProductionState)
def create_delivery_manifest(
    project_id: str,
    body: DeliveryCreate,
    email: str = Depends(current_user),
) -> ProductionState:
    try:
        return store.record_delivery(email, project_id, body)
    except (FileNotFoundError, ValueError) as error:
        raise _translate_file_error(error) from error
