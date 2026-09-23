"""Vertex Lyria 3 music adapter using the documented global interactions API."""

from __future__ import annotations

import asyncio
from typing import Any

from app.ai_video.core.contracts.audio_generation import AudioGenerationInput, AudioGenerationResult
from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.integrations.vertex.auth import adc_access_token


class VertexMusicApiAdapter:
    """Generate Lyria 3 background music with ADC authentication."""

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: AudioGenerationInput,
        timeout_s: float,
    ) -> AudioGenerationResult:
        if not cfg.project_id or not cfg.location:
            raise RuntimeError("Vertex music generation requires project_id and location from server configuration")
        if cfg.location != "global":
            raise RuntimeError("Lyria 3 requires the configured Vertex location to be global")
        if not inp.model:
            raise RuntimeError("Vertex music generation requires an explicit model selected in Model Management")
        if inp.model not in {"lyria-3-clip-preview", "lyria-3-pro-preview"}:
            raise RuntimeError(f"Unsupported Vertex music model: {inp.model}")

        token = await asyncio.to_thread(adc_access_token)
        request_body: dict[str, Any] = {
            "model": inp.model,
            "input": [{"type": "text", "text": inp.prompt}],
        }
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("httpx is required for Vertex music generation") from exc
        endpoint = f"https://aiplatform.googleapis.com/v1beta1/projects/{cfg.project_id}/locations/global/interactions"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(endpoint, headers=headers, json=request_body)
            response.raise_for_status()
            payload = response.json()
        return _parse_lyria_response(payload, model=inp.model)


def _parse_lyria_response(payload: Any, *, model: str) -> AudioGenerationResult:
    if not isinstance(payload, dict):
        raise RuntimeError("Vertex Lyria response is not a JSON object")
    status = str(payload.get("status") or "").strip().lower()
    if status and status != "completed":
        raise RuntimeError(f"Vertex Lyria generation did not complete: {status}")
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        raise RuntimeError("Vertex Lyria response contains no outputs")
    for item in outputs:
        if not isinstance(item, dict) or item.get("type") != "audio":
            continue
        data = str(item.get("data") or "").strip()
        if data:
            content_type = str(item.get("mime_type") or "audio/mpeg").strip()
            return AudioGenerationResult(
                url=f"data:{content_type};base64,{data}",
                provider="vertex",
                provider_task_id=None,
                status="succeeded",
            )
    raise RuntimeError(f"Vertex Lyria {model} response contains no audio output")
