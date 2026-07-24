"""Independent state for the Video Production Workspace.

This intentionally does not create CreativeThread records. A production is a
structured ad-making workspace with its own brief, script revisions, storyboard,
and shot-level delivery history.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import json
import logging
import math
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest

from app.incept.config import get_settings
from app.incept.db import load_video_productions, upsert_asset, upsert_job, upsert_video_production
from app.incept.models import (
    Asset,
    AssetRole,
    GenerationJob,
    JobStatus,
    User,
    VideoProduction,
    VideoProductionAgentRequest,
    VideoProductionAudioCue,
    VideoProductionAudioPlan,
    VideoProductionAssetLink,
    VideoProductionBeat,
    VideoProductionConversationMessage,
    VideoProductionCreativeDirection,
    VideoProductionCreateRequest,
    VideoProductionDesignBible,
    VideoProductionDesignSheet,
    VideoProductionScene,
    VideoProductionScript,
    VideoProductionShot,
    VideoProductionShotOrderRequest,
    VideoProductionShotUpdateRequest,
    VideoProductionStage,
    VideoProductionUpdateRequest,
    VideoGenerationMode,
    VideoGenerationRequest,
)
from app.incept.store import (
    ASSETS,
    JOBS,
    SOURCE_ASSETS,
    _dispatch_generation,
    _export_master_images_to_assets,
    _build_gcs_object_path,
    _guess_content_type,
    _inherit_root_asset_id,
    _load_asset_bytes,
    _mark_generation_progress,
    _record_asset_storage_status,
    _upload_bytes_to_gcs,
)
from app.incept.video_store import (
    _asset_part_for_text_model,
    _call_multimodal_text_model,
    _concat_video_sequence,
    _execute_veo_request,
    _guess_video_dimensions,
    _save_local_video_file,
)

logger = logging.getLogger(__name__)

VIDEO_PRODUCTIONS: dict[str, VideoProduction] = {}


def _bootstrap() -> None:
    for row in load_video_productions():
        try:
            production = VideoProduction.model_validate(json.loads(row["payload_json"]))
            VIDEO_PRODUCTIONS[production.production_id] = production
        except Exception:
            logger.warning("Skipping unreadable video production", exc_info=True)


_bootstrap()


def _asset_by_id(asset_id: str) -> Asset | None:
    return ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)


_ASSET_PACK_TYPES = {"character", "environment", "prop", "ui", "lighting", "transition"}


def _brand_image_asset_ids(production: VideoProduction) -> set[str]:
    """Only current-production brand inputs may condition a reusable Pack.

    Creative-reference media is analyzed upstream. It must never silently become
    a Design Pack source, otherwise historical or competitor material is
    mistaken for a new production asset.
    """
    return {
        link.asset_id
        for link in production.asset_links
        if link.role in {"brand", "character", "product", "logo", "background"}
        and (asset := _asset_by_id(link.asset_id))
        and asset.type in {"image", "gif", "video"}
    }


def _allowed_roles_for_pack(pack_type: str) -> set[str]:
    """Return only the production roles that are safe for a Pack type."""
    return {
        # Older productions commonly stored a character reference as a generic
        # brand asset, so preserve that compatibility for character locking.
        "character": {"character", "brand"},
        "environment": {"background"},
        # Product Packs deliberately exclude generic brand and character media.
        # A prop board must never inherit a person's face, body, or wardrobe.
        "prop": {"product"},
        "ui": {"logo"},
        "lighting": set(),
        "transition": set(),
    }.get(pack_type, set())


def _filter_pack_asset_ids(
    production: VideoProduction,
    pack_type: str,
    asset_ids: list[str],
) -> list[str]:
    """Keep only asset IDs that may condition the requested visual Pack."""
    allowed_roles = _allowed_roles_for_pack(pack_type)
    if not allowed_roles:
        return []
    allowed_ids = {
        link.asset_id
        for link in production.asset_links
        if link.role in allowed_roles
    }
    current_brand_ids = _brand_image_asset_ids(production)
    return list(dict.fromkeys(
        asset_id
        for asset_id in asset_ids
        if asset_id in allowed_ids and asset_id in current_brand_ids
    ))


def _sheet_identity_key(sheet: VideoProductionDesignSheet) -> str:
    """Create a conservative semantic key for duplicate Pack suppression."""
    title = re.sub(r"\b(character|environment|prop|product|ui|lighting|color|transition|pair|pack|card)\b", "", sheet.title.lower())
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff\uac00-\ud7af]+", " ", title).strip()
    scenes = ",".join(sorted(sheet.scene_ids))
    return f"{sheet.asset_pack_type}:{scenes or title or 'global'}"


def _pack_limit(production: VideoProduction) -> int:
    """Keep the reusable pre-production inventory proportional to the script."""
    scene_count = max(len(production.script.scenes), len(production.script.beats), 1)
    return min(10, max(4, math.ceil(production.target_seconds / 5) + 2, scene_count))


def _normalize_asset_packs(
    production: VideoProduction,
    packs: list[VideoProductionDesignSheet],
) -> list[VideoProductionDesignSheet]:
    """Keep only genuinely reusable, script-bound Design Packs.

    This is deliberately defensive because Design data is persisted and older
    prompts used to create one default Pack for every type. The function removes
    reference/history leakage, merges duplicate semantic states, allows one
    global lighting card, and limits transition pairs to actual scene handoffs.
    """
    valid_scene_ids = {scene.id for scene in production.script.scenes}
    transition_limit = max(0, min(2, len(valid_scene_ids) - 1))
    kept: list[VideoProductionDesignSheet] = []
    seen: set[str] = set()
    type_counts: dict[str, int] = {pack_type: 0 for pack_type in _ASSET_PACK_TYPES}

    for pack in packs:
        inferred_type = _infer_asset_pack_type(pack)
        if pack.asset_pack_type == "environment" or pack.asset_pack_type not in _ASSET_PACK_TYPES:
            pack.asset_pack_type = inferred_type  # type: ignore[assignment]
        pack.kind = "character_consistency" if pack.asset_pack_type == "character" else "scene_style"
        pack.asset_ids = _filter_pack_asset_ids(production, pack.asset_pack_type, pack.asset_ids)
        pack.scene_ids = list(dict.fromkeys(scene_id for scene_id in pack.scene_ids if scene_id in valid_scene_ids))

        # Lighting is a rule in the bible, not a recurring image Pack. Keep one
        # only when the agent supplied an explicit visual instruction.
        if pack.asset_pack_type == "lighting" and not pack.prompt.strip():
            continue
        # A transition needs two adjacent scenes; otherwise the global
        # transition rules are sufficient and no extra Pack should exist.
        if pack.asset_pack_type == "transition" and transition_limit == 0:
            continue

        key = _sheet_identity_key(pack)
        if key in seen:
            continue
        if pack.asset_pack_type == "lighting" and type_counts["lighting"] >= 1:
            continue
        if pack.asset_pack_type == "transition" and type_counts["transition"] >= transition_limit:
            continue
        if len(kept) >= _pack_limit(production):
            continue

        seen.add(key)
        type_counts[pack.asset_pack_type] += 1
        kept.append(pack)
    return kept


def _infer_asset_pack_type(sheet: VideoProductionDesignSheet) -> str:
    """Repair older generic Environment packs from their production intent."""
    text = " ".join([sheet.title, sheet.purpose, sheet.prompt]).lower()
    if any(token in text for token in ("transition", "match-cut", "match cut", "转场", "衔接", "切换")):
        return "transition"
    if any(token in text for token in ("lighting", "color card", "color grade", "光影", "色温", "色彩", "调色")):
        return "lighting"
    if any(token in text for token in (" ui", "ui ", "cta", "end-card", "end card", "logo", "界面", "片尾", "落盘", "按钮")):
        return "ui"
    if any(token in text for token in ("character", "performer", "mascot", "girl", "woman", "duo", "角色", "人物", "闺蜜", "女生", "女主", "看板娘")):
        return "character"
    if any(token in text for token in ("prop", "product", "hero product", "道具", "产品", "花束", "手机屏幕")):
        return "prop"
    return "environment"


def _split_duo_character_pack(sheet: VideoProductionDesignSheet) -> list[VideoProductionDesignSheet]:
    """Turn a vague two-person sheet into reusable A/B identity packs."""
    text = " ".join([sheet.title, sheet.purpose, sheet.prompt]).lower()
    duo_markers = ("duo", "two women", "two girls", "friend", "闺蜜", "两位", "女生a", "女生b")
    if not any(marker in text for marker in duo_markers):
        return [sheet]
    if "character a" in text or "角色a" in text:
        return [sheet]
    base_title = sheet.title.replace("一致性画板", "").strip(" -") or "Character"
    primary = sheet.model_copy(deep=True)
    primary.title = f"{base_title} - Character A"
    primary.purpose = f"Lock Character A only: face, hair, makeup, wardrobe, body proportions, accessories, and hero-product handling. {sheet.purpose}"
    primary.prompt = f"Character A only. Do not show Character B. {sheet.prompt}"
    primary.crop_plan = []
    primary.grid_asset_id = None
    primary.panel_asset_ids = []
    primary.approved_panel_asset_ids = {}
    primary.approved_asset_ids = []
    primary.selected_asset_id = None
    primary.selected_panel = None
    primary.status = "draft"

    secondary = primary.model_copy(deep=True)
    secondary.id = f"design_{uuid4().hex[:8]}"
    secondary.title = f"{base_title} - Character B"
    secondary.purpose = f"Lock Character B only: face, hair, makeup, wardrobe, body proportions, accessories, and reaction performance. {sheet.purpose}"
    secondary.prompt = f"Character B only. Do not show Character A. {sheet.prompt}"
    return [primary, secondary]


def _hydrate_asset_pack_inventory(production: VideoProduction) -> None:
    """Normalize legacy Design data into the canonical reusable Asset Pack inventory."""
    bible = production.design_bible
    packs = bible.asset_packs or [*bible.character_consistency_sheets, *bible.scene_style_sheets]
    if not packs:
        return

    normalized: list[VideoProductionDesignSheet] = []
    for pack in packs:
        inferred_type = _infer_asset_pack_type(pack)
        # Earlier versions defaulted missing types to environment. Prefer intent
        # when the title/purpose clearly describes a character, UI, or transition.
        if pack.asset_pack_type == "environment" or pack.asset_pack_type not in _ASSET_PACK_TYPES:
            pack.asset_pack_type = inferred_type  # type: ignore[assignment]
        pack.kind = "character_consistency" if pack.asset_pack_type == "character" else "scene_style"
        normalized.extend(_split_duo_character_pack(pack) if pack.asset_pack_type == "character" else [pack])

    normalized = _normalize_asset_packs(production, normalized)
    bible.asset_packs = normalized
    bible.character_consistency_sheets = [pack for pack in normalized if pack.asset_pack_type == "character"]
    bible.scene_style_sheets = [pack for pack in normalized if pack.asset_pack_type != "character"]


def _normalize_production(production: VideoProduction) -> VideoProduction:
    production.asset_links = [VideoProductionAssetLink.model_validate(link) for link in production.asset_links]
    production.creative_direction = VideoProductionCreativeDirection.model_validate(production.creative_direction)
    production.script = VideoProductionScript.model_validate(production.script)
    production.design_bible = VideoProductionDesignBible.model_validate(production.design_bible)
    _hydrate_asset_pack_inventory(production)
    production.shots = [VideoProductionShot.model_validate(shot) for shot in production.shots]
    production.audio_plan = VideoProductionAudioPlan.model_validate(production.audio_plan)
    production.conversation = [
        VideoProductionConversationMessage.model_validate(message) for message in production.conversation
    ]
    return production


def _save(production: VideoProduction) -> VideoProduction:
    production = _normalize_production(production)
    production.updated_at = datetime.utcnow()
    VIDEO_PRODUCTIONS[production.production_id] = production
    upsert_video_production(production)
    return production


def _assert_owner(production: VideoProduction, user: User) -> None:
    if production.created_by != user.id and user.role.value not in {"manager", "admin"}:
        raise PermissionError("This video production is not available to the current user.")


def list_video_productions(workspace_id: str, user: User) -> list[VideoProduction]:
    values = [production for production in VIDEO_PRODUCTIONS.values() if production.workspace_id == workspace_id]
    if user.role.value not in {"manager", "admin"}:
        values = [production for production in values if production.created_by == user.id]
    return sorted(values, key=lambda item: item.updated_at, reverse=True)


def get_video_production(production_id: str, user: User) -> VideoProduction | None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    if production:
        production = _normalize_production(production)
        VIDEO_PRODUCTIONS[production.production_id] = production
        _assert_owner(production, user)
    return production


def create_video_production(request: VideoProductionCreateRequest, user: User) -> VideoProduction:
    production = VideoProduction(
        production_id=f"vprod_{uuid4().hex[:12]}",
        workspace_id=request.workspace_id,
        created_by=user.id,
        title=request.title.strip() or "Untitled video",
        target_seconds=request.target_seconds,
        aspect_ratio=request.aspect_ratio,
        resolution=request.resolution,
    )
    production.conversation.append(
        VideoProductionConversationMessage(
            role="assistant",
            text="Upload a creative reference or describe the commercial goal. The Creative Strategist will first identify the transferable structure and the brand assets required for an original production.",
        )
    )
    return _save(production)


def update_video_production(
    production_id: str,
    request: VideoProductionUpdateRequest,
    user: User,
) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    values = request.model_dump(exclude_unset=True)
    for field, value in values.items():
        if field == "asset_links" and value is not None:
            value = [VideoProductionAssetLink.model_validate(link) for link in value]
        elif field == "creative_direction" and value is not None:
            value = VideoProductionCreativeDirection.model_validate(value)
        elif field == "script" and value is not None:
            value = VideoProductionScript.model_validate(value)
        elif field == "design_bible" and value is not None:
            value = VideoProductionDesignBible.model_validate(value)
        elif field == "audio_plan" and value is not None:
            value = VideoProductionAudioPlan.model_validate(value)
        setattr(production, field, value)
    return _save(production)


def _safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _parse_json(text: str) -> dict[str, object]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _fallback_script(production: VideoProduction, instruction: str) -> VideoProductionScript:
    target = production.target_seconds
    beat_count = 4 if target == 15 else 8 if target == 30 else 15
    beat_duration = target / beat_count
    beats = [
        VideoProductionBeat(
            start_seconds=round(index * beat_duration, 1),
            end_seconds=round((index + 1) * beat_duration, 1),
            title=("Hook" if index == 0 else "Brand close" if index == beat_count - 1 else f"Product proof {index}"),
            purpose=("Establish the audience hook immediately." if index == 0 else "Land a clean, branded CTA-ready close." if index == beat_count - 1 else "Advance a specific product benefit or gameplay action."),
        )
        for index in range(beat_count)
    ]
    asset_names = [(_asset_by_id(asset_id).title if _asset_by_id(asset_id) else asset_id) for asset_id in production.reference_asset_ids]
    return VideoProductionScript(
        revision=production.script.revision + 1,
        creative_goal=instruction or production.brief or "Create a clear, conversion-focused commercial video.",
        audience="Define the primary audience before locking the script.",
        logline="A focused commercial story that moves from a clear hook to product proof and a clean branded close.",
        style_bible=["Keep the supplied brand assets visually consistent.", "Use deliberate, readable camera language.", "Prioritize one idea per shot."],
        beats=beats,
        scenes=[
            VideoProductionScene(id=f"scene_{index + 1}", title=beat.title, setting="Defined from reference assets", action=beat.purpose)
            for index, beat in enumerate(beats)
        ],
        brand_rules=["Preserve supplied logos, product details, and approved brand colors."],
        asset_manifest=[f"Reference asset: {name}" for name in asset_names] or ["Upload product, logo, character, and background assets as applicable."],
        risks=["Confirm all final copy, licensing, and CTA requirements before delivery."],
        raw_script=instruction or production.brief,
    )


def _normalize_script_beats(production: VideoProduction, beats: list[VideoProductionBeat]) -> list[VideoProductionBeat]:
    normalized: list[VideoProductionBeat] = []
    for beat in sorted(beats, key=lambda item: item.start_seconds):
        start = max(0.0, beat.start_seconds)
        end = min(float(production.target_seconds), beat.end_seconds)
        duration = end - start
        if duration <= 0:
            continue
        if duration <= 5:
            normalized.append(VideoProductionBeat(
                start_seconds=round(start, 1),
                end_seconds=round(end, 1),
                title=beat.title,
                purpose=beat.purpose,
            ))
            continue

        pieces = max(2, math.ceil(duration / 5))
        piece_duration = duration / pieces
        for piece_index in range(pieces):
            piece_start = start + piece_duration * piece_index
            piece_end = end if piece_index == pieces - 1 else start + piece_duration * (piece_index + 1)
            normalized.append(VideoProductionBeat(
                start_seconds=round(piece_start, 1),
                end_seconds=round(piece_end, 1),
                title=f"{beat.title} {piece_index + 1}" if pieces > 1 else beat.title,
                purpose=beat.purpose,
            ))
    return normalized or _fallback_script(production, production.brief).beats


def _script_from_payload(production: VideoProduction, payload: dict[str, object], instruction: str) -> VideoProductionScript:
    fallback = _fallback_script(production, instruction)
    raw_beats = payload.get("beats") if isinstance(payload.get("beats"), list) else []
    beats: list[VideoProductionBeat] = []
    for index, item in enumerate(raw_beats):
        if not isinstance(item, dict):
            continue
        try:
            beats.append(VideoProductionBeat(
                start_seconds=float(item.get("start_seconds", index * (production.target_seconds / max(len(raw_beats), 1)))),
                end_seconds=float(item.get("end_seconds", (index + 1) * (production.target_seconds / max(len(raw_beats), 1)))),
                title=str(item.get("title") or f"Beat {index + 1}"),
                purpose=str(item.get("purpose") or "Advance the commercial story."),
            ))
        except (TypeError, ValueError):
            continue
    raw_scenes = payload.get("scenes") if isinstance(payload.get("scenes"), list) else []
    scenes: list[VideoProductionScene] = []
    for index, item in enumerate(raw_scenes):
        if not isinstance(item, dict):
            continue
        scenes.append(VideoProductionScene(
            id=str(item.get("id") or f"scene_{index + 1}"),
            title=str(item.get("title") or f"Scene {index + 1}"),
            setting=str(item.get("setting") or ""),
            action=str(item.get("action") or ""),
            dialogue_or_copy=str(item.get("dialogue_or_copy") or ""),
        ))
    list_value = lambda key, fallback_value: _string_list(payload, key, fallback_value)
    return VideoProductionScript(
        revision=production.script.revision + 1,
        status="draft",
        creative_goal=str(payload.get("creative_goal") or fallback.creative_goal),
        audience=str(payload.get("audience") or fallback.audience),
        logline=str(payload.get("logline") or fallback.logline),
        style_bible=list_value("style_bible", fallback.style_bible),
        beats=_normalize_script_beats(production, beats or fallback.beats),
        scenes=scenes or fallback.scenes,
        brand_rules=list_value("brand_rules", fallback.brand_rules),
        asset_manifest=list_value("asset_manifest", fallback.asset_manifest),
        risks=list_value("risks", fallback.risks),
        raw_script=str(payload.get("raw_script") or instruction or production.brief),
    )


def _asset_parts(production: VideoProduction, roles: set[str] | None = None) -> list[object]:
    parts: list[object] = []
    seen: set[str] = set()
    links = [VideoProductionAssetLink.model_validate(link) for link in production.asset_links]
    if roles is None:
        asset_ids = [*production.reference_asset_ids, *[link.asset_id for link in links]]
    elif "reference" in roles:
        # New productions have explicit links. Prefer those so legacy brand
        # assets accidentally stored in reference_asset_ids are not reanalyzed.
        asset_ids = (
            [link.asset_id for link in links if link.role in roles]
            if links
            else list(production.reference_asset_ids)
        )
    else:
        asset_ids = [link.asset_id for link in links if link.role in roles]
    for asset_id in asset_ids:
        if asset_id in seen:
            continue
        seen.add(asset_id)
        asset = _asset_by_id(asset_id)
        if not asset:
            continue
        try:
            parts.append(_asset_part_for_text_model(asset))
        except Exception:
            logger.info("Skipping unavailable production asset %s during planning", asset_id)
    return parts


def _role_payload(
    production: VideoProduction,
    *,
    role_prompt: str,
    instruction: str,
    roles: set[str] | None = None,
    include_asset_parts: bool = True,
) -> dict[str, object]:
    """Run one named production role with only the assets relevant to that role."""
    asset_links = [VideoProductionAssetLink.model_validate(link) for link in production.asset_links]
    relevant_links = [
        {
            **link.model_dump(mode="json"),
            "asset_title": asset.title if (asset := _asset_by_id(link.asset_id)) else link.asset_id,
            "asset_type": asset.type if asset else "unknown",
            "asset_dimensions": f"{asset.width}x{asset.height}" if asset and asset.width and asset.height else None,
        }
        for link in asset_links
        if roles is None or link.role in roles
    ]
    try:
        return _parse_json(_call_multimodal_text_model(
            prompt=(
                f"{role_prompt}\n"
                "Return JSON only. Do not use markdown fences. Do not invent assets, approvals, or brand claims. "
                "Use native JSON types: arrays must be real JSON arrays, never stringified JSON or Python list literals. "
                "Fields that request a summary or title must be one plain string, never an array. "
                f"Output language: {_response_language_hint(production, instruction)}. Write every user-facing value in that language. Keep only JSON keys in English, and do not translate filenames or supplied brand copy. "
                f"Production format: {production.target_seconds}s, {production.aspect_ratio}, {production.resolution}. "
                f"Creative brief: {production.brief or 'Not written yet.'} "
                f"User instruction: {instruction or 'Create the first pass.'} "
                f"Creative direction: {_safe_json(production.creative_direction.model_dump(mode='json'))}. "
                f"Current script: {_safe_json(production.script.model_dump(mode='json'))}. "
                f"Design bible: {_safe_json(production.design_bible.model_dump(mode='json'))}. "
                f"Relevant asset links: {_safe_json(relevant_links)}. "
                f"Recent production conversation: {_safe_json([message.model_dump(mode='json') for message in production.conversation[-12:]])}."
            ),
            # Media is expensive to process, especially reference video. Most follow-up
            # messages only need the saved structured analysis and conversation history.
            parts=_asset_parts(production, roles) if include_asset_parts else [],
            model_id=get_settings().vertex_video_analysis_model,
        ))
    except Exception:
        logger.warning("Video Production role unavailable; using a local fallback", exc_info=True)
        return {}


def _expand_list_value(value: object) -> list[object]:
    """Normalize model list fields, including stringified JSON/Python arrays."""
    if value is None:
        return []
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("[") and candidate.endswith("]"):
            parsed: object = candidate
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(candidate)
                except (SyntaxError, ValueError):
                    pass
            if isinstance(parsed, list):
                return [nested for item in parsed for nested in _expand_list_value(item)]
        return [value]
    if isinstance(value, list):
        return [nested for item in value for nested in _expand_list_value(item)]
    return [value]


def _string_list(payload: dict[str, object], key: str, fallback: list[str] | None = None) -> list[str]:
    items = [_format_list_item(item) for item in _expand_list_value(payload.get(key))]
    return [item for item in items if item] or fallback or []


def _string_value(
    payload: dict[str, object],
    key: str,
    fallback: str,
    *,
    separator: str = " ",
) -> str:
    values = _string_list(payload, key)
    return separator.join(values) if values else fallback


def _production_rule_list(payload: dict[str, object], key: str, fallback: list[str]) -> list[str]:
    """Reject placeholder model text so every production rule is actionable."""
    placeholders = {
        "not defined yet",
        "not defined",
        "n/a",
        "none",
        "unknown",
        "未定义",
        "暂无",
        "无",
    }
    items = [
        item
        for item in _string_list(payload, key)
        if item.strip().lower().strip(".。") not in placeholders
    ]
    return items or fallback


def _format_list_item(value: object) -> str:
    """Convert structured model list items into concise, human-readable report rows."""
    if not isinstance(value, dict):
        return str(value).strip()
    title = str(
        value.get("item")
        or value.get("title")
        or value.get("name")
        or value.get("beat")
        or value.get("rule")
        or ""
    ).strip()
    purpose = next((
        str(value.get(key)).strip()
        for key in ("purpose", "action", "description", "rationale")
        if value.get(key)
    ), "")
    specifications = []
    if value.get("priority"):
        specifications.append(f"Priority: {str(value['priority']).strip()}")
    if value.get("recommended_aspect_ratio_or_pixel_dimensions"):
        specifications.append(str(value["recommended_aspect_ratio_or_pixel_dimensions"]).strip())
    if value.get("file_format"):
        specifications.append(str(value["file_format"]).strip())
    if value.get("transparency_required") is True:
        specifications.append("transparent background")
    prefix = str(value.get("timecode") or "").strip()
    details = " · ".join(part for part in [purpose, *specifications] if part)
    main = " — ".join([part for part in [title, details] if part])
    if main:
        return f"{prefix}: {main}" if prefix else main
    return "; ".join(str(item).strip() for item in value.values() if str(item).strip())


def _response_language_hint(production: VideoProduction, instruction: str) -> str:
    """Keep agent-facing content in the language used most recently by the user."""
    candidates = [instruction]
    candidates.extend(message.text for message in reversed(production.conversation) if message.role == "user")
    candidates.append(production.brief)
    sample = next((text for text in candidates if text and text.strip()), "")
    if re.search(r"[\u4e00-\u9fff]", sample):
        return "Simplified Chinese"
    if re.search(r"[\uac00-\ud7af]", sample):
        return "Korean"
    if re.search(r"[\u3040-\u30ff]", sample):
        return "Japanese"
    return "the same language as the user's latest message (English when unclear)"


def _creative_direction_fallbacks(production: VideoProduction, instruction: str) -> dict[str, list[str]]:
    """Keep the direction report actionable when a model omits an optional section."""
    is_chinese = _response_language_hint(production, instruction) == "Simplified Chinese"
    if is_chinese:
        return {
            "strengths": ["前 2 秒建立清晰的产品或利益点钩子", "用可见的使用结果建立可信度", "以清晰的品牌 CTA 收束"],
            "story": ["00:00–00:03：用产品、人物或关键利益点建立钩子", "00:03–00:10：展示机制、证明或核心体验", "00:10–00:15：强化价值主张并进入品牌 CTA"],
            "guardrails": ["仅借鉴参考素材的节奏、结构和镜头语言，不复制人物、品牌、文案或镜头画面", "使用品牌方授权的素材与原创角色、配色及 CTA 设计"],
        }
    return {
        "strengths": ["Establish a clear product or benefit hook in the first two seconds", "Use visible proof of the experience or outcome", "Close with a clear branded CTA"],
        "story": ["00:00–00:03: Establish the product, character, or benefit hook", "00:03–00:10: Demonstrate the mechanism, proof, or core experience", "00:10–00:15: Reinforce the value proposition and land on the branded CTA"],
        "guardrails": ["Learn only pacing, structure, and camera language from the reference; do not copy its people, brand, copy, or footage", "Use authorized brand assets and original characters, colors, and CTA design"],
    }


def _reference_frame_plan(payload: dict[str, object]) -> list[dict[str, object]]:
    """Keep only safe, actionable timestamps produced by the reference analysis."""
    raw_plan = payload.get("reference_frame_plan")
    if not isinstance(raw_plan, list):
        return []
    plan: list[dict[str, object]] = []
    for item in raw_plan[:3]:
        if not isinstance(item, dict):
            continue
        try:
            timestamp = max(0.0, float(item.get("timestamp_seconds", 0)))
        except (TypeError, ValueError):
            continue
        plan.append({
            "timestamp_seconds": round(timestamp, 2),
            "purpose": str(item.get("purpose") or "Reference visual state").strip(),
            "rationale": str(item.get("rationale") or "Use as a visual reference for design.").strip(),
        })
    return plan


def _creative_direction_asset_ids(production: VideoProduction) -> list[str]:
    """Return only creative-reference inputs that determine direction freshness."""
    asset_ids: list[str] = []
    seen: set[str] = set()
    links = [VideoProductionAssetLink.model_validate(link) for link in production.asset_links]
    source_ids = (
        [link.asset_id for link in links if link.role == "reference"]
        if links
        else production.reference_asset_ids
    )
    for asset_id in source_ids:
        if asset_id and asset_id not in seen:
            seen.add(asset_id)
            asset_ids.append(asset_id)
    return asset_ids


def _creative_direction_needs_asset_analysis(production: VideoProduction) -> bool:
    current_asset_ids = _creative_direction_asset_ids(production)
    analyzed_asset_ids = production.creative_direction.analyzed_asset_ids
    has_reference_video = any(
        (asset := _asset_by_id(asset_id)) is not None and asset.type == "video"
        for asset_id in current_asset_ids
    )
    # Existing productions created before frame extraction was introduced need
    # one lightweight re-analysis so Design has timestamped still references.
    needs_frame_plan = has_reference_video and not production.creative_direction.reference_frame_plan
    return (
        not production.creative_direction.reference_summary
        or set(current_asset_ids) != set(analyzed_asset_ids)
        or needs_frame_plan
    )


def run_creative_director(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    message = request.message.strip()
    needs_asset_analysis = _creative_direction_needs_asset_analysis(production)
    analyzed_asset_ids = _creative_direction_asset_ids(production)
    if message:
        production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
        if not production.brief:
            production.brief = message
    analysis_mode_instruction = (
        "This is a fresh media-analysis pass. Inspect the supplied media and create or refresh the full direction report. "
        if needs_asset_analysis
        else "This is a text-only follow-up. Do not claim to re-inspect uploaded media; use the saved creative direction, supplied asset metadata, and conversation history to answer or revise the direction. "
    )
    payload = _role_payload(
        production,
        roles={"reference"},
        instruction=message,
        role_prompt=(
            "You are the Creative Strategist for an original commercial-video production. Analyze only the CREATIVE REFERENCE media supplied to you. Extract transferable commercial craft such as format, hook, pacing, scene progression, camera language, performance, music mood, CTA strategy, and copywriting structure. Never copy protected characters, logos, text, footage, product identity, or exact compositions. "
            "Do not inspect, identify, or make claims about brand assets at this stage. The Screenwriter will later use the approved direction together with the brand-asset inventory, and the Production Designer will later inspect the actual brand media. "
            "In asset_request, produce a practical asset brief for the future production: list what the Screenwriter and Production Designer will need, including purpose, priority, recommended dimensions, file format, and whether a transparent background is required. Do not mention uploaded asset IDs or claim that an asset is already suitable. "
            "In reference_summary, describe only transferable lessons from the reference and how they can be adapted into an original commercial. "
            f"{analysis_mode_instruction}"
            "Return exactly: reply, reference_summary, commercial_type, strengths_to_adapt, story_structure, scene_and_character_notes, camera_and_pacing, music_direction, asset_request, originality_guardrails, risks, reference_frame_plan. "
            "reply, reference_summary, and commercial_type must each be one human-readable plain string; never return arrays or stringified arrays for those fields. All other listed fields must be native JSON arrays. "
            "Every listed field must contain at least three concrete, actionable items. For story_structure, include timecode, beat, and action for each item. "
            "reference_frame_plan must contain exactly three objects with timestamp_seconds (number), purpose, and rationale. Pick an opening/hook frame, a core mechanism/gameplay frame, and an end-card/CTA frame from the supplied reference video."
        ),
        include_asset_parts=needs_asset_analysis,
    )
    defaults = _creative_direction_fallbacks(production, message)
    production.creative_direction = VideoProductionCreativeDirection(
        status="draft",
        reference_summary=_string_value(
            payload,
            "reference_summary",
            "Analyze the supplied reference for its transferable commercial structure.",
        ),
        commercial_type=_string_value(payload, "commercial_type", "Commercial video", separator=" · "),
        strengths_to_adapt=_string_list(payload, "strengths_to_adapt", defaults["strengths"]),
        story_structure=_string_list(payload, "story_structure", defaults["story"]),
        scene_and_character_notes=_string_list(payload, "scene_and_character_notes"),
        camera_and_pacing=_string_list(payload, "camera_and_pacing"),
        music_direction=_string_list(payload, "music_direction"),
        asset_request=_string_list(payload, "asset_request", ["Logo in transparent PNG", "Product or gameplay screenshots", "Character or product reference images", "Approved CTA copy"]),
        originality_guardrails=_string_list(payload, "originality_guardrails", defaults["guardrails"]),
        risks=_string_list(payload, "risks", ["Confirm rights for all uploaded brand assets and copy."]),
        reference_frame_plan=_reference_frame_plan(payload) if needs_asset_analysis else production.creative_direction.reference_frame_plan,
        analyzed_asset_ids=analyzed_asset_ids if needs_asset_analysis else production.creative_direction.analyzed_asset_ids,
    )
    production.stage = VideoProductionStage.direction
    reply = _string_value(
        payload,
        "reply",
        "I analyzed the creative direction and prepared the brand-asset checklist. Upload the required assets, then approve the direction to move into scripting.",
    )
    production.conversation.append(VideoProductionConversationMessage(role="assistant", text=reply))
    return _save(production)


def run_production_designer(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    message = request.message.strip()
    if message:
        production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
    payload = _role_payload(
        production,
        roles={"brand", "character", "product", "logo", "background", "audio"},
        instruction=message,
        role_prompt=(
            "You are the Production Designer for a commercial video. Turn the locked script and supplied brand assets into a controlled visual production bible. "
            "Inspect only the brand assets supplied to this stage and map them to practical visual rules for future keyframes and Veo shots. "
            "Do not rewrite the script, do not create storyboard shots yet, and do not invent assets that were not supplied. "
            "Lock visual identity, product and character handling, logo/copy treatment, keyframe rules, and continuity rules before video generation. "
        "Create the smallest Asset Pack inventory needed by the locked script before storyboarding. Do NOT create one pack for every category. A Pack is only valid when it locks a reusable visual state used by one or more script scenes. "
        "Brand and reference uploads are input material only: they may be listed in asset_ids for a Pack, but they must never become separate Packs just because they were uploaded or appeared in prior history. "
        "Use character packs for each recurring on-screen identity, environment packs for a reusable physical space, prop or UI packs only for a recurring hero product or UI state, one optional global lighting pack only when a visual sheet is genuinely needed, and transition packs only for a real scene handoff that needs a shared visual anchor. "
            "Create one separate Character Pack for every recurring performer or mascot. Never place two identities in one Character Pack. Environment Packs must contain no people, faces, hands, mascots, or character silhouettes: they only lock the empty spatial geometry. "
            "Prop Packs are isolated object or product boards only. Never show people, faces, hands, bodies, mascots, or character silhouettes in a Prop Pack, and never attach Character, generic Brand, or reference media to it. If no approved product asset exists, list it in missing_assets instead of creating a Prop Pack. "
            "Each pack must have a title, purpose, reason_for_new_pack, scene_ids, a precise English image-generation prompt, a crop_plan mapping all four cells, and only IDs of supplied relevant brand assets. scene_ids must contain only IDs from the locked script scenes. A 2x2 sheet is a contact sheet for approving visual states, never a final Veo input. "
            "Every cell must be a complete, standalone, full safe-frame composition: use medium or wide framing and keep head, torso, hands, hero product, and relevant environment inside an 8-10% edge margin. "
            "Never request or use extreme close-ups, partial faces, cropped heads, cut-off hands, or a subject crossing a grid divider. Character packs must lock the exact identity, hair, wardrobe, body proportions, and product. Environment packs must lock 360-degree geometry, object placement, horizon, and lighting. "
            "Return concrete lighting_and_color_cards, motion_blueprints, and transition_rules. Motion blueprints must define anticipation, primary action, micro-motion, and camera movement. Transition rules must name a shared visual anchor for adjacent shots. "
            "Every list item must be a plain, concise production rule. Do not output JSON-like dictionaries, semicolon metadata, or 'Not defined yet'. If something is missing, put it in missing_assets. "
            "Return exactly: reply, visual_identity, character_and_product_rules, logo_and_copy_rules, keyframe_rules, continuity_rules, missing_assets, keyframe_prompts, lighting_and_color_cards, motion_blueprints, transition_rules, asset_packs. "
            "asset_packs must be an array of objects with title, asset_pack_type, purpose, reason_for_new_pack, scene_ids, prompt, crop_plan, asset_ids. "
            "Return at most 8 packs for a 30-second commercial, proportionally fewer for 15 seconds, and never duplicate the same type and entity/scene."
        ),
    )
    links = [VideoProductionAssetLink.model_validate(link) for link in production.asset_links]
    available_asset_ids = _brand_image_asset_ids(production)
    valid_scene_ids = {scene.id for scene in production.script.scenes}

    def design_sheets(key: str, kind: str, fallback_title: str, fallback_purpose: str, asset_pack_type: str) -> list[VideoProductionDesignSheet]:
        raw_sheets = payload.get(key)
        sheets: list[VideoProductionDesignSheet] = []
        if isinstance(raw_sheets, list):
            for index, item in enumerate(raw_sheets, start=1):
                if not isinstance(item, dict):
                    continue
                raw_asset_ids = item.get("asset_ids")
                asset_ids = [str(asset_id) for asset_id in raw_asset_ids if str(asset_id) in available_asset_ids] if isinstance(raw_asset_ids, list) else []
                sheets.append(VideoProductionDesignSheet(
                    id=f"design_{uuid4().hex[:8]}",
                    title=str(item.get("title") or f"{fallback_title} {index}"),
                    kind=kind,  # type: ignore[arg-type]
                    asset_pack_type=asset_pack_type,  # type: ignore[arg-type]
                    purpose=str(item.get("purpose") or fallback_purpose),
                    prompt=str(item.get("prompt") or ""),
                    crop_plan=_string_list(item, "crop_plan", ["Top-left: establish the approved visual state.", "Top-right: preserve the same subject and lighting.", "Bottom-left: show the next controlled action state.", "Bottom-right: show the resolved action state."]),
                    asset_ids=asset_ids,
                ))
        if sheets:
            return sheets
        scene_name = production.script.scenes[0].title if production.script.scenes else "hero scene"
        return [VideoProductionDesignSheet(
            id=f"design_{uuid4().hex[:8]}",
            title=fallback_title,
            kind=kind,  # type: ignore[arg-type]
            asset_pack_type=asset_pack_type,  # type: ignore[arg-type]
            purpose=fallback_purpose,
            prompt=(
                f"Create one polished 2x2 visual sequence sheet for the {scene_name} of this commercial. "
                "Keep the same supplied character, product, art direction, palette, lighting, and world state in all four equal cells. "
                "Every cell is a complete medium or wide safe-frame composition: keep all heads, hands, hero products, and important action fully inside its own cell with 8% edge margin. "
                "Show four controlled variations or consecutive states. No close-ups, cropped faces, cut-off subjects, captions, labels, watermarks, borders, or invented logos."
            ),
            crop_plan=["Top-left: approved establishing state.", "Top-right: matching alternate angle or pose.", "Bottom-left: controlled action state.", "Bottom-right: resolved state for the next shot."],
            asset_ids=[],
        )]

    def asset_packs() -> list[VideoProductionDesignSheet]:
        raw_packs = payload.get("asset_packs")
        packs: list[VideoProductionDesignSheet] = []
        allowed_types = {"character", "environment", "prop", "ui", "lighting", "transition"}
        if isinstance(raw_packs, list):
            for index, item in enumerate(raw_packs, start=1):
                if not isinstance(item, dict):
                    continue
                pack_type = str(item.get("asset_pack_type") or "environment").lower()
                if pack_type not in allowed_types:
                    pack_type = "environment"
                raw_asset_ids = item.get("asset_ids")
                requested_asset_ids = [str(asset_id) for asset_id in raw_asset_ids if str(asset_id) in available_asset_ids] if isinstance(raw_asset_ids, list) else []
                pack_asset_ids = _filter_pack_asset_ids(production, pack_type, requested_asset_ids)
                sheet = VideoProductionDesignSheet(
                    id=f"design_{uuid4().hex[:8]}",
                    title=str(item.get("title") or f"{pack_type.title()} Pack {index}"),
                    kind="character_consistency" if pack_type == "character" else "scene_style",
                    asset_pack_type=pack_type,  # type: ignore[arg-type]
                    purpose=str(item.get("purpose") or f"Lock the reusable {pack_type} state for storyboard keyframes."),
                    prompt=str(item.get("prompt") or ""),
                    crop_plan=_string_list(item, "crop_plan"),
                    scene_ids=list(dict.fromkeys(
                        scene_id for scene_id in item.get("scene_ids", [])
                        if isinstance(scene_id, str) and scene_id in valid_scene_ids
                    )) if isinstance(item.get("scene_ids"), list) else [],
                    reason_for_new_pack=str(item.get("reason_for_new_pack") or "Reusable visual state required by the locked script."),
                    asset_ids=pack_asset_ids,
                )
                inferred_type = _infer_asset_pack_type(sheet)
                if pack_type == "environment" and inferred_type != "environment":
                    sheet.asset_pack_type = inferred_type  # type: ignore[assignment]
                    sheet.kind = "character_consistency" if inferred_type == "character" else "scene_style"
                packs.extend(_split_duo_character_pack(sheet) if sheet.asset_pack_type == "character" else [sheet])
        if packs:
            return _normalize_asset_packs(production, packs)

        # A model fallback must be deliberately small. Do not manufacture a
        # category inventory or attach every uploaded image to every Pack.
        scene_ids = [scene.id for scene in production.script.scenes]
        image_asset_ids = [
            link.asset_id for link in links
            if link.asset_id in available_asset_ids
            and (_asset := _asset_by_id(link.asset_id))
            and _asset.type in {"image", "gif"}
        ]
        fallback: list[VideoProductionDesignSheet] = [
            VideoProductionDesignSheet(
                id=f"design_{uuid4().hex[:8]}",
                title="Primary Environment Pack",
                kind="scene_style",
                asset_pack_type="environment",
                purpose="Lock the reusable location geometry, primary angle, reverse angle, and spatial anchors.",
                reason_for_new_pack="The script uses a recurring physical location across multiple shots.",
                scene_ids=scene_ids[:3],
            )
        ]
        if image_asset_ids:
            fallback.append(VideoProductionDesignSheet(
                id=f"design_{uuid4().hex[:8]}",
                title="Primary Character or Product Pack",
                kind="character_consistency",
                asset_pack_type="character",
                purpose="Lock the main recurring on-screen identity and approved hero-product handling.",
                reason_for_new_pack="The script requires a stable recurring hero identity.",
                scene_ids=scene_ids[:3],
                asset_ids=_filter_pack_asset_ids(production, "character", image_asset_ids[:1]),
            ))
        return _normalize_asset_packs(production, fallback)

    packs = asset_packs()
    production.design_bible = VideoProductionDesignBible(
        status="draft",
        visual_identity=_string_list(payload, "visual_identity", production.script.style_bible),
        character_and_product_rules=_string_list(payload, "character_and_product_rules"),
        logo_and_copy_rules=_string_list(payload, "logo_and_copy_rules", production.script.brand_rules),
        keyframe_rules=_string_list(payload, "keyframe_rules", ["Use one controlled full-frame composition per shot.", "Preserve approved product, character, palette, and layout details."]),
        continuity_rules=_string_list(payload, "continuity_rules", ["Match lighting, palette, product state, and character styling between adjacent shots."]),
        missing_assets=_string_list(payload, "missing_assets"),
        keyframe_prompts=_string_list(payload, "keyframe_prompts"),
        lighting_and_color_cards=_production_rule_list(payload, "lighting_and_color_cards", ["Use one consistent key light, color temperature, contrast curve, focal length, and depth-of-field rule per scene sequence."]),
        motion_blueprints=_production_rule_list(payload, "motion_blueprints", ["Every shot begins with a readable anticipation pose, one primary action, subtle physical micro-motion, and a deliberate camera move."]),
        transition_rules=_production_rule_list(payload, "transition_rules", ["Adjacent scene transitions must share one visible anchor such as a phone screen, hero product, flower, or white flash."]),
        asset_packs=packs,
        character_consistency_sheets=[sheet for sheet in packs if sheet.asset_pack_type == "character"],
        scene_style_sheets=[sheet for sheet in packs if sheet.asset_pack_type != "character"],
    )
    _hydrate_asset_pack_inventory(production)
    production.stage = VideoProductionStage.design
    reply = str(payload.get("reply") or "I created the production design bible. Approve it before the Director creates the shot cards and keyframes.")
    production.conversation.append(VideoProductionConversationMessage(role="assistant", text=reply))
    return _save(production)


def _agent_payload(production: VideoProduction, instruction: str) -> dict[str, object]:
    asset_links = [VideoProductionAssetLink.model_validate(link) for link in production.asset_links]
    reference_names = [
        (_asset_by_id(link.asset_id).title if _asset_by_id(link.asset_id) else link.asset_id)
        for link in asset_links
        if link.role == "reference"
    ]
    brand_names = [
        f"{link.role}: {(_asset_by_id(link.asset_id).title if _asset_by_id(link.asset_id) else link.asset_id)}"
        for link in asset_links
        if link.role != "reference"
    ]
    prompt = (
        "You are the Screenwriter for an AI commercial video production workspace. "
        "Create or revise an original, production-ready commercial script from the approved creative direction, user's brief, and supplied brand assets. "
        "Use reference material only to extract structure, pace, and visual lessons; do not copy protected characters, logos, copy, or footage. "
        f"Creative reference assets (analysis only): {_safe_json(reference_names)}. "
        f"Brand assets (use these to create the new ad): {_safe_json(brand_names)}. "
        "Return JSON only with exactly: reply, creative_goal, audience, logline, style_bible, beats, scenes, brand_rules, asset_manifest, risks, raw_script. "
        f"Output language: {_response_language_hint(production, instruction)}. Write every user-facing value in that language; keep only JSON keys in English. Do not translate filenames or supplied brand copy. "
        "beats must be an array with start_seconds, end_seconds, title, purpose. "
        "Every beat must be short and shootable: 3-5 seconds each, never longer than 5 seconds. Use 4 beats for 15s, 7-8 beats for 30s, and 12-15 beats for 60s. "
        "scenes must be an array with id, title, setting, action, dialogue_or_copy. "
        "raw_script must be divided into matching timecoded blocks no longer than 5 seconds each. If a gameplay demo, dialogue exchange, or product proof needs more time, split it into multiple precise blocks instead of writing one long range. "
        f"Build a {production.target_seconds}s, {production.aspect_ratio} commercial in {production.resolution}. Keep the response practical and concise. "
        "The user may refine a prior script; retain agreed decisions unless explicitly changed. "
        f"Production brief: {production.brief or 'Not written yet.'} "
        f"User message: {instruction or 'Draft the first script.'} "
        f"Current script: {_safe_json(production.script.model_dump(mode='json'))}. "
        f"Conversation: {_safe_json([message.model_dump(mode='json') for message in production.conversation[-8:]])}."
    )
    try:
        return _parse_json(_call_multimodal_text_model(
            prompt=prompt,
            # The Screenwriter works from the approved strategy and a textual asset
            # inventory. Actual brand media is intentionally reserved for Design.
            parts=[],
            model_id=get_settings().vertex_video_analysis_model,
        ))
    except Exception:
        logger.warning("Video Script Agent unavailable; using a local structured draft", exc_info=True)
        return {}


def run_script_agent(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    message = request.message.strip()
    if message:
        production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
    if not production.brief and message:
        production.brief = message
    payload = _agent_payload(production, message)
    production.script = _script_from_payload(production, payload, message)
    reply = str(payload.get("reply") or "I drafted an editable script. Review the beats and scenes, then lock it when the creative direction is ready.")
    production.conversation.append(VideoProductionConversationMessage(role="assistant", text=reply))
    production.stage = VideoProductionStage.script
    return _save(production)


def _apply_default_shot_asset_bindings(
    production: VideoProduction,
    shots: list[VideoProductionShot],
) -> list[VideoProductionShot]:
    """Bind approved Asset Pack states to every shot without ever using a raw grid.

    The Director may refine these bindings in the storyboard UI. These defaults
    make the first editable storyboard deterministic once Design has approved
    character, environment, product/UI, lighting, and transition states.
    """
    approved_by_type: dict[str, list[str]] = {}
    for sheet in _all_design_sheets(production):
        state_ids = list(dict.fromkeys([
            *sheet.approved_asset_ids,
            sheet.selected_asset_id,
        ]))
        if state_ids:
            approved_by_type.setdefault(sheet.asset_pack_type, []).extend(
                asset_id for asset_id in state_ids if asset_id
            )

    for asset_type, state_ids in approved_by_type.items():
        approved_by_type[asset_type] = list(dict.fromkeys(state_ids))

    characters = approved_by_type.get("character", [])
    environments = approved_by_type.get("environment", [])
    props_and_ui = [
        *approved_by_type.get("prop", []),
        *approved_by_type.get("ui", []),
    ]
    transitions = approved_by_type.get("transition", [])

    for index, shot in enumerate(shots):
        if not shot.character_state_asset_id and characters:
            shot.character_state_asset_id = characters[index % len(characters)]
        if not shot.environment_state_asset_id and environments:
            shot.environment_state_asset_id = environments[index % len(environments)]
        if not shot.prop_ui_asset_ids and props_and_ui:
            # A scene can draw on a small, stable set of approved product/UI states.
            shot.prop_ui_asset_ids = props_and_ui[:2]
        if not shot.transition_in_asset_id and transitions and index > 0:
            shot.transition_in_asset_id = transitions[(index - 1) % len(transitions)]
        if not shot.transition_out_asset_id and transitions and index < len(shots) - 1:
            shot.transition_out_asset_id = transitions[index % len(transitions)]
    return shots


def _fallback_shots(production: VideoProduction) -> list[VideoProductionShot]:
    beats = production.script.beats or _fallback_script(production, production.brief).beats
    shots = [
        VideoProductionShot(
            id=f"shot_{uuid4().hex[:8]}",
            order=index + 1,
            scene_id=production.script.scenes[index].id if index < len(production.script.scenes) else "",
            title=beat.title,
            start_seconds=beat.start_seconds,
            duration_seconds=max(1, beat.end_seconds - beat.start_seconds),
            purpose=beat.purpose,
            visual="Create an approved keyframe from the linked brand and reference assets.",
            action=beat.purpose,
            camera="Deliberate commercial framing; preserve continuity with adjacent shots.",
            veo_prompt=f"{beat.purpose} Maintain the approved art direction and visual continuity.",
            continuity="Match the previous shot's lighting, palette, product state, and character styling.",
            audio_cue="Define music and SFX at edit stage.",
            lighting_rule=(production.design_bible.lighting_and_color_cards[0] if production.design_bible.lighting_and_color_cards else "Maintain the approved lighting and color card."),
            motion_blueprint=(production.design_bible.motion_blueprints[0] if production.design_bible.motion_blueprints else "Start with anticipation, complete one readable action, add micro-motion, and use one deliberate camera move."),
        )
        for index, beat in enumerate(beats)
    ]
    return _apply_default_shot_asset_bindings(production, shots)


def lock_script_and_create_storyboard(production_id: str, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    production.script.status = "locked"
    production.script.updated_at = datetime.utcnow()
    production.stage = VideoProductionStage.design
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text="The script is locked. Next, the Production Designer will turn it into a visual bible before the Director creates the storyboard.",
    ))
    return _save(production)


def _shots_from_payload(production: VideoProduction, payload: dict[str, object]) -> list[VideoProductionShot]:
    items = payload.get("shots")
    if not isinstance(items, list):
        return _fallback_shots(production)
    shots: list[VideoProductionShot] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        duration = float(item.get("duration_seconds") or 4)
        shots.append(VideoProductionShot(
            id=f"shot_{uuid4().hex[:8]}",
            order=index,
            scene_id=str(item.get("scene_id") or ""),
            title=str(item.get("title") or f"Shot {index}"),
            start_seconds=float(item.get("start_seconds") or sum(shot.duration_seconds for shot in shots)),
            duration_seconds=max(1, min(8, duration)),
            purpose=str(item.get("purpose") or "Advance the commercial story."),
            visual=str(item.get("visual") or ""),
            action=str(item.get("action") or ""),
            camera=str(item.get("camera") or ""),
            dialogue_or_copy=str(item.get("dialogue_or_copy") or ""),
            veo_prompt=str(item.get("veo_prompt") or ""),
            continuity=str(item.get("continuity") or ""),
            audio_cue=str(item.get("audio_cue") or ""),
            transition=str(item.get("transition") or "cut"),
            lighting_rule=str(item.get("lighting_rule") or (production.design_bible.lighting_and_color_cards[0] if production.design_bible.lighting_and_color_cards else "")),
            motion_blueprint=str(item.get("motion_blueprint") or (production.design_bible.motion_blueprints[0] if production.design_bible.motion_blueprints else "")),
        ))
    return _apply_default_shot_asset_bindings(production, shots) if shots else _fallback_shots(production)


def run_director_agent(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    message = request.message.strip()
    if message:
        production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
    payload = _role_payload(
        production,
        roles={"reference", "brand", "character", "product", "logo", "background"},
        instruction=message,
        role_prompt=(
            "You are the Director for a commercial video production. Convert the locked script and approved production design bible into a practical storyboard. Use 3-5 shots for 15 seconds, 6-12 shots for 30 seconds, and 12-18 shots for 60 seconds. Each shot must be independently generatable, 4-8 seconds long, and have a keyframe concept, camera language, continuity instruction, audio cue, and English Veo prompt. "
            "Every shot must bind one or more character asset states when people appear, one environment state, relevant product/UI states, one lighting rule, one motion blueprint, and optional transition-in/transition-out anchors from the approved Asset Packs. Do not use raw contact sheets as a Veo input. "
            "Return exactly: reply, shots. shots is an array with scene_id, title, start_seconds, duration_seconds, purpose, visual, action, camera, dialogue_or_copy, veo_prompt, continuity, audio_cue, transition, lighting_rule, motion_blueprint."
        ),
    )
    production.shots = _shots_from_payload(production, payload)
    production.stage = VideoProductionStage.storyboard
    reply = str(payload.get("reply") or "The Director created editable shot cards. Generate and approve the keyframe for each shot before video production.")
    production.conversation.append(VideoProductionConversationMessage(role="assistant", text=reply))
    return _save(production)


def update_video_production_shot(
    production_id: str,
    shot_id: str,
    request: VideoProductionShotUpdateRequest,
    user: User,
) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    shot = next((item for item in production.shots if item.id == shot_id), None)
    if not shot:
        raise KeyError("Shot not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(shot, field, value)
    return _save(production)


def reorder_video_production_shots(
    production_id: str,
    request: VideoProductionShotOrderRequest,
    user: User,
) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    by_id = {shot.id: shot for shot in production.shots}
    ordered = [by_id[shot_id] for shot_id in request.shot_ids if shot_id in by_id]
    ordered.extend(shot for shot in production.shots if shot.id not in request.shot_ids)
    for index, shot in enumerate(ordered, start=1):
        shot.order = index
    production.shots = ordered
    return _save(production)


def _production_job(*, production: VideoProduction, shot: VideoProductionShot, kind: str) -> GenerationJob:
    now = datetime.utcnow()
    job = GenerationJob(
        job_id=f"job_{uuid4().hex[:12]}",
        workspace_id=production.workspace_id,
        status=JobStatus.running,
        progress=5,
        lineage_key=f"vprod_{uuid4().hex[:16]}",
        message=f"Preparing {kind} for S{shot.order:02d}…",
        tool_id="video-production-keyframe" if kind == "keyframe" else "video-production-veo",
        title=f"{production.title} · S{shot.order:02d} {kind}",
        source_asset_id=shot.keyframe_asset_id if kind == "video" else None,
        created_at=now,
        updated_at=now,
    )
    JOBS[job.job_id] = job
    upsert_job(job)
    return job


def _keyframe_size(production: VideoProduction) -> str:
    return "1200x628" if production.aspect_ratio == "16:9" else "628x1200"


def _design_sheet_size(_production: VideoProduction) -> str:
    """A square contact sheet gives each 2x2 panel usable, uncropped space."""
    return "2048x2048"


def _shot_asset_ids(production: VideoProduction, shot: VideoProductionShot) -> list[str]:
    explicit_state_ids = [
        shot.character_state_asset_id,
        *shot.additional_character_state_asset_ids,
        shot.environment_state_asset_id,
        *shot.prop_ui_asset_ids,
        shot.transition_in_asset_id,
        shot.transition_out_asset_id,
    ]
    # A shot must prefer its explicit Asset Pack bindings. For older productions
    # without bindings, use approved independent panel crops only - never send a
    # whole contact sheet to the final keyframe or Veo generation call.
    approved_fallback_ids = [
        asset_id
        for sheet in _all_design_sheets(production)
        if sheet.status in {"ready", "approved"}
        for asset_id in [*sheet.approved_asset_ids, sheet.selected_asset_id, *sheet.panel_asset_ids]
        if asset_id
    ]
    return list(dict.fromkeys([
        *shot.asset_ids,
        *(asset_id for asset_id in explicit_state_ids if asset_id),
        *approved_fallback_ids,
        *production.reference_asset_ids,
    ]))


def _keyframe_prompt(production: VideoProduction, shot: VideoProductionShot) -> str:
    rules = "; ".join(production.script.brand_rules) or "Preserve supplied product and brand assets."
    return (
        "You are the final keyframe artist for a commercial video storyboard. Create exactly ONE polished, "
        "production-ready still for the exact shot below. This is a single-frame Veo input, never a grid, collage, contact sheet, or multi-panel image. "
        "Use only the attached approved Asset Pack states as sources of truth. If multiple character states are attached, show those exact recurring characters together without changing their identity or wardrobe. Keep supplied brand and product references consistent. Do not invent logos or copy. "
        f"Shot: {shot.title}. Purpose: {shot.purpose}. Visual: {shot.visual}. Action: {shot.action}. "
        f"Camera: {shot.camera}. Lighting card: {shot.lighting_rule}. Motion blueprint: {shot.motion_blueprint}. "
        f"Continuity: {shot.continuity}. Transition: {shot.transition}. Brand rules: {rules}. "
        "Keep one clear hero focus. Preserve character identity, wardrobe, scene geometry, prop/UI placement, light direction, color grade, focal length, and depth of field. "
        "Show a readable pre-action pose with natural physical micro-motion cues where appropriate. Keep face, head, torso, hands, product, and essential UI fully inside a 10 percent safe margin. "
        "No borders, split screens, watermarks, edge clipping, truncated faces, cropped heads, cut-off hands, duplicate limbs, or unapproved text."
    )


def _all_design_sheets(production: VideoProduction) -> list[VideoProductionDesignSheet]:
    """Return canonical Asset Packs while allowing saved legacy productions."""
    sheets = production.design_bible.asset_packs or [
        *production.design_bible.character_consistency_sheets,
        *production.design_bible.scene_style_sheets,
    ]
    seen: set[str] = set()
    return [sheet for sheet in sheets if not (sheet.id in seen or seen.add(sheet.id))]


def _find_design_sheet(production: VideoProduction, sheet_id: str) -> VideoProductionDesignSheet | None:
    return next((sheet for sheet in _all_design_sheets(production) if sheet.id == sheet_id), None)


def _design_sheet_asset_ids(production: VideoProduction, sheet: VideoProductionDesignSheet) -> list[str]:
    if sheet.asset_pack_type == "environment":
        # A spatial pack must not inherit character/product reference pixels.
        # It can use an explicitly tagged background, otherwise the text prompt
        # is intentionally enough to generate an empty location geometry.
        return [
            link.asset_id
            for link in production.asset_links
            if link.role == "background"
            and (_asset := _asset_by_id(link.asset_id))
            and _asset.type in {"image", "gif"}
        ][:4]
    asset_ids = _filter_pack_asset_ids(production, sheet.asset_pack_type, sheet.asset_ids)
    if asset_ids:
        return list(dict.fromkeys(asset_ids))
    allowed_roles = _allowed_roles_for_pack(sheet.asset_pack_type)
    if not allowed_roles:
        return []
    return [
        link.asset_id
        for link in production.asset_links
        if link.role in allowed_roles
        and (_asset := _asset_by_id(link.asset_id))
        and _asset.type in {"image", "gif"}
    ][:4]


def _design_sheet_reference_video_ids(
    production: VideoProduction,
    sheet: VideoProductionDesignSheet,
) -> list[str]:
    """Return creative-reference videos that can be converted into image inputs.

    Gemini Image uses still-image conditioning most reliably for this workflow.
    The Creative Strategist supplies the moments to sample; the original video
    remains a reference input and is never sent wholesale to image generation.
    """
    # Environment geometry is a controlled empty space. Conditioning it on a
    # live-action reference often leaks the competitor's people into the pack.
    if sheet.asset_pack_type == "environment":
        return []
    # Reference video is analyzed by the Creative Strategist. Design uses only
    # explicitly assigned, current-production brand video inputs so a competitor
    # reference cannot leak into a reusable visual state.
    candidates = list(sheet.asset_ids)
    seen: set[str] = set()
    video_ids: list[str] = []
    for asset_id in candidates:
        asset = _asset_by_id(asset_id)
        if not asset or asset.type != "video" or asset_id in seen:
            continue
        seen.add(asset_id)
        video_ids.append(asset_id)
    return video_ids


def _reference_video_suffix(asset: Asset) -> str:
    """Keep a media extension when staging an uploaded reference for FFmpeg."""
    suffix = Path(asset.title).suffix.lower()
    return suffix if suffix in {".mp4", ".mov", ".m4v", ".webm"} else ".mp4"


def _extract_reference_video_frames(
    production: VideoProduction,
    video_assets: list[Asset],
) -> list[bytes]:
    """Extract Strategist-selected stills for Design image conditioning.

    A current direction report normally contains hook, gameplay, and CTA frame
    timings. Older productions without that report intentionally skip video
    extraction instead of guessing arbitrary moments from a possibly short clip.
    """
    frame_plan = production.creative_direction.reference_frame_plan
    if not frame_plan or not video_assets:
        return []
    settings = get_settings()
    ffmpeg_path = settings.playable_capture_ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg is required to extract Design reference frames from a video.")

    source = video_assets[0]
    source_bytes = _load_asset_bytes(source)
    if not source_bytes:
        raise RuntimeError("The Creative Reference video could not be read for Design frame extraction.")

    frames: list[bytes] = []
    with tempfile.TemporaryDirectory(prefix="incept-design-reference-") as directory:
        root = Path(directory)
        video_path = root / f"reference{_reference_video_suffix(source)}"
        video_path.write_bytes(source_bytes)
        for index, frame in enumerate(frame_plan[:3]):
            try:
                timestamp = max(0.0, float(frame.get("timestamp_seconds", 0)))
            except (AttributeError, TypeError, ValueError):
                continue
            output_path = root / f"reference-frame-{index}.jpg"
            command = [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=1280:-2",
                "-q:v",
                "3",
                str(output_path),
            ]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                frames.append(output_path.read_bytes())
            else:
                logger.warning(
                    "Could not extract Design reference frame at %.2fs from %s: %s",
                    timestamp,
                    source.id,
                    result.stderr.decode("utf-8", errors="replace")[:300],
                )
    return frames


def _normalize_design_sheet_for_asset_grid(sheet: VideoProductionDesignSheet) -> None:
    """Give every sheet an explicit production role for its four locked panels."""
    if sheet.asset_pack_type == "character":
        sheet.crop_plan = [
            "A: front-facing medium hero view locking face, hair, wardrobe, body shape, hands, hero product, and environment.",
            "B: complete three-quarter view of the exact same character, wardrobe, accessories, and product.",
            "C: complete rear view locking hair, costume silhouette, and spatial relationship to the environment.",
            "D: complete contextual action view with the same character, product, lighting, and environment.",
        ]
    elif sheet.asset_pack_type == "environment":
        sheet.crop_plan = [
            "A: empty wide establishing view that maps the complete environment and spatial anchors.",
            "B: empty primary camera angle preserving furniture, product placement, and practical light sources.",
            "C: empty reverse angle preserving the same background geometry and lighting.",
            "D: empty transition or product anchor frame that can match-cut into the next scene.",
        ]
    elif sheet.asset_pack_type == "prop":
        sheet.crop_plan = [
            "A: clean isolated hero product view with all approved details readable and inside safe margins.",
            "B: complete three-quarter product view preserving exact materials, colors, and logo treatment.",
            "C: tabletop or environmental product placement showing relative scale without any person or body part.",
            "D: clean product presentation with an empty contextual background and no character, hand, face, or mascot.",
        ]
    elif sheet.asset_pack_type == "ui":
        sheet.crop_plan = [
            "A: clean approved UI or device-screen state with readable hierarchy and safe copy areas.",
            "B: alternate approved UI state preserving device proportions and layout rules.",
            "C: gameplay or product screen placement without a person, hand, or new brand element.",
            "D: CTA-safe end-card UI presentation using only approved brand materials and copy-safe areas.",
        ]
    elif sheet.asset_pack_type == "lighting":
        sheet.crop_plan = [
            "A: wide lighting reference showing the key light direction, color temperature, contrast, and depth.",
            "B: hero medium frame under the same locked light and color grade.",
            "C: product close-medium frame preserving reflections, material response, and shadow direction.",
            "D: reverse angle that proves the lighting remains coherent throughout the space.",
        ]
    else:  # transition
        sheet.crop_plan = [
            "A: outgoing shot end frame with the shared match-cut anchor visible and safely framed.",
            "B: incoming shot start frame containing the same anchor, geometry, and color relationship.",
            "C: bridge frame showing the anchor filling or wiping the frame without clipping the subject.",
            "D: resolved target scene frame that continues from the same visual anchor.",
        ]


def _design_sheet_grid_prompt(production: VideoProduction, sheet: VideoProductionDesignSheet) -> str:
    """Generate one contact sheet that locks a shared visual state before keyframing."""
    rules = "; ".join([
        *production.design_bible.visual_identity,
        *production.design_bible.character_and_product_rules,
        *production.design_bible.continuity_rules,
    ]) or "Preserve the supplied brand references exactly."
    panel_plan = " ".join(
        f"Panel {chr(65 + index)}: {instruction}"
        for index, instruction in enumerate(sheet.crop_plan[:4])
    )
    pack_type = sheet.asset_pack_type.upper()
    pack_rules = {
        "CHARACTER": "All four panels must show the identical character identity: matching facial structure, hairstyle, makeup, skin tone, wardrobe, body proportions, accessories, and hero product.",
        "ENVIRONMENT": "All four panels must describe one coherent empty 360-degree environment: preserve exact light source direction, horizon, furniture, props, background anchors, product placement, and color grade across establishing, primary, and reverse views. Do not show any person, face, hand, mascot, or character silhouette.",
        "PROP": "All four panels must preserve the exact product form, materials, colors, logo treatment, and relative scale. Do not show any person, face, hand, body part, mascot, or character silhouette in any panel.",
        "UI": "All four panels must preserve the exact approved UI hierarchy, device proportions, gameplay state, and copy-safe areas. Never invent readable copy or a new logo.",
        "LIGHTING": "All four panels must lock one consistent color temperature, key-light direction, contrast curve, lens feeling, material response, and depth-of-field treatment.",
        "TRANSITION": "All four panels must preserve the exact shared transition anchor, scale, color relationship, and spatial handoff needed to cut cleanly between adjacent scenes.",
    }
    consistency_rule = pack_rules.get(pack_type, pack_rules["ENVIRONMENT"])
    prop_isolation = (
        "For this PROP Pack, ignore any character, performer, lifestyle, hand-held, or action wording in the production instruction. "
        "Generate the approved product alone in an empty set; no person or body part may appear. "
        if pack_type == "PROP" else ""
    )
    return (
        "You are a Lead Pre-Visualization Art Director creating controlled asset sheets for an AI video production. "
        "Create exactly ONE square 1:1 2x2 contact sheet with four equal panels, thin neutral gutters, and no text, labels, captions, watermarks, or UI chrome. "
        f"Asset pack type: {pack_type}. Sheet title: {sheet.title}. Purpose: {sheet.purpose}. "
        f"Production instruction: {sheet.prompt}. Approved visual rules: {rules}. "
        f"Required panel layout: {panel_plan}. {consistency_rule} {prop_isolation}"
        "Each panel is a complete medium or wide composition, not a close-up crop. Keep every allowed subject, hero product, and relevant environment fully inside its own panel with a generous 10 percent outer safe margin. "
        "Use one unified lighting direction, color temperature, material treatment, and color grade. Include subtle physical pre-action cues such as natural posture, fabric movement, hair movement, steam, or particles when appropriate. "
        "Never split a person or product across panels. Never crop a face, head, body part, hand, or product at a panel edge. Never merge panels, overlap subjects, change wardrobe, change character identity, add duplicate limbs, or create irregular panel sizes. "
        "Use only supplied brand assets as references. Do not invent a new brand, logo, product, or protected character identity. This sheet locks visual assets only; it will not be sent directly to Veo."
    )


def create_design_sheet_job(production_id: str, sheet_id: str, user: User) -> GenerationJob:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    sheet = _find_design_sheet(production, sheet_id)
    if not sheet:
        raise KeyError("Design sheet not found")
    _normalize_design_sheet_for_asset_grid(sheet)
    if sheet.asset_pack_type == "prop":
        linked_product_assets = [
            _asset_by_id(asset_id)
            for asset_id in sheet.asset_ids
        ]
        if not any(
            asset is not None and asset.type in {"image", "gif"}
            for asset in linked_product_assets
        ):
            # A product pack cannot be inferred from a character or reference
            # frame. Keep it editable until the user supplies the hero product.
            sheet.status = "draft"
            sheet.job_id = None
            _save(production)
            raise ValueError(
                "This Prop Pack needs an approved product image before it can be generated. "
                "Upload the hero product in Brand Assets, then regenerate the Design Bible."
            )
    now = datetime.utcnow()
    job = GenerationJob(
        job_id=f"job_{uuid4().hex[:12]}",
        workspace_id=production.workspace_id,
        status=JobStatus.running,
        progress=5,
        lineage_key=f"vprod_{uuid4().hex[:16]}",
        message=f"Generating controlled 2x2 consistency sheet: {sheet.title}…",
        tool_id="video-production-design-sheet",
        title=f"{production.title} · {sheet.title}",
        created_at=now,
        updated_at=now,
    )
    JOBS[job.job_id] = job
    upsert_job(job)
    sheet.job_id = job.job_id
    sheet.status = "generating"
    sheet.selected_panel = None
    sheet.selected_asset_id = None
    sheet.approved_panel_asset_ids = {}
    sheet.approved_asset_ids = []
    sheet.panel_asset_ids = []
    sheet.grid_asset_id = None
    _save(production)
    return job


async def run_design_sheet_background(production_id: str, sheet_id: str, job_id: str, user: User) -> None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    job = JOBS.get(job_id)
    if not production or not job:
        return
    sheet = _find_design_sheet(production, sheet_id)
    if not sheet:
        return
    settings = get_settings()
    try:
        if not settings.vertex_gemini_enabled or not settings.gcp_project_id:
            raise RuntimeError("Gemini Image is not configured for Video Production design sheets.")
        asset_ids = _design_sheet_asset_ids(production, sheet)
        image_reference_bytes = [
            content for asset_id in asset_ids
            if (asset := _asset_by_id(asset_id)) and asset.type in {"image", "gif"}
            if (content := _load_asset_bytes(asset))
        ]
        reference_video_assets = [
            asset
            for asset_id in _design_sheet_reference_video_ids(production, sheet)
            if (asset := _asset_by_id(asset_id))
        ]
        video_reference_bytes = await asyncio.to_thread(
            _extract_reference_video_frames,
            production,
            reference_video_assets,
        )
        # Gemini 3.1 Flash Image accepts a limited number of image inputs. Keep
        # Brand Asset references first, then add up to three Strategist-selected
        # video frames for gameplay and transition context.
        reference_bytes = [*image_reference_bytes, *video_reference_bytes][:14]
        if not reference_bytes and sheet.asset_pack_type != "environment":
            raise RuntimeError(
                "Attach an image Brand Asset, or refresh Creative Direction so Design can extract approved frames from a Creative Reference video."
            )
        grid_prompt = _design_sheet_grid_prompt(production, sheet)
        _mark_generation_progress(job, 20, f"Generating controlled 2x2 consistency sheet: {sheet.title}…")
        response = await _dispatch_generation(
            grid_prompt,
            provider="gemini",
            model=settings.vertex_gemini_image_model,
            variants=1,
            reference_images=reference_bytes,
            target_size=_design_sheet_size(production),
            image_size="4K",
        )
        image = next((item for item in response if item), None)
        if not image:
            raise RuntimeError("Gemini Image returned no controlled 2x2 consistency sheet.")
        raw_grid = base64.b64decode(image)
        _mark_generation_progress(job, 82, f"Saving controlled 2x2 consistency sheet: {sheet.title}…")
        source_asset = (
            _asset_by_id(asset_ids[0]) if asset_ids
            else (reference_video_assets[0] if reference_video_assets else None)
        )
        context_asset_ids = list(dict.fromkeys([
            *asset_ids,
            *[asset.id for asset in reference_video_assets],
        ]))
        assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=[raw_grid],
            workspace_id=production.workspace_id,
            created_by=user.id,
            provider="gemini",
            model=settings.vertex_gemini_image_model,
            label=f"{production.title}_{sheet.title}_asset_sheet",
            theme="Video Production Design Asset Sheet",
            requested_sizes=[_design_sheet_size(production)],
            source_asset=source_asset,
            context_assets=[asset for asset_id in context_asset_ids if (asset := _asset_by_id(asset_id))],
        )
        if len(assets) != 1:
            raise RuntimeError("Could not save the controlled 2x2 consistency sheet.")
        grid_asset = assets[0]
        grid_asset.analysis = {
            **(grid_asset.analysis or {}),
            "video_production_id": production_id,
            "design_sheet_id": sheet_id,
            "kind": "design_asset_sheet",
            "prompt": grid_prompt,
            "reference_frame_plan": production.creative_direction.reference_frame_plan,
            "reference_video_asset_ids": [asset.id for asset in reference_video_assets],
        }
        upsert_asset(grid_asset)
        job.output_asset_ids = [grid_asset.id]
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Controlled 2x2 consistency sheet ready: {sheet.title}."
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        sheet.panel_asset_ids = []
        sheet.grid_asset_id = grid_asset.id
        sheet.status = "ready"
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text=(
                f"The controlled 2x2 consistency sheet for '{sheet.title}' is ready. "
                "Select A, B, C, or D to export one locked reference frame for related storyboard keyframes."
            ),
        ))
        _save(production)
    except Exception as exc:
        logger.exception("Video production design sheet failed for %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"Design asset sheet generation failed: {exc}"[:500]
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        sheet.status = "failed"
        _save(production)


async def select_design_sheet_panel(
    production_id: str,
    sheet_id: str,
    panel: int,
    user: User,
) -> VideoProduction:
    """Export one controlled asset-sheet quadrant as a keyframe reference."""
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    sheet = _find_design_sheet(production, sheet_id)
    if panel < 0 or panel > 3:
        raise ValueError("Design candidate must be A, B, C, or D.")
    if len(sheet.panel_asset_ids) == 4:
        candidate_asset = _asset_by_id(sheet.panel_asset_ids[panel])
        if not candidate_asset:
            raise KeyError("The generated design candidate could not be found.")
        now = datetime.utcnow()
        job = GenerationJob(
            job_id=f"job_{uuid4().hex[:12]}",
            workspace_id=production.workspace_id,
            status=JobStatus.completed,
            progress=100,
            lineage_key=f"vprod_{uuid4().hex[:16]}",
            message=f"Selected {chr(65 + panel)} from {sheet.title}.",
            tool_id="video-production-design-candidate",
            title=f"{production.title} · {sheet.title} {chr(65 + panel)}",
            output_asset_ids=[candidate_asset.id],
            created_at=now,
            updated_at=now,
        )
        JOBS[job.job_id] = job
        upsert_job(job)
        sheet.selected_panel = panel
        sheet.selected_asset_id = candidate_asset.id
        sheet.approved_panel_asset_ids[str(panel)] = candidate_asset.id
        sheet.approved_asset_ids = list(dict.fromkeys([*sheet.approved_asset_ids, candidate_asset.id]))
        sheet.status = "approved"
        _save(production)
        return production

    if not sheet.grid_asset_id:
        raise ValueError("Generate the controlled 2x2 consistency sheet before selecting a panel.")
    source_asset = _asset_by_id(sheet.grid_asset_id)
    if not source_asset:
        raise KeyError("The design sheet asset could not be found.")
    existing_asset_id = sheet.approved_panel_asset_ids.get(str(panel))
    if existing_asset_id and (existing_asset := _asset_by_id(existing_asset_id)):
        sheet.selected_panel = panel
        sheet.selected_asset_id = existing_asset.id
        sheet.status = "approved"
        _save(production)
        return production
    raw_grid = _load_asset_bytes(source_asset)
    if not raw_grid:
        raise ValueError("The design sheet could not be read.")
    from io import BytesIO
    from PIL import Image
    with Image.open(BytesIO(raw_grid)) as image:
        image.load()
        width, height = image.size
        column, row = panel % 2, panel // 2
        candidate = image.crop((round(width * column / 2), round(height * row / 2), round(width * (column + 1) / 2), round(height * (row + 1) / 2))).convert("RGB")
        candidate_bytes = BytesIO()
        candidate.save(candidate_bytes, format="PNG")

    now = datetime.utcnow()
    job = GenerationJob(
        job_id=f"job_{uuid4().hex[:12]}",
        workspace_id=production.workspace_id,
        status=JobStatus.completed,
        progress=100,
        lineage_key=f"vprod_{uuid4().hex[:16]}",
        message=f"Selected {chr(65 + panel)} from {sheet.title}.",
        tool_id="video-production-design-candidate",
        title=f"{production.title} · {sheet.title} {chr(65 + panel)}",
        created_at=now,
        updated_at=now,
    )
    JOBS[job.job_id] = job
    upsert_job(job)
    candidate_assets = await _export_master_images_to_assets(
        job=job,
        raw_outputs=[candidate_bytes.getvalue()],
        workspace_id=production.workspace_id,
        created_by=user.id,
        provider="gemini",
        model=get_settings().vertex_gemini_image_model,
        label=f"{production.title}_{sheet.title}_{chr(65 + panel)}",
        theme="Video Production Approved Design Candidate",
        requested_sizes=[_keyframe_size(production)],
        source_asset=source_asset,
        context_assets=[source_asset],
    )
    if not candidate_assets:
        raise RuntimeError("Could not save the selected design candidate.")
    candidate_asset = candidate_assets[0]
    candidate_asset.analysis = {
        **(candidate_asset.analysis or {}),
        "video_production_id": production_id,
        "design_sheet_id": sheet_id,
        "kind": "design_sheet_keyframe_reference",
        "panel": panel,
        "prompt": _design_sheet_grid_prompt(production, sheet),
        "source_grid_asset_id": source_asset.id,
    }
    upsert_asset(candidate_asset)
    job.output_asset_ids = [candidate_asset.id]
    upsert_job(job)

    sheet.selected_panel = panel
    sheet.selected_asset_id = candidate_asset.id
    sheet.approved_panel_asset_ids[str(panel)] = candidate_asset.id
    sheet.approved_asset_ids = list(dict.fromkeys([*sheet.approved_asset_ids, candidate_asset.id]))
    sheet.status = "approved"
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text=(
            f"Approved {chr(65 + panel)} from the 2x2 design sheet '{sheet.title}'. "
            "This standalone frame will guide subsequent storyboard keyframes."
        ),
    ))
    _save(production)
    return production


def _veo_shot_prompt(production: VideoProduction, shot: VideoProductionShot) -> str:
    return (
        f"{shot.veo_prompt}\n\n"
        f"Shot purpose: {shot.purpose}. Action: {shot.action}. Camera: {shot.camera}. "
        f"Lighting card: {shot.lighting_rule}. Motion blueprint: {shot.motion_blueprint}. "
        f"Continuity requirements: {shot.continuity}. Transition: {shot.transition}. Audio direction for post-production only: {shot.audio_cue}. "
        "Use the supplied single keyframe as the visual source of truth. Preserve its product, characters, environment geometry, UI placement, lighting, palette, and brand details. "
        "Generate only this shot with stable commercial framing. Do not introduce a collage, split screen, new logo, new text, wardrobe change, or a different character identity."
    )


def create_keyframe_job(production_id: str, shot_id: str, user: User) -> GenerationJob:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    shot = next((item for item in production.shots if item.id == shot_id), None)
    if not shot:
        raise KeyError("Shot not found")
    job = _production_job(production=production, shot=shot, kind="keyframe")
    shot.keyframe_job_id = job.job_id
    shot.status = "generating"
    _save(production)
    return job


async def run_keyframe_background(production_id: str, shot_id: str, job_id: str, user: User) -> None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    job = JOBS.get(job_id)
    if not production or not job:
        return
    shot = next((item for item in production.shots if item.id == shot_id), None)
    if not shot:
        return
    settings = get_settings()
    try:
        if not settings.vertex_gemini_enabled or not settings.gcp_project_id:
            raise RuntimeError("Gemini Image is not configured for Video Production keyframes.")
        _mark_generation_progress(job, 20, f"Building keyframe for S{shot.order:02d} from approved assets…")
        reference_bytes = [
            content for asset_id in _shot_asset_ids(production, shot)
            if (asset := _asset_by_id(asset_id)) and asset.type in {"image", "gif"}
            if (content := _load_asset_bytes(asset))
        ]
        if not reference_bytes:
            raise RuntimeError("Attach at least one image asset before generating a keyframe.")
        raw_outputs = [
            base64.b64decode(image)
            for image in await _dispatch_generation(
                _keyframe_prompt(production, shot),
                provider="gemini",
                model=settings.vertex_gemini_image_model,
                variants=1,
                reference_images=reference_bytes,
                target_size=_keyframe_size(production),
            )
            if image
        ]
        if not raw_outputs:
            raise RuntimeError("Gemini Image returned no keyframe output.")
        _mark_generation_progress(job, 82, f"Saving S{shot.order:02d} keyframe…")
        source_asset = _asset_by_id(_shot_asset_ids(production, shot)[0]) if _shot_asset_ids(production, shot) else None
        assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=raw_outputs,
            workspace_id=production.workspace_id,
            created_by=user.id,
            provider="gemini",
            model=settings.vertex_gemini_image_model,
            label=f"{production.title}_S{shot.order:02d}_keyframe",
            theme="Video Production Keyframe",
            requested_sizes=[_keyframe_size(production)],
            source_asset=source_asset,
            context_assets=[asset for asset_id in _shot_asset_ids(production, shot) if (asset := _asset_by_id(asset_id))],
        )
        for asset in assets:
            asset.analysis = {
                **(asset.analysis or {}),
                "video_production_id": production_id,
                "shot_id": shot_id,
                "kind": "keyframe",
                "prompt": _keyframe_prompt(production, shot),
            }
            upsert_asset(asset)
        job.output_asset_ids = [asset.id for asset in assets]
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Keyframe ready for S{shot.order:02d}. Review and approve it before video generation."
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        shot.keyframe_asset_id = assets[0].id
        shot.status = "draft"
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text=f"S{shot.order:02d} keyframe is ready. Review the composition, then approve the shot before generating the Veo take.",
        ))
        _save(production)
    except Exception as exc:
        logger.exception("Video production keyframe failed for %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"Keyframe generation failed: {exc}"[:500]
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        shot.status = "failed"
        _save(production)


def _audio_plan_from_payload(production: VideoProduction, payload: dict[str, object]) -> VideoProductionAudioPlan:
    raw_cues = payload.get("cue_sheet")
    cue_sheet: list[VideoProductionAudioCue] = []
    if isinstance(raw_cues, list):
        for item in raw_cues:
            if not isinstance(item, dict):
                continue
            try:
                start_seconds = max(0, float(item.get("start_seconds") or 0))
                end_seconds = min(float(item.get("end_seconds") or production.target_seconds), float(production.target_seconds))
            except (TypeError, ValueError):
                continue
            cue_sheet.append(VideoProductionAudioCue(
                shot_id=str(item.get("shot_id") or ""),
                start_seconds=start_seconds,
                end_seconds=max(start_seconds, end_seconds),
                purpose=str(item.get("purpose") or ""),
                music_direction=str(item.get("music_direction") or ""),
                sfx=_string_list(item, "sfx"),
            ))
    if not cue_sheet:
        cue_sheet = [VideoProductionAudioCue(
            shot_id=shot.id,
            start_seconds=shot.start_seconds,
            end_seconds=shot.start_seconds + shot.duration_seconds,
            purpose=shot.purpose,
            music_direction=shot.audio_cue or "Support the shot without masking dialogue or CTA.",
        ) for shot in production.shots]
    bpm_raw = payload.get("bpm")
    try:
        bpm = int(bpm_raw) if bpm_raw is not None else None
    except (TypeError, ValueError):
        bpm = None
    if bpm is not None and not 40 <= bpm <= 220:
        bpm = None
    default_prompt = (
        f"Instrumental commercial soundtrack for a {production.target_seconds}-second {production.aspect_ratio} ad. "
        "Modern, polished, brand-safe production music with a clear opening hook, light mid-section lift, and a clean final resolve. "
        "No vocals, lyrics, spoken words, artist imitation, copyrighted melody, or sound logos."
    )
    return VideoProductionAudioPlan(
        status="draft",
        music_prompt=str(payload.get("music_prompt") or default_prompt).strip(),
        bpm=bpm,
        intensity=str(payload.get("intensity") or "medium").strip(),
        instrumental=bool(payload.get("instrumental", True)),
        cue_sheet=cue_sheet,
        music_asset_ids=production.audio_plan.music_asset_ids,
        updated_at=datetime.utcnow(),
    )


def run_audio_producer(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    message = request.message.strip()
    if message:
        production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
    payload = _role_payload(
        production,
        instruction=message or "Create the first soundtrack blueprint from the approved script and shot cards.",
        include_asset_parts=False,
        role_prompt=(
            "You are the Audio Producer for an original commercial video. Work only from the approved script, design bible, shot cards, and conversation. "
            "Create a practical instrumental soundtrack blueprint that reinforces editing rhythm without masking dialogue, captions, CTA, or legal copy. "
            "Do not inspect media directly. Do not request vocals, speech, lyrics, a known song, a named artist, or a copyrighted melody. "
            "Return exactly: reply, music_prompt, bpm, intensity, instrumental, cue_sheet. "
            "music_prompt must be a 60-140 word English prompt for Lyria: instrumental only; include mood, tempo, instrumentation, energy changes, and a clean ending. "
            "cue_sheet must be an array of objects with shot_id, start_seconds, end_seconds, purpose, music_direction, sfx. "
            "SFX are editorial notes only; do not claim they will be generated by Lyria."
        ),
    )
    production.audio_plan = _audio_plan_from_payload(production, payload)
    production.stage = VideoProductionStage.edit
    reply = str(payload.get("reply") or "I prepared an instrumental soundtrack blueprint. Review the cue sheet, then generate a Lyria music preview for the edit.")
    production.conversation.append(VideoProductionConversationMessage(role="assistant", text=reply))
    return _save(production)


def _generate_lyria_music(prompt: str) -> bytes:
    settings = get_settings()
    if not settings.vertex_lyria_enabled:
        raise RuntimeError("Lyria music generation is disabled by VERTEX_LYRIA_ENABLED.")
    if not settings.gcp_project_id:
        raise RuntimeError("GCP_PROJECT_ID is required to generate a Lyria soundtrack.")
    credentials, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(GoogleAuthRequest())
    endpoint = (
        "https://aiplatform.googleapis.com/v1beta1/projects/"
        f"{quote(settings.gcp_project_id, safe='')}/locations/"
        f"{quote(settings.vertex_lyria_location, safe='')}/interactions"
    )
    request = UrlRequest(
        endpoint,
        data=json.dumps({
            "model": settings.vertex_lyria_model,
            "input": [{"type": "text", "text": prompt}],
        }).encode("utf-8"),
        headers={"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Lyria request failed ({exc.code}): {detail[:500]}") from exc
    outputs = payload.get("outputs") if isinstance(payload, dict) else None
    audio_output = next((
        item for item in outputs or []
        if isinstance(item, dict) and item.get("type") == "audio" and item.get("data")
    ), None)
    if not audio_output:
        raise RuntimeError("Lyria returned no playable audio output.")
    try:
        return base64.b64decode(str(audio_output["data"]))
    except (KeyError, ValueError) as exc:
        raise RuntimeError("Lyria returned invalid audio data.") from exc


def create_production_audio_job(production_id: str, user: User) -> GenerationJob:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    if not production.audio_plan.music_prompt.strip():
        raise ValueError("Create an Audio Producer blueprint before generating music.")
    now = datetime.utcnow()
    job = GenerationJob(
        job_id=f"job_{uuid4().hex[:12]}",
        workspace_id=production.workspace_id,
        status=JobStatus.running,
        progress=5,
        lineage_key=f"vprod_{uuid4().hex[:16]}",
        message="Preparing the approved soundtrack with Lyria…",
        tool_id="video-production-audio",
        title=f"{production.title} · soundtrack",
        created_at=now,
        updated_at=now,
    )
    JOBS[job.job_id] = job
    upsert_job(job)
    production.audio_plan.status = "generating"
    production.audio_plan.job_id = job.job_id
    production.audio_plan.updated_at = now
    production.stage = VideoProductionStage.edit
    _save(production)
    return job


async def run_production_audio_background(production_id: str, job_id: str, user: User) -> None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    job = JOBS.get(job_id)
    if not production or not job:
        return
    try:
        _mark_generation_progress(job, 20, "Generating the instrumental soundtrack with Lyria…")
        content = await asyncio.to_thread(_generate_lyria_music, production.audio_plan.music_prompt)
        _mark_generation_progress(job, 75, "Saving the soundtrack for the final edit…")
        asset_id = f"{job.lineage_key}_music"
        preview_url = _save_local_video_file(asset_id, content, ".mp3")
        object_path = _build_gcs_object_path(
            category="generated",
            workspace_id=production.workspace_id,
            created_at=job.created_at,
            job_id=job.job_id,
            filename=f"{asset_id}.mp3",
        )
        gcs_uri = _upload_bytes_to_gcs(content=content, object_path=object_path, content_type="audio/mpeg")
        asset = Asset(
            id=asset_id,
            title=f"{production.title}_soundtrack_v{len(production.audio_plan.music_asset_ids) + 1}",
            type="audio",
            gcs_uri=gcs_uri,
            preview_url=preview_url,
            provider="vertex-ai",
            model=get_settings().vertex_lyria_model,
            workspace_id=production.workspace_id,
            job_id=job.job_id,
            prompt_hash="",
            created_by=user.id,
            created_at=job.created_at,
            asset_role=AssetRole.generated,
            analysis={"video_production_id": production_id, "kind": "soundtrack", "music_prompt": production.audio_plan.music_prompt},
        )
        _record_asset_storage_status(asset, category="generated")
        ASSETS[asset.id] = asset
        upsert_asset(asset)
        production.audio_plan.status = "ready"
        production.audio_plan.music_asset_ids.append(asset.id)
        production.audio_plan.updated_at = datetime.utcnow()
        job.output_asset_ids = [asset.id]
        job.status = JobStatus.completed
        job.progress = 100
        job.message = "Soundtrack ready. Preview it in Edit, then render the final cut with music."
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text="The Audio Producer soundtrack is ready. Preview it in Edit, then render a final cut with music when you are happy with the pacing.",
        ))
        _save(production)
    except Exception as exc:
        logger.exception("Video production soundtrack failed for %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"Soundtrack generation failed: {exc}"[:500]
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        production.audio_plan.status = "failed"
        production.audio_plan.updated_at = datetime.utcnow()
        _save(production)


def _mix_audio_into_video(*, video_content: bytes, audio_content: bytes, target_seconds: int) -> bytes:
    settings = get_settings()
    ffmpeg_path = settings.playable_capture_ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg is required to mix the Lyria soundtrack into the final cut.")
    with tempfile.TemporaryDirectory(prefix="incept-production-mix-") as directory:
        root = Path(directory)
        video_path = root / "picture.mp4"
        audio_path = root / "music.mp3"
        output_path = root / "final.mp4"
        video_path.write_bytes(video_content)
        audio_path.write_bytes(audio_content)
        fade_start = max(target_seconds - 1, 0)
        command = [
            ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
            "-stream_loop", "-1", "-i", str(video_path),
            "-stream_loop", "-1", "-i", str(audio_path),
            "-filter_complex", f"[1:a]volume=0.45,afade=t=in:st=0:d=0.3,afade=t=out:st={fade_start}:d=1[a]",
            "-map", "0:v:0", "-map", "[a]", "-t", str(target_seconds),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output_path),
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode != 0 or not output_path.exists():
            detail = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"FFmpeg audio mix failed: {detail[:500]}")
        return output_path.read_bytes()


def create_production_render_job(production_id: str, user: User, *, include_audio: bool = False) -> GenerationJob:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    ready_shots = [shot for shot in production.shots if shot.status == "ready" and shot.video_asset_ids]
    if not ready_shots:
        raise ValueError("Generate at least one approved shot before assembling the first cut.")
    if include_audio and not production.audio_plan.music_asset_ids:
        raise ValueError("Generate a soundtrack with the Audio Producer before rendering a cut with music.")
    now = datetime.utcnow()
    job = GenerationJob(
        job_id=f"job_{uuid4().hex[:12]}",
        workspace_id=production.workspace_id,
        status=JobStatus.running,
        progress=5,
        lineage_key=f"vprod_{uuid4().hex[:16]}",
        message="Preparing the final production mix…" if include_audio else "Preparing the first production cut…",
        tool_id="video-production-edit",
        title=f"{production.title} · final mix" if include_audio else f"{production.title} · first cut",
        created_at=now,
        updated_at=now,
    )
    JOBS[job.job_id] = job
    upsert_job(job)
    production.render_job_id = job.job_id
    production.stage = VideoProductionStage.edit
    _save(production)
    return job


async def run_production_render_background(production_id: str, job_id: str, user: User, include_audio: bool = False) -> None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    job = JOBS.get(job_id)
    if not production or not job:
        return
    try:
        video_assets = [
            _asset_by_id(shot.video_asset_ids[0])
            for shot in sorted(production.shots, key=lambda item: item.order)
            if shot.status == "ready" and shot.video_asset_ids
        ]
        video_assets = [asset for asset in video_assets if asset and asset.type == "video"]
        clips = [_load_asset_bytes(asset) for asset in video_assets]
        clips = [clip for clip in clips if clip]
        if not clips:
            raise RuntimeError("No readable shot videos are available for the first cut.")
        _mark_generation_progress(job, 25, "Assembling approved shot takes in storyboard order…")
        content = _concat_video_sequence(clips=clips, target_seconds=production.target_seconds)
        if include_audio:
            soundtrack = _asset_by_id(production.audio_plan.music_asset_ids[-1])
            if not soundtrack or soundtrack.type != "audio":
                raise RuntimeError("The approved soundtrack is no longer available for mixing.")
            audio_content = _load_asset_bytes(soundtrack)
            if not audio_content:
                raise RuntimeError("The approved soundtrack could not be read for mixing.")
            _mark_generation_progress(job, 65, "Mixing the approved soundtrack into the final cut…")
            content = _mix_audio_into_video(
                video_content=content,
                audio_content=audio_content,
                target_seconds=production.target_seconds,
            )
        _mark_generation_progress(job, 82, "Saving the first production cut…")
        asset_id = f"{job.lineage_key}_final"
        width, height = _guess_video_dimensions(production.aspect_ratio, production.resolution)
        preview_url = _save_local_video_file(asset_id, content, ".mp4")
        object_path = _build_gcs_object_path(
            category="generated",
            workspace_id=production.workspace_id,
            created_at=job.created_at,
            job_id=job.job_id,
            filename=f"{asset_id}.mp4",
        )
        gcs_uri = _upload_bytes_to_gcs(content=content, object_path=object_path, content_type="video/mp4")
        parent = video_assets[0] if video_assets else None
        asset = Asset(
            id=asset_id,
            title=f"{production.title}_{'final_mix' if include_audio else 'first_cut'}",
            type="video",
            gcs_uri=gcs_uri,
            preview_url=preview_url,
            provider="ffmpeg",
            model="storyboard-final-mix" if include_audio else "storyboard-first-cut",
            workspace_id=production.workspace_id,
            job_id=job.job_id,
            prompt_hash="",
            created_by=user.id,
            created_at=job.created_at,
            width=width,
            height=height,
            asset_role=AssetRole.generated,
            analysis={
                "video_production_id": production_id,
                "kind": "final_mix" if include_audio else "first_cut",
                "shot_ids": [shot.id for shot in production.shots if shot.status == "ready" and shot.video_asset_ids],
                "transition": "hard_cut",
                "audio": "lyria soundtrack mixed" if include_audio else "not mixed",
            },
            parent_asset_id=parent.id if parent else None,
            root_asset_id=_inherit_root_asset_id(parent, asset_id),
        )
        _record_asset_storage_status(asset, category="generated")
        ASSETS[asset.id] = asset
        upsert_asset(asset)
        job.output_asset_ids = [asset.id]
        job.status = JobStatus.completed
        job.progress = 100
        job.message = "Final mix ready. Review the complete edit before delivery QA." if include_audio else "First cut ready. Review the edit before adding sound, captions, transitions, or final CTA treatment."
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        production.final_asset_id = asset.id
        production.stage = VideoProductionStage.deliver
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text="The final cut with the approved soundtrack is ready for delivery QA." if include_audio else "The first cut is ready. Review shot continuity before adding the final sound, caption, CTA, and QA passes.",
        ))
        _save(production)
    except Exception as exc:
        logger.exception("Video production first cut failed for %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"First-cut assembly failed: {exc}"[:500]
        job.updated_at = datetime.utcnow()
        upsert_job(job)


def create_shot_video_job(production_id: str, shot_id: str, user: User) -> GenerationJob:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    shot = next((item for item in production.shots if item.id == shot_id), None)
    if not shot:
        raise KeyError("Shot not found")
    if not shot.keyframe_asset_id:
        raise ValueError("Generate and approve a keyframe before producing this shot.")
    job = _production_job(production=production, shot=shot, kind="video")
    shot.video_job_id = job.job_id
    shot.status = "generating"
    _save(production)
    return job


async def run_shot_video_background(production_id: str, shot_id: str, job_id: str, user: User) -> None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    job = JOBS.get(job_id)
    if not production or not job:
        return
    shot = next((item for item in production.shots if item.id == shot_id), None)
    if not shot or not shot.keyframe_asset_id:
        return
    settings = get_settings()
    try:
        if not settings.vertex_veo_fast_model:
            raise RuntimeError("VERTEX_VEO_FAST_MODEL is not configured.")
        duration = 4 if shot.duration_seconds <= 4 else 6 if shot.duration_seconds <= 6 else 8
        request = VideoGenerationRequest(
            workspace_id=production.workspace_id,
            prompt=_veo_shot_prompt(production, shot),
            model=settings.vertex_veo_fast_model,
            created_by=user.id,
            source_asset_id=shot.keyframe_asset_id,
            video_generation_mode=VideoGenerationMode.image_to_video,
            aspect_ratio=production.aspect_ratio,
            duration_seconds=duration,
            resolution=production.resolution,
            variants=1,
        )
        _mark_generation_progress(job, 20, f"Sending approved S{shot.order:02d} keyframe to Veo Fast…")
        assets = await _execute_veo_request(job=job, request=request, user=user, model_id=settings.vertex_veo_fast_model)
        job.output_asset_ids = [asset.id for asset in assets]
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Veo take ready for S{shot.order:02d}."
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        shot.video_asset_ids = job.output_asset_ids
        shot.status = "ready"
        production.stage = VideoProductionStage.generate
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text=f"S{shot.order:02d} Veo take is ready. Review it in the production queue or replace the keyframe and regenerate only this shot.",
        ))
        _save(production)
    except Exception as exc:
        logger.exception("Video production Veo shot failed for %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"Shot generation failed: {exc}"[:500]
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        shot.status = "failed"
        _save(production)
