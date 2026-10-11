import json
import threading
import time
import pytest
from app.video_studio import store,pi_agent,pi_http
from app.video_studio.pi_runs import RunJournal
from app.video_studio.models import ProjectCreate
from app.video_studio.agent_turns import prepare_turn
from test_video_legacy_api import client,headers
from test_video_pi_agent import reply,call

EMAIL='features@example.com'

def test_resource_revision_forget_and_user_isolation(tmp_path,monkeypatch):
    api=client(tmp_path,monkeypatch)
    p=store.create_project(EMAIL,ProjectCreate(name='Resources'))
    args={'directory':p.id,'resource':'memory','scope':'user'}
    initial=api.get('/video-legacy/api/agent/resources',params=args,headers=headers(EMAIL)).json()['data']
    saved=api.patch('/video-legacy/api/agent/resources',json={**args,'content':'Use English','expectedRevision':initial['revision']},headers=headers(EMAIL))
    assert saved.status_code==200
    stale=api.patch('/video-legacy/api/agent/resources',json={**args,'content':'Overwrite','expectedRevision':initial['revision']},headers=headers(EMAIL))
    assert stale.status_code==409
    denied=api.get('/video-legacy/api/agent/resources',params=args,headers=headers('stranger@example.com'))
    assert denied.status_code==404
    forgotten=api.patch('/video-legacy/api/agent/resources',json={**args,'content':'','enabled':False,'expectedRevision':saved.json()['data']['revision']},headers=headers(EMAIL))
    assert forgotten.json()['data']['content']=='' and forgotten.json()['data']['enabled'] is False

def test_event_replay_and_reload_retains_tool_cards_and_omits_canvas_replacement(tmp_path,monkeypatch):
    api=client(tmp_path,monkeypatch)
    p=store.create_project(EMAIL,ProjectCreate(name='Replay'))
    def model(payload,**kw):
        if any(m['role']=='toolResult' for m in payload['context']['messages']): return reply(payload,'Read canvas receipt.')
        return reply(payload,calls=[call('getCanvas',{})])
    monkeypatch.setattr(pi_agent,'model_response',model)
    response=api.post('/video-legacy/api/agent',json={'directory':p.id,'prompt':'Inspect canvas'},headers=headers(EMAIL))
    events=[json.loads(l) for l in response.text.splitlines()]
    assert [e['sequence'] for e in events]==list(range(1,len(events)+1))
    identity=events[0]
    replay=api.get('/video-legacy/api/agent/events',params={'directory':p.id,'sessionFile':identity['file'],'runId':identity['runId'],'after':2},headers=headers(EMAIL))
    replayed=[json.loads(l) for l in replay.text.splitlines()]
    assert all(e['sequence']>2 and e['type']!='canvasCall' for e in replayed)
    snapshot=api.get('/video-legacy/api/agent/get',params={'directory':p.id,'sessionFile':identity['file']},headers=headers(EMAIL)).json()['data']
    tools=[part['tool'] for part in snapshot['messages'][-1]['parts'] if part['type']=='tool']
    assert tools and tools[0]['status']=='success'
    assert snapshot['lastSequence']==events[-1]['sequence']
    assert snapshot['stats']['cost'] is None

def test_thinking_supported_configured_model_without_model_or_location_changes(tmp_path,monkeypatch):
    api=client(tmp_path,monkeypatch)
    p=store.create_project(EMAIL,ProjectCreate(name='Thinking'))
    seen=[]
    def model(payload,**kw):
        seen.append(payload)
        return reply(payload,'Configured thinking received.')
    monkeypatch.setattr(pi_agent,'model_response',model)
    response=api.post('/video-legacy/api/agent',json={'directory':p.id,'prompt':'Hello','thinkingLevel':'high'},headers=headers(EMAIL))
    assert response.status_code==200 and 'error' not in {json.loads(l)['type'] for l in response.text.splitlines()}
    assert seen[0]['reasoning']=='high'
    assert store.list_conversations(EMAIL,p.id)[0].thinking_level=='high'
    rejected=api.post('/video-legacy/api/agent',json={'directory':p.id,'prompt':'Hello','thinkingLevel':'invented'},headers=headers(EMAIL))
    assert rejected.status_code==400

