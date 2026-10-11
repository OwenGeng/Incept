from pathlib import Path

import pytest

from app.video_studio import pi_agent, pi_sessions, store
from app.video_studio.models import ProjectCreate
from test_video_pi_agent import reply, EMAIL, run


@pytest.fixture
def persisted(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    records = {}
    monkeypatch.setattr(pi_sessions.metadata_repository, 'read', lambda key: records.get(key))
    monkeypatch.setattr(pi_sessions.metadata_repository, 'write', lambda key, value: records.update({key: value}))
    monkeypatch.setattr(pi_sessions.metadata_repository, 'delete', lambda key: records.pop(key, None))
    def delete_prefix(prefix):
        for key in list(records):
            if key == prefix or key.startswith(prefix + '/'):
                records.pop(key)
    monkeypatch.setattr(pi_sessions.metadata_repository, 'delete_prefix', delete_prefix)
    monkeypatch.setattr(pi_sessions.metadata_repository, 'list_prefix', lambda prefix: [
        (key, value) for key, value in records.items() if key == prefix or key.startswith(prefix + '/')])
    return records


def test_sdk_restores_from_database_after_local_instance_cache_is_lost(persisted, monkeypatch):
    project = store.create_project(EMAIL, ProjectCreate(name='Durable Pi'))
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: reply(p, '3W Bronco approved 30-second draft.'))
    first, _, _ = run(project, '3W Bronco 30 seconds')
    path = pi_agent.session_directory(EMAIL, project.id, first.id) / first.pi_session_file
    original = path.read_bytes()
    path.unlink()  # Test-only cache loss, not deleting production history.
    seen = []
    def model(p, **k):
        seen.append(str(p['context']['messages']))
        return reply(p, 'Continue the 30-second draft.')
    monkeypatch.setattr(pi_agent, 'model_response', model)
    second, _, _ = run(project, 'Continue.', first.id)
    assert path.read_bytes() == original
    assert '3W Bronco' in seen[-1]
    snapshots = [key for key in persisted if key.startswith('pi-sessions/')]
    assert len(snapshots) == 1 and snapshots[0].endswith(second.pi_session_file)
    assert not any('pi-sessions/' in key for key in persisted if key.startswith('users/'))


def test_missing_corrupt_or_traversal_snapshot_fails_closed(persisted, tmp_path):
    project = store.create_project(EMAIL, ProjectCreate(name='Snapshot boundary'))
    directory = tmp_path / 'sessions'
    directory.mkdir()
    with pytest.raises(ValueError, match='unavailable'):
        pi_sessions.restore_snapshot(EMAIL, project.id, 'a'*32, directory, 'missing.jsonl')
    with pytest.raises(ValueError, match='filename'):
        pi_sessions.restore_snapshot(EMAIL, project.id, 'a'*32, directory, '../foreign.jsonl')
    path = directory / 'valid.jsonl'
    path.write_text('{"type":"session"}\n')
    pi_sessions.save_snapshot(EMAIL, project.id, 'a'*32, path)
    key = next(key for key in persisted if key.startswith('pi-sessions/'))
    persisted[key]['sha256'] = 'corrupt'
    with pytest.raises(ValueError, match='checksum'):
        pi_sessions.restore_snapshot(EMAIL, project.id, 'a'*32, directory, path.name)
    persisted[key] = {'jsonl': 42}
    with pytest.raises(ValueError, match='Invalid durable'):
        pi_sessions.restore_snapshot(EMAIL, project.id, 'a'*32, directory, path.name)


def test_snapshot_storage_budget_preserves_existing_metadata(persisted, tmp_path, monkeypatch):
    project = store.create_project(EMAIL, ProjectCreate(name='Storage budget'))
    path = tmp_path / 'big.jsonl'
    path.write_text('oversized')
    monkeypatch.setattr(pi_sessions, 'MAX_SESSION_BYTES', 2)
    before = dict(persisted)
    with pytest.raises(ValueError, match='storage budget'):
        pi_sessions.save_snapshot(EMAIL, project.id, 'a'*32, path)
    assert persisted == before


def test_conversation_listing_restores_after_cache_loss_and_delete_cleans_private_history(persisted, monkeypatch):
    project = store.create_project(EMAIL, ProjectCreate(name='List/delete durability'))
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **k: reply(p, 'Saved reply.'))
    conversation, _, _ = run(project, 'Hello')
    path = store._conversation_path(EMAIL, project.id, conversation.id)
    path.unlink()
    restored = store.list_conversations(EMAIL, project.id)
    assert len(restored) == 1 and restored[0].id == conversation.id
    assert path.is_file()
    directory = pi_agent.session_directory(EMAIL, project.id, conversation.id)
    assert directory.is_dir()
    store.delete_conversation(EMAIL, project.id, conversation.id)
    assert not directory.exists()
    assert not any(key.startswith('pi-sessions/') for key in persisted)
    assert store.list_conversations(EMAIL, project.id) == []
