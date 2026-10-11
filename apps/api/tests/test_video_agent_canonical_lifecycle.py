from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routers import video_studio as api_module
from app.video_studio import pi_agent as agent, store
from test_video_pi_agent import reply, call
from app.video_studio.agent_turns import prepare_turn
from app.video_studio.models import CanvasCreate, ProjectCreate, VideoNode

EMAIL = "canonical-lifecycle@linglonglab.internal"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project(EMAIL, ProjectCreate(name="Canonical lifecycle"))
    app = FastAPI()
    app.include_router(api_module.router)
    return TestClient(app), {"x-user-email": EMAIL, "x-internal-api-key": settings.internal_api_key}, project


def test_canonical_chat_never_emits_canvas_snapshot_over_concurrent_user_edit(setup, monkeypatch):
    api, headers, project = setup
    def model(payload, **kwargs):
        canvas = store.get_project(EMAIL, project.id).canvas
        canvas.nodes.append(VideoNode(id="human", type="text", data={"text": "human edit"}))
        store.save_canvas(EMAIL, project.id, canvas)
        return reply(payload, '你好！')
    monkeypatch.setattr(agent, "model_response", model)

    response = api.post(f"/video-studio/projects/{project.id}/agent", json={"prompt": "解释文字节点"}, headers=headers)
    events = [json.loads(line) for line in response.text.splitlines()]

    assert not any(event["type"] == "canvas" for event in events)
    assert [node.id for node in store.get_project(EMAIL, project.id).canvas.nodes] == ["human"]


def test_canonical_request_uses_original_canvas_even_if_active_switches_before_worker(setup, monkeypatch):
    api, headers, project = setup
    original_id = project.active_canvas_id
    second_id = store.create_canvas(EMAIL, project.id, CanvasCreate(name="Second")).active_canvas_id
    store.activate_canvas(EMAIL, project.id, original_id)
    called = {}
    real_run = agent.run_agent
    def run(**kwargs):
        called["canvas_id"] = kwargs.get("canvas_id")
        called["canvas_document"] = kwargs.get("canvas_document")
        store.activate_canvas(EMAIL, project.id, second_id)
        return real_run(**kwargs)
    monkeypatch.setattr(api_module, "run_agent", run)
    def model(payload, **kwargs):
        if any(m['role'] == 'toolResult' for m in payload['context']['messages']):
            return reply(payload, '已添加图片节点。')
        return reply(payload, calls=[call('addNode', {'type':'imageNode','position':{'x':100,'y':100}})])
    monkeypatch.setattr(agent, "model_response", model)

    response = api.post(f"/video-studio/projects/{project.id}/agent", json={"prompt": "请添加图片节点"}, headers=headers)
    events = [json.loads(line) for line in response.text.splitlines()]

    assert called["canvas_id"] == original_id
    assert called["canvas_document"] is not None
    assert len(store.get_project_canvas(EMAIL, project.id, original_id).nodes) == 1
    assert store.get_project_canvas(EMAIL, project.id, second_id).nodes == []
    assert any(event["type"] == "canvas" for event in events)


def test_canonical_cancel_requires_run_id_and_stale_stop_cannot_cancel_new_run(setup):
    api, headers, project = setup
    conversation = prepare_turn(email=EMAIL, project_id=project.id, prompt="你好", conversation_id=None)
    url = f"/video-studio/projects/{project.id}/conversations/{conversation.id}/cancel"
    missing = api.post(url, json={}, headers=headers)
    malformed = api.post(url, json={"run_id": "malformed"}, headers=headers)
    stale = api.post(url, json={"run_id": "f" * 32}, headers=headers)
    assert missing.status_code == 422
    assert malformed.status_code == 422
    assert stale.status_code == 204
    assert store.get_conversation(EMAIL, project.id, conversation.id).run_status == "running"
    stopped = api.post(url, json={"run_id": conversation.run_id}, headers=headers)
    assert stopped.status_code == 204
    assert store.get_conversation(EMAIL, project.id, conversation.id).run_status == "cancelled"
