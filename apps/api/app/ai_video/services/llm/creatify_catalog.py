"""Synchronize Creatify's live Asset Generator catalog into Linglong Lab models.

The JSON Schema is stored with each model instead of being translated into a
static server-side model list. The explicitly approved Creatify families are
enabled on first discovery; a sync never deletes, changes a default, or
overrides an administrator's later enablement choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.core.contracts.provider import ProviderConfig
from app.ai_video.core.integrations.creatify import CreatifyAssetGeneratorAdapter
from app.ai_video.models.llm import Model, ModelCategoryKey, Provider
from app.ai_video.services.llm.provider_resolver import resolve_provider_config_from_provider
from app.ai_video.services.llm.provider_registry import resolve_provider_key_from_name
from app.ai_video.bootstrap import bootstrap_all_registries


@dataclass(frozen=True, slots=True)
class CreatifyCatalogSyncResult:
    """Counts returned after a non-destructive Creatify catalog synchronization."""

    discovered: int
    created: int
    updated: int
    skipped: int


def creatify_model_id(model_name: str) -> str:
    """Create a stable database-safe model identifier from a provider model name."""
    return f"creatify-{sha256(model_name.encode('utf-8')).hexdigest()[:48]}"


def _category_for_item(item: dict[str, Any]) -> ModelCategoryKey | None:
    """Map documented image/video media types without guessing unsupported types."""
    raw = str(item.get("media_type") or item.get("type") or "").strip().lower()
    if raw == "image":
        return ModelCategoryKey.image
    if raw == "video":
        return ModelCategoryKey.video
    return None


def _is_requested_creatify_family(item: dict[str, Any]) -> bool:
    """Recognize approved product families without hard-coding catalog IDs.

    The live Creatify catalog remains authoritative for variant identifiers and
    JSON Schema. This policy only enables newly found Seedance 2.0/2.5 and
    Kling O3 Standard variants; it never changes an existing choice.
    """
    label = " ".join(
        str(item.get(key) or "").strip().casefold()
        for key in ("title", "model_name", "name", "description")
    )
    return any(token in label for token in ("seedance 2.0", "seedance 2.5", "kling o3 standard"))


async def sync_creatify_catalog(
    db: AsyncSession,
    *,
    provider_id: str,
    adapter: CreatifyAssetGeneratorAdapter | None = None,
) -> CreatifyCatalogSyncResult:
    """Fetch the current Creatify catalog and upsert schema-backed models.

    Existing custom values are deliberately preserved.  The remote schema,
    description, media type, and timestamp are refreshed under the
    `creatify_catalog` namespace so generated jobs remain reproducible.
    """
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    bootstrap_all_registries()
    if resolve_provider_key_from_name(provider.name) != "creatify":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider is not Creatify")

    resolved = resolve_provider_config_from_provider(provider=provider, category=ModelCategoryKey.video)
    client = adapter or CreatifyAssetGeneratorAdapter()
    items = await client.list_schemas(
        cfg=ProviderConfig(
            provider="creatify",
            api_key=resolved.api_key,
            api_secret=resolved.api_secret,
            base_url=resolved.base_url,
        )
    )

    created = updated = skipped = 0
    synced_at = datetime.now(UTC).isoformat()
    for item in items:
        model_name = str(item.get("model_name") or item.get("name") or "").strip()
        category = _category_for_item(item)
        schema = item.get("input_params_schema")
        if not model_name or category is None or not isinstance(schema, dict):
            skipped += 1
            continue

        model_id = creatify_model_id(model_name)
        row = await db.get(Model, model_id)
        catalog = {
            "model_name": model_name,
            "media_type": category.value,
            "title": str(item.get("title") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "plan_level": str(item.get("plan_level") or "").strip(),
            "input_params_schema": schema,
            "synced_at": synced_at,
        }
        if row is None:
            db.add(
                Model(
                    id=model_id,
                    name=model_name,
                    category=category,
                    provider_id=provider.id,
                    params={
                        "catalog_source": "creatify",
                        "enabled": _is_requested_creatify_family(item),
                        "creatify_catalog": catalog,
                    },
                    description=catalog["description"],
                    created_by="creatify-catalog-sync",
                )
            )
            created += 1
            continue

        # A catalog model can be transferred between model categories only when
        # it already belongs to this same Creatify provider; a conflicting ID is
        # a configuration error rather than something sync should overwrite.
        if row.provider_id != provider.id:
            skipped += 1
            continue
        params = dict(row.params or {})
        params["catalog_source"] = "creatify"
        params.setdefault("enabled", False)
        params["creatify_catalog"] = catalog
        row.name = model_name
        row.category = category
        row.params = params
        row.description = catalog["description"] or row.description
        updated += 1

    await db.flush()
    return CreatifyCatalogSyncResult(discovered=len(items), created=created, updated=updated, skipped=skipped)
