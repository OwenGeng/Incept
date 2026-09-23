"""Vertex AI video adapter using Google GenAI's long-running operation API."""

from __future__ import annotations

import asyncio
import base64
import uuid

from app.ai_video.core import gcs_storage
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

        if not gcs_storage.enabled():
            raise RuntimeError("Veo video generation requires the configured GCS asset bucket")

        # Veo writes its long-running result to Cloud Storage.  Keep this
        # provider staging object in a unique private prefix, download it, and
        # let the established FileItem flow persist the final asset normally.
        output_gcs_uri = gcs_storage.object_uri(f"provider-outputs/veo/{uuid.uuid4().hex}/")
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
            # This is the SDK's documented first/last-frame configuration shape;
            # supported combinations are still enforced by the selected model.
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
                content = await gcs_storage.download_owned_uri(uri=str(output_uri))
            finally:
                await gcs_storage.delete_owned_uri(uri=str(output_uri))
        if not content:
            raise RuntimeError("Veo video output contained neither inline bytes nor a GCS URI")
        return VideoGenerationResult(
            url=f"data:video/{getattr(video, 'mime_type', None) or 'mp4'};base64,{base64.b64encode(content).decode('ascii')}",
            provider="vertex",
            provider_task_id=str(getattr(operation, "name", "") or "") or None,
            status="succeeded",
        )
