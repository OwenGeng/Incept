import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from app.video_studio import agent, store
from app.video_studio.models import ProjectCreate


@pytest.mark.parametrize('message,invalid', [
    ('我已经听到了视频里的配音，并逐帧观看了完整视频。', True),
    ('I have listened to the audio and watched every frame.', True),
    ('我已经听到了视频里的配音。', True),
    ('I have listened to the audio.', True),
    ('仅看了采样帧，未听取音轨。建议新广告增加旁白。', False),
    ('I have not listened to the audio; these are sampled frames only.', False),
    ('建议正式交付前逐帧检查视频，并为新广告录制旁白。', False),
])
def test_sampled_video_cannot_claim_audio_or_every_frame(tmp_path, monkeypatch, message, invalid):
    import json
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    project = store.create_project('sample@example.com', ProjectCreate(name='Sampling'))
    store.safe_asset_path(store.assets_root('sample@example.com', project.id), 'clip.mp4').write_bytes(b'synthetic')
    monkeypatch.setattr(agent, '_asset_parts', lambda *args, **kwargs: ([], [
        {'path':'clip.mp4', 'name':'clip.mp4', 'inspection':'attached', 'mode':'sampled-frames', 'no_audio':True,
         'timestamps_seconds':[0, 1.9], 'notes':['没有音频，仅采样帧']}]))
    monkeypatch.setattr(agent, '_call_model', lambda *args, **kwargs: json.dumps({'message':message, 'operations':[]}))
    def run():
        return agent.run_agent(email='sample@example.com', project_id=project.id,
            prompt='分析这份客户素材', conversation_id=None, asset_paths=['clip.mp4'])
    if invalid:
        with pytest.raises(ValueError, match='媒体分析范围'):
            run()
    else:
        conversation, _, _ = run()
        assert message in conversation.messages[-1].content


@pytest.mark.parametrize('provider', ['openai', 'anthropic'])
def test_attached_image_reaches_selected_sdk_and_survives_followup(tmp_path, monkeypatch, provider):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    project = store.create_project('media-wire@example.com', ProjectCreate(name='Media wire'))
    image = store.safe_asset_path(store.assets_root('media-wire@example.com', project.id), 'blue.png')
    Image.new('RGB', (16, 12), 'blue').save(image)
    original = image.read_bytes()
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output_text='{"message":"图片是蓝色。","operations":[]}',
            content=[SimpleNamespace(type='text', text='{"message":"图片是蓝色。","operations":[]}')])
    monkeypatch.setattr(agent, 'configured_text_models', lambda **kwargs: [{'providerId':provider,'modelId':'customer-model','isDefault':True}])
    monkeypatch.setattr(agent, 'get_settings', lambda: SimpleNamespace(openai_api_key='synthetic',anthropic_api_key='synthetic'))
    if provider == 'openai':
        import openai
        monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    else:
        import anthropic
        monkeypatch.setattr(anthropic, 'Anthropic', lambda **kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)))
    conv, _, _ = agent.run_agent(email='media-wire@example.com', project_id=project.id,
        prompt='分析这张客户图片', conversation_id=None, asset_paths=['blue.png'])
    agent.run_agent(email='media-wire@example.com', project_id=project.id,
        prompt='请再看同一张图片的颜色', conversation_id=conv.id, asset_paths=['blue.png'])
    assert len(requests) == 2
    for request in requests:
        content = request['input'][0]['content'] if provider == 'openai' else request['messages'][0]['content']
        if provider == 'openai':
            encoded = next(item['image_url'].split(',',1)[1] for item in content if item['type']=='input_image')
        else:
            encoded = next(item['source']['data'] for item in content if item['type']=='image')
        inspected = Image.open(io.BytesIO(base64.b64decode(encoded))).convert('RGB')
        assert inspected.getpixel((0,0))[2] > inspected.getpixel((0,0))[0]
        assert request['model'] == 'customer-model'
    assert image.read_bytes() == original
    assert store.get_conversation('media-wire@example.com', project.id, conv.id).messages[0].attachments[0]['path'] == 'blue.png'
