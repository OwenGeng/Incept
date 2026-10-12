"""Direct child reports survive refresh without rewriting the parent's SDK context."""
import copy
import json

import pytest

from app.video_studio import pi_agent, store
from app.video_studio.agent_turns import TurnControl, prepare_turn
from app.video_studio.models import AgentConversation, ProjectCreate
from app.video_studio.pi_runs import RunJournal
from test_video_legacy_api import client, headers

EMAIL = 'native-reports@example.com'


@pytest.fixture
def reports(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    project = store.create_project(EMAIL, ProjectCreate(name='Direct child reports'))
    parent = prepare_turn(email=EMAIL, project_id=project.id, prompt='Delegate', conversation_id=None)
    TurnControl(EMAIL, project.id, parent).finish('completed')
    child = AgentConversation(id='e' * 32, name='Writer', parent_file=f'agent/{parent.id}.json', run_status='completed')
    store.save_conversation(EMAIL, project.id, child)
    journal = RunJournal(EMAIL, project.id, parent.id, parent.run_id)
    journal.create()
    journal.emit({'type': 'subAgent', 'agent': {'file': f'agent/{child.id}.json', 'name': 'Writer', 'status': 'running'}})
    journal.finish('completed')
    payload = {'name': 'nativeParentReport', 'id': 'call-report', 'conversationFile': f'agent/{child.id}.json',
        'arguments': {'id': 'explicit-child-report', 'file': f'agent/{child.id}.json',
            'parentFile': child.parent_file, 'name': child.name, 'content': 'Explicit progress before final completion.'}}
    return api, project, parent, child, payload


def test_direct_child_explicit_report_persists_deduplicates_and_reloads(reports):
    api, project, parent, child, payload = reports
    original = store.get_conversation(EMAIL, project.id, parent.id).model_dump()
    assert pi_agent._parent_report(EMAIL, project.id, child, payload) == {'id': 'explicit-child-report'}
    assert pi_agent._parent_report(EMAIL, project.id, child, payload) == {'id': 'explicit-child-report'}
    metadata = store._read_json(store._project_root(EMAIL, project.id) / '.agent/children' / f'{child.id}.json', {})
    assert len(metadata['reports']) == 1
    for _ in range(2):
        response = api.get('/video-legacy/api/agent/get', params={'directory': project.id,
            'sessionFile': f'agent/{parent.id}.json'}, headers=headers(EMAIL))
        assert response.status_code == 200, response.text
        projected = [m for m in response.json()['data']['messages'] if m.get('report')]
        assert len(projected) == 1
        assert projected[0]['content'] == payload['arguments']['content']
        assert projected[0]['id'] == payload['arguments']['id']
    assert store.get_conversation(EMAIL, project.id, parent.id).model_dump() == original


@pytest.mark.parametrize('field,value', [('file', 'agent/' + 'a' * 32 + '.json'),
    ('parentFile', 'agent/' + 'b' * 32 + '.json'), ('id', '../report'),
    ('name', ''), ('content', '文' * 22000)])
def test_report_validates_scope_identity_and_utf8_size(reports, field, value):
    _, project, _, child, payload = reports
    payload['arguments'][field] = value
    with pytest.raises(ValueError):
        pi_agent._parent_report(EMAIL, project.id, child, payload)
    path = store._project_root(EMAIL, project.id) / '.agent/children' / f'{child.id}.json'
    assert not store._read_json(path, {}).get('reports')


def test_report_id_cannot_be_rebound_or_submitted_from_other_conversation(reports):
    _, project, parent, child, payload = reports
    pi_agent._parent_report(EMAIL, project.id, child, payload)
    changed = copy.deepcopy(payload)
    changed['arguments']['content'] = 'Rebound content'
    with pytest.raises(ValueError, match='different content'):
        pi_agent._parent_report(EMAIL, project.id, child, changed)
    changed = copy.deepcopy(payload)
    changed['conversationFile'] = f'agent/{parent.id}.json'
    with pytest.raises(ValueError, match='ownership'):
        pi_agent._parent_report(EMAIL, project.id, child, changed)
    with pytest.raises(ValueError, match='owned child'):
        pi_agent._parent_report(EMAIL, project.id, parent, payload)
    with pytest.raises(FileNotFoundError):
        pi_agent._parent_report('stranger@example.com', project.id, child, payload)


def test_native_parent_report_transfer_checks_owned_child_metadata_and_bounds(reports):
    _, project, parent, child, payload = reports
    pi_agent._parent_report(EMAIL, project.id, child, payload)
    assert pi_agent._stored_parent_reports(EMAIL, project.id, parent) == [payload['arguments']]
    other = AgentConversation(id='a' * 32, name='Other parent')
    store.save_conversation(EMAIL, project.id, other)
    assert pi_agent._stored_parent_reports(EMAIL, project.id, other) == []
    path = store._project_root(EMAIL, project.id) / '.agent/children' / f'{child.id}.json'
    saved = store._read_json(path, {})
    corrupt = {**payload['arguments'], 'id': 'forged-report', 'parentFile': f'agent/{other.id}.json'}
    store._write_json(path, {**saved, 'reports': [*saved['reports'], corrupt]})
    assert pi_agent._stored_parent_reports(EMAIL, project.id, parent) == [payload['arguments']]
    assert pi_agent._stored_parent_reports(EMAIL, project.id, other) == []
    bounded = [{**payload['arguments'], 'id': f'report-{i}', 'content': 'x' * 65536} for i in range(65)]
    store._write_json(path, {**saved, 'reports': bounded})
    with pytest.raises(ValueError, match='transfer budget'):
        pi_agent._stored_parent_reports(EMAIL, project.id, parent)


def test_actual_native_direct_child_report_callback_survives_parent_refresh(reports, monkeypatch):
    import json
    from test_video_pi_agent import reply, call
    from app.video_studio.native_host import shutdown_host
    api, project, parent, _, _ = reports
    report_text = 'Native explicit progress survives a browser reload.'
    phase = 'delegate'
    contexts = []
    def model(payload, **kwargs):
        messages = payload['context']['messages']
        latest_user = max(i for i, message in enumerate(messages) if message['role'] == 'user')
        receipts = any(m['role'] == 'toolResult' for m in messages[latest_user + 1:])
        if phase == 'delegate':
            if payload.get('conversationFile'): return reply(payload, 'Delegated child draft.')
            return reply(payload, 'Parent delegated.') if receipts else reply(payload,
                calls=[call('delegateTask', {'name': 'Native writer', 'task': 'Write a draft.'})])
        if phase == 'report':
            if receipts: return reply(payload, 'Direct child completed.')
            assert any(tool['name'] == 'report' for tool in payload['context']['tools'])
            return reply(payload, calls=[call('report', {'content': report_text})])
        contexts.append(json.dumps(messages, ensure_ascii=False))
        return reply(payload, 'Parent received the explicit native report.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    def send(file, prompt):
        response = api.post('/video-legacy/api/agent', json={'directory': project.id,
            'sessionFile': file, 'prompt': prompt}, headers=headers(EMAIL))
        events = [json.loads(line) for line in response.text.splitlines()]
        assert not [e for e in events if e['type'] == 'error'], events
        return events
    try:
        send(f'agent/{parent.id}.json', 'Delegate a writing task.')
        parent = store.get_conversation(EMAIL, project.id, parent.id)
        child_file = next(item['file'] for item in parent.sub_agents if item['name'] == 'Native writer')
        original = parent.model_dump()
        phase = 'report'
        events = send(child_file, 'Report current progress to my parent.')
        explicit = [e for e in events if e['type'] == 'report' and e.get('content') == report_text]
        assert len(explicit) == 1
        for _ in range(2):
            snapshot = api.get('/video-legacy/api/agent/get', params={'directory': project.id,
                'sessionFile': f'agent/{parent.id}.json'}, headers=headers(EMAIL)).json()['data']
            projected = [m for m in snapshot['messages'] if m.get('report') and m['content'] == report_text]
            assert len(projected) == 1
        assert store.get_conversation(EMAIL, project.id, parent.id).model_dump() == original
        phase = 'parent'
        send(f'agent/{parent.id}.json', 'Read the report and continue.')
        send(f'agent/{parent.id}.json', 'Continue once more.')
        assert len(contexts) == 2
        assert all(context.count(report_text) == 1 for context in contexts)
    finally:
        shutdown_host()


def test_actual_disabled_user_memory_retains_editable_content_but_never_enters_native_provider(reports, monkeypatch):
    from app.video_studio.pi_business import BusinessTools
    from app.video_studio.native_host import shutdown_host
    from test_video_pi_agent import reply
    api, project, parent, _, _ = reports
    business = BusinessTools(EMAIL, project.id, parent.id, None, None)
    initial = business.resource_read('memory', 'user')
    marker = 'DISABLED_PRIVATE_MEMORY_native_a651f'
    business.resource_write('memory', marker, initial['revision'], enabled=False, scope='user')
    observed = []
    def model(payload, **kwargs):
        observed.append(payload['context'])
        assert marker not in json.dumps(payload['context'], ensure_ascii=False)
        assert not any(tool['name'] == 'memory' for tool in payload['context']['tools'])
        return reply(payload, 'Disabled memory remains excluded.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    try:
        response = api.post('/video-legacy/api/agent', json={'directory': project.id,
            'sessionFile': f'agent/{parent.id}.json', 'prompt': 'Hello again.'}, headers=headers(EMAIL))
        events = [json.loads(line) for line in response.text.splitlines()]
        assert not [e for e in events if e['type'] == 'error'], events
        assert len(observed) == 1
        editable = business.resource_read('memory', 'user')
        assert editable['content'] == marker and editable['enabled'] is False
    finally:
        shutdown_host()


@pytest.mark.parametrize('replace',[False,True])
def test_report_callback_waiting_metadata_lock_rejects_cancelled_or_replaced_run(reports,monkeypatch,replace):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from app.video_studio.agent_turns import AgentCancelled, cancel_turn
    from app.video_studio.workspace_documents import document_lock
    _,project,_,child,payload=reports
    turn=prepare_turn(email=EMAIL,project_id=project.id,prompt='Report direct progress',conversation_id=child.id)
    journal=RunJournal(EMAIL,project.id,child.id,turn.run_id);journal.create()
    runtime_ready=threading.Event()
    allow_report=threading.Event()
    waiting_for_metadata=threading.Event()
    worker_id=None
    path=store._project_root(EMAIL,project.id)/'.agent/children'/f'{child.id}.json'
    def observed_lock(target):
        if threading.get_ident()==worker_id and target==path:
            waiting_for_metadata.set()
        return document_lock(target)
    monkeypatch.setattr(pi_agent,'document_lock',observed_lock)
    def run_process(config,callback,*args,**kwargs):
        nonlocal worker_id
        worker_id=threading.get_ident()
        runtime_ready.set()
        assert allow_report.wait(5), 'The test must release the report callback'
        callback('tool',payload)
        raise AssertionError('A cancelled report must never reach result commit')
    monkeypatch.setattr(pi_agent,'run_process',run_process)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(pi_agent.run_agent,email=EMAIL,project_id=project.id,prompt='Report direct progress',
            conversation_id=child.id,prepared_conversation=turn,journal=journal,progress=journal.emit)
        # Startup is outside the race under test. Hold the lock only after the
        # runtime is ready, and verify the callback actually attempts that lock.
        assert runtime_ready.wait(15), 'Agent initialization did not reach the runtime'
        with document_lock(path):
            allow_report.set()
            assert waiting_for_metadata.wait(5), 'Report callback did not attempt the metadata lock'
            cancel_turn(EMAIL,project.id,child.id,turn.run_id)
            if replace:prepare_turn(email=EMAIL,project_id=project.id,prompt='New independent turn',conversation_id=child.id)
        with pytest.raises(AgentCancelled):future.result(timeout=5)
    assert not store._read_json(path,{}).get('reports')


def test_actual_native_four_child_models_overlap_with_fair_callback_budget(reports,monkeypatch):
    import threading
    from app.video_studio.native_host import shutdown_host
    from test_video_pi_agent import reply,call
    api,project,parent,_,_=reports
    barrier=threading.Barrier(4)
    files=set()
    lock=threading.Lock()
    def provider(payload,**kwargs):
        if payload.get('conversationFile'):
            with lock:files.add(payload['conversationFile'])
            barrier.wait(timeout=10)
            return reply(payload,'Concurrent child completed.')
        if any(m['role']=='toolResult' for m in payload['context']['messages']):return reply(payload,'All four native tasks completed.')
        return reply(payload,calls=[call('subAgent',{'tasks':[{'name':f'Worker {i}','task':f'Independent task {i}'} for i in range(4)]})])
    monkeypatch.setattr(pi_agent,'model_response',provider)
    try:
        response=api.post('/video-legacy/api/agent',json={'directory':project.id,'sessionFile':f'agent/{parent.id}.json',
            'prompt':'Delegate four independent tasks concurrently.'},headers=headers(EMAIL))
        events=[json.loads(line) for line in response.text.splitlines()]
        assert not [e for e in events if e['type']=='error'],events
        assert len(files)==4
        canonical=store.get_conversation(EMAIL,project.id,parent.id)
        assert len(canonical.sub_agents)==4 and all(a['status']=='completed' for a in canonical.sub_agents)
    finally:shutdown_host()
