from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai_video.core.db import Base
from app.ai_video.models.llm import Model, ModelCategoryKey, Provider
from app.ai_video.services.llm.builtin_model_catalog import seed_user_approved_models
from app.ai_video.services.llm.pricing_catalog import (
    CATALOG_SCHEMA_VERSION,
    estimate_video_price,
    pricing_catalog_for_model,
)


def test_omni_360p_video_output_estimate_has_auditable_snapshot() -> None:
    model = Model(
        id="vertex-gemini-omni-1-1-flash",
        name="gemini-omni-1.1-flash-preview",
        category=ModelCategoryKey.video,
        provider_id="vertex",
        params={},
    )

    estimate = estimate_video_price(model, seconds=3, provider_params={"resolution": "360p"})

    assert estimate["complete"] is True
    assert estimate["amount"] == Decimal("0.1013775")
    assert estimate["estimate_scope"] == "media_output_only"
    assert estimate["exclusions"] == ["input_tokens", "text_output_tokens"]
    assert estimate["pricing_snapshot"]["schema_version"] == CATALOG_SCHEMA_VERSION
    assert estimate["pricing_snapshot"]["matched_rule"]["derived_from"]["tokens_per_second"] == 1931
    assert estimate["pricing_snapshot"]["source_url"].startswith("https://cloud.google.com/")


def test_catalog_estimate_requires_explicit_resolution() -> None:
    model = Model(
        id="vertex-gemini-omni-1-1-flash",
        name="gemini-omni-1.1-flash-preview",
        category=ModelCategoryKey.video,
        provider_id="vertex",
        params={},
    )

    estimate = estimate_video_price(model, seconds=3, provider_params={})

    assert estimate == {
        "complete": False,
        "reason": "resolution_required_for_pricing",
        "estimate_kind": "catalog_output_estimate",
        "pricing_snapshot": {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "source_url": "https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing",
            "verified_on": "2026-09-25",
            "model_name": "gemini-omni-1.1-flash-preview",
        },
    }


def test_catalog_includes_effective_dated_gemini_flash_rates() -> None:
    catalog = pricing_catalog_for_model("vertex-gemini-3-8-flash")
    assert catalog is not None
    assert any(rule.get("effective_until") == "2026-12-31" for rule in catalog["rules"])
    assert any(rule.get("effective_from") == "2027-01-01" for rule in catalog["rules"])


@pytest.mark.asyncio
async def test_builtin_seed_merges_catalog_without_overwriting_user_params() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_local() as db:
        db.add(Provider(id="vertex", name="Vertex", base_url="https://aiplatform.googleapis.com"))
        db.add(
            Model(
                id="vertex-gemini-omni-1-1-flash",
                name="gemini-omni-1.1-flash-preview",
                category=ModelCategoryKey.video,
                provider_id="vertex",
                params={"user_owned": "preserve-me", "provider_timeout": 120},
            )
        )
        await db.commit()

        await seed_user_approved_models(db)
        await db.commit()

        model = await db.get(Model, "vertex-gemini-omni-1-1-flash")
        assert model is not None
        assert model.params["user_owned"] == "preserve-me"
        assert model.params["provider_timeout"] == 120
        assert model.params["pricing_catalog"]["schema_version"] == CATALOG_SCHEMA_VERSION
    await engine.dispose()
