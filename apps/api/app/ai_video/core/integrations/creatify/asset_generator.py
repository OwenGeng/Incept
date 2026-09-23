"""HTTP client for Creatify Asset Generator.

The API catalog is deliberately discovered at runtime.  This module does not
contain a model allowlist or parameter mapping, because Creatify model variants
and their input JSON Schemas change independently of Linglong Lab releases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai_video.core.contracts.provider import ProviderConfig


@dataclass(frozen=True, slots=True)
class CreatifyAssetJob:
    """Normalized external job state returned by the Asset Generator API."""

    id: str
    status: str
    assets: tuple[dict[str, Any], ...]
    raw: dict[str, Any]

    @property
    def is_terminal(self) -> bool:
        return self.status.lower() in {"completed", "succeeded", "done", "failed", "cancelled", "canceled"}

    @property
    def is_successful(self) -> bool:
        return self.status.lower() in {"completed", "succeeded", "done"}


class CreatifyAssetGeneratorAdapter:
    """Call Creatify's schema, create, and status endpoints with safe auth headers."""

    @staticmethod
    def _base_url(cfg: ProviderConfig) -> str:
        return (cfg.base_url or "https://api.creatify.ai/api").rstrip("/")

    @staticmethod
    def _headers(cfg: ProviderConfig) -> dict[str, str]:
        api_id = (cfg.api_secret or "").strip()
        api_key = (cfg.api_key or "").strip()
        if not api_id or not api_key:
            raise RuntimeError("Creatify credentials are missing; configure CREATIFY_API_ID and CREATIFY_API_KEY server-side")
        return {"X-API-ID": api_id, "X-API-KEY": api_key, "Content-Type": "application/json"}

    async def list_schemas(self, *, cfg: ProviderConfig, timeout_s: float = 30.0) -> list[dict[str, Any]]:
        """Fetch the live model catalog and normalize common API envelope shapes."""
        import httpx

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(
                f"{self._base_url(cfg)}/asset_generator/schemas/",
                headers=self._headers(cfg),
            )
            response.raise_for_status()
            payload = response.json()
        return _as_catalog_items(payload)

    async def create_asset(
        self,
        *,
        cfg: ProviderConfig,
        model_name: str,
        input_params: dict[str, Any],
        webhook_url: str | None = None,
        timeout_s: float = 60.0,
    ) -> CreatifyAssetJob:
        """Submit one asynchronous asset job using a catalog-validated payload."""
        import httpx

        body: dict[str, Any] = {"model_name": model_name, "input_params": input_params}
        if webhook_url:
            body["webhook_url"] = webhook_url
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                f"{self._base_url(cfg)}/asset_generator/",
                headers=self._headers(cfg),
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
        return _parse_job(payload)

    async def get_asset(self, *, cfg: ProviderConfig, asset_id: str, timeout_s: float = 30.0) -> CreatifyAssetJob:
        """Read a previously submitted Asset Generator job without creating work."""
        import httpx

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(
                f"{self._base_url(cfg)}/asset_generator/{asset_id}/",
                headers=self._headers(cfg),
            )
            response.raise_for_status()
            payload = response.json()
        return _parse_job(payload)


def _as_catalog_items(payload: Any) -> list[dict[str, Any]]:
    """Accept the documented list response and compatible paginated envelopes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise RuntimeError("Creatify schema response is not a JSON object or list")
    for key in ("results", "data", "schemas", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("Creatify schema response contains no catalog list")


def _parse_job(payload: Any) -> CreatifyAssetJob:
    """Normalize job fields while retaining raw output for forward compatibility."""
    if not isinstance(payload, dict):
        raise RuntimeError("Creatify asset response is not a JSON object")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    job_id = str(data.get("id") or data.get("asset_id") or data.get("task_id") or "").strip()
    if not job_id:
        raise RuntimeError("Creatify asset response has no job id")
    raw_assets = data.get("assets") or []
    assets = tuple(item for item in raw_assets if isinstance(item, dict)) if isinstance(raw_assets, list) else ()
    return CreatifyAssetJob(
        id=job_id,
        status=str(data.get("status") or "pending").strip().lower() or "pending",
        assets=assets,
        raw=data,
    )
