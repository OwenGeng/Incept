from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routers.video_studio import router


def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def headers(email: str) -> dict[str, str]:
    return {
        "x-user-email": email,
        "x-internal-api-key": settings.internal_api_key,
    }


def test_project_canvas_and_asset_api(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    request_headers = headers("artist@example.com")

    created = api.post("/video-studio/projects", json={"name": "Campaign"}, headers=request_headers)
    assert created.status_code == 201
    project_id = created.json()["id"]

    canvas = {
        "nodes": [
            {
                "id": "brief",
                "type": "text",
                "position": {"x": 10, "y": 20},
                "data": {"text": "A concise launch film"},
            }
        ],
        "edges": [],
    }
    saved = api.put(
        f"/video-studio/projects/{project_id}/canvas", json=canvas, headers=request_headers
    )
    assert saved.status_code == 200
    assert saved.json()["nodes"][0]["id"] == "brief"

    uploaded = api.post(
        f"/video-studio/projects/{project_id}/assets/upload",
        params={"path": "references"},
        files={"file": ("brief.txt", b"hello", "text/plain")},
        headers=request_headers,
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["path"] == "references/brief.txt"

    listing = api.get(
        f"/video-studio/projects/{project_id}/assets",
        params={"path": "references"},
        headers=request_headers,
    )
    assert [item["name"] for item in listing.json()] == ["brief.txt"]

    content = api.get(
        f"/video-studio/projects/{project_id}/assets/file",
        params={"path": "references/brief.txt"},
        headers=request_headers,
    )
    assert content.content == b"hello"


def test_project_api_is_user_scoped(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    created = api.post(
        "/video-studio/projects",
        json={"name": "Private"},
        headers=headers("one@example.com"),
    )
    project_id = created.json()["id"]

    missing = api.get(
        f"/video-studio/projects/{project_id}",
        headers=headers("two@example.com"),
    )
    assert missing.status_code == 404
