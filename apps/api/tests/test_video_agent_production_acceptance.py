"""Hermetic multi-turn production acceptance: real routing, persistence and canvas.

Only the model/media/network boundary is stubbed. No live credentials, provider
requests, paid generation or customer-site downloads are permitted here.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from app.video_studio import agent, store
from app.video_studio.agent_context import validate_delivery
from app.video_studio.models import AgentMessage, ProjectCreate


EMAIL = "production-acceptance@example.com"
WEBSITE = "https://3wliners.com/"
PRODUCT = "https://3wliners.com/products/ford-bronco-custom-floor-mats"
BRIEF = "Fit For Your Wild · 泥沙防护与易清洁"
TIMELINE = "0–5秒 开场；5–11秒 贴合；11–17秒 防护；17–23秒 清洗；23–30秒 品牌"


def proposal():
    return {
        "message": f"3W Liners / Ford Bronco 2021–2026 四门款，30秒CTV方案：{BRIEF}。\n"
                   f"{TIMELINE}。\n产品声明待核验。确认后可以搭建文字节点；不会执行付费生成。",
        "operations": [],
        "storyboard": {"duration_seconds": 30, "shots": [
            {"duration_seconds": value} for value in [5, 6, 6, 6, 7]
        ]},
    }


@pytest.fixture
def production(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project(EMAIL, ProjectCreate(name="Production acceptance"))
    prompts, media = [], []
    current_reply = None
    calls = 0

    def model(prompt, _parts, **_kwargs):
        nonlocal calls
        prompts.append(prompt)
        calls += 1
        assert current_reply is not None, "Every model turn needs an explicit response"
        # Retry the same reply so genuine application-validation failures are
        # reported, rather than hidden by an exhausted sequence of stubs.
        reply = current_reply
        if isinstance(current_reply, list):
            reply = current_reply.pop(0) if len(current_reply) > 1 else current_reply[0]
        return json.dumps(reply, ensure_ascii=False)

    def assets(_email, _project, paths, **_kwargs):
        media.append(list(paths))
        assert not paths, "Historical attachments must not be analyzed automatically"
        return [], []

    monkeypatch.setattr(agent, "_call_model", model)
    monkeypatch.setattr(agent, "_asset_parts", assets)
    monkeypatch.setattr(agent, "execute_research_tool", lambda *a, **k: pytest.fail(
        "This production/chat flow must not search, download or generate media"))

    def turn(prompt, conversation_id=None, response=None):
        nonlocal current_reply
        current_reply = response or {"message": "继续当前已确认方案，不执行付费生成。", "operations": []}
        before = calls
        result = agent.run_agent(email=EMAIL, project_id=project.id, prompt=prompt,
                                 conversation_id=conversation_id)
        assert calls > before, "Supplied model reply was not consumed"
        reloaded = store.get_conversation(EMAIL, project.id, result[0].id)
        assert reloaded.run_status == "completed"
        return reloaded, result[1], result[2]

    return project, prompts, media, turn


def begin(production):
    _, _, _, turn = production
    conversation, _, _ = turn(
        f"给3W Liners客户{WEBSITE}做30秒CTV视频，商品{PRODUCT}，有什么方案？",
        response=proposal(),
    )
    return conversation


def test_ordinary_chat_followup_keeps_conversational_memory(production):
    _, prompts, _, turn = production
    first, _, _ = turn('我叫小王，今天想先聊聊', response={'message': '你好小王。', 'operations': []})
    turn('我叫什么名字？', first.id, response={'message': '你叫小王。', 'operations': []})
    assert '我叫小王' in prompts[-1]


def test_existing_brand_does_not_block_missing_advertising_rights_question():
    result = {'message': '请提供品牌授权，才能用于广告投放。', 'status': 'needs_input'}
    assert validate_delivery(result, 'proposal', {'website': WEBSITE, 'production_draft': {'content': BRIEF}}, []) == []


def test_echoing_approved_storyboard_does_not_force_a_second_confirmation(production):
    _, _, _, turn = production
    first = begin(production)
    approved, _, _ = turn('确认', first.id, response=proposal())
    continued, _, _ = turn('继续制作', approved.id)
    assert continued.task_state['brief_approved'] is True


def test_a_revised_storyboard_invalidates_previous_approval(production):
    _, _, _, turn = production
    first = begin(production)
    approved, _, _ = turn('确认', first.id)
    revised = proposal()
    revised['storyboard']['shots'][0]['description'] = 'Replace opening concept'
    updated, _, _ = turn('修改分镜，保留30秒', approved.id, response=revised)
    continued, _, _ = turn('继续制作', updated.id)
    assert continued.task_state['brief_approved'] is False


@pytest.mark.parametrize("approval", ["好的，我们开始制作吧", "确认"])
def test_proposal_approval_and_explicit_canvas_authorization_continue_existing_brief(production, approval):
    project, prompts, _, turn = production
    first = begin(production)
    approved, canvas, _ = turn(approval, first.id)
    assert PRODUCT in prompts[-1] and BRIEF in prompts[-1], "Follow-up lost customer/brief context"
    assert approved.task_state["brief_approved"] is True
    assert approved.task_state["duration_seconds"] == 30
    assert canvas.nodes == [], "Brief approval alone does not authorize canvas mutation or paid generation"

    final, canvas, _ = turn("立即在画布搭建30秒分镜制作工作流节点", approved.id, response={
        **proposal(),
        "message": f"已创建30秒脚本文字节点。{TIMELINE}。",
        "operations": [{"action": "add_node", "type": "text", "label": "30秒分镜",
                        "data": {"text": f"{BRIEF}\n{TIMELINE}"}, "position": {"x": 120, "y": 80}}],
    })
    assert PRODUCT in prompts[-1] and BRIEF in prompts[-1]
    assert [node.type for node in canvas.nodes] == ["text"]
    assert store.get_project(EMAIL, project.id).node_count == 1
    assert final.task_state["duration_seconds"] == 30


def test_independent_node_question_does_not_reanalyze_old_media_or_trigger_research(production):
    project, prompts, media, turn = production
    first = begin(production)
    first.messages.insert(0, AgentMessage(id="old-media", role="user",
        content="旧客户无毒产品调研", attachments=[{"path": "old-client.png"}]))
    first.research_history = [{"name": "web_search", "result": {"url": "https://old-client.test"}}]
    store.save_conversation(EMAIL, project.id, first)
    _, canvas, text = turn("不要修改画布，请解释文字节点的作用", first.id,
        response={"message": "文字节点保存脚本，不会自动生成图片或视频。", "operations": []})
    assert "文字节点保存脚本" in text
    assert canvas.nodes == []
    assert all(not paths for paths in media)
    assert "https://old-client.test" not in prompts[-1]
    assert "旧客户无毒" not in prompts[-1]


def test_approval_alone_does_not_authorize_model_suggested_generation_nodes(production):
    project, _, _, turn = production
    first = begin(production)
    conversation, canvas, _ = turn("确认", first.id, response={
        "message": "已记录方案确认，没有开始生成媒体。",
        "operations": [{"action": "add_node", "type": "videoGeneration", "label": "未经授权的生成",
                        "data": {"prompt": "generate now"}, "position": {"x": 0, "y": 0}}],
    })
    assert conversation.task_state["brief_approved"] is True
    assert canvas.nodes == []
    assert store.get_project(EMAIL, project.id).node_count == 0


def test_long_history_and_disk_reload_preserve_approved_product_and_brief(production):
    project, prompts, _, turn = production
    first = begin(production)
    approved, _, _ = turn("确认这个方案，可以开始制作", first.id)
    for index in range(25):
        approved.messages.extend([
            AgentMessage(id=f"u-{index}", role="user", content="说明一般制作流程"),
            AgentMessage(id=f"a-{index}", role="assistant", content="一般说明" * 1100),
        ])
    store.save_conversation(EMAIL, project.id, approved)
    reloaded, _, _ = turn("按刚才批准的方案继续制作", approved.id)
    assert reloaded.task_state["brief_approved"] is True
    assert reloaded.task_state["product_url"] == PRODUCT
    assert PRODUCT in prompts[-1] and BRIEF in prompts[-1], "Window trimming erased the approved brief"


@pytest.mark.parametrize("change", [
    "换个客户https://new-brand.test/，先给新方案", "改用https://3wliners.com/products/tesla-floor-mats，给新方案",
])
def test_changed_customer_or_product_cannot_reuse_previous_approval(production, change):
    _, _, _, turn = production
    first = begin(production)
    approved, _, _ = turn("确认这个方案", first.id)
    assert approved.task_state["brief_approved"] is True
    changed, canvas, _ = turn(change, approved.id,
        response={"message": "新商品方案待确认，尚未搭建节点。", "operations": []})
    assert changed.task_state["brief_approved"] is False
    assert canvas.nodes == []


@pytest.mark.parametrize("reply", ["不要确认，先修改", "这个方案确认了吗？", "我还没批准方案"])
def test_rejection_or_question_does_not_approve_pending_brief(production, reply):
    _, _, _, turn = production
    first = begin(production)
    conversation, canvas, _ = turn(reply, first.id,
        response={"message": "当前方案仍待您确认，没有执行制作。", "operations": []})
    assert conversation.task_state["brief_approved"] is False
    assert canvas.nodes == []


@pytest.mark.parametrize("extra", ["Ford Bronco 2021–2026 四门款。", "制作5秒开场镜头，其余镜头保持总片30秒。"])
def test_valid_storyboard_does_not_treat_years_or_single_shot_duration_as_whole_film(production, extra):
    _, _, _, turn = production
    first = begin(production)
    result = proposal()
    result["message"] = f"{extra}\n{TIMELINE}。"
    conversation, _, message = turn("请给我30秒分镜脚本", first.id, response=result)
    assert TIMELINE in message
    assert conversation.task_state["duration_seconds"] == 30


@pytest.mark.parametrize("timeline", [
    "0–5秒 开场；6–11秒 贴合；11–17秒 防护；17–23秒 清洗；23–30秒 品牌",
    "0–5秒 开场；4–11秒 贴合；11–17秒 防护；17–23秒 清洗；23–30秒 品牌",
    "0–5秒 开场；5–11秒 贴合；11–17秒 防护；17–23秒 清洗；23–29秒 品牌",
])
def test_broken_visible_timeline_remains_rejected(timeline):
    result = deepcopy(proposal())
    result["message"] = timeline
    assert validate_delivery(result, "storyboard", {"duration_seconds": 30}, [])


@pytest.mark.parametrize("duration", [0, -1, float("nan"), 6])
def test_invalid_or_wrong_total_structured_storyboard_remains_rejected(duration):
    result = deepcopy(proposal())
    result["storyboard"]["shots"][0]["duration_seconds"] = duration
    assert validate_delivery(result, "storyboard", {"duration_seconds": 30}, [])


def test_invalid_storyboard_never_commits_operations_and_persists_failed_turn(production):
    project, _, _, turn = production
    first = begin(production)
    broken = proposal()
    broken["storyboard"]["shots"][0]["duration_seconds"] = 9
    broken["operations"] = [{"action": "add_node", "type": "text", "label": "不应提交",
                             "data": {"text": "invalid"}, "position": {"x": 0, "y": 0}}]
    with pytest.raises(ValueError, match="时长|秒"):
        turn("立即在画布搭建30秒分镜制作工作流节点", first.id, response=broken)
    assert store.get_project(EMAIL, project.id).canvas.nodes == []
    saved = store.get_conversation(EMAIL, project.id, first.id)
    assert saved.run_status == "failed"
    assert saved.messages[-1].role == "user"


def test_continuation_repairs_repeated_intake_question_instead_of_delivering_it(production):
    _, prompts, _, turn = production
    first = begin(production)
    before = len(prompts)
    conversation, canvas, message = turn("好的，我们开始制作吧", first.id, response=[
        {"message": "请先告诉我品牌、产品官网链接以及希望的视频时长。", "operations": []},
        {"message": "继续3W Liners的Ford Bronco 30秒方案。下一步确认可使用的产品图片，再搭建分镜文字节点。", "operations": []},
    ])
    assert len(prompts) == before + 2, "Repeated known-brief questions must trigger a repair"
    assert "下一步" in message and "请先告诉我品牌" not in message
    assert conversation.task_state["brief_approved"] is True
    assert canvas.nodes == []


def test_continuation_model_prompt_has_one_non_chat_task_contract(production):
    _, prompts, _, turn = production
    first = begin(production)
    turn("确认", first.id)
    contracts = re.findall(r"Current task:\s*([^\n]+)", prompts[-1])
    assert len(contracts) == 1, "The model must receive one authoritative task"
    assert contracts[0].strip().rstrip(".") != "chat", "A production continuation must not be labelled ordinary chat"


@pytest.mark.parametrize("reply", ["Yes, let's start production.", "Confirmed, let's proceed!", "Okay, start production."])
def test_punctuated_english_approval_continues_known_brief(production, reply):
    _, prompts, _, turn = production
    first = begin(production)
    conversation, canvas, _ = turn(reply, first.id)
    assert PRODUCT in prompts[-1] and BRIEF in prompts[-1]
    assert conversation.task_state["brief_approved"] is True
    assert canvas.nodes == []


@pytest.mark.parametrize("reply", ["Do not confirm this plan.", "I have not approved the brief.", "Don't start production."])
def test_english_negation_never_approves_pending_brief(production, reply):
    _, _, _, turn = production
    first = begin(production)
    conversation, canvas, _ = turn(reply, first.id)
    assert conversation.task_state["brief_approved"] is False
    assert canvas.nodes == []


def test_english_seconds_year_range_and_aspect_ratio_do_not_corrupt_storyboard(production):
    _, _, _, turn = production
    first = begin(production)
    response = proposal()
    response["message"] = ("Ford Bronco 2021–2026; MP4, 16:9, 1920×1080, 30 FPS. "
        "30-second storyboard: 0–5s Hook; 5–11s Fit; 11–17s Protection; "
        "17–23s Cleaning; 23–30s Brand CTA.")
    conversation, _, text = turn("请给30秒分镜脚本", first.id, response=response)
    assert "23–30s Brand CTA" in text
    assert conversation.task_state["duration_seconds"] == 30
