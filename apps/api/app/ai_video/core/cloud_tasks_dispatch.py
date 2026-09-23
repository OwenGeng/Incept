"""Cloud Tasks dispatch for the Cloud Run AI Video executor endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from app.ai_video.config import settings


def _validate_configuration() -> None:
    """Fail closed when Cloud Tasks was selected without its deployment contract."""
    missing = [
        name
        for name, value in {
            "GCP_PROJECT_ID": settings.resolved_cloud_tasks_project_id,
            "CLOUD_TASKS_LOCATION": settings.cloud_tasks_location,
            "CLOUD_TASKS_QUEUE": settings.cloud_tasks_queue,
            "TASK_RUNNER_URL": settings.task_runner_url,
            "TASK_RUNNER_SERVICE_ACCOUNT_EMAIL": settings.task_runner_service_account_email,
            "INTERNAL_API_KEY": settings.internal_api_key,
        }.items()
        if not value.strip()
    ]
    if missing:
        raise RuntimeError(f"Cloud Tasks is selected but missing deployment configuration: {', '.join(missing)}")


@lru_cache
def _client():
    """Create the ADC-authenticated Cloud Tasks client once per API process."""
    try:
        from google.cloud import tasks_v2
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("google-cloud-tasks must be installed to use TASK_EXECUTOR_BACKEND=cloud_tasks") from exc
    return tasks_v2.CloudTasksClient()


def _queue_path() -> str:
    """Return the fully-qualified, operator-owned queue name."""
    _validate_configuration()
    return _client().queue_path(
        settings.resolved_cloud_tasks_project_id,
        settings.cloud_tasks_location,
        settings.cloud_tasks_queue,
    )


def enqueue_task(*, task_id: str, countdown: int | None = None) -> str:
    """Create an authenticated HTTP task and return its durable Cloud Tasks name."""
    _validate_configuration()
    from google.cloud import tasks_v2

    # AI Video is mounted in the Incept API, rather than deployed as its own
    # Cloud Run service. Keep the configured URL at the service root so OIDC
    # has a stable audience, then append the mounted module route here.
    request_url = f"{settings.task_runner_url.rstrip('/')}/ai-video/api/v1/internal/task-executions/{task_id}"
    http_request = tasks_v2.HttpRequest(
        http_method=tasks_v2.HttpMethod.POST,
        url=request_url,
        headers={"X-Internal-API-Key": settings.internal_api_key},
        oidc_token=tasks_v2.OidcToken(
            service_account_email=settings.task_runner_service_account_email,
            audience=settings.task_runner_url.rstrip("/"),
        ),
    )
    task = tasks_v2.Task(http_request=http_request)
    deadline_seconds = settings.task_runner_dispatch_deadline_seconds
    if deadline_seconds < 15 or deadline_seconds > 1800:
        raise RuntimeError("TASK_RUNNER_DISPATCH_DEADLINE_SECONDS must be between 15 and 1800")
    # proto-plus exposes these protobuf fields as Python datetime objects.
    task.dispatch_deadline = timedelta(seconds=deadline_seconds)
    if countdown is not None and countdown > 0:
        task.schedule_time = datetime.now(timezone.utc) + timedelta(seconds=countdown)
    response = _client().create_task(parent=_queue_path(), task=task)
    return str(response.name)


def revoke_task(*, executor_task_id: str) -> bool:
    """Delete a pending Cloud Tasks task; a running HTTP request cannot be preempted."""
    if not executor_task_id.strip():
        return False
    try:
        _client().delete_task(name=executor_task_id)
    except Exception:  # noqa: BLE001
        return False
    return True
