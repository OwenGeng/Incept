"""Enterprise Gemini transport for Pi; no agent/tool orchestration here.

OpenAI/Anthropic use Pi's native transports. Deployment-owned Gemini model,
project and location are unchanged. Only native SDK messages cross this bridge.
"""
import base64
import os
import threading
import time
import uuid

from google import genai
from google.genai import types

from app.incept.config import get_settings
from app.routers.video_runtime import configured_text_models

# Production callbacks already share the native host's 30-worker budget. This
# extra bound also covers a client.close implementation that does not return.
_WATCHER_SLOTS = threading.BoundedSemaphore(30)


def gemini_contents(context: dict, media_parts: list) -> list:
    contents = []
    messages = context.get('messages', [])
    current_user = max((i for i, message in enumerate(messages) if message.get('role') == 'user'), default=-1)
    for index, message in enumerate(messages):
        role = message.get('role')
        content = message.get('content', [])
        blocks = [{'type': 'text', 'text': content}] if isinstance(content, str) else content
        parts = []
        for block in blocks:
            if block.get('type') == 'text' and block.get('text'):
                parts.append(types.Part(text=block['text']))
            elif block.get('type') == 'toolCall':
                signature = block.get('thoughtSignature')
                parts.append(types.Part(function_call=types.FunctionCall(id=block.get('id'),name=block['name'], args=block['arguments']),
                    thought_signature=base64.b64decode(signature) if signature else None))
        if role == 'toolResult':
            parts = [types.Part(function_response=types.FunctionResponse(id=message.get('toolCallId'),name=message['toolName'],
                response={'result': '\n'.join(block.get('text', '') for block in blocks), 'isError': bool(message.get('isError'))}))]
        if index == current_user:
            parts.extend(media_parts)
        if parts:
            contents.append(types.Content(role='model' if role == 'assistant' else 'user', parts=parts))
    return contents


def model_response(payload: dict, media_parts=None, emit=None, check_cancel=None) -> dict:
    model = payload['model']
    if not any(item['providerId'] == model['provider'] and item['modelId'] == model['id']
               for item in configured_text_models()):
        raise ValueError('Pi selected model is not enabled by this deployment')
    if model['provider'] != 'google-vertex-ai':
        raise ValueError('Only Enterprise Gemini uses the Python Pi model transport')
    settings = get_settings()
    context = payload['context']
    declarations = [types.FunctionDeclaration(name=tool['name'], description=tool['description'],
        parameters_json_schema=tool['parameters']) for tool in context.get('tools', [])]
    config = types.GenerateContentConfig(system_instruction=context.get('systemPrompt') or None,
        tools=[types.Tool(function_declarations=declarations)] if declarations else None,
        max_output_tokens=payload.get('maxTokens') or model['maxTokens'])
    reasoning=payload.get('reasoning')
    if reasoning and reasoning != 'off':
        if reasoning not in {'low','medium','high'}: raise ValueError('Unsupported thinking level')
        config.thinking_config=types.ThinkingConfig(thinking_level=reasoning.upper(),include_thoughts=False)
    timeout_seconds = int(os.getenv('VIDEO_AGENT_MODEL_TIMEOUT_SECONDS', '120'))
    if not 1 <= timeout_seconds <= 900:
        raise ValueError('VIDEO_AGENT_MODEL_TIMEOUT_SECONDS must be between 1 and 900')
    if check_cancel: check_cancel()
    client = genai.Client(enterprise=True, project=settings.gcp_project_id, location=settings.gcp_location,
        http_options=types.HttpOptions(timeout=timeout_seconds * 1000))
    stopped, close_lock = threading.Event(), threading.Lock()
    closed, cancellation = False, []
    def close_client():
        nonlocal closed
        with close_lock:
            if closed: return
            closed = True
        client.close()
    watcher = None
    if check_cancel:
        if not _WATCHER_SLOTS.acquire(blocking=False):
            close_client()
            raise ValueError('Model cancellation monitor capacity exhausted; wait for pending requests to close')
        def watch_cancel():
            try:
                while not stopped.wait(.1):
                    try: check_cancel()
                    except Exception as error:
                        cancellation.append(error)
                        try: close_client()
                        except Exception: pass
                        return
            finally:
                _WATCHER_SLOTS.release()
        watcher = threading.Thread(target=watch_cancel, daemon=True, name='linglonglab-model-cancellation')
        watcher.start()
    responses=[]
    try:
        contents=gemini_contents(context, media_parts or [])
        if emit:
            for response in client.models.generate_content_stream(model=model['id'],contents=contents,config=config):
                if check_cancel: check_cancel()
                responses.append(response)
                for candidate in (response.candidates or [])[:1]:
                    for part in candidate.content.parts if candidate.content else []:
                        if part.text and not part.thought:
                            emit({'type':'text_delta','delta':part.text})
        else:
            responses.append(client.models.generate_content(model=model['id'],contents=contents,config=config))
        if cancellation: raise cancellation[0]
        if check_cancel: check_cancel()
    except Exception:
        if cancellation: raise cancellation[0]
        if check_cancel: check_cancel()
        raise
    finally:
        stopped.set()
        close_client()
        if watcher: watcher.join(timeout=1)
    blocks = []
    for response in responses:
        for candidate in (response.candidates or [])[:1]:
            for part in candidate.content.parts if candidate.content else []:
                if part.text and not part.thought:
                    if blocks and blocks[-1]['type']=='text': blocks[-1]['text']+=part.text
                    else: blocks.append({'type': 'text', 'text': part.text})
                if part.function_call:
                    block = {'type': 'toolCall', 'id': part.function_call.id or f'call_{uuid.uuid4().hex}', 'name': part.function_call.name,
                             'arguments': dict(part.function_call.args or {})}
                    if part.thought_signature:
                        block['thoughtSignature'] = base64.b64encode(part.thought_signature).decode()
                    blocks.append(block)
    if not blocks:
        raise RuntimeError('Enterprise Gemini returned no visible text or tool call')
    usage = next((r.usage_metadata for r in reversed(responses) if r.usage_metadata),None)
    input_tokens = (usage.prompt_token_count or 0) if usage else 0
    output_tokens = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0
    cached = (usage.cached_content_token_count or 0) if usage else 0
    capped = any(r.candidates and r.candidates[0].finish_reason == types.FinishReason.MAX_TOKENS for r in responses)
    return {'role': 'assistant', 'api': model['api'], 'provider': model['provider'], 'model': model['id'],
        'content': blocks, 'stopReason': 'length' if capped else 'toolUse' if any(b['type'] == 'toolCall' for b in blocks) else 'stop',
        'timestamp': int(time.time() * 1000), 'usage': {'input': max(0,input_tokens-cached), 'output': output_tokens,
        'cacheRead': cached, 'cacheWrite': 0, 'totalTokens': input_tokens + output_tokens,
        'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'total': 0}}}
