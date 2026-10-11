"""Five authenticated accounts exercise the native host and real Pi SDK.

Only provider responses and durable database storage are synthetic. Host IPC,
session construction, tools, cancellation and journal persistence are real.
"""
import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.video_studio import metadata_repository, pi_agent, pi_runs, store
from app.video_studio.agent_turns import AgentCancelled, cancel_turn, prepare_turn
from app.video_studio.models import ProjectCreate
from test_video_pi_agent import call, reply


@pytest.fixture
def five_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    records = {}
    monkeypatch.setattr(metadata_repository, 'write', lambda key, value: records.__setitem__(key, value))
    monkeypatch.setattr(metadata_repository, 'read', lambda key: records.get(key))
    monkeypatch.setattr(metadata_repository, 'delete', lambda key: records.pop(key, None))
    accounts = []
    for index in range(5):
        email = f'native-acceptance-{index}@example.com'
        marker = f'PRIVATE_NATIVE_ACCOUNT_{index}'
        project = store.create_project(email, ProjectCreate(name=f'Native acceptance {index}'))
        store.assets_root(email, project.id).joinpath('brief.md').write_text(marker)
        conversation = prepare_turn(email=email, project_id=project.id,
            prompt=f'Read brief.md and return only my marker {marker}.', conversation_id=None)
        journal = pi_runs.RunJournal(email, project.id, conversation.id, conversation.run_id)
        journal.create()
        accounts.append((email, marker, project, conversation, journal))
    return accounts


def execute(account):
    email, _, project, conversation, journal = account
    result = pi_agent.run_agent(email=email, project_id=project.id,
        prompt=conversation.messages[-1].content, conversation_id=conversation.id,
        prepared_conversation=conversation, journal=journal, progress=journal.emit)
    journal.finish('completed')
    return result


def test_five_accounts_share_one_native_host_without_context_tool_or_event_leaks(five_accounts, monkeypatch):
    from app.video_studio import native_host
    barrier = threading.Barrier(5)
    identities = []
    identity_lock = threading.Lock()

    def provider(payload, **kwargs):
        messages = payload['context']['messages']
        own = [account for account in five_accounts if account[1] in json.dumps(messages)]
        assert len(own) == 1, 'Each native session must receive exactly one account context'
        marker = own[0][1]
        receipts = [m for m in messages if m['role'] == 'toolResult']
        if not receipts:
            with identity_lock:
                identities.append(native_host.host_identity())
            barrier.wait(timeout=20)
            # Deliberately identical tool-call IDs across all five runs.
            return reply(payload, calls=[call('workspaceDocuments', {'action': 'read', 'path': 'brief.md'})])
        assert marker in json.dumps(receipts)
        assert not any(other[1] in json.dumps(receipts) for other in five_accounts if other[1] != marker)
        return reply(payload, marker)

    monkeypatch.setattr(pi_agent, 'model_response', provider)
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(execute, five_accounts))
    assert len(identities) == 5
    assert len({identity['pid'] for identity in identities}) == 1
    assert len({identity['generation'] for identity in identities}) == 1
    snapshot_names = set()
    for account, (conversation, _, text) in zip(five_accounts, results):
        email, marker, project, _, journal = account
        assert text == marker and conversation.run_status == 'completed'
        assert all(message.pi_entry_id for message in conversation.messages)
        snapshot = pi_agent.session_directory(email, project.id, conversation.id) / conversation.pi_session_file
        snapshot_names.add(str(snapshot))
        assert snapshot.is_file()
        rendered = json.dumps(journal.events())
        assert all(event['runId'] == conversation.run_id for event in journal.events())
        assert marker in rendered
        assert not any(other[1] in rendered for other in five_accounts if other[1] != marker)
        with pytest.raises(FileNotFoundError):
            store.get_conversation(five_accounts[(five_accounts.index(account) + 1) % 5][0], project.id, conversation.id)
    assert len(snapshot_names) == 5


def test_cancelling_one_of_five_native_runs_preserves_other_users_and_the_host(five_accounts, monkeypatch):
    from app.video_studio import native_host
    barrier = threading.Barrier(5)
    release = threading.Event()
    entered = threading.Event()
    count = 0
    lock = threading.Lock()

    def provider(payload, emit=None, check_cancel=None, **kwargs):
        nonlocal count
        messages = json.dumps(payload['context']['messages'])
        own = next(account for account in five_accounts if account[1] in messages)
        with lock:
            count += 1
            if count == 5:
                entered.set()
        barrier.wait(timeout=20)
        if emit:
            emit({'type': 'text_delta', 'delta': own[1]})
        deadline = time.monotonic() + 20
        while not release.wait(.05):
            if check_cancel:
                check_cancel()
            assert time.monotonic() < deadline, 'Acceptance control did not release the provider'
        if check_cancel:
            check_cancel()
        return reply(payload, own[1])

    monkeypatch.setattr(pi_agent, 'model_response', provider)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(execute, account) for account in five_accounts]
        assert entered.wait(20), 'All five native sessions must execute concurrently'
        before = native_host.host_identity()
        email, _, project, conversation, _ = five_accounts[0]
        cancel_turn(email, project.id, conversation.id, conversation.run_id)
        release.set()
        with pytest.raises(AgentCancelled):
            futures[0].result(timeout=20)
        for account, future in zip(five_accounts[1:], futures[1:]):
            completed, _, text = future.result(timeout=20)
            assert completed.run_status == 'completed' and text == account[1]
    assert native_host.host_identity() == before
    assert store.get_conversation(email, project.id, conversation.id).run_status == 'cancelled'


def test_real_native_sdk_restores_committed_context_after_host_and_local_cache_loss(five_accounts, monkeypatch):
    from app.video_studio import native_host
    account = five_accounts[0]
    email, marker, project, _, _ = account
    requests = []

    def provider(payload, **kwargs):
        requests.append(payload['context']['messages'])
        return reply(payload, f'{marker}: retained SDK reply')

    monkeypatch.setattr(pi_agent, 'model_response', provider)
    previous, _, _ = execute(account)
    identity = native_host.host_identity()
    native_host.shutdown_host()
    shutil.rmtree(pi_agent.session_directory(email, project.id, previous.id))
    continued = prepare_turn(email=email, project_id=project.id,
        prompt='Continue after process and local journal loss.', conversation_id=previous.id)
    journal = pi_runs.RunJournal(email, project.id, continued.id, continued.run_id)
    journal.create()
    completed, _, text = execute((email, marker, project, continued, journal))
    assert native_host.host_identity()['generation'] != identity['generation']
    assert f'{marker}: retained SDK reply' in json.dumps(requests[-1])
    assert requests[-1][0]['role'] == 'user'
    assert completed.messages[0].pi_entry_id == previous.messages[0].pi_entry_id
    assert completed.messages[1].pi_entry_id == previous.messages[1].pi_entry_id
    assert len(completed.messages) == 4 and completed.run_status == 'completed'
    assert marker in text
