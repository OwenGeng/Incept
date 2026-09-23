"""Background-task orchestration for speech and music generation."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.core.db import async_session_maker
from app.ai_video.core.task_manager import SqlAlchemyTaskStore
from app.ai_video.core.task_manager.types import TaskStatus
from app.ai_video.core.contracts.audio_generation import AudioGenerationInput, AudioGenerationResult
from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.tasks import AudioGenerationTask
from app.ai_video.models.llm import Model, ModelCategoryKey, ModelSettings
from app.ai_video.services.llm.provider_resolver import resolve_provider_config_by_model
from app.ai_video.services.worker.async_task_support import cancel_if_requested_async
from app.ai_video.services.worker.task_logging import log_task_event, log_task_failure
from app.ai_video.utils.files import create_file_from_url_or_b64


async def resolve_audio_model(db: AsyncSession, *, generation_kind: str, model_id: str | None) -> Model:
    """Resolve an explicitly selected speech/music model or its configured default."""
    expected_category = ModelCategoryKey.speech if generation_kind == "speech" else ModelCategoryKey.music
    settings_row = await db.get(ModelSettings, 1)
    default_id = (
        settings_row.default_speech_model_id if generation_kind == "speech" else settings_row.default_music_model_id
    ) if settings_row else None
    effective_model_id = (model_id or "").strip() or default_id
    if not effective_model_id:
        raise HTTPException(status_code=503, detail=f"No default {generation_kind} model is configured")
    model = await db.get(Model, effective_model_id)
    if model is None:
        raise HTTPException(status_code=503, detail=f"Configured {generation_kind} model not found: {effective_model_id}")
    if model.category != expected_category:
        raise HTTPException(
            status_code=400,
            detail=f"Model {model.id} has category={model.category}; expected {expected_category}",
        )
    return model


async def _provider_config(db: AsyncSession, model: Model) -> ProviderConfig:
    resolved = await resolve_provider_config_by_model(db, model=model)
    return ProviderConfig(
        provider=resolved.provider_key,  # type: ignore[arg-type]
        api_key=resolved.api_key,
        api_secret=resolved.api_secret,
        base_url=resolved.base_url,
        project_id=resolved.project_id,
        location=resolved.location,
    )


async def build_audio_run_args(
    db: AsyncSession,
    *,
    generation_kind: str,
    prompt: str,
    model_id: str | None,
    voice: str | None,
    response_format: str,
    speed: float | None,
    provider_params: dict,
) -> dict:
    """Build safe serialized worker arguments without persisting credentials."""
    model = await resolve_audio_model(db, generation_kind=generation_kind, model_id=model_id)
    cfg = await _provider_config(db, model)
    return {
        "generation_kind": generation_kind,
        "model_id": model.id,
        "provider_id": model.provider_id,
        "provider": cfg.provider,
        "input": {
            "prompt": prompt,
            "model": model.name,
            "voice": voice,
            "response_format": response_format,
            "speed": speed,
            "provider_params": dict(provider_params),
        },
    }


async def run_audio_generation_task(task_id: str, run_args: dict) -> None:
    """Execute one audio task, retain the output in storage, and expose file_id in task result."""
    async with async_session_maker() as session:
        try:
            store = SqlAlchemyTaskStore(session)
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 10)
            await session.commit()
            log_task_event("audio_generation", task_id, "running")
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("audio_generation", task_id, "cancelled", stage="before_execute")
                return

            model_id = str(run_args.get("model_id") or "").strip()
            model = await session.get(Model, model_id)
            if model is None:
                raise RuntimeError(f"Configured audio model is unavailable: {model_id}")
            cfg = await _provider_config(session, model)
            if cfg.provider != str(run_args.get("provider") or ""):
                raise RuntimeError("Provider changed after task creation; create a new generation task")
            task = AudioGenerationTask(
                provider_config=cfg,
                input_=AudioGenerationInput.model_validate(dict(run_args.get("input") or {})),
            )
            await task.run()
            result = await task.get_result()
            if result is None:
                detail = await task.status()
                raise RuntimeError(str(detail.get("error") or "Audio generation returned no result"))
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("audio_generation", task_id, "cancelled", stage="after_execute")
                return

            url = result.url.strip()
            file_obj = await create_file_from_url_or_b64(
                session,
                url=None if url.startswith("data:") else url,
                b64_data=url if url.startswith("data:") else None,
                name=f"{run_args.get('generation_kind') or 'audio'}-{task_id}",
                prefix=f"generated-audio/{run_args.get('generation_kind') or 'audio'}",
                httpx_timeout=600.0,
            )
            result_payload = result.model_dump()
            result_payload["file_id"] = file_obj.id
            await store.set_result(task_id, result_payload)
            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await session.commit()
            log_task_event("audio_generation", task_id, "succeeded")
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            async with async_session_maker() as failure_session:
                store = SqlAlchemyTaskStore(failure_session)
                await store.set_error(task_id, str(exc))
                await store.set_status(task_id, TaskStatus.failed)
                await failure_session.commit()
            log_task_failure("audio_generation", task_id, str(exc))
