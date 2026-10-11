"""Accepted instructions remain display receipts after cancellation, never Pi replay."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.video_studio import pi_agent, pi_http, store
from app.video_studio.agent_turns import prepare_turn
from app.video_studio.models import AgentConversation, ProjectCreate
from app.video_studio.pi_runs import RunJournal
from test_video_legacy_api import client, headers
from test_video_pi_agent import reply

EMAIL = 'native-control-receipts@example.com'


def test_actual_enqueue_then_cancel_reload_keeps_owned_instruction_without_model_replay(tmp_path, monkeypatch):
    from app.video_studio.native_host import shutdown_host
    api = client(tmp_path, monkeypatch)
    project = store.create_project(EMAIL, ProjectCreate(name='Interrupted native instruction'))
    entered, release = threading.Event(), threading.Event()
    phase = 'blocked'
    marker = 'EXACT_PENDING_INSTRUCTION_c7bb3'
    def provider(payload, check_cancel=None, **kwargs):
        if phase == 'blocked':
            entered.set()
            while not release.wait(.05):
                if check_cancel: check_cancel()
            return reply(payload, 'Late response must not be saved.')
        assert marker not in json.dumps(payload['context'])
        return reply(payload, 'New normal user turn.')
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(api.post, '/video-legacy/api/agent', json={'directory': project.id,
                'prompt': 'Keep working until I stop.'}, headers=headers(EMAIL))
            assert entered.wait(10)
            conversation = store.list_conversations(EMAIL, project.id)[0]
            scope = {'directory': project.id, 'sessionFile': f'agent/{conversation.id}.json', 'runId': conversation.run_id}
            accepted = api.post('/video-legacy/api/agent/control', json={**scope, 'action': 'followUp', 'prompt': marker}, headers=headers(EMAIL))
            assert accepted.status_code == 200, accepted.text
            command = RunJournal(EMAIL, project.id, conversation.id, conversation.run_id).commands(0)[0]
            denied = api.get('/video-legacy/api/agent/get', params=scope, headers=headers('other@example.com'))
            assert denied.status_code == 404
            cancelled = api.post('/video-legacy/api/agent/cancel', json=scope, headers=headers(EMAIL))
            assert cancelled.status_code == 200
            release.set()
            running.result(timeout=10)
        for _ in range(2):
            snapshot = api.get('/video-legacy/api/agent/get', params=scope, headers=headers(EMAIL)).json()['data']
            pending = [m for m in snapshot['messages'] if m.get('pendingInstruction')]
            assert len(pending) == 1 and pending[0]['content'] == marker
            assert pending[0]['controlId'] == command['controlId']
            assert pending[0]['instructionType'] == 'followUp' and 'entryId' not in pending[0]
        canonical = store.get_conversation(EMAIL, project.id, conversation.id)
        assert marker not in canonical.model_dump_json()
        assert canonical.pi_session_file is None
        phase = 'next'
        continued = api.post('/video-legacy/api/agent', json={'directory': project.id,
            'sessionFile': scope['sessionFile'], 'prompt': 'Start my next normal turn.'}, headers=headers(EMAIL))
        assert not [e for e in map(json.loads, continued.text.splitlines()) if e['type'] == 'error']
    finally:
        release.set()
        shutdown_host()


def test_child_instruction_projection_is_scoped_and_native_receipt_suppresses_pending(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    project = store.create_project(EMAIL, ProjectCreate(name='Scoped pending instructions'))
    parent = prepare_turn(email=EMAIL, project_id=project.id, prompt='Delegate', conversation_id=None)
    parent_journal = RunJournal(EMAIL, project.id, parent.id, parent.run_id); parent_journal.create()
    children = []
    for index in ('a', 'b'):
        child = AgentConversation(id=index * 32, name=index, parent_file=f'agent/{parent.id}.json', run_id=parent.run_id, run_status='cancelled')
        store.save_conversation(EMAIL, project.id, child)
        journal = RunJournal(EMAIL, project.id, child.id, parent.run_id); journal.create(); journal.finish('cancelled')
        children.append((child, journal))
    parent_journal.enqueue('followUp', 'Parent only.')
    parent_journal.enqueue('steer', 'Child A only.', f'agent/{children[0][0].id}.json')
    parent_journal.enqueue('followUp', 'Child B delivered.', f'agent/{children[1][0].id}.json')
    children[1][1].emit({'type': 'userMessage', 'id': 'sdk-native-user', 'content': 'Child B delivered.'})
    parent_journal.finish('cancelled')
    def projection(journal):
        return pi_http.project_snapshot(journal, {'messages': [], 'subAgents': [], 'running': False})['messages']
    assert [m['content'] for m in projection(parent_journal)] == ['Parent only.']
    first = projection(children[0][1])
    assert len(first) == 1 and first[0]['pendingInstruction'] and first[0]['content'] == 'Child A only.'
    second = projection(children[1][1])
    assert len(second) == 1 and second[0]['entryId'] == 'sdk-native-user' and not second[0].get('pendingInstruction')


def test_repeated_historical_instruction_still_has_a_distinct_pending_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    project = store.create_project(EMAIL, ProjectCreate(name='Repeated instruction'))
    conversation = prepare_turn(email=EMAIL, project_id=project.id, prompt='Use blue', conversation_id=None)
    journal = RunJournal(EMAIL, project.id, conversation.id, conversation.run_id); journal.create()
    first = journal.enqueue('followUp', 'Use blue')
    second = journal.enqueue('followUp', 'Use blue')
    journal.emit({'type': 'userMessage', 'id': 'actually-delivered', 'content': 'Use blue'})
    journal.finish('cancelled')
    snapshot = pi_http.project_snapshot(journal, {'messages': [{'id': 'historical', 'role': 'user', 'content': 'Use blue'}], 'subAgents': [], 'running': False})
    pending = [m for m in snapshot['messages'] if m.get('pendingInstruction')]
    assert len(pending) == 1 and pending[0]['controlId'] == second['controlId']
    assert pending[0]['controlId'] != first['controlId']
