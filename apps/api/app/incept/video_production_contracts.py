"""Typed, cross-stage contracts for Incept's AI-video production pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OutputSpec(BaseModel):
    duration_seconds: int = 30
    aspect_ratio: str = "9:16"
    resolution: str = "720x1280"
    safe_area_top_px: int = 0
    safe_area_bottom_px: int = 0


class ProductionContract(BaseModel):
    version: Literal["v1"] = "v1"
    product_name: str = ""
    product_category: str = ""
    objective: str = ""
    allowed_claims: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    target_market: str = ""
    cultural_context: list[str] = Field(default_factory=list)
    output_language: str = "English"
    platforms: list[str] = Field(default_factory=list)
    output_spec: OutputSpec = Field(default_factory=OutputSpec)


class ReferenceGuidance(BaseModel):
    reference_frame_indexes: list[int] = Field(default_factory=list)
    allowed_use: list[str] = Field(default_factory=lambda: ["role", "energy", "composition", "cultural_context"])
    forbidden_use: list[str] = Field(default_factory=lambda: ["exact_face", "exact_likeness", "exact_costume_copy"])


class CharacterIdentity(BaseModel):
    character_key: str
    role: str = ""
    recurring: bool = True
    cultural_context: list[str] = Field(default_factory=list)
    age_range: str = ""
    presentation: str = ""
    face_and_skin_guidance: str = ""
    hair_and_makeup: str = ""
    wardrobe: str = ""
    body_and_accessories: str = ""
    performance: str = ""
    continuity_lock: list[str] = Field(default_factory=list)
    reference_guidance: ReferenceGuidance = Field(default_factory=ReferenceGuidance)


class CreativeBeat(BaseModel):
    beat_id: str
    start_seconds: float
    end_seconds: float
    purpose: str
    action: str
    required_asset_keys: list[str] = Field(default_factory=list)


class CreativeContract(BaseModel):
    version: Literal["v1"] = "v1"
    concept: str = ""
    core_promise: str = ""
    emotional_arc: str = ""
    format: str = ""
    reference_deconstruction: dict[str, list[str]] = Field(default_factory=dict)
    story_beats: list[CreativeBeat] = Field(default_factory=list)
    characters: list[CharacterIdentity] = Field(default_factory=list)
    continuity_rules: list[str] = Field(default_factory=list)
    originality_guardrails: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class AssetContractItem(BaseModel):
    asset_key: str
    asset_type: Literal["character", "environment", "prop", "ui", "lighting", "transition"]
    name: str
    required: bool = True
    reused_across_scenes: bool = True
    scene_ids: list[str] = Field(default_factory=list)
    source_strategy: Literal["original_prompt", "brand_asset", "reference_frame_guidance"] = "original_prompt"
    identity_source: str = ""
    generation_requirements: list[str] = Field(default_factory=list)
    brand_asset_ids: list[str] = Field(default_factory=list)
    reference_frame_indexes: list[int] = Field(default_factory=list)
    status: Literal["planned", "generated", "approved", "blocked"] = "planned"


class AssetContract(BaseModel):
    version: Literal["v1"] = "v1"
    assets: list[AssetContractItem] = Field(default_factory=list)


def contract_validation_errors(
    creative: CreativeContract,
    assets: AssetContract,
) -> list[str]:
    """Deterministic contract checks before data reaches downstream agents."""
    errors: list[str] = []
    asset_keys = {item.asset_key for item in assets.assets}
    for character in creative.characters:
        if character.recurring and character.character_key not in asset_keys:
            errors.append(f"Missing Character Asset Contract for {character.character_key}.")
        if character.recurring and not character.cultural_context:
            errors.append(f"Missing cultural identity for {character.character_key}.")
    for beat in creative.story_beats:
        unknown = set(beat.required_asset_keys) - asset_keys
        if unknown:
            errors.append(f"{beat.beat_id} references undefined assets: {', '.join(sorted(unknown))}.")
    return errors


def script_asset_validation_errors(script, creative: CreativeContract, assets: AssetContract) -> list[str]:
    """Reject a locked script that drifts from the approved world or assets."""
    errors: list[str] = []
    known = {item.asset_key for item in assets.assets}
    cultural_terms = {term.lower() for character in creative.characters for term in character.cultural_context}
    for scene in script.scenes:
        referenced = [*scene.character_keys, scene.environment_key, *scene.prop_keys, *scene.ui_keys]
        if not any(referenced):
            errors.append(f"{scene.id} has no explicit asset bindings.")
        unknown = {key for key in referenced if key and key not in known}
        if unknown:
            errors.append(f"{scene.id} references undefined assets: {', '.join(sorted(unknown))}.")
        if "korean" in cultural_terms and "european" in scene.setting.lower():
            errors.append(f"{scene.id} conflicts with the Korean cultural setting in Creative Contract.")
    return errors
