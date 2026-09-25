"""Auditable batch admission, provider checkpoints, and usage ledger APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai_video.dependencies import get_db
from app.ai_video.models.production_execution import (
    GenerationBatch,
    ProviderExecutionCheckpoint,
    UsageLedgerEntry,
)
from app.ai_video.models.task import GenerationTask, GenerationTaskStatus
from app.ai_video.api.v1.routes.film.common import TaskCreated
from app.ai_video.schemas.common import ApiResponse, created_response, success_response
from app.ai_video.schemas.studio.production_execution import (
    GenerationBatchRead,
    ProviderCheckpointRead,
    UsageLedgerEntryRead,
    UsageSummaryRead,
    VideoBatchConfirm,
    VideoBatchCreate,
)
from app.ai_video.services.studio.production_execution import confirm_video_batch, create_video_batch, usage_summary
from app.ai_video.tasks.execute_task import enqueue_task_execution

router = APIRouter()


@router.post(
    "/projects/{project_id}/production/batches/video",
    response_model=ApiResponse[GenerationBatchRead],
    status_code=status.HTTP_201_CREATED,
    summary="Preflight and atomically enqueue a video generation batch",
)
async def create_batch(
    project_id: str,
    body: VideoBatchCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[GenerationBatchRead]:
    batch = await create_video_batch(db, project_id=project_id, body=body)
    task_ids = [item.task_id for item in batch.items if item.status == "queued" and item.task_id]
    await db.commit()
    for task_id in task_ids:
        enqueue_task_execution(task_id)
    return created_response(GenerationBatchRead.model_validate(batch))


@router.post(
    "/projects/{project_id}/production/batches/{batch_id}/confirm",
    response_model=ApiResponse[GenerationBatchRead],
    summary="Confirm the exact quote produced by an existing video batch preflight",
)
async def confirm_batch(
    project_id: str,
    batch_id: str,
    body: VideoBatchConfirm,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[GenerationBatchRead]:
    batch, task_ids = await confirm_video_batch(
        db,
        project_id=project_id,
        batch_id=batch_id,
        body=body,
    )
    await db.commit()
    for task_id in task_ids:
        enqueue_task_execution(task_id)
    return success_response(GenerationBatchRead.model_validate(batch))


@router.get(
    "/projects/{project_id}/production/batches",
    response_model=ApiResponse[list[GenerationBatchRead]],
    summary="List auditable generation batches",
)
async def list_batches(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[GenerationBatchRead]]:
    stmt = (
        select(GenerationBatch)
        .options(selectinload(GenerationBatch.items))
        .where(GenerationBatch.project_id == project_id)
        .order_by(GenerationBatch.created_at.desc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return success_response([GenerationBatchRead.model_validate(row) for row in rows])


@router.get(
    "/tasks/{task_id}/execution-checkpoint",
    response_model=ApiResponse[ProviderCheckpointRead | None],
    summary="Inspect a generation task provider checkpoint",
)
async def get_checkpoint(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProviderCheckpointRead | None]:
    row = await db.get(ProviderExecutionCheckpoint, task_id)
    return success_response(ProviderCheckpointRead.model_validate(row) if row else None)


@router.post(
    "/tasks/{task_id}/retry-download",
    response_model=ApiResponse[TaskCreated],
    summary="Retry only the download/persistence stage after provider completion",
)
async def retry_download(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    task = await db.get(GenerationTask, task_id)
    checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
    provider_result = checkpoint.checkpoint.get("provider_result") if checkpoint else None
    if task is None or checkpoint is None:
        raise HTTPException(status_code=404, detail="Generation task checkpoint not found")
    if checkpoint.state not in {"provider_completed", "download_failed"} or not isinstance(provider_result, dict):
        raise HTTPException(status_code=409, detail="Task has no completed provider result available for download retry")
    task.status = GenerationTaskStatus.pending
    task.progress = 50
    task.error = ""
    checkpoint.last_error_code = None
    checkpoint.last_error_message = ""
    await db.commit()
    enqueue_task_execution(task_id)
    return success_response(TaskCreated(task_id=task_id))


@router.get(
    "/projects/{project_id}/production/usage",
    response_model=ApiResponse[list[UsageLedgerEntryRead]],
    summary="List the immutable usage ledger",
)
async def list_usage(
    project_id: str,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[UsageLedgerEntryRead]]:
    stmt = (
        select(UsageLedgerEntry)
        .where(UsageLedgerEntry.project_id == project_id)
        .order_by(UsageLedgerEntry.created_at.desc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return success_response([UsageLedgerEntryRead.model_validate(row) for row in rows])


@router.get(
    "/projects/{project_id}/production/usage/summary",
    response_model=ApiResponse[UsageSummaryRead],
    summary="Summarize configured and settled usage by currency",
)
async def get_usage_summary(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UsageSummaryRead]:
    return success_response(UsageSummaryRead.model_validate(await usage_summary(db, project_id=project_id)))
