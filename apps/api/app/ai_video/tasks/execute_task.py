"""统一 Celery 执行入口。

职责：
- Celery 统一只接收业务 task_id；
- 通过 GenerationTask.task_kind + registry 找到具体 WorkerTaskExecutor；
- 回写 executor_type / executor_task_id，便于排障。
"""

from __future__ import annotations

import logging

from celery.result import AsyncResult

from app.ai_video.config import settings
from app.ai_video.core.celery_app import celery_app
from app.ai_video.core.db_sync import sync_session_maker
from app.ai_video.models.task import GenerationTask
from app.ai_video.services.worker.task_registry import task_executor_registry

logger = logging.getLogger(__name__)


def _record_executor_dispatch(task_id: str, *, executor_type: str, executor_task_id: str | None) -> None:
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return
        row.executor_type = executor_type
        row.executor_task_id = executor_task_id
        db.commit()


def enqueue_task_execution(task_id: str, *, countdown: int | None = None) -> AsyncResult | str:
    """Dispatch a task immediately or schedule a durable provider-status poll.

    Creatify jobs are external and may take minutes.  Scheduling a fresh short
    Celery invocation keeps a worker free between polls while `GenerationTask`
    remains the source of truth for UI status.
    """
    if settings.task_executor_backend.strip().lower() == "cloud_tasks":
        from app.ai_video.core.cloud_tasks_dispatch import enqueue_task

        executor_task_id = enqueue_task(task_id=task_id, countdown=countdown)
        _record_executor_dispatch(
            task_id,
            executor_type="cloud_tasks",
            executor_task_id=executor_task_id,
        )
        return executor_task_id

    async_result = (
        run_task_celery.apply_async(args=(task_id,), countdown=countdown)
        if countdown is not None and countdown > 0
        else run_task_celery.delay(task_id)
    )
    _record_executor_dispatch(
        task_id,
        executor_type="celery",
        executor_task_id=async_result.id,
    )
    return async_result


def revoke_task_execution(task_id: str, *, terminate: bool = True, signal: str = "SIGTERM") -> bool:
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return False
        executor_type = (row.executor_type or "").strip()
        executor_task_id = (row.executor_task_id or "").strip()
        if not executor_task_id:
            return False

    if executor_type == "cloud_tasks":
        from app.ai_video.core.cloud_tasks_dispatch import revoke_task

        return revoke_task(executor_task_id=executor_task_id)
    if executor_type != "celery":
        return False
    try:
        AsyncResult(executor_task_id, app=celery_app).revoke(terminate=terminate, signal=signal)
    except Exception:  # noqa: BLE001
        logger.exception("failed to revoke celery task: task_id=%s executor_task_id=%s", task_id, executor_task_id)
        return False
    return True


def run_task(task_id: str) -> None:
    """Run one durable GenerationTask in the current process."""
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return
        task_kind = (row.task_kind or "").strip() or str((row.payload or {}).get("task_kind") or "").strip()
    executor = task_executor_registry.resolve(task_kind)
    executor.run(task_id)


@celery_app.task(name="task.execute")
def run_task_celery(task_id: str) -> None:
    """Celery-compatible local development wrapper around the common runner."""
    run_task(task_id)
