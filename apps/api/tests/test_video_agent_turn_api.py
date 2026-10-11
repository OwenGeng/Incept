from __future__ import annotations

import json

from app.video_studio import pi_agent as agent, store
from test_video_pi_agent import reply, call
from app.video_studio.models import ProjectCreate
from test_video_legacy_api import client, headers

EMAIL = 'turn-api@example.com'


def canvas_model(payload, **kwargs):
    if any(m['role'] == 'toolResult' for m in payload['context']['messages']):
        return reply(payload, '已添加脚本节点。')
    return reply(payload, calls=[call('addNode', {'type':'textNode','position':{'x':100,'y':100}})])


def events(response):
    return [json.loads(line) for line in response.text.splitlines()]


def test_cancel_without_run_identity_is_rejected(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    project = store.create_project(EMAIL, ProjectCreate(name='Cancel identity'))
    response = api.post('/video-legacy/api/agent/cancel', headers=headers(EMAIL),
        json={'directory':project.id, 'sessionFile':'conversation-'+'a'*32+'.json'})
    assert response.status_code == 400


def test_failed_turn_has_early_session_and_identical_stored_user_id(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    project = store.create_project(EMAIL, ProjectCreate(name='Turn API'))
    monkeypatch.setattr(agent, 'model_response', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('模型暂时不可用')))
    response = api.post('/video-legacy/api/agent', headers=headers(EMAIL), json={'directory':project.id,'prompt':'请帮我回答'})
    received = events(response)
    assert received[0]['type'] == 'session'
    assert received[1]['type'] == 'userMessage'
    conv = store.list_conversations(EMAIL, project.id)[0]
    assert received[1]['id'] == conv.messages[0].id
    assert conv.run_status == 'failed'
    assert any(item['type'] == 'error' for item in received)


def test_failed_turn_retry_branches_and_reload_keeps_attachments(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    project = store.create_project(EMAIL, ProjectCreate(name='Retry API'))
    store.safe_asset_path(store.assets_root(EMAIL,project.id), 'brief.txt').write_text('blue product')
    monkeypatch.setattr(agent, 'model_response', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('模型暂时不可用')))
    first = events(api.post('/video-legacy/api/agent', headers=headers(EMAIL), json={'directory':project.id,'attachments':[{'path':'brief.txt'}]}))
    monkeypatch.setattr(agent, 'model_response', lambda p, **k: reply(p, '附件是蓝色产品简报。'))
    retry = events(api.post('/video-legacy/api/agent', headers=headers(EMAIL), json={'directory':project.id, 'sessionFile':first[0]['file'], 'resendFrom':first[1]['id'], 'prompt':'请分析简报','attachments':[{'path':'brief.txt'}]}))
    assert retry[-1]['type'] == 'done'
    loaded = api.get('/video-legacy/api/agent/get', headers=headers(EMAIL), params={'directory':project.id,'sessionFile':first[0]['file']})
    assert loaded.status_code == 200
    messages = loaded.json()['data']['messages']
    assert len(messages) == 2
    assert messages[0]['attachments'][0]['path'] == 'brief.txt'
    assert messages[0]['entryId'] == retry[1]['id']
    assert messages[1]['replyTo'] == retry[1]['id']


def test_named_workspace_canvas_is_targeted_not_active_backend_canvas(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    project = store.create_project(EMAIL, ProjectCreate(name='Named canvas'))
    path = store.safe_asset_path(store.assets_root(EMAIL, project.id), '客户方案.json')
    path.write_text(json.dumps({'linglonglabVideoCanvas':True,'nodes':[],'edges':[],'viewport':{'x':0,'y':0,'zoom':1}}))
    monkeypatch.setattr(agent, 'model_response', canvas_model)
    result = events(api.post('/video-legacy/api/agent', headers=headers(EMAIL), json={'directory':project.id,'prompt':'添加节点','canvas':{'id':'客户方案.json'}}))
    assert any(event['type']=='canvasCall' for event in result)
    assert len(json.loads(path.read_text())['nodes']) == 1
    assert store.get_project(EMAIL, project.id).canvas.nodes == []


def test_named_canvas_changed_during_model_is_preserved(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    project = store.create_project(EMAIL, ProjectCreate(name='Concurrent canvas'))
    path = store.safe_asset_path(store.assets_root(EMAIL, project.id), '客户方案.json')
    original = {'linglonglabVideoCanvas':True,'nodes':[],'edges':[]}
    path.write_text(json.dumps(original))
    def model(payload, **kwargs):
        path.write_text(json.dumps({**original,'nodes':[{'id':'human','type':'remote-textNode','data':{},'position':{'x':0,'y':0}}]}))
        return canvas_model(payload)
    monkeypatch.setattr(agent, 'model_response', model)
    result = events(api.post('/video-legacy/api/agent', headers=headers(EMAIL), json={'directory':project.id,'prompt':'添加节点','canvas':{'id':'客户方案.json'}}))
    assert any(event['type']=='error' for event in result)
    assert not any(event['type']=='canvasCall' for event in result)
    assert [node['id'] for node in json.loads(path.read_text())['nodes']] == ['human']
