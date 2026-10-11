import json

import pytest

from app.video_studio import agent, store
from app.video_studio.agent_turns import AgentBusy, TurnControl, prepare_turn, cancel_turn
from app.video_studio.models import AgentConversation, AgentMessage, ProjectCreate

EMAIL = 'boundary@example.com'


def test_read_only_node_question_never_applies_model_operations(project, monkeypatch):
    initial = store.get_project(EMAIL, project.id).canvas.model_copy(deep=True)
    monkeypatch.setattr(agent, '_call_model', lambda *args, **kwargs: json.dumps({
        'message':'文字节点用来保存和编辑文案。',
        'operations':[{'action':'add_node', 'type':'text', 'id':'unrequested', 'label':'unexpected'}]}))
    agent.run_agent(email=EMAIL, project_id=project.id, prompt='不要修改画布，请解释节点的作用', conversation_id=None)
    assert store.get_project(EMAIL, project.id).canvas == initial


@pytest.mark.parametrize('prompt,result', [
    ('继续完善30秒分镜方案', {'message':'0–5秒 开场；5–30秒 产品展示与收尾。', 'operations':[],
        'storyboard':{'duration_seconds':30, 'shots':[{'duration_seconds':5}, {'duration_seconds':25}]}}),
    ('继续添加文字节点', {'message':'已添加文字节点。',
        'operations':[{'action':'add_node', 'type':'text'}]}),
])
def test_production_followup_does_not_restart_historical_research(project, monkeypatch, prompt, result):
    conversation = store.save_conversation(EMAIL, project.id, AgentConversation(id='a'*32, name='Production', messages=[
        AgentMessage(id='b'*32, role='user', content='调研https://brand.test/，30秒'),
        AgentMessage(id='c'*32, role='assistant', content='已有初步调研结果。')]))
    monkeypatch.setattr(agent, '_call_model', lambda *args, **kwargs: json.dumps(result))
    _, _, message = agent.run_agent(email=EMAIL, project_id=project.id,
        prompt=prompt, conversation_id=conversation.id)
    assert result['message'] in message


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    return store.create_project(EMAIL, ProjectCreate(name='Boundary tests'))


def test_provider_exception_body_is_not_persisted_or_exposed(project, monkeypatch):
    monkeypatch.setattr(agent, '_call_model', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('provider trace api_key=secret-value')))
    with pytest.raises(RuntimeError):
        agent.run_agent(email=EMAIL, project_id=project.id, prompt='解释文字节点', conversation_id=None)
    conv = store.list_conversations(EMAIL, project.id)[0]
    assert 'secret-value' not in (conv.run_error or '')


def test_running_turn_rejects_duplicate_and_stale_cancel_cannot_stop_retry(project):
    first = prepare_turn(email=EMAIL, project_id=project.id, prompt='first', conversation_id=None)
    with pytest.raises(AgentBusy):
        prepare_turn(email=EMAIL, project_id=project.id, prompt='duplicate', conversation_id=first.id)
    cancel_turn(EMAIL, project.id, first.id, first.run_id)
    retry = prepare_turn(email=EMAIL, project_id=project.id, prompt='retry', conversation_id=first.id, resend_from=first.messages[0].id)
    cancel_turn(EMAIL, project.id, retry.id, first.run_id)
    TurnControl(EMAIL, project.id, retry).check()


def test_no_website_download_without_import_request(project, monkeypatch):
    calls = []
    responses = iter([
        {'message':'下载','tool_calls':[{'name':'website_assets_import','arguments':{'asset_ids':['a'*32]}}]},
        {'message':'未下载素材；请确认需要导入的官网素材。','operations':[]},
    ])
    monkeypatch.setattr(agent, '_call_model', lambda *a, **kw:json.dumps(next(responses)))
    monkeypatch.setattr(agent, 'execute_research_tool', lambda *a, **kw:calls.append(a[0]) or {})
    _, _, message = agent.run_agent(email=EMAIL, project_id=project.id, prompt='解释文字节点', conversation_id=None)
    assert calls == []
    assert '未下载' in message


