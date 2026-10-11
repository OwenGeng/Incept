from __future__ import annotations

import asyncio
import base64
import hashlib
import mimetypes
import threading
import uuid
from pathlib import Path

from app.routers.video_runtime import ManagedMediaRequest, generate_media, validate_media_model
from app.incept.config import get_settings

from . import store
from .models import MediaJob, MediaJobCreate


_tasks: dict[str, asyncio.Task[None]] = {}
_lock = threading.RLock()


def _frame_base64(email: str, project_id: str, relative_path: str | None, expected_sha256: str | None = None) -> str | None:
    if not relative_path:
        return None
    root = store.assets_root(email, project_id)
    path = store.safe_asset_path(root, relative_path)
    if not path.is_file():
        raise FileNotFoundError(relative_path)
    mime_type = store.asset_mime_type(path)
    if not mime_type.startswith("image/"):
        raise ValueError(f"Frame asset must be an image: {relative_path}")
    payload = path.read_bytes()
    if expected_sha256 and hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('Approved frame asset has changed; approve a new request before generation')
    return base64.b64encode(payload).decode("ascii")


def _extension_for_mime(mime_type: str) -> str:
    preferred = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/opus": ".opus",
    }
    return preferred.get(mime_type) or mimetypes.guess_extension(mime_type) or ".bin"


def _write_result(
    email: str,
    project_id: str,
    job_id: str,
    media_type: str,
    mime_type: str,
    encoded: str,
    output_directory: str,
) -> tuple[str, int]:
    try:
        payload = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise ValueError("Vertex returned invalid media bytes") from error
    if not payload:
        raise ValueError("Vertex returned an empty media file")

    root = store.assets_root(email, project_id)
    directory = store.safe_asset_path(root, output_directory, allow_root=True)
    relative_path = directory.relative_to(root) / f"{media_type}-{job_id}{_extension_for_mime(mime_type)}"
    target = store.safe_asset_path(root, relative_path.as_posix())
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return relative_path.as_posix(), len(payload)


def create_media_job(email: str, project_id: str, request: MediaJobCreate) -> MediaJob:
    # Validate ownership before accepting a potentially billable operation.
    store.get_project(email, project_id)
    validate_media_model(request.media_type, request.provider_id, request.model_id)
    if request.idempotency_key:
        existing = next(
            (
                job
                for job in store.list_media_jobs(email, project_id)
                if job.request.idempotency_key == request.idempotency_key
            ),
            None,
        )
        if existing:
            if existing.status == "queued":
                _start_task(email, project_id, existing.id)
            return existing
    settings = get_settings()
    location = settings.vertex_veo_location if request.media_type == "video" else settings.gcp_location
    job = store.save_media_job(
        email,
        MediaJob(
            id=uuid.uuid4().hex,
            project_id=project_id,
            request=request,
            provider=request.provider_id,
            model=request.model_id,
            location=location,
        ),
    )
    _start_task(email, project_id, job.id)
    return job


def _start_task(email: str, project_id: str, job_id: str) -> None:
    with _lock:
        existing = _tasks.get(job_id)
        if existing and not existing.done():
            return
        _tasks[job_id] = asyncio.create_task(_run_media(email, project_id, job_id))


def ensure_media_job_running(email: str, project_id: str, job_id: str) -> MediaJob:
    job = store.get_media_job(email, project_id, job_id)
    if job.status == "queued":
        _start_task(email, project_id, job_id)
    elif job.status == "running":
        with _lock:
            active = _tasks.get(job_id)
        if not active or active.done():
            # A generation request cannot be safely replayed after a process
            # restart because that could charge twice for the same user action.
            job = store.save_media_job(
                email,
                job.model_copy(
                    update={
                        "status": "failed",
                        "message": "Generation was interrupted; retry to start a new request",
                    }
                ),
            )
    return job


async def _run_media(email: str, project_id: str, job_id: str) -> None:
    try:
        current = store.get_media_job(email, project_id, job_id)
        if current.status == "cancelled":
            return
        current = store.save_media_job(
            email,
            current.model_copy(
                update={"status": "running", "progress": 5, "message": "Preparing media request"}
            ),
        )
        first_frame, last_frame = await asyncio.gather(
            asyncio.to_thread(
                _frame_base64,
                email,
                project_id,
                current.request.first_frame_path,
                current.request.input_revisions.get(current.request.first_frame_path),
            ),
            asyncio.to_thread(
                _frame_base64,
                email,
                project_id,
                current.request.last_frame_path,
                current.request.input_revisions.get(current.request.last_frame_path),
            ),
        )
        if store.get_media_job(email, project_id, job_id).status == "cancelled":
            return
        store.save_media_job(
            email,
            current.model_copy(
                update={"status": "running", "progress": 15, "message": "Generating with Vertex AI"}
            ),
        )
        response = await generate_media(
            ManagedMediaRequest(
                media_type=current.request.media_type,
                provider_id=current.request.provider_id,
                model_id=current.request.model_id,
                prompt=current.request.prompt,
                ratio=current.request.ratio,
                size=current.request.size,
                duration=current.request.duration,
                first_frame=first_frame,
                last_frame=last_frame,
                resolution=current.request.resolution,
                generate_audio=current.request.generate_audio,
                voice=current.request.voice,
                speed=current.request.speed,
                format=current.request.format,
            )
        )
        if store.get_media_job(email, project_id, job_id).status == "cancelled":
            return
        store.save_media_job(
            email,
            current.model_copy(
                update={"status": "running", "progress": 90, "message": "Saving generated asset"}
            ),
        )
        asset_path, result_size = await asyncio.to_thread(
            _write_result,
            email,
            project_id,
            job_id,
            response.media_type,
            response.mime_type,
            response.data,
            current.request.output_directory,
        )
        latest = store.get_media_job(email, project_id, job_id)
        if latest.status != "cancelled":
            store.save_media_job(
                email,
                latest.model_copy(
                    update={
                        "status": "completed",
                        "progress": 100,
                        "message": "Media generation complete",
                        "result_asset_path": asset_path,
                        "result_mime_type": response.mime_type,
                        "result_size": result_size,
                    }
                ),
            )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        current = store.get_media_job(email, project_id, job_id)
        if current.status != "cancelled":
            store.save_media_job(
                email,
                current.model_copy(
                    update={"status": "failed", "message": str(error)[-2_000:]}
                ),
            )
    finally:
        with _lock:
            _tasks.pop(job_id, None)


def cancel_media_job(email: str, project_id: str, job_id: str) -> MediaJob:
    job = store.get_media_job(email, project_id, job_id)
    if job.status in {"completed", "failed", "cancelled"}:
        return job
    cancelled = store.save_media_job(
        email,
        job.model_copy(
            update={"status": "cancelled", "message": "Cancellation requested"}
        ),
    )
    with _lock:
        active = _tasks.get(job_id)
    if active and not active.done():
        active.cancel()
    return cancelled
