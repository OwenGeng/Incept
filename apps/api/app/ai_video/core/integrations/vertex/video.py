"""Vertex AI video adapter using Google GenAI's long-running operation API."""

from __future__ import annotations

import asyncio
import base64

from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.contracts.video_generation import VideoGenerationInput, VideoGenerationResult


def _decode_data_image(value: str | None) -> tuple[bytes, str] | None:
    """Decode Linglong Lab's existing data-URL reference format for the Vertex SDK."""
    if not value:
        return None
    raw = value.strip()
    if not raw.startswith("data:") or ";base64," not in raw:
        raise RuntimeError("Vertex video reference frames must be data URLs")
    header, encoded = raw.split(";base64,", 1)
    return base64.b64decode(encoded), header[5:] or "image/png"


class VertexVideoApiAdapter:
    """Submit and poll a Vertex video operation for the explicitly selected model."""

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: VideoGenerationInput,
        poll_interval_s: float,
        timeout_s: float,
    ) -> VideoGenerationResult:
        """Run a Vertex long-running operation and return portable data-url bytes.

        The implementation purposefully has no fallback model or location.  It
        consumes only the model chosen in Linglong Lab Model Management and ADC
        project/location configuration supplied by the deployment.
        """
        if not cfg.project_id or not cfg.location:
            raise RuntimeError("Vertex video generation requires project_id and location from server configuration")
        if not inp.model:
            raise RuntimeError("Vertex video generation requires an explicit model selected in Model Management")
        if inp.model == "gemini-omni-1.1-flash-preview":
            from app.ai_video.core.integrations.vertex.omni_video import VertexOmniVideoApiAdapter

            return await VertexOmniVideoApiAdapter().generate(
                cfg=cfg,
                inp=inp,
                timeout_s=timeout_s,
            )
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:  # pragma: no cover - deployment dependency check
            raise RuntimeError("google-genai must be installed to enable Vertex AI generation") from exc

        client = genai.Client(vertexai=True, project=cfg.project_id, location=cfg.location)
        config_kwargs: dict[str, object] = {"number_of_videos": 1, "aspect_ratio": inp.ratio}
        if inp.seconds is not None:
            config_kwargs["duration_seconds"] = inp.seconds
        config = genai_types.GenerateVideosConfig(**config_kwargs)
        kwargs: dict[str, object] = {"model": inp.model, "prompt": inp.prompt or "", "config": config}

        first = _decode_data_image(inp.first_frame_base64 or inp.key_frame_base64)
        last = _decode_data_image(inp.last_frame_base64)
        if first:
            kwargs["image"] = genai_types.Image(image_bytes=first[0], mime_type=first[1])
        if last:
            # This is the SDK's documented first/last-frame configuration shape;
            # supported combinations are still enforced by the selected model.
            config.last_frame = genai_types.Image(image_bytes=last[0], mime_type=last[1])

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
        content = getattr(video, "video_bytes", None) if video is not None else None
        if not content:
            raise RuntimeError("Vertex video output has no inline bytes; configure durable output storage before enabling this model")
        return VideoGenerationResult(
            url=f"data:video/{getattr(video, 'mime_type', None) or 'mp4'};base64,{base64.b64encode(content).decode('ascii')}",
            provider="vertex",
            provider_task_id=str(getattr(operation, "name", "") or "") or None,
            status="succeeded",
        )
