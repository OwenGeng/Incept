from fastapi.testclient import TestClient

from app.ai_video.config import settings
from app.ai_video.main import app


def test_internal_proxy_key_is_required_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "internal_api_key", "test-internal-key")

    with TestClient(app) as client:
        denied = client.get("/api/v1/health")
        allowed = client.get("/api/v1/health", headers={"x-internal-api-key": "test-internal-key"})

    assert denied.status_code == 401
    assert allowed.status_code == 200
