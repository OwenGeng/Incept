from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai_video.config import settings
from app.ai_video.core.db import Base
from app.ai_video.models.llm import Model, ModelCategoryKey, Provider
from app.ai_video.services.integrations.creatify_tasks import _prepare_input_params
from app.ai_video.services.llm.creatify_catalog import creatify_model_id, sync_creatify_catalog


class _FakeCatalogAdapter:
    """Test double that makes catalog synchronization deterministic and offline."""

    async def list_schemas(self, **_: object) -> list[dict]:
        return [
            {
                "model_name": "provider/video/text-to-video",
                "media_type": "video",
                "title": "Video model",
                "description": "A test video model",
                "plan_level": "starter",
                "input_params_schema": {
                    "type": "object",
                    "properties": {"prompt": {"type": "string"}, "aspect_ratio": {"type": "string"}},
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
            },
            {"model_name": "missing-schema", "media_type": "video"},
        ]


class _RequestedFamilyCatalogAdapter:
    """One approved family to verify first-sync enablement policy."""

    async def list_schemas(self, **_: object) -> list[dict]:
        return [
            {
                "model_name": "seedance-2.5/text-to-video",
                "media_type": "video",
                "title": "Seedance 2.5",
                "input_params_schema": {"type": "object", "properties": {"prompt": {"type": "string"}}},
            }
        ]


@pytest.mark.asyncio
async def test_creatify_catalog_sync_is_schema_backed_and_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(settings, "creatify_api_id", "test-id")
    monkeypatch.setattr(settings, "creatify_api_key", "test-key")

    async with session_local() as db:
        db.add(Provider(id="creatify", name="Creatify", base_url="https://api.creatify.ai/api"))
        await db.commit()

        first = await sync_creatify_catalog(db, provider_id="creatify", adapter=_FakeCatalogAdapter())
        assert (first.discovered, first.created, first.updated, first.skipped) == (2, 1, 0, 1)
        row = await db.get(Model, creatify_model_id("provider/video/text-to-video"))
        assert row is not None
        assert row.category == ModelCategoryKey.video
        assert row.params["enabled"] is False
        assert row.params["creatify_catalog"]["input_params_schema"]["required"] == ["prompt"]

        second = await sync_creatify_catalog(db, provider_id="creatify", adapter=_FakeCatalogAdapter())
        assert (second.created, second.updated) == (0, 1)
    await engine.dispose()


@pytest.mark.asyncio
async def test_creatify_runtime_params_only_add_fields_advertised_by_schema() -> None:
    schema = {
        "type": "object",
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
        "additionalProperties": False,
    }
    assert await _prepare_input_params(schema=schema, prompt="scene", provider_params={}, ratio="16:9") == {
        "prompt": "scene"
    }

    with pytest.raises(RuntimeError, match="does not accept"):
        await _prepare_input_params(
            schema=schema,
            prompt="scene",
            provider_params={"duration_seconds": 5},
            ratio=None,
        )


@pytest.mark.asyncio
async def test_creatify_requested_family_is_enabled_but_existing_choice_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(settings, "creatify_api_id", "test-id")
    monkeypatch.setattr(settings, "creatify_api_key", "test-key")

    async with session_local() as db:
        db.add(Provider(id="creatify", name="Creatify", base_url="https://api.creatify.ai/api"))
        await db.commit()
        await sync_creatify_catalog(db, provider_id="creatify", adapter=_RequestedFamilyCatalogAdapter())
        row = await db.get(Model, creatify_model_id("seedance-2.5/text-to-video"))
        assert row is not None and row.params["enabled"] is True
        row.params = {**row.params, "enabled": False}
        await db.flush()
        await sync_creatify_catalog(db, provider_id="creatify", adapter=_RequestedFamilyCatalogAdapter())
        assert row.params["enabled"] is False
    await engine.dispose()
