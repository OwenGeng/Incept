"""Audio adapter contract tests using HTTPX MockTransport only."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.ai_video.core.contracts.audio_generation import AudioGenerationInput
from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.integrations.creatify.text_to_speech import CreatifyTextToSpeechAdapter
from app.ai_video.core.integrations.openai.audio import OpenAIAudioApiAdapter
from app.ai_video.core.integrations.vertex.music import _parse_lyria_response


def _patch_httpx_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    real_client = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=transport, timeout=kwargs.get("timeout", 60.0))  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_openai_tts_adapter_returns_portable_data_url(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["body"] = json.loads(request.content.decode())
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, content=b"audio-bytes", headers={"Content-Type": "audio/mpeg"})

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    result = await OpenAIAudioApiAdapter().generate(
        cfg=ProviderConfig(provider="openai", api_key="sk-test"),
        inp=AudioGenerationInput(prompt="Hello", model="gpt-4o-mini-tts", voice="coral"),
        timeout_s=30,
    )
    assert observed["path"] == "/v1/audio/speech"
    assert observed["body"] == {
        "model": "gpt-4o-mini-tts",
        "input": "Hello",
        "voice": "coral",
        "response_format": "mp3",
    }
    assert result.url == "data:audio/mpeg;base64," + base64.b64encode(b"audio-bytes").decode()


@pytest.mark.asyncio
async def test_creatify_tts_adapter_uses_dedicated_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"id": "job-1", "status": "pending"})
        return httpx.Response(
            200,
            json={"id": "job-1", "status": "done", "output": "https://cdn.example.com/audio.mp3", "duration": 12},
        )

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="creatify", api_key="key", api_secret="id")
    adapter = CreatifyTextToSpeechAdapter()
    created = await adapter.create(cfg=cfg, script="A script", accent="accent-1", webhook_url=None, timeout_s=30)
    completed = await adapter.get(cfg=cfg, job_id=created.id, timeout_s=30)
    assert calls[0].url.path == "/api/text_to_speech/"
    assert json.loads(calls[0].content.decode()) == {"script": "A script", "accent": "accent-1"}
    assert calls[1].url.path == "/api/text_to_speech/job-1/"
    assert completed.is_successful
    assert completed.output_url == "https://cdn.example.com/audio.mp3"
    assert completed.duration_seconds == 12


def test_lyria_response_returns_audio_data_url() -> None:
    result = _parse_lyria_response(
        {
            "status": "completed",
            "outputs": [{"type": "audio", "mime_type": "audio/mpeg", "data": "YWJj"}],
        },
        model="lyria-3-clip-preview",
    )
    assert result.provider == "vertex"
    assert result.url == "data:audio/mpeg;base64,YWJj"
