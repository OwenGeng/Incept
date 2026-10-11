import json
import pytest

from app.video_studio.workspace_copy import copy_workspace_file

from test_video_legacy_api import client, headers


def test_canvas_copy_has_independent_ids_text_and_owned_assets(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    directory = api.post('/video-legacy/api/workspaces/create', json={'name': 'Copy safety'}, headers=headers()).json()['data']['directory']
    def write(path, content):
        return api.put('/video-legacy/api/workspaces/files/write', params={'directory': directory, 'path': path}, content=content, headers=headers())
    write('assets/old/content.md', b'original text')
    write('assets/old/photo.png', b'image')
    write('assets/generated/shared.png', b'shared')
    canvas = {'linglonglabVideoCanvas': True, 'nodes': [{'id': 'old', 'type': 'remote-textNode', 'position': {'x': 0, 'y': 0}, 'data': {'textPath': 'assets/old/content.md', 'owned': {'url': 'assets/old/photo.png'}, 'shared': 'assets/generated/shared.png'}}, {'id': 'second', 'type': 'remote-imageNode', 'position': {'x': 0, 'y': 0}, 'data': {}}], 'edges': [{'id': 'edge', 'source': 'old', 'target': 'second'}], 'viewport': {'x': 0, 'y': 0, 'zoom': 1}}
    write('original.json', json.dumps(canvas).encode())
    copied = api.post('/video-legacy/api/workspaces/files/copy', json={'directory': directory, 'path': 'original.json', 'target': 'copy.json'}, headers=headers())
    assert copied.status_code == 200
    def read(path):
        return api.get('/video-legacy/api/workspaces/files/read', params={'directory': directory, 'path': path}, headers=headers())
    clone = read('copy.json').json()
    first, second = clone['nodes']
    assert first['id'] != 'old' and second['id'] != 'second'
    assert first['data']['textPath'] == f"assets/{first['id']}/content.md"
    assert first['data']['owned']['url'] == f"assets/{first['id']}/photo.png"
    assert first['data']['shared'] == 'assets/generated/shared.png'
    assert clone['edges'][0]['source'] == first['id']
    assert clone['edges'][0]['target'] == second['id']
    assert clone['edges'][0]['id'] != 'edge'
    assert read(first['data']['textPath']).content == b'original text'
    write(first['data']['textPath'], b'changed clone')
    assert read('assets/old/content.md').content == b'original text'
    assert read('original.json').json() == canvas
    assert api.post('/video-legacy/api/workspaces/files/copy', json={'directory': directory, 'path': 'original.json', 'target': 'copy.json'}, headers=headers()).status_code == 409


def test_copy_rejects_unsafe_targets_and_self_copy(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    directory = api.post('/video-legacy/api/workspaces/create', json={'name': 'Copy safety'}, headers=headers()).json()['data']['directory']
    for target in ['../outside.json', '画布1.json']:
        response = api.post('/video-legacy/api/workspaces/files/copy', json={'directory': directory, 'path': '画布1.json', 'target': target}, headers=headers())
        assert response.status_code in [400, 409]


def test_copy_rejects_symlinks_and_oversized_files(tmp_path, monkeypatch):
    source = tmp_path / 'original.txt'
    source.write_bytes(b'original')
    (tmp_path / 'link.txt').symlink_to(source)
    with pytest.raises(ValueError, match='符号链接'):
        copy_workspace_file(tmp_path, 'link.txt', 'clone.txt')
    monkeypatch.setattr('app.video_studio.workspace_copy.MAX_COPY_BYTES', 3)
    with pytest.raises(ValueError):
        copy_workspace_file(tmp_path, 'original.txt', 'clone.txt')
    assert not (tmp_path / 'clone.txt').exists()
