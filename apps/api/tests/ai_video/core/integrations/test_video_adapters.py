"""视频 integrations：httpx MockTransport 单测。"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from app.ai_video.core.integrations.openai.video import OpenAIVideoApiAdapter
from app.ai_video.core.integrations.vertex.omni_video import VertexOmniVideoApiAdapter
from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.contracts.video_generation import VideoGenerationInput


def _patch_httpx_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    real_client = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        timeout = kwargs.get("timeout", 60.0)
        return real_client(transport=transport, timeout=timeout)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_openai_video_create_returns_id(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url).rstrip("/").endswith("/videos")
        payload = json.loads(request.content.decode())
        assert payload["ratio"] == "16:9"
        assert payload["seed"] == 42
        assert payload["watermark"] is False
        assert payload["seconds"] == "6"
        return httpx.Response(200, json={"id": "video-1"})

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="openai", api_key="sk-test")
    inp = VideoGenerationInput.model_validate(
        {"prompt": "a cat", "ratio": "16:9", "seed": 42, "watermark": False, "seconds": 6}
    )
    vid = await OpenAIVideoApiAdapter().create_video(cfg=cfg, input_=inp, timeout_s=30.0)
    assert vid == "video-1"


@pytest.mark.asyncio
async def test_openai_video_get_returns_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/videos/v-99" in str(request.url)
        return httpx.Response(200, json={"status": "completed", "id": "v-99"})

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="openai", api_key="sk-test")
    meta = await OpenAIVideoApiAdapter().get_video(cfg=cfg, video_id="v-99", timeout_s=30.0)
    assert meta["status"] == "completed"


def test_video_input_seed_bounds_validation() -> None:
    # 边界值应可通过：-1 以及 uint32 最大值
    VideoGenerationInput.model_validate({"prompt": "ok", "ratio": "16:9", "seed": -1})
    VideoGenerationInput.model_validate({"prompt": "ok", "ratio": "16:9", "seed": 4294967295})

    # 越界值应被拒绝：小于 -1 或大于 uint32 最大值
    with pytest.raises(ValidationError):
        VideoGenerationInput.model_validate({"prompt": "bad", "ratio": "16:9", "seed": -2})
    with pytest.raises(ValidationError):
        VideoGenerationInput.model_validate({"prompt": "bad", "ratio": "16:9", "seed": 4294967296})


@pytest.mark.asyncio
async def test_gemini_omni_text_video_uses_global_interactions(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url).endswith("/v1beta1/projects/test-project/locations/global/interactions")
        payload = json.loads(request.content.decode())
        assert payload["model"] == "gemini-omni-1.1-flash-preview"
        assert payload["input"] == [{"type": "text", "text": "a flying linglonglab"}]
        assert payload["response_format"][0] == {
            "type": "video",
            "delivery": "inline",
            "aspect_ratio": "16:9",
            "duration": "6s",
            "resolution": "1080p",
        }
        assert payload["generation_config"]["video_config"]["task"] == "text_to_video"
        return httpx.Response(
            200,
            json={
                "id": "interaction-1",
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "video", "data": "dmlkZW8=", "mime_type": "video/mp4"}],
                    }
                ],
            },
        )

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    monkeypatch.setattr("app.ai_video.core.integrations.vertex.omni_video.adc_access_token", lambda: "adc-token")
    result = await VertexOmniVideoApiAdapter().generate(
        cfg=ProviderConfig(provider="vertex", api_key="", project_id="test-project", location="global"),
        inp=VideoGenerationInput.model_validate(
            {
                "prompt": "a flying linglonglab",
                "model": "gemini-omni-1.1-flash-preview",
                "ratio": "16:9",
                "seconds": 6,
                "provider_params": {"resolution": "1080p"},
            }
        ),
        timeout_s=30.0,
    )
    assert result.provider == "vertex"
    assert result.provider_task_id == "interaction-1"
    assert result.url == "data:video/mp4;base64,dmlkZW8="


@pytest.mark.asyncio
async def test_gemini_omni_rejects_data_url_reference_frames() -> None:
    with pytest.raises(RuntimeError, match="GCS image URIs"):
        await VertexOmniVideoApiAdapter().generate(
            cfg=ProviderConfig(provider="vertex", api_key="", project_id="test-project", location="global"),
            inp=VideoGenerationInput.model_validate(
                {
                    "prompt": "animate this image",
                    "model": "gemini-omni-1.1-flash-preview",
                    "ratio": "16:9",
                    "seconds": 6,
                    "first_frame_base64": "data:image/png;base64,aGVsbG8=",
                }
            ),
            timeout_s=30.0,
        )


@pytest.mark.asyncio
async def test_gemini_omni_uses_verified_gcs_reference_media(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        assert payload["input"] == [
            {"type": "text", "text": "animate this image"},
            {"type": "image", "uri": "gs://incept-assets/ai-video/files/frame.png", "mime_type": "image/png"},
        ]
        assert payload["generation_config"]["video_config"]["task"] == "reference_to_video"
        return httpx.Response(
            200,
            json={
                "id": "interaction-reference",
                "status": "completed",
                "steps": [{"type": "model_output", "content": [{"type": "video", "data": "dmlkZW8="}]}],
            },
        )

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    monkeypatch.setattr("app.ai_video.core.integrations.vertex.omni_video.adc_access_token", lambda: "adc-token")
    result = await VertexOmniVideoApiAdapter().generate(
        cfg=ProviderConfig(provider="vertex", api_key="", project_id="test-project", location="global"),
        inp=VideoGenerationInput.model_validate(
            {
                "prompt": "animate this image",
                "model": "gemini-omni-1.1-flash-preview",
                "ratio": "16:9",
                "seconds": 6,
                "reference_media": [{"uri": "gs://incept-assets/ai-video/files/frame.png", "mime_type": "image/png"}],
            }
        ),
        timeout_s=30.0,
    )
    assert result.provider_task_id == "interaction-reference"
