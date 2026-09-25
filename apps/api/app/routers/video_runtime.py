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

from app.ai_video.core.contracts.image_generation import ImageGenerationInput
from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.contracts.video_generation import VideoGenerationInput
from app.ai_video.core.integrations.vertex.images import VertexImageApiAdapter
from app.ai_video.core.integrations.vertex.video import VertexVideoApiAdapter
from app.incept.config import get_settings
from app.services.auth import require_internal_key


router = APIRouter(
    prefix="/api/video-runtime",
    tags=["video-runtime"],
    dependencies=[Depends(require_internal_key)],
)


class ManagedMediaRequest(BaseModel):
    media_type: Literal["image", "video"]
    prompt: str = Field(min_length=1, max_length=12_000)
    ratio: str | None = None
    size: str | None = None
    duration: int | None = Field(default=None, ge=1, le=60)
    first_frame: str | None = None
    last_frame: str | None = None


class ManagedMediaResponse(BaseModel):
    media_type: Literal["image", "video"]
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


def _chat_stream(body: dict[str, Any]) -> Iterator[str]:
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()
    if not settings.gcp_project_id:
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
    if isinstance(body.get("temperature"), (int, float)):
        config["temperature"] = body["temperature"]
    if isinstance(body.get("max_tokens"), int):
        config["max_output_tokens"] = body["max_tokens"]
    client = genai.Client(enterprise=True, project=settings.gcp_project_id, location=settings.gcp_location)
    stream = client.models.generate_content_stream(
        model=settings.vertex_gemini_model,
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
    if body.media_type == "image":
        result = await VertexImageApiAdapter().generate(
            cfg=_vertex_config(location=settings.gcp_location),
            inp=ImageGenerationInput(
                prompt=body.prompt,
                model=settings.vertex_gemini_image_model,
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

    video_model = settings.vertex_veo_model or settings.vertex_veo_fast_model
    if not video_model:
        raise HTTPException(status_code=503, detail="Vertex video model is not configured")
    result = await VertexVideoApiAdapter().generate(
        cfg=_vertex_config(location=settings.vertex_veo_location),
        inp=VideoGenerationInput(
            prompt=body.prompt,
            first_frame_base64=body.first_frame,
            last_frame_base64=body.last_frame,
            model=video_model,
            ratio=body.ratio or "16:9",
            seconds=body.duration,
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
