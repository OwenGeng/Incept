"""Permission, persistence and concurrency boundaries of Pi business tools."""
import asyncio
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from app.video_studio import store
from app.video_studio.models import CanvasDocument, ExportJob, MediaJob, ProjectCreate
from app.video_studio.pi_business import BusinessTools
from app.video_studio.pi_tools import CanvasTools
from app.video_studio.workspace_documents import DocumentConflict


class Control:
    def check(self):
        pass

    @contextmanager
    def mutation(self):
        yield


@pytest.fixture
def business(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    email = 'owner@example.com'
    project = store.create_project(email, ProjectCreate(name='Pi business'))
    tools = CanvasTools(project.canvas, {'text', 'image', 'video', 'audio', 'imageGeneration', 'videoGeneration'})
    return BusinessTools(email, project.id, 'a' * 32, Control(), tools)


@pytest.fixture
def api_loop():
    """A real long-lived API loop, independent from the tool worker thread."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever)
    thread.start()
    def invoke(coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=10)
    yield loop, invoke
    loop.call_soon_threadsafe(loop.stop)
    thread.join()
    loop.close()


def request(key='approved-request-1'):
    return {'idempotency_key': key, 'media_type': 'image', 'provider_id': 'configured', 'model_id': 'configured-image', 'prompt': 'Original product scene'}


def fake_generation(monkeypatch, loop):
    from app.video_studio import media_jobs
    created = []
    monkeypatch.setattr('app.routers.video_runtime.validate_media_model', lambda *args: None)
    def create(email, project_id, body):
        assert asyncio.get_running_loop() is loop
        created.append(body)
        return store.save_media_job(email, MediaJob(id='b' * 32, project_id=project_id, request=body))
    monkeypatch.setattr(media_jobs, 'create_media_job', create)
    return created


def test_memory_revisions_disabled_context_and_forget_history(business):
    before = business.resource_read('memory')
    saved = business.resource_write('memory', 'Prefer original 16:9 videos.', before['revision'])
    assert 'Prefer original 16:9' in business.context()
    with pytest.raises(DocumentConflict):
        business.resource_write('memory', 'Stale overwrite', before['revision'])
    disabled = business.execute('memoryOperator', {'action': 'configure', 'enabled': False, 'expected_revision': saved['revision']})
    assert not disabled['enabled'] and business.context() == ''
    forgotten = business.execute('memoryOperator', {'action': 'forget', 'expected_revision': disabled['revision']})
    assert forgotten['content'] == ''
    state = store._read_json(business._resource_path('memory', 'project'), {})
    assert state['history'] == [] and 'Prefer original' not in json.dumps(state)


def test_memory_user_and_project_isolation_and_ownership(business):
    initial = business.resource_read('memory', 'user')
    business.resource_write('memory', 'User preference', initial['revision'], scope='user')
    another = store.create_project(business.email, ProjectCreate(name='Another'))
    other = BusinessTools(business.email, another.id, 'c' * 32, None, CanvasTools(another.canvas, {'text'}))
    assert other.resource_read('memory', 'user')['content'] == 'User preference'
    assert other.resource_read('memory')['content'] == ''
    with pytest.raises(FileNotFoundError):
        BusinessTools('intruder@example.com', business.project_id, 'c' * 32, None, business.canvas_tools)
    independent = store.create_project('intruder@example.com', ProjectCreate(name='Private'))
    intruder = BusinessTools('intruder@example.com', independent.id, 'd' * 32, None, CanvasTools(independent.canvas, {'text'}))
    assert intruder.resource_read('memory', 'user')['content'] == ''
    with pytest.raises(ValueError):
        business.resource_read('rules', 'user')


def test_memory_remember_allowed_in_readonly_chat_but_workspace_write_denied(business):
    business.definitions(readonly=True)
    initial = business.resource_read('memory')
    result = business.execute('memoryOperator', {'action': 'write', 'content': 'Use Mandarin', 'expected_revision': initial['revision']})
    assert result['content'] == 'Use Mandarin'
    with pytest.raises(ValueError):
        business.execute('workspaceDocuments', {'action': 'create', 'path': 'brief.md', 'text': 'no'})


def test_two_concurrent_resource_writes_only_one_wins(business):
    revision = business.resource_read('rules')['revision']
    def write(content):
        try:
            return business.resource_write('rules', content, revision)['content']
        except DocumentConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ['First rule', 'Second rule']))
    assert results.count('conflict') == 1
    assert business.resource_read('rules')['content'] in {'First rule', 'Second rule'}


def test_workspace_create_conflict_search_and_private_paths(business):
    created = business.execute('workspaceDocuments', {'action': 'create', 'path': 'production/brief.md', 'text': 'Brand brief\nOriginal story'})
    snapshot = business.execute('workspaceDocuments', {'action': 'read', 'path': 'production/brief.md'})
    assert snapshot['revision'] == created['revision']
    saved = business.execute('workspaceDocuments', {'action': 'write', 'path': snapshot['path'], 'text': 'Brand approved\nOriginal story', 'expected_revision': snapshot['revision']})
    with pytest.raises(DocumentConflict):
        business.execute('workspaceDocuments', {'action': 'write', 'path': snapshot['path'], 'text': 'Stale', 'expected_revision': snapshot['revision']})
    with pytest.raises(FileExistsError):
        business.execute('workspaceDocuments', {'action': 'create', 'path': snapshot['path'], 'text': 'Replace'})
    matches = business.execute('workspaceDocuments', {'action': 'search', 'query': 'brand', 'limit': 1})
    assert matches['matches'][0]['line'] == 1
    assert matches['matches'][0]['revision'] == saved['revision'] and matches['truncated']
    for path in ['../pi-private/memory.json', '/etc/passwd', 'C:\\private', '..\\project.json']:
        with pytest.raises(ValueError):
            business.execute('workspaceDocuments', {'action': 'read', 'path': path})
    assert business.execute('workspaceDocuments', {'action': 'list'})['entries'][0]['path'] == 'production'


def test_workspace_symlink_cannot_escape_and_binary_not_text(business, tmp_path):
    root = store.assets_root(business.email, business.project_id)
    external = tmp_path / 'private.txt'
    external.write_text('Private')
    (root / 'link').symlink_to(external)
    with pytest.raises(ValueError):
        business.execute('workspaceDocuments', {'action': 'read', 'path': 'link'})
    (root / 'binary.bin').write_bytes(b'\x00\xff')
    with pytest.raises(ValueError):
        business.execute('workspaceDocuments', {'action': 'read', 'path': 'binary.bin'})
    assert not any(item['path'] == 'link' for item in business.execute('workspaceDocuments', {'action': 'list'})['entries'])


def test_tools_validate_unknown_args_limits_and_permissions(business):
    for args in [{'action': 'list', 'command': 'cat secret'}, {'action': 'list', 'limit': 201}, {'action': 'create', 'path': 'x', 'text': 3}]:
        with pytest.raises(ValueError):
            business.execute('workspaceDocuments', args)
    business.permissions = {'canvas': False}
    with pytest.raises(ValueError, match='authorize'):
        business.execute('workspaceDocuments', {'action': 'create', 'path': 'x.md', 'text': 'x'})
    business.enabled_extensions = set()
    assert 'workspaceDocuments' not in {item['name'] for item in business.definitions()}
    with pytest.raises(ValueError, match='disabled'):
        business.execute('workspaceDocuments', {'action': 'list'})


def test_canvas_changes_and_file_target_cannot_be_lost_by_switch(business):
    original_id = business.canvas_id
    created = business.execute('canvasManager', {'action': 'create', 'name': 'Storyboard'})
    assert created['status'] == 'saved' and business.canvas_id != original_id
    assert business.canvas_baseline == business.canvas_tools.canvas
    renamed = business.execute('canvasManager', {'action': 'rename', 'canvas_id': business.canvas_id, 'name': 'Approved storyboard'})
    assert renamed['canvases'][-1]['name'] == 'Approved storyboard'
    business.canvas_tools.execute('addNode', {'type': 'textNode', 'position': {'x': 0, 'y': 0}})
    with pytest.raises(DocumentConflict):
        business.execute('canvasManager', {'action': 'switch', 'canvas_id': original_id})
    assert len(business.canvas_tools.canvas.nodes) == 1
    business.canvas_tools.changed = False
    business.canvas_file_locked = True
    with pytest.raises(ValueError, match='canvas file'):
        business.execute('canvasManager', {'action': 'switch', 'canvas_id': original_id})


def test_skill_crud_revisions_enable_and_user_isolation(business):
    initial = business.execute('skillManager', {'action': 'list'})
    saved = business.execute('skillManager', {'action': 'write', 'expected_revision': initial['revision'],
        'skill': {'id': 'original-stories', 'name': 'Original stories', 'instructions': 'Write original scripts.', 'enabled': False}})
    read = business.execute('skillManager', {'action': 'read', 'id': 'original-stories'})
    assert read['skill']['instructions'] == 'Write original scripts.' and not read['skill']['enabled']
    assert not any(item.id == 'original-stories' for item in store.get_catalog('someone@example.com').skills)
    with pytest.raises(DocumentConflict):
        business.execute('skillManager', {'action': 'delete', 'id': 'original-stories', 'expected_revision': initial['revision']})
    deleted = business.execute('skillManager', {'action': 'delete', 'id': 'original-stories', 'expected_revision': saved['revision']})
    assert not any(item['id'] == 'original-stories' for item in deleted['skills'])
    with pytest.raises(ValueError, match='Builtin'):
        business.execute('skillManager', {'action': 'delete', 'id': 'storyboard', 'expected_revision': deleted['revision']})


def test_skill_resource_bulk_edit_preserves_extensions_and_conflicts(business):
    initial = business.resource_read('skills')
    skills = json.loads(initial['content'])
    skills[0]['enabled'] = False
    extensions = store.get_catalog(business.email).extensions
    saved = business.resource_write('skills', json.dumps(skills), initial['revision'])
    assert not json.loads(saved['content'])[0]['enabled']
    assert store.get_catalog(business.email).extensions == extensions
    with pytest.raises(DocumentConflict):
        business.resource_write('skills', initial['content'], initial['revision'])
    with pytest.raises(ValueError, match='individual skills'):
        business.resource_write('skills', saved['content'], saved['revision'], enabled=False)
    assert business.resource_read('skills') == saved


def test_team_config_rejects_private_remote_urls_and_invalid_structure(business):
    before = business.resource_read('team')
    valid = {'agents': [{'id': 'writer', 'name': 'Writer', 'instructions': 'Write original scripts'}], 'remote_agents': []}
    saved = business.resource_write('team', json.dumps(valid), before['revision'])
    assert json.loads(saved['content']) == valid
    for config in [{'agents': 'wrong'}, {'remote_agents': [{'name': 'Internal', 'url': 'https://127.0.0.1/a2a'}]}, {'command': 'shell'}]:
        with pytest.raises(ValueError):
            business.resource_write('team', json.dumps(config), saved['revision'])


@pytest.mark.parametrize('answer', [{'answer': '取消'}, {'skipped': True}, {'answer': 'yes'}, None])
def test_paid_generation_denial_never_submits_and_persists(business, api_loop, monkeypatch, answer):
    loop, business.invoke_async = api_loop
    created = fake_generation(monkeypatch, loop)
    questions = []
    business.ask = lambda call, question: questions.append(question) or answer
    result = business.execute('mediaJobs', {'action': 'submit', 'request': request()}, tool_call_id='tool-1')
    assert result['status'] == 'approval_denied' and created == []
    assert questions[0]['paidRequest']['request']['prompt'] == request()['prompt']
    assert request()['prompt'] in questions[0]['question']
    again = business.execute('mediaJobs', {'action': 'submit', 'request': request()}, tool_call_id='different-tool')
    assert again['status'] == 'approval_denied' and len(questions) == 1


def test_paid_generation_exact_request_durable_idempotency_on_api_loop(business, api_loop, monkeypatch):
    loop, business.invoke_async = api_loop
    created = fake_generation(monkeypatch, loop)
    questions = []
    business.ask = lambda call, question: questions.append(question) or {'answer': '批准并提交'}
    first = business.execute('mediaJobs', {'action': 'submit', 'request': request()}, tool_call_id='tool-1')
    assert first['job']['id'] == 'b' * 32 and not first['reused']
    # Recreate host state: receipt and job persistence survive a process restart.
    resumed = BusinessTools(business.email, business.project_id, business.conversation_id, None, business.canvas_tools,
                            invoke_async=business.invoke_async, ask=lambda *args: pytest.fail('Approval should not repeat'))
    second = resumed.execute('mediaJobs', {'action': 'submit', 'request': request()}, tool_call_id='new-tool')
    assert second['reused'] and len(created) == len(questions) == 1
    assert created[0].idempotency_key.startswith('pi-')
    with pytest.raises(DocumentConflict, match='different exact request'):
        resumed.execute('mediaJobs', {'action': 'submit', 'request': {**request(), 'prompt': 'Changed prompt'}})
    assert len(created) == 1


def test_job_persisted_before_receipt_crash_is_recovered_without_duplicate_job_or_approval(business, api_loop, monkeypatch):
    from app.video_studio import media_jobs
    _, business.invoke_async = api_loop
    monkeypatch.setattr('app.routers.video_runtime.validate_media_model', lambda *args: None)
    monkeypatch.setattr(media_jobs, 'validate_media_model', lambda *args: None)
    # Exercise the real durable job idempotency lookup without starting a
    # provider worker. This simulates a crash before dispatch to the provider.
    monkeypatch.setattr(media_jobs, '_start_task', lambda *args: None)
    questions = []
    business.ask = lambda call, question: questions.append(question) or {'answer': '批准并提交'}
    original_write = store._write_json
    failed = False
    def crash_receipt(path, value):
        nonlocal failed
        if path.parent.name == 'receipts' and value.get('status') == 'submitted' and not failed:
            failed = True
            raise OSError('Simulated receipt persistence interruption')
        return original_write(path, value)
    monkeypatch.setattr(store, '_write_json', crash_receipt)
    with pytest.raises(OSError):
        business.execute('mediaJobs', {'action': 'submit', 'request': request()})
    assert len(store.list_media_jobs(business.email, business.project_id)) == 1
    result = business.execute('mediaJobs', {'action': 'submit', 'request': request()})
    assert result['job']['id'] == store.list_media_jobs(business.email, business.project_id)[0].id
    assert len(store.list_media_jobs(business.email, business.project_id)) == len(questions) == 1


@pytest.mark.parametrize('changed_path', ['first.png', 'last.png'])
def test_approved_reference_hashes_are_bound_before_ask_and_worker_rejects_changed_frames(business, api_loop, monkeypatch, changed_path):
    from app.video_studio import media_jobs
    _, business.invoke_async = api_loop
    root = store.assets_root(business.email, business.project_id)
    approved_bytes = {'first.png': b'approved first frame', 'last.png': b'approved last frame'}
    for path, payload in approved_bytes.items():
        (root / path).write_bytes(payload)
    revisions = {path: hashlib.sha256(payload).hexdigest() for path, payload in approved_bytes.items()}
    monkeypatch.setattr('app.routers.video_runtime.validate_media_model', lambda *args: None)
    monkeypatch.setattr(media_jobs, 'validate_media_model', lambda *args: None)
    monkeypatch.setattr(media_jobs, '_start_task', lambda *args: None)
    questions, provider_calls = [], []
    def approve(call, question):
        questions.append(question)
        assert question['paidRequest']['request']['input_revisions'] == revisions
        # User/editor changes the approved reference while the question waits.
        (root / changed_path).write_bytes(b'changed after approval displayed')
        return {'answer': '批准并提交'}
    async def no_provider_call(body):
        provider_calls.append(body)
        raise AssertionError('Changed references must fail before the paid provider call')
    business.ask = approve
    monkeypatch.setattr(media_jobs, 'generate_media', no_provider_call)
    result = business.execute('mediaJobs', {'action': 'submit', 'request': {**request(), 'first_frame_path': 'first.png', 'last_frame_path': 'last.png'}})
    job = store.get_media_job(business.email, business.project_id, result['job']['id'])
    assert job.request.input_revisions == revisions and len(questions) == 1
    business.invoke_async(media_jobs._run_media(business.email, business.project_id, job.id))
    completed = store.get_media_job(business.email, business.project_id, job.id)
    assert completed.status == 'failed' and 'Approved frame asset has changed' in completed.message
    assert provider_calls == []


def test_model_cannot_supply_reference_hashes_to_bypass_host_binding(business):
    business.ask = lambda *args: pytest.fail('Model-authored approval hashes must be rejected')
    with pytest.raises(ValueError, match='Unknown tool argument'):
        business.execute('mediaJobs', {'action': 'submit', 'request': {**request(), 'input_revisions': {'first.png': 'f' * 64}}})


def test_media_disabled_and_unconfigured_model_do_not_ask_or_submit(business, monkeypatch):
    business.ask = lambda *args: pytest.fail('No approval for disabled/unconfigured request')
    business.enabled_extensions = {'tool-canvas', 'tool-workspace'}
    with pytest.raises(ValueError):
        business.execute('mediaJobs', {'action': 'submit', 'request': request()})
    business.enabled_extensions = None
    with pytest.raises(ValueError, match='not enabled'):
        business.execute('mediaJobs', {'action': 'submit', 'request': request()})


def test_paid_generation_requires_stable_key_and_bounded_paths(business, monkeypatch):
    monkeypatch.setattr('app.routers.video_runtime.validate_media_model', lambda *args: None)
    business.ask = lambda *args: pytest.fail('Invalid request must not ask approval')
    for payload in [{**request(), 'idempotency_key': None}, {**request(), 'output_directory': '../private'}, {**request(), 'shell': 'rm -rf'}]:
        with pytest.raises(ValueError):
            business.execute('mediaJobs', {'action': 'submit', 'request': payload})


def test_export_submission_on_api_loop_no_paid_request_and_reuse(business, api_loop, monkeypatch):
    from app.video_studio import jobs
    loop, business.invoke_async = api_loop
    root = store.assets_root(business.email, business.project_id)
    (root / 'shot.png').write_bytes(b'fake image')
    created = []
    def create(email, project_id, body):
        assert asyncio.get_running_loop() is loop
        created.append(body)
        return store.save_export_job(email, ExportJob(id='e' * 32, project_id=project_id, request=body))
    monkeypatch.setattr(jobs, 'create_export_job', create)
    payload = {'idempotency_key': 'local-export-1', 'clips': [{'asset_path': 'shot.png', 'duration': 3}]}
    result = business.execute('exportJobs', {'action': 'submit', 'request': payload})
    assert result['job']['id'] == 'e' * 32
    assert business.execute('exportJobs', {'action': 'submit', 'request': payload})['reused']
    assert len(created) == 1


def test_status_and_cancel_jobs_run_on_original_api_loop(business, api_loop, monkeypatch):
    from app.video_studio import media_jobs
    loop, business.invoke_async = api_loop
    job = store.save_media_job(business.email, MediaJob(id='b' * 32, project_id=business.project_id, request=request()))
    seen = []
    def action(email, project_id, job_id):
        assert asyncio.get_running_loop() is loop
        seen.append(job_id)
        return job
    monkeypatch.setattr(media_jobs, 'ensure_media_job_running', action)
    monkeypatch.setattr(media_jobs, 'cancel_media_job', action)
    assert business.execute('mediaJobs', {'action': 'status', 'job_id': job.id})['job']['status'] == 'queued'
    assert business.execute('mediaJobs', {'action': 'cancel', 'job_id': job.id})['job']['id'] == job.id
    assert seen == [job.id, job.id]
    business.permissions = {'canvas': True, 'destructive': False}
    with pytest.raises(ValueError, match='cancellation'):
        business.execute('mediaJobs', {'action': 'cancel', 'job_id': job.id})


def test_attach_completed_job_uses_authenticated_workspace_path(business):
    root = store.assets_root(business.email, business.project_id)
    (root / 'result.png').write_bytes(b'image')
    job = store.save_media_job(business.email, MediaJob(id='b' * 32, project_id=business.project_id, request=request(),
        status='completed', result_asset_path='result.png', result_mime_type='image/png'))
    result = business.execute('mediaJobs', {'action': 'attach', 'job_id': job.id})
    assert result['status'] == 'staged_pending_commit'
    node = business.canvas_tools.canvas.nodes[-1]
    assert node.data['outputs']['image']['value'] == {'url': 'result.png', 'mimeType': 'image/png'}
    with pytest.raises(ValueError, match='incompatible'):
        business.execute('mediaJobs', {'action': 'attach', 'job_id': job.id, 'node_id': 'missing'})
    assert len(business.canvas_tools.canvas.nodes) == 1
    target = business.canvas_tools.execute('addNode', {'type': 'imageGenerationNode', 'position': {'x': 20, 'y': 0}})['node']['id']
    # Disabling a primitive image node does not disable an enabled generation
    # node's existing output; creating a new image node still remains forbidden.
    business.canvas_tools.enabled_types.remove('image')
    assert business.execute('mediaJobs', {'action': 'attach', 'job_id': job.id, 'node_id': target})['node_id'] == target
    with pytest.raises(ValueError, match='disabled'):
        business.execute('mediaJobs', {'action': 'attach', 'job_id': job.id})


def test_media_processing_has_fixed_commands_limits_and_no_private_paths(business, monkeypatch):
    from app.video_studio import render
    root = store.assets_root(business.email, business.project_id)
    (root / 'source.mp4').write_bytes(b'video')
    commands = []
    def run(command, asset_root, *, timeout):
        commands.append(command)
        assert asset_root == root
        assert timeout == 120 and 'file,pipe' in command
        from pathlib import Path
        Path(command[-1]).write_bytes(b'processed')
    monkeypatch.setattr(business, '_run_media_process', run)
    result = business.execute('mediaProcess', {'action': 'trim', 'path': 'source.mp4', 'start': 1, 'duration': 3})
    assert result['status'] == 'completed' and result['asset_path'].startswith('processed/trim-')
    assert commands[0][commands[0].index('-t') + 1] == '3'
    for args in [{'action': 'trim', 'path': 'source.mp4'}, {'action': 'resize', 'path': 'source.mp4', 'width': 321, 'height': 240},
                 {'action': 'trim', 'path': 'source.mp4', 'duration': float('nan')}, {'action': 'custom', 'path': 'source.mp4'}]:
        with pytest.raises(ValueError):
            business.execute('mediaProcess', args)
    assert len(commands) == 1
    monkeypatch.setattr(render, 'probe_asset', lambda *args: {'format': {'filename': '/private/server/source.mp4', 'duration': '3'}})
    probed = business.execute('mediaProcess', {'action': 'probe', 'path': 'source.mp4'})
    assert 'filename' not in probed['metadata']['format']


def test_domain_authority_does_not_require_canvas_mutation_for_generation_or_documents(business, api_loop, monkeypatch):
    loop, business.invoke_async = api_loop
    fake_generation(monkeypatch, loop)
    business.permissions = {'canvas': False, 'workspace': True, 'media': True}
    definitions = {item['name']: item['parameters'] for item in business.definitions(readonly=True)}
    assert 'create' in definitions['workspaceDocuments']['properties']['action']['enum']
    assert 'create' not in definitions['canvasManager']['properties']['action']['enum']
    assert 'submit' in definitions['mediaJobs']['properties']['action']['enum']
    assert business.execute('workspaceDocuments', {'action': 'create', 'path': 'brief.md', 'text': 'Brief'})['status'] == 'saved'
    business.ask = lambda *args: {'answer': '批准并提交'}
    assert business.execute('mediaJobs', {'action': 'submit', 'request': request()})['job']['id'] == 'b' * 32


def test_interrupted_paid_question_can_be_asked_again_without_submission(business, api_loop, monkeypatch):
    loop, business.invoke_async = api_loop
    created = fake_generation(monkeypatch, loop)
    def interrupted(*args):
        raise InterruptedError('Run cancelled')
    business.ask = interrupted
    with pytest.raises(InterruptedError):
        business.execute('mediaJobs', {'action': 'submit', 'request': request()})
    assert created == []
    business.ask = lambda *args: {'answer': '批准并提交'}
    assert business.execute('mediaJobs', {'action': 'submit', 'request': request()})['job']['id'] == 'b' * 32
    assert len(created) == 1


def test_resource_revision_does_not_allow_stale_aba_overwrites(business):
    initial = business.resource_read('memory')
    second = business.resource_write('memory', 'A', initial['revision'])
    restored = business.resource_write('memory', '', second['revision'])
    assert restored['revision'] != initial['revision']
    with pytest.raises(DocumentConflict):
        business.resource_write('memory', 'Stale overwrite', initial['revision'])


def test_processing_cancellation_terminates_the_fixed_media_subprocess(business, monkeypatch):
    from pathlib import Path
    root = store.assets_root(business.email, business.project_id)
    (root / 'source.mp4').write_bytes(b'video')
    children = []
    class Process:
        def __init__(self, command, **kwargs):
            self.terminated = False
            self.returncode = None
            Path(command[-1]).write_bytes(b'partial output')
            children.append(self)
        def poll(self):
            return None
        def terminate(self):
            self.terminated = True
        def wait(self, timeout):
            return 0
    monkeypatch.setattr('app.video_studio.pi_business.subprocess.Popen', Process)
    checks = 0
    def check():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise InterruptedError('Cancelled')
    business.control.check = check
    with pytest.raises(InterruptedError):
        business.execute('mediaProcess', {'action': 'trim', 'path': 'source.mp4', 'duration': 3})
    assert children[0].terminated
    assert list((root / 'processed').iterdir()) == []


def configure_remote(business, monkeypatch):
    monkeypatch.setattr('app.video_studio.research_tools._assert_public_url', lambda url: url)
    before = business.resource_read('team')
    business.resource_write('team', json.dumps({'remote_agents': [{'id': 'writer', 'name': 'External writer', 'url': 'https://configured.example/a2a'}]}), before['revision'])


def test_remote_transmission_requires_exact_user_approval_and_never_accepts_arbitrary_url(business, monkeypatch):
    configure_remote(business, monkeypatch)
    calls, questions = [], []
    business.ask = lambda call, question: questions.append(question) or {'answer': '取消'}
    monkeypatch.setattr(business, '_remote_rpc', lambda *args: calls.append(args))
    result = business.execute('remoteTeam', {'action': 'send', 'target_id': 'writer', 'text': 'Write an original scene', 'idempotency_key': 'remote-task-1'})
    assert result['status'] == 'approval_denied' and not calls
    assert questions[0]['outboundRequest']['request']['target']['url'] == 'https://configured.example/a2a'
    assert 'Write an original scene' in questions[0]['question']
    with pytest.raises(ValueError):
        business.execute('remoteTeam', {'action': 'send', 'url': 'https://arbitrary.example', 'text': 'Task', 'idempotency_key': 'remote-task-2'})


def test_remote_receipts_bind_exact_task_and_uncertain_requests_never_replay(business, monkeypatch):
    configure_remote(business, monkeypatch)
    calls = []
    business.ask = lambda *args: {'answer': '批准并发送'}
    def rpc(url, method, params):
        calls.append((url, method, params))
        return {'kind': 'task', 'id': 'task-1', 'status': {'state': 'working'}}
    monkeypatch.setattr(business, '_remote_rpc', rpc)
    payload = {'action': 'send', 'target_id': 'writer', 'text': 'Original script', 'idempotency_key': 'remote-task-1'}
    first = business.execute('remoteTeam', payload)
    assert first['status'] == 'sent' and calls[0][1] == 'message/send'
    assert calls[0][2]['configuration']['blocking'] is False
    assert calls[0][2]['message']['parts'] == [{'kind': 'text', 'text': 'Original script'}]
    assert business.execute('remoteTeam', payload)['reused'] and len(calls) == 1
    with pytest.raises(DocumentConflict):
        business.execute('remoteTeam', {**payload, 'text': 'Changed script'})
    assert business.execute('remoteTeam', {'action': 'status', 'receipt_id': first['receipt_id']})['result']['id'] == 'task-1'
    assert calls[-1][1] == 'tasks/get'
    business.ask = lambda *args: {'answer': '取消'}
    assert business.execute('remoteTeam', {'action': 'cancel', 'receipt_id': first['receipt_id']})['status'] == 'approval_denied'
    assert len(calls) == 2
    business.ask = lambda *args: {'answer': '批准并发送'}
    def failure(*args):
        calls.append('uncertain')
        raise TimeoutError('External response timed out')
    monkeypatch.setattr(business, '_remote_rpc', failure)
    uncertain_payload = {**payload, 'idempotency_key': 'remote-task-2'}
    with pytest.raises(TimeoutError):
        business.execute('remoteTeam', uncertain_payload)
    assert business.execute('remoteTeam', uncertain_payload)['status'] == 'uncertain'
    assert calls.count('uncertain') == 1


def test_remote_http_uses_pinned_transport_bounded_json_and_rejects_protocol_errors(business, monkeypatch):
    import httpx
    from app.video_studio.website_assets import PublicMediaTransport
    requests = []
    class Client:
        def __init__(self, **kwargs):
            assert isinstance(kwargs['transport'], PublicMediaTransport)
            assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def stream(self, method, url, *, json, headers):
            assert method == 'POST' and json['jsonrpc'] == '2.0'
            requests.append(json)
            return httpx.Response(200, headers={'content-type': 'application/json'}, json={'jsonrpc': '2.0', 'id': json['id'],
                'result': {'kind': 'message', 'role': 'agent', 'messageId': 'reply-1', 'parts': [{'kind': 'text', 'text': 'Original scene'}]}})
    class ResponseContext:
        def __init__(self, response):
            self.response = response
        def __enter__(self):
            return self.response
        def __exit__(self, *args):
            self.response.close()
    original = Client.stream
    monkeypatch.setattr(Client, 'stream', lambda self, *args, **kwargs: ResponseContext(original(self, *args, **kwargs)))
    monkeypatch.setattr(httpx, 'Client', Client)
    assert business._remote_rpc('https://configured.example/a2a', 'message/send', {})['kind'] == 'message'
    assert len(requests) == 1
    monkeypatch.setattr(Client, 'stream', lambda *args, **kwargs: ResponseContext(httpx.Response(200,
        headers={'content-type': 'application/json'}, json={'jsonrpc': '2.0', 'id': 'wrong-id', 'result': {'kind': 'task'}})))
    with pytest.raises(ValueError, match='invalid JSON-RPC'):
        business._remote_rpc('https://configured.example/a2a', 'message/send', {})
    monkeypatch.setattr(Client, 'stream', lambda *args, **kwargs: ResponseContext(httpx.Response(302, headers={'location': 'https://127.0.0.1'})))
    with pytest.raises(ValueError, match='HTTP 302'):
        business._remote_rpc('https://configured.example/a2a', 'message/send', {})
    monkeypatch.setattr(Client, 'stream', lambda *args, **kwargs: ResponseContext(httpx.Response(200,
        headers={'content-type': 'application/json'}, content=b'x' * 200_001)))
    with pytest.raises(ValueError, match='response budget'):
        business._remote_rpc('https://configured.example/a2a', 'message/send', {})


@pytest.mark.parametrize('language', ['zh-CN', 'en-US'])
@pytest.mark.parametrize('decision', ['approve', 'cancel', 'skip', 'ambiguous', 'wrong_action', 'wrong_language'])
def test_media_approval_follows_account_language_and_exact_visible_choice(business, api_loop, monkeypatch, language, decision):
    settings = store.get_settings(business.email)
    store.save_settings(business.email, settings.model_copy(update={'language': language}))
    loop, business.invoke_async = api_loop
    created = fake_generation(monkeypatch, loop)
    questions = []
    def ask(call, question):
        questions.append(question)
        # Changing settings while a card is open must not change its approval meaning.
        store.save_settings(business.email, settings.model_copy(update={'language': 'zh-CN' if language.startswith('en') else 'en-US'}))
        return {'approve': {'answer': question['options'][0]},
                'cancel': {'answer': question['options'][1]},
                'skip': {'skipped': True, 'answer': question['options'][0]},
                'ambiguous': {'answer': 'yes'},
                'wrong_action': {'answer': 'Approve and send'},
                'wrong_language': {'answer': '批准并提交' if language.startswith('en') else 'Approve and submit'}}[decision]
    business.ask = ask
    result = business.execute('mediaJobs', {'action': 'submit', 'request': request()}, tool_call_id='locale-media')
    question = questions[0]
    if language.startswith('en'):
        assert question['title'] == 'Approve media generation'
        assert question['options'] == ['Approve and submit', 'Cancel']
        assert not any('\u4e00' <= char <= '\u9fff' for char in json.dumps(question, ensure_ascii=False))
        assert 'cost is currently unknown' in question['question']
    else:
        assert question['title'] == '批准媒体生成'
        assert question['options'] == ['批准并提交', '取消']
    assert question['paidRequest']['request']['prompt'] == request()['prompt']
    assert len(created) == (1 if decision == 'approve' else 0)
    if decision != 'approve':
        assert result['status'] == 'approval_denied'


@pytest.mark.parametrize('language', ['zh-CN', 'en-US'])
@pytest.mark.parametrize('decision', ['approve', 'cancel', 'skip', 'ambiguous'])
def test_external_send_and_cancel_use_localized_exact_approval(business, monkeypatch, language, decision):
    configure_remote(business, monkeypatch)
    settings = store.get_settings(business.email).model_copy(update={'language': language})
    store.save_settings(business.email, settings)
    questions, calls = [], []
    def ask(call, question):
        questions.append(question)
        return {'approve': {'values': {'choice': question['options'][0]}},
                'cancel': {'answer': question['options'][1]},
                'skip': {'skipped': True}, 'ambiguous': {'answer': 'yes'}}[decision]
    business.ask = ask
    def rpc(url, method, params):
        calls.append(method)
        return {'kind': 'task', 'id': 'locale-task', 'status': {'state': 'working'}}
    monkeypatch.setattr(business, '_remote_rpc', rpc)
    payload = {'action': 'send', 'target_id': 'writer', 'text': 'Original task', 'idempotency_key': 'locale-remote'}
    result = business.execute('remoteTeam', payload)
    question = questions[0]
    if language.startswith('en'):
        assert question['title'] == 'Approve external agent collaboration'
        assert question['options'] == ['Approve and send', 'Cancel']
        assert not any('\u4e00' <= char <= '\u9fff' for char in json.dumps(question, ensure_ascii=False))
    else:
        assert question['title'] == '批准外部代理协作'
        assert question['options'] == ['批准并发送', '取消']
    assert calls == (['message/send'] if decision == 'approve' else [])
    if decision != 'approve':
        assert result['status'] == 'approval_denied'
        # Seed a separate approved task, then exercise the chosen cancel decision.
        business.ask = lambda call, question: {'answer': question['options'][0]}
        result = business.execute('remoteTeam', {**payload, 'idempotency_key': 'seed-task'})
        business.ask = ask
    before = len(calls)
    cancelled = business.execute('remoteTeam', {'action': 'cancel', 'receipt_id': result['receipt_id']})
    assert calls[before:] == (['tasks/cancel'] if decision == 'approve' else [])
    if language.startswith('en'):
        assert questions[-1]['title'] == 'Cancel external agent task'
        assert 'configured external agent' in questions[-1]['question']
    else:
        assert questions[-1]['title'] == '取消外部代理任务'
    if decision != 'approve':
        assert cancelled['status'] == 'approval_denied'


def test_localized_approval_preserves_customer_request_and_account_isolation(business):
    settings = store.get_settings(business.email)
    store.save_settings(business.email, settings.model_copy(update={'language': 'en-US'}))
    copy = business._approval_copy('remote_cancel', target_name='客户代理', task_id='task-1')
    assert copy['title'] == 'Cancel external agent task'
    assert '客户代理' in copy['question']
    other_project = store.create_project('another@example.com', ProjectCreate(name='Separate locale'))
    other = BusinessTools('another@example.com', other_project.id, business.conversation_id, business.control, business.canvas_tools)
    assert other._approval_copy('media')['title'] == '批准媒体生成'


def test_media_submit_uses_deployment_default_before_exact_paid_approval(business, api_loop, monkeypatch):
    loop, business.invoke_async = api_loop
    created = fake_generation(monkeypatch, loop)
    configured = [{'type': 'image', 'providerId': 'configured', 'modelId': 'configured-image', 'isDefault': True}]
    monkeypatch.setattr('app.routers.video_runtime.configured_media_models', lambda: configured)
    questions = []
    business.ask = lambda call, question: questions.append(question) or {'answer': '批准并提交'}
    payload = request()
    del payload['provider_id'], payload['model_id']
    result = business.execute('mediaJobs', {'action': 'submit', 'request': payload})
    assert result['job']['id'] == 'b' * 32
    assert (created[0].provider_id, created[0].model_id) == ('configured', 'configured-image')
    assert 'configured-image' in json.dumps(questions)
    assert 'configured-image' in business.media_context()


def test_media_default_missing_does_not_request_approval(business, monkeypatch):
    monkeypatch.setattr('app.routers.video_runtime.configured_media_models', lambda: [])
    business.ask = lambda *args: pytest.fail('No paid approval when deployment has no model')
    payload = request()
    del payload['provider_id'], payload['model_id']
    with pytest.raises(ValueError, match='No configured image|未配置图片默认模型'):
        business.execute('mediaJobs', {'action': 'submit', 'request': payload})


@pytest.mark.parametrize('language', ['en-US', 'zh-CN'])
def test_media_partial_override_never_asks_approval_and_error_is_localized(business, monkeypatch, language):
    from app.video_studio.models import VideoStudioSettings
    store.save_settings(business.email, VideoStudioSettings(language=language))
    business.ask = lambda *args: pytest.fail('Partial model override must fail before approval')
    payload = request()
    del payload['model_id']
    with pytest.raises(ValueError) as failure:
        business.execute('mediaJobs', {'action': 'submit', 'request': payload})
    assert str(failure.value).startswith('Specify both' if language.startswith('en') else '请同时指定')


def test_disabled_media_context_does_not_advertise_generation(business, monkeypatch):
    business.enabled_extensions = {'tool-workspace'}
    monkeypatch.setattr('app.routers.video_runtime.configured_media_models', lambda: pytest.fail('Disabled generation must not be advertised'))
    assert '"generation_enabled": false' in business.media_context()
    assert '"models": []' in business.media_context()
