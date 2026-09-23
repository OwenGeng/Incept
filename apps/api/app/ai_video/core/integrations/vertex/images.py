"""Vertex AI image adapter backed by the existing google-genai ADC contract."""

from __future__ import annotations

import asyncio
import base64

from app.ai_video.core.contracts.image_generation import ImageGenerationInput, ImageGenerationResult, ImageItem
from app.ai_video.core.contracts.provider import ProviderConfig


class VertexImageApiAdapter:
    """Generate still images without treating Vertex as an OpenAI-compatible API."""

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

        client = genai.Client(vertexai=True, project=cfg.project_id, location=cfg.location)

        def _call() -> list[ImageItem]:
            response = client.models.generate_images(
                model=inp.model,
                prompt=inp.prompt[:4000],
                config=genai_types.GenerateImagesConfig(
                    number_of_images=min(inp.n, 4),
                    output_mime_type="image/png",
                ),
            )
            items: list[ImageItem] = []
            for generated in response.generated_images or []:
                image = getattr(generated, "image", None)
                raw = getattr(image, "image_bytes", None) if image is not None else None
                if raw:
                    items.append(ImageItem(b64_json=base64.b64encode(raw).decode("ascii")))
            return items

        items = await asyncio.to_thread(_call)
        if not items:
            raise RuntimeError("Vertex image response contained no image bytes")
        return ImageGenerationResult(images=items, provider="vertex", status="succeeded")
