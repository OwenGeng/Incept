from __future__ import annotations

from types import SimpleNamespace

import anthropic
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.routers.video_legacy import router


def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def headers(email: str = "local@linglonglab.internal") -> dict[str, str]:
    return {"x-user-email": email, "x-internal-api-key": settings.internal_api_key}


def test_vue_workspace_project_and_file_compatibility(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    created = api.post(
        "/video-legacy/api/workspaces/create",
        json={"name": "Vue project"},
        headers=headers(),
    )
    assert created.status_code == 200
    project_id = created.json()["data"]["directory"]

    projects = api.get("/video-legacy/api/workspaces/projects", headers=headers())
    assert projects.json()["data"][0]["directory"] == project_id

    listing = api.get(
        "/video-legacy/api/workspaces/files/list",
        params={"directory": project_id},
        headers=headers(),
    )
    assert listing.status_code == 200
    assert "画布1.json" in {item["name"] for item in listing.json()["data"]["entries"]}

    written = api.put(
        "/video-legacy/api/workspaces/files/write",
        params={"directory": project_id, "path": "notes/brief.txt"},
        content=b"hello",
        headers={**headers(), "content-type": "application/octet-stream"},
    )
    assert written.status_code == 200
    content = api.get(
        "/video-legacy/api/workspaces/files/read",
        params={"directory": project_id, "path": "notes/brief.txt"},
        headers=headers(),
    )
    assert content.content == b"hello"


def test_vue_settings_and_built_in_nodes_are_server_managed(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    response = api.get("/video-legacy/api/settings/get", headers=headers())
    assert response.status_code == 200
    assert response.json()["data"]["privacy"]["dataCollectionEnabled"] is False
    assert response.json()["data"]["customProviders"][0]["apiKey"] == ""
    assert response.json()["data"]["ui"]["language"] == "en"

    nodes = api.get("/video-legacy/api/nodes/get", headers=headers()).json()["data"]
    assert {item["name"] for item in nodes} == {
        "audioNode",
        "director3dNode",
        "imageGenerationNode",
        "imageNode",
        "textNode",
        "videoGenerationNode",
        "videoNode",
    }
    assert all(item["url"].startswith("/video-app/nodes/") for item in nodes)

    language_models = api.get("/video-legacy/api/ai/models", headers=headers()).json()["data"]
    model_ids = {item["modelId"] for item in language_models}
    assert {"gemini-3.8-flash", "gemini-3.1-pro-preview", "gpt-6.1-sol"} <= model_ids
    assert "claude-opus-5-5" not in model_ids
    assert "gemini-3.1-flash-lite" not in model_ids
    assert "gemini-3.6-flash" not in model_ids
    text_default = next(item for item in language_models if item["isDefault"])
    assert (text_default["providerId"], text_default["modelId"]) == ("google-vertex-ai", "gemini-3.8-flash")

    media_models = api.get("/video-legacy/api/ai/media/models", headers=headers()).json()["data"]
    media_ids = {item["modelId"] for item in media_models}
    assert "gemini-3.1-flash-image" in media_ids
    assert "gpt-image-2.5-flare" in media_ids
    assert "gemini-omni-1.1-flash-preview" in media_ids
    assert "gpt-4o-mini-tts-2025-12-15" in media_ids
    assert "gemini-3.1-flash-tts-preview" in media_ids
    defaults = {item["type"]: (item["providerId"], item["modelId"]) for item in media_models if item["isDefault"]}
    assert defaults == {
        "image": ("google-vertex-ai", "gemini-3.1-flash-image"),
        "video": ("google-vertex-ai", "gemini-omni-1.1-flash-preview"),
        "audio": ("google-cloud-tts", "gemini-3.1-flash-tts-preview"),
    }

    tools = api.get("/video-legacy/api/tools/get", headers=headers()).json()["data"]["tools"]
    transcript = next(item for item in tools if item["name"] == "videoTranscriptFetch")
    assert transcript["enabled"] is True
    assert transcript["author"] == "LinglongLab"


def test_claude_sonnet_5_5_is_listed_only_when_anthropic_key_is_configured(tmp_path, monkeypatch):
    from app.incept.config import get_settings

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    get_settings.cache_clear()
    api = client(tmp_path, monkeypatch)
    models = api.get("/video-legacy/api/ai/models", headers=headers()).json()["data"]
    assert all(item["providerId"] != "anthropic" for item in models)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    get_settings.cache_clear()
    try:
        api = client(tmp_path, monkeypatch)
        models = api.get("/video-legacy/api/ai/models", headers=headers()).json()["data"]
        claude = next(item for item in models if item["modelId"] == "claude-sonnet-5-5")
        assert claude["providerId"] == "anthropic"
        assert claude["protocol"] == "anthropic-messages"
    finally:
        get_settings.cache_clear()


def test_claude_generation_uses_direct_anthropic_api(tmp_path, monkeypatch):
    from app.incept.config import get_settings

    captured: dict[str, object] = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="direct anthropic response")])

    class FakeAnthropic:
        def __init__(self, *, api_key: str):
            captured["api_key"] = api_key
            self.messages = FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    get_settings.cache_clear()
    try:
        api = client(tmp_path, monkeypatch)
        response = api.post(
            "/video-legacy/api/ai/generate",
            headers=headers(),
            json={
                "providerId": "anthropic",
                "modelId": "claude-sonnet-5-5",
                "context": {
                    "systemPrompt": "You are a video producer.",
                    "messages": [{"role": "user", "content": "Create a shot list."}],
                },
            },
        )
        assert response.status_code == 200
        assert "direct anthropic response" in response.text
        assert captured["api_key"] == "test-anthropic-key"
        assert captured["model"] == "claude-sonnet-5-5"
        assert captured["system"] == "You are a video producer."
        assert captured["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Create a shot list."}]}]
    finally:
        get_settings.cache_clear()


def test_vue_agent_skill_menu_uses_enabled_fastapi_catalog(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    created = api.post(
        "/video-legacy/api/workspaces/create",
        json={"name": "Skill project"},
        headers=headers(),
    )
    project_id = created.json()["data"]["directory"]

    response = api.get(
        "/video-legacy/api/agent/skills",
        params={"directory": project_id},
        headers=headers(),
    )

    assert response.status_code == 200
    skills = response.json()["data"]
    assert skills
    assert all(set(item) == {"name", "description"} for item in skills)


def test_video_api_requires_forwarded_authenticated_identity(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    response = api.get(
        "/video-legacy/api/workspaces/projects",
        headers={"x-internal-api-key": settings.internal_api_key},
    )
    assert response.status_code == 401


def test_retired_video_production_routes_are_not_published():
    api = TestClient(create_app())
    assert api.get("/video-productions").status_code == 404
    assert api.get("/video-production-capabilities").status_code == 404