def test_explicit_no_download_never_enables_import_tool(project, monkeypatch):
    calls = []
    responses = iter([
        {'tool_calls':[{'name':'website_assets_import','arguments':{'asset_ids':['a'*32]}}]},
        {'message':'没有下载；可以手动将客户素材添加到输入框。','operations':[]},
    ])
    monkeypatch.setattr(agent, '_call_model', lambda *args, **kwargs: json.dumps(next(responses)))
    monkeypatch.setattr(agent, 'execute_research_tool', lambda *args, **kwargs: calls.append(args[0]) or {})
    agent.run_agent(email=EMAIL, project_id=project.id, prompt='不要下载客户图片', conversation_id=None)
    assert calls == []


def test_cancelled_turn_does_not_save_after_provider_call(project, monkeypatch):
    prepared = prepare_turn(email=EMAIL, project_id=project.id, prompt='请解释', conversation_id=None)
    def model(*args, **kwargs):
        cancel_turn(EMAIL, project.id, prepared.id, prepared.run_id)
        return '{"message":"说明","operations":[]}'
    monkeypatch.setattr(agent, '_call_model', model)
    with pytest.raises(ValueError, match='取消'):
        agent.run_agent(email=EMAIL, project_id=project.id, prompt='请解释', conversation_id=prepared.id, prepared_conversation=prepared)
    assert len(store.get_conversation(EMAIL, project.id, prepared.id).messages) == 1


def test_website_download_cancelled_mid_stream_is_not_imported(project, monkeypatch):
    import httpx
    from app.video_studio import website_assets
    from test_video_website_assets import public_dns as resolver
    prepared = prepare_turn(email=EMAIL, project_id=project.id, prompt='导入图片', conversation_id=None)
    control = TurnControl(EMAIL, project.id, prepared)
    html = '<img src="https://public.test/product.png" alt="Product">'
    asset_client = httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200, headers={'content-type':'text/html'}, text=html)))
    found = website_assets.discover_website_assets(EMAIL, project.id, 'https://public.test/', client=asset_client, resolver=resolver)
    class CancelledStream(httpx.SyncByteStream):
        def __iter__(self):
            cancel_turn(EMAIL, project.id, prepared.id, prepared.run_id)
            yield b'\x89PNG\r\n\x1a\n' + b'payload'
    download_client = httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200, stream=CancelledStream())))
    with pytest.raises(ValueError, match='取消'):
        website_assets.import_website_assets(EMAIL, project.id, [found['assets'][0]['id']], client=download_client,
            resolver=resolver, check_cancel=control.check, mutation_lock=control.mutation)
    assets = website_assets.list_website_assets(EMAIL, project.id)
    assert assets[0]['status'] == 'discovered'
    assert not list(store.assets_root(EMAIL, project.id).rglob('*.png'))


def test_model_cannot_claim_import_without_successful_tool_result(project, monkeypatch):
    monkeypatch.setattr(agent, '_call_model', lambda *a, **kw:'{"message":"已经导入客户商品图片。","operations":[]}')
    with pytest.raises(ValueError, match='导入|import'):
        agent.run_agent(email=EMAIL, project_id=project.id, prompt='导入客户商品图片', conversation_id=None)


def test_model_cannot_claim_canvas_changes_without_effective_operations(project, monkeypatch):
    monkeypatch.setattr(agent, '_call_model', lambda *a, **kw:'{"message":"已经添加所需节点，画布搭建完成。","operations":[]}')
    with pytest.raises(ValueError, match='画布|canvas'):
        agent.run_agent(email=EMAIL, project_id=project.id, prompt='添加节点', conversation_id=None)


def test_current_reattached_asset_is_not_displaced_by_older_uploads(project, monkeypatch):
    for index in range(21):
        store.safe_asset_path(store.assets_root(EMAIL, project.id), f'brief{index}.txt').write_text(f'asset {index}')
    monkeypatch.setattr(agent, '_call_model', lambda *a, **kw:'{"message":"了解。","operations":[]}')
    conv, _, _ = agent.run_agent(email=EMAIL, project_id=project.id, prompt='附件', conversation_id=None,
        asset_paths=[f'brief{i}.txt' for i in range(20)])
    captured = {}
    def model(prompt, parts, **kwargs):
        captured['parts'] = parts
        return '{"message":"了解。","operations":[]}'
    monkeypatch.setattr(agent, '_call_model', model)
    agent.run_agent(email=EMAIL, project_id=project.id, prompt='本轮只看第一个和新附件', conversation_id=conv.id, asset_paths=['brief0.txt','brief20.txt'])
    assert 'brief0.txt' in captured['parts'][0].text
    assert 'brief20.txt' in captured['parts'][1].text
