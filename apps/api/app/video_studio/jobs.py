from __future__ import annotations

import asyncio
import threading
import uuid

from . import store
from .models import ExportJob, ExportRequest
from .render import export_project


_tasks: dict[str, asyncio.Task[None]] = {}
_lock = threading.RLock()


def create_export_job(email: str, project_id: str, request: ExportRequest) -> ExportJob:
    store.get_project(email, project_id)
    if request.idempotency_key:
        existing = next(
            (
                job
                for job in store.list_export_jobs(email, project_id)
                if job.request.idempotency_key == request.idempotency_key
            ),
            None,
        )
        if existing:
            if existing.status in {"queued", "running"}:
                _start_task(email, project_id, existing.id)
            return existing
    job = store.save_export_job(
        email,
        ExportJob(id=uuid.uuid4().hex, project_id=project_id, request=request),
    )
    _start_task(email, project_id, job.id)
    return job


def _start_task(email: str, project_id: str, job_id: str) -> None:
    with _lock:
        existing = _tasks.get(job_id)
        if existing and not existing.done():
            return
        _tasks[job_id] = asyncio.create_task(_run_export(email, job_id, project_id))


def ensure_export_job_running(email: str, project_id: str, job_id: str) -> ExportJob:
    job = store.get_export_job(email, project_id, job_id)
    if job.status in {"queued", "running"}:
        _start_task(email, project_id, job_id)
    return job


async def _run_export(email: str, job_id: str, project_id: str) -> None:
    def update(progress: int, message: str) -> None:
        current = store.get_export_job(email, project_id, job_id)
        if current.status != "cancelled":
            store.save_export_job(
                email,
                current.model_copy(
                    update={"status": "running", "progress": progress, "message": message}
                ),
            )

    def cancelled() -> bool:
        return store.get_export_job(email, project_id, job_id).status == "cancelled"

    try:
        job = store.get_export_job(email, project_id, job_id)
        update(1, "Starting export")
        result = await asyncio.to_thread(
            export_project,
            email,
            project_id,
            job.request,
            progress=update,
            cancelled=cancelled,
        )
        current = store.get_export_job(email, project_id, job_id)
        if current.status != "cancelled":
            store.save_export_job(
                email,
                current.model_copy(
                    update={
                        "status": "completed",
                        "progress": 100,
                        "message": "Export complete",
                        "result": result,
                    }
                ),
            )
    except InterruptedError:
        current = store.get_export_job(email, project_id, job_id)
        store.save_export_job(
            email,
            current.model_copy(update={"status": "cancelled", "message": "Export cancelled"}),
        )
    except Exception as error:
        current = store.get_export_job(email, project_id, job_id)
        if current.status != "cancelled":
            store.save_export_job(
                email,
                current.model_copy(
                    update={"status": "failed", "message": str(error)[-2_000:]}
                ),
            )
    finally:
        with _lock:
            _tasks.pop(job_id, None)


def cancel_export_job(email: str, project_id: str, job_id: str) -> ExportJob:
    job = store.get_export_job(email, project_id, job_id)
    if job.status in {"completed", "failed"}:
        return job
    return store.save_export_job(
        email,
        job.model_copy(
            update={"status": "cancelled", "message": "Cancellation requested"}
        ),
    )
