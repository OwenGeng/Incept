"""Private media bridge for the LinglongLab Video workspace.

The workspace sends normalized media requests here. This module deliberately
uses only deployment-owned Vertex model IDs, locations, ADC and GCS settings.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any, Iterator, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.incept.config import get_settings
from app.services.auth import require_internal_key
from app.video_studio.vertex_media import (
    ImageGenerationInput,
    ProviderConfig,
    VertexImageApiAdapter,
    VertexVideoApiAdapter,
    VideoGenerationInput,
    _adc_access_token,
)


router = APIRouter(
    prefix="/api/video-runtime",
    tags=["video-runtime"],
    dependencies=[Depends(require_internal_key)],
)


class ManagedMediaRequest(BaseModel):
    media_type: Literal["image", "video", "audio"]
    provider_id: str
    model_id: str
    prompt: str = Field(min_length=1, max_length=12_000)
    ratio: str | None = None
    size: str | None = None
    duration: int | None = Field(default=None, ge=1, le=60)
    first_frame: str | None = None
    last_frame: str | None = None
    resolution: str | None = None
    generate_audio: bool | None = None
    voice: str | None = None
    speed: float | None = Field(default=None, gt=0, le=4)
    format: str | None = None


class ManagedMediaResponse(BaseModel):
    media_type: Literal["image", "video", "audio"]
    mime_type: str
    data: str


def _openai_parts(content: Any, genai_types: Any) -> list[Any]:
    if isinstance(content, str):
        return [genai_types.Part(text=content)] if content else []
    parts: list[Any] = []
    for item in content if isinstance(content, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(genai_types.Part(text=item["text"]))
        image = item.get("image_url")
        url = image.get("url") if isinstance(image, dict) else None
        if item.get("type") == "image_url" and isinstance(url, str) and url.startswith("data:") and ";base64," in url:
            header, encoded = url.split(";base64,", 1)
            parts.append(genai_types.Part.from_bytes(data=base64.b64decode(encoded), mime_type=header[5:]))
    return parts


def _gemini_contents(messages: list[dict[str, Any]], genai_types: Any) -> tuple[str, list[Any]]:
    system: list[str] = []
    contents: list[Any] = []
    call_names: dict[str, str] = {}
    for message in messages:
        role = str(message.get("role") or "user")
        if role in {"system", "developer"}:
            if isinstance(message.get("content"), str):
                system.append(message["content"])
            continue
        parts = _openai_parts(message.get("content"), genai_types)
        if role == "assistant":
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                    continue
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                call_id = str(call.get("id") or "")
                if call_id:
                    call_names[call_id] = function["name"]
                parts.append(genai_types.Part(function_call=genai_types.FunctionCall(name=function["name"], args=arguments)))
            gemini_role = "model"
        elif role == "tool":
            name = call_names.get(str(message.get("tool_call_id") or ""), "tool")
            raw_response = message.get("content")
            try:
                response = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
            except json.JSONDecodeError:
                response = {"result": raw_response}
            if not isinstance(response, dict):
                response = {"result": response}
            parts = [genai_types.Part(function_response=genai_types.FunctionResponse(name=name, response=response))]
            gemini_role = "user"
        else:
            gemini_role = "user"
        if parts:
            contents.append(genai_types.Content(role=gemini_role, parts=parts))
    return "\n\n".join(system), contents


def _gemini_tools(tools: Any, genai_types: Any) -> list[Any]:
    declarations: list[Any] = []
    for tool in tools if isinstance(tools, list) else []:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            continue
        declarations.append(
            genai_types.FunctionDeclaration(
                name=function["name"],
                description=str(function.get("description") or ""),
                parameters_json_schema=function.get("parameters") or {"type": "object", "properties": {}},
            )
        )
    return [genai_types.Tool(function_declarations=declarations)] if declarations else []


def _openai_delta(part: Any, *, call_index: int) -> tuple[dict[str, Any] | None, int]:
    text = getattr(part, "text", None)
    if isinstance(text, str) and text:
        return {"content": text}, call_index
    function_call = getattr(part, "function_call", None)
    name = getattr(function_call, "name", None) if function_call is not None else None
    if not name:
        return None, call_index
    args = getattr(function_call, "args", None) or {}
    delta = {
        "tool_calls": [{
            "index": call_index,
            "id": f"call_{uuid.uuid4().hex}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
        }]
    }
    return delta, call_index + 1


def _chat_stream(body: dict[str, Any], *, model_id: str | None = None) -> Iterator[str]:
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()
    project_id = settings.gcp_project_id
    if not project_id:
        raise HTTPException(status_code=503, detail="GCP project is not configured")
    system, contents = _gemini_contents(body.get("messages") or [], genai_types)
    if not contents:
        raise HTTPException(status_code=400, detail="messages must contain user content")
    config: dict[str, Any] = {}
    if system:
        config["system_instruction"] = system
    tools = _gemini_tools(body.get("tools"), genai_types)
    if tools:
        config["tools"] = tools
    if isinstance(body.get("max_tokens"), int):
        config["max_output_tokens"] = body["max_tokens"]
    client = genai.Client(
        enterprise=True,
        project=project_id,
        location=settings.gcp_location,
    )
    stream = client.models.generate_content_stream(
        model=model_id or settings.vertex_gemini_model,
        contents=contents,
        config=genai_types.GenerateContentConfig(**config),
    )
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': 'linglonglab-managed-text', 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
    call_index = 0
    used_tools = False
    for chunk in stream:
        for candidate in getattr(chunk, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                delta, call_index = _openai_delta(part, call_index=call_index)
                if not delta:
                    continue
                used_tools = used_tools or "tool_calls" in delta
                payload = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": "linglonglab-managed-text",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    finish = "tool_calls" if used_tools else "stop"
    yield f"data: {json.dumps({'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': 'linglonglab-managed-text', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]})}\n\n"
    yield "data: [DONE]\n\n"


def _vertex_config(*, location: str) -> ProviderConfig:
    settings = get_settings()
    if not settings.gcp_project_id:
        raise HTTPException(status_code=503, detail="GCP project is not configured")
    return ProviderConfig(
        provider="vertex",
        api_key="",
        project_id=settings.gcp_project_id,
        location=location,
    )


def _data_url_payload(value: str, expected_prefix: str) -> tuple[str, str]:
    if not value.startswith("data:") or ";base64," not in value:
        raise HTTPException(status_code=502, detail="Vertex returned an unsupported media reference")
    header, data = value.split(";base64,", 1)
    mime_type = header[5:]
    if not mime_type.startswith(expected_prefix):
        raise HTTPException(status_code=502, detail="Vertex returned an unexpected media type")
    return mime_type, data


def configured_text_models() -> list[dict[str, Any]]:
    settings = get_settings()
    models: list[dict[str, Any]] = []
    if settings.gcp_project_id:
        models.extend([
        {"providerId": "google-vertex-ai", "providerLabel": "Google Vertex AI", "modelId": settings.vertex_playable_flash_model, "label": settings.vertex_playable_flash_model, "protocol": "openai-completions", "isDefault": True},
        {"providerId": "google-vertex-ai", "providerLabel": "Google Vertex AI", "modelId": settings.vertex_playable_pro_model, "label": settings.vertex_playable_pro_model, "protocol": "openai-completions", "isDefault": False},
        ])
    if settings.openai_api_key:
        models.append({"providerId": "openai", "providerLabel": "OpenAI", "modelId": settings.openai_text_model, "label": settings.openai_text_model, "protocol": "openai-responses", "isDefault": False})
    if settings.anthropic_api_key and settings.anthropic_model:
        models.append({"providerId": "anthropic", "providerLabel": "Anthropic", "modelId": settings.anthropic_model, "label": settings.anthropic_model, "protocol": "anthropic-messages", "isDefault": False})
    return [model for model in models if model["modelId"]]


def configured_media_models() -> list[dict[str, Any]]:
    settings = get_settings()
    models: list[dict[str, Any]] = []
    if settings.gcp_project_id:
        models.extend([
            {"providerId": "google-vertex-ai", "modelId": settings.vertex_gemini_image_model, "type": "image", "isDefault": True},
            {"providerId": "google-vertex-ai", "modelId": settings.vertex_gemini_image_fallback_model, "type": "image", "isDefault": False},
            {"providerId": "google-vertex-ai", "modelId": settings.vertex_veo_fast_model, "type": "video", "isDefault": True},
            {"providerId": "google-cloud-tts", "modelId": settings.google_tts_model, "type": "audio", "isDefault": True},
        ])
    if settings.openai_api_key:
        models.extend([
            {"providerId": "openai", "modelId": settings.openai_image_model, "type": "image", "isDefault": False},
            {"providerId": "openai", "modelId": settings.openai_tts_model, "type": "audio", "isDefault": False},
        ])
    return [model for model in models if model["modelId"]]


def validate_media_model(media_type: str, provider_id: str, model_id: str) -> None:
    if not any(
        item["type"] == media_type and item["providerId"] == provider_id and item["modelId"] == model_id
        for item in configured_media_models()
    ):
        raise ValueError("The selected media provider/model is not enabled by this deployment")


async def _openai_image(body: ManagedMediaRequest) -> ManagedMediaResponse:
    from openai import AsyncOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")
    size = body.size or "1024x1024"
    response = await AsyncOpenAI(api_key=settings.openai_api_key).images.generate(
        model=body.model_id,
        prompt=body.prompt,
        n=1,
        size=size,
    )
    encoded = response.data[0].b64_json if response.data else None
    if not encoded:
        raise HTTPException(status_code=502, detail="OpenAI image generation returned no bytes")
    return ManagedMediaResponse(media_type="image", mime_type="image/png", data=encoded)


async def _openai_tts(body: ManagedMediaRequest) -> ManagedMediaResponse:
    from openai import AsyncOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")
    audio_format = (body.format or "mp3").lower()
    if audio_format not in {"mp3", "wav", "opus", "aac", "flac", "pcm"}:
        raise HTTPException(status_code=400, detail="Unsupported OpenAI TTS output format")
    response = await AsyncOpenAI(api_key=settings.openai_api_key).audio.speech.create(
        model=body.model_id,
        voice=body.voice or "alloy",
        input=body.prompt,
        response_format=audio_format,
        speed=body.speed or 1.0,
    )
    payload = bytes(response.content)
    if not payload:
        raise HTTPException(status_code=502, detail="OpenAI TTS returned no audio bytes")
    mime_type = {"mp3": "audio/mpeg", "wav": "audio/wav", "opus": "audio/opus", "aac": "audio/aac", "flac": "audio/flac", "pcm": "audio/pcm"}[audio_format]
    return ManagedMediaResponse(media_type="audio", mime_type=mime_type, data=base64.b64encode(payload).decode("ascii"))


async def _google_tts(body: ManagedMediaRequest) -> ManagedMediaResponse:
    import httpx

    import asyncio

    settings = get_settings()
    if not settings.gcp_project_id:
        raise HTTPException(status_code=503, detail="GCP project is not configured")
    token = await asyncio.to_thread(_adc_access_token)
    audio_format = (body.format or "mp3").lower()
    encoding = {"mp3": "MP3", "wav": "LINEAR16", "ogg": "OGG_OPUS"}.get(audio_format)
    if not encoding:
        raise HTTPException(status_code=400, detail="Google TTS supports mp3, wav, or ogg in this workspace")
    payload = {
        "input": {"text": body.prompt},
        "voice": {"languageCode": "en-US", "name": body.voice or "Kore", "modelName": body.model_id},
        "audioConfig": {"audioEncoding": encoding, "speakingRate": body.speed or 1.0},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-goog-user-project": settings.gcp_project_id,
            },
            json=payload,
        )
        response.raise_for_status()
    encoded = str(response.json().get("audioContent") or "")
    if not encoded:
        raise HTTPException(status_code=502, detail="Google TTS returned no audio bytes")
    mime_type = {"mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg"}[audio_format]
    return ManagedMediaResponse(media_type="audio", mime_type=mime_type, data=encoded)


@router.post("/chat/completions")
async def chat_completions(body: dict[str, Any]):
    """OpenAI-compatible streaming facade over the deployment-owned text model."""
    if body.get("stream") is not True:
        raise HTTPException(status_code=400, detail="LinglongLab Agent requires stream=true")
    return StreamingResponse(
        _chat_stream(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/media/generate", response_model=ManagedMediaResponse)
async def generate_media(body: ManagedMediaRequest) -> ManagedMediaResponse:
    settings = get_settings()
    try:
        validate_media_model(body.media_type, body.provider_id, body.model_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if body.media_type == "image":
        if body.provider_id == "openai":
            return await _openai_image(body)
        result = await VertexImageApiAdapter().generate(
            cfg=_vertex_config(location=settings.gcp_location),
            inp=ImageGenerationInput(
                prompt=body.prompt,
                model=body.model_id,
                target_ratio=body.ratio,
                size=body.size,
                response_format="b64_json",
            ),
            timeout_s=120.0,
        )
        image = result.images[0]
        if not image.b64_json:
            raise HTTPException(status_code=502, detail="Vertex image generation returned no bytes")
        return ManagedMediaResponse(media_type="image", mime_type="image/png", data=image.b64_json)

    if body.media_type == "audio":
        return await (_openai_tts(body) if body.provider_id == "openai" else _google_tts(body))

    video_model = body.model_id
    result = await VertexVideoApiAdapter().generate(
        cfg=_vertex_config(location=settings.vertex_veo_location),
        inp=VideoGenerationInput(
            prompt=body.prompt,
            first_frame_base64=body.first_frame,
            last_frame_base64=body.last_frame,
            model=video_model,
            ratio=body.ratio or "16:9",
            seconds=body.duration,
            provider_params={"resolution": body.resolution} if body.resolution else {},
        ),
        poll_interval_s=2.0,
        timeout_s=30 * 60.0,
    )
    if not result.url:
        raise HTTPException(status_code=502, detail="Vertex video generation returned no bytes")
    mime_type, data = _data_url_payload(result.url, "video/")
    # Validate the base64 before handing it to the workspace file writer.
    try:
        base64.b64decode(data, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Vertex returned invalid video bytes") from exc
    return ManagedMediaResponse(media_type="video", mime_type=mime_type, data=data)
