"""Acceptance runs the real Pi SDK; only provider responses are simulated."""
import json
from pathlib import Path

import pytest

from app.video_studio import store, pi_agent
from app.video_studio.models import AgentConversation, AgentMessage, ProjectCreate

EMAIL = 'pi-acceptance@example.com'


def reply(payload, text='', calls=None):
    model = payload['model']
    return {'role': 'assistant', 'content': calls or [{'type': 'text', 'text': text}],
        'api': model['api'], 'provider': model['provider'], 'model': model['id'],
        'stopReason': 'toolUse' if calls else 'stop', 'timestamp': 1,
        'usage': {'input': 10, 'output': 10, 'cacheRead': 0, 'cacheWrite': 0, 'totalTokens': 20,
            'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'total': 0}}}


def call(name, arguments):
    return {'type': 'toolCall', 'id': 'call-' + name, 'name': name, 'arguments': arguments}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    return store.create_project(EMAIL, ProjectCreate(name='Pi acceptance'))


def run(project, prompt, conversation_id=None, **kwargs):
    return pi_agent.run_agent(email=EMAIL, project_id=project.id, prompt=prompt,
        conversation_id=conversation_id, **kwargs)


def test_stage_inference_and_python_history_replay_are_not_pi_context(project, monkeypatch):
    def model(payload, **kwargs):
        assert 'Current user choices (policy hints' not in payload['context']['systemPrompt']
        return reply(payload, 'Pi owns the brief and approval state.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    first, _, _ = run(project, '3W Bronco 30-second plan')
    assert first.messages[0].pi_entry_id and first.messages[1].pi_entry_id
    assert first.task_state == {}


def test_old_text_history_is_not_silently_replayed_into_pi(project):
    conversation = AgentConversation(id='a'*32, name='Retired history', messages=[
        AgentMessage(id='b'*32, role='user', content='Old custom-agent request'),
        AgentMessage(id='c'*32, role='assistant', content='Old custom-agent reply')])
    store.save_conversation(EMAIL, project.id, conversation)
    with pytest.raises(ValueError, match='new conversation'):
        run(project, 'Continue', conversation.id)


def test_pre_mapping_sdk_edit_fails_closed_instead_of_forgetting_retained_context(project, monkeypatch):
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: reply(p, 'Approved draft.'))
    first, _, _ = run(project, 'Keep the original product.')
    for message in first.messages:
        message.pi_entry_id = None
    store.save_conversation(EMAIL, project.id, first)
    second, _, _ = run(project, 'Add another note.', first.id)
    with pytest.raises(ValueError, match='SDK entry mapping'):
        run(project, 'Edit only the second note.', first.id, resend_from=second.messages[-2].id)


def test_draft_delivery_is_not_rejected_by_a_python_timeline_parser(project, monkeypatch):
    def model(payload, **kwargs):
        results = [m for m in payload['context']['messages'] if m['role'] == 'toolResult']
        if not results:
            return reply(payload, calls=[call('addNode', {'type': 'textNode', 'position': {'x': 0, 'y': 0}})])
        if len(results) == 1:
            node = json.loads(results[0]['content'][0]['text'])['node']
            return reply(payload, calls=[call('nodeTools', {'nodeId': node['id'], 'name': 'node:setText',
                'args': {'text': 'Preliminary draft: 0–5s hook; 6–30s CTA. Timing requires revision before production.'}})])
        return reply(payload, 'Draft delivered with timing limitations; not final production approval.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    conversation, canvas, text = run(project, 'Create a preliminary 30-second script node on canvas.')
    assert conversation.run_status == 'completed'
    assert 'requires revision' in canvas.nodes[0].data['textSnapshot']
    assert 'not final' in text


def test_restored_sdk_history_continues_approved_plan_without_intake(project, monkeypatch):
    seen = []
    def model(payload, **kwargs):
        seen.append(payload['context']['messages'])
        return reply(payload, '3W Ford Bronco 30-second plan: 0–5s, 5–11s, 11–17s, 17–23s, 23–30s.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    first, _, _ = run(project, '3W Liners Ford Bronco: make a 30-second CTV plan.')
    second, _, _ = run(project, 'Confirmed. Continue the approved plan.', first.id)
    assert second.pi_session_file != first.pi_session_file  # Successful source is immutable.
    assert 'Ford Bronco' in json.dumps(seen[-1])
    assert len(second.messages) == 4
    assert not Path(second.pi_session_file).is_absolute()
    assert second.run_status == 'completed'


def test_actual_sdk_tool_loop_persists_script_node(project, monkeypatch):
    def model(payload, **kwargs):
        assert 'addNode' in {tool['name'] for tool in payload['context']['tools']}, payload['context']['tools']
        results = [m for m in payload['context']['messages'] if m['role'] == 'toolResult']
        if not results:
            return reply(payload, calls=[call('addNode', {'type': 'textNode', 'position': {'x': 100, 'y': 100}, 'label': '30s script'})])
        if len(results) == 1:
            assert not results[0].get('isError'), results[0]
            node = json.loads(results[0]['content'][0]['text'])['node']
            return reply(payload, calls=[call('nodeTools', {'nodeId': node['id'], 'name': 'node:setText',
                'args': {'text': '0–5s hook; 5–11s fit; 11–17s coverage; 17–23s cleaning; 23–30s CTA.'}})])
        return reply(payload, 'Created the 30-second script node. No paid generation started.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    conversation, canvas, text = run(project, 'Create a 30-second script node on the canvas.')
    assert len(canvas.nodes) == 1
    assert '23–30s' in canvas.nodes[0].data['textSnapshot']
    assert store.get_project(EMAIL, project.id).canvas.nodes[0].id == canvas.nodes[0].id
    assert conversation.pi_session_file
    assert 'No paid' in text


def test_edit_resend_does_not_restore_abandoned_sdk_branch(project, monkeypatch):
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: reply(p, 'Old Ford Bronco draft.'))
    first, _, _ = run(project, 'Ford Bronco draft')
    seen = []
    def new_model(p, **k):
        seen.append(json.dumps(p['context']['messages']))
        return reply(p, 'New Tesla draft.')
    monkeypatch.setattr(pi_agent, 'model_response', new_model)
    run(project, 'Tesla draft', first.id, resend_from=first.messages[0].id)
    assert 'Ford Bronco' not in seen[-1]


def test_sdk_history_and_partial_tool_failure_keep_useful_delivery(project, monkeypatch):
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: reply(p, 'Approved 3W Bronco 30-second draft is available.'))
    conv, _, _ = run(project, '3W Bronco, 30 seconds')
    def model(p, **k):
        assert '3W Bronco' in json.dumps(p['context']['messages'])
        if not any(m['role'] == 'toolResult' for m in p['context']['messages']):
            return reply(p, calls=[call('web_fetch', {'url': 'https://test.invalid'})])
        return reply(p, 'The site is unavailable; here is a preliminary plan with facts marked unverified.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    monkeypatch.setattr(pi_agent, 'execute_research_tool', lambda *a, **k: (_ for _ in ()).throw(ValueError('Unavailable')))
    result, _, text = run(project, 'Continue the proposal using the client website.', conv.id)
    assert result.run_status == 'completed'
    assert 'preliminary' in text


def test_ordinary_chat_cannot_mutate_canvas_or_import_assets(project, monkeypatch):
    def model(p, **k):
        names = {tool['name'] for tool in p['context']['tools']}
        assert 'addNode' not in names
        assert 'website_assets_import' not in names
        return reply(p, 'Hello!')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    _, canvas, text = run(project, 'Hello!')
    assert canvas.nodes == [] and text == 'Hello!'


def test_model_error_preserves_successful_sdk_history_for_retry(project, monkeypatch):
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: reply(p, 'Original approved 30-second plan.'))
    original, _, _ = run(project, '3W Bronco 30 seconds')
    source = pi_agent.session_directory(EMAIL, project.id, original.id) / original.pi_session_file
    before = source.read_bytes()
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: (_ for _ in ()).throw(ValueError('HTTP 400')))
    with pytest.raises(ValueError, match='400'):
        run(project, 'Continue.', original.id)
    assert source.read_bytes() == before
    failed = store.get_conversation(EMAIL, project.id, original.id)
    assert failed.run_status == 'failed'
    assert failed.pi_session_file == original.pi_session_file


def test_current_selection_only_and_no_media_during_compaction(project, monkeypatch):
    root = store.assets_root(EMAIL, project.id)
    (root / 'old.txt').write_text('old attachment')
    (root / 'new.txt').write_text('new attachment')
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: reply(p, 'Analyzed current file.'))
    first, _, _ = run(project, 'Read old file', asset_paths=['old.txt'])
    selected = []
    original_prepare = pi_agent.prepare_assets
    def prepare(email, pid, paths, **kwargs):
        selected.extend(paths)
        return original_prepare(email, pid, paths, **kwargs)
    monkeypatch.setattr(pi_agent, 'prepare_assets', prepare)
    run(project, 'Read new file', first.id, asset_paths=['new.txt'])
    assert selected == ['new.txt']


def test_create_permission_does_not_enable_destructive_tools(project, monkeypatch):
    def model(p, **k):
        names = {tool['name'] for tool in p['context']['tools']}
        assert 'addNode' in names
        assert 'deleteNodes' not in names and 'deleteEdges' not in names
        return reply(p, 'Ready to add draft nodes.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    run(project, 'Create a draft workflow, do not delete existing nodes.')


@pytest.mark.parametrize('prompt', ['不要调研竞品，给我初步方案', 'Do not research competitors; give me a preliminary plan.'])
def test_declining_research_does_not_enable_search_or_auto_permission_cards(project, monkeypatch, prompt):
    def model(p, **k):
        names = {tool['name'] for tool in p['context']['tools']}
        assert 'web_search' not in names and 'video_transcript_fetch' not in names
        return reply(p, 'Preliminary plan using only confirmed client information.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    result, _, _ = run(project, prompt)
    assert result.research_question is None


def test_cancel_after_provider_response_cannot_commit_or_save_reply(project, monkeypatch):
    from threading import Event
    from app.video_studio.agent_turns import AgentCancelled
    cancelled = Event()
    def model(p, **k):
        cancelled.set()
        return reply(p, 'Must not be saved.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    with pytest.raises(AgentCancelled):
        run(project, 'Hello', cancel_event=cancelled)
    conv = store.list_conversations(EMAIL, project.id)[0]
    assert len(conv.messages) == 1
    assert conv.run_status == 'cancelled' and conv.pi_session_file is None


@pytest.mark.parametrize('language', ['zh-CN', 'en-US'])
def test_language_and_brief_approval_permissions_survive_reload(project, monkeypatch, language):
    from app.video_studio.models import VideoStudioSettings
    store.save_settings(EMAIL, VideoStudioSettings(language=language))
    def model(p, **k):
        assert f'Answer and all visible progress in {"English" if language == "en-US" else "Chinese"}' in p['context']['systemPrompt']
        assert 'Seedance-specific' in p['context']['systemPrompt']
        return reply(p, '3W Bronco 30s draft, not generated media.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    first, _, _ = run(project, '3W Bronco 30秒方案')
    def confirm(p, **k):
        assert '3W Bronco' in json.dumps(p['context']['messages'])
        assert 'addNode' not in {tool['name'] for tool in p['context']['tools']}
        return reply(p, 'Approved content retained. Next: create the draft workflow when authorized.')
    monkeypatch.setattr(pi_agent, 'model_response', confirm)
    second, canvas, _ = run(project, '确认' if language == 'zh-CN' else 'Confirmed.', first.id)
    assert second.run_status == 'completed' and canvas.nodes == []


def test_bad_session_path_and_disabled_agent_fail_before_any_provider_call(project, monkeypatch):
    from app.video_studio.models import CatalogImport, ExtensionDefinition
    catalog = CatalogImport(extensions=[ExtensionDefinition(id='agent-workflow', category='agent', name='Workflow', enabled=False)])
    store.save_catalog(EMAIL, catalog)
    with pytest.raises(ValueError, match='disabled'):
        run(project, 'Hello')
    assert store.list_conversations(EMAIL, project.id)[0].run_status == 'failed'
