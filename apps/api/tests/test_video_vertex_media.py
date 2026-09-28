from __future__ import annotations

import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

import httpx
import pytest

from app.video_studio.vertex_media import (
    ImageGenerationInput,
    ProviderConfig,
    VertexImageApiAdapter,
    VertexOmniVideoApiAdapter,
    VertexVideoApiAdapter,
    VideoGenerationInput,
)


def _patch_httpx_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    real_client = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=transport, timeout=kwargs.get("timeout", 60.0))  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_vertex_image_uses_enterprise_generate_content(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"image-bytes"))]
                        )
                    )
                ]
            )

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["client_kwargs"] = kwargs
            self.models = FakeModels()

    class FakeConfig:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    fake_genai = ModuleType("google.genai")
    fake_genai.Client = FakeClient  # type: ignore[attr-defined]
    fake_types = ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = FakeConfig  # type: ignore[attr-defined]
    fake_types.Modality = SimpleNamespace(TEXT="TEXT", IMAGE="IMAGE")  # type: ignore[attr-defined]
    fake_genai.types = fake_types  # type: ignore[attr-defined]
    import google

    monkeypatch.setattr(google, "genai", fake_genai, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

    result = asyncio.run(
        VertexImageApiAdapter().generate(
            cfg=ProviderConfig(provider="vertex", api_key="", project_id="example-project", location="global"),
            inp=ImageGenerationInput(prompt="A bright product photo", model="configured-image-model"),
            timeout_s=30.0,
        )
    )

    assert captured["client_kwargs"] == {
        "enterprise": True,
        "project": "example-project",
        "location": "global",
    }
    assert captured["model"] == "configured-image-model"
    assert result.images[0].b64_json == "aW1hZ2UtYnl0ZXM="


def test_vertex_video_downloads_and_removes_transient_output(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    fetched: list[str] = []
    removed: list[str] = []

    class FakeModels:
        def generate_videos(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                done=True,
                name="operations/veo-test",
                response=SimpleNamespace(
                    generated_videos=[SimpleNamespace(video=SimpleNamespace(uri="gs://test-bucket/video.mp4"))]
                ),
            )

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["client_kwargs"] = kwargs
            self.models = FakeModels()
            self.operations = SimpleNamespace()

    class FakeConfig:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeImage:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    fake_genai = ModuleType("google.genai")
    fake_genai.Client = FakeClient  # type: ignore[attr-defined]
    fake_types = ModuleType("google.genai.types")
    fake_types.GenerateVideosConfig = FakeConfig  # type: ignore[attr-defined]
    fake_types.Image = FakeImage  # type: ignore[attr-defined]
    fake_genai.types = fake_types  # type: ignore[attr-defined]
    import google

    monkeypatch.setattr(google, "genai", fake_genai, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    monkeypatch.setattr("app.video_studio.vertex_media._provider_output_uri", lambda: "gs://test-bucket/video/output/")

    async def download(uri: str) -> bytes:
        fetched.append(uri)
        return b"video-bytes"

    async def delete(uri: str) -> None:
        removed.append(uri)

    monkeypatch.setattr("app.video_studio.vertex_media._download_owned_gcs_uri", download)
    monkeypatch.setattr("app.video_studio.vertex_media._delete_owned_gcs_uri", delete)

    result = asyncio.run(
        VertexVideoApiAdapter().generate(
            cfg=ProviderConfig(provider="vertex", api_key="", project_id="test-project", location="global"),
            inp=VideoGenerationInput(model="configured-video-model", prompt="A product video", ratio="16:9"),
            poll_interval_s=1,
            timeout_s=30,
        )
    )

    assert captured["model"] == "configured-video-model"
    assert fetched == ["gs://test-bucket/video.mp4"]
    assert removed == fetched
    assert result.url == "data:video/mp4;base64,dmlkZW8tYnl0ZXM="


def test_omni_video_keeps_configured_global_interactions_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/v1beta1/projects/test-project/locations/global/interactions")
        payload = json.loads(request.content.decode())
        assert payload["model"] == "gemini-omni-1.1-flash-preview"
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
    monkeypatch.setattr("app.video_studio.vertex_media._adc_access_token", lambda: "adc-token")
    result = asyncio.run(
        VertexOmniVideoApiAdapter().generate(
            cfg=ProviderConfig(provider="vertex", api_key="", project_id="test-project", location="global"),
            inp=VideoGenerationInput(
                prompt="A product video",
                model="gemini-omni-1.1-flash-preview",
                ratio="16:9",
                seconds=6,
            ),
            timeout_s=30.0,
        )
    )

    assert result.provider_task_id == "interaction-1"
    assert result.url == "data:video/mp4;base64,dmlkZW8="
