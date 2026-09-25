"""Persisted edit documents and deterministic render tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.dependencies import get_db
from app.ai_video.schemas.common import ApiResponse, created_response, success_response
from app.ai_video.schemas.studio.editing import (
    EditDocument,
    EditRevisionRequest,
    TimelineRenderCreated,
    TimelineRenderRequest,
)
from app.ai_video.schemas.studio.production_control import ProductionRevisionRead
from app.ai_video.services.studio.editing import (
    build_default_edit_document,
    create_edit_revision,
    create_timeline_render_task,
)
from app.ai_video.tasks.execute_task import enqueue_task_execution

router = APIRouter()


@router.get(
    "/projects/{project_id}/production/edit/default",
    response_model=ApiResponse[EditDocument],
    summary="Build an edit document from the project's explicitly selected takes",
)
async def get_default_edit(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EditDocument]:
    return success_response(await build_default_edit_document(db, project_id=project_id))


@router.post(
    "/projects/{project_id}/production/edit/revisions",
    response_model=ApiResponse[ProductionRevisionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Validate and persist an immutable edit revision",
)
async def create_edit(
    project_id: str,
    body: EditRevisionRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionRevisionRead]:
    revision = await create_edit_revision(
        db,
        project_id=project_id,
        document=body.document,
        created_by=body.created_by,
    )
    await db.commit()
    return created_response(ProductionRevisionRead.model_validate(revision))


@router.post(
    "/projects/{project_id}/production/render",
    response_model=ApiResponse[TimelineRenderCreated],
    status_code=status.HTTP_201_CREATED,
    summary="Queue a deterministic FFmpeg render of an approved edit revision",
)
async def render_edit(
    project_id: str,
    body: TimelineRenderRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TimelineRenderCreated]:
    task_id, fingerprint = await create_timeline_render_task(
        db,
        project_id=project_id,
        edit_revision_id=body.edit_revision_id,
        output_name=body.output_name,
    )
    await db.commit()
    enqueue_task_execution(task_id)
    return created_response(
        TimelineRenderCreated(
            task_id=task_id,
            edit_revision_id=body.edit_revision_id,
            manifest_fingerprint=fingerprint,
        )
    )
