"""Unit coverage for the GCP-only Cloud Tasks execution path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai_video.config import settings
from app.ai_video.core import cloud_tasks_dispatch


def _configure_cloud_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply a complete non-secret Cloud Tasks configuration to shared settings."""
    monkeypatch.setattr(settings, "gcp_project_id", "incept-project")
    monkeypatch.setattr(settings, "cloud_tasks_project_id", "")
    monkeypatch.setattr(settings, "cloud_tasks_location", "asia-northeast1")
    monkeypatch.setattr(settings, "cloud_tasks_queue", "ai-video")
    monkeypatch.setattr(settings, "task_runner_url", "https://ai-video-api.example.run.app")
    monkeypatch.setattr(settings, "task_runner_service_account_email", "runner@example.iam.gserviceaccount.com")
    monkeypatch.setattr(settings, "internal_api_key", "test-internal-key")
    monkeypatch.setattr(settings, "task_runner_dispatch_deadline_seconds", 900)


def test_cloud_tasks_requires_explicit_deployment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gcp_project_id", "")
    monkeypatch.setattr(settings, "cloud_tasks_location", "")
    monkeypatch.setattr(settings, "cloud_tasks_queue", "")
    monkeypatch.setattr(settings, "task_runner_url", "")
    monkeypatch.setattr(settings, "task_runner_service_account_email", "")
    monkeypatch.setattr(settings, "internal_api_key", "")

    with pytest.raises(RuntimeError, match="missing deployment configuration"):
        cloud_tasks_dispatch._validate_configuration()


def test_enqueue_cloud_task_uses_private_runner_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_cloud_tasks(monkeypatch)
    captured: dict[str, object] = {}

    class _Client:
        def queue_path(self, project: str, location: str, queue: str) -> str:
            assert (project, location, queue) == ("incept-project", "asia-northeast1", "ai-video")
            return "projects/incept-project/locations/asia-northeast1/queues/ai-video"

        def create_task(self, *, parent: str, task: object) -> SimpleNamespace:
            captured["parent"] = parent
            captured["task"] = task
            return SimpleNamespace(name="projects/incept-project/tasks/task-1")

        def delete_task(self, *, name: str) -> None:
            captured["deleted"] = name

    fake_client = _Client()
    monkeypatch.setattr(cloud_tasks_dispatch, "_client", lambda: fake_client)

    name = cloud_tasks_dispatch.enqueue_task(task_id="task-1", countdown=30)
    assert name == "projects/incept-project/tasks/task-1"
    assert captured["parent"] == "projects/incept-project/locations/asia-northeast1/queues/ai-video"
    task = captured["task"]
    request = task.http_request  # type: ignore[union-attr]
    assert request.url.endswith("/api/v1/internal/task-executions/task-1")
    assert request.headers["X-Internal-API-Key"] == "test-internal-key"
    assert request.oidc_token.service_account_email == "runner@example.iam.gserviceaccount.com"
    assert cloud_tasks_dispatch.revoke_task(executor_task_id=name) is True
    assert captured["deleted"] == name
