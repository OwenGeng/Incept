from __future__ import annotations

import json

from app.video_studio import agent, store
from app.video_studio.models import ProjectCreate


def test_agent_updates_canvas_and_persists_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project("agent@example.com", ProjectCreate(name="Agent test"))
    monkeypatch.setattr(
        agent,
        "_call_model",
        lambda _prompt, _parts: json.dumps(
            {
                "message": "已创建脚本和图片生成节点。",
                "operations": [
                    {
                        "action": "add_node",
                        "type": "text",
                        "label": "脚本",
                        "data": {"text": "产品登场"},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "action": "add_node",
                        "type": "imageGeneration",
                        "label": "主视觉",
                        "data": {"prompt": "cinematic product hero"},
                        "position": {"x": 400, "y": 100},
                    },
                ],
            },
            ensure_ascii=False,
        ),
    )

    conversation, canvas, message = agent.run_agent(
        email="agent@example.com",
        project_id=project.id,
        prompt="帮我搭建两个节点",
        conversation_id=None,
    )

    assert message == "已创建脚本和图片生成节点。"
    assert [node.type for node in canvas.nodes] == ["text", "imageGeneration"]
    assert len(conversation.messages) == 2
    assert store.get_project("agent@example.com", project.id).node_count == 2
    assert store.list_conversations("agent@example.com", project.id)[0].id == conversation.id


def test_agent_rejects_unknown_node_types(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project("agent@example.com", ProjectCreate(name="Agent test"))
    monkeypatch.setattr(
        agent,
        "_call_model",
        lambda _prompt, _parts: '{"message":"ignored","operations":[{"action":"add_node","type":"shell"}]}',
    )

    _, canvas, _ = agent.run_agent(
        email="agent@example.com",
        project_id=project.id,
        prompt="run a shell",
        conversation_id=None,
    )
    assert canvas.nodes == []


def test_agent_attaches_project_asset_bytes_to_multimodal_request(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project("agent@example.com", ProjectCreate(name="Agent test"))
    asset = store.safe_asset_path(store.assets_root("agent@example.com", project.id), "refs/brief.txt")
    asset.parent.mkdir(parents=True)
    asset.write_text("The product must stay cobalt blue.", encoding="utf-8")
    captured = {}

    def fake_model(prompt, parts):
        captured["prompt"] = prompt
        captured["parts"] = parts
        return '{"message":"understood","operations":[]}'

    monkeypatch.setattr(agent, "_call_model", fake_model)
    agent.run_agent(
        email="agent@example.com",
        project_id=project.id,
        prompt="Use the attached brief",
        conversation_id=None,
        asset_paths=["refs/brief.txt"],
    )

    assert '"inspection": "attached"' in captured["prompt"]
    assert len(captured["parts"]) == 1
    assert "cobalt blue" in captured["parts"][0].text
