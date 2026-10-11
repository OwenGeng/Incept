from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routers.video_legacy import router, _conversation_file
from app.routers.video_studio import router as canonical_router
from app.video_studio import store
from app.video_studio.agent_turns import prepare_turn, TurnControl
from app.video_studio.models import AgentMessage, ProjectCreate

EMAIL = "mutations@linglonglab.internal"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project(EMAIL, ProjectCreate(name="Mutation safety"))
    conversation = prepare_turn(email=EMAIL, project_id=project.id,
        prompt="30秒，方向1没问题，确认方案", conversation_id=None)
    app = FastAPI()
    app.include_router(router)
    app.include_router(canonical_router)
    api = TestClient(app, raise_server_exceptions=False)
    headers = {"x-user-email": EMAIL, "x-internal-api-key": settings.internal_api_key}
    body = {"directory": project.id, "sessionFile": _conversation_file(conversation)}
    return api, headers, body, project, conversation


@pytest.mark.parametrize("method,path,extra", [
    ("patch", "/agent/rename", {"name": "Renamed"}),
    ("delete", "/agent/message", {"entryIds": []}),
    ("delete", "/agent/conversation", {}),
])
def test_mutations_reject_running_turn(setup, method, path, extra):
    api, headers, body, project, conversation = setup
    response = api.request(method, "/video-legacy/api" + path, json={**body, **extra}, headers=headers)
    assert response.status_code == 409
    persisted = store.get_conversation(EMAIL, project.id, conversation.id)
    assert persisted.run_status == "running"
    assert persisted.messages[0].id == conversation.messages[0].id


def test_delete_user_removes_associated_reply_and_replays_remaining_choices(setup):
    api, headers, body, project, conversation = setup
    selected_user_id = conversation.messages[0].id
    conversation.run_status = "completed"
    conversation.task_state = {"duration_seconds": 30, "brief_approved": True}
    conversation.research_history = [{"name": "old-branch", "result": {"approved": True}}]
    conversation.messages.extend([
        AgentMessage(id="reply", role="assistant", content="Approved 30 seconds"),
        AgentMessage(id="other-user", role="user", content="你好"),
        AgentMessage(id="other-reply", role="assistant", content="你好！"),
    ])
    store.save_conversation(EMAIL, project.id, conversation)

    response = api.request("delete", "/video-legacy/api/agent/message", json={**body, "entryIds": [selected_user_id]}, headers=headers)

    assert response.status_code == 200
    persisted = store.get_conversation(EMAIL, project.id, conversation.id)
    assert [message.id for message in persisted.messages] == ["other-user", "other-reply"]
    assert persisted.task_state == {}  # No second, Python-inferred production memory.
    assert persisted.research_history == []


def test_ui_message_delete_is_applied_to_sdk_history_without_rebuilding_text(setup, monkeypatch):
    import json
    from app.video_studio import pi_agent
    from test_video_pi_agent import reply
    api, headers, body, project, _ = setup
    def run(prompt, conversation_id=None):
        return pi_agent.run_agent(email=EMAIL, project_id=project.id, prompt=prompt, conversation_id=conversation_id)[0]
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: reply(p, 'Saved reply.'))
    first = run('Keep Bronco plan.')
    second = run('Delete this Tesla topic later.', first.id)
    deleted_user = second.messages[-2]
    third = run('Keep another unrelated note.', first.id)
    response = api.request('delete', '/video-legacy/api/agent/message', json={**body,
        'sessionFile': _conversation_file(third), 'entryIds': [deleted_user.id]}, headers=headers)
    assert response.status_code == 200
    pending = store.get_conversation(EMAIL, project.id, first.id)
    assert deleted_user.pi_entry_id in pending.pi_deleted_entries
    def model(payload, **kwargs):
        context = json.dumps(payload['context']['messages'])
        assert 'Tesla' not in context
        assert 'Bronco' in context and 'unrelated note' in context
        return reply(payload, 'The deleted turn is not model context.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    saved = run('Continue.', first.id)
    assert saved.pi_deleted_entries == []


@pytest.mark.parametrize("method,path,extra", [
    ("patch", "/agent/rename", {"name": "Renamed"}),
    ("delete", "/agent/message", {"entryIds": []}),
    ("delete", "/agent/conversation", {}),
])
def test_mutations_validate_ids_and_do_not_access_another_user(setup, method, path, extra):
    api, headers, body, _, _ = setup
    malformed = api.request(method, "/video-legacy/api" + path,
        json={**body, **extra, "sessionFile": "../../secrets.json"}, headers=headers)
    assert malformed.status_code == 400
    other = api.request(method, "/video-legacy/api" + path,
        json={**body, **extra}, headers={**headers, "x-user-email": "other@linglonglab.internal"})
    assert other.status_code == 404


def test_agent_rejects_oversized_canvas_before_reading_or_starting_turn(setup):
    api, headers, body, project, conversation = setup
    target = store.safe_asset_path(store.assets_root(EMAIL, project.id), "large.json")
    with target.open("wb") as stream:
        stream.truncate(5 * 1024 * 1024 + 1)
    response = api.post("/video-legacy/api/agent", json={**body, "prompt": "你好", "canvas": {"id": "large.json"}}, headers=headers)
    assert response.status_code == 413
    assert len(store.get_conversation(EMAIL, project.id, conversation.id).messages) == 1


def test_completed_conversation_can_be_renamed(setup):
    api, headers, body, project, conversation = setup
    conversation.run_status = "completed"
    store.save_conversation(EMAIL, project.id, conversation)
    response = api.patch("/video-legacy/api/agent/rename", json={**body, "name": "New name"}, headers=headers)
    assert response.status_code == 200
    assert store.get_conversation(EMAIL, project.id, conversation.id).name == "New name"


def test_deleting_cancelled_conversation_cannot_be_undone_by_old_worker(setup):
    api, headers, body, project, conversation = setup
    conversation.run_status = "cancelled"
    store.save_conversation(EMAIL, project.id, conversation)
    response = api.request("delete", "/video-legacy/api/agent/conversation", json=body, headers=headers)
    assert response.status_code == 200
    with pytest.raises(FileNotFoundError):
        TurnControl(EMAIL, project.id, conversation).save(conversation)
    assert store.list_conversations(EMAIL, project.id) == []


@pytest.mark.parametrize("method,extra", [("patch", {"name": "New name"}), ("delete", None)])
def test_canonical_mutations_reject_running_conversation(setup, method, extra):
    api, headers, _, project, conversation = setup
    response = api.request(method, f"/video-studio/projects/{project.id}/conversations/{conversation.id}", json=extra, headers=headers)
    assert response.status_code == 409
    assert store.get_conversation(EMAIL, project.id, conversation.id).run_status == "running"


def test_canonical_completed_conversation_can_be_renamed_and_deleted(setup):
    api, headers, _, project, conversation = setup
    conversation.run_status = "completed"
    store.save_conversation(EMAIL, project.id, conversation)
    url = f"/video-studio/projects/{project.id}/conversations/{conversation.id}"
    assert api.patch(url, json={"name": "New name"}, headers=headers).status_code == 200
    assert store.get_conversation(EMAIL, project.id, conversation.id).name == "New name"
    assert api.delete(url, headers=headers).status_code == 204
