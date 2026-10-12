import base64
from io import BytesIO

import pytest
from PIL import Image

from test_video_legacy_api import client, headers
from app.incept.config import get_settings


def png(image):
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture
def images(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    directory = api.post('/video-legacy/api/workspaces/create', json={'name': 'Image edit safety'}, headers=headers()).json()['data']['directory']
    source = png(Image.new('RGBA', (4, 4), (20, 30, 40, 128)))
    mask = Image.new('L', (4, 4), 0)
    mask.putpixel((1, 1), 255)
    for path, payload in [('assets/source/image.png', source), ('assets/new/mask.png', png(mask))]:
        api.put('/video-legacy/api/workspaces/files/write', params={'directory': directory, 'path': path}, content=payload, headers=headers())
    return api, {'directory': directory, 'sourcePath': 'assets/source/image.png', 'maskPath': 'assets/new/mask.png', 'prompt': 'Change selected area to red', 'providerId': 'google-vertex-ai', 'modelId': get_settings().vertex_gemini_image_model, 'outputDirectory': 'assets/new'}, source


@pytest.mark.parametrize('use_fallback', [False, True])
def test_masked_edit_keeps_original_and_every_unmasked_pixel(images, monkeypatch, use_fallback):
    api, body, source = images
    if use_fallback:
        body['modelId'] = get_settings().vertex_gemini_image_fallback_model
    captured = {}
    async def generate(self, **kwargs):
        from app.video_studio.vertex_media import ImageGenerationResult, ImageItem
        captured.update(kwargs)
        return ImageGenerationResult(images=[ImageItem(b64_json=base64.b64encode(png(Image.new('RGBA', (4, 4), (255, 0, 0, 255)))).decode())], provider='vertex', status='succeeded')
    monkeypatch.setattr('app.video_studio.vertex_media.VertexImageApiAdapter.generate', generate)
    response = api.post('/video-legacy/api/ai/media/inpaint', json=body, headers=headers())
    assert response.status_code == 200, response.text
    result = response.json()['data'][0]
    assert result['path'].startswith('assets/new/')
    assert result['path'] != body['sourcePath']
    assert len(captured['inp'].images) == 2
    output = api.get('/video-legacy/api/workspaces/files/read', params={'directory': body['directory'], 'path': result['path']}, headers=headers())
    edited = Image.open(BytesIO(output.content)).convert('RGBA')
    original = Image.open(BytesIO(source)).convert('RGBA')
    assert edited.getpixel((1, 1)) == (255, 0, 0, 255)
    for y in range(4):
        for x in range(4):
            if (x, y) != (1, 1):
                assert edited.getpixel((x, y)) == original.getpixel((x, y))
    assert api.get('/video-legacy/api/workspaces/files/read', params={'directory': body['directory'], 'path': body['sourcePath']}, headers=headers()).content == source


@pytest.mark.parametrize('changes', [{'providerId': 'openai'}, {'modelId': 'not-configured'}, {'sourcePath': '../other/image.png'}, {'outputDirectory': '../outside'}, {'prompt': ''}])
def test_masked_edit_rejects_invalid_requests_before_model_call(images, monkeypatch, changes):
    api, body, _ = images
    async def forbidden(*args, **kwargs):
        pytest.fail('Invalid requests must not call a paid model')
    monkeypatch.setattr('app.video_studio.vertex_media.VertexImageApiAdapter.generate', forbidden)
    response = api.post('/video-legacy/api/ai/media/inpaint', json={**body, **changes}, headers=headers())
    assert response.status_code in [400, 422]


def test_empty_or_wrong_size_mask_is_rejected_before_generation(images, monkeypatch):
    api, body, _ = images
    async def forbidden(*args, **kwargs):
        pytest.fail('Invalid mask must not call a paid model')
    monkeypatch.setattr('app.video_studio.vertex_media.VertexImageApiAdapter.generate', forbidden)
    for mask in [Image.new('L', (4, 4), 0), Image.new('L', (2, 2), 255)]:
        api.put('/video-legacy/api/workspaces/files/write', params={'directory': body['directory'], 'path': body['maskPath']}, content=png(mask), headers=headers())
        assert api.post('/video-legacy/api/ai/media/inpaint', json=body, headers=headers()).status_code == 400
