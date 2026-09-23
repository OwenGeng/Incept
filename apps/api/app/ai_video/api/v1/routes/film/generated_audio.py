"""Task API for standalone narration and background-music generation."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.ai_video.dependencies import get_db
from app.ai_video.schemas.common import ApiResponse, created_response
from app.ai_video.services.film.generated_audio import build_audio_run_args
from app.ai_video.tasks.execute_task import enqueue_task_execution

from .common import TaskCreated, _CreateOnlyTask

router = APIRouter()


class AudioGenerationTaskRequest(BaseModel):
    """A narration script or a music brief submitted as a durable task."""

    generation_kind: Literal["speech", "music"] = Field(..., description="Whether the selected model produces speech or music.")
    prompt: str = Field(..., min_length=1, max_length=8000, description="Narration script or music prompt.")
    model_id: str | None = Field(None, description="Optional models.id; otherwise the matching default is used.")
    voice: str | None = Field(None, description="Optional speech voice.")
    response_format: Literal["mp3", "wav", "opus", "aac", "flac", "pcm"] = "mp3"
    speed: float | None = Field(None, ge=0.25, le=4.0)
    provider_params: dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/tasks/audio",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="Speech or background-music generation task",
)
async def create_audio_generation_task(
    body: AudioGenerationTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    """Queue audio work; retrieve result/file_id from the regular task-status endpoint."""
    store = SqlAlchemyTaskStore(db)
    task_manager = TaskManager(store=store, strategies={})
    run_args = await build_audio_run_args(
        db,
        generation_kind=body.generation_kind,
        prompt=body.prompt,
        model_id=body.model_id,
        voice=body.voice,
        response_format=body.response_format,
        speed=body.speed,
        provider_params=body.provider_params,
    )
    task_record = await task_manager.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind="audio_generation",
        run_args=run_args,
    )
    await db.commit()
    enqueue_task_execution(task_record.id)
    return created_response(TaskCreated(task_id=task_record.id))
