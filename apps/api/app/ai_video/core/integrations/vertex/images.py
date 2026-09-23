"""Gemini Enterprise Agent Platform image adapter backed by ADC."""

from __future__ import annotations

import asyncio
import base64

from app.ai_video.core.contracts.image_generation import ImageGenerationInput, ImageGenerationResult, ImageItem
from app.ai_video.core.contracts.provider import ProviderConfig


class VertexImageApiAdapter:
    """Generate still images through the configured Google Enterprise endpoint."""

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float,  # noqa: ARG002 - SDK call is bounded by worker timeout
    ) -> ImageGenerationResult:
        """Use ADC and the selected DB model; no model ID or location is inferred here."""
        if inp.images:
            raise RuntimeError(
                "Vertex reference-image generation requires an explicitly configured image-edit workflow; "
                "the generic Asset task supports text-to-image only"
            )
        if not cfg.project_id or not cfg.location:
            raise RuntimeError("Vertex image generation requires project_id and location from server configuration")
        if not inp.model:
            raise RuntimeError("Vertex image generation requires an explicit model selected in Model Management")

        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:  # pragma: no cover - deployment dependency check
            raise RuntimeError("google-genai must be installed to enable Vertex AI generation") from exc

        # gemini-3.1-flash-image is an Enterprise Agent Platform Gemini model,
        # not an Imagen publisher model.  It must use generate_content with an
        # IMAGE response modality.  Calling generate_images instead targets the
        # Vertex publisher-model path and returns a misleading model-not-found
        # error even when the configured model ID and location are valid.
        client = genai.Client(enterprise=True, project=cfg.project_id, location=cfg.location)

        def _call() -> list[ImageItem]:
            response = client.models.generate_content(
                model=inp.model,
                contents=inp.prompt[:4000],
                config=genai_types.GenerateContentConfig(
                    # The model supports one generated image per request.  The
                    # public contract permits n > 1 for providers that support
                    # it, but Enterprise image generation currently returns a
                    # single candidate per request.
                    candidateCount=1,
                    responseModalities=[
                        genai_types.Modality.TEXT,
                        genai_types.Modality.IMAGE,
                    ],
                ),
            )
            items: list[ImageItem] = []
            for candidate in getattr(response, "candidates", None) or []:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", None) or []:
                    inline_data = getattr(part, "inline_data", None)
                    raw = getattr(inline_data, "data", None) if inline_data is not None else None
                    if raw:
                        items.append(ImageItem(b64_json=base64.b64encode(raw).decode("ascii")))
            return items

        items = await asyncio.to_thread(_call)
        if not items:
            raise RuntimeError("Vertex image response contained no image bytes")
        return ImageGenerationResult(images=items, provider="vertex", status="succeeded")
