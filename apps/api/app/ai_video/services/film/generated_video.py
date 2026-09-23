from __future__ import annotations

import base64
import mimetypes

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.core import storage
from app.ai_video.core.db import async_session_maker
from app.ai_video.core.task_manager import SqlAlchemyTaskStore
from app.ai_video.core.task_manager.types import TaskStatus
from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.contracts.video_generation import VideoGenerationInput, VideoGenerationResult
from app.ai_video.core.tasks import VideoGenerationTask
from app.ai_video.models.llm import Model, ModelCategoryKey, ModelSettings
from app.ai_video.models.task_links import GenerationTaskLink
from app.ai_video.models.studio import FileItem, Shot, ShotDetail, ShotFrameType
from app.ai_video.models.types import FileUsageKind
from app.ai_video.services.common import entity_not_found
from app.ai_video.services.llm.provider_resolver import resolve_provider_config_by_model
from app.ai_video.services.studio.file_usages import sync_usage_from_shot_context
from app.ai_video.services.studio.generation.video import (
    REQUIRED_FRAMES_BY_MODE,
    build_video_base_draft,
    build_video_context,
    build_video_submission_payload,
    validate_images_count,
)
from app.ai_video.services.studio.shot_status import recompute_shot_status
from app.ai_video.services.worker.async_task_support import cancel_if_requested_async
from app.ai_video.services.worker.task_logging import log_task_event, log_task_failure
from app.ai_video.utils.files import create_file_from_url_or_b64

async def validate_shot_and_duration(db: AsyncSession, shot_id: str) -> ShotDetail:
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Shot"))
    shot_detail = await db.get(ShotDetail, shot_id)
    if shot_detail is None:
        raise HTTPException(status_code=404, detail=entity_not_found("ShotDetail"))
    if shot_detail.duration is None or shot_detail.duration <= 0:
        raise HTTPException(status_code=400, detail="Shot duration is not configured; please set shot duration first")
    return shot_detail


async def file_id_to_data_url(db: AsyncSession, *, file_id: str) -> str:
    file_obj = await db.get(FileItem, file_id)
    if file_obj is None or not file_obj.storage_key:
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")
    try:
        content = await storage.download_file(key=file_obj.storage_key)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}") from None
    if not content:
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")

    content_type: str | None = None
    try:
        info = await storage.get_file_info(key=file_obj.storage_key)
        content_type = (info.content_type or "").strip().lower() or None
    except Exception:  # noqa: BLE001
        content_type = None
    if not content_type:
        guessed_type, _ = mimetypes.guess_type(file_obj.storage_key)
        content_type = (guessed_type or "").strip().lower() or None
    if not content_type or not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")

    image_format = content_type.split("/", 1)[1].split(";", 1)[0].strip().lower() or "png"
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/{image_format};base64,{encoded}"


async def file_id_to_gcs_reference(db: AsyncSession, *, file_id: str) -> dict[str, str]:
    """Resolve a Studio image to the verified GCS URI Gemini Omni requires."""
    file_obj = await db.get(FileItem, file_id)
    if file_obj is None or not file_obj.storage_key:
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")
    try:
        info = await storage.get_file_info(key=file_obj.storage_key)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}") from None
    content_type = (info.content_type or "").strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")
    try:
        uri = storage.create_gcs_uri(key=file_obj.storage_key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Gemini Omni reference generation requires the production GCS asset store",
        ) from exc
    return {"uri": uri, "mime_type": content_type}


async def preview_prompt_and_images(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    prompt: str | None,
    images: list[str] | None = None,
) -> tuple[str, list[str], dict | None]:
    await validate_shot_and_duration(db, shot_id)
    base = build_video_base_draft(shot_id=shot_id, prompt=prompt)
    context = await build_video_context(
        db,
        shot_id=shot_id,
        reference_mode=reference_mode,
        images=images,
    )
    submission = await build_video_submission_payload(db, base=base, context=context)
    if not submission.prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    prompt_preview_payload = submission.extra.get("prompt_preview")
    if isinstance(prompt_preview_payload, dict):
        pack = prompt_preview_payload.get("pack")
        return submission.prompt, submission.images, pack if isinstance(pack, dict) else None
    return submission.prompt, submission.images, None


