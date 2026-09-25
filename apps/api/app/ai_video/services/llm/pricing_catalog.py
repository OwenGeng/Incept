"""Versioned local pricing catalog for the user-approved model list.

Amounts are stored as strings so the catalog can be copied into JSON columns
without losing decimal precision.  This catalog is an estimate source, never a
substitute for provider-reported billing data.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any


CATALOG_SCHEMA_VERSION = 2
CATALOG_VERIFIED_ON = "2026-09-25"

GOOGLE_PRICING_URL = "https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing"
OPENAI_PRICING_URL = "https://developers.openai.com/api/docs/pricing"


def _catalog(
    *,
    provider: str,
    model_name: str,
    source_url: str,
    rules: list[dict[str, Any]],
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "currency": "USD",
        "provider": provider,
        "model_name": model_name,
        "billing_mode": "standard",
        "source_url": source_url,
        "verified_on": CATALOG_VERIFIED_ON,
        "rules": rules,
        "notes": notes or [],
    }


MODEL_PRICING_CATALOGS: dict[str, dict[str, Any]] = {
    "openai-gpt-5-6-terra": _catalog(
        provider="openai",
        model_name="gpt-5.6-terra",
        source_url=OPENAI_PRICING_URL,
        rules=[
            {"metric": "input_token", "unit": "million_tokens", "amount": "2.00", "selectors": {"context": "short"}},
            {"metric": "cached_input_token", "unit": "million_tokens", "amount": "0.20", "selectors": {"context": "short"}},
            {"metric": "cache_write_token", "unit": "million_tokens", "amount": "2.50", "selectors": {"context": "short"}},
            {"metric": "output_token", "unit": "million_tokens", "amount": "12.00", "selectors": {"context": "short"}},
            {"metric": "input_token", "unit": "million_tokens", "amount": "4.00", "selectors": {"context": "over_272k"}},
            {"metric": "cached_input_token", "unit": "million_tokens", "amount": "0.40", "selectors": {"context": "over_272k"}},
            {"metric": "cache_write_token", "unit": "million_tokens", "amount": "5.00", "selectors": {"context": "over_272k"}},
            {"metric": "output_token", "unit": "million_tokens", "amount": "18.00", "selectors": {"context": "over_272k"}},
        ],
    ),
    "openai-gpt-5-6-sol": _catalog(
        provider="openai",
        model_name="gpt-5.6-sol",
        source_url=OPENAI_PRICING_URL,
        rules=[
            {"metric": "input_token", "unit": "million_tokens", "amount": "4.00", "selectors": {"context": "short"}},
            {"metric": "cached_input_token", "unit": "million_tokens", "amount": "0.40", "selectors": {"context": "short"}},
            {"metric": "cache_write_token", "unit": "million_tokens", "amount": "5.00", "selectors": {"context": "short"}},
            {"metric": "output_token", "unit": "million_tokens", "amount": "20.00", "selectors": {"context": "short"}},
            {"metric": "input_token", "unit": "million_tokens", "amount": "8.00", "selectors": {"context": "over_272k"}},
            {"metric": "cached_input_token", "unit": "million_tokens", "amount": "0.80", "selectors": {"context": "over_272k"}},
            {"metric": "cache_write_token", "unit": "million_tokens", "amount": "10.00", "selectors": {"context": "over_272k"}},
            {"metric": "output_token", "unit": "million_tokens", "amount": "30.00", "selectors": {"context": "over_272k"}},
        ],
        notes=["Published promotional pricing is time-limited; re-verify before 2026-11-21."],
    ),
    "openai-gpt-image-2-5-sunburst": _catalog(
        provider="openai",
        model_name="gpt-image-2.5-sunburst",
        source_url=OPENAI_PRICING_URL,
        rules=[
            {"metric": "text_input_token", "unit": "million_tokens", "amount": "5.00"},
            {"metric": "cached_text_input_token", "unit": "million_tokens", "amount": "1.25"},
            {"metric": "image_input_token", "unit": "million_tokens", "amount": "8.00"},
            {"metric": "cached_image_input_token", "unit": "million_tokens", "amount": "2.00"},
            {"metric": "image_output_token", "unit": "million_tokens", "amount": "30.00"},
        ],
    ),
    "openai-gpt-image-2-5-flare": _catalog(
        provider="openai",
        model_name="gpt-image-2.5-flare",
        source_url=OPENAI_PRICING_URL,
        rules=[
            {"metric": "text_input_token", "unit": "million_tokens", "amount": "5.00"},
            {"metric": "cached_text_input_token", "unit": "million_tokens", "amount": "1.25"},
            {"metric": "image_input_token", "unit": "million_tokens", "amount": "8.00"},
            {"metric": "cached_image_input_token", "unit": "million_tokens", "amount": "2.00"},
            {"metric": "image_output_token", "unit": "million_tokens", "amount": "30.00"},
        ],
    ),
    "openai-gpt-4o-mini-tts": _catalog(
        provider="openai",
        model_name="gpt-4o-mini-tts",
        source_url=OPENAI_PRICING_URL,
        rules=[
            {"metric": "text_input_token", "unit": "million_tokens", "amount": "0.60"},
            {"metric": "audio_output_token", "unit": "million_tokens", "amount": "12.00"},
        ],
    ),
    "vertex-gemini-3-1-flash-image": _catalog(
        provider="vertex",
        model_name="gemini-3.1-flash-image",
        source_url=GOOGLE_PRICING_URL,
        rules=[
            {"metric": "input_token", "unit": "million_tokens", "amount": "0.50"},
            {"metric": "cached_input_token", "unit": "million_tokens", "amount": "0.05"},
            {"metric": "text_output_token", "unit": "million_tokens", "amount": "3.00"},
            {"metric": "image_output_token", "unit": "million_tokens", "amount": "60.00"},
            {"metric": "image_output", "unit": "image", "amount": "0.045", "selectors": {"resolution": "512"}, "derived_from": {"tokens_per_image": 747}},
            {"metric": "image_output", "unit": "image", "amount": "0.067", "selectors": {"resolution": "1k"}, "derived_from": {"tokens_per_image": 1120}},
            {"metric": "image_output", "unit": "image", "amount": "0.101", "selectors": {"resolution": "2k"}, "derived_from": {"tokens_per_image": 1680}},
            {"metric": "image_output", "unit": "image", "amount": "0.15", "selectors": {"resolution": "4k"}, "derived_from": {"tokens_per_image": 2520}},
        ],
    ),
    "vertex-gemini-3-8-flash": _catalog(
        provider="vertex",
        model_name="gemini-3.8-flash",
        source_url=GOOGLE_PRICING_URL,
        rules=[
            {"metric": "input_token", "unit": "million_tokens", "amount": "0.75", "effective_until": "2026-12-31"},
            {"metric": "cached_input_token", "unit": "million_tokens", "amount": "0.075", "effective_until": "2026-12-31"},
            {"metric": "output_token", "unit": "million_tokens", "amount": "3.75", "effective_until": "2026-12-31"},
            {"metric": "input_token", "unit": "million_tokens", "amount": "1.50", "effective_from": "2027-01-01"},
            {"metric": "cached_input_token", "unit": "million_tokens", "amount": "0.15", "effective_from": "2027-01-01"},
            {"metric": "output_token", "unit": "million_tokens", "amount": "7.50", "effective_from": "2027-01-01"},
        ],
    ),
    "vertex-veo-3-1-fast": _catalog(
        provider="vertex",
        model_name="veo-3.1-fast-generate-001",
        source_url=GOOGLE_PRICING_URL,
        rules=[
            {"metric": "video_output", "unit": "second", "amount": "0.08", "selectors": {"resolution": "720p", "audio": False}},
            {"metric": "video_output", "unit": "second", "amount": "0.10", "selectors": {"resolution": "1080p", "audio": False}},
            {"metric": "video_output", "unit": "second", "amount": "0.25", "selectors": {"resolution": "4k", "audio": False}},
            {"metric": "video_output", "unit": "second", "amount": "0.10", "selectors": {"resolution": "720p", "audio": True}},
            {"metric": "video_output", "unit": "second", "amount": "0.12", "selectors": {"resolution": "1080p", "audio": True}},
            {"metric": "video_output", "unit": "second", "amount": "0.30", "selectors": {"resolution": "4k", "audio": True}},
        ],
    ),
    "vertex-lyria-3-clip": _catalog(
        provider="vertex",
        model_name="lyria-3-clip-preview",
        source_url=GOOGLE_PRICING_URL,
        rules=[{"metric": "music_output", "unit": "generation", "amount": "0.04", "selectors": {"maximum_seconds": 30}}],
    ),
    "vertex-lyria-3-pro": _catalog(
        provider="vertex",
        model_name="lyria-3-pro-preview",
        source_url=GOOGLE_PRICING_URL,
        rules=[{"metric": "music_output", "unit": "generation", "amount": "0.08", "selectors": {"maximum_seconds": 184}}],
    ),
    "vertex-gemini-omni-1-1-flash": _catalog(
        provider="vertex",
        model_name="gemini-omni-1.1-flash-preview",
        source_url=GOOGLE_PRICING_URL,
        rules=[
            {"metric": "input_token", "unit": "million_tokens", "amount": "1.50"},
            {"metric": "text_output_token", "unit": "million_tokens", "amount": "9.00"},
            {"metric": "video_output_token", "unit": "million_tokens", "amount": "17.50"},
            {"metric": "video_output", "unit": "second", "amount": "0.0337925", "selectors": {"resolution": "360p"}, "derived_from": {"tokens_per_second": 1931, "token_rate_per_million": "17.50"}},
            {"metric": "video_output", "unit": "second", "amount": "0.10136", "selectors": {"resolution": "720p"}, "derived_from": {"tokens_per_second": 5792, "token_rate_per_million": "17.50"}},
            {"metric": "video_output", "unit": "second", "amount": "0.15204", "selectors": {"resolution": "1080p"}, "derived_from": {"tokens_per_second": 8688, "token_rate_per_million": "17.50"}},
            {"metric": "video_output", "unit": "second", "amount": "0.30408", "selectors": {"resolution": "4k"}, "derived_from": {"tokens_per_second": 17376, "token_rate_per_million": "17.50"}},
        ],
    ),
}


def pricing_catalog_for_model(model_id: str) -> dict[str, Any] | None:
    catalog = MODEL_PRICING_CATALOGS.get(model_id)
    return deepcopy(catalog) if catalog is not None else None


def list_model_pricing_catalogs() -> list[dict[str, Any]]:
    """Return a stable JSON-safe view for the local pricing-table endpoint."""
    return [
        {"model_id": model_id, **deepcopy(catalog)}
        for model_id, catalog in sorted(MODEL_PRICING_CATALOGS.items())
    ]


def merge_builtin_pricing_params(model_id: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Merge our versioned catalog without overwriting user-owned parameters."""
    merged = deepcopy(params or {})
    catalog = pricing_catalog_for_model(model_id)
    if catalog is not None:
        merged["pricing_catalog"] = catalog
    return merged


