from __future__ import annotations

from enum import Enum


class AnchorRole(str, Enum):
    logo = "logo"
    cta = "cta"
    headline_block = "headline_block"
    character_face = "character_face"
    character_head = "character_head"
    hero_subject = "hero_subject"
    product = "product"


HARD_REQUIRED_ANCHOR_ROLES = {
    AnchorRole.logo.value,
    AnchorRole.cta.value,
}


def normalize_anchor_role(value: str) -> str:
    raw = value.strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"headline", "headline_text", "text_block"}:
        return AnchorRole.headline_block.value
    if raw in {"character", "hero", "hero_subject", "subject"}:
        return AnchorRole.hero_subject.value
    if raw in {"character_face", "face"}:
        return AnchorRole.character_face.value
    if raw in {"character_head", "head"}:
        return AnchorRole.character_head.value
    if raw in {"packshot", "product_packshot"}:
        return AnchorRole.product.value
    if raw in {role.value for role in AnchorRole}:
        return raw
    return raw or AnchorRole.hero_subject.value


def classify_size_family(width: int, height: int) -> str:
    ratio = width / max(height, 1)
    if ratio >= 4.0 or height <= 100:
        return "banner"
    if ratio <= 0.8:
        return "portrait"
    if 0.9 <= ratio <= 1.15:
        return "square"
    return "hero"
