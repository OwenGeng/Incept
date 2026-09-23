"""OpenAI Text-to-Speech HTTP adapter."""

from __future__ import annotations

import base64

from app.ai_video.core.contracts.audio_generation import AudioGenerationInput, AudioGenerationResult
from app.ai_video.core.contracts.provider import ProviderConfig


class OpenAIAudioApiAdapter:
    """Call OpenAI's synchronous ``/audio/speech`` endpoint."""

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: AudioGenerationInput,
        timeout_s: float,
    ) -> AudioGenerationResult:
        if not inp.model:
            raise RuntimeError("OpenAI speech generation requires an explicit model selected in Model Management")
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - dependency is declared by the application
            raise RuntimeError("httpx is required for OpenAI speech generation") from exc

        body: dict[str, object] = {
            "model": inp.model,
            "input": inp.prompt,
            # OpenAI requires a voice. Alloy is the documented neutral default
            # and callers can override it explicitly through the request.
            "voice": inp.voice or "alloy",
            "response_format": inp.response_format,
        }
        if inp.speed is not None:
            body["speed"] = inp.speed
        # Do not let generic provider_params replace the selected model, script,
        # or voice. The only extra OpenAI TTS field intentionally exposed here
        # is its optional delivery instruction.
        instructions = inp.provider_params.get("instructions")
        if isinstance(instructions, str) and instructions.strip():
            body["instructions"] = instructions.strip()

        base_url = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(f"{base_url}/audio/speech", headers=headers, json=body)
            response.raise_for_status()
            raw_audio = response.content
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip() or "audio/mpeg"

        if not raw_audio:
            raise RuntimeError("OpenAI speech response contains no audio bytes")
        encoded = base64.b64encode(raw_audio).decode("ascii")
        return AudioGenerationResult(
            url=f"data:{content_type};base64,{encoded}",
            provider="openai",
            status="succeeded",
        )
