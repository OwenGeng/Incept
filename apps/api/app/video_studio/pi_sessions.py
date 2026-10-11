"""Durable, private SDK snapshots; JSONL interpretation remains Pi's job."""
import hashlib
import re
import uuid
from pathlib import Path

from . import metadata_repository, store

MAX_SESSION_BYTES = 64 * 1024 * 1024


def _key(email, project_id, conversation_id, filename):
    store._conversation_path(email, project_id, conversation_id)  # Ownership/IDs.
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}\.jsonl', filename):
        raise ValueError('Invalid SDK snapshot filename')
    # Outside users/projects, so project listing does not retrieve large private
    # tool histories. This key is never an accessible workspace asset path.
    return f'pi-sessions/{store._user_key(email)}/{project_id}/{conversation_id}/{filename}'


def _local_snapshot(email, project_id, conversation_id, filename):
    root = store._project_root(email, project_id) / '.agent' / 'pi'
    return store.safe_asset_path(root, f'{conversation_id}/snapshots/{filename}')


def _write_local(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
    try:
        with temporary.open('xb') as output:
            temporary.chmod(0o600)
            output.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _legacy_child_snapshot(email, project_id, conversation_id, filename):
    # Older local installations saved delegated SDK journals only under their
    # parent. Derive that owned location from canonical IDs, never a supplied
    # absolute path or reconstructed conversation text.
    try:
        conversation = store.get_conversation(email, project_id, conversation_id)
    except FileNotFoundError:
        return None
    match = re.fullmatch(r'agent/([a-f0-9]{32})\.json', conversation.parent_file or '')
    if not match:
        return None
    store.get_conversation(email, project_id, match[1])
    root = store._project_root(email, project_id) / '.agent' / 'pi'
    source = store.safe_asset_path(root, f'{match[1]}/children/{conversation_id}/{filename}')
    return source if source.is_file() else None


def restore_snapshot(email, project_id, conversation_id, directory, filename):
    key = _key(email, project_id, conversation_id, filename)
    path = store.safe_asset_path(directory, filename)
    saved = metadata_repository.read(key)
    if saved is not None:
        if not isinstance(saved, dict) or not isinstance(saved.get('jsonl'), str):
            raise ValueError('Invalid durable Pi snapshot; existing conversation retained')
        data = saved['jsonl'].encode('utf-8')
        if len(data) > MAX_SESSION_BYTES or hashlib.sha256(data).hexdigest() != saved.get('sha256'):
            raise ValueError('Invalid durable Pi snapshot size or checksum')
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != saved['sha256']:
            _write_local(path, data)
    else:
        snapshot = _local_snapshot(email, project_id, conversation_id, filename)
        source = snapshot if snapshot.is_file() else None
        if source is None and not path.is_file():
            source = _legacy_child_snapshot(email, project_id, conversation_id, filename)
        if source is not None:
            if source.stat().st_size > MAX_SESSION_BYTES:
                raise ValueError('Pi history exceeded the 64 MiB storage budget')
            data = source.read_bytes()
            if not path.is_file() or path.read_bytes() != data:
                _write_local(path, data)
            if source != snapshot:
                _write_local(snapshot, data)
    if not path.is_file() or path.stat().st_size > MAX_SESSION_BYTES:
        raise ValueError('Pi history snapshot is unavailable; conversation retained. Restore the snapshot before retrying.')
    return str(path)


def save_snapshot(email, project_id, conversation_id, path):
    path = Path(path)
    key = _key(email, project_id, conversation_id, path.name)
    if path.stat().st_size > MAX_SESSION_BYTES:
        raise ValueError('Pi history exceeded the 64 MiB storage budget; current attempt retained but not committed.')
    data = path.read_bytes()
    snapshot = {'jsonl': data.decode('utf-8'), 'sha256': hashlib.sha256(data).hexdigest()}
    metadata_repository.write(key, snapshot)
    # The database may be intentionally disabled. Keep a committed private
    # snapshot under the child identity, independent of its execution folder.
    _write_local(_local_snapshot(email, project_id, conversation_id, path.name), data)


def release_previous_snapshot(email, project_id, conversation_id, filename):
    # Invoke only after the new canonical conversation points at a fully durable
    # SDK branch. It contains the retained history; local source JSONL is kept.
    if filename:
        metadata_repository.delete(_key(email, project_id, conversation_id, filename))
        _local_snapshot(email, project_id, conversation_id, filename).unlink(missing_ok=True)