def _legacy_flat_rate(pricing: Any, *, seconds: int) -> dict[str, Any] | None:
    if not isinstance(pricing, dict):
        return None
    currency = str(pricing.get("currency") or "").strip().upper()
    unit = str(pricing.get("unit") or "").strip().lower()
    raw_amount = pricing.get("amount")
    if not currency or unit != "second" or raw_amount is None:
        return {"complete": False, "reason": "invalid_pricing_contract"}
    try:
        unit_amount = Decimal(str(raw_amount))
    except (InvalidOperation, ValueError):
        return {"complete": False, "reason": "invalid_pricing_amount"}
    if unit_amount < 0:
        return {"complete": False, "reason": "invalid_pricing_amount"}
    quantity = Decimal(seconds)
    return {
        "complete": True,
        "currency": currency,
        "unit": "second",
        "quantity": quantity,
        "unit_amount": unit_amount,
        "amount": quantity * unit_amount,
        "estimate_kind": "legacy_flat_rate",
        "estimate_scope": "configured_output_rate",
        "exclusions": [],
        "pricing_snapshot": {
            "schema_version": 1,
            "source": "models.params.pricing",
            "currency": currency,
            "unit": "second",
            "unit_amount": str(unit_amount),
        },
    }


def estimate_video_price(
    model: Any,
    *,
    seconds: int,
    provider_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimate video output cost from a custom rate or an exact catalog rule."""
    params = model.params if model is not None and isinstance(model.params, dict) else {}
    legacy = _legacy_flat_rate(params.get("pricing"), seconds=seconds)
    if legacy is not None:
        return legacy

    catalog = params.get("pricing_catalog")
    if not isinstance(catalog, dict):
        catalog = MODEL_PRICING_CATALOGS.get(str(getattr(model, "id", "")))
    if not isinstance(catalog, dict):
        return {"complete": False, "reason": "pricing_not_configured"}

    supplied = provider_params or {}
    resolution = str(supplied.get("resolution") or "").strip().lower()
    if not resolution:
        return {
            "complete": False,
            "reason": "resolution_required_for_pricing",
            "estimate_kind": "catalog_output_estimate",
            "pricing_snapshot": {
                "schema_version": catalog.get("schema_version"),
                "source_url": catalog.get("source_url"),
                "verified_on": catalog.get("verified_on"),
                "model_name": catalog.get("model_name"),
            },
        }

    selector: dict[str, Any] = {"resolution": resolution}
    if str(getattr(model, "id", "")) == "vertex-veo-3-1-fast":
        if "audio" not in supplied:
            return {
                "complete": False,
                "reason": "audio_setting_required_for_pricing",
                "estimate_kind": "catalog_output_estimate",
            }
        selector["audio"] = bool(supplied.get("audio"))

    matched = next(
        (
            rule
            for rule in catalog.get("rules", [])
            if rule.get("metric") == "video_output"
            and rule.get("unit") == "second"
            and rule.get("selectors") == selector
        ),
        None,
    )
    if not isinstance(matched, dict):
        return {
            "complete": False,
            "reason": "pricing_rule_not_found",
            "estimate_kind": "catalog_output_estimate",
            "requested_selectors": selector,
        }
    try:
        unit_amount = Decimal(str(matched["amount"]))
    except (InvalidOperation, KeyError, ValueError):
        return {"complete": False, "reason": "invalid_pricing_amount"}
    quantity = Decimal(seconds)
    exclusions = ["input_tokens", "text_output_tokens"] if catalog.get("model_name") == "gemini-omni-1.1-flash-preview" else []
    return {
        "complete": True,
        "currency": str(catalog.get("currency") or "USD"),
        "unit": "second",
        "quantity": quantity,
        "unit_amount": unit_amount,
        "amount": quantity * unit_amount,
        "estimate_kind": "catalog_output_estimate",
        "estimate_scope": "media_output_only" if exclusions else "video_output",
        "exclusions": exclusions,
        "pricing_snapshot": {
            "schema_version": catalog.get("schema_version"),
            "provider": catalog.get("provider"),
            "model_name": catalog.get("model_name"),
            "currency": catalog.get("currency"),
            "billing_mode": catalog.get("billing_mode"),
            "source_url": catalog.get("source_url"),
            "verified_on": catalog.get("verified_on"),
            "matched_rule": deepcopy(matched),
            "estimate_scope": "media_output_only" if exclusions else "video_output",
            "exclusions": exclusions,
        },
    }
