"""Cross-boundary regressions execute the installed Pi SDK and authenticated host.

Only deployment model responses are simulated; session journals, business
callbacks, child persistence, event projection and control delivery are real.
"""
import json
import shutil
import threading
import time

import pytest

from app.video_studio import metadata_repository, pi_agent, pi_http, pi_runs, store
from app.video_studio.agent_turns import prepare_turn
from app.video_studio.models import ProjectCreate

EMAIL = 'pi-cross-host@example.com'


def reply(payload, text='', calls=None):
    return {'role': 'assistant', 'content': calls or [{'type': 'text', 'text': text}],
        'api': payload['model']['api'], 'provider': payload['model']['provider'], 'model': payload['model']['id'],
        'stopReason': 'toolUse' if calls else 'stop', 'timestamp': int(time.time()*1000),
        'usage': {'input': 10, 'output': 10, 'cacheRead': 0, 'cacheWrite': 0, 'totalTokens': 20,
            'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'total': 0}}}


def tool(name, arguments):
    return {'type': 'toolCall', 'id': 'call-' + name, 'name': name, 'arguments': arguments}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    # Keep durable storage hermetic while proving restoration without local SDK files.
    records = {}
    monkeypatch.setattr(metadata_repository, 'write', lambda key, value: records.__setitem__(key, value))
    monkeypatch.setattr(metadata_repository, 'read', lambda key: records.get(key))
    monkeypatch.setattr(metadata_repository, 'delete', lambda key: records.pop(key, None))
    return store.create_project(EMAIL, ProjectCreate(name='Pi cross-host acceptance'))


def run(project, prompt, conversation_id=None):
    conv = prepare_turn(email=EMAIL, project_id=project.id, prompt=prompt, conversation_id=conversation_id)
    journal = pi_runs.RunJournal(EMAIL, project.id, conv.id, conv.run_id)
    journal.create()
    result = pi_agent.run_agent(email=EMAIL, project_id=project.id, prompt=prompt, conversation_id=conv.id,
        prepared_conversation=conv, journal=journal, progress=journal.emit)
    journal.finish('completed')
    return result, journal


def test_actual_child_journal_restores_after_local_loss_and_preserves_sdk_entry_identities(project, monkeypatch):
    child_file = None
    child_contexts = []
    def provider(payload, **kwargs):
        nonlocal child_file
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']
            child_contexts.append(payload['context']['messages'])
            return reply(payload, 'Child draft retained.')
        messages = payload['context']['messages']
        last_user = max(i for i, m in enumerate(messages) if m['role'] == 'user')
        receipt = any(m['role'] == 'toolResult' for m in messages[last_user + 1:])
        if receipt: return reply(payload, 'Parent delivery.')
        return reply(payload, calls=[tool('messageSubAgent', {'file': child_file, 'prompt': 'Continue retained child draft.'})
            if child_file else tool('delegateTask', {'name': 'Draft specialist', 'task': 'Prepare child draft.'})])
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    (parent, _, _), journal = run(project, 'Delegate one drafting task.')
    assert child_file, parent.sub_agents
    child_events=[event for event in journal.events() if event['type']=='subAgent']
    assert child_events and all(event['agent']['runId']==parent.run_id for event in child_events)
    child_id = child_file.removeprefix('agent/').removesuffix('.json')
    first_child = store.get_conversation(EMAIL, project.id, child_id)
    assert first_child.run_status == 'completed'
    assert first_child.pi_session_file
    assert first_child.parent_file == f'agent/{parent.id}.json'
    assert len({m.pi_entry_id for m in first_child.messages}) == len(first_child.messages)
    assert all(m.id == m.pi_entry_id for m in first_child.messages)
    child_directory = pi_agent.session_directory(EMAIL, project.id, parent.id) / 'children' / child_id
    shutil.rmtree(child_directory)
    run(project, 'Continue delegated draft.', parent.id)
    second_child = store.get_conversation(EMAIL, project.id, child_id)
    assert len(second_child.messages) == 4
    assert second_child.pi_session_file != first_child.pi_session_file
    assert 'Child draft retained.' in json.dumps(child_contexts[-1])
    assert len({m.pi_entry_id for m in second_child.messages}) == 4
    assert all(m.id == m.pi_entry_id for m in second_child.messages)


def test_child_question_is_replayed_and_its_scoped_answer_reaches_real_sdk(project, monkeypatch):
    child_file = None
    answers = []
    questions = []
    answer_threads = []
    original_question = pi_runs.RunJournal.question
    def respond_to_question(self, call_id, request):
        result = original_question(self, call_id, request)
        def answer():
            path = store._project_root(EMAIL, project.id) / '.agent' / 'questions' / f'{result}.json'
            event = store._read_json(path, None)['event']
            questions.append(event)
            answers.append(pi_runs.answer(EMAIL, project.id, result,
                {'sessionFile': event['sessionFile'], 'runId': event['runId'], 'answer': 'Direction B'}))
        thread = threading.Thread(target=answer)
        thread.start(); answer_threads.append(thread)
        return result
    monkeypatch.setattr(pi_runs.RunJournal, 'question', respond_to_question)
    def provider(payload, **kwargs):
        nonlocal child_file
        receipts = [m for m in payload['context']['messages'] if m['role'] == 'toolResult']
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']
            if not receipts: return reply(payload, calls=[tool('askUser', {'title': 'Direction', 'question': 'Choose the direction.', 'options': ['A', 'B']})])
            assert 'Direction B' in json.dumps(receipts)
            return reply(payload, 'Child used Direction B.')
        return reply(payload, 'Parent complete.') if receipts else reply(payload,
            calls=[tool('delegateTask', {'name': 'Question specialist', 'task': 'Ask for missing direction.'})])
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    (parent, _, _), journal = run(project, 'Delegate a task that needs a direction.')
    for thread in answer_threads: thread.join(2)
    assert answers == [{'answer': 'Direction B', 'skipped': False}]
    question = questions[0]
    assert question['sessionFile'] == child_file
    child_id = child_file.removeprefix('agent/').removesuffix('.json')
    assert question['toolCallId'] == child_id + ':call-askUser'
    child_journal = pi_runs.RunJournal(EMAIL, project.id, child_id, parent.run_id)
    replay = child_journal.events(0)
    assert any(e['type'] == 'question' and e['callId'] == question['callId'] for e in replay)
    child = store.get_conversation(EMAIL, project.id, child_id)
    card = next(p for p in child.messages[-1].parts if p['type'] == 'tool')
    assert card['tool']['id'] == question['toolCallId']
    assert json.loads(card['tool']['result'])['answer'] == 'Direction B'
    assert card['tool'].get('question', {}).get('callId') == question['callId']


def test_failed_reloaded_child_retains_prior_display_history_and_new_failed_attempt(project, monkeypatch):
    child_file = None
    calls = 0
    def provider(payload, **kwargs):
        nonlocal child_file, calls
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']; calls += 1
            if calls > 1: raise ValueError('Simulated HTTP 400; owner config retained')
            return reply(payload, 'Original successful child draft.')
        messages = payload['context']['messages']
        last_user = max(i for i, m in enumerate(messages) if m['role'] == 'user')
        receipt = any(m['role'] == 'toolResult' for m in messages[last_user + 1:])
        if receipt: return reply(payload, 'Parent reviewed the child result.')
        return reply(payload, calls=[tool('messageSubAgent', {'file': child_file, 'prompt': 'Continue after reload.'})
            if child_file else tool('delegateTask', {'name': 'Writer', 'task': 'Original task.'})])
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    (parent, _, _), _ = run(project, 'Delegate writing.')
    child_id = child_file.removeprefix('agent/').removesuffix('.json')
    original = store.get_conversation(EMAIL, project.id, child_id)
    run(project, 'Continue child.', parent.id)
    child = store.get_conversation(EMAIL, project.id, child_id)
    assert child.run_status == 'failed'
    assert any(m.content == 'Original successful child draft.' for m in child.messages)
    assert any(m.content == 'Continue after reload.' for m in child.messages)
    assert {m.pi_entry_id for m in original.messages}.issubset({m.pi_entry_id for m in child.messages})


def test_child_cancel_unblocks_question_keeps_parent_running_and_preserves_cancel_status(project, monkeypatch):
    original_question = pi_runs.RunJournal.question
    questions = []
    def cancel_question_child(self, tool_id, request):
        call_id = original_question(self, tool_id, request)
        question = store._read_json(store._project_root(EMAIL, project.id) / '.agent' / 'questions' / f'{call_id}.json', None)
        questions.append(question['event'])
        self.abort_child(question['event']['sessionFile'])
        return call_id
    monkeypatch.setattr(pi_runs.RunJournal, 'question', cancel_question_child)
    child_file = None
    child_model_calls = 0
    def provider(payload, **kwargs):
        nonlocal child_file, child_model_calls
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']; child_model_calls += 1
            return reply(payload, calls=[tool('askUser', {'title': 'Direction', 'question': 'Choose one.'})])
        receipts = [m for m in payload['context']['messages'] if m['role'] == 'toolResult']
        return reply(payload, 'Parent continues after cancellation.') if receipts else reply(payload,
            calls=[tool('delegateTask', {'name': 'Question task', 'task': 'Need missing direction.'})])
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    (parent, _, text), journal = run(project, 'Delegate a question task.')
    assert parent.run_status == 'completed'
    assert 'Parent continues' in text
    assert child_model_calls == 1
    child = store.get_conversation(EMAIL, project.id, child_file.removeprefix('agent/').removesuffix('.json'))
    assert child.run_status == 'cancelled'
    assert parent.sub_agents[0]['status'] == 'cancelled'
    with pytest.raises(ValueError, match='no longer'):
        pi_runs.answer(EMAIL, project.id, questions[0]['callId'], {'answer': 'Too late'})


def test_stale_child_display_lease_does_not_interrupt_a_live_parent_and_failed_progress_reloads(project):
    from app.video_studio.models import AgentConversation, AgentMessage
    parent = prepare_turn(email=EMAIL, project_id=project.id, prompt='Parent task.', conversation_id=None)
    parent_journal = pi_runs.RunJournal(EMAIL, project.id, parent.id, parent.run_id)
    parent_journal.create()
    child = AgentConversation(id='e' * 32, name='Waiting child', parent_file=f'agent/{parent.id}.json',
        run_id=parent.run_id, run_status='running', messages=[AgentMessage(id='f'*32, role='user', content='Child task.')])
    store.save_conversation(EMAIL, project.id, child)
    journal = pi_runs.RunJournal(EMAIL, project.id, child.id, parent.run_id)
    journal.create()
    state = journal.state(); state['heartbeat'] = time.time() - 180
    store._write_json(journal.path, state)
    assert pi_http.recover(journal)['status'] == 'running'
    journal.emit({'type': 'text', 'blockId': 'partial-1', 'delta': 'Partial retained draft.'})
    journal.emit({'type': 'tool', 'blockId': 'tool-1', 'tool': {'id': 'tool-1', 'name': 'draft', 'status': 'running'}})
    journal.finish('failed')
    child.run_status = 'failed'; child.run_error = 'Provider failure'
    store.save_conversation(EMAIL, project.id, child)
    snapshot = pi_http.project_snapshot(journal, {'messages': [m.model_dump() for m in child.messages], 'running': False, 'runError': child.run_error})
    attempt = snapshot['messages'][-1]
    assert attempt['streaming'] is False
    assert attempt['error'] == 'Provider failure'
    assert attempt['parts'][0]['content'] == 'Partial retained draft.'
    assert attempt['parts'][1]['tool']['status'] == 'interrupted'


def test_late_model_success_after_child_cancel_cannot_publish_completed_or_report(project, monkeypatch):
    child_file = None
    def provider(payload, **kwargs):
        nonlocal child_file
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']
            parent_id = payload['parentFile'].removeprefix('agent/').removesuffix('.json')
            parent = store.get_conversation(EMAIL, project.id, parent_id)
            pi_runs.RunJournal(EMAIL, project.id, parent_id, parent.run_id).abort_child(child_file)
            # Simulate a model HTTP response racing the asynchronously pumped abort.
            return reply(payload, 'Late child success must not become a completed delivery.')
        receipts = [m for m in payload['context']['messages'] if m['role'] == 'toolResult']
        return reply(payload, 'Parent continues safely.') if receipts else reply(payload,
            calls=[tool('delegateTask', {'name': 'Late child', 'task': 'Work until cancelled.'})])
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    (parent, _, _), journal = run(project, 'Delegate cancellable task.')
    child_id = child_file.removeprefix('agent/').removesuffix('.json')
    child = store.get_conversation(EMAIL, project.id, child_id)
    assert child.run_status == 'cancelled'
    assert parent.sub_agents[0]['status'] == 'cancelled'
    assert not any(event['type'] == 'report' and event['file'] == child_file for event in journal.events(0))


def test_parent_cancel_cascades_to_sdk_child_and_rejects_its_pending_question(project, monkeypatch):
    from app.video_studio.agent_turns import AgentCancelled, cancel_turn
    original_question = pi_runs.RunJournal.question
    questions = []
    child_file = None
    def cancel_parent(self, tool_id, request):
        call_id = original_question(self, tool_id, request)
        question = store._read_json(store._project_root(EMAIL, project.id) / '.agent' / 'questions' / f'{call_id}.json', None)
        questions.append(question['event'])
        cancel_turn(EMAIL, project.id, self.conversation_id, self.run_id)
        return call_id
    monkeypatch.setattr(pi_runs.RunJournal, 'question', cancel_parent)
    def provider(payload, **kwargs):
        nonlocal child_file
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']
            return reply(payload, calls=[tool('askUser', {'title': 'Waiting', 'question': 'Need an answer.'})])
        return reply(payload, calls=[tool('delegateTask', {'name': 'Child waiting for input', 'task': 'Ask for missing input.'})])
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    with pytest.raises(AgentCancelled): run(project, 'Delegate then cancel parent.')
    child_id = child_file.removeprefix('agent/').removesuffix('.json')
    child = store.get_conversation(EMAIL, project.id, child_id)
    assert child.run_status == 'cancelled'
    assert pi_runs.RunJournal(EMAIL, project.id, child_id, child.run_id).state()['status'] == 'cancelled'
    with pytest.raises(ValueError, match='no longer'):
        pi_runs.answer(EMAIL, project.id, questions[0]['callId'], {'answer': 'Late answer'})


def test_direct_user_child_turn_is_retained_when_parent_later_resumes_the_delegate(project, monkeypatch):
    child_file = None
    delegated_contexts = []
    def provider(payload, **kwargs):
        nonlocal child_file
        messages = payload['context']['messages']
        last_user = max(i for i, m in enumerate(messages) if m['role'] == 'user')
        content = messages[last_user]['content']
        user_text = content if isinstance(content, str) else ''.join(b.get('text', '') for b in content)
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']
            delegated_contexts.append(messages)
            return reply(payload, 'Delegated child reply.')
        if user_text == 'Direct user instruction: preserve the violet direction.':
            assert 'Assigned child draft.' in json.dumps(messages)
            return reply(payload, 'Direct child reply: violet retained.')
        receipt = any(m['role'] == 'toolResult' for m in messages[last_user + 1:])
        if receipt: return reply(payload, 'Parent delivery.')
        return reply(payload, calls=[tool('messageSubAgent', {'file': child_file, 'prompt': 'Continue after direct user instruction.'})
            if child_file else tool('delegateTask', {'name': 'Writer', 'task': 'Assigned child draft.'})])
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    (parent, _, _), _ = run(project, 'Delegate the draft.')
    child_id = child_file.removeprefix('agent/').removesuffix('.json')
    (direct, _, text), _ = run(project, 'Direct user instruction: preserve the violet direction.', child_id)
    assert direct.parent_file == f'agent/{parent.id}.json'
    assert direct.run_id != parent.run_id
    assert text == 'Direct child reply: violet retained.'
    run(project, 'Parent resumes delegated draft.', parent.id)
    assert len(delegated_contexts) == 2
    resumed_context = json.dumps(delegated_contexts[-1])
    assert 'Direct user instruction: preserve the violet direction.' in resumed_context
    assert 'Direct child reply: violet retained.' in resumed_context
    latest = store.get_conversation(EMAIL, project.id, child_id)
    assert len([m for m in latest.messages if m.role == 'user']) == 3
    assert len({m.pi_entry_id for m in latest.messages}) == len(latest.messages)


def test_parent_cannot_resume_child_while_its_independent_user_run_is_active(project, monkeypatch):
    child_file = None
    child_calls = 0
    errors = []
    def provider(payload, **kwargs):
        nonlocal child_file, child_calls
        messages = payload['context']['messages']
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']; child_calls += 1
            return reply(payload, 'Initial child reply.')
        last_user = max(i for i, m in enumerate(messages) if m['role'] == 'user')
        receipts = [m for m in messages[last_user + 1:] if m['role'] == 'toolResult']
        if receipts:
            if receipts[-1].get('isError'): errors.append(receipts[-1])
            return reply(payload, 'Parent acknowledged child state.')
        return reply(payload, calls=[tool('messageSubAgent', {'file': child_file, 'prompt': 'Attempt parallel continuation.'})
            if child_file else tool('delegateTask', {'name': 'Writer', 'task': 'Initial task.'})])
    monkeypatch.setattr(pi_agent, 'model_response', provider)
    (parent, _, _), _ = run(project, 'Delegate initial task.')
    child_id = child_file.removeprefix('agent/').removesuffix('.json')
    independent = prepare_turn(email=EMAIL, project_id=project.id, prompt='Independent child user task.', conversation_id=child_id)
    own_journal = pi_runs.RunJournal(EMAIL, project.id, child_id, independent.run_id); own_journal.create()
    run(project, 'Parent attempts to resume busy child.', parent.id)
    assert child_calls == 1
    assert errors
    assert 'active' in json.dumps(errors).lower() or 'running' in json.dumps(errors).lower()
    current = store.get_conversation(EMAIL, project.id, child_id)
    assert current.run_id == independent.run_id
    assert current.run_status == 'running'


def test_deleted_child_turn_and_tool_receipt_stay_deleted_when_parent_resumes_sdk(project, monkeypatch):
    removed_user = 'Removed child instruction: amber-heron-732.'
    removed_reply = 'Removed child reply: silver-otter-419.'
    removed_receipt = 'Removed workspace receipt: cobalt-ibis-856.'
    continued_prompt = 'Continue with a fresh child instruction.'
    continued_reply = 'Fresh child reply retained.'
    (store.assets_root(EMAIL, project.id) / 'deleted-note.txt').write_text(removed_receipt)
    child_file = None
    child_calls = 0
    resumed_contexts = []
    running_snapshots = []
    deleted_ids = []
    original_child_session = pi_agent._child_session

    def observe_child_save(email, project_id, parent, directory, args):
        result = original_child_session(email, project_id, parent, directory, args)
        if deleted_ids and args.get('action') == 'save' and args.get('status') == 'running':
            current = store.get_conversation(email, project_id, args['file'][6:-5])
            running_snapshots.append(current.model_copy(deep=True))
        return result

    def provider(payload, **kwargs):
        nonlocal child_file, child_calls
        messages = payload['context']['messages']
        last_user = max(i for i, m in enumerate(messages) if m['role'] == 'user')
        receipts = [m for m in messages[last_user + 1:] if m['role'] == 'toolResult']
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']
            child_calls += 1
            if child_calls == 1:
                return reply(payload, calls=[tool('workspaceDocuments', {'action': 'read', 'path': 'deleted-note.txt'})])
            if child_calls == 2:
                assert removed_receipt in json.dumps(receipts)
                return reply(payload, removed_reply)
            resumed_contexts.append(messages)
            return reply(payload, continued_reply)
        if receipts:
            return reply(payload, 'Parent delivery.')
        return reply(payload, calls=[tool('messageSubAgent', {'file': child_file, 'prompt': continued_prompt})
            if child_file else tool('delegateTask', {'name': 'Writer', 'task': removed_user})])

    monkeypatch.setattr(pi_agent, 'model_response', provider)
    monkeypatch.setattr(pi_agent, '_child_session', observe_child_save)
    (parent, _, _), _ = run(project, 'Delegate a document-reading child.')
    child_id = child_file[6:-5]
    child = store.get_conversation(EMAIL, project.id, child_id)
    raw_journal = pi_agent.session_directory(EMAIL, project.id, parent.id) / 'children' / child_id / child.pi_session_file
    assert removed_receipt in raw_journal.read_text()
    deleted_ids.extend(m.pi_entry_id for m in child.messages)
    assert all(deleted_ids)
    child.messages = []
    child.pi_deleted_entries = deleted_ids.copy()
    store.save_conversation(EMAIL, project.id, child)

    run(project, 'Resume the child after deleting its prior turn.', parent.id)

    assert len(resumed_contexts) == 1
    for marker in (removed_user, removed_reply, removed_receipt):
        assert marker not in json.dumps(resumed_contexts)
    assert running_snapshots
    # The original native lifecycle also checkpoints running state after the
    # SDK has physically redacted the journal; those later markers may clear.
    assert running_snapshots[0].pi_deleted_entries == deleted_ids
    for snapshot in running_snapshots:
        assert snapshot.pi_deleted_entries in (deleted_ids, [])
        assert all(m.pi_entry_id not in deleted_ids for m in snapshot.messages)
        assert all(removed_user not in m.content and removed_reply not in m.content for m in snapshot.messages)
    latest = store.get_conversation(EMAIL, project.id, child_id)
    assert [m.content for m in latest.messages] == [continued_prompt, continued_reply]
    assert not latest.pi_deleted_entries
    assert not set(deleted_ids).intersection(m.pi_entry_id for m in latest.messages)
    for marker in (removed_user, removed_reply, removed_receipt):
        assert marker not in (raw_journal.parent / latest.pi_session_file).read_text()


def test_local_only_child_snapshot_supports_delegate_direct_and_parent_continuation(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('VIDEO_STUDIO_METADATA_DATABASE', '0')
    project = store.create_project(EMAIL, ProjectCreate(name='Local Pi child acceptance'))
    assert not metadata_repository.enabled()
    child_file = None
    resumed_contexts = []

    def provider(payload, **kwargs):
        nonlocal child_file
        messages = payload['context']['messages']
        last_user = max(i for i, m in enumerate(messages) if m['role'] == 'user')
        content = messages[last_user]['content']
        user_text = content if isinstance(content, str) else ''.join(b.get('text', '') for b in content)
        if payload.get('conversationFile'):
            child_file = payload['conversationFile']
            resumed_contexts.append(messages)
            return reply(payload, 'Local delegated reply retained.')
        if user_text == 'Direct local child instruction: retain the violet choice.':
            assert 'Local assigned task.' in json.dumps(messages)
            assert 'Local delegated reply retained.' in json.dumps(messages)
            return reply(payload, 'Direct local child reply retained.')
        if any(m['role'] == 'toolResult' for m in messages[last_user + 1:]):
            return reply(payload, 'Parent delivery.')
        return reply(payload, calls=[tool('messageSubAgent', {'file': child_file, 'prompt': 'Resume local child after direct user turn.'})
            if child_file else tool('delegateTask', {'name': 'Local writer', 'task': 'Local assigned task.'})])

    monkeypatch.setattr(pi_agent, 'model_response', provider)
    (parent, _, _), _ = run(project, 'Delegate a local child.')
    child_id = child_file[6:-5]
    child = store.get_conversation(EMAIL, project.id, child_id)
    # Existing installations only have the delegated SDK file, not a separate
    # local snapshot. Preserve that file while exercising the migration path.
    local_snapshots = pi_agent.session_directory(EMAIL, project.id, child_id) / 'snapshots'
    if local_snapshots.exists():
        shutil.rmtree(local_snapshots)
    assert child.pi_session_file
    (direct, _, _), _ = run(project, 'Direct local child instruction: retain the violet choice.', child_id)
    assert direct.run_status == 'completed'
    run(project, 'Parent resumes its local delegate.', parent.id)
    assert len(resumed_contexts) == 2
    context = json.dumps(resumed_contexts[-1])
    assert 'Direct local child instruction: retain the violet choice.' in context
    assert 'Direct local child reply retained.' in context
    latest = store.get_conversation(EMAIL, project.id, child_id)
    assert latest.run_status == 'completed'
    assert len([m for m in latest.messages if m.role == 'user']) == 3
    assert len({m.pi_entry_id for m in latest.messages}) == len(latest.messages)
