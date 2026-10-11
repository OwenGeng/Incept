from concurrent.futures import ThreadPoolExecutor
import hashlib

import pytest

from test_video_legacy_api import client, headers


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    directory = api.post('/video-legacy/api/workspaces/create', json={'name': 'Document safety'}, headers=headers()).json()['data']['directory']
    return api, {'directory': directory, 'path': 'research/brief.md'}


def write(api, params, content):
    return api.put('/video-legacy/api/workspaces/files/write', params=params, content=content, headers={**headers(), 'content-type': 'application/octet-stream'})


def snapshot(api, params):
    return api.get('/video-legacy/api/workspaces/files/read', params={**params, 'snapshot': True}, headers=headers())


def test_stale_document_save_preserves_new_disk_content(workspace):
    api, params = workspace
    assert write(api, params, b'original').status_code == 200
    original = snapshot(api, params).json()['data']
    assert original == {'text': 'original', 'revision': hashlib.sha256(b'original').hexdigest(), 'encoding': 'utf-8'}
    assert write(api, params, b'agent updated').status_code == 200
    stale = write(api, {**params, 'expectedRevision': original['revision']}, b'old editor draft')
    assert stale.status_code == 409
    assert stale.json()['detail']['code'] == 'ESTALE'
    assert snapshot(api, params).json()['data']['text'] == 'agent updated'


def test_successful_saves_advance_revision_and_only_one_concurrent_save_wins(workspace):
    api, params = workspace
    write(api, params, b'original')
    revision = snapshot(api, params).json()['data']['revision']
    conditional = {**params, 'expectedRevision': revision}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda text: write(api, conditional, text), [b'first', b'second']))
    assert sorted(result.status_code for result in results) == [200, 409]
    winner = next(result for result in results if result.status_code == 200)
    new_revision = winner.json()['data']['revision']
    assert new_revision != revision
    next_save = write(api, {**params, 'expectedRevision': new_revision}, b'next')
    assert next_save.status_code == 200
    assert snapshot(api, params).json()['data']['text'] == 'next'


@pytest.mark.parametrize('encoding,prefix,codec', [('utf-8-bom', b'\xef\xbb\xbf', 'utf-8'), ('utf-16le', b'\xff\xfe', 'utf-16-le'), ('utf-16be', b'\xfe\xff', 'utf-16-be')])
def test_text_snapshot_preserves_encoding(workspace, encoding, prefix, codec):
    api, params = workspace
    write(api, params, prefix + '方案'.encode(codec))
    before = snapshot(api, params).json()['data']
    assert before['text'] == '方案'
    assert before['encoding'] == encoding
    saved = write(api, {**params, 'expectedRevision': before['revision'], 'encoding': encoding}, '新方案'.encode())
    assert saved.status_code == 200
    raw = api.get('/video-legacy/api/workspaces/files/read', params=params, headers=headers())
    assert raw.content == prefix + '新方案'.encode(codec)


def test_snapshot_rejects_binary_oversize_and_invalid_revision(workspace):
    api, params = workspace
    write(api, params, b'\x00\xff\x00')
    assert snapshot(api, params).status_code == 400
    write(api, params, b'hello')
    assert snapshot(api, {**params, 'maxBytes': 2}).status_code == 413
    assert write(api, {**params, 'expectedRevision': 'bad'}, b'overwrite').status_code == 422
    assert snapshot(api, params).json()['data']['text'] == 'hello'


def test_save_deleted_file_is_a_conflict_not_a_recreation(workspace):
    api, params = workspace
    write(api, params, b'original')
    revision = snapshot(api, params).json()['data']['revision']
    assert api.request('DELETE', '/video-legacy/api/workspaces/files/remove', json=params, headers=headers()).status_code == 200
    assert write(api, {**params, 'expectedRevision': revision}, b'draft').status_code == 409
    assert snapshot(api, params).status_code == 404


def test_text_save_limits_encoded_size_and_rejects_nul(workspace, monkeypatch):
    api, params = workspace
    write(api, params, b'original')
    revision = snapshot(api, params).json()['data']['revision']
    monkeypatch.setattr('app.video_studio.workspace_documents.MAX_TEXT_BYTES', 10)
    conditional = {**params, 'expectedRevision': revision}
    assert write(api, conditional, b'x' * 11).status_code == 413
    assert write(api, {**conditional, 'encoding': 'utf-16le'}, b'x' * 5).status_code == 413
    assert write(api, conditional, b'x\x00').status_code == 400
    assert snapshot(api, params).json()['data']['text'] == 'original'
