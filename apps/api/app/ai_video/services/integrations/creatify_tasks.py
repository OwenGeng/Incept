"""Persisted, non-blocking orchestration for Creatify Asset Generator jobs."""

from __future__ import annotations

from typing import Any

from app.ai_video.config import settings
from app.ai_video.core import storage
from app.ai_video.core.contracts.image_generation import ImageGenerationResult, ImageItem
from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.contracts.video_generation import VideoGenerationResult
from app.ai_video.core.integrations.creatify import CreatifyAssetGeneratorAdapter
from app.ai_video.core.task_manager import SqlAlchemyTaskStore
from app.ai_video.core.task_manager.types import TaskStatus
from app.ai_video.models.llm import Model, ModelCategoryKey
from app.ai_video.models.task import GenerationTask
from app.ai_video.services.llm.provider_resolver import resolve_provider_config_by_model


def _schema_for_model(model: Model) -> dict[str, Any]:
    """Read the last synchronized Creatify JSON schema for one approved model."""
    params = dict(model.params or {})
    if params.get("catalog_source") != "creatify" or not bool(params.get("enabled")):
        raise RuntimeError("Creatify model is not enabled by an administrator")
    catalog = params.get("creatify_catalog")
    if not isinstance(catalog, dict) or not isinstance(catalog.get("input_params_schema"), dict):
        raise RuntimeError("Creatify model has no synchronized input schema; run catalog sync before generating")
    return catalog["input_params_schema"]


async def _replace_file_markers(value: Any) -> Any:
    """Turn explicit ``linglong-file://<id>`` markers into short-lived HTTPS URLs."""
    if isinstance(value, str) and value.startswith("linglong-file://"):
        file_id = value.removeprefix("linglong-file://").strip()
        if not file_id:
            raise RuntimeError("Empty Linglong Lab media reference")
        from app.ai_video.core.db import async_session_maker
        from app.ai_video.models.studio import FileItem

        async with async_session_maker() as session:
            file_obj = await session.get(FileItem, file_id)
            if file_obj is None or not file_obj.storage_key:
                raise RuntimeError(f"Referenced file is unavailable: {file_id}")
            return await storage.create_download_url(key=file_obj.storage_key)
    if isinstance(value, list):
        return [await _replace_file_markers(item) for item in value]
    if isinstance(value, dict):
        return {key: await _replace_file_markers(item) for key, item in value.items()}
    return value


def _validate_top_level_schema(schema: dict[str, Any], params: dict[str, Any]) -> None:
    """Perform safe preflight checks; Creatify remains the authority for full JSON Schema validation."""
    required = schema.get("required")
    if isinstance(required, list):
        missing = [str(name) for name in required if isinstance(name, str) and name not in params]
        if missing:
            raise RuntimeError(f"Creatify model requires input parameter(s): {', '.join(missing)}")
    properties = schema.get("properties")
    if schema.get("additionalProperties") is False and isinstance(properties, dict):
        unknown = sorted(set(params) - set(properties))
        if unknown:
            raise RuntimeError(f"Creatify model does not accept parameter(s): {', '.join(unknown)}")


async def _prepare_input_params(
    *,
    schema: dict[str, Any],
    prompt: str,
    provider_params: dict[str, Any],
    ratio: str | None = None,
) -> dict[str, Any]:
    """Merge explicit runtime fields with safe universal fields exposed in live schema."""
    params = dict(provider_params)
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    if prompt and "prompt" in properties and "prompt" not in params:
        params["prompt"] = prompt
    if ratio and "aspect_ratio" in properties and "aspect_ratio" not in params:
        params["aspect_ratio"] = ratio
    params = await _replace_file_markers(params)
    _validate_top_level_schema(schema, params)
    return params


async def _load_model_and_config(*, model_id: str, category: ModelCategoryKey) -> tuple[Model, ProviderConfig]:
    """Resolve model and credentials at execution time, avoiding secrets in task payloads."""
    from app.ai_video.core.db import async_session_maker

    async with async_session_maker() as session:
        model = await session.get(Model, model_id)
        if model is None or model.category != category:
            raise RuntimeError(f"Creatify {category.value} model is unavailable: {model_id}")
        resolved = await resolve_provider_config_by_model(session, model=model)
        if resolved.provider_key != "creatify":
            raise RuntimeError("Creatify task was created with a non-Creatify model")
        return model, ProviderConfig(
            provider="creatify",
            api_key=resolved.api_key,
            api_secret=resolved.api_secret,
            base_url=resolved.base_url,
        )


def _asset_url(asset: dict[str, Any]) -> str | None:
    """Find an output URL in the documented asset object and common compatible fields."""
    for key in ("url", "asset_url", "download_url", "video_url", "image_url"):
        value = asset.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _next_delay_seconds(attempt: int) -> int:
    """Use capped backoff so external polling does not monopolize workers or provider quota."""
    initial = max(5, int(settings.creatify_poll_initial_delay_seconds))
    maximum = max(initial, int(settings.creatify_poll_max_delay_seconds))
    return min(maximum, initial * (2 ** min(max(0, attempt), 3)))


