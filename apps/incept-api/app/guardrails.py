from __future__ import annotations

import io
import re
from typing import Any, Awaitable, Callable

from app.models import Asset, AssetRole

_BANNER_PRIORITY = ["logo", "cta", "headline_block", "character_head", "product"]
_ALL_SIZE_VISIBLE = {"logo", "cta"}
_PRESERVE_TYPE_LABELS = {
    "logo": "brand logo",
    "cta": "CTA button / Play Now",
    "headline_block": "headline text block",
    "character_head": "main character head / face",
    "product": "main product / packshot",
}
_ROLE_TO_ANCHOR = {
    AssetRole.client_logo: "logo",
    AssetRole.client_character: "character_head",
    AssetRole.client_product: "product",
    AssetRole.brand_element: "cta",
}
_AMBIGUOUS_EDIT_TERMS = (
    "clean up",
    "cleanup",
    "simplify",
    "make it better",
    "improve",
    "adjust",
    "polish",
    "refresh",
    "fix this",
)
_EXPLICIT_CHANGE_TERMS = (
    "remove",
    "delete",
    "replace",
    "swap",
    "move",
    "add",
    "place",
    "logo",
    "play now",
    "cta",
    "button",
    "headline",
    "text",
    "background",
    "outpaint",
)


class ClarificationRequired(Exception):
    def __init__(
        self,
        question: str,
        *,
        reason: str | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(question)
        self.question = question
        self.reason = reason or "clarification_required"
        self.manifest = manifest or {}


def clarification_options_for_manifest(
    manifest: dict[str, Any],
    *,
    reason: str | None = None,
) -> list[dict[str, str]]:
    why = reason or str(manifest.get("clarification_reason") or "")
    if why in {
        "ultra_wide_priority_conflict",
        "size_priority_conflict",
        "completeness_validation_failed",
    }:
        return [
            {
                "id": "logo_cta",
                "label": "Logo + CTA",
                "note": "Priority for narrow sizes: keep logo and CTA first. It is acceptable to simplify headline, character, and product if needed.",
            },
            {
                "id": "logo_character",
                "label": "Logo + Character",
                "note": "Priority for narrow sizes: keep logo and the main character visible first. CTA and headline may be simplified if needed.",
            },
            {
                "id": "logo_headline",
                "label": "Logo + Headline",
                "note": "Priority for narrow sizes: keep logo and the main headline visible first. CTA, character, and product may be simplified if needed.",
            },
        ]
    return []


def build_preservation_manifest(
    *,
    task_type: str,
    prompt: str,
    target_sizes: list[str],
    context_assets: list[Asset],
    directive: dict[str, Any] | None = None,
    clarification_note: str | None = None,
) -> dict[str, Any]:
    operation = str((directive or {}).get("operation") or task_type or "generate").strip().lower()
    combined_prompt = " ".join(part for part in [prompt or "", clarification_note or ""] if part)
    prompt_lower = " ".join(combined_prompt.lower().split())
    must_preserve_types = {"logo", "cta"}
    preferred_types = {"headline_block"}
    must_remove_tokens = _extract_remove_tokens(prompt, directive or {})
    must_remove_anchor_types = _to_removed_anchor_types(must_remove_tokens)
    low_confidence_items: list[str] = []

    for asset in context_assets:
        mapped = _ROLE_TO_ANCHOR.get(asset.asset_role)
        if mapped:
            must_preserve_types.add(mapped)

    if any(asset.asset_role == AssetRole.reference_ad for asset in context_assets):
        preferred_types.add("headline_block")

    if task_type in {"edit", "outpaint", "remove_bg", "add_text"}:
        preferred_types.update({"character_head", "product"})

    if "logo" in must_remove_anchor_types:
        must_preserve_types.discard("logo")
    if "cta" in must_remove_anchor_types:
        must_preserve_types.discard("cta")

    if operation == "edit_text":
        low_confidence_items.append("headline_text_change")

    size_specific_priorities = {
        size: _size_priority_for(size)
        for size in target_sizes
    }
    user_priority_provided = any(
        phrase in prompt_lower
        for phrase in ("prioritize", "priority", "keep logo", "preserve logo", "logo first")
    )

    manifest = {
        "task_type": task_type,
        "operation": operation,
        "must_preserve": [_PRESERVE_TYPE_LABELS[item] for item in sorted(must_preserve_types)],
        "must_preserve_types": sorted(must_preserve_types),
        "preferred_preserve_types": sorted(preferred_types - must_preserve_types),
        "must_remove": must_remove_tokens,
        "must_remove_anchor_types": sorted(must_remove_anchor_types),
        "may_change": _default_may_change(task_type, operation),
        "must_remain_visible_in_all_sizes": sorted(_ALL_SIZE_VISIBLE - must_remove_anchor_types),
        "size_specific_priorities": size_specific_priorities,
        "low_confidence_items": low_confidence_items,
        "user_priority_provided": user_priority_provided,
        "clarification_note": clarification_note,
        "needs_user_clarification": False,
        "clarification_reason": None,
        "clarification_question": None,
        "clarification_options": [],
    }

    clarification = _manifest_level_clarification(
        prompt_lower=prompt_lower,
        task_type=task_type,
        context_assets=context_assets,
        manifest=manifest,
    )
    if clarification:
        manifest["needs_user_clarification"] = True
        manifest["clarification_reason"] = clarification["reason"]
        manifest["clarification_question"] = clarification["question"]
        manifest["clarification_options"] = clarification_options_for_manifest(
            manifest,
            reason=clarification["reason"],
        )

    return manifest


def build_anchor_hints_from_manifest(
    manifest: dict[str, Any],
    context_assets: list[Asset] | None = None,
) -> list[str]:
    hints: list[str] = []
    for anchor_type in manifest.get("must_preserve_types", []):
        if anchor_type == "logo":
            hints.append("brand logo")
        elif anchor_type == "cta":
            hints.append("cta button")
        elif anchor_type == "headline_block":
            hints.append("headline text block")
        elif anchor_type == "character_head":
            hints.append("main character face")
        elif anchor_type == "product":
            hints.append("main product packshot")
    for anchor_type in manifest.get("preferred_preserve_types", []):
        if anchor_type == "headline_block" and "headline text block" not in hints:
            hints.append("headline text block")
    if context_assets and any(asset.asset_role == AssetRole.brand_element for asset in context_assets):
        if "cta button" not in hints:
            hints.append("cta button")
    return hints


def ensure_manifest_clarity(manifest: dict[str, Any]) -> None:
    if manifest.get("needs_user_clarification"):
        raise ClarificationRequired(
            manifest.get("clarification_question") or "Please confirm which elements must stay visible.",
            reason=manifest.get("clarification_reason"),
            manifest=manifest,
        )


def clarification_for_size(
    manifest: dict[str, Any],
    *,
    target_size: str,
    source_anchors: list[dict[str, Any]],
) -> str | None:
    if not _is_ultra_wide(target_size):
        return None
    if manifest.get("user_priority_provided"):
        return None
    if not source_anchors:
        return None

    present = _collapse_anchor_types(anchor["type"] for anchor in source_anchors)
    critical = [item for item in _BANNER_PRIORITY if item in present]
    if len(critical) < 4:
        return None

    width, height = _parse_size(target_size)
    return (
        f"{width}x{height} cannot safely keep {', '.join(_humanize_anchor(item) for item in critical[:4])} "
        "together. Please confirm which elements should take priority."
    )


async def validate_output_asset(
    *,
    output_bytes: bytes,
    target_size: str,
    manifest: dict[str, Any],
    source_anchors: list[dict[str, Any]],
    detect_fn: Callable[[bytes, str | None, list[str] | None], Awaitable[list[dict[str, Any]]]],
    api_key: str | None,
    overlay_applied: bool = False,
) -> dict[str, Any]:
    width, height = _read_image_size(output_bytes)
    target_w, target_h = _parse_size(target_size)
    size_ok = bool(width and height and width == target_w and height == target_h)

    hints = build_anchor_hints_from_manifest(manifest)
    detected = await detect_fn(output_bytes, api_key, hints=hints) if api_key else []
    present = _collapse_anchor_types(anchor.get("type", "") for anchor in detected)
    if overlay_applied:
        present.add("logo")

    removed_types = set(manifest.get("must_remove_anchor_types", []))
    source_types = _collapse_anchor_types(anchor.get("type", "") for anchor in source_anchors)
    required_hard = _required_hard_types(manifest, source_types, target_size)
    required_soft = _required_soft_types(manifest, source_types, target_size)

    missing_hard = sorted(anchor_type for anchor_type in required_hard if anchor_type not in present)
    missing_soft = sorted(anchor_type for anchor_type in required_soft if anchor_type not in present)
    unexpected_removed = sorted(anchor_type for anchor_type in removed_types if anchor_type in present)

    reasons: list[str] = []
    status = "pass"
    if not size_ok:
        status = "hard_fail"
        reasons.append("size_mismatch")
    if missing_hard:
        status = "hard_fail"
        reasons.append("missing_required_elements")
    if unexpected_removed:
        status = "hard_fail"
        reasons.append("removed_element_still_present")
    if status == "pass" and missing_soft:
        status = "soft_fail"
        reasons.append("missing_soft_elements")

    return {
        "status": status,
        "target_size": target_size,
        "measured_size": {"width": width, "height": height},
        "required_hard_types": sorted(required_hard),
        "required_soft_types": sorted(required_soft),
        "present_anchor_types": sorted(present),
        "source_anchor_types": sorted(source_types),
        "missing_hard_types": missing_hard,
        "missing_soft_types": missing_soft,
        "unexpected_removed_types": unexpected_removed,
        "reasons": reasons,
    }


def prompt_preserve_elements(manifest: dict[str, Any]) -> list[str]:
    return list(manifest.get("must_preserve", []))


def prompt_remove_elements(manifest: dict[str, Any]) -> list[str]:
    return list(manifest.get("must_remove", []))


def _manifest_level_clarification(
    *,
    prompt_lower: str,
    task_type: str,
    context_assets: list[Asset],
    manifest: dict[str, Any],
) -> dict[str, str] | None:
    logo_count = sum(1 for asset in context_assets if asset.asset_role == AssetRole.client_logo)
    if logo_count > 1:
        return {
            "reason": "multiple_logos_detected",
            "question": "I found more than one logo asset. Which logo must stay in the final creative?",
        }

    if task_type in {"edit", "outpaint", "remove_bg", "add_text"}:
        has_ambiguous_term = any(term in prompt_lower for term in _AMBIGUOUS_EDIT_TERMS)
        has_explicit_term = any(term in prompt_lower for term in _EXPLICIT_CHANGE_TERMS)
        if has_ambiguous_term and not has_explicit_term:
            return {
                "reason": "ambiguous_edit_request",
                "question": "Please tell me which element should change and which elements must stay visible.",
            }

    # Only ask for priority clarification on explicit EDIT tasks where the user
    # is manually changing something. For generate / export / style_match /
    # theme_create operations, apply the default priority (logo + CTA) and
    # proceed — never block generation with a priority question.
    _EDIT_ONLY_TASKS = {"edit", "outpaint", "remove_bg", "add_text"}
    if task_type in _EDIT_ONLY_TASKS:
        sizes = list(manifest.get("size_specific_priorities", {}).keys())
        if any(_is_ultra_wide(size) for size in sizes) and not manifest.get("user_priority_provided"):
            preserve_count = len(set(manifest.get("must_preserve_types", [])))
            if preserve_count >= 4:
                return {
                    "reason": "ultra_wide_priority_conflict",
                    "question": "The narrow banner sizes may not fit every critical element. Should I prioritize logo + CTA, or keep character/product visibility too?",
                }
    return None


def _required_hard_types(
    manifest: dict[str, Any],
    source_types: set[str],
    target_size: str,
) -> set[str]:
    removed = set(manifest.get("must_remove_anchor_types", []))
    required = set(manifest.get("must_preserve_types", [])) - removed
    required &= source_types | _ALL_SIZE_VISIBLE | {"character_head", "product"}
    if "character_head" in source_types or "character_face" in source_types:
        required.add("character_head")
    if _is_ultra_wide(target_size):
        required &= {"logo", "cta", "headline_block", "character_head", "product"}
        if "headline_block" in source_types and "headline_block" not in removed:
            required.add("headline_block")
    return required


def _required_soft_types(
    manifest: dict[str, Any],
    source_types: set[str],
    target_size: str,
) -> set[str]:
    removed = set(manifest.get("must_remove_anchor_types", []))
    soft = set(manifest.get("preferred_preserve_types", [])) - removed
    soft &= source_types | {"headline_block"}
    if _is_ultra_wide(target_size):
        soft &= {"headline_block"}
    return soft


def _extract_remove_tokens(prompt: str, directive: dict[str, Any]) -> list[str]:
    prompt_lower = (prompt or "").lower()
    pieces: list[str] = []
    operation = str(directive.get("operation") or "").lower()
    if operation in {"remove", "replace"}:
        pieces.extend(
            str(value or "")
            for value in (directive.get("target"), directive.get("source"))
            if value
        )
    if any(word in prompt_lower for word in ("remove", "delete", "take out", "去掉", "删掉")):
        pieces.append(prompt_lower)

    removed: list[str] = []
    joined = " ".join(piece.lower() for piece in pieces)
    if any(token in joined for token in ("play now", "playnow")):
        removed.append("play_now")
    if any(token in joined for token in ("cta", "button", "call to action")):
        removed.append("cta")
    if "logo" in joined:
        removed.append("logo")
    if any(token in joined for token in ("headline", "title text", "copy block")):
        removed.append("headline_block")
    return list(dict.fromkeys(removed))


def _to_removed_anchor_types(tokens: list[str]) -> set[str]:
    removed: set[str] = set()
    for token in tokens:
        if token in {"play_now", "cta"}:
            removed.add("cta")
        elif token in {"logo"}:
            removed.add("logo")
        elif token in {"headline_block"}:
            removed.add("headline_block")
    return removed


def _default_may_change(task_type: str, operation: str) -> list[str]:
    if task_type == "outpaint":
        return ["background extension", "edge continuation"]
    if task_type == "remove_bg":
        return ["background"]
    if task_type == "add_text":
        return ["new text overlay"]
    if operation in {"remove", "replace", "edit", "edit_text"}:
        return ["masked area only"]
    return ["background", "decorative elements", "non-critical layout spacing"]


def _size_priority_for(size: str) -> list[str]:
    if _is_ultra_wide(size):
        return list(_BANNER_PRIORITY)
    width, height = _parse_size(size)
    if width and height and width < height:
        return ["logo", "character_head", "product", "cta", "headline_block"]
    if width and height and abs(width - height) < max(40, int(min(width, height) * 0.15)):
        return ["logo", "character_head", "cta", "product", "headline_block"]
    return ["logo", "headline_block", "cta", "character_head", "product"]


def _collapse_anchor_types(anchor_types: Any) -> set[str]:
    collapsed: set[str] = set()
    for item in anchor_types:
        raw = str(item or "").strip().lower()
        if raw in {"character_face", "character_head"}:
            collapsed.add("character_head")
        elif raw:
            collapsed.add(raw)
    return collapsed


def _humanize_anchor(anchor_type: str) -> str:
    return {
        "logo": "logo",
        "cta": "CTA",
        "headline_block": "headline",
        "character_head": "character",
        "product": "product",
    }.get(anchor_type, anchor_type.replace("_", " "))


def _parse_size(size: str) -> tuple[int | None, int | None]:
    try:
        width, height = size.lower().split("x", 1)
        return int(width), int(height)
    except ValueError:
        return None, None


def _is_ultra_wide(size: str) -> bool:
    width, height = _parse_size(size)
    if not width or not height:
        return False
    return height <= 100 or (width / max(1, height)) >= 4


def _read_image_size(image_bytes: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as img:
            return img.size
    except Exception:
        return None, None