async def resolve_video_model(db: AsyncSession, *, model_id: str | None = None) -> Model:
    """Resolve an explicitly selected video model or the configured default."""
    settings_row = await db.get(ModelSettings, 1)
    effective_model_id = (model_id or "").strip() or (settings_row.default_video_model_id if settings_row else None)
    if not effective_model_id:
        raise HTTPException(
            status_code=503,
            detail="No default video model configured; please set ModelSettings.default_video_model_id first",
        )
    model = await db.get(Model, effective_model_id)
    if model is None:
        raise HTTPException(status_code=503, detail=f"Configured video model not found: {effective_model_id}")
    if model.category != ModelCategoryKey.video:
        raise HTTPException(
            status_code=503,
            detail=f"Configured default video model is not video category: {model_id} (category={model.category})",
        )
    return model


async def resolve_default_video_model(db: AsyncSession) -> Model:
    """Backward-compatible default-model resolver used by existing callers."""
    return await resolve_video_model(db)


async def load_provider_config_by_model(db: AsyncSession, model: Model) -> ProviderConfig:
    resolved = await resolve_provider_config_by_model(db, model=model)
    return ProviderConfig(
        provider=resolved.provider_key,  # type: ignore[arg-type]
        api_key=resolved.api_key,
        api_secret=resolved.api_secret,
        base_url=resolved.base_url,
        project_id=resolved.project_id,
        location=resolved.location,
    )


def _normalize_optional_text(value: str | None) -> str | None:
    """归一化可选文本参数：空字符串视为未设置。"""
    normalized = (value or "").strip()
    return normalized or None


async def resolve_effective_video_options(
    requested_ratio: str | None,
) -> str:
    """解析视频比例：请求参数为唯一主参数。"""
    req_ratio = _normalize_optional_text(requested_ratio)
    if not req_ratio:
        raise HTTPException(status_code=400, detail="ratio is required")
    return req_ratio


async def build_run_args(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    prompt: str | None,
    images: list[str],
    ratio: str | None,
    model_id: str | None = None,
    provider_params: dict | None = None,
) -> dict:
    model = await resolve_video_model(db, model_id=model_id)
    provider_cfg = await load_provider_config_by_model(db, model)
    shot_detail = await validate_shot_and_duration(db, shot_id)
    resolved_ratio = await resolve_effective_video_options(requested_ratio=ratio)
    base = build_video_base_draft(shot_id=shot_id, prompt=prompt)
    context = await build_video_context(
        db,
        shot_id=shot_id,
        reference_mode=reference_mode,
        images=images,
    )
    submission = await build_video_submission_payload(db, base=base, context=context)
    validate_images_count(reference_mode, submission.images)

    final_prompt = submission.prompt.strip()
    if not final_prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    frame_map: dict[ShotFrameType, str | None] = {}
    # Creatify parameters are driven by the selected model's runtime JSON
    # Schema. It receives media only through explicit linglong-file markers
    # in provider_params, so do not force its inputs into OpenAI data-URL fields.
    is_gemini_omni = provider_cfg.provider == "vertex" and model.name == "gemini-omni-1.1-flash-preview"
    reference_media: list[dict[str, str]] = []
    if provider_cfg.provider != "creatify":
        required_frames = tuple(ShotFrameType(item) for item in REQUIRED_FRAMES_BY_MODE[reference_mode])
        if is_gemini_omni:
            reference_media = [await file_id_to_gcs_reference(db, file_id=file_id) for file_id in submission.images]
        else:
            frame_data_urls = [await file_id_to_data_url(db, file_id=file_id) for file_id in submission.images]
            frame_map = {ft: frame_data_urls[i] for i, ft in enumerate(required_frames)}

    run_args = {
        "shot_id": shot_id,
        "model_id": model.id,
        "provider_id": model.provider_id,
        "provider": provider_cfg.provider,
        "input": {
            "prompt": final_prompt,
            "first_frame_base64": frame_map.get(ShotFrameType.first),
            "last_frame_base64": frame_map.get(ShotFrameType.last),
            "key_frame_base64": frame_map.get(ShotFrameType.key),
            "reference_media": reference_media,
            "model": model.name,
            "ratio": resolved_ratio,
            "seconds": shot_detail.duration,
            "provider_params": dict(provider_params or {}),
        },
    }
    # Credentials are resolved from the current Provider record only by the
    # worker.  Never persist API keys in GenerationTask.payload.
    prompt_preview_payload = submission.extra.get("prompt_preview")
    if isinstance(prompt_preview_payload, dict):
        run_args["prompt_preview"] = prompt_preview_payload
    return run_args