async def _load_external_job(task_id: str) -> dict[str, Any] | None:
    """Read the persisted external job metadata from task payload."""
    from app.ai_video.core.db import async_session_maker

    async with async_session_maker() as session:
        row = await session.get(GenerationTask, task_id)
        if row is None:
            raise RuntimeError(f"Task not found: {task_id}")
        run_args = dict((row.payload or {}).get("run_args") or {})
        job = run_args.get("creatify_job")
        return dict(job) if isinstance(job, dict) else None


async def _save_external_job(task_id: str, job: dict[str, Any], *, progress: int) -> None:
    """Persist state before scheduling the next poll, making retries idempotent."""
    from app.ai_video.core.db import async_session_maker

    async with async_session_maker() as session:
        row = await session.get(GenerationTask, task_id)
        if row is None:
            raise RuntimeError(f"Task not found: {task_id}")
        payload = dict(row.payload or {})
        run_args = dict(payload.get("run_args") or {})
        run_args["creatify_job"] = job
        payload["run_args"] = run_args
        row.payload = payload
        store = SqlAlchemyTaskStore(session)
        await store.set_status(task_id, TaskStatus.running)
        await store.set_progress(task_id, progress)
        await session.commit()


def _schedule_poll(task_id: str, *, attempt: int) -> None:
    """Enqueue a later status read only after state is durably committed."""
    from app.ai_video.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id, countdown=_next_delay_seconds(attempt))


async def advance_creatify_video_job(task_id: str, run_args: dict[str, Any]) -> VideoGenerationResult | None:
    """Create or poll one video job; return a result only after Creatify completes."""
    model_id = str(run_args.get("model_id") or "").strip()
    model, cfg = await _load_model_and_config(model_id=model_id, category=ModelCategoryKey.video)
    client = CreatifyAssetGeneratorAdapter()
    external = await _load_external_job(task_id)
    if external is None:
        inp = dict(run_args.get("input") or {})
        schema = _schema_for_model(model)
        params = await _prepare_input_params(
            schema=schema,
            prompt=str(inp.get("prompt") or "").strip(),
            ratio=str(inp.get("ratio") or "").strip() or None,
            provider_params=dict(inp.get("provider_params") or {}),
        )
        job = await client.create_asset(cfg=cfg, model_name=model.name, input_params=params)
        external = {"id": job.id, "attempt": 0, "status": job.status, "model": model.name}
        await _save_external_job(task_id, external, progress=20)
        _schedule_poll(task_id, attempt=0)
        return None

    job = await client.get_asset(cfg=cfg, asset_id=str(external.get("id") or ""))
    attempt = int(external.get("attempt") or 0) + 1
    external.update({"id": job.id, "attempt": attempt, "status": job.status})
    if not job.is_terminal:
        await _save_external_job(task_id, external, progress=min(90, 20 + (attempt * 5)))
        _schedule_poll(task_id, attempt=attempt)
        return None
    if not job.is_successful:
        raise RuntimeError(f"Creatify video generation ended with status={job.status}")
    url = next((candidate for item in job.assets if (candidate := _asset_url(item))), None)
    if not url:
        raise RuntimeError("Creatify completed video job without a downloadable asset URL")
    return VideoGenerationResult(
        url=url,
        provider="creatify",
        provider_task_id=job.id,
        status=job.status,
        artifacts=list(job.assets),
    )


async def advance_creatify_image_job(task_id: str, run_args: dict[str, Any]) -> ImageGenerationResult | None:
    """Create or poll one image job; return images only after Creatify completes."""
    model_id = str(run_args.get("model_id") or "").strip()
    model, cfg = await _load_model_and_config(model_id=model_id, category=ModelCategoryKey.image)
    client = CreatifyAssetGeneratorAdapter()
    external = await _load_external_job(task_id)
    if external is None:
        inp = dict(run_args.get("input") or {})
        schema = _schema_for_model(model)
        params = await _prepare_input_params(
            schema=schema,
            prompt=str(inp.get("prompt") or "").strip(),
            ratio=str(inp.get("target_ratio") or "").strip() or None,
            provider_params=dict(inp.get("provider_params") or {}),
        )
        job = await client.create_asset(cfg=cfg, model_name=model.name, input_params=params)
        external = {"id": job.id, "attempt": 0, "status": job.status, "model": model.name}
        await _save_external_job(task_id, external, progress=20)
        _schedule_poll(task_id, attempt=0)
        return None

    job = await client.get_asset(cfg=cfg, asset_id=str(external.get("id") or ""))
    attempt = int(external.get("attempt") or 0) + 1
    external.update({"id": job.id, "attempt": attempt, "status": job.status})
    if not job.is_terminal:
        await _save_external_job(task_id, external, progress=min(90, 20 + (attempt * 5)))
        _schedule_poll(task_id, attempt=attempt)
        return None
    if not job.is_successful:
        raise RuntimeError(f"Creatify image generation ended with status={job.status}")
    images = [ImageItem(url=url) for item in job.assets if (url := _asset_url(item))]
    if not images:
        raise RuntimeError("Creatify completed image job without downloadable asset URLs")
    return ImageGenerationResult(images=images, provider="creatify", provider_task_id=job.id, status=job.status)
