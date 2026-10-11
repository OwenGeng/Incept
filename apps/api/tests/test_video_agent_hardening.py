from __future__ import annotations

import json
import threading

import pytest

from app.video_studio import agent, store
from app.video_studio.models import ProjectCreate, VideoNode, Position, AgentConversation, AgentMessage, CanvasDocument

EMAIL = 'hardening@example.com'


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    return store.create_project(EMAIL, ProjectCreate(name='Agent hardening'))


def reply(monkeypatch, content='已收到你的要求。'):
    monkeypatch.setattr(agent, '_call_model', lambda *args, **kwargs: json.dumps({'message': content, 'operations': []}))


def test_website_ctv_proposal_does_not_trigger_research_without_request():
    assert not agent._research_intent('我想给https://3wliners.com/客户做ctv的素材，帮我出一个方案')
    assert agent._research_intent('调研https://3wliners.com/品牌')
    assert not agent._research_intent('方向1没问题，我问你能从客户的网页上自动抓取素材吗')


def test_prompt_budget_keeps_latest_request_and_newest_tool_result():
    conversation = AgentConversation(id='a'*32, name='Budget',
        messages=[AgentMessage(id=f'{index:032x}', role='user', content='旧备注'*2000) for index in range(12)],
        task_state={'duration_seconds':30, 'constraints':'旧约束'*20000})
    prompt = agent._agent_prompt(user_prompt='当前请求'+('需'*19990), canvas=CanvasDocument(),
        conversation=conversation, language='zh', custom_system_prompt='\\"'*10000,
        agent_id='default', skills=[{'content':'旧技能'*20000}],
        asset_manifest=[{'path':'素材'*20000}], allowed_node_types={'text'}, allow_canvas_edits=False,
        research_tools=[{'description':'工具'*20000}],
        tool_history=[{'result':'旧结果'*20000}, {'result':'NEWEST_EVIDENCE'}])
    assert len(prompt) < 160_000
    assert '当前请求' in prompt
    assert 'NEWEST_EVIDENCE' in prompt
    assert 'duration_seconds' in prompt


def test_attachment_is_persisted_but_not_reused_without_current_selection(project, monkeypatch):
    path = store.safe_asset_path(store.assets_root(EMAIL, project.id), 'brief.txt')
    path.write_text('cobalt blue product', encoding='utf-8')
    reply(monkeypatch)
    conv, _, _ = agent.run_agent(email=EMAIL, project_id=project.id, prompt='请看附件', conversation_id=None, asset_paths=['brief.txt'])
    assert conv.messages[0].attachments[0]['path'] == 'brief.txt'
    seen = {}
    def model(prompt, parts, **kwargs):
        seen['parts'] = parts
        return '{"message":"颜色保持蓝色。","operations":[]}'
    monkeypatch.setattr(agent, '_call_model', model)
    agent.run_agent(email=EMAIL, project_id=project.id, prompt='保持这个颜色', conversation_id=conv.id)
    assert not seen['parts']
    agent.run_agent(email=EMAIL, project_id=project.id, prompt='保持这个颜色', conversation_id=conv.id, asset_paths=['brief.txt'])
    assert any('cobalt blue' in (part.text or '') for part in seen['parts'])


def test_edit_resend_truncates_old_branch_and_keeps_one_user_turn(project, monkeypatch):
    reply(monkeypatch)
    conv, _, _ = agent.run_agent(email=EMAIL, project_id=project.id, prompt='15秒版本', conversation_id=None)
    original = conv.messages[0].id
    conv, _, _ = agent.run_agent(email=EMAIL, project_id=project.id, prompt='30秒版本', conversation_id=conv.id, resend_from=original)
    assert [item.content for item in conv.messages if item.role == 'user'] == ['30秒版本']
    assert conv.task_state['duration_seconds'] == 30


def test_confirmed_choices_survive_long_history(project, monkeypatch):
    reply(monkeypatch)
    conv, _, _ = agent.run_agent(email=EMAIL, project_id=project.id, prompt='30秒，https://3wliners.com/products/model-y-juniper 方向1没问题', conversation_id=None)
    for index in range(15):
        conv, _, _ = agent.run_agent(email=EMAIL, project_id=project.id, prompt=f'补充备注 {index}', conversation_id=conv.id)
    assert conv.task_state['duration_seconds'] == 30
    assert conv.task_state['approved_direction'] == 1
    assert conv.task_state['product_url'] == 'https://3wliners.com/products/model-y-juniper'


def test_concurrent_canvas_edit_is_not_overwritten(project, monkeypatch):
    def model(*args, **kwargs):
        latest = store.get_project(EMAIL, project.id).canvas
        latest.nodes.append(VideoNode(id='human', type='text', position=Position(x=0,y=0), data={'text':'human edit'}))
        store.save_canvas(EMAIL, project.id, latest)
        return '{"message":"添加节点。","operations":[{"action":"add_node","type":"text"}]}'
    monkeypatch.setattr(agent, '_call_model', model)
    with pytest.raises(ValueError, match='画布.*修改|canvas.*changed'):
        agent.run_agent(email=EMAIL, project_id=project.id, prompt='添加节点', conversation_id=None)
    assert [node.id for node in store.get_project(EMAIL, project.id).canvas.nodes] == ['human']


def test_cancellation_after_model_prevents_canvas_and_assistant_write(project, monkeypatch):
    cancel = threading.Event()
    def model(*args, **kwargs):
        cancel.set()
        return '{"message":"已添加节点。","operations":[{"action":"add_node","type":"text"}]}'
    monkeypatch.setattr(agent, '_call_model', model)
    with pytest.raises(ValueError, match='取消'):
        agent.run_agent(email=EMAIL, project_id=project.id, prompt='添加节点', conversation_id=None, cancel_event=cancel)
    assert store.get_project(EMAIL, project.id).canvas.nodes == []
    conv = store.list_conversations(EMAIL, project.id)[0]
    assert len(conv.messages) == 1
    assert conv.run_status == 'cancelled'


def test_add_node_aliases_can_be_connected_in_same_response():
    from app.video_studio.models import CanvasDocument
    canvas = agent._apply_operations(CanvasDocument(), [
        {'action':'add_node','id':'script','type':'text'},
        {'action':'add_node','id':'image','type':'image'},
        {'action':'connect','source':'script','target':'image'},
    ])
    assert len(canvas.edges) == 1
    assert canvas.edges[0].source == canvas.nodes[0].id


def test_thirty_second_storyboard_cannot_deliver_twenty_two_seconds(project, monkeypatch):
    monkeypatch.setattr(agent, '_call_model', lambda *args, **kwargs: json.dumps({
        'message':'30秒方案：0–4秒 产品亮相；4–22秒 CTA。', 'operations':[],
        'storyboard': {'duration_seconds':30, 'shots':[{'duration_seconds':4},{'duration_seconds':18}]},
    }))
    with pytest.raises(ValueError, match='时长|duration'):
        agent.run_agent(email=EMAIL, project_id=project.id, prompt='写30秒分镜脚本', conversation_id=None)
