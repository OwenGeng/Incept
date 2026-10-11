import asyncio
import pytest

from app.video_studio import store
from app.video_studio.models import ProjectCreate
from app.routers import video_legacy


class StreamOnlyRequest:
    def __init__(self, chunks):
        self.chunks = chunks
    async def body(self):
        raise AssertionError('Large uploads must not buffer request.body()')
    async def stream(self):
        for chunk in self.chunks:
            yield chunk


def test_workspace_binary_upload_streams_and_commits_complete_file(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    project = store.create_project('stream@example.com', ProjectCreate(name='Stream'))
    result = asyncio.run(video_legacy.write_workspace_file(StreamOnlyRequest([b'first', b'second']),
        directory=project.id, path='client.mp4', exclusive=True, expectedRevision=None,
        encoding=None, email='stream@example.com'))
    assert result['code'] == 200
    target = store.safe_asset_path(store.assets_root('stream@example.com',project.id), 'client.mp4')
    assert target.read_bytes() == b'firstsecond'
    assert not list(target.parent.glob('*.tmp'))


def test_overflow_and_disconnect_preserve_existing_file_and_clean_partial(tmp_path, monkeypatch):
    from app.video_studio import workspace_uploads
    target = tmp_path / 'client.mp4'
    target.write_bytes(b'original')
    monkeypatch.setattr(workspace_uploads, 'upload_limit', lambda path: 8)
    with pytest.raises(OverflowError):
        asyncio.run(workspace_uploads.write_stream(target, StreamOnlyRequest([b'12345',b'67890']).stream()))
    async def broken_stream():
        yield b'partial'
        raise ConnectionError('disconnected')
    with pytest.raises(ConnectionError):
        asyncio.run(workspace_uploads.write_stream(target, broken_stream()))
    assert target.read_bytes() == b'original'
    assert not list(tmp_path.glob('*.tmp'))


def test_exclusive_stream_never_overwrites_existing_and_video_limit_is_decimal(tmp_path):
    from app.video_studio import workspace_uploads
    target = tmp_path / 'client.mp4'
    target.write_bytes(b'original')
    assert workspace_uploads.upload_limit(target) == 450_000_000
    with pytest.raises(FileExistsError):
        asyncio.run(workspace_uploads.write_stream(target, StreamOnlyRequest([b'new']).stream(), exclusive=True))
    assert target.read_bytes() == b'original'
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('canonical', [False, True])
def test_upload_routes_reject_overflow_without_losing_original(tmp_path, monkeypatch, canonical):
    from app.video_studio import workspace_uploads
    from test_video_legacy_api import client as legacy_client, headers
    from test_video_studio_api import client as canonical_client
    api = (canonical_client if canonical else legacy_client)(tmp_path, monkeypatch)
    project = store.create_project('stream@example.com', ProjectCreate(name='Stream'))
    target = store.safe_asset_path(store.assets_root('stream@example.com',project.id), 'client.mp4')
    target.write_bytes(b'original')
    monkeypatch.setattr(workspace_uploads, 'upload_limit', lambda path: 8)
    if canonical:
        response = api.post(f'/video-studio/projects/{project.id}/assets/upload',
            files={'file':('client.mp4', b'123456789', 'video/mp4')}, headers=headers('stream@example.com'))
    else:
        response = api.put('/video-legacy/api/workspaces/files/write',
            params={'directory':project.id,'path':'client.mp4'}, content=b'123456789', headers=headers('stream@example.com'))
    assert response.status_code == 413
    assert target.read_bytes() == b'original'
    assert not list(target.parent.glob('*.tmp'))
