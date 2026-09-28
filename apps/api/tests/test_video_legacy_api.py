from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
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

    tools = api.get("/video-legacy/api/tools/get", headers=headers()).json()["data"]["tools"]
    transcript = next(item for item in tools if item["name"] == "videoTranscriptFetch")
    assert transcript["enabled"] is True
    assert transcript["author"] == "LinglongLab"


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
