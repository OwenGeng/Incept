import base64
from types import SimpleNamespace

import pytest
from google.genai import types

from app.video_studio import agent


@pytest.mark.parametrize('provider', ['openai', 'anthropic'])
def test_real_sdk_request_contains_image_and_unchanged_model(monkeypatch, provider):
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_text='{"message":"蓝色图片","operations":[]}',
            content=[SimpleNamespace(type='text', text='{"message":"蓝色图片","operations":[]}')])
    monkeypatch.setattr(agent, 'get_settings', lambda: SimpleNamespace(openai_api_key='synthetic', anthropic_api_key='synthetic'))
    if provider == 'openai':
        import openai
        monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    else:
        import anthropic
        monkeypatch.setattr(anthropic, 'Anthropic', lambda **kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)))
    payload = b'synthetic-image-wire-bytes'
    parts = [types.Part(text='客户素材 product.png'), types.Part.from_bytes(data=payload, mime_type='image/png')]
    assert '蓝色图片' in agent._call_model('分析颜色', parts, provider_id=provider, model_id='user-configured-model')
    assert captured['model'] == 'user-configured-model'
    if provider == 'openai':
        content = captured['input'][0]['content']
        image = next(item for item in content if item['type'] == 'input_image')
        assert image['image_url'] == 'data:image/png;base64,'+base64.b64encode(payload).decode('ascii')
        assert captured['store'] is False
        assert content[0]['text'] == '分析颜色'
    else:
        content = captured['messages'][0]['content']
        image = next(item for item in content if item['type'] == 'image')
        assert image['source'] == {'type':'base64','media_type':'image/png','data':base64.b64encode(payload).decode('ascii')}
        assert content[0]['text'] == '分析颜色'
    assert any(item.get('text') == '客户素材 product.png' for item in content)


@pytest.mark.parametrize('provider', ['openai', 'anthropic'])
def test_nonimage_binary_requires_preparation_not_silent_discard(monkeypatch, provider):
    monkeypatch.setattr(agent, 'get_settings', lambda: SimpleNamespace(openai_api_key='synthetic', anthropic_api_key='synthetic'))
    with pytest.raises(ValueError, match='图片|image|采样'):
        agent._call_model('分析', [types.Part.from_bytes(data=b'video', mime_type='video/mp4')], provider_id=provider, model_id='user-model')
