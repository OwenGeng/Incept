"""Vertex media generation owned by the LinglongLab Video workspace.

This module is intentionally small: it contains only the image/video contracts
and Google Cloud adapters used by ``/api/video-runtime``. Model IDs, locations,
project IDs and the asset bucket always come from the existing LinglongLab settings.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.incept.config import get_settings


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    provider: Literal["vertex"]
    api_key: str
    project_id: str | None = None
    location: str | None = None


class ImageGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    model: str | None = None
    target_ratio: str | None = None
    size: str | None = None
    response_format: Literal["url", "b64_json"] = "url"
    images: list[str] = Field(default_factory=list)


class ImageItem(BaseModel):
    b64_json: str | None = None


class ImageGenerationResult(BaseModel):
    images: list[ImageItem]
    provider: Literal["vertex"]
    status: str


class VideoReferenceMedia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str
    mime_type: str


class VideoGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str | None = None
    first_frame_base64: str | None = None
    last_frame_base64: str | None = None
    key_frame_base64: str | None = None
    reference_media: list[VideoReferenceMedia] = Field(default_factory=list)
    model: str | None = None
    ratio: str = "16:9"
    seconds: int | None = None
    provider_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_prompt_or_reference(self) -> "VideoGenerationInput":
        if not (self.prompt or "").strip() and not any(
            (
                self.first_frame_base64,
                self.last_frame_base64,
                self.key_frame_base64,
                self.reference_media,
            )
        ):
            raise ValueError("Video generation requires a prompt or reference media")
        return self


class VideoGenerationResult(BaseModel):
    url: str
    provider: Literal["vertex"]
    provider_task_id: str | None = None
    status: str


def _asset_bucket() -> str:
    bucket = (get_settings().incept_asset_bucket or "").strip()
    if not bucket or bucket == "INCEPT_ASSET_BUCKET":
        raise RuntimeError("Veo video generation requires a configured INCEPT_ASSET_BUCKET")
    return bucket


@lru_cache
def _gcs_client():
    try:
        from google.cloud import storage
    except ImportError as exc:  # pragma: no cover - deployment dependency check
        raise RuntimeError("google-cloud-storage must be installed to use Vertex video generation") from exc
    settings = get_settings()
    return storage.Client(project=settings.gcp_project_id or None)


def _provider_output_uri() -> str:
    return f"gs://{_asset_bucket()}/video/provider-outputs/veo/{uuid.uuid4().hex}/"


def _parse_owned_gcs_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    bucket = parsed.netloc.strip()
    object_key = unquote(parsed.path.lstrip("/"))
    if parsed.scheme != "gs" or not bucket or not object_key:
        raise RuntimeError("Vertex returned an invalid GCS output URI")
    if bucket != _asset_bucket():
        raise RuntimeError("Vertex returned output outside the configured LinglongLab asset bucket")
    return bucket, object_key


async def _download_owned_gcs_uri(uri: str) -> bytes:
    bucket, object_key = _parse_owned_gcs_uri(uri)
    return await asyncio.to_thread(
        _gcs_client().bucket(bucket).blob(object_key).download_as_bytes
    )


async def _delete_owned_gcs_uri(uri: str) -> None:
    bucket, object_key = _parse_owned_gcs_uri(uri)
    await asyncio.to_thread(_gcs_client().bucket(bucket).blob(object_key).delete)


def _decode_data_image(value: str | None) -> tuple[bytes, str] | None:
    if not value:
        return None
    raw = value.strip()
    if not raw.startswith("data:") or ";base64," not in raw:
        raise RuntimeError("Vertex video reference frames must be data URLs")
    header, encoded = raw.split(";base64,", 1)
    return base64.b64decode(encoded), header[5:] or "image/png"


@asynccontextmanager
async def _omni_reference_frames(inp: VideoGenerationInput):
    uploaded = []
    references = list(inp.reference_media)
    try:
        for value in (inp.first_frame_base64 or inp.key_frame_base64, inp.last_frame_base64):
            decoded = _decode_data_image(value)
            if decoded is None:
                continue
            data, mime = decoded
            if mime not in {'image/png', 'image/jpeg', 'image/webp'} or not 0 < len(data) <= 20 * 1024 * 1024:
                raise RuntimeError('Omni reference must be a PNG, JPEG or WebP image under 20 MiB')
            bucket = _asset_bucket()
            key = f'video/provider-inputs/omni/{uuid.uuid4().hex}'
            blob = _gcs_client().bucket(bucket).blob(key)
            task = asyncio.create_task(asyncio.to_thread(blob.upload_from_string, data,
                content_type=mime, if_generation_match=0, timeout=30))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await task  # Finish the bounded upload before deleting its result.
                uploaded.append(blob)
                raise
            uploaded.append(blob)
            references.append(VideoReferenceMedia(uri=f'gs://{bucket}/{key}', mime_type=mime))
        yield inp.model_copy(update={'first_frame_base64': None, 'last_frame_base64': None,
            'key_frame_base64': None, 'reference_media': references})
    finally:
        for blob in uploaded:
            await asyncio.to_thread(blob.delete, if_generation_match=blob.generation, timeout=30)


class VertexImageApiAdapter:
    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float,
    ) -> ImageGenerationResult:
        if not cfg.project_id or not cfg.location:
            raise RuntimeError("Vertex image generation requires configured project and location values")
        if not inp.model:
            raise RuntimeError("Vertex image generation requires the configured LinglongLab image model")
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:  # pragma: no cover - deployment dependency check
            raise RuntimeError("google-genai must be installed to enable Vertex AI generation") from exc

        client = genai.Client(enterprise=True, project=cfg.project_id, location=cfg.location, http_options={'timeout': max(1, int(timeout_s * 1000))})

        def call() -> list[ImageItem]:
            contents: Any = inp.prompt[:4000]
            if inp.images:
                if len(inp.images) > 4:
                    raise ValueError("Image editing supports at most four references")
                parts = []
                for image in inp.images:
                    reference = _decode_data_image(image)
                    if reference is None:
                        raise ValueError("Image references must be inline data images")
                    raw, mime_type = reference
                    if not mime_type.startswith("image/") or len(raw) > 25 * 1024 * 1024:
                        raise ValueError("Invalid or oversized image reference")
                    parts.append(genai_types.Part.from_bytes(data=raw, mime_type=mime_type))
                contents = [*parts, inp.prompt[:4000]]
            response = client.models.generate_content(
                model=inp.model,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    candidateCount=1,
                    responseModalities=[genai_types.Modality.TEXT, genai_types.Modality.IMAGE],
                    image_config=genai_types.ImageConfig(aspect_ratio=inp.target_ratio) if inp.target_ratio else None,
                ),
            )
            images: list[ImageItem] = []
            for candidate in getattr(response, "candidates", None) or []:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", None) or []:
                    inline_data = getattr(part, "inline_data", None)
                    raw = getattr(inline_data, "data", None) if inline_data is not None else None
                    if raw:
                        images.append(ImageItem(b64_json=base64.b64encode(raw).decode("ascii")))
            return images

        images = await asyncio.to_thread(call)
        if not images:
            raise RuntimeError("Vertex image response contained no image bytes")
        return ImageGenerationResult(images=images, provider="vertex", status="succeeded")


class VertexVideoApiAdapter:
    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: VideoGenerationInput,
        poll_interval_s: float,
        timeout_s: float,
    ) -> VideoGenerationResult:
        if not cfg.project_id or not cfg.location:
            raise RuntimeError("Vertex video generation requires configured project and location values")
        if not inp.model:
            raise RuntimeError("Vertex video generation requires the configured LinglongLab video model")
        if inp.model == "gemini-omni-1.1-flash-preview":
            async with _omni_reference_frames(inp) as prepared:
                return await VertexOmniVideoApiAdapter().generate(cfg=cfg, inp=prepared, timeout_s=timeout_s)
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:  # pragma: no cover - deployment dependency check
            raise RuntimeError("google-genai must be installed to enable Vertex AI generation") from exc

        output_gcs_uri = _provider_output_uri()
        client = genai.Client(enterprise=True, project=cfg.project_id, location=cfg.location)
        config_kwargs: dict[str, object] = {
            "numberOfVideos": 1,
            "aspectRatio": inp.ratio,
            "outputGcsUri": output_gcs_uri,
        }
        if inp.seconds is not None:
            config_kwargs["durationSeconds"] = inp.seconds
        config = genai_types.GenerateVideosConfig(**config_kwargs)
        kwargs: dict[str, object] = {"model": inp.model, "prompt": inp.prompt or "", "config": config}

        first = _decode_data_image(inp.first_frame_base64 or inp.key_frame_base64)
        last = _decode_data_image(inp.last_frame_base64)
        if first:
            kwargs["image"] = genai_types.Image(imageBytes=first[0], mimeType=first[1])
        if last:
            config.lastFrame = genai_types.Image(imageBytes=last[0], mimeType=last[1])

        operation = await asyncio.to_thread(client.models.generate_videos, **kwargs)
        waited = 0.0
        while not getattr(operation, "done", False):
            if waited >= timeout_s:
                raise TimeoutError("Vertex video operation did not finish before task timeout")
            await asyncio.sleep(poll_interval_s)
            waited += poll_interval_s
            operation = await asyncio.to_thread(client.operations.get, operation)
        if getattr(operation, "error", None):
            raise RuntimeError(f"Vertex video operation failed: {operation.error}")
        response = getattr(operation, "result", None) or getattr(operation, "response", None)
        generated = getattr(response, "generated_videos", None) or []
        if not generated:
            raise RuntimeError("Vertex video operation completed without generated videos")
        video = getattr(generated[0], "video", None)
        content = (
            getattr(video, "videoBytes", None) or getattr(video, "video_bytes", None)
            if video is not None
            else None
        )
        output_uri = getattr(video, "uri", None) if video is not None else None
        if not content and output_uri:
            try:
                content = await _download_owned_gcs_uri(str(output_uri))
            finally:
                await _delete_owned_gcs_uri(str(output_uri))
        if not content:
            raise RuntimeError("Veo video output contained neither inline bytes nor a GCS URI")
        mime_type = getattr(video, "mime_type", None) or "mp4"
        return VideoGenerationResult(
            url=f"data:video/{mime_type};base64,{base64.b64encode(content).decode('ascii')}",
            provider="vertex",
            provider_task_id=str(getattr(operation, "name", "") or "") or None,
            status="succeeded",
        )


def _adc_access_token() -> str:
    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError as exc:  # pragma: no cover - deployment dependency check
        raise RuntimeError("google-auth must be installed to enable Vertex generation") from exc
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    token = str(credentials.token or "").strip()
    if not token:
        raise RuntimeError("Vertex ADC did not provide an access token")
    return token


class VertexOmniVideoApiAdapter:
    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: VideoGenerationInput,
        timeout_s: float,
    ) -> VideoGenerationResult:
        if not cfg.project_id or not cfg.location:
            raise RuntimeError("Gemini Omni video generation requires configured project and location values")
        if cfg.location != "global":
            raise RuntimeError("Gemini Omni 1.1 Flash Preview requires the configured Vertex location to be global")
        if inp.model != "gemini-omni-1.1-flash-preview":
            raise RuntimeError(f"Unsupported Gemini Omni video model: {inp.model}")
        if inp.ratio not in {"16:9", "9:16"}:
            raise RuntimeError("Gemini Omni supports only 16:9 or 9:16 video ratios")
        if inp.seconds is None or not 3 <= inp.seconds <= 10:
            raise RuntimeError("Gemini Omni video duration must be between 3 and 10 seconds")
        if any((inp.first_frame_base64, inp.last_frame_base64, inp.key_frame_base64)):
            raise RuntimeError("Gemini Omni reference video requires deployment-owned GCS image URIs")
        for reference in inp.reference_media:
            if not reference.uri.startswith("gs://") or not reference.mime_type.startswith("image/"):
                raise RuntimeError("Gemini Omni reference media must be a verified GCS image URI")
        resolution = inp.provider_params.get("resolution")
        if resolution is not None and resolution not in {"360p", "720p", "1080p", "4k"}:
            raise RuntimeError("Gemini Omni resolution must be one of 360p, 720p, 1080p, or 4k")

        response_format: dict[str, str] = {
            "type": "video",
            "delivery": "inline",
            "aspect_ratio": inp.ratio,
            "duration": f"{inp.seconds}s",
        }
        if resolution is not None:
            response_format["resolution"] = str(resolution)
        input_items: list[dict[str, str]] = [{"type": "text", "text": (inp.prompt or "").strip()}]
        input_items.extend(
            {"type": "image", "uri": reference.uri, "mime_type": reference.mime_type}
            for reference in inp.reference_media
        )
        request_body: dict[str, Any] = {
            "model": inp.model,
            "input": input_items,
            "response_format": [response_format],
            "generation_config": {
                "video_config": {"task": "reference_to_video" if inp.reference_media else "text_to_video"}
            },
        }
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - project dependency check
            raise RuntimeError("httpx is required for Gemini Omni video generation") from exc
        token = await asyncio.to_thread(_adc_access_token)
        endpoint = (
            f"https://aiplatform.googleapis.com/v1beta1/projects/{cfg.project_id}"
            "/locations/global/interactions"
        )
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                json=request_body,
            )
            response.raise_for_status()
            payload = response.json()
        return _parse_omni_response(payload)


def _parse_omni_response(payload: Any) -> VideoGenerationResult:
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini Omni response is not a JSON object")
    status = str(payload.get("status") or "").strip().lower()
    if status != "completed":
        raise RuntimeError(f"Gemini Omni generation did not complete: {status or 'unknown status'}")
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise RuntimeError("Gemini Omni response contains no output steps")
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for artifact in step.get("content") if isinstance(step.get("content"), list) else []:
            if not isinstance(artifact, dict) or artifact.get("type") != "video":
                continue
            data = str(artifact.get("data") or "").strip()
            if not data:
                continue
            content_type = str(artifact.get("mime_type") or "video/mp4").strip()
            return VideoGenerationResult(
                url=f"data:{content_type};base64,{data}",
                provider="vertex",
                provider_task_id=str(payload.get("id") or "").strip() or None,
                status="succeeded",
            )
    raise RuntimeError("Gemini Omni response contains no inline video output")