def test_child_journals_do_not_alias_parent_run_identity(tmp_path,monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR',str(tmp_path))
    p=store.create_project(EMAIL,ProjectCreate(name='Child'))
    c=prepare_turn(email=EMAIL,project_id=p.id,prompt='Parent',conversation_id=None)
    parent=RunJournal(EMAIL,p.id,c.id,c.run_id)
    child=RunJournal(EMAIL,p.id,'a'*32,c.run_id)
    parent.create();child.create()
    parent.emit({'type':'text','blockId':'parent','delta':'parent'})
    child.emit({'type':'text','blockId':'child','delta':'child'})
    assert parent.events()[0]['blockId']=='parent' and child.events()[0]['blockId']=='child'

def test_python_model_deltas_are_observed_before_transport_returns(tmp_path,monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR',str(tmp_path))
    p=store.create_project(EMAIL,ProjectCreate(name='Live deltas'))
    c=prepare_turn(email=EMAIL,project_id=p.id,prompt='Hello',conversation_id=None)
    journal=RunJournal(EMAIL,p.id,c.id,c.run_id);journal.create()
    observed=threading.Event()
    def progress(event):
        journal.emit(event)
        if event['type']=='text' and event.get('delta')=='Hello': observed.set()
    def model(payload,emit=None,**kw):
        emit({'type':'text_delta','delta':'Hello'})
        assert observed.wait(3), 'HTTP events must not wait for model completion'
        return reply(payload,'Hello world')
    monkeypatch.setattr(pi_agent,'model_response',model)
    result=pi_agent.run_agent(email=EMAIL,project_id=p.id,prompt='Hello',conversation_id=c.id,
        prepared_conversation=c,journal=journal,progress=progress)
    assert result[2]=='Hello world'

def test_modern_api_control_answer_and_replay_keep_conversation_scope(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers.video_studio import router
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR',str(tmp_path))
    app=FastAPI();app.include_router(router)
    api=TestClient(app)
    p=store.create_project(EMAIL,ProjectCreate(name='Modern controls'))
    c=prepare_turn(email=EMAIL,project_id=p.id,prompt='Pending task',conversation_id=None)
    journal=RunJournal(EMAIL,p.id,c.id,c.run_id);journal.create()
    base=f'/video-studio/projects/{p.id}'
    # POST on an active session delegates to Pi without duplicating canonical users.
    sent=api.post(base+'/agent',json={'prompt':'Keep this direction','conversation_id':c.id,'streaming_behavior':'followUp'},headers=headers(EMAIL))
    assert sent.status_code==200
    assert journal.commands(0)[0]['type']=='followUp'
    assert len(store.get_conversation(EMAIL,p.id,c.id).messages)==1
    scoped=base+f'/conversations/{c.id}'
    wrong=api.post(scoped+'/control',json={'run_id':'0'*32,'action':'steer','prompt':'Wrong run'},headers=headers(EMAIL))
    assert wrong.status_code==400
    call_id=journal.question('modern-q',{'title':'Question','question':'Which direction?','options':['A','B']})
    denied=api.post(scoped+'/answer',json={'callId':call_id,'answer':'A'},headers=headers('other@example.com'))
    assert denied.status_code==404
    answer=api.post(scoped+'/answer',json={'callId':call_id,'answer':'A'},headers=headers(EMAIL))
    assert answer.status_code==200 and answer.json()['answer']=='A'
    duplicate=api.post(scoped+'/answer',json={'callId':call_id,'answer':'B'},headers=headers(EMAIL))
    assert duplicate.status_code==400
    journal.emit({'type':'done'});journal.finish('completed')
    replay=api.get(scoped+'/events',params={'run_id':c.run_id,'after':0},headers=headers(EMAIL))
    assert replay.status_code==200
    assert [json.loads(line)['sequence'] for line in replay.text.splitlines()]==[1,2]

def test_direct_child_turn_uses_its_own_controls_and_cancel_after_parent_completes(tmp_path,monkeypatch):
    from app.video_studio.models import AgentConversation
    from app.video_studio.agent_turns import TurnControl
    api=client(tmp_path,monkeypatch)
    p=store.create_project(EMAIL,ProjectCreate(name='Direct child control'))
    parent=prepare_turn(email=EMAIL,project_id=p.id,prompt='Delegate',conversation_id=None)
    TurnControl(EMAIL,p.id,parent).finish('completed')
    child=AgentConversation(id='d'*32,name='Child',parent_file=f'agent/{parent.id}.json')
    store.save_conversation(EMAIL,p.id,child)
    child=prepare_turn(email=EMAIL,project_id=p.id,prompt='Continue child directly',conversation_id=child.id)
    journal=RunJournal(EMAIL,p.id,child.id,child.run_id);journal.create()
    scope={'directory':p.id,'sessionFile':f'agent/{child.id}.json','runId':child.run_id}
    controlled=api.post('/video-legacy/api/agent/control',json={**scope,'action':'steer','prompt':'Keep it short'},headers=headers(EMAIL))
    assert controlled.status_code==200, controlled.json()
    assert journal.commands(0)[0]['prompt']=='Keep it short'
    assert 'childFile' not in journal.commands(0)[0]
    cancelled=api.post('/video-legacy/api/agent/cancel',json=scope,headers=headers(EMAIL))
    assert cancelled.status_code==200
    assert store.get_conversation(EMAIL,p.id,child.id).run_status=='cancelled'
    assert store.get_conversation(EMAIL,p.id,parent.id).run_status=='completed'

def test_reloaded_parent_projects_latest_child_report_without_rewriting_sdk_context(tmp_path,monkeypatch):
    from app.video_studio.models import AgentConversation,AgentMessage
    from app.video_studio.agent_turns import TurnControl
    api=client(tmp_path,monkeypatch)
    p=store.create_project(EMAIL,ProjectCreate(name='Child report replay'))
    parent=prepare_turn(email=EMAIL,project_id=p.id,prompt='Delegate',conversation_id=None)
    TurnControl(EMAIL,p.id,parent).finish('completed')
    journal=RunJournal(EMAIL,p.id,parent.id,parent.run_id);journal.create()
    child=AgentConversation(id='e'*32,name='Writer',parent_file=f'agent/{parent.id}.json',
        run_status='completed',messages=[AgentMessage(id='child-reply',role='assistant',content='Human revised child result.')])
    store.save_conversation(EMAIL,p.id,child)
    journal.emit({'type':'subAgent','agent':{'file':f'agent/{child.id}.json','name':'Writer','status':'running'}})
    journal.finish('completed')
    snapshot=api.get('/video-legacy/api/agent/get',params={'directory':p.id,'sessionFile':f'agent/{parent.id}.json'},headers=headers(EMAIL)).json()['data']
    assert snapshot['subAgents'][0]['status']=='completed'
    reports=[m for m in snapshot['messages'] if m.get('report')]
    assert len(reports)==1 and reports[0]['content']=='Human revised child result.'
    assert len(store.get_conversation(EMAIL,p.id,parent.id).messages)==1