async def persist_generated_video_to_shot(
    session: AsyncSession,
    *,
    task_id: str,
    shot_id: str,
    result: VideoGenerationResult,
    provider: str,
    api_key: str,
) -> FileItem:
    url = (result.url or "").strip()
    if not url:
        raise RuntimeError("Video generation result has no download url")

    url_headers: dict[str, str] | None = None
    if provider == "openai":
        url_headers = {"Authorization": f"Bearer {api_key}"}

    file_obj = await create_file_from_url_or_b64(
        session,
        url=None if url.startswith("data:") else url,
        b64_data=url if url.startswith("data:") else None,
        name=f"shot-{shot_id}-video",
        prefix=f"generated-videos/shots/{shot_id}",
        url_request_headers=url_headers,
        httpx_timeout=600.0,
    )

    link_stmt = (
        select(GenerationTaskLink)
        .where(
            GenerationTaskLink.task_id == task_id,
            GenerationTaskLink.resource_type == "video",
            GenerationTaskLink.relation_type == "video",
            GenerationTaskLink.relation_entity_id == shot_id,
        )
        .limit(1)
    )
    link_row = (await session.execute(link_stmt)).scalars().first()
    if link_row is not None:
        link_row.file_id = file_obj.id

    shot = await session.get(Shot, shot_id)
    if shot is not None:
        shot.generated_video_file_id = file_obj.id

    await sync_usage_from_shot_context(
        session,
        file_id=file_obj.id,
        shot_id=shot_id,
        usage_kind=FileUsageKind.generated_video,
        source_ref=f"shot:{shot_id}:generated_video",
    )

    return file_obj


async def run_video_generation_task(
    task_id: str,
    run_args: dict,
) -> None:
    async with async_session_maker() as session:
        try:
            store = SqlAlchemyTaskStore(session)
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 10)
            await session.commit()
            log_task_event("video_generation", task_id, "running")
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("video_generation", task_id, "cancelled", stage="before_execute")
                return

            provider = str(run_args.get("provider") or "")
            if provider == "creatify":
                from app.ai_video.services.integrations.creatify_tasks import advance_creatify_video_job

                result = await advance_creatify_video_job(task_id, run_args)
                # A non-terminal external task has been persisted and its next
                # poll scheduled; it must remain `running`, not be marked done.
                if result is None:
                    log_task_event("video_generation", task_id, "external_pending", provider="creatify")
                    return
            else:
                model_id = str(run_args.get("model_id") or "").strip()
                model = await session.get(Model, model_id)
                if model is None:
                    raise RuntimeError(f"Configured video model is unavailable: {model_id}")
                provider_cfg = await load_provider_config_by_model(session, model)
                if provider_cfg.provider != provider:
                    raise RuntimeError("Provider changed after task creation; cancel and create a new generation task")
                input_dict = dict(run_args.get("input") or {})

                task = VideoGenerationTask(
                    provider_config=provider_cfg,
                    input_=VideoGenerationInput.model_validate(input_dict),
                    # The documented synchronous Omni interaction can take more
                    # than a minute; allow the worker's normal 30-minute ceiling
                    # to govern it rather than failing the provider request at 120s.
                    timeout_s=600.0 if model.name == "gemini-omni-1.1-flash-preview" else 120.0,
                )
                await task.run()
                result = await task.get_result()
                if result is None:
                    status_dict = await task.status()
                    detailed_error = ""
                    if isinstance(status_dict, dict):
                        detailed_error = str(status_dict.get("error") or "")
                    msg = detailed_error or "Video generation task returned no result"
                    raise RuntimeError(msg)
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("video_generation", task_id, "cancelled", stage="after_execute")
                return

            shot_id = str(run_args.get("shot_id") or "")
            if not shot_id:
                raise RuntimeError("run_args missing shot_id for video persistence")

            file_obj = await persist_generated_video_to_shot(
                session,
                task_id=task_id,
                shot_id=shot_id,
                result=result,
                provider=provider,
                api_key=provider_cfg.api_key if provider != "creatify" else "",
            )

            result_payload = result.model_dump()
            result_payload["file_id"] = file_obj.id
            await store.set_result(task_id, result_payload)
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("video_generation", task_id, "cancelled", stage="after_persist")
                return
            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await recompute_shot_status(session, shot_id=shot_id)
            await session.commit()
            log_task_event("video_generation", task_id, "succeeded")
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            async with async_session_maker() as s2:
                store = SqlAlchemyTaskStore(s2)
                await store.set_error(task_id, str(exc))
                await store.set_status(task_id, TaskStatus.failed)
                shot_id = str(run_args.get("shot_id") or "")
                if shot_id:
                    await recompute_shot_status(s2, shot_id=shot_id)
                await s2.commit()
            log_task_failure("video_generation", task_id, str(exc))
