from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.dependencies import get_db
from app.ai_video.schemas.studio.shots import ShotVideoPromptPackRead
from app.ai_video.schemas.studio.production_execution import VideoBatchItemRequest
from app.ai_video.services.film.generated_video import preview_prompt_and_images
from app.ai_video.services.studio.production_execution import create_video_task_record, quote_video_item
from app.ai_video.tasks.execute_task import enqueue_task_execution
from app.ai_video.schemas.common import ApiResponse, created_response, success_response

from .common import TaskCreated
from .video_request import ConfirmedVideoGenerationTaskRequest, VideoGenerationQuoteRead, VideoGenerationTaskRequest

router = APIRouter()


class VideoPromptPreviewResponse(BaseModel):
    prompt: str = Field(..., description="最终用于视频生成的提示词")
    images: list[str] = Field(default_factory=list, description="关联参考图 file_id 列表")
    pack: ShotVideoPromptPackRead | None = Field(None, description="视频提示词预览上下文包")



@router.post(
    "/tasks/video/preview-prompt",
    response_model=ApiResponse[VideoPromptPreviewResponse],
    status_code=200,
    summary="视频提示词预览",
)
async def preview_video_generation_prompt(
    body: VideoGenerationTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VideoPromptPreviewResponse]:
    """预览视频生成的提示词与自动关联参考图。"""
    prompt, images, pack = await preview_prompt_and_images(
        db,
        shot_id=body.shot_id,
        reference_mode=body.reference_mode,
        prompt=body.prompt,
        images=body.images,
    )
    return success_response(VideoPromptPreviewResponse(prompt=prompt, images=images, pack=pack))


@router.post(
    "/tasks/video/preflight",
    response_model=ApiResponse[VideoGenerationQuoteRead],
    status_code=200,
    summary="视频生成价格预检",
)
async def preflight_video_generation_task(
    body: VideoGenerationTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VideoGenerationQuoteRead]:
    quote = await quote_video_item(
        db,
        item=VideoBatchItemRequest.model_validate(body.model_dump()),
    )
    return success_response(VideoGenerationQuoteRead.model_validate(quote))


@router.post(
    "/tasks/video",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="视频生成（任务版）",
)
async def create_video_generation_task(
    body: ConfirmedVideoGenerationTaskRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    """创建视频生成任务并后台执行，结果通过 /tasks/{task_id}/result 获取。"""

    item = VideoBatchItemRequest.model_validate(
        body.model_dump(exclude={"quote_fingerprint", "confirmed_by"})
    )
    current_quote = await quote_video_item(db, item=item)
    if current_quote["quote_fingerprint"] != body.quote_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "quote_changed",
                "message": "Price or generation inputs changed; run preflight again",
            },
        )

    task_id, reused = await create_video_task_record(
        db,
        item=item,
        idempotency_key=idempotency_key,
        quote_fingerprint=body.quote_fingerprint,
        confirmed_by=body.confirmed_by,
    )

    # 确保任务记录已提交，避免后台 runner 新 session 查询不到任务行而无法更新状态。
    await db.commit()
    if not reused:
        enqueue_task_execution(task_id)
    return created_response(TaskCreated(task_id=task_id))
