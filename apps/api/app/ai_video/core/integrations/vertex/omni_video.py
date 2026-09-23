"""Gemini Omni 1.1 Flash Preview adapter for the Agent Platform Interactions API."""

from __future__ import annotations

import asyncio
from typing import Any

from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.contracts.video_generation import VideoGenerationInput, VideoGenerationResult
from app.ai_video.core.integrations.vertex.auth import adc_access_token


_OMNI_MODEL = "gemini-omni-1.1-flash-preview"
_ALLOWED_RATIOS = {"16:9", "9:16"}
_ALLOWED_RESOLUTIONS = {"360p", "720p", "1080p", "4k"}


class VertexOmniVideoApiAdapter:
    """Generate a video through Gemini Omni's documented global Interactions API."""

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: VideoGenerationInput,
        timeout_s: float,
    ) -> VideoGenerationResult:
        """Submit a stateless Omni request and normalize its inline video output.

        Reference media is passed only as server-verified, deployment-owned
        GCS image URIs. Browser-supplied URLs and data URLs are deliberately
        not supported by this adapter.
        """
        if not cfg.project_id or not cfg.location:
            raise RuntimeError("Gemini Omni video generation requires project_id and location from server configuration")
        if cfg.location != "global":
            raise RuntimeError("Gemini Omni 1.1 Flash Preview requires the configured Vertex location to be global")
        if inp.model != _OMNI_MODEL:
            raise RuntimeError(f"Unsupported Gemini Omni video model: {inp.model}")
        if inp.ratio not in _ALLOWED_RATIOS:
            raise RuntimeError("Gemini Omni supports only 16:9 or 9:16 video ratios")
        if inp.seconds is None or not 3 <= inp.seconds <= 10:
            raise RuntimeError("Gemini Omni video duration must be between 3 and 10 seconds")
        if any((inp.first_frame_base64, inp.last_frame_base64, inp.key_frame_base64)):
            raise RuntimeError(
                "Gemini Omni reference video requires deployment-owned GCS image URIs, not base64 frames."
            )
        for reference in inp.reference_media:
            if not reference.uri.startswith("gs://") or not reference.mime_type.startswith("image/"):
                raise RuntimeError("Gemini Omni reference media must be a GCS image URI with a verified image MIME type")

        resolution = inp.provider_params.get("resolution")
        if resolution is not None and resolution not in _ALLOWED_RESOLUTIONS:
            raise RuntimeError("Gemini Omni resolution must be one of 360p, 720p, 1080p, or 4k")

        response_format: dict[str, str] = {
            "type": "video",
            "delivery": "uri",
            "aspect_ratio": inp.ratio,
            "duration": f"{inp.seconds}s",
        }
        if resolution is not None:
            response_format["resolution"] = resolution
        input_items: list[dict[str, str]] = [{"type": "text", "text": (inp.prompt or "").strip()}]
        input_items.extend(
            {"type": "image", "uri": reference.uri, "mime_type": reference.mime_type}
            for reference in inp.reference_media
        )
        request_body: dict[str, Any] = {
            "model": _OMNI_MODEL,
            "input": input_items,
            "response_format": [response_format],
            "generation_config": {
                "video_config": {"task": "reference_to_video" if inp.reference_media else "text_to_video"}
            },
        }
        token = await asyncio.to_thread(adc_access_token)
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - project dependency check
            raise RuntimeError("httpx is required for Gemini Omni video generation") from exc
        endpoint = f"https://aiplatform.googleapis.com/v1beta1/projects/{cfg.project_id}/locations/global/interactions"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(endpoint, headers=headers, json=request_body)
            response.raise_for_status()
            payload = response.json()
        return _parse_omni_response(payload)


def _parse_omni_response(payload: Any) -> VideoGenerationResult:
    """Extract inline video bytes from a completed stateless Interactions response."""
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
        content = step.get("content")
        if not isinstance(content, list):
            continue
        for artifact in content:
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
