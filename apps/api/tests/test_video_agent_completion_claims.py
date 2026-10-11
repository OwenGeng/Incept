from __future__ import annotations

import json

import pytest

from app.video_studio import agent, store
from app.video_studio.models import ProjectCreate

EMAIL = "completion@linglonglab.internal"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    return store.create_project(EMAIL, ProjectCreate(name="Completion claims"))


@pytest.mark.parametrize("prompt,message", [
    ("请导入客户素材", "未成功导入素材，客户网站需要登录，请提供图片文件。"),
    ("请导入客户素材", "没成功导入素材，客户网站需要登录，请提供图片文件。"),
    ("请导入客户素材", "尚未成功下载素材，客户网站需要登录，请提供图片文件。"),
    ("请导入客户素材", "Assets have not been imported; website requires login. Please provide customer images."),
    ("请添加图片节点", "未成功添加图片节点，画布工具不可用，请确认配置。"),
    ("请添加图片节点", "画布尚未完成，缺少客户图片文件，请提供素材。"),
    ("请添加图片节点", "画布没完成，缺少客户图片文件，请提供素材。"),
])
def test_blocked_negative_action_is_delivered_not_misread_as_completed(project, monkeypatch, prompt, message):
    monkeypatch.setattr(agent, "_call_model", lambda *args, **kwargs: json.dumps({
        "message": message, "status": "blocked", "operations": [], "tool_calls": [],
    }))
    conversation, canvas, delivered = agent.run_agent(email=EMAIL, project_id=project.id,
        prompt=prompt, conversation_id=None)
    assert delivered == message
    assert conversation.messages[-1].content == message
    assert canvas.nodes == []


@pytest.mark.parametrize("prompt,message", [
    ("请导入客户素材", "已成功导入客户图片，素材库中可以预览。"),
    ("请导入客户素材", "未下载视频；已成功导入客户图片，素材库中可以预览。"),
    ("请添加图片节点", "已成功添加图片节点，画布制作完成。"),
])
def test_positive_completion_still_requires_real_action(project, monkeypatch, prompt, message):
    monkeypatch.setattr(agent, "_call_model", lambda *args, **kwargs: json.dumps({
        "message": message, "status": "complete", "operations": [], "tool_calls": [],
    }))
    with pytest.raises(ValueError, match="没有成功|没有有效"):
        agent.run_agent(email=EMAIL, project_id=project.id, prompt=prompt, conversation_id=None)


def test_positive_canvas_completion_with_effective_operation_is_delivered(project, monkeypatch):
    monkeypatch.setattr(agent, "_call_model", lambda *args, **kwargs: json.dumps({
        "message": "已成功添加图片节点。", "status": "complete", "tool_calls": [],
        "operations": [{"action": "add_node", "type": "image"}],
    }))
    _, canvas, message = agent.run_agent(email=EMAIL, project_id=project.id,
        prompt="请添加图片节点", conversation_id=None)
    assert len(canvas.nodes) == 1
    assert message == "已成功添加图片节点。"


def test_preliminary_ctv_proposal_survives_one_unverified_safety_claim(project, monkeypatch):
    monkeypatch.setattr(agent, '_call_model', lambda *args, **kwargs: json.dumps({
        'message':'方向一：防泥沙保护。\n产品无毒、无甲醛。\n方向二：快速清洗。',
        'status':'complete', 'research':{'status':'complete'}, 'operations':[], 'tool_calls':[],
    }))
    conversation, _, delivered = agent.run_agent(email=EMAIL, project_id=project.id,
        prompt='给我几个CTV视频方案，无需调研竞品。', conversation_id=None)
    assert '方向一：防泥沙保护。' in delivered
    assert '方向二：快速清洗。' in delivered
    assert '待核验' in delivered or 'Unverified claim' in delivered
    assert 'Agent 未交付' not in delivered
    assert conversation.messages[-1].content == delivered
