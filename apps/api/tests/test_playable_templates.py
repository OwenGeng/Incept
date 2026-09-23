from __future__ import annotations

import app.incept.db as db
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.incept.auth import get_current_user
from app.incept.models import PlayableTemplateCreateRequest, Role, User
from app.incept.playable_store import create_template, fork_template, list_templates, toggle_template_favorite
from app.routers.incept import router


def _user(user_id: str) -> User:
    return User(id=user_id, name=user_id.title(), email=f"{user_id}@test.local", role=Role.user, team="test")


def _schema() -> dict:
    return {
        "schemaVersion": 1,
        "runtime": "phaser-preview-v1",
        "metadata": {"title": "Garden Quest", "ctaLabel": "Play now", "orientation": "portrait"},
        "assets": {"backgroundDataUri": "data:image/png;base64,client-artwork"},
        "gameplay": {"template": "merge", "accentColor": "#138a72", "targetValue": 16, "tutorialText": "Merge"},
    }


def test_template_strips_client_artwork_and_forks_an_independent_project(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "playables.db")
    owner = _user("owner")
    template = create_template(
        PlayableTemplateCreateRequest(
            workspace_id="wsp_test",
            title="Garden recipe",
            description="A reusable merge loop.",
            visibility="workspace",
            category="merge",
            schema=_schema(),
        ),
        owner,
    )

    assert template.schema_payload["assets"] == {}
    assert template.schema_payload["templateAssetSlots"] == ["background_art"]
    assert "data:" not in str(template.schema_payload)

    fork = fork_template(template.template_id, _user("creator"))
    assert fork.source_template_id == template.template_id
    assert fork.owner_user_id == "creator"
    assert fork.schema_payload["assets"] == {}

    visible = list_templates("wsp_test", _user("creator"))
    assert visible[0].fork_count == 1
    assert visible[0].visibility == "workspace"


def test_private_template_is_not_visible_to_another_creator_and_favorites_toggle(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "private-playables.db")
    owner = _user("owner")
    template = create_template(
        PlayableTemplateCreateRequest(title="Private recipe", visibility="private", category="merge", schema=_schema()),
        owner,
    )

    assert list_templates("wsp_q2", _user("other")) == []
    first = toggle_template_favorite(template.template_id, owner)
    assert first.is_favorited and first.favorite_count == 1
    second = toggle_template_favorite(template.template_id, owner)
    assert not second.is_favorited and second.favorite_count == 0


def test_template_api_serializes_schema_alias_and_forks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "template-api.db")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _user("api-owner")
    client = TestClient(app, raise_server_exceptions=True)

    created = client.post("/playable-templates", json={
        "workspace_id": "wsp_test",
        "title": "API recipe",
        "visibility": "workspace",
        "category": "merge",
        "schema": _schema(),
    })
    assert created.status_code == 200
    payload = created.json()
    assert payload["schema"]["assets"] == {}
    assert "schema_payload" not in payload

    forked = client.post(f"/playable-templates/{payload['template_id']}/fork", json={})
    assert forked.status_code == 200
    assert forked.json()["source_template_id"] == payload["template_id"]


def test_project_api_lists_and_reads_only_its_owner_projects(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "projects-api.db")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _user("api-owner")
    client = TestClient(app, raise_server_exceptions=True)

    created = client.post("/playable-projects", json={
        "workspace_id": "wsp_test",
        "title": "My playable",
        "schema": _schema(),
    })
    assert created.status_code == 200
    project = created.json()
    assert project["schema"]["metadata"]["title"] == "Garden Quest"

    listed = client.get("/playable-projects?workspace_id=wsp_test")
    assert listed.status_code == 200
    assert [item["project_id"] for item in listed.json()] == [project["project_id"]]

    loaded = client.get(f"/playable-projects/{project['project_id']}")
    assert loaded.status_code == 200
    assert loaded.json()["title"] == "My playable"
