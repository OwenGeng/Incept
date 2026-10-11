"""Pi model adapter uses native provider messages, not the old JSON agent loop."""
import pytest
from app.video_studio.pi_model import gemini_contents, model_response


def test_native_tool_history_and_signatures_are_preserved():
    context = {'messages': [
        {'role': 'user', 'content': 'Make a draft'},
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'c1', 'name': 'canvas',
          'arguments': {'operations_json': '[]'}, 'thoughtSignature': 'c2ln'}]},
        {'role': 'toolResult', 'toolName': 'canvas', 'toolCallId': 'c1', 'content': [{'type': 'text', 'text': '{"staged":true}'}]},
    ]}
    contents = gemini_contents(context, [])
    assert contents[1].role == 'model'
    assert contents[1].parts[0].function_call.name == 'canvas'
    assert contents[1].parts[0].thought_signature == b'sig'
    assert contents[2].parts[0].function_response.response == {'result': '{"staged":true}', 'isError': False}


def test_only_current_user_turn_receives_selected_video_parts():
    from google.genai import types
    part = types.Part.from_bytes(data=b'video', mime_type='video/mp4')
    contents = gemini_contents({'messages': [
        {'role': 'user', 'content': 'Old'}, {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Old review'}]},
        {'role': 'user', 'content': 'New'},
    ]}, [part])
    assert len(contents[0].parts) == 1
    assert contents[-1].parts[-1].inline_data.data == b'video'


def test_model_selection_is_rejected_before_provider_request():
    with pytest.raises(ValueError, match='not enabled'):
        model_response({'model': {'provider': 'google-vertex-ai', 'id': 'invented-model'}, 'context': {'messages': []}})


@pytest.mark.parametrize('capped', [False, True])
def test_enterprise_transport_keeps_deployment_config_native_calls_and_usage(monkeypatch, capped):
    from types import SimpleNamespace
    from google.genai import types
    from app.video_studio import pi_model
    seen = {}
    monkeypatch.setattr(pi_model, 'configured_text_models', lambda: [{'providerId': 'google-vertex-ai', 'modelId': 'owner-model'}])
    monkeypatch.setattr(pi_model, 'get_settings', lambda: SimpleNamespace(gcp_project_id='owner-project', gcp_location='owner-region'))
    def generate(**kwargs):
        seen.update(kwargs)
        return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[
            types.Part(text='Current result'),
            types.Part(function_call=types.FunctionCall(name='getCanvas', args={}), thought_signature=b'original')]),
            finish_reason=types.FinishReason.MAX_TOKENS if capped else types.FinishReason.STOP)],
            usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=12, candidates_token_count=7, thoughts_token_count=3, cached_content_token_count=2))
    def client(**kwargs):
        seen['client'] = kwargs
        return SimpleNamespace(models=SimpleNamespace(generate_content=generate), close=lambda: seen.update(closed=True))
    monkeypatch.setattr(pi_model.genai, 'Client', client)
    result = model_response({'model': {'provider': 'google-vertex-ai', 'id': 'owner-model', 'api': 'openai-completions', 'maxTokens': 2048},
        'context': {'systemPrompt': 'Current system', 'messages': [{'role': 'user', 'content': 'Hello'}],
            'tools': [{'name': 'getCanvas', 'description': 'Read canvas', 'parameters': {'type': 'object', 'properties': {}}}]}})
    assert seen['client'] == {'enterprise': True, 'project': 'owner-project', 'location': 'owner-region'}
    assert seen['model'] == 'owner-model' and seen['closed']
    assert result['stopReason'] == ('length' if capped else 'toolUse')
    assert result['content'][1]['thoughtSignature'] == 'b3JpZ2luYWw='
    assert result['usage']['input'] == 10 and result['usage']['output'] == 10  # Cache tokens are accounted separately.
    assert result['usage']['cacheRead'] == 2
    assert seen['config'].max_output_tokens == 2048


def test_enterprise_client_closes_on_failure_and_preserves_tool_error_flag(monkeypatch):
    from types import SimpleNamespace
    from app.video_studio import pi_model
    monkeypatch.setattr(pi_model, 'configured_text_models', lambda: [{'providerId': 'google-vertex-ai', 'modelId': 'owner-model'}])
    monkeypatch.setattr(pi_model, 'get_settings', lambda: SimpleNamespace(gcp_project_id='owner-project', gcp_location='owner-region'))
    closed = []
    def fail(**kwargs):
        raise ValueError('HTTP 400')
    monkeypatch.setattr(pi_model.genai, 'Client', lambda **k: SimpleNamespace(models=SimpleNamespace(generate_content=fail), close=lambda: closed.append(True)))
    with pytest.raises(ValueError, match='400'):
        model_response({'model': {'provider': 'google-vertex-ai', 'id': 'owner-model', 'maxTokens': 10}, 'context': {}})
    assert closed == [True]
    result = gemini_contents({'messages': [{'role': 'toolResult', 'toolName': 'web_fetch', 'isError': True, 'content': [{'type': 'text', 'text': 'Unavailable'}]}]}, [])
    assert result[0].parts[0].function_response.response['isError'] is True


def test_streaming_emits_visible_deltas_before_completion_and_native_thinking(monkeypatch):
    from types import SimpleNamespace
    from google.genai import types
    from app.video_studio import pi_model
    emitted=[]
    seen={}
    monkeypatch.setattr(pi_model,'configured_text_models',lambda:[{'providerId':'google-vertex-ai','modelId':'owner-model'}])
    monkeypatch.setattr(pi_model,'get_settings',lambda:SimpleNamespace(gcp_project_id='owner-project',gcp_location='global'))
    def generate(**kwargs):
        seen.update(kwargs)
        yield types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[types.Part(text='Hello')]))])
        assert emitted==[{'type':'text_delta','delta':'Hello'}]
        yield types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[types.Part(text=' world')]),finish_reason=types.FinishReason.STOP)])
    monkeypatch.setattr(pi_model.genai,'Client',lambda **kw:SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate),close=lambda:None))
    result=model_response({'model':{'provider':'google-vertex-ai','id':'owner-model','api':'openai-completions','maxTokens':1024},
        'reasoning':'high','context':{'messages':[{'role':'user','content':'Hello'}]}},emit=emitted.append)
    assert result['content']==[{'type':'text','text':'Hello world'}]
    assert seen['config'].thinking_config.thinking_level==types.ThinkingLevel.HIGH
    assert seen['config'].thinking_config.include_thoughts is False
