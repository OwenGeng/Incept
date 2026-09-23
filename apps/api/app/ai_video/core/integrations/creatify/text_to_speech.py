"""Creatify Text-to-Speech API adapter.

Creatify TTS is a dedicated asynchronous API, not an Asset Generator model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai_video.core.contracts.provider import ProviderConfig


@dataclass(frozen=True, slots=True)
class CreatifySpeechJob:
    id: str
    status: str
    output_url: str | None
    failed_reason: str | None
    duration_seconds: int | None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"done", "failed", "cancelled", "canceled"}

    @property
    def is_successful(self) -> bool:
        return self.status == "done"


class CreatifyTextToSpeechAdapter:
    """Submit and poll Creatify's documented Text-to-Speech resource."""

    @staticmethod
    def _base_url(cfg: ProviderConfig) -> str:
        return (cfg.base_url or "https://api.creatify.ai/api").rstrip("/")

    @staticmethod
    def _headers(cfg: ProviderConfig) -> dict[str, str]:
        api_id = (cfg.api_secret or "").strip()
        api_key = (cfg.api_key or "").strip()
        if not api_id or not api_key:
            raise RuntimeError("Creatify credentials are missing; configure API ID and API key server-side")
        return {"X-API-ID": api_id, "X-API-KEY": api_key, "Content-Type": "application/json"}

    async def create(
        self,
        *,
        cfg: ProviderConfig,
        script: str,
        accent: str | None,
        webhook_url: str | None,
        timeout_s: float,
    ) -> CreatifySpeechJob:
        import httpx

        body: dict[str, object] = {"script": script}
        if accent:
            body["accent"] = accent
        if webhook_url:
            body["webhook_url"] = webhook_url
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                f"{self._base_url(cfg)}/text_to_speech/",
                headers=self._headers(cfg),
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
        return _parse_job(payload)

    async def get(self, *, cfg: ProviderConfig, job_id: str, timeout_s: float) -> CreatifySpeechJob:
        import httpx

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(
                f"{self._base_url(cfg)}/text_to_speech/{job_id}/",
                headers=self._headers(cfg),
            )
            response.raise_for_status()
            payload = response.json()
        return _parse_job(payload)


def _parse_job(payload: Any) -> CreatifySpeechJob:
    if not isinstance(payload, dict):
        raise RuntimeError("Creatify Text-to-Speech response is not a JSON object")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    job_id = str(data.get("id") or "").strip()
    if not job_id:
        raise RuntimeError("Creatify Text-to-Speech response has no job id")
    duration = data.get("duration")
    return CreatifySpeechJob(
        id=job_id,
        status=str(data.get("status") or "pending").strip().lower() or "pending",
        output_url=str(data.get("output") or "").strip() or None,
        failed_reason=str(data.get("failed_reason") or "").strip() or None,
        duration_seconds=int(duration) if isinstance(duration, int | float) else None,
    )
