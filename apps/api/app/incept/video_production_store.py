"""Independent state for the Video Production Workspace.

This intentionally does not create CreativeThread records. A production is a
structured ad-making workspace with its own brief, script revisions, storyboard,
and shot-level delivery history.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import hashlib
import json
import logging
import math
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest

from app.incept.config import get_settings
from app.incept.datetime_utils import utcnow_naive
from app.incept.video_production_capabilities import (
    default_video_production_selection,
    validate_video_production_selection,
)
from app.incept.db import (
    delete_video_production as delete_video_production_row,
    load_video_production_events,
    load_video_productions,
    upsert_asset,
    upsert_job,
    upsert_video_production,
    upsert_video_production_event,
)
from app.incept.models import (
    Asset,
    AssetRole,
    GenerationJob,
    GenerationRequest,
    JobStatus,
    UsageEvent,
    User,
    VideoProduction,
    VideoProductionAgentRequest,
    VideoProductionAudioCue,
    VideoProductionAudioPlan,
    VideoProductionBridgeFrameRequest,
    VideoProductionAssetLink,
    VideoProductionBeat,
    VideoProductionConversationMessage,
    VideoProductionConfirmation,
    VideoProductionCopilotRequest,
    VideoProductionCopilotResponse,
    VideoProductionCreativeDirection,
    VideoProductionCreateRequest,
    VideoProductionDesignBible,
    VideoProductionDesignSheetCreateRequest,
    VideoProductionDesignSheet,
    VideoProductionDesignSheetUpdateRequest,
    VideoProductionEvent,
    VideoProductionEditPlan,
    VideoProductionTakeReview,
    VideoProductionSceneReframeRequest,
    VideoProductionScene,
    VideoProductionSetup,
    VideoProductionScript,
    VideoProductionScriptRevision,
    VideoProductionShot,
    VideoProductionShotCreateRequest,
    VideoProductionShotOrderRequest,
    VideoProductionShotUpdateRequest,
    VideoProductionStage,
    VideoProductionUpdateRequest,
    VideoProductionRevision,
    VideoGenerationMode,
    VideoGenerationRequest,
)
from app.incept.video_production_policy import (
    can_access_video_production,
    can_list_workspace_video_productions,
)
from app.incept.video_production_agents import (
    CREATIVE_STRATEGIST_PROMPT,
    PRODUCTION_DESIGNER_PROMPT,
    REFERENCE_VIDEO_ANALYST_PROMPT,
    SENIOR_SCREENWRITER_PROMPT,
    STORYBOARD_DIRECTOR_PROMPT,
    EDIT_REVIEWER_PROMPT,
    PRODUCTION_COPILOT_PROMPT,
    STORYBOARD_GENERATE_PROMPT,
)
from app.incept.video_production_contracts import (
    AssetContract,
    AssetContractItem,
    CharacterIdentity,
    CreativeContract,
    OutputSpec,
    ProductionContract,
    contract_validation_errors,
    script_asset_validation_errors,
)
from app.incept.store import (
    ASSETS,
    JOBS,
    SOURCE_ASSETS,
    USAGE_EVENTS,
    _record_usage,
    assert_image_budget_available,
    current_monthly_studio_spend_usd,
    monthly_budget_reset_message,
    _dispatch_generation,
    _export_master_images_to_assets,
    _build_gcs_object_path,
    _guess_content_type,
    _inherit_root_asset_id,
    _load_asset_bytes,
    _mark_generation_progress,
    _record_asset_storage_status,
    _save_image_file,
    _upload_bytes_to_gcs,
)
from app.incept.video_store import (
    _asset_part_for_text_model,
    _call_multimodal_text_model,
    _concat_video_sequence,
    _execute_veo_request,
    _guess_video_dimensions,
    _save_local_video_file,
    _record_video_usage,
    assert_video_budget_available,
)

logger = logging.getLogger(__name__)


class CopilotQuotaExceeded(RuntimeError):
    """Expected per-user safety limit; routers should return HTTP 429."""

VIDEO_PRODUCTIONS: dict[str, VideoProduction] = {}
# A user can press Enter again before a long model response returns. Serialize
# each production's conversation so a later user question never lands above
# the previous assistant reply.
_COPILOT_CONVERSATION_LOCKS: dict[str, threading.Lock] = {}
_COPILOT_CONVERSATION_LOCKS_GUARD = threading.Lock()
_COPILOT_CANCELLED: set[str] = set()


def _copilot_conversation_lock(production_id: str) -> threading.Lock:
    with _COPILOT_CONVERSATION_LOCKS_GUARD:
        return _COPILOT_CONVERSATION_LOCKS.setdefault(production_id, threading.Lock())


def cancel_production_copilot(production_id: str, user: User) -> None:
    """Discard an in-flight Copilot result before it can change Project State."""
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    _COPILOT_CANCELLED.add(production_id)


def _copilot_was_cancelled(production_id: str) -> bool:
    if production_id not in _COPILOT_CANCELLED:
        return False
    _COPILOT_CANCELLED.discard(production_id)
    return True


def _bootstrap() -> None:
    for row in load_video_productions():
        try:
            production = VideoProduction.model_validate(json.loads(row["payload_json"]))
            VIDEO_PRODUCTIONS[production.production_id] = production
        except Exception:
            logger.warning("Skipping unreadable video production", exc_info=True)
    recover_interrupted_video_production_jobs()


def recover_interrupted_video_production_jobs() -> list[str]:
    """Make request-scoped production jobs actionable after an API restart.

    FastAPI BackgroundTasks cannot survive a process boundary. Persisted jobs
    that were queued or running when that boundary occurred have no executor
    left, so leaving them in-progress would hide a permanent stall. This is a
    recovery marker, not an automatic re-run: the producer must review the
    retained project state and explicitly retry the exact operation.
    """
    recovered: list[str] = []
    for job in JOBS.values():
        if not job.tool_id.startswith("video-production-"):
            continue
        if job.status not in {JobStatus.queued, JobStatus.running}:
            continue
        job.status = JobStatus.failed
        job.progress = 0
        job.message = (
            "Interrupted by an API restart. Review the retained project inputs "
            "and retry this exact operation from the workspace. No output was selected or replaced."
        )
        job.updated_at = utcnow_naive()
        upsert_job(job)
        recovered.append(job.job_id)
    if recovered:
        logger.warning("Marked %d interrupted Video Production job(s) retryable after restart", len(recovered))
    return recovered


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


def _static_brand_asset_ids_for_roles(
    production: VideoProduction,
    roles: set[str],
) -> list[str]:
    """Return ordered static brand inputs that can condition an image Pack."""
    return list(dict.fromkeys(
        link.asset_id
        for link in production.asset_links
        if link.role in roles
        and (asset := _asset_by_id(link.asset_id))
        and asset.type in {"image", "gif"}
    ))


def _prop_pack_asset_ids(
    production: VideoProduction,
    asset_ids: list[str],
) -> list[str]:
    """Resolve a hero-product reference without borrowing people or media.

    Earlier productions stored product photography under the generic Brand role.
    Prefer explicit Product inputs, then use one static Brand image as a
    backwards-compatible fallback. Reference videos and character media are
    intentionally never eligible.
    """
    product_ids = _static_brand_asset_ids_for_roles(production, {"product"})
    legacy_brand_ids = _static_brand_asset_ids_for_roles(production, {"brand"})
    eligible_ids = set(product_ids + legacy_brand_ids)
    requested_ids = [asset_id for asset_id in asset_ids if asset_id in eligible_ids]
    return (requested_ids or product_ids or legacy_brand_ids)[:1]


def _filter_pack_asset_ids(
    production: VideoProduction,
    pack_type: str,
    asset_ids: list[str],
) -> list[str]:
    """Keep only asset IDs that may condition the requested visual Pack."""
    if pack_type == "prop":
        return _prop_pack_asset_ids(production, asset_ids)
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
        # A user-selected source is explicit intent. Never reinterpret it from
        # a production role (brand/logo/character) or replace it with a
        # fallback asset merely because the Pack has an old classification.
        if _is_user_authored_sheet(pack):
            pack.asset_ids = list(dict.fromkeys(
                asset_id for asset_id in pack.asset_ids
                if (asset := _asset_by_id(asset_id)) is not None and asset.type in {"image", "gif"}
            ))
            pack.scene_ids = list(dict.fromkeys(scene_id for scene_id in pack.scene_ids if scene_id in valid_scene_ids))
            pack.kind = "character_consistency" if pack.asset_pack_type == "character" else "scene_style"
            kept.append(pack)
            continue
        inferred_type = _infer_asset_pack_type(pack)
        if (
            pack.asset_pack_type == "environment"
            or pack.asset_pack_type not in _ASSET_PACK_TYPES
            or _has_explicit_pack_type_title(pack)
        ):
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
    # A deliberately named Pack is more reliable than a descriptive prompt.
    # "empty of characters" must never turn an Environment Pack into a
    # Character Pack.
    title = sheet.title.lower()
    if "transition" in title:
        return "transition"
    if "lighting" in title or "color card" in title:
        return "lighting"
    if "environment" in title:
        return "environment"
    if "prop" in title or "product" in title:
        return "prop"
    if "ui" in title:
        return "ui"
    if "character" in title or "mascot" in title:
        return "character"
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


def _has_explicit_pack_type_title(sheet: VideoProductionDesignSheet) -> bool:
    title = sheet.title.lower()
    return any(token in title for token in ("transition", "lighting", "color card", "environment", "prop", "product", "ui", "character", "mascot"))


def _split_duo_character_pack(sheet: VideoProductionDesignSheet) -> list[VideoProductionDesignSheet]:
    """Character identity is explicit in Asset Contract; never infer a split from prose."""
    return [sheet]


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
        if (
            pack.asset_pack_type == "environment"
            or pack.asset_pack_type not in _ASSET_PACK_TYPES
            or _has_explicit_pack_type_title(pack)
        ):
            pack.asset_pack_type = inferred_type  # type: ignore[assignment]
        pack.kind = "character_consistency" if pack.asset_pack_type == "character" else "scene_style"
        normalized.extend(_split_duo_character_pack(pack) if pack.asset_pack_type == "character" else [pack])

    normalized = _normalize_asset_packs(production, normalized)
    bible.asset_packs = normalized
    bible.character_consistency_sheets = [pack for pack in normalized if pack.asset_pack_type == "character"]
    bible.scene_style_sheets = [pack for pack in normalized if pack.asset_pack_type != "character"]


def _normalize_production(production: VideoProduction) -> VideoProduction:
    # Audio was an experimental optional stage. Existing projects should open
    # directly in Edit rather than being stranded on a hidden route.
    if production.stage == VideoProductionStage.audio:
        production.stage = VideoProductionStage.edit
    production.asset_links = [VideoProductionAssetLink.model_validate(link) for link in production.asset_links]
    production.creative_direction = VideoProductionCreativeDirection.model_validate(production.creative_direction)
    _normalize_handoff_keys(production)
    if not production.production_contract:
        production.production_contract = ProductionContract(
            output_spec=OutputSpec(
                duration_seconds=production.target_seconds,
                aspect_ratio=production.aspect_ratio,
                resolution="720x1280" if production.aspect_ratio == "9:16" and production.resolution == "720p" else production.resolution,
            ),
            output_language=production.creative_direction.output_language or "English",
        ).model_dump(mode="json")
    _normalize_ai_handoff_scopes(production)
    _hydrate_reference_frame_sources(production)
    production.script = VideoProductionScript.model_validate(production.script)
    # Legacy projects did not retain the source hash. Their currently saved
    # working copy is the only safe baseline until it is edited again.
    if not production.script.structured_raw_script_hash:
        production.script.structured_raw_script_hash = _script_hash(production.script.raw_script)
    production.video_setup = VideoProductionSetup.model_validate(production.video_setup)
    selection = production.video_setup.provider_selection
    if not any((item.provider or item.model) for item in (selection.text, selection.image, selection.video, selection.audio)):
        production.video_setup.provider_selection = default_video_production_selection()
    production.design_bible = VideoProductionDesignBible.model_validate(production.design_bible)
    _hydrate_asset_pack_inventory(production)
    # Generated images are usable library material by default. Backfill older
    # one-image Scene packs that were left in "ready" awaiting a redundant
    # manual Use-image click.
    for sheet in _all_design_sheets(production):
        if sheet.status == "ready" and sheet.grid_asset_id and not sheet.approved_asset_ids:
            sheet.selected_panel = 0
            sheet.selected_asset_id = sheet.grid_asset_id
            sheet.approved_panel_asset_ids = {"0": sheet.grid_asset_id}
            sheet.approved_asset_ids = [sheet.grid_asset_id]
            sheet.status = "approved"
    # Backfill failure context for productions created before failure_reason was
    # persisted on the Pack itself. Jobs are loaded from SQLite at process start.
    for sheet in _all_design_sheets(production):
        if sheet.status == "failed" and not sheet.failure_reason and sheet.job_id:
            job = JOBS.get(sheet.job_id)
            if job and job.message:
                sheet.failure_reason = job.message
    production.shots = [VideoProductionShot.model_validate(shot) for shot in production.shots]
    # A storyboard must never keep using a state from a Pack that was removed
    # or reset. Clear those stale bindings instead of silently sending them to
    # keyframe/video generation.
    active_state_ids = {
        asset_id
        for sheet in _all_design_sheets(production)
        for asset_id in [
            *sheet.approved_asset_ids,
            *sheet.approved_panel_asset_ids.values(),
            sheet.selected_asset_id,
        ]
        if asset_id
    }
    for shot in production.shots:
        if shot.character_state_asset_id not in active_state_ids:
            shot.character_state_asset_id = None
        if shot.environment_state_asset_id not in active_state_ids:
            shot.environment_state_asset_id = None
        if shot.transition_in_asset_id not in active_state_ids:
            shot.transition_in_asset_id = None
        if shot.transition_out_asset_id not in active_state_ids:
            shot.transition_out_asset_id = None
        shot.additional_character_state_asset_ids = [
            asset_id for asset_id in shot.additional_character_state_asset_ids if asset_id in active_state_ids
        ]
        shot.prop_ui_asset_ids = [
            asset_id for asset_id in shot.prop_ui_asset_ids if asset_id in active_state_ids
        ]
        # Keyframes may also be direct user uploads, so only clear a missing ID.
        if shot.keyframe_asset_id and not _asset_by_id(shot.keyframe_asset_id):
            shot.keyframe_asset_id = None
        if shot.end_keyframe_asset_id and not _asset_by_id(shot.end_keyframe_asset_id):
            shot.end_keyframe_asset_id = None
    production.audio_plan = VideoProductionAudioPlan.model_validate(production.audio_plan)
    production.conversation = [
        VideoProductionConversationMessage.model_validate(message) for message in production.conversation
    ]
    return production


def _save(
    production: VideoProduction,
    *,
    event_type: str = "project.saved",
    actor_user_id: str = "system",
    event_summary: str | None = None,
) -> VideoProduction:
    production = _normalize_production(production)
    _refresh_production_preflight(production)
    production.state_revision = max(1, production.state_revision + 1)
    production.revisions = [
        *production.revisions[-39:],
        VideoProductionRevision(
            revision=production.state_revision,
            label=production.branch_label or "Main",
            summary=_revision_summary(production),
        ),
    ]
    production.updated_at = utcnow_naive()
    VIDEO_PRODUCTIONS[production.production_id] = production
    upsert_video_production(production)
    upsert_video_production_event(
        VideoProductionEvent(
            event_id=f"vpe_{uuid4().hex}",
            production_id=production.production_id,
            workspace_id=production.workspace_id,
            event_type=event_type,
            summary=event_summary or _revision_summary(production),
            state_revision=production.state_revision,
            actor_user_id=actor_user_id,
            metadata={
                "stage": production.stage.value,
                "script_status": production.script.status,
                "storyboard_approved": bool(production.storyboard_approved_at),
            },
        )
    )
    return production


def _record_script_revision(
    production: VideoProduction,
    *,
    reason: str,
    actor_user_id: str,
) -> None:
    """Append a compact script checkpoint before the containing project save."""

    checkpoint = VideoProductionScriptRevision(
        revision=production.script.revision,
        status=production.script.status,
        reason=reason,
        actor_user_id=actor_user_id,
        raw_script=production.script.raw_script,
        scene_count=len(production.script.scenes),
        beat_count=len(production.script.beats),
        script=production.script.model_copy(deep=True),
    )
    previous = production.script_revisions[-1] if production.script_revisions else None
    if previous and previous.revision == checkpoint.revision and previous.status == checkpoint.status and previous.raw_script == checkpoint.raw_script:
        return
    production.script_revisions = [*production.script_revisions[-19:], checkpoint]


def restore_video_production_script_revision(
    production_id: str,
    revision_id: str,
    user: User,
) -> VideoProduction:
    """Restore one complete checkpoint as a new editable draft.

    A restore intentionally never makes an old checkpoint the current locked
    baseline in place. The restored content receives a new revision and clears
    downstream storyboard approval so a human reviews its consequences again.
    """

    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    checkpoint = next(
        (entry for entry in production.script_revisions if entry.revision_id == revision_id),
        None,
    )
    if checkpoint is None:
        raise KeyError("Script checkpoint not found")
    if checkpoint.script is None:
        raise ValueError("This legacy script receipt cannot be restored because it has no structured checkpoint.")
    restored = checkpoint.script.model_copy(deep=True)
    restored.revision = max(production.script.revision, checkpoint.revision) + 1
    restored.status = "draft"
    restored.updated_at = utcnow_naive()
    production.script = restored
    production.stage = VideoProductionStage.script
    _refresh_director_prompts_from_script(production)
    _invalidate_storyboard_approval(production)
    _record_script_revision(
        production,
        reason=f"Restored checkpoint r{checkpoint.revision}",
        actor_user_id=user.id,
    )
    return _save(
        production,
        event_type="script.checkpoint_restored",
        actor_user_id=user.id,
        event_summary=f"Restored script checkpoint r{checkpoint.revision} as an editable draft.",
    )


def _script_hash(raw_script: str) -> str:
    return hashlib.sha256((raw_script or "").encode("utf-8")).hexdigest()


def _production_model(production: VideoProduction, operation: str, fallback: str) -> str:
    """Resolve a persisted, server-validated project selection at execution time."""
    choice = getattr(production.video_setup.provider_selection, operation, None)
    selected = getattr(choice, "model", "") if choice else ""
    return selected.strip() or fallback


def _invalidate_storyboard_approval(production: VideoProduction) -> None:
    production.storyboard_approved_at = None
    production.storyboard_approved_revision = None


def _revision_summary(production: VideoProduction) -> str:
    """Compact audit text; the actual source of truth remains Project State."""
    return (
        f"{len(production.script.scenes)} script moments · "
        f"{len(production.design_bible.asset_packs)} visual assets · "
        f"{len(production.shots)} storyboard frames"
    )


def _shot_source_signature(shot: VideoProductionShot) -> str:
    """Only generation inputs belong in this signature, never Take outputs."""
    payload = {
        "start": shot.keyframe_asset_id,
        "end": shot.end_keyframe_asset_id,
        "bridge_source": shot.bridge_source_video_asset_id,
        "bridge_timestamp": shot.bridge_timestamp_seconds,
        "prompt": shot.veo_prompt,
        "camera": shot.camera,
        "action": shot.action,
        "continuity": shot.continuity,
        "duration": shot.generation_duration_seconds,
        "variants": shot.generation_variants,
        "mode": shot.generation_mode,
        "extend_source": shot.extend_source_video_asset_id,
        "transition": shot.recommended_transition_strategy,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _estimate_dialogue_seconds(text: str) -> float:
    """Conservative reading-time estimate for Timeline planning only."""
    clean = re.sub(r"\s+", "", text or "")
    if not clean:
        return 0.0
    cjk = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", clean))
    latin_words = len(re.findall(r"[A-Za-z0-9']+", text or ""))
    # Korean/CJK delivery is commonly 4–5 readable characters/sec; English
    # commercial VO is roughly 2.4 words/sec. Add a small performance buffer.
    return round((cjk / 4.2) + (latin_words / 2.4) + (0.25 if clean else 0), 2)


def _refresh_shot_preflight(shot: VideoProductionShot) -> None:
    dialogue_seconds = _estimate_dialogue_seconds(shot.dialogue_or_copy)
    shot.estimated_dialogue_seconds = dialogue_seconds or None
    shot.estimated_audio_seconds = max(dialogue_seconds, 0.6) if (dialogue_seconds or shot.audio_cue) else None
    if not shot.end_keyframe_asset_id:
        if shot.generation_mode == "first_last_frame":
            shot.generation_mode = "image_to_video"
        shot.motion_feasibility = "not_checked"
        shot.recommended_transition_strategy = "cut"
        shot.motion_risk_reasons = []
        return
    # An End Scene can be prepared for a later cut without forcing Veo to
    # interpolate toward it.  Only the user-selected first/last mode needs
    # feasibility review; preserving start-image mode avoids accidental
    # morphing merely because an editor attached a possible next visual.
    if shot.generation_mode != "first_last_frame":
        shot.motion_feasibility = "not_checked"
        shot.recommended_transition_strategy = "cut"
        shot.motion_risk_reasons = []
        return
    if shot.first_last_frame_status == "needs_intermediate":
        shot.motion_feasibility = "blocked"
        shot.recommended_transition_strategy = "bridge"
        shot.motion_risk_reasons = [shot.first_last_frame_note or "This start/end pair needs an intermediate bridge scene."]
    elif shot.first_last_frame_status == "ready":
        shot.motion_feasibility = "safe"
        shot.recommended_transition_strategy = "continuous"
        shot.motion_risk_reasons = []
    else:
        shot.motion_feasibility = "review"
        shot.recommended_transition_strategy = "match_cut"
        shot.motion_risk_reasons = ["Generate or refresh the Director Prompt so it can evaluate this exact start/end pair."]


def _refresh_production_preflight(production: VideoProduction) -> None:
    for shot in production.shots:
        previous_signature = shot.source_signature
        shot.source_signature = _shot_source_signature(shot)
        if shot.video_asset_ids and shot.take_source_signature and shot.take_source_signature != shot.source_signature:
            shot.take_outdated = True
        # Old records have no signature. Their Take is still usable; do not
        # retroactively mark it stale just because this feature was added.
        if not previous_signature and shot.video_asset_ids and not shot.take_source_signature:
            shot.take_source_signature = shot.source_signature
        _refresh_shot_preflight(shot)


def _assert_owner(production: VideoProduction, user: User) -> None:
    if not can_access_video_production(owner_id=production.created_by, user=user):
        raise PermissionError("This video production is not available to the current user.")


def list_video_productions(
    workspace_id: str,
    user: User,
    *,
    scope: str = "mine",
    include_archived: bool = False,
) -> list[VideoProduction]:
    normalized_scope = (scope or "mine").strip().lower()
    if normalized_scope == "all" and not can_list_workspace_video_productions(user):
        raise PermissionError("Only workspace operators can view every video production in a workspace.")
    values = [
        _normalize_production(production)
        for production in VIDEO_PRODUCTIONS.values()
        if production.workspace_id == workspace_id
    ]
    if normalized_scope != "all":
        values = [production for production in values if production.created_by == user.id]
    if not include_archived:
        values = [production for production in values if production.archived_at is None]
    return sorted(values, key=lambda item: item.updated_at, reverse=True)


def get_video_production(production_id: str, user: User) -> VideoProduction | None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    if production:
        production = _normalize_production(production)
        VIDEO_PRODUCTIONS[production.production_id] = production
        _assert_owner(production, user)
    return production


def list_video_production_events(
    production_id: str,
    user: User,
    *,
    limit: int = 40,
) -> list[VideoProductionEvent]:
    """Read the durable transition receipts after normal project authorization.

    Events are never globally enumerable: a caller must be allowed to read the
    production before any actor, timing, or state metadata is returned.
    """
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    values: list[VideoProductionEvent] = []
    for row in load_video_production_events(production_id, limit):
        try:
            values.append(VideoProductionEvent.model_validate({
                **row,
                "metadata": json.loads(row.get("metadata_json") or "{}"),
            }))
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Skipping unreadable Video Production event %s", row.get("event_id"))
    return values


def create_video_production(request: VideoProductionCreateRequest, user: User) -> VideoProduction:
    video_setup = VideoProductionSetup.model_validate(request.video_setup or VideoProductionSetup())
    video_setup.provider_selection = validate_video_production_selection(video_setup.provider_selection)
    production = VideoProduction(
        production_id=f"vprod_{uuid4().hex[:12]}",
        workspace_id=request.workspace_id,
        created_by=user.id,
        title=request.title.strip() or "Untitled video",
        brief=request.brief.strip(),
        target_seconds=request.target_seconds,
        aspect_ratio=request.aspect_ratio,
        resolution=request.resolution,
        video_setup=video_setup,
    )
    production.conversation.append(
        VideoProductionConversationMessage(
            role="assistant",
            text="I’m your Production Copilot. Upload a reference or describe the video you want to make. I’ll first clarify anything essential, then help you build the plan, assets, storyboard, takes, and edit in one shared project state.",
        )
    )
    return _save(
        production,
        event_type="project.created",
        actor_user_id=user.id,
        event_summary="Project created from reviewed intake.",
    )


def update_video_production(
    production_id: str,
    request: VideoProductionUpdateRequest,
    user: User,
) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    values = request.model_dump(exclude_unset=True)
    expected_revision = values.pop("expected_revision", None)
    if expected_revision is not None and expected_revision != production.state_revision:
        raise ValueError(
            "This project changed in another view. Refresh it before saving so no confirmed work is overwritten."
        )
    invalidates_storyboard = bool(
        {"script", "design_bible", "asset_links", "reference_asset_ids"} & values.keys()
    )
    script_was_updated = False
    for field, value in values.items():
        if field == "asset_links" and value is not None:
            value = [VideoProductionAssetLink.model_validate(link) for link in value]
        elif field == "creative_direction" and value is not None:
            value = VideoProductionCreativeDirection.model_validate(value)
        elif field == "script" and value is not None:
            value = VideoProductionScript.model_validate(value)
            script_was_updated = True
        elif field == "video_setup" and value is not None:
            value = VideoProductionSetup.model_validate(value)
            value.provider_selection = validate_video_production_selection(value.provider_selection)
        elif field == "design_bible" and value is not None:
            value = VideoProductionDesignBible.model_validate(value)
        elif field == "audio_plan" and value is not None:
            value = VideoProductionAudioPlan.model_validate(value)
        elif field == "edit_plan" and value is not None:
            value = VideoProductionEditPlan.model_validate(value)
        setattr(production, field, value)
    if script_was_updated:
        _record_script_revision(
            production,
            reason="Manual working-script save",
            actor_user_id=user.id,
        )
    if invalidates_storyboard:
        _invalidate_storyboard_approval(production)
    return _save(
        production,
        event_type="project.updated",
        actor_user_id=user.id,
        event_summary="Project settings or production state saved.",
    )


def fork_video_production(production_id: str, label: str, user: User) -> VideoProduction:
    """Fork Project State without deleting or mutating the original production."""
    source = get_video_production(production_id, user)
    if not source:
        raise KeyError("Video production not found")
    clone = source.model_copy(deep=True)
    clone.production_id = f"vprod_{uuid4().hex[:12]}"
    clone.title = f"{source.title} · {label.strip() or 'Variant'}"
    clone.parent_production_id = source.production_id
    clone.branch_label = label.strip() or "Variant"
    clone.state_revision = 0
    clone.render_job_id = None
    clone.final_asset_id = None
    clone.pending_confirmation = None
    clone.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text=f"Created branch ‘{clone.branch_label}’. Existing assets and generated Takes remain available; changes here will not overwrite the original production.",
    ))
    return _save(
        clone,
        event_type="project.forked",
        actor_user_id=user.id,
        event_summary=f"Created a safe variant from {source.production_id}.",
    )


def _copilot_requires_confirmation(message: str) -> bool:
    """Only changes that can replace established work need an explicit choice."""
    lower = message.lower()
    return any(token in lower for token in (
        "replace all", "rewrite all", "change every", "new direction", "start over", "delete",
        "全部替换", "全部重写", "重写全部", "换方向", "重新开始", "删除",
    ))


_COPILOT_TOOL_NAMES = {
    "creative_direction",
    "script",
    "design",
    "director_prompts",
    "review_takes",
    "storyboard_generate",
}


def _copilot_project_state(production: VideoProduction) -> dict[str, object]:
    """Compact durable context for intent routing; page navigation is excluded."""
    assets = []
    for link in production.asset_links[:24]:
        asset = _asset_by_id(link.asset_id)
        assets.append({
            "id": link.asset_id,
            "title": asset.title if asset else link.asset_id,
            "type": asset.type if asset else "unknown",
            "project_role": link.role,
        })
    return {
        "title": production.title,
        "brief": production.brief,
        "output": {
            "duration_seconds": production.target_seconds,
            "aspect_ratio": production.aspect_ratio,
            "resolution": production.resolution,
        },
        "assets": assets,
        "script": {
            "status": production.script.status if production.script else "missing",
            "scene_count": len(production.script.scenes) if production.script else 0,
            "scene_titles": [scene.title for scene in (production.script.scenes if production.script else [])[:16]],
        },
        "storyboard": {
            "frame_count": len(production.shots),
            "frames": [shot.title for shot in production.shots[:16]],
        },
    }


def _copilot_intent(production: VideoProduction, message: str, attachment_ids: list[str] | None = None) -> dict[str, object]:
    """Use Gemini to choose an action. Never let the visible page select an agent."""
    router_prompt = (
        f"{PRODUCTION_COPILOT_PROMPT}\n\n"
        "<router_role>You are an intent router for the same Copilot. Do not use the current UI page as a signal. "
        "Understand the user's latest message and choose the smallest safe next action.</router_role>\n"
        "<tools>\n"
        "creative_direction: analyze a brief/reference and create or revise the production direction.\n"
        "script: create or revise the working screenplay.\n"
        "design: create or revise reusable visual asset requirements.\n"
        "director_prompts: create or revise per-frame Director Veo prompts from an existing script/storyboard.\n"
        "review_takes: review generated video takes and prepare edit guidance.\n"
        "storyboard_generate: produce one English prompt for a 16:9 colored 3x4, 12-panel storyboard-sheet image.\n"
        "</tools>\n"
        "<rules>\n"
        "For greetings, capability questions, factual questions, or advice, return kind=chat and reply in the user's latest language.\n"
        "If a required creative detail is missing, return kind=clarification with one concise question in the user's latest language.\n"
        "Use kind=tool only for a clear request to create, revise, generate, or review project work.\n"
        "Set requires_confirmation=true only before a major script rewrite, style pivot, delete, restart, or a change likely to invalidate established work.\n"
        "Do not request confirmation for ordinary questions, greetings, or a first draft.\n"
        "</rules>\n"
        "<response_format>Return ONLY valid JSON: {\"kind\":\"chat|clarification|tool\",\"reply\":\"...\",\"tool_name\":\"one tool name or null\",\"requires_confirmation\":true|false,\"confirmation_question\":\"...\",\"confirmation_reason\":\"...\"}.</response_format>\n"
        "<project_state>" + _safe_json(_copilot_project_state(production)) + "</project_state>\n"
        "<message_attachment_ids>" + _safe_json(attachment_ids or []) + "</message_attachment_ids>\n"
        "<user_message>" + message + "</user_message>"
    )
    try:
        response = _call_multimodal_text_model(
            prompt=router_prompt,
            # Key elements are project-scoped attachments, not merely file
            # names. Give the Copilot the actual image/video inputs so it can
            # answer about what the user just added and choose the right tool.
            parts=_asset_parts(production),
            model_id=_production_model(production, "text", get_settings().vertex_video_analysis_model),
            json_response=True,
        )
        payload = _parse_json(response)
    except Exception:
        logger.warning("Copilot intent routing unavailable", exc_info=True)
        payload = {}

    kind = str(payload.get("kind") or "chat").strip().lower()
    tool_name = str(payload.get("tool_name") or "").strip()
    if kind not in {"chat", "clarification", "tool"}:
        kind = "chat"
    if kind == "tool" and tool_name not in _COPILOT_TOOL_NAMES:
        kind, tool_name = "chat", ""
    reply = str(payload.get("reply") or "").strip()
    if not reply:
        reply = "I can help with the video. Tell me what you would like to create or change."
    return {
        "kind": kind,
        "reply": reply,
        "tool_name": tool_name or None,
        "requires_confirmation": bool(payload.get("requires_confirmation")) or _copilot_requires_confirmation(message),
        "confirmation_question": str(payload.get("confirmation_question") or "Review this change before applying it?"),
        "confirmation_reason": str(payload.get("confirmation_reason") or "It may affect existing creative work."),
    }


def _run_storyboard_generate_skill(production_id: str, message: str, user: User) -> VideoProduction:
    """Run the narrow storyboard-sheet skill exactly as specified: prompt output only."""
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    prompt = (
        f"{PRODUCTION_COPILOT_PROMPT}\n\n<active_skill>\n{STORYBOARD_GENERATE_PROMPT}\n</active_skill>\n"
        "<instruction>Return one English image-generation prompt only. Do not add an introduction, JSON, or Markdown.</instruction>\n"
        "<script>" + (production.script.raw_script if production.script and production.script.raw_script else production.brief) + "</script>\n"
        "<user_request>" + message + "</user_request>"
    )
    try:
        generated_prompt = _call_multimodal_text_model(
            prompt=prompt,
            parts=_asset_parts(production),
            model_id=_production_model(production, "text", get_settings().vertex_video_analysis_model),
            json_response=False,
        ).strip()
    except Exception as exc:
        logger.warning("Storyboard generate skill unavailable", exc_info=True)
        raise RuntimeError("Storyboard prompt generation failed. No existing work was changed; please try again.") from exc
    production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
    production.conversation.append(VideoProductionConversationMessage(role="assistant", text=generated_prompt))
    return _save(
        production,
        event_type="copilot.storyboard_prompt",
        actor_user_id=user.id,
        event_summary="Storyboard prompt prepared for human review; no media was generated.",
    )


def _dispatch_copilot_tool(production_id: str, tool_name: str, message: str, user: User) -> VideoProduction:
    request = VideoProductionAgentRequest(message=message)
    if tool_name == "creative_direction":
        return run_creative_director(production_id, request, user)
    if tool_name == "script":
        return run_script_agent(production_id, request, user)
    if tool_name == "design":
        return run_production_designer(production_id, request, user)
    if tool_name == "director_prompts":
        return run_director_agent(production_id, request, user)
    if tool_name == "review_takes":
        return run_edit_reviewer(production_id, request, user)
    if tool_name == "storyboard_generate":
        return _run_storyboard_generate_skill(production_id, message, user)
    raise ValueError("Unsupported Copilot tool")


def _run_production_copilot_serial(
    production_id: str,
    request: VideoProductionCopilotRequest,
    user: User,
) -> VideoProductionCopilotResponse:
    """Single conversational entry point; legacy specialists remain internal skills.

    The function deliberately does not guess missing goals, markets, or a
    high-impact scope. It records a confirmation card and returns without
    touching the working result until the user chooses.
    """
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    message = request.message.strip()
    attachment_ids = list(dict.fromkeys(
        asset_id for asset_id in request.asset_ids
        if _asset_by_id(asset_id) and any(link.asset_id == asset_id for link in production.asset_links)
    ))
    forced_tool: str | None = None
    decision: dict[str, object] | None = None
    if request.confirm_action_id and production.pending_confirmation and request.confirm_action_id == production.pending_confirmation.id:
        message = production.pending_confirmation.proposed_action or message
        candidate = production.pending_confirmation.stage
        forced_tool = candidate if candidate in _COPILOT_TOOL_NAMES else None
        production.pending_confirmation = None
    else:
        decision = _copilot_intent(production, message, attachment_ids)
        if _copilot_was_cancelled(production_id):
            return VideoProductionCopilotResponse(production=production)
        if decision["kind"] in {"chat", "clarification"}:
            production.conversation.append(VideoProductionConversationMessage(role="user", text=message, asset_ids=attachment_ids))
            production.conversation.append(VideoProductionConversationMessage(role="assistant", text=str(decision["reply"])))
            return VideoProductionCopilotResponse(
                production=_save(production),
                needs_confirmation=False,
                clarification_questions=[str(decision["reply"])] if decision["kind"] == "clarification" else [],
            )
        if decision["requires_confirmation"]:
            production.conversation.append(VideoProductionConversationMessage(role="user", text=message, asset_ids=attachment_ids))
            production.pending_confirmation = VideoProductionConfirmation(
                question=str(decision["confirmation_question"]),
                reason=str(decision["confirmation_reason"]),
                proposed_action=message,
                stage=str(decision["tool_name"]),
                choices=[],
            )
            production.conversation.append(VideoProductionConversationMessage(
                role="assistant",
                text=str(decision["reply"]),
            ))
            return VideoProductionCopilotResponse(
                production=_save(production), needs_confirmation=True,
            )
    if forced_tool:
        result = _dispatch_copilot_tool(production_id, forced_tool, message, user)
    else:
        # The visible page is deliberately irrelevant. Gemini selects a narrow,
        # explicit internal tool from the user's request and Project State.
        decision = decision or _copilot_intent(production, message, attachment_ids)
        if decision["kind"] != "tool" or not decision["tool_name"]:
            production.conversation.append(VideoProductionConversationMessage(role="user", text=message, asset_ids=attachment_ids))
            production.conversation.append(VideoProductionConversationMessage(role="assistant", text=str(decision["reply"])))
            return VideoProductionCopilotResponse(production=_save(production))
        result = _dispatch_copilot_tool(production_id, str(decision["tool_name"]), message, user)
    if attachment_ids:
        # Existing specialist tools own their conversation wording. Tag their
        # just-written user turn with this message's selected attachments.
        for turn in reversed(result.conversation):
            if turn.role == "user" and turn.text == message:
                turn.asset_ids = attachment_ids
                result = _save(result)
                break
    return VideoProductionCopilotResponse(production=result)


def run_production_copilot(
    production_id: str,
    request: VideoProductionCopilotRequest,
    user: User,
) -> VideoProductionCopilotResponse:
    """Serialize each visible conversation into strict user/assistant turns."""
    settings = get_settings()
    message = request.message.strip()
    if len(message) > settings.studio_copilot_max_message_chars:
        raise ValueError(
            f"Copilot messages are limited to {settings.studio_copilot_max_message_chars:,} characters. "
            "Please shorten the request or attach the asset instead."
        )
    now = utcnow_naive()
    minute_ago = now.timestamp() - 60
    recent_requests = [
        event for event in USAGE_EVENTS.values()
        if event.user_id == user.id
        and event.operation == "copilot"
        and event.created_at.timestamp() >= minute_ago
    ]
    if len(recent_requests) >= max(1, settings.studio_copilot_requests_per_minute):
        raise CopilotQuotaExceeded("Copilot rate limit reached. Please wait a minute before sending another message.")
    estimated_input_tokens = max(1, math.ceil(len(message) / 4)) + (1000 * len(request.asset_ids))
    # Reserve a bounded completion estimate for usage audit and optional
    # finance-approved dollar pricing. It is not a daily token limit.
    reserved_output_tokens = 4096
    token_total = estimated_input_tokens + reserved_output_tokens
    estimated_cost = round(
        token_total / 1000 * max(0.0, settings.studio_copilot_estimated_cost_per_1k_tokens_usd), 6
    )
    budget_limit = max(0.0, settings.studio_user_budget_usd)
    if budget_limit and current_monthly_studio_spend_usd(user) + estimated_cost > budget_limit:
        raise CopilotQuotaExceeded(monthly_budget_reset_message(budget_limit))
    with _copilot_conversation_lock(production_id):
        _COPILOT_CANCELLED.discard(production_id)
        response = _run_production_copilot_serial(production_id, request, user)
    event = UsageEvent(
        id=f"use_{uuid4().hex[:12]}",
        job_id="",
        workspace_id=response.production.workspace_id,
        user_id=user.id,
        user_email=user.email,
        provider="gemini",
        model=_production_model(response.production, "text", settings.vertex_video_analysis_model),
        operation="copilot",
        prompt_hash="",
        variants=1,
        output_size_count=0,
        output_format="text",
        estimated_provider_generations=1,
        output_asset_count=0,
        estimated_cost_usd=estimated_cost,
        input_tokens=estimated_input_tokens,
        output_tokens=reserved_output_tokens,
        created_at=now,
    )
    USAGE_EVENTS[event.id] = event
    from app.incept.db import upsert_usage_event
    upsert_usage_event(event)
    return response


def delete_video_production(production_id: str, user: User) -> None:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    _assert_owner(production, user)
    VIDEO_PRODUCTIONS.pop(production_id, None)
    delete_video_production_row(production_id)


def archive_video_production(production_id: str, user: User) -> VideoProduction:
    """Hide a project from the active library without destroying its lineage."""
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    _assert_owner(production, user)
    if production.archived_at is not None:
        return production
    production.archived_at = utcnow_naive()
    production.archived_by = user.id
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text="This production was archived. Its source assets, decisions, and delivery history are retained and can be restored.",
    ))
    return _save(
        production,
        event_type="project.archived",
        actor_user_id=user.id,
        event_summary="Project archived; production lineage remains available for restore.",
    )


def restore_video_production(production_id: str, user: User) -> VideoProduction:
    """Return an archived project to the active library without changing work."""
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    _assert_owner(production, user)
    if production.archived_at is None:
        return production
    production.archived_at = None
    production.archived_by = None
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text="This production was restored to the active library. No production decisions were changed.",
    ))
    return _save(
        production,
        event_type="project.restored",
        actor_user_id=user.id,
        event_summary="Archived project restored without changing production decisions.",
    )


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
    if not normalized:
        raise ValueError("Screenwriter returned no valid timed beats. The previous script was kept; please try again.")
    return normalized


def _timecode(seconds: float) -> str:
    total_seconds = max(0, round(seconds))
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def _format_working_script(
    production: VideoProduction,
    scenes: list[VideoProductionScene],
    beats: list[VideoProductionBeat],
    instruction: str,
) -> str:
    """Render the human-facing script deterministically from the scene contract.

    The Screenwriter returns one source of truth (`scenes[]`). Deriving the
    readable script here prevents a second model-written version from drifting
    away from the fields later used by Design, Storyboard, and the Director.
    """
    # Direction may have been written in another language earlier. The current
    # Screenwriter request owns the presentation language of Working Script.
    language = _response_language_hint(production, instruction).lower()
    chinese = "chinese" in language or language.startswith("zh") or "中文" in language
    labels = (
        ("场景", "画面与动作", "镜头", "台词", "字幕", "声音", "连续性", "限制")
        if chinese
        else ("Scene", "Visual action", "Camera", "Dialogue", "On-screen text", "Sound", "Continuity", "Restrictions")
    )
    none = "无" if chinese else "None"
    blocks: list[str] = []
    for index, scene in enumerate(scenes):
        beat = beats[index] if index < len(beats) else None
        start = _timecode(beat.start_seconds) if beat else _timecode(index * production.target_seconds / max(len(scenes), 1))
        end = _timecode(beat.end_seconds) if beat else _timecode((index + 1) * production.target_seconds / max(len(scenes), 1))
        dialogue = "；".join(
            " ".join(part for part in [
                f"({line.speaker})",
                f"[{line.voice_description}]" if line.voice_description else "",
                f"[{line.delivery}]" if line.delivery else "",
                f"\"{line.text}\"",
            ] if part)
            for line in scene.dialogue
        ) or none
        on_screen_text = "；".join(scene.on_screen_text) or none
        restrictions = "；".join(scene.restrictions) or none
        blocks.append(
            f"[{start} - {end}]\n"
            f"{scene.title}\n"
            f"{labels[0]}：{scene.setting}\n"
            f"{labels[1]}：{scene.action}\n"
            f"{labels[2]}：{scene.camera_direction}\n"
            f"{labels[3]}：{dialogue}\n"
            f"{labels[4]}：{on_screen_text}\n"
            f"{labels[5]}：{scene.sound_direction}\n"
            f"{labels[6]}：{scene.continuity_notes}\n"
            f"{labels[7]}：{restrictions}"
        )
    return "\n\n".join(blocks)


def _script_from_payload(production: VideoProduction, payload: dict[str, object], instruction: str) -> VideoProductionScript:
    raw_beats = payload.get("beats") if isinstance(payload.get("beats"), list) else []
    raw_scenes = payload.get("scenes") if isinstance(payload.get("scenes"), list) else []
    if not raw_beats or not raw_scenes:
        raise ValueError("Screenwriter returned no complete beat sheet and scene list. The previous script was kept; please try again.")
    beats: list[VideoProductionBeat] = []
    for index, item in enumerate(raw_beats):
        if not isinstance(item, dict):
            continue
        try:
            beats.append(VideoProductionBeat(
                start_seconds=float(item.get("start_seconds", index * (production.target_seconds / max(len(raw_beats), 1)))),
                end_seconds=float(item.get("end_seconds", (index + 1) * (production.target_seconds / max(len(raw_beats), 1)))),
                title=str(item.get("title") or "").strip(),
                purpose=str(item.get("purpose") or "").strip(),
            ))
        except (TypeError, ValueError):
            continue
    scenes: list[VideoProductionScene] = []
    for index, item in enumerate(raw_scenes):
        if not isinstance(item, dict):
            continue
        scenes.append(VideoProductionScene(
            id=str(item.get("id") or f"scene_{index + 1}"),
            title=str(item.get("title") or "").strip(),
            setting=str(item.get("setting") or ""),
            action=str(item.get("action") or ""),
            dialogue_or_copy=str(item.get("dialogue_or_copy") or ""),
            spoken_language=str(item.get("spoken_language") or ""),
            dialogue=[
                {
                    "speaker": str(line.get("speaker") or ""),
                    "text": str(line.get("text") or ""),
                    "on_camera": bool(line.get("on_camera", True)),
                    "voice_description": str(line.get("voice_description") or ""),
                    "delivery": str(line.get("delivery") or ""),
                }
                for line in item.get("dialogue", [])
                if isinstance(line, dict) and str(line.get("text") or "").strip()
            ] if isinstance(item.get("dialogue"), list) else [],
            on_screen_text=[str(text) for text in item.get("on_screen_text", []) if str(text).strip()] if isinstance(item.get("on_screen_text"), list) else [],
            camera_direction=str(item.get("camera_direction") or ""),
            sound_direction=str(item.get("sound_direction") or ""),
            continuity_notes=str(item.get("continuity_notes") or ""),
            restrictions=[str(rule) for rule in item.get("restrictions", []) if str(rule).strip()] if isinstance(item.get("restrictions"), list) else [],
            character_keys=[str(key) for key in item.get("character_keys", []) if str(key)] if isinstance(item.get("character_keys"), list) else [],
            environment_key=str(item.get("environment_key") or ""),
            prop_keys=[str(key) for key in item.get("prop_keys", []) if str(key)] if isinstance(item.get("prop_keys"), list) else [],
            ui_keys=[str(key) for key in item.get("ui_keys", []) if str(key)] if isinstance(item.get("ui_keys"), list) else [],
        ))
    placeholders = {"hook", "brand close", "product proof", "advance the commercial story."}
    if not beats or not scenes or any(not beat.title or not beat.purpose for beat in beats):
        raise ValueError("Screenwriter returned incomplete beats. The previous script was kept; please try again.")
    if all(beat.title.lower() in placeholders or beat.title.lower().startswith("product proof") for beat in beats):
        raise ValueError("Screenwriter returned generic placeholder beats. The previous script was kept; please try again.")
    if any(
        not scene.title
        or not scene.setting
        or not scene.action
        or not scene.camera_direction
        or not scene.sound_direction
        or not scene.continuity_notes
        for scene in scenes
    ):
        raise ValueError("Screenwriter returned incomplete scene detail. The previous script was kept; please try again.")
    list_value = lambda key, fallback_value: _string_list(payload, key, fallback_value)
    normalised_scenes = _bind_script_scenes_to_contract(production, scenes)
    raw_script = _format_working_script(production, normalised_scenes, beats, instruction)
    return VideoProductionScript(
        revision=production.script.revision + 1,
        status="draft",
        creative_goal=str(payload.get("creative_goal") or production.brief),
        audience=str(payload.get("audience") or ""),
        logline=str(payload.get("logline") or ""),
        style_bible=list_value("style_bible", []),
        beats=_normalize_script_beats(production, beats),
        scenes=normalised_scenes,
        brand_rules=list_value("brand_rules", []),
        asset_manifest=_asset_manifest_display(payload, []),
        risks=list_value("risks", []),
        raw_script=raw_script,
        structured_raw_script_hash=_script_hash(raw_script),
    )


def _bind_script_scenes_to_contract(
    production: VideoProduction,
    scenes: list[VideoProductionScene],
) -> list[VideoProductionScene]:
    """Repair missing model bindings using only approved Asset Contract keys.

    This is not a licence to invent visuals: it filters unknown model-provided
    keys and supplies the smallest reusable contract set when the model omits
    structured bindings altogether. The Script remains explicit and lockable.
    """
    try:
        contract = AssetContract.model_validate(production.asset_contract)
    except Exception:
        return scenes
    confirmed_keys = _confirmed_asset_keys(production)
    if confirmed_keys:
        contract = AssetContract(assets=[asset for asset in contract.assets if asset.asset_key in confirmed_keys])
    keys_by_type: dict[str, list[str]] = {}
    known = {item.asset_key for item in contract.assets}
    for asset in contract.assets:
        keys_by_type.setdefault(asset.asset_type, []).append(asset.asset_key)
    characters = keys_by_type.get("character", [])
    environments = keys_by_type.get("environment", [])
    props = keys_by_type.get("prop", [])
    ui = keys_by_type.get("ui", [])
    for index, scene in enumerate(scenes):
        scene.character_keys = [key for key in scene.character_keys if key in known]
        scene.prop_keys = [key for key in scene.prop_keys if key in known]
        scene.ui_keys = [key for key in scene.ui_keys if key in known]
        if scene.environment_key not in known:
            scene.environment_key = ""
        if not scene.character_keys and characters:
            scene.character_keys = characters[:2]
        if not scene.environment_key and environments:
            scene.environment_key = environments[0]
        scene_text = f"{scene.title} {scene.setting} {scene.action} {scene.dialogue_or_copy}".lower()
        if not scene.prop_keys and props and (index < len(scenes) - 1 or "flower" in scene_text or "phone" in scene_text or "product" in scene_text):
            scene.prop_keys = props[:1]
        if not scene.ui_keys and ui and (index == len(scenes) - 1 or any(term in scene_text for term in ("app", "game", "screen", "cta", "download", "end card"))):
            scene.ui_keys = ui[:1]
        # An abstract/end-card-only production may have no character or
        # environment. Bind its first approved contract state rather than
        # leaving a structurally empty scene.
        if not any([scene.character_keys, scene.environment_key, scene.prop_keys, scene.ui_keys]) and contract.assets:
            fallback_asset = contract.assets[0]
            if fallback_asset.asset_type == "character": scene.character_keys = [fallback_asset.asset_key]
            elif fallback_asset.asset_type == "environment": scene.environment_key = fallback_asset.asset_key
            elif fallback_asset.asset_type == "prop": scene.prop_keys = [fallback_asset.asset_key]
            else: scene.ui_keys = [fallback_asset.asset_key]
    return scenes


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
    include_contracts: bool = True,
    parts_override: list[object] | None = None,
    stage_context: str = "",
    language_policy: str | None = None,
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
        response = _call_multimodal_text_model(
            prompt=(
                f"{PRODUCTION_COPILOT_PROMPT}\n\n"
                "<active_skill>\n"
                f"{role_prompt}\n"
                "</active_skill>\n\n"
                "<response_format>Return one native JSON object. Do not use Markdown fences or stringify nested values. JSON keys remain English.</response_format>\n"
                + (
                    "<production_contract>" + _safe_json(production.production_contract) + "</production_contract>\n"
                    "<creative_contract>" + _safe_json(production.creative_contract) + "</creative_contract>\n"
                    "<asset_contract>" + _safe_json(production.asset_contract) + "</asset_contract>\n"
                    if include_contracts else ""
                )
                + "<brief>" + (production.brief or "Not written yet.") + "</brief>\n"
                + "<user_instruction>" + (instruction or "Create the first pass.") + "</user_instruction>\n"
                + "<asset_inventory>" + _safe_json(relevant_links) + "</asset_inventory>\n"
                + "<stage_context>" + stage_context + "</stage_context>\n"
                + (language_policy if language_policy is not None else _output_language_policy(production, instruction))
            ),
            parts=(parts_override if parts_override is not None else _asset_parts(production, roles)) if include_asset_parts else (parts_override or []),
            model_id=_production_model(production, "text", get_settings().vertex_video_analysis_model),
            json_response=True,
        )
    except Exception as exc:
        logger.warning("Video Production role unavailable", exc_info=True)
        raise RuntimeError("The production agent did not return a response. No existing work was replaced; please try again.") from exc
    payload = _parse_json(response)
    if not payload:
        raise ValueError("The production agent returned an invalid structured response. No existing work was replaced; please try again.")
    return payload


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


def _asset_manifest_display(payload: dict[str, object], fallback: list[str]) -> list[str]:
    """Format asset records for people instead of leaking JSON/Python objects."""
    raw = payload.get("asset_manifest")
    if isinstance(raw, dict):
        raw = raw.get("assets", [])
    if not isinstance(raw, list):
        return _string_list(payload, "asset_manifest", fallback)
    values: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            values.extend(str(value) for value in _expand_list_value(item))
            continue
        name = str(item.get("name") or item.get("asset_key") or "Asset").strip()
        asset_type = str(item.get("asset_type") or "").strip()
        description = str(item.get("description") or item.get("purpose") or "").strip()
        values.append(" — ".join(part for part in [name, asset_type, description] if part))
    return [value for value in values if value] or fallback


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
    """Derive output language from the latest user-authored input, never prior output."""
    # Do not reuse creative_direction.output_language here. It describes an old
    # agent result and can be in the reference video's language rather than the
    # language the user most recently used to direct this production.
    candidates = [instruction]
    candidates.extend(message.text for message in reversed(production.conversation) if message.role == "user")
    candidates.append(production.brief)
    sample = next((text for text in candidates if text and text.strip()), "")
    # The instruction itself can be in Chinese/Japanese/Korean while explicitly
    # requesting an English deliverable. Resolve that intent before inspecting
    # the instruction's characters (for example: "把 script 改成英文").
    requested = sample.lower()
    if (
        re.search(r"\b(?:write|rewrite|translate|change|switch|make|return|output|respond)\b[^\n]{0,80}\b(?:in|into|to|as)\s+english\b", requested)
        or re.search(r"\benglish\s+(?:script|version|output|copy)\b", requested)
        or re.search(r"(?:改|写|转|翻译|输出|生成).{0,20}(?:成|为|用)?(?:英文|英语)(?:script|脚本|版本|输出)?", sample, re.IGNORECASE)
    ):
        return "English"
    if (
        re.search(r"\b(?:write|rewrite|translate|change|switch|make|return|output|respond)\b[^\n]{0,80}\b(?:in|into|to|as)\s+(?:simplified\s+)?chinese\b", requested)
        or re.search(r"\b(?:simplified\s+)?chinese\s+(?:script|version|output|copy)\b", requested)
        or re.search(r"(?:改|写|转|翻译|输出|生成).{0,20}(?:成|为|用)?(?:中文|简体中文|汉语)(?:script|脚本|版本|输出)?", sample, re.IGNORECASE)
    ):
        return "Simplified Chinese"
    if (
        re.search(r"\b(?:write|rewrite|translate|change|switch|make|return|output|respond)\b[^\n]{0,80}\b(?:in|into|to|as)\s+korean\b", requested)
        or re.search(r"\bkorean\s+(?:script|version|output|copy)\b", requested)
        or re.search(r"(?:改|写|转|翻译|输出|生成).{0,20}(?:成|为|用)?(?:韩文|韩语)(?:script|脚本|版本|输出)?", sample, re.IGNORECASE)
    ):
        return "Korean"
    if (
        re.search(r"\b(?:write|rewrite|translate|change|switch|make|return|output|respond)\b[^\n]{0,80}\b(?:in|into|to|as)\s+japanese\b", requested)
        or re.search(r"\bjapanese\s+(?:script|version|output|copy)\b", requested)
        or re.search(r"(?:改|写|转|翻译|输出|生成).{0,20}(?:成|为|用)?(?:日文|日语)(?:script|脚本|版本|输出)?", sample, re.IGNORECASE)
    ):
        return "Japanese"
    if re.search(r"[\u4e00-\u9fff]", sample):
        return "Simplified Chinese"
    if re.search(r"[\uac00-\ud7af]", sample):
        return "Korean"
    if re.search(r"[\u3040-\u30ff]", sample):
        return "Japanese"
    return "English"


def _output_language_policy(production: VideoProduction, instruction: str) -> str:
    """Make output localization an explicit rule, not a weak model hint."""
    language = _response_language_hint(production, instruction)
    return (
        f"<language_policy>Target language: {language}. Every human-readable JSON string that you create "
        f"(analysis, titles, descriptions, dialogue, copy, asset names, risks, and replies) MUST be written in {language}. "
        "Translate observations rather than mirroring the reference language. Preserve original on-screen text, brand names, "
        "file names, and quoted dialogue only when reporting them as source evidence. JSON keys remain English.</language_policy>"
    )


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


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _contract_seconds(value: object, fallback: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        matches = re.findall(r"\d+(?:\.\d+)?", value)
        if matches:
            return float(matches[0])
    return fallback


def _normalise_creative_contract_payload(payload: object, production: VideoProduction) -> dict[str, object]:
    """Coerce common Gemini contract shapes into the strict internal schema.

    The agent often returns `beat_number` + a timecode string, and scalar text
    for fields whose contract schema intentionally uses arrays. Those are
    recoverable shape differences, not a reason to discard the whole strategy.
    """
    raw = payload if isinstance(payload, dict) else {}
    beats: list[dict[str, object]] = []
    raw_beats = raw.get("story_beats")
    if isinstance(raw_beats, list):
        for index, item in enumerate(raw_beats, start=1):
            if not isinstance(item, dict):
                continue
            timecode = str(item.get("timecode") or item.get("timing") or "")
            times = re.findall(r"\d+(?:\.\d+)?", timecode)
            start = _contract_seconds(item.get("start_seconds"), float(times[0]) if times else (index - 1) * production.target_seconds / max(len(raw_beats), 1))
            end = _contract_seconds(item.get("end_seconds"), float(times[1]) if len(times) > 1 else index * production.target_seconds / max(len(raw_beats), 1))
            beats.append({
                "beat_id": str(item.get("beat_id") or item.get("id") or f"beat_{index}"),
                "start_seconds": start,
                "end_seconds": max(start + 0.1, end),
                "purpose": str(item.get("purpose") or item.get("beat") or item.get("action") or f"Story beat {index}"),
                "action": str(item.get("action") or item.get("description") or item.get("purpose") or f"Advance story beat {index}"),
                "required_asset_keys": _as_string_list(item.get("required_asset_keys") or item.get("asset_keys")),
            })
    characters: list[dict[str, object]] = []
    raw_characters = raw.get("characters")
    if isinstance(raw_characters, list):
        for index, item in enumerate(raw_characters, start=1):
            if not isinstance(item, dict):
                continue
            guidance = item.get("reference_guidance")
            guidance_value = guidance if isinstance(guidance, dict) else {"allowed_use": [str(guidance)] if guidance else ["role", "energy", "cultural_context"]}
            characters.append({
                **item,
                "character_key": str(item.get("character_key") or item.get("asset_key") or f"character_{index}"),
                "cultural_context": _as_string_list(item.get("cultural_context")),
                "continuity_lock": _as_string_list(item.get("continuity_lock")),
                "reference_guidance": guidance_value,
            })
    return {
        **raw,
        "story_beats": beats,
        "characters": characters,
        "continuity_rules": _as_string_list(raw.get("continuity_rules")),
        "originality_guardrails": _as_string_list(raw.get("originality_guardrails")),
        "risks": _as_string_list(raw.get("risks")),
    }


def _normalise_asset_contract_payload(payload: object) -> dict[str, object]:
    raw = payload if isinstance(payload, dict) else {}
    strategy_map = {
        "casting_brief": "original_prompt", "onset_prop": "original_prompt", "prompt_only": "original_prompt",
        "3d_render": "original_prompt", "ui_graphic": "original_prompt", "motion_graphic": "original_prompt",
        "vector_asset": "original_prompt", "reference_frame": "reference_frame_guidance",
    }
    assets: list[dict[str, object]] = []
    raw_assets = raw.get("assets")
    if isinstance(raw_assets, list):
        for index, item in enumerate(raw_assets, start=1):
            if not isinstance(item, dict):
                continue
            source = str(item.get("source_strategy") or item.get("source_mode") or "original_prompt")
            asset_type = str(item.get("asset_type") or item.get("pack_type") or "ui").lower()
            assets.append({
                **item,
                "asset_key": _handoff_key(item.get("asset_key") or item.get("pack_key") or item.get("name"), f"asset_{index}"),
                "asset_type": asset_type if asset_type in _ASSET_PACK_TYPES else "ui",
                "name": str(item.get("name") or item.get("asset_name") or f"Asset {index}"),
                "source_strategy": strategy_map.get(source, source if source in {"original_prompt", "brand_asset", "reference_frame_guidance"} else "original_prompt"),
                "identity_source": str(item.get("identity_source") or item.get("source_requirement") or "Original production asset."),
                "generation_requirements": _as_string_list(item.get("generation_requirements") or item.get("visual_brief")),
                "scene_ids": _as_string_list(item.get("scene_ids")),
                "reference_frame_indexes": [int(value) for value in _as_string_list(item.get("reference_frame_indexes") or item.get("reference_frame_index")) if value.isdigit()],
            })
    return {**raw, "assets": assets}


def _ensure_creative_contracts(
    production: VideoProduction,
    inventory: dict[str, list[dict[str, object]]],
    defaults: dict[str, list[str]],
) -> None:
    """Keep a malformed Strategist JSON reply from leaving the next stage unusable.

    Gemini's human-readable Direction can be valid even when its auxiliary
    contract fields are absent or partially malformed. Derive the minimum typed
    contracts from the already-normalised visual inventory instead of silently
    leaving `{}` and allowing Screenwriter/lock-script to fail later.
    """
    production_contract = ProductionContract.model_validate(production.production_contract)
    cultural_context = production_contract.cultural_context
    assets: list[AssetContractItem] = []
    characters: list[CharacterIdentity] = []
    for category, asset_type in _VISUAL_INVENTORY_CATEGORIES.items():
        for item in inventory.get(category, []):
            key = str(item["asset_key"])
            name = str(item["asset_name"])
            brief = str(item["visual_brief"])
            frame_index = int(item.get("reference_frame_index", 0) or 0)
            assets.append(AssetContractItem(
                asset_key=key,
                asset_type=asset_type,  # type: ignore[arg-type]
                name=name,
                source_strategy="reference_frame_guidance" if frame_index else "original_prompt",
                identity_source=brief,
                generation_requirements=[brief, "Create an original reusable AI visual state; do not copy the reference."],
                reference_frame_indexes=[frame_index] if frame_index else [],
            ))
            if category == "recurring_characters":
                characters.append(CharacterIdentity(
                    character_key=key,
                    role=name,
                    cultural_context=cultural_context,
                    presentation=brief,
                    continuity_lock=["Maintain the approved identity, cultural context, wardrobe, and performance across all scenes."],
                ))
    # A product-only commercial is valid: do not invent a presenter just to
    # satisfy the schema. It still needs at least one reusable visual asset.
    if not assets:
        assets.append(AssetContractItem(
            asset_key="brand_end_card",
            asset_type="ui",
            name="Brand end-card UI",
            source_strategy="original_prompt",
            identity_source="Fallback for a missing Strategist asset inventory.",
            generation_requirements=["Create an original CTA end-card layout consistent with the production brief."],
        ))
    try:
        existing_creative = CreativeContract.model_validate(production.creative_contract)
    except Exception:
        existing_creative = CreativeContract()
    if not production.creative_contract or not existing_creative.concept:
        production.creative_contract = CreativeContract(
            concept=production.brief or production.title,
            core_promise=(defaults["strengths"][0] if defaults["strengths"] else "Present one clear benefit."),
            emotional_arc="Hook, proof, and a clear call to action.",
            format=f"{production.target_seconds}s {production.aspect_ratio}",
            reference_deconstruction={"transferable_strengths": defaults["strengths"]},
            characters=characters,
            continuity_rules=["Maintain the same approved visual states across connected scenes."],
            originality_guardrails=defaults["guardrails"],
            risks=["The Strategist contract was reconstructed from its visual inventory; review before locking."],
        ).model_dump(mode="json")
    try:
        existing_assets = AssetContract.model_validate(production.asset_contract)
    except Exception:
        existing_assets = AssetContract()
    if not production.asset_contract or not existing_assets.assets:
        production.asset_contract = AssetContract(assets=assets).model_dump(mode="json")


def _reconcile_asset_contract_with_handoff(production: VideoProduction) -> None:
    """Make the visible approval plan and the machine Asset Contract identical.

    The Strategist can return a complete `design_handoff` while its compact
    asset_contract omits a row. Keeping both silently is the source of the
    Direction(7) → Designer(4) mismatch. The handoff is the user-reviewed
    proposal, so missing rows are deterministically added to the contract.
    """
    try:
        contract = AssetContract.model_validate(production.asset_contract)
    except Exception:
        contract = AssetContract()
    known = {item.asset_key for item in contract.assets}
    source_map = {
        "brand_asset": "brand_asset",
        "reference_frame": "reference_frame_guidance",
    }
    for item in production.creative_direction.design_handoff:
        if not isinstance(item, dict):
            continue
        key = _handoff_key(item.get("pack_key"), "asset")
        if key in known:
            continue
        pack_type = str(item.get("pack_type") or "ui")
        if pack_type not in _ASSET_PACK_TYPES:
            pack_type = "ui"
        source_mode = str(item.get("source_mode") or "prompt_only")
        contract.assets.append(AssetContractItem(
            asset_key=key,
            asset_type=pack_type,  # type: ignore[arg-type]
            name=str(item.get("asset_name") or key.replace("_", " ").title()),
            source_strategy=source_map.get(source_mode, "original_prompt"),
            identity_source=str(item.get("visual_brief") or item.get("source_requirement") or item.get("purpose") or "Approved Direction handoff."),
            generation_requirements=[
                str(item.get("visual_brief") or item.get("purpose") or "Lock this reusable visual state."),
                *_as_string_list(item.get("continuity_rules")),
                *_as_string_list(item.get("negative_constraints")),
            ],
            reference_frame_indexes=[int(item.get("reference_frame_index", 0))] if source_mode == "reference_frame" else [],
        ))
        known.add(key)
    production.asset_contract = contract.model_dump(mode="json")


def _confirmed_asset_keys(production: VideoProduction) -> set[str]:
    proposed = {str(item.get("pack_key")) for item in production.creative_direction.design_handoff if isinstance(item, dict) and item.get("pack_key")}
    confirmed = {key for key in production.creative_direction.confirmed_pack_keys if key}
    # Empty is legacy-compatible: a pre-gate production continues to use all
    # known handoff rows. New productions get explicit selections on approval.
    return confirmed & proposed if confirmed else proposed


def _reference_frame_plan(
    payload: dict[str, object],
    source_asset_ids: list[str] | None = None,
) -> list[dict[str, object]]:
    """Keep only safe, actionable timestamps produced by the reference analysis."""
    raw_plan = payload.get("reference_frame_plan")
    if not isinstance(raw_plan, list):
        return []
    source_asset_ids = source_asset_ids or []
    source_asset_id = next((asset_id for asset_id in source_asset_ids if _asset_by_id(asset_id)), "")
    source_asset = _asset_by_id(source_asset_id) if source_asset_id else None
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
            "source_asset_id": source_asset_id,
            "source_asset_title": source_asset.title if source_asset else source_asset_id,
        })
    return plan


def _hydrate_reference_frame_sources(production: VideoProduction) -> None:
    """Backfill the Creative Reference provenance on plans saved before it existed."""
    source_ids = production.creative_direction.analyzed_asset_ids or _creative_direction_asset_ids(production)
    source_asset_id = next((asset_id for asset_id in source_ids if _asset_by_id(asset_id)), "")
    source_asset = _asset_by_id(source_asset_id) if source_asset_id else None
    for frame in production.creative_direction.reference_frame_plan:
        if not isinstance(frame, dict):
            continue
        frame.setdefault("source_asset_id", source_asset_id)
        frame.setdefault("source_asset_title", source_asset.title if source_asset else source_asset_id)


_VISUAL_INVENTORY_CATEGORIES = {
    "recurring_characters": "character",
    "props_and_key_objects": "prop",
    "environments": "environment",
    "ui_and_brand_assets": "ui",
}
_HANDOFF_SOURCE_MODES = {
    "prompt_only", "brand_asset", "reference_frame", "casting_brief",
    "onset_prop", "3d_render", "ui_graphic", "motion_graphic", "vector_asset",
}
_HANDOFF_SCOPES = {"design_asset"}


def _handoff_key(value: object, fallback: str) -> str:
    """Produce a stable JSON-safe Pack key from a model-supplied label."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return fallback if normalized in {"", "none", "null", "undefined", "unknown", "n_a", "na"} else normalized


def _normalize_handoff_keys(production: VideoProduction) -> None:
    """Repair duplicate/placeholder model keys before React or approval sees them."""
    handoff = production.creative_direction.design_handoff
    if not handoff:
        return
    used: set[str] = set()
    placeholder_was_selected = any(
        _handoff_key(key, "") == ""
        for key in production.creative_direction.confirmed_pack_keys
    )
    for index, item in enumerate(handoff, start=1):
        if not isinstance(item, dict):
            continue
        pack_type = str(item.get("pack_type") or "asset").lower()
        base = _handoff_key(item.get("pack_key"), f"{pack_type}_{index}")
        key = base
        suffix = 2
        while key in used:
            key = f"{base}_{suffix}"
            suffix += 1
        item["pack_key"] = key
        used.add(key)
    if placeholder_was_selected:
        production.creative_direction.confirmed_pack_keys = list(used)
    else:
        production.creative_direction.confirmed_pack_keys = [
            key for key in production.creative_direction.confirmed_pack_keys if key in used
        ]


def _visual_inventory(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    """Normalize the Strategist's visual audit before reconciling the handoff."""
    raw_inventory = payload.get("visual_inventory")
    if not isinstance(raw_inventory, dict):
        return {}
    inventory: dict[str, list[dict[str, object]]] = {}
    for category in _VISUAL_INVENTORY_CATEGORIES:
        raw_items = raw_inventory.get(category)
        if not isinstance(raw_items, list):
            continue
        items: list[dict[str, object]] = []
        # A short-form production needs a concise execution contract. Keep the
        # inventory rich enough to reconcile handoff coverage, but do not let a
        # single category inflate the final production plan.
        category_limit = {
            "recurring_characters": 3,
            "props_and_key_objects": 2,
            # Consolidate related locations into one reusable environment
            # brief, and related UI/logo/CTA elements into one brand/UI suite.
            "environments": 1,
            "ui_and_brand_assets": 1,
        }[category]
        for index, item in enumerate(raw_items[:category_limit], start=1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("asset_name") or item.get("name") or "").strip()
            brief = str(item.get("visual_brief") or item.get("brief") or "").strip()
            if not name and not brief:
                continue
            try:
                frame_index = max(0, int(item.get("reference_frame_index", 0) or 0))
            except (TypeError, ValueError):
                frame_index = 0
            items.append({
                "asset_key": _handoff_key(item.get("asset_key") or name, f"{category}_{index}"),
                "asset_name": name or f"{_VISUAL_INVENTORY_CATEGORIES[category].title()} asset {index}",
                "visual_brief": brief or "Lock this reusable visual state for the original production.",
                "reference_frame_index": frame_index,
                # LinglongLab generates AI video. A casting or on-set description is
                # an input to an AI consistency sheet, never a reason to omit
                # the person or prop from the reusable visual-asset contract.
                "handoff_scope": "design_asset",
            })
        if items:
            inventory[category] = items
    return inventory


def _design_handoff(
    payload: dict[str, object],
    visual_inventory: dict[str, list[dict[str, object]]] | None = None,
) -> list[dict[str, object]]:
    """Normalize and complete Direction's explicit contract for Design."""
    # Accept the two names most commonly used by a structured Strategist
    # response. The internal normalized representation is always
    # `design_handoff`; this compatibility is input repair, not a second plan.
    raw_handoff = payload.get("design_handoff") or payload.get("asset_plan")
    if isinstance(raw_handoff, dict):
        raw_handoff = raw_handoff.get("items") or raw_handoff.get("assets")
    if not isinstance(raw_handoff, list):
        raw_handoff = []
    allowed_types = {"character", "environment", "prop", "ui", "lighting", "transition"}
    handoff: list[dict[str, object]] = []
    seen: dict[tuple[str, str], dict[str, object]] = {}
    for index, item in enumerate(raw_handoff[:8], start=1):
        if not isinstance(item, dict):
            continue
        pack_type = str(item.get("pack_type") or "environment").lower()
        source_mode = str(item.get("source_mode") or "prompt_only").lower()
        try:
            reference_frame_index = max(0, int(item.get("reference_frame_index", 0) or 0))
        except (TypeError, ValueError):
            reference_frame_index = 0
        normalized = {
            "pack_key": _handoff_key(item.get("pack_key"), f"pack_{index}"),
            "pack_type": pack_type if pack_type in allowed_types else "environment",
            "asset_name": str(item.get("asset_name") or item.get("pack_key") or f"Pack {index}").strip(),
            "purpose": str(item.get("purpose") or "Lock a reusable visual state.").strip(),
            "visual_mode": str(item.get("visual_mode") or "ai_generated").strip(),
            "composition_role": str(item.get("composition_role") or "reusable_visual_state").strip(),
            "visual_brief": str(item.get("visual_brief") or item.get("purpose") or "Lock a reusable visual state.").strip(),
            "continuity_rules": _as_string_list(item.get("continuity_rules")),
            "scene_uses": _as_string_list(item.get("scene_uses")),
            "negative_constraints": _as_string_list(item.get("negative_constraints")),
            "source_mode": source_mode if source_mode in _HANDOFF_SOURCE_MODES else "prompt_only",
            "source_requirement": str(item.get("source_requirement") or "No external image source is required.").strip(),
            "reference_frame_index": reference_frame_index,
            "priority": str(item.get("priority") or "medium").lower() if str(item.get("priority") or "medium").lower() in {"high", "medium", "low"} else "medium",
            "required": bool(item.get("required", True)),
            "status": str(item.get("status") or "ready").lower() if str(item.get("status") or "ready").lower() in {"ready", "missing"} else "ready",
            "handoff_scope": "design_asset",
        }
        identity = (str(normalized["pack_type"]), _handoff_key(normalized["asset_name"], str(normalized["pack_key"])))
        # Keep one authoritative source instruction per entity. Repeated rows
        # with a different source mode are a model error, not separate assets.
        if identity not in seen:
            seen[identity] = normalized
            handoff.append(normalized)
    # Self-correction: the model first audits every visual entity, then this
    # deterministic reconciliation supplies any omitted contract row. This
    # protects live action, animation, UI, and product-led references alike.
    for category, pack_type in _VISUAL_INVENTORY_CATEGORIES.items():
        for item in (visual_inventory or {}).get(category, []):
            key = str(item["asset_key"])
            name_key = _handoff_key(item["asset_name"], key)
            matching = next((
                existing for existing in handoff
                if existing["pack_key"] == key
                or (
                    existing["pack_type"] == pack_type
                    and _handoff_key(existing["asset_name"], str(existing["pack_key"])) == name_key
                )
            ), None)
            if matching:
                # Inventory is the audit authority for coverage, while the
                # authored handoff row remains the source of truth for its
                # single source instruction.
                matching["handoff_scope"] = "design_asset"
                continue
            frame_index = int(item["reference_frame_index"])
            source_mode = "reference_frame" if frame_index > 0 else "prompt_only"
            handoff.append({
                "pack_key": key,
                "pack_type": pack_type,
                "asset_name": str(item["asset_name"]),
                "purpose": str(item["visual_brief"]),
                "source_mode": source_mode,
                "source_requirement": (
                    f"Use Designer reference frame {frame_index + 1} only for semantic guidance; create an original visual state."
                    if source_mode == "reference_frame"
                    else "Create an original visual state from the production brief; no supplied image is required."
                ),
                "reference_frame_index": frame_index,
                "priority": "high" if pack_type in {"character", "prop"} else "medium",
                "required": True,
                "status": "ready",
                "handoff_scope": "design_asset",
            })
    # The Strategist is instructed to consolidate into 5-8 rows. This guard
    # prevents a malformed response from becoming an unworkable pack board.
    return handoff[:8]


def _has_meaningful_asset_plan(handoff: list[dict[str, object]]) -> bool:
    """Reject schema-shaped placeholders before they reach the approval UI."""
    if not handoff:
        return False
    placeholder_rows = 0
    for item in handoff:
        name = str(item.get("asset_name") or "").strip().lower()
        purpose = str(item.get("purpose") or "").strip().lower()
        if (
            not name
            or re.fullmatch(r"(?:asset|pack|environment)\s*\d+", name)
            or purpose in {"", "lock a reusable visual state.", "lock a reusable visual state"}
        ):
            placeholder_rows += 1
    # One incomplete optional row is recoverable. A plan made mostly of schema
    # defaults is not a plan and must be rebuilt from observed evidence.
    return placeholder_rows * 2 < len(handoff)


def _is_generic_story_structure(items: list[str]) -> bool:
    if not items:
        return True
    generic_markers = (
        "establish the product, character, or benefit hook",
        "demonstrate the mechanism, proof, or core experience",
        "reinforce the value proposition and land on the branded cta",
        "product proof",
    )
    return sum(any(marker in item.lower() for marker in generic_markers) for item in items) * 2 >= len(items)


def _story_structure_from_reference_analysis(
    reference_analysis: dict[str, object],
    target_seconds: int,
) -> list[str]:
    """Provide a specific reviewable recovery plan, never generic beat labels."""
    timeline = [item for item in reference_analysis.get("timeline", []) if isinstance(item, dict)]
    if not timeline:
        return []
    selected = timeline[: min(6, len(timeline))]
    source_end = max(
        (float(item.get("end_seconds", 0) or 0) for item in selected),
        default=float(target_seconds),
    )
    scale = target_seconds / source_end if source_end else 1.0
    beats: list[str] = []
    for index, item in enumerate(selected, start=1):
        try:
            start = max(0.0, float(item.get("start_seconds", 0) or 0) * scale)
            end = max(start + 0.5, float(item.get("end_seconds", start + 1) or start + 1) * scale)
        except (TypeError, ValueError):
            continue
        visual = str(item.get("observed_visual") or item.get("action") or "the observed visual interaction").strip()
        action = str(item.get("action") or "Advance the original benefit demonstration.").strip()
        camera = str(item.get("camera") or "a clear social-video framing").strip()
        beats.append(
            f"{start:.1f}s–{min(float(target_seconds), end):.1f}s: Original adaptation of {visual} — "
            f"{action}. Use {camera}; bridge directly into the next proof or reaction beat."
        )
    return beats


def _asset_plan_from_reference_analysis(reference_analysis: dict[str, object]) -> list[dict[str, object]]:
    """Last-resort, visible plan when a valid strategy omits its Asset Plan.

    This protects the user from a dead end while keeping every inferred row
    reviewable. It never pretends that a client asset was supplied.
    """
    plan: list[dict[str, object]] = []

    def add(pack_type: str, name: str, purpose: str) -> None:
        key = _handoff_key(name, f"{pack_type}_{len(plan) + 1}")
        if any(item["pack_key"] == key for item in plan):
            return
        plan.append({
            "pack_key": key,
            "pack_type": pack_type,
            "asset_name": name,
            "purpose": purpose,
            "source_mode": "prompt_only",
            "source_requirement": "AI-generated original visual state; verify this inferred plan before scripting.",
            "reference_frame_index": 0,
            "priority": "high" if pack_type in {"character", "prop", "ui"} else "medium",
            "required": True,
            "status": "ready",
            "handoff_scope": "design_asset",
        })

    people = reference_analysis.get("people_and_wardrobe")
    if isinstance(people, list):
        for index, person in enumerate((str(item).strip() for item in people if str(item).strip()), start=1):
            add("character", person[:120] or f"On-screen character {index}", "Lock the recurring AI performer identity inferred from the reference analysis.")
            if index >= 2:
                break
    locations = reference_analysis.get("locations")
    if isinstance(locations, list) and locations:
        add("environment", str(locations[0]).strip()[:120] or "Primary environment", "Lock the reusable environment inferred from the reference analysis.")
    props = reference_analysis.get("props_and_ui")
    if isinstance(props, list):
        for item in props:
            label = str(item).strip()
            if label:
                add("prop", label[:120], "Lock the handled hero prop inferred from the reference analysis.")
                break
    add("ui", "Brand CTA and end-card UI", "Lock the original brand CTA, app UI, and download layout required to close the ad.")
    return plan[:8]


def _complete_inventory_from_handoff(
    inventory: dict[str, list[dict[str, object]]],
    handoff: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Make the visible Asset Plan the single coverage authority.

    Strategist output can contain a perfectly valid plan but omit its parallel
    visual_inventory object. Deriving the inventory here prevents downstream
    contracts from silently losing the same character or prop the user just
    approved in the plan.
    """
    category_for_type = {pack_type: category for category, pack_type in _VISUAL_INVENTORY_CATEGORIES.items()}
    completed = {category: [dict(item) for item in items] for category, items in inventory.items()}
    for category in _VISUAL_INVENTORY_CATEGORIES:
        completed.setdefault(category, [])
    existing_keys = {
        str(item.get("asset_key"))
        for items in completed.values()
        for item in items
        if item.get("asset_key")
    }
    for item in handoff:
        pack_type = str(item.get("pack_type") or "")
        category = category_for_type.get(pack_type)
        if not category:
            continue
        key = _handoff_key(item.get("pack_key"), f"{pack_type}_{len(completed[category]) + 1}")
        if key in existing_keys:
            continue
        try:
            frame_index = max(0, int(item.get("reference_frame_index", 0) or 0))
        except (TypeError, ValueError):
            frame_index = 0
        completed[category].append({
            "asset_key": key,
            "asset_name": str(item.get("asset_name") or key.replace("_", " ").title()),
            "visual_brief": str(item.get("purpose") or "Lock this reusable visual state."),
            "reference_frame_index": frame_index,
            "handoff_scope": "design_asset",
        })
        existing_keys.add(key)
    return {category: items for category, items in completed.items() if items}


def _reference_frame_plan_from_analysis(
    reference_analysis: dict[str, object],
    source_asset_ids: list[str],
) -> list[dict[str, object]]:
    """Choose review still timestamps deterministically from observed footage.

    Screenshot extraction remains a code responsibility: the model supplies a
    factual timeline, while this function selects three spread-out timestamps
    and `_extract_reference_video_frames` performs the FFmpeg extraction.
    """
    timeline = reference_analysis.get("timeline")
    if not isinstance(timeline, list):
        return []
    observations = [item for item in timeline if isinstance(item, dict)]
    if not observations:
        return []
    indexes = sorted({0, len(observations) // 2, len(observations) - 1})
    source_asset_id = next((asset_id for asset_id in source_asset_ids if _asset_by_id(asset_id)), "")
    source_asset = _asset_by_id(source_asset_id) if source_asset_id else None
    plan: list[dict[str, object]] = []
    for index in indexes:
        observation = observations[index]
        try:
            timestamp = max(0.0, float(observation.get("start_seconds", 0) or 0))
        except (TypeError, ValueError):
            continue
        purpose = str(observation.get("action") or observation.get("observed_visual") or "Reference visual moment").strip()
        rationale = str(observation.get("observed_visual") or observation.get("camera") or "Observed composition and pacing reference.").strip()
        plan.append({
            "timestamp_seconds": round(timestamp, 2),
            "purpose": purpose,
            "rationale": rationale,
            "source_asset_id": source_asset_id,
            "source_asset_title": source_asset.title if source_asset else source_asset_id,
        })
    return plan


def _normalize_ai_handoff_scopes(production: VideoProduction) -> None:
    """Migrate legacy filmed-production handoffs into LinglongLab's AI workflow."""
    for item in production.creative_direction.design_handoff:
        if isinstance(item, dict):
            item["handoff_scope"] = "design_asset"
    for items in production.creative_direction.visual_inventory.values():
        for item in items:
            if isinstance(item, dict):
                item["handoff_scope"] = "design_asset"


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
    needs_reference_analysis = has_reference_video and not production.creative_direction.reference_analysis
    return (
        not production.creative_direction.reference_summary
        or set(current_asset_ids) != set(analyzed_asset_ids)
        or needs_frame_plan
        or needs_reference_analysis
    )


def _run_reference_video_analysis(production: VideoProduction, instruction: str) -> dict[str, object]:
    """Analyse reference media without letting strategy or brand context bias it."""
    parts = _asset_parts(production, {"reference"})
    if not parts:
        return {}
    response = _call_multimodal_text_model(
        prompt=(
            f"{REFERENCE_VIDEO_ANALYST_PROMPT}\n\n"
            "Return JSON only, without Markdown fences. Use native JSON arrays and objects. "
            + _output_language_policy(production, instruction)
        ),
        parts=parts,
        model_id=_production_model(production, "text", get_settings().vertex_video_analysis_model),
        json_response=True,
    )
    payload = _parse_json(response)
    if not isinstance(payload.get("timeline"), list) or not payload["timeline"]:
        raise ValueError("Reference Video Analyst returned no usable time-coded observations.")
    payload["_output_language"] = _response_language_hint(production, instruction)
    return payload


def _legacy_run_creative_director(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
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
    raise RuntimeError("Legacy Creative Strategist flow is disabled. Use run_creative_director.")
    defaults = _creative_direction_fallbacks(production, message)
    if isinstance(payload.get("creative_contract"), dict):
        try:
            production.creative_contract = CreativeContract.model_validate(
                _normalise_creative_contract_payload(payload["creative_contract"], production)
            ).model_dump(mode="json")
        except Exception:
            logger.warning("Creative Strategist returned an invalid creative contract", exc_info=True)
    if isinstance(payload.get("asset_contract"), dict):
        try:
            production.asset_contract = AssetContract.model_validate(
                _normalise_asset_contract_payload(payload["asset_contract"])
            ).model_dump(mode="json")
        except Exception:
            logger.warning("Creative Strategist returned an invalid asset contract", exc_info=True)
    if production.creative_contract and production.asset_contract:
        try:
            contract_errors = contract_validation_errors(
                CreativeContract.model_validate(production.creative_contract),
                AssetContract.model_validate(production.asset_contract),
            )
            if contract_errors:
                payload["risks"] = [*_string_list(payload, "risks"), *contract_errors]
        except Exception:
            logger.warning("Could not validate creative and asset contracts", exc_info=True)
    visual_inventory = _visual_inventory(payload) if needs_asset_analysis else production.creative_direction.visual_inventory
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
        reference_frame_plan=_reference_frame_plan(payload, analyzed_asset_ids) if needs_asset_analysis else production.creative_direction.reference_frame_plan,
        visual_inventory=visual_inventory,
        design_handoff=(
            _design_handoff(payload, visual_inventory)
            if needs_asset_analysis
            else production.creative_direction.design_handoff
        ),
        output_language=_response_language_hint(production, message),
        analyzed_asset_ids=analyzed_asset_ids if needs_asset_analysis else production.creative_direction.analyzed_asset_ids,
    )
    _ensure_creative_contracts(production, visual_inventory, defaults)
    _reconcile_asset_contract_with_handoff(production)
    production.stage = VideoProductionStage.direction
    reply = _string_value(
        payload,
        "reply",
        "I analyzed the creative direction and prepared the brand-asset checklist. Upload the required assets, then approve the direction to move into scripting.",
    )
    production.conversation.append(VideoProductionConversationMessage(role="assistant", text=reply))
    return _save(production)


def run_creative_director(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    """Run reference observation first, then build strategy from that evidence."""
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    message = request.message.strip()
    if message:
        production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
        if not production.brief:
            production.brief = message

    reference_analysis = production.creative_direction.reference_analysis
    requested_language = _response_language_hint(production, message)
    needs_analysis = (
        _creative_direction_needs_asset_analysis(production)
        or reference_analysis.get("_output_language") != requested_language
    )
    analyzed_asset_ids = _creative_direction_asset_ids(production)
    if needs_analysis:
        try:
            reference_analysis = _run_reference_video_analysis(production, message)
        except Exception as exc:
            logger.warning("Reference video analysis failed", exc_info=True)
            raise RuntimeError(
                "Creative Strategist could not complete the reference-video analysis. The previous direction was kept; please try again."
            ) from exc

    strategy_context = (
        "<reference_analysis>" + _safe_json(reference_analysis) + "</reference_analysis>\n"
        "<stage_constraint>The output schema in your role instruction is authoritative. Create an original adaptation, not a retelling of the reference. Do not return internal contracts.</stage_constraint>"
    )
    payload = _role_payload(
        production,
        roles={"brand", "character", "product", "logo", "background"},
        instruction=message,
        role_prompt=(
            f"{CREATIVE_STRATEGIST_PROMPT}\n"
            "Use the evidence record faithfully. Do not use or describe a reference action that the evidence record does not contain."
        ),
        include_asset_parts=True,
        stage_context=strategy_context,
    )

    # Strategist suggestions reduce setup friction, but the user remains the
    # decision maker. Never replace an already confirmed market/language plan.
    suggested_setup = payload.get("video_setup")
    if not production.video_setup.confirmed and isinstance(suggested_setup, dict):
        production.video_setup = VideoProductionSetup(
            target_market=str(suggested_setup.get("target_market") or production.video_setup.target_market),
            target_audience=str(suggested_setup.get("target_audience") or production.video_setup.target_audience),
            video_type=str(suggested_setup.get("video_type") or payload.get("commercial_type") or production.video_setup.video_type),
            visual_style=str(suggested_setup.get("visual_style") or production.video_setup.visual_style),
            spoken_language=str(suggested_setup.get("spoken_language") or production.video_setup.spoken_language),
            subtitle_language=str(suggested_setup.get("subtitle_language") or production.video_setup.subtitle_language),
            platform=str(suggested_setup.get("platform") or production.video_setup.platform),
            conversion_goal=str(suggested_setup.get("conversion_goal") or production.video_setup.conversion_goal),
            confirmed=False,
        )

    visual_inventory = _visual_inventory(payload)
    design_handoff = _design_handoff(payload, visual_inventory)
    if not _has_meaningful_asset_plan(design_handoff):
        design_handoff = _asset_plan_from_reference_analysis(reference_analysis)
        if not design_handoff:
            raise ValueError("Creative Strategist returned no usable Asset Plan. Add a reference video or describe the people, setting, and product in the brief, then try again.")
        payload["risks"] = [
            *_string_list(payload, "risks"),
            "Asset Plan was rebuilt from reference observations because the Strategist returned placeholder rows; review the plan before confirming.",
        ]
    visual_inventory = _complete_inventory_from_handoff(visual_inventory, design_handoff)

    defaults = _creative_direction_fallbacks(production, message)
    story_structure = _string_list(payload, "story_structure", defaults["story"])
    if _is_generic_story_structure(story_structure):
        story_structure = _story_structure_from_reference_analysis(reference_analysis, production.target_seconds) or story_structure
    # Contracts are generated from the user-readable Asset Plan rather than
    # asking the Strategist to produce a second, brittle schema in one turn.
    production.creative_contract = {}
    production.asset_contract = {}
    production.creative_direction = VideoProductionCreativeDirection(
        status="draft",
        reference_analysis=reference_analysis,
        reference_summary=_string_value(payload, "reference_summary", "Reference observations were converted into an original production plan."),
        commercial_type=_string_value(payload, "commercial_type", "Commercial video", separator=" · "),
        strengths_to_adapt=_string_list(payload, "strengths_to_adapt", defaults["strengths"]),
        story_structure=story_structure,
        scene_and_character_notes=_string_list(payload, "scene_and_character_notes"),
        camera_and_pacing=_string_list(payload, "camera_and_pacing"),
        music_direction=_string_list(payload, "music_direction"),
        asset_request=_string_list(payload, "asset_request"),
        originality_guardrails=_string_list(payload, "originality_guardrails", defaults["guardrails"]),
        risks=_string_list(payload, "risks"),
        reference_frame_plan=(
            _reference_frame_plan(payload, analyzed_asset_ids)
            or _reference_frame_plan_from_analysis(reference_analysis, analyzed_asset_ids)
        ),
        visual_inventory=visual_inventory,
        design_handoff=design_handoff,
        output_language=_response_language_hint(production, message),
        analyzed_asset_ids=analyzed_asset_ids,
    )
    _ensure_creative_contracts(production, visual_inventory, defaults)
    _reconcile_asset_contract_with_handoff(production)
    production.stage = VideoProductionStage.direction
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text=_string_value(payload, "reply", "I completed a source-evidence analysis and built the original production plan. Review the analysis and confirm the asset plan before scripting."),
    ))
    return _save(production)


def run_production_designer(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    if not production.creative_contract or not production.asset_contract:
        _ensure_creative_contracts(
            production,
            production.creative_direction.visual_inventory,
            _creative_direction_fallbacks(production, production.brief),
        )
    _reconcile_asset_contract_with_handoff(production)
    production.script.scenes = _bind_script_scenes_to_contract(production, production.script.scenes)
    message = request.message.strip()
    if message:
        production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
    payload = _role_payload(
        production,
        roles={"brand", "character", "product", "logo", "background", "audio"},
        instruction=message,
        role_prompt=(
            f"{PRODUCTION_DESIGNER_PROMPT}\n"
            "The confirmed Asset Plan contains visual_mode, composition_role, visual_brief, continuity_rules, scene_uses, and negative_constraints. Use those as the creative brief; write the final image prompt by combining them with the locked Script, selected source assets, and design continuity. Do not merely repeat the brief. "
            "Return exactly: reply, visual_identity, character_and_product_rules, logo_and_copy_rules, keyframe_rules, continuity_rules, missing_assets, keyframe_prompts, lighting_and_color_cards, motion_blueprints, transition_rules, asset_packs. "
            "asset_packs is an array of title, asset_pack_type, purpose, reason_for_new_pack, handoff_key, source_mode, source_notes, scene_ids, prompt, crop_plan, asset_ids. "
            "Use each confirmed handoff_key used in the script once. scene_ids must be script scene IDs. A 2x2 sheet is a review contact sheet, never a final video input."
        ),
        stage_context=(
            f"Locked Script: {_safe_json(production.script.model_dump(mode='json'))}\n"
            f"Confirmed Asset Plan: {_safe_json(production.creative_direction.design_handoff)}"
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
        confirmed_keys = _confirmed_asset_keys(production)
        design_handoff_keys = {
            str(item.get("pack_key"))
            for item in production.creative_direction.design_handoff
            if isinstance(item, dict) and (not confirmed_keys or str(item.get("pack_key")) in confirmed_keys)
        }
        if isinstance(raw_packs, list):
            for index, item in enumerate(raw_packs, start=1):
                if not isinstance(item, dict):
                    continue
                handoff_key = str(item.get("handoff_key") or "")
                if design_handoff_keys and handoff_key not in design_handoff_keys:
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
                    handoff_key=handoff_key,
                    source_mode=str(item.get("source_mode") or "prompt_only") if str(item.get("source_mode") or "prompt_only") in {"prompt_only", "brand_asset", "reference_frame"} else "prompt_only",  # type: ignore[arg-type]
                    source_notes=str(item.get("source_notes") or ""),
                    asset_ids=pack_asset_ids,
                )
                inferred_type = _infer_asset_pack_type(sheet)
                if pack_type == "environment" and inferred_type != "environment":
                    sheet.asset_pack_type = inferred_type  # type: ignore[assignment]
                    sheet.kind = "character_consistency" if inferred_type == "character" else "scene_style"
                packs.extend(_split_duo_character_pack(sheet) if sheet.asset_pack_type == "character" else [sheet])
        if packs:
            # Designer may improve prompts, but it may never choose to omit an
            # asset explicitly bound by the locked Script. Add deterministic
            # drafts for any missing contract key instead of silently dropping
            # a performer such as char_friend_b.
            expected_keys = {
                key
                for scene in production.script.scenes
                for key in [*scene.character_keys, scene.environment_key, *scene.prop_keys, *scene.ui_keys]
                if key
            }
            contract_specs = {
                item.get("asset_key"): item
                for item in production.asset_contract.get("assets", [])
                if isinstance(item, dict) and item.get("asset_key")
            }
            handoff_specs = {
                str(item.get("pack_key")): item
                for item in production.creative_direction.design_handoff
                if isinstance(item, dict) and item.get("pack_key")
            }
            present_keys = {sheet.handoff_key for sheet in packs}
            for key in sorted(expected_keys - present_keys):
                spec = contract_specs.get(key) or handoff_specs.get(key) or {}
                pack_type = str(spec.get("asset_type") or spec.get("pack_type") or "environment")
                if pack_type not in allowed_types:
                    pack_type = "environment"
                name = str(spec.get("name") or spec.get("asset_name") or key.replace("_", " ").title())
                linked_scenes = [scene.id for scene in production.script.scenes if key in [*scene.character_keys, scene.environment_key, *scene.prop_keys, *scene.ui_keys]]
                packs.append(VideoProductionDesignSheet(
                    id=f"design_{uuid4().hex[:8]}",
                    title=f"{name} Pack",
                    kind="character_consistency" if pack_type == "character" else "scene_style",
                    asset_pack_type=pack_type,  # type: ignore[arg-type]
                    purpose=f"Required AI visual state for {name}; generated because the locked Script references {key}.",
                    reason_for_new_pack="Required by an explicit locked-script asset binding.",
                    handoff_key=key,
                    source_mode="prompt_only",
                    source_notes="Deterministically added from the locked Script Asset Contract.",
                    prompt=f"Create the reusable AI visual state for {name}. Follow the immutable Creative Contract and preserve all identity, cultural, and continuity rules.",
                    scene_ids=linked_scenes,
                ))
            return _normalize_asset_packs(production, packs)

        if design_handoff_keys:
            # A Designer text response can fail or omit `asset_packs`; that
            # must never collapse a valid Script + Direction into an empty
            # board. Compile the contract rows into deterministic drafts, then
            # let the user/Designer refine prompts without losing coverage.
            expected_keys = {
                key
                for scene in production.script.scenes
                for key in [*scene.character_keys, scene.environment_key, *scene.prop_keys, *scene.ui_keys]
                if key
            } or design_handoff_keys
            contract_specs = {
                str(item.get("asset_key")): item
                for item in production.asset_contract.get("assets", [])
                if isinstance(item, dict) and item.get("asset_key")
            }
            handoff_specs = {
                str(item.get("pack_key")): item
                for item in production.creative_direction.design_handoff
                if isinstance(item, dict) and item.get("pack_key")
            }
            deterministic: list[VideoProductionDesignSheet] = []
            for key in sorted(expected_keys):
                spec = contract_specs.get(key) or handoff_specs.get(key) or {}
                pack_type = str(spec.get("asset_type") or spec.get("pack_type") or "environment")
                if pack_type not in allowed_types:
                    pack_type = "environment"
                name = str(spec.get("name") or spec.get("asset_name") or key.replace("_", " ").title())
                linked_scenes = [scene.id for scene in production.script.scenes if key in [*scene.character_keys, scene.environment_key, *scene.prop_keys, *scene.ui_keys]]
                deterministic.append(VideoProductionDesignSheet(
                    id=f"design_{uuid4().hex[:8]}",
                    title=f"{name} Pack",
                    kind="character_consistency" if pack_type == "character" else "scene_style",
                    asset_pack_type=pack_type,  # type: ignore[arg-type]
                    purpose=f"Required reusable AI visual state for {name}.",
                    reason_for_new_pack="Compiled from the Script and Asset Contract because Designer omitted a pack row.",
                    handoff_key=key,
                    source_mode="prompt_only",
                    source_notes="Deterministic contract coverage fallback.",
                    prompt=f"Create the reusable AI visual state for {name}. Follow the Creative Contract exactly; preserve identity, cultural context, continuity, and original-reference boundaries.",
                    scene_ids=linked_scenes,
                ))
            return _normalize_asset_packs(production, deterministic)

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
    if not production.video_setup.confirmed:
        raise ValueError("Confirm Video setup before generating or revising the Script. Choose the market, audience, video type, visual style, and spoken language first.")
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
    direction = production.creative_direction
    confirmed_keys = _confirmed_asset_keys(production)
    approved_direction = {
        "reference_summary": direction.reference_summary,
        "story_structure": direction.story_structure,
        "scene_and_character_notes": direction.scene_and_character_notes,
        "camera_and_pacing": direction.camera_and_pacing,
        "music_direction": direction.music_direction,
        "originality_guardrails": direction.originality_guardrails,
        "confirmed_asset_plan": [
            item for item in direction.design_handoff
            if isinstance(item, dict) and (not confirmed_keys or str(item.get("pack_key")) in confirmed_keys)
        ],
    }
    prompt = (
        f"{SENIOR_SCREENWRITER_PROMPT}\n\n"
        "<response_format>Return one native JSON object only. JSON keys remain English.</response_format>\n"
        "<output_schema>Return one valid JSON object with these root keys: reply (string), creative_goal (string), audience (string), logline (string), style_bible (string array), brand_rules (string array), asset_manifest (string array), risks (string array), beats (array), scenes (array). "
        "Each beat is {start_seconds:number,end_seconds:number,title:string,purpose:string}; beats total the requested duration and each is at most five seconds. "
        "Each scene is {id,title,setting,action,dialogue_or_copy,spoken_language,dialogue,on_screen_text,camera_direction,sound_direction,continuity_notes,restrictions,character_keys,environment_key,prop_keys,ui_keys}. "
        "dialogue is [{speaker:string,text:string,on_camera:boolean,voice_description:string,delivery:string}]. voice_description must state the appropriate age/gender presentation, register or timbre, and texture; delivery must state emotion, energy, pace, and performance style. Use empty strings only when no spoken dialogue exists. on_screen_text and restrictions are string arrays; character_keys, prop_keys, and ui_keys are confirmed asset-key arrays; environment_key is one confirmed asset key or an empty string. "
        "Every scene needs concrete title, setting, action, camera_direction, sound_direction, continuity_notes, and at least one confirmed asset binding. "
        "The application creates the Working Script from scenes, so do not return raw_script. Every scene must be detailed enough for a Director to form a video prompt without guessing action, camera, sound, or continuity.</output_schema>\n"
        "<production_contract>" + _safe_json({
            "duration_seconds": production.target_seconds,
            "aspect_ratio": production.aspect_ratio,
            "resolution": production.resolution,
            "output_language": _response_language_hint(production, instruction),
        }) + "</production_contract>\n"
        "<video_setup>" + _safe_json(production.video_setup.model_dump()) + "</video_setup>\n"
        "<existing_script>" + _safe_json(production.script.model_dump(mode="json")) + "</existing_script>\n"
        "<approved_direction>" + _safe_json(approved_direction) + "</approved_direction>\n"
        "<creative_contract>" + _safe_json(production.creative_contract) + "</creative_contract>\n"
        "<confirmed_asset_contract>" + _safe_json(production.asset_contract) + "</confirmed_asset_contract>\n"
        "<brand_asset_inventory>" + _safe_json(brand_names) + "</brand_asset_inventory>\n"
        "<user_instruction>" + (instruction or "Draft the first script.") + "</user_instruction>\n"
        + _output_language_policy(production, instruction)
    )
    try:
        return _parse_json(_call_multimodal_text_model(
            prompt=prompt,
            # The Screenwriter works from the approved strategy and a textual asset
            # inventory. Actual brand media is intentionally reserved for Design.
            parts=[],
            model_id=_production_model(production, "text", get_settings().vertex_video_analysis_model),
            json_response=True,
        ))
    except Exception as exc:
        logger.warning("Video Script Agent unavailable", exc_info=True)
        raise RuntimeError("Screenwriter could not return a valid script. The previous script was kept; please try again.") from exc


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
    _record_script_revision(
        production,
        reason="Screenwriter draft",
        actor_user_id=user.id,
    )
    _refresh_director_prompts_from_script(production)
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


def _director_veo_prompt(
    production: VideoProduction,
    *,
    scene: VideoProductionScene | None,
    beat: VideoProductionBeat,
    duration_seconds: float,
) -> str:
    """Create the Director-owned, editable Veo brief for one locked script moment.

    This is deliberately deterministic: Script supplies the narrative facts and
    the Director turns them into a shot instruction. It avoids a second agent
    inventing people, language, or product claims after the user has locked the
    Working Script.
    """
    if not scene:
        return (
            f"A single clear commercial shot that advances this moment: {beat.purpose}. "
            "Use one stable, readable camera move, no spoken dialogue, and preserve the established visual state."
        )
    dialogue_lines = [
        " ".join(part for part in [
            f"{line.speaker or 'Speaker'} {'speaks on camera' if line.on_camera else 'speaks off camera'} in {scene.spoken_language.strip() or production.video_setup.spoken_language.strip() or 'the confirmed language'}",
            f"with {line.voice_description}" if line.voice_description else "",
            f"and a {line.delivery} delivery" if line.delivery else "",
            f"saying \"{line.text}\".",
        ] if part)
        for line in scene.dialogue
        if line.text.strip()
    ]
    if not dialogue_lines and scene.dialogue_or_copy.strip():
        dialogue_lines = [scene.dialogue_or_copy.strip()]
    scene_text = ". ".join(part for part in [scene.setting.strip() or scene.title, scene.action.strip() or beat.purpose] if part)
    if scene.on_screen_text:
        scene_text += (
            ". Show the exact on-screen subtitle at the bottom safe area in white text with a thin black outline: "
            + " | ".join(scene.on_screen_text)
        )
    dialogue_text = " ".join(dialogue_lines) if dialogue_lines else "No spoken dialogue."
    return " ".join(part for part in [
        scene_text,
        scene.camera_direction.strip() or "Use one stable, readable commercial camera move.",
        dialogue_text,
        scene.sound_direction.strip() or "Use only the sound direction stated in the Working Script.",
        scene.continuity_notes.strip() or "Maintain established identity, props, environment, lighting, palette, and UI placement.",
    ] if part)


def _refresh_director_prompts_from_script(production: VideoProduction) -> None:
    """Refresh stale Director Prompts after a Screenwriter revision.

    A script revision changes the source-of-truth narrative, so existing shot
    prompts must be regenerated before the user reviews them in Storyboard.
    Frame selections remain untouched.
    """
    # A Script is usually written in the user's working language. Do not expose
    # a concatenated Script as a false "Director Veo Prompt": the Director is
    # responsible for producing the final plain-English Veo instruction.
    for shot in production.shots:
        shot.veo_prompt = ""


def _fallback_shots(production: VideoProduction) -> list[VideoProductionShot]:
    beats = production.script.beats
    if not beats:
        raise ValueError("Storyboard cannot be created without a valid locked script.")
    shots = []
    for index, beat in enumerate(beats):
        scene = production.script.scenes[index] if index < len(production.script.scenes) else None
        # Storyboard is an assembly surface, not a second screenplay. Seed each
        # frame directly from the locked script scene so its setting, action,
        # and dialogue remain readable and unchanged for the user to pair with
        # a Scene Builder image.
        shots.append(VideoProductionShot(
            id=f"shot_{uuid4().hex[:8]}",
            order=index + 1,
            scene_id=scene.id if scene else "",
            title=scene.title if scene and scene.title else beat.title,
            start_seconds=beat.start_seconds,
            duration_seconds=max(1, beat.end_seconds - beat.start_seconds),
            purpose=beat.purpose,
            visual=scene.setting if scene else beat.purpose,
            action=scene.action if scene else beat.purpose,
            dialogue_or_copy=scene.dialogue_or_copy if scene else "",
            camera=scene.camera_direction if scene else "",
            veo_prompt="",
            continuity=scene.continuity_notes if scene else "",
            audio_cue=scene.sound_direction if scene else "",
            lighting_rule=(production.design_bible.lighting_and_color_cards[0] if production.design_bible.lighting_and_color_cards else "Maintain the approved lighting and color card."),
            motion_blueprint=(production.design_bible.motion_blueprints[0] if production.design_bible.motion_blueprints else "Start with anticipation, complete one readable action, add micro-motion, and use one deliberate camera move."),
        ))
    return _apply_default_shot_asset_bindings(production, shots)


def lock_script_and_create_storyboard(production_id: str, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    if production.script.structured_raw_script_hash != _script_hash(production.script.raw_script):
        raise ValueError("Working script text changed after the structured scene plan. Use “Restructure draft” before locking so the storyboard matches the reviewed script.")
    # Productions created before the contract fallback existed can have a
    # complete readable Direction but empty JSON contracts. Hydrate from the
    # stored visual inventory so the user is not stranded behind a generic
    # lock error. A script that predates those contracts still goes through the
    # normal explicit binding validation below.
    if not production.creative_contract or not production.asset_contract:
        _ensure_creative_contracts(
            production,
            production.creative_direction.visual_inventory,
            _creative_direction_fallbacks(production, production.brief),
        )
        production = _save(production)
    _reconcile_asset_contract_with_handoff(production)
    creative = CreativeContract.model_validate(production.creative_contract)
    assets = AssetContract.model_validate(production.asset_contract)
    if not production.creative_contract or not production.asset_contract or not assets.assets:
        raise ValueError("Script cannot be locked until Creative Strategist creates a valid Creative Contract and Asset Contract. Run or refresh Creative Direction, then try again.")
    # Repair legacy/current drafts that were written while a malformed
    # Strategist reply had no usable asset contract. Only known contract keys
    # may be attached, and an already explicit valid binding is preserved.
    production.script.scenes = _bind_script_scenes_to_contract(production, production.script.scenes)
    errors = script_asset_validation_errors(
        production.script,
        creative,
        assets,
    )
    if errors:
        raise ValueError("Script cannot be locked: " + " ".join(errors))
    production.script.status = "locked"
    production.script.revision += 1
    production.script.updated_at = utcnow_naive()
    _record_script_revision(
        production,
        reason="Locked production baseline",
        actor_user_id=user.id,
    )
    production.stage = VideoProductionStage.design
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text="The script is locked. Next, the Production Designer will turn it into a visual bible before the Director creates the storyboard.",
    ))
    return _save(production)


def approve_storyboard(production_id: str, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    if production.script.status != "locked":
        raise ValueError("Lock the reviewed script before approving its storyboard.")
    if not production.shots:
        raise ValueError("Create at least one storyboard frame before approval.")
    incomplete = [shot.order for shot in production.shots if not shot.title.strip() or not shot.visual.strip() or not shot.action.strip()]
    if incomplete:
        raise ValueError("Complete title, visual and action for every storyboard frame before approval: " + ", ".join(f"S{order:02d}" for order in incomplete))
    production.storyboard_approved_at = utcnow_naive()
    # `_save` increments the revision, so record the revision that will persist.
    production.storyboard_approved_revision = production.state_revision + 1
    production.stage = VideoProductionStage.generate
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text="Storyboard approved by the team. Keyframe generation is now available for its explicitly reviewed frames.",
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


def _director_prompt_payload(production: VideoProduction, instruction: str, shots: list[VideoProductionShot] | None = None) -> dict[str, object]:
    """Ask the Director for prompts only; frame order and selected Scenes stay user-owned."""
    scenes_by_id = {scene.id: scene for scene in production.script.scenes}
    visual_inputs: list[dict[str, object]] = []
    visual_parts: list[object] = []

    def attach_frame(shot: VideoProductionShot, role: str, asset_id: str | None) -> dict[str, object] | None:
        if not asset_id:
            return None
        asset = _asset_by_id(asset_id)
        if not asset or asset.type != "image":
            return None
        try:
            visual_parts.append(_asset_part_for_text_model(asset))
        except Exception:
            logger.info("Skipping unavailable %s frame for Director shot %s", role, shot.id)
            return None
        item = {
            "sequence": len(visual_inputs) + 1,
            "shot_id": shot.id,
            "role": role,
            "asset_id": asset.id,
            "title": asset.title,
            "dimensions": f"{asset.width}x{asset.height}" if asset.width and asset.height else "unknown",
        }
        visual_inputs.append(item)
        return item

    frames: list[dict[str, object]] = []
    for shot in sorted(shots if shots is not None else production.shots, key=lambda item: item.order):
        frames.append({
            "shot_id": shot.id,
            "order": shot.order,
            "scene_id": shot.scene_id,
            "title": shot.title,
            # Give the model the exact scene next to the ID it must return.
            # This is much less error-prone than asking it to cross-reference
            # a long script object elsewhere in the context.
            "working_script_scene": scenes_by_id[shot.scene_id].model_dump(mode="json") if shot.scene_id in scenes_by_id else {},
            "start_frame": attach_frame(shot, "start", shot.keyframe_asset_id),
            "end_frame": attach_frame(shot, "end", shot.end_keyframe_asset_id),
            "generation_duration_seconds": shot.generation_duration_seconds or (4 if shot.duration_seconds <= 4 else 6 if shot.duration_seconds <= 6 else 8),
        })
    stage_context = (
        "<output_contract>Return JSON with reply and prompts. prompts must contain exactly one item for every storyboard frame: "
        "shot_id, veo_prompt, camera, audio_cue, continuity, first_last_frame_status, first_last_frame_note. veo_prompt must be one concise, plain-English natural-language paragraph for Veo. "
        "Do not use XML, tags, headings, lists, aspect ratio, resolution, quality labels, visual-reference, format, or restrictions. "
        "If a frame's working_script_scene includes non-empty on_screen_text, veo_prompt must include that exact text as a bottom-safe-area subtitle in white type with a thin black outline. "
        "Keep exact dialogue in the confirmed spoken language. Never invent new story facts.</output_contract>\n"
        "<video_setup>" + _safe_json(production.video_setup.model_dump()) + "</video_setup>\n"
        "<locked_script>" + _safe_json(production.script.model_dump(mode="json")) + "</locked_script>\n"
        "<storyboard_frames>" + _safe_json(frames) + "</storyboard_frames>\n"
        "<frame_visual_input_order>" + _safe_json(visual_inputs) + "</frame_visual_input_order>\n"
        "<first_last_frame_policy>For a frame with both attached start and end images, inspect that exact pair before writing the prompt. Return first_last_frame_status=ready only when identity, setting, lighting, camera geometry, and movement distance can plausibly connect in the supplied duration. When ready, the English Veo Prompt must state one single continuous shot, the subject's step-by-step path from start to end, matching camera tracking or pan, fluid motion, no cuts, and no teleportation. If the pair has a large spatial jump, incompatible camera/background geometry, or incompatible identity/lighting, return first_last_frame_status=needs_intermediate and a concise first_last_frame_note explaining the bridging frame required. Do not claim the pair will be seamless. For frames without an end image, return first_last_frame_status=not_set and an empty note.</first_last_frame_policy>\n"
        "<design_bible>" + _safe_json(production.design_bible.model_dump(mode="json")) + "</design_bible>"
    )
    return _role_payload(
        production,
        role_prompt=STORYBOARD_DIRECTOR_PROMPT,
        instruction=instruction or "Generate Director Veo Prompts for every locked Working Script moment.",
        include_asset_parts=True,
        include_contracts=False,
        parts_override=visual_parts,
        stage_context=stage_context,
        language_policy=(
            "<language_policy>Write reply, camera, audio_cue, and continuity in the user's latest input language. "
            "Every veo_prompt value MUST be a concise, plain-English natural-language paragraph because it is sent directly to Veo. "
            "Keep quoted dialogue verbatim in its confirmed spoken language. JSON keys remain English.</language_policy>"
        ),
    )


def _director_prompt_items(payload: dict[str, object]) -> list[dict[str, object]]:
    """Accept narrowly compatible Director responses while the prompt contract settles.

    The canonical field is ``prompts``. The alternatives cover older saved
    prompt versions without weakening the new model contract, and let the
    caller fall back to the deterministic Script composer instead of 500ing.
    """
    # Gemini's JSON mode is reliable, but older saved prompt versions and
    # occasional model replies wrap the array in `data`/`result` or stringify
    # it. Normalise those harmless shape differences here; the caller still
    # enforces exactly one usable prompt per storyboard frame.
    candidates: list[dict[str, object]] = [payload]
    for wrapper in ("data", "result", "output"):
        nested = payload.get(wrapper)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for key in ("prompts", "director_prompts", "frames", "shots"):
            items = _expand_list_value(candidate.get(key))
            dict_items = [item for item in items if isinstance(item, dict)]
            if dict_items:
                return dict_items
    return []


def run_director_agent(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    message = request.message.strip()
    if message:
        production.conversation.append(VideoProductionConversationMessage(role="user", text=message))
    if not production.shots:
        production.shots = _fallback_shots(production)
    requested_ids = set(request.shot_ids)
    target_shots = [shot for shot in production.shots if not requested_ids or shot.id in requested_ids]
    if requested_ids and not target_shots:
        raise ValueError("The requested storyboard frame no longer exists.")
    payload = _director_prompt_payload(production, message, target_shots)
    prompts = _director_prompt_items(payload)
    ordered_shots = sorted(target_shots, key=lambda shot: shot.order)
    shots_by_id = {shot.id: shot for shot in ordered_shots}
    shots_by_scene_id = {shot.scene_id: shot for shot in ordered_shots if shot.scene_id}
    shots_by_order = {shot.order: shot for shot in ordered_shots}
    updated_ids: set[str] = set()
    for index, item in enumerate(prompts):
        if not isinstance(item, dict):
            continue
        shot = shots_by_id.get(str(item.get("shot_id") or ""))
        if not shot:
            shot = shots_by_scene_id.get(str(item.get("scene_id") or ""))
        if not shot:
            try:
                shot = shots_by_order.get(int(item.get("order") or item.get("frame_order") or 0))
            except (TypeError, ValueError):
                shot = None
        # If Gemini preserved the order and returned one item per frame, use
        # that order rather than discarding an otherwise valid English prompt.
        if not shot and len(prompts) == len(ordered_shots):
            shot = ordered_shots[index]
        prompt = str(item.get("veo_prompt") or item.get("director_prompt") or item.get("prompt") or "").strip()
        if not shot or not prompt:
            continue
        shot.veo_prompt = prompt
        shot.camera = str(item.get("camera") or shot.camera)
        shot.audio_cue = str(item.get("audio_cue") or shot.audio_cue)
        shot.continuity = str(item.get("continuity") or shot.continuity)
        if shot.end_keyframe_asset_id:
            status = str(item.get("first_last_frame_status") or "").strip().lower()
            shot.first_last_frame_status = status if status in {"ready", "needs_intermediate"} else "ready"
            shot.first_last_frame_note = str(item.get("first_last_frame_note") or "").strip()
        else:
            shot.first_last_frame_status = "not_set"
            shot.first_last_frame_note = ""
        updated_ids.add(shot.id)
    if len(updated_ids) != len(target_shots):
        missing = len(target_shots) - len(updated_ids)
        logger.warning(
            "Storyboard Director returned prompts for only %s of %s frames; %s frame(s) were missing. No prompts were saved.",
            len(updated_ids), len(target_shots), missing,
        )
        raise ValueError(
            f"Director Prompt generation returned {len(updated_ids)} of {len(target_shots)} English prompts. "
            f"No prompts were saved; please try Generate all Director Prompts again."
        )
    production.stage = VideoProductionStage.storyboard
    reply = str(payload.get("reply") or "Director Veo Prompts were generated for every locked Working Script moment. Review and edit them in Video generate before creating videos.")
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
    if "keyframe_asset_id" in request.model_fields_set or "end_keyframe_asset_id" in request.model_fields_set:
        # A manually chosen start Scene supersedes any extracted bridge-frame
        # lineage.  Keep the bridge image in Library, but do not present it as
        # the active continuity source for this shot any longer.
        if "keyframe_asset_id" in request.model_fields_set:
            shot.bridge_source_video_asset_id = None
            shot.bridge_timestamp_seconds = None
        shot.first_last_frame_status = "not_set"
        shot.first_last_frame_note = ""
        # A Take belongs to one exact Start/End Scene pair. Keep it attached
        # and visibly stale so users can compare it, trim it, or keep it in an
        # existing cut. Never erase costly work merely because a source image
        # changed.
        shot.take_outdated = bool(shot.video_asset_ids)
        shot.video_job_id = None
        shot.status = "approved" if shot.keyframe_asset_id else "draft"
        production.final_asset_id = None
    if shot.selected_video_asset_id and shot.selected_video_asset_id not in shot.video_asset_ids:
        raise ValueError("Choose a generated take that belongs to this storyboard frame.")
    _invalidate_storyboard_approval(production)
    return _save(production)


def extract_video_production_bridge_frame(
    production_id: str,
    shot_id: str,
    request: VideoProductionBridgeFrameRequest,
    user: User,
) -> VideoProduction:
    """Extract a reviewed frame from one Take and use it as the next start frame.

    This is intentionally user-driven: the system never guesses which frame is
    usable.  The extracted image is a normal Library asset with lineage back to
    the Take, so it can be inspected, replaced, or reused later.
    """
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    source_shot = next((item for item in production.shots if item.id == shot_id), None)
    if not source_shot:
        raise KeyError("Storyboard frame not found")
    ordered = sorted(production.shots, key=lambda item: item.order)
    source_index = next((index for index, item in enumerate(ordered) if item.id == source_shot.id), -1)
    target = next((item for item in ordered if item.id == request.target_shot_id), None) if request.target_shot_id else (
        ordered[source_index + 1] if 0 <= source_index < len(ordered) - 1 else None
    )
    if not target:
        raise ValueError("Choose a later storyboard frame to receive this bridge frame.")
    if target.order <= source_shot.order:
        raise ValueError("A bridge frame can only continue into a later storyboard frame.")

    take_id = request.source_video_asset_id or source_shot.selected_video_asset_id or (
        source_shot.video_asset_ids[0] if source_shot.video_asset_ids else None
    )
    if not take_id or take_id not in source_shot.video_asset_ids:
        raise ValueError("Choose a generated Take from this storyboard frame before extracting a bridge frame.")
    take = _asset_by_id(take_id)
    if not take or take.type != "video":
        raise ValueError("The selected bridge source is not a readable video Take.")
    duration = float(source_shot.generation_duration_seconds or (4 if source_shot.duration_seconds <= 4 else 6 if source_shot.duration_seconds <= 6 else 8))
    timestamp = round(float(request.timestamp_seconds), 3)
    if timestamp < 0 or timestamp >= duration:
        raise ValueError(f"Choose a frame between 0.0s and {max(duration - 0.01, 0):.2f}s of this Take.")
    content = _load_asset_bytes(take)
    if not content:
        raise ValueError("The selected Take could not be read. Refresh the Library and try again.")

    with tempfile.TemporaryDirectory(prefix="incept-bridge-frame-") as directory:
        root = Path(directory)
        source_path = root / "take.mp4"
        output_path = root / "bridge.png"
        source_path.write_bytes(content)
        result = subprocess.run(
            [
                _ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(source_path), "-ss", f"{timestamp:.3f}", "-frames:v", "1",
                "-pix_fmt", "rgb24", str(output_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0 or not output_path.is_file():
            detail = result.stderr.decode("utf-8", errors="replace")[-500:]
            raise RuntimeError(f"Could not extract the bridge frame. {detail}")
        image_content = output_path.read_bytes()

    created_at = utcnow_naive()
    asset_id = f"asset_bridge_{uuid4().hex[:12]}"
    preview_url = _save_image_file(asset_id, base64.b64encode(image_content).decode("ascii"))
    width, height = _guess_video_dimensions(production.aspect_ratio, production.resolution)
    bridge_asset = Asset(
        id=asset_id,
        title=f"{production.title}_S{source_shot.order:02d}_bridge_{timestamp:.2f}s",
        type="image",
        gcs_uri="",
        preview_url=preview_url,
        provider="ffmpeg",
        model="video-bridge-frame",
        workspace_id=production.workspace_id,
        job_id="",
        prompt_hash="",
        created_by=user.id,
        created_at=created_at,
        width=width,
        height=height,
        asset_role=AssetRole.working,
        parent_asset_id=take.id,
        root_asset_id=_inherit_root_asset_id(take, asset_id),
        analysis={
            "video_production_id": production_id,
            "kind": "bridge_frame",
            "source_shot_id": source_shot.id,
            "source_video_asset_id": take.id,
            "timestamp_seconds": timestamp,
            "target_shot_id": target.id,
        },
    )
    bridge_asset.gcs_uri = _upload_bytes_to_gcs(
        content=image_content,
        object_path=_build_gcs_object_path(
            category="generated",
            workspace_id=production.workspace_id,
            created_at=created_at,
            filename=f"{asset_id}.png",
        ),
        content_type="image/png",
    ) or f"local://generated/{asset_id}.png"
    _record_asset_storage_status(bridge_asset, category="generated")
    ASSETS[asset_id] = bridge_asset
    upsert_asset(bridge_asset)

    # Updating one downstream start state never deletes the user's previous
    # scenes or Takes. It only marks the affected Take stale and asks the
    # Director to re-evaluate the new first/last relationship.
    target.keyframe_asset_id = asset_id
    target.bridge_source_video_asset_id = take.id
    target.bridge_timestamp_seconds = timestamp
    target.first_last_frame_status = "not_set"
    target.first_last_frame_note = "Bridge frame extracted from the previous Take. Refresh the Director Prompt to evaluate this new start/end pair."
    target.take_outdated = bool(target.video_asset_ids)
    target.video_job_id = None
    target.status = "approved"
    production.final_asset_id = None
    production.stage = VideoProductionStage.storyboard
    _invalidate_storyboard_approval(production)
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text=(f"Extracted a bridge frame at {timestamp:.2f}s from S{source_shot.order:02d} and set it as the start Scene for S{target.order:02d}. "
              "Refresh that Director Prompt before regenerating the affected shot."),
    ))
    return _save(production)


def create_video_production_shot(production_id: str, request: VideoProductionShotCreateRequest, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    start_seconds = sum(max(0, shot.duration_seconds) for shot in production.shots)
    production.shots.append(VideoProductionShot(
        id=f"shot_{uuid4().hex[:10]}", scene_id="", order=len(production.shots) + 1,
        start_seconds=start_seconds, duration_seconds=request.duration_seconds, title=request.title.strip(),
        purpose=request.purpose.strip(), visual=request.visual.strip(), action=request.action.strip(), status="draft",
    ))
    production.stage = VideoProductionStage.storyboard
    _invalidate_storyboard_approval(production)
    return _save(production)


def delete_video_production_shot(production_id: str, shot_id: str, user: User) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    before = len(production.shots)
    production.shots = [shot for shot in production.shots if shot.id != shot_id]
    if len(production.shots) == before:
        raise KeyError("Shot not found")
    start_seconds = 0.0
    for order, shot in enumerate(production.shots, start=1):
        shot.order = order
        shot.start_seconds = start_seconds
        start_seconds += max(0, shot.duration_seconds)
    _invalidate_storyboard_approval(production)
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
    _invalidate_storyboard_approval(production)
    return _save(production)


def _production_job(*, production: VideoProduction, shot: VideoProductionShot, kind: str) -> GenerationJob:
    now = utcnow_naive()
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


def _design_sheet_size(production: VideoProduction, sheet: VideoProductionDesignSheet) -> str:
    """Asset sheets stay square; scene compositions use their delivery framing."""
    if sheet.design_mode == "scene":
        ratio = production.aspect_ratio if sheet.output_aspect_ratio == "project" else sheet.output_aspect_ratio
        return "1920x1080" if ratio == "16:9" else "1080x1920"
    return "2048x2048"


def _production_image_request(
    production: VideoProduction,
    *,
    prompt: str,
    output_size: str,
    user: User,
) -> GenerationRequest:
    """Use the normal Studio image admission/accounting contract for Video."""
    settings = get_settings()
    return GenerationRequest(
        workspace_id=production.workspace_id,
        prompt=prompt,
        provider="gemini",
        model=_production_model(production, "image", settings.vertex_gemini_image_model),
        variants=1,
        created_by=user.id,
        theme="Video workflow",
        output_sizes=[output_size],
        output_format="image",
    )


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


def create_custom_design_sheet(
    production_id: str,
    request: VideoProductionDesignSheetCreateRequest,
    user: User,
) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    source_ids = [
        asset_id for asset_id in request.source_asset_ids
        if (asset := _asset_by_id(asset_id)) is not None and asset.type in {"image", "gif"}
    ]
    valid_scene_ids = {scene.id for scene in production.script.scenes}
    sheet = VideoProductionDesignSheet(
        id=f"design_{uuid4().hex[:8]}",
        title=request.title.strip(),
        kind="character_consistency" if request.asset_pack_type == "character" else "scene_style",
        asset_pack_type=request.asset_pack_type,
        purpose=request.purpose.strip(),
        reason_for_new_pack="Created manually by the user.",
        user_authored=True,
        design_mode=request.design_mode,
        output_aspect_ratio=request.output_aspect_ratio,
        handoff_key=_handoff_key(request.title, f"custom_pack_{uuid4().hex[:6]}"),
        source_mode="brand_asset" if source_ids else "prompt_only",
        source_notes="User-selected source image(s)." if source_ids else "User-authored prompt only.",
        prompt=request.prompt.strip(),
        asset_ids=list(dict.fromkeys(source_ids)),
        scene_ids=[scene_id for scene_id in request.scene_ids if scene_id in valid_scene_ids],
    )
    production.design_bible.asset_packs.append(sheet)
    _hydrate_asset_pack_inventory(production)
    production.stage = VideoProductionStage.design
    return _save(production)


def _is_user_authored_sheet(sheet: VideoProductionDesignSheet) -> bool:
    """Recognise new explicit custom packs and preserve older manual packs."""
    return sheet.user_authored or sheet.reason_for_new_pack == "Created manually by the user."


_LEGACY_CUSTOM_CHARACTER_SUFFIX = (
    "Use the shared neutral identity-board background: simple warm-gray studio cyclorama, "
    "soft even lighting, no scenery or final-story location."
)


def _restore_user_authored_prompt(sheet: VideoProductionDesignSheet) -> None:
    """Remove the one legacy suffix that older releases wrote into custom prompts."""
    if not _is_user_authored_sheet(sheet):
        return
    suffix = _LEGACY_CUSTOM_CHARACTER_SUFFIX.lower()
    if sheet.prompt.lower().endswith(suffix):
        sheet.prompt = sheet.prompt[: -len(_LEGACY_CUSTOM_CHARACTER_SUFFIX)].rstrip()


def _should_split_design_output(sheet: VideoProductionDesignSheet) -> bool:
    """Split standard boards and user-requested custom 2x2 boards into panels."""
    if not _is_user_authored_sheet(sheet):
        return True
    if sheet.design_mode == "scene":
        return False
    return bool(re.search(r"(?:2\s*[x×]\s*2|contact\s*sheet|four[-\s]*panel|四宫格|四格)", sheet.prompt, re.IGNORECASE))


def update_custom_design_sheet(
    production_id: str,
    sheet_id: str,
    request: VideoProductionDesignSheetUpdateRequest,
    user: User,
) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    sheet = _find_design_sheet(production, sheet_id)
    if not sheet:
        raise KeyError("Design pack not found")
    changes = request.model_dump(exclude_unset=True)
    reset_candidate = any(key in changes for key in {"asset_pack_type", "prompt", "source_asset_ids", "design_mode", "output_aspect_ratio"})
    if "title" in changes:
        sheet.title = str(changes["title"]).strip()
    if "asset_pack_type" in changes:
        sheet.asset_pack_type = changes["asset_pack_type"]
        sheet.kind = "character_consistency" if sheet.asset_pack_type == "character" else "scene_style"
    if "purpose" in changes:
        sheet.purpose = str(changes["purpose"] or "").strip()
    if "prompt" in changes:
        sheet.prompt = str(changes["prompt"] or "").strip()
    if "source_asset_ids" in changes:
        sheet.asset_ids = list(dict.fromkeys(
            asset_id for asset_id in (changes["source_asset_ids"] or [])
            if (asset := _asset_by_id(asset_id)) is not None and asset.type in {"image", "gif"}
        ))
        sheet.source_mode = "brand_asset" if sheet.asset_ids else "prompt_only"
        sheet.source_notes = "User-selected source image(s)." if sheet.asset_ids else "User-authored prompt only."
    if "scene_ids" in changes:
        valid_scene_ids = {scene.id for scene in production.script.scenes}
        sheet.scene_ids = [scene_id for scene_id in (changes["scene_ids"] or []) if scene_id in valid_scene_ids]
    if "design_mode" in changes:
        sheet.design_mode = changes["design_mode"]
    if "output_aspect_ratio" in changes:
        sheet.output_aspect_ratio = changes["output_aspect_ratio"]
    if reset_candidate:
        sheet.grid_asset_id = None
        sheet.panel_asset_ids = []
        sheet.selected_panel = None
        sheet.selected_asset_id = None
        sheet.approved_panel_asset_ids = {}
        sheet.approved_asset_ids = []
        sheet.job_id = None
        sheet.failure_reason = None
        sheet.status = "draft"
    _hydrate_asset_pack_inventory(production)
    return _save(production)


def delete_custom_design_sheet(production_id: str, sheet_id: str, user: User) -> None:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    before = len(production.design_bible.asset_packs)
    production.design_bible.asset_packs = [sheet for sheet in production.design_bible.asset_packs if sheet.id != sheet_id]
    if len(production.design_bible.asset_packs) == before:
        raise KeyError("Design pack not found")
    _hydrate_asset_pack_inventory(production)
    _save(production)


def _scene_reframe_size(
    production: VideoProduction,
    output_aspect_ratio: str,
) -> str:
    ratio = production.aspect_ratio if output_aspect_ratio == "project" else output_aspect_ratio
    return "1920x1080" if ratio == "16:9" else "1080x1920"


def create_scene_reframe_job(
    production_id: str,
    request: VideoProductionSceneReframeRequest,
    user: User,
) -> tuple[GenerationJob, VideoProductionDesignSheet]:
    """Create a Gemini image-to-image Scene version at an explicit delivery ratio."""
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    source_asset = _asset_by_id(request.source_asset_id)
    if not source_asset or source_asset.type not in {"image", "gif"}:
        raise ValueError("Choose an existing Scene image to reframe.")

    target_size = _scene_reframe_size(production, request.output_aspect_ratio)
    target_ratio = production.aspect_ratio if request.output_aspect_ratio == "project" else request.output_aspect_ratio
    preserve_prompt = (
        f"以附图为唯一参考。保证图中所有内容不变，只将画面比例扩展为 {target_ratio}（{target_size}）。"
        "不要增加、删除、替换或修改任何人物、物体、文字、构图、光线、颜色或风格。"
    )
    sheet = VideoProductionDesignSheet(
        id=f"design_{uuid4().hex[:8]}",
        title=f"{source_asset.title or 'Scene'} · Reframed {target_ratio}",
        kind="scene_style",
        asset_pack_type="environment",
        purpose=f"A {target_ratio} scene version that preserves the selected original composition.",
        reason_for_new_pack="Created by Reframe from a selected Scene image.",
        user_authored=True,
        design_mode="scene",
        output_aspect_ratio=request.output_aspect_ratio,
        handoff_key=_handoff_key(source_asset.title or "scene", f"reframe_{uuid4().hex[:6]}"),
        source_mode="brand_asset",
        source_notes=f"Reframed from the existing Scene image: {source_asset.title or source_asset.id}.",
        prompt=preserve_prompt,
        asset_ids=[source_asset.id],
        status="draft",
    )
    production.design_bible.asset_packs.append(sheet)
    production.stage = VideoProductionStage.design
    _save(production)
    # Reuse the standard Designer image chain: Gemini Flash Image receives the
    # selected Scene as its sole image reference and generates the exact target
    # dimensions. This intentionally avoids the OpenAI outpaint adapter.
    job = create_design_sheet_job(production_id, sheet.id, user)
    return job, sheet


async def run_scene_reframe_background(
    production_id: str,
    sheet_id: str,
    job_id: str,
    user: User,
) -> None:
    """Run reframe through the same Gemini Designer job as every Scene."""
    await run_design_sheet_background(production_id, sheet_id, job_id, user)


def _design_sheet_asset_ids(production: VideoProduction, sheet: VideoProductionDesignSheet) -> list[str]:
    explicit_source_ids = [
        asset_id for asset_id in sheet.asset_ids
        if (asset := _asset_by_id(asset_id)) is not None and asset.type in {"image", "gif"}
    ]
    if explicit_source_ids:
        return list(dict.fromkeys(explicit_source_ids))[:4]
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
    if sheet.asset_pack_type == "prop":
        return _prop_pack_asset_ids(production, sheet.asset_ids)
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


def _character_identity_prompt(production: VideoProduction, handoff_key: str) -> str:
    """Compile the immutable Creative Contract identity into an image prompt."""
    characters = production.creative_contract.get("characters", []) if isinstance(production.creative_contract, dict) else []
    character = next((item for item in characters if isinstance(item, dict) and item.get("character_key") == handoff_key), None)
    if not character:
        return ""
    fields = [
        ("cultural context", ", ".join(character.get("cultural_context", []))),
        ("age range", character.get("age_range", "")),
        ("presentation", character.get("presentation", "")),
        ("face and skin guidance", character.get("face_and_skin_guidance", "")),
        ("hair and makeup", character.get("hair_and_makeup", "")),
        ("wardrobe", character.get("wardrobe", "")),
        ("body and accessories", character.get("body_and_accessories", "")),
        ("performance", character.get("performance", "")),
    ]
    details = "; ".join(f"{label}: {value}" for label, value in fields if value)
    return f"Immutable Character Identity Contract: {details}. Preserve these traits in every panel. " if details else ""


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
        "CHARACTER": "All four panels must show the identical character identity: matching facial structure, hairstyle, makeup, skin tone, wardrobe, body proportions, and accessories. Use the shared neutral identity-board background in every panel: a simple warm-gray studio cyclorama, soft even lighting, and no location cues, furniture, scenery, or final-story environment.",
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
    character_background_rule = (
        "For this CHARACTER Pack, ignore any cafe, street, shop, game-world, or final-scene background wording in the production instruction. "
        "Lock the person only against the shared neutral identity-board background so this reference can be composited into the approved Environment Pack later. "
        if pack_type == "CHARACTER" else ""
    )
    identity_contract = _character_identity_prompt(production, sheet.handoff_key) if pack_type == "CHARACTER" else ""
    return (
        "You are a Lead Pre-Visualization Art Director creating controlled asset sheets for an AI video production. "
        "Create exactly ONE square 1:1 2x2 contact sheet with four equal panels, thin neutral gutters, and no text, labels, captions, watermarks, or UI chrome. "
        f"Asset pack type: {pack_type}. Sheet title: {sheet.title}. Purpose: {sheet.purpose}. "
        f"Production instruction: {sheet.prompt}. Approved visual rules: {rules}. "
        f"Required panel layout: {panel_plan}. {consistency_rule} {identity_contract}{prop_isolation}{character_background_rule}"
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
    _restore_user_authored_prompt(sheet)
    if not _is_user_authored_sheet(sheet):
        _normalize_design_sheet_for_asset_grid(sheet)
    if (
        not _is_user_authored_sheet(sheet)
        and sheet.asset_pack_type == "character"
        and "shared neutral identity-board background" not in sheet.prompt.lower()
    ):
        sheet.prompt = (
            f"{sheet.prompt.rstrip()} "
            "Use the shared neutral identity-board background: simple warm-gray studio cyclorama, soft even lighting, no scenery or final-story location."
        ).strip()
    if sheet.asset_pack_type == "prop":
        resolved_asset_ids = _design_sheet_asset_ids(production, sheet)
        if sheet.source_mode == "brand_asset" and not resolved_asset_ids:
            sheet.status = "draft"
            sheet.job_id = None
            _save(production)
            raise ValueError(
                "This Prop Pack needs a static product image in Brand Assets before it can be generated."
            )
        if resolved_asset_ids:
            sheet.asset_ids = resolved_asset_ids
    budget_prompt = sheet.prompt if _is_user_authored_sheet(sheet) else _design_sheet_grid_prompt(production, sheet)
    assert_image_budget_available(
        _production_image_request(
            production,
            prompt=budget_prompt,
            output_size=_design_sheet_size(production, sheet),
            user=user,
        ),
        user,
    )
    now = utcnow_naive()
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
    sheet.failure_reason = None
    sheet.selected_panel = None
    sheet.selected_asset_id = None
    sheet.approved_panel_asset_ids = {}
    sheet.approved_asset_ids = []
    sheet.panel_asset_ids = []
    sheet.grid_asset_id = None
    _save(production)
    return job


def cancel_design_sheet_generation(
    production_id: str,
    sheet_id: str,
    user: User,
) -> VideoProduction:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    sheet = _find_design_sheet(production, sheet_id)
    if not sheet:
        raise KeyError("Design sheet not found")
    job = JOBS.get(sheet.job_id or "")
    if job and job.status in {JobStatus.running, JobStatus.queued}:
        job.status = JobStatus.failed
        job.progress = 0
        job.message = "Cancelled by user"
        job.updated_at = utcnow_naive()
        upsert_job(job)
    sheet.status = "failed"
    sheet.failure_reason = "Generation stopped by user. You can adjust the sources or prompt and generate again."
    production.conversation.append(VideoProductionConversationMessage(
        role="assistant",
        text=f"Stopped generation for '{sheet.title}'. The previous image, if any, was kept unchanged.",
    ))
    return _save(production)


async def run_design_sheet_background(production_id: str, sheet_id: str, job_id: str, user: User) -> None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    job = JOBS.get(job_id)
    if not production or not job:
        return
    sheet = _find_design_sheet(production, sheet_id)
    if not sheet:
        return
    settings = get_settings()
    image_model = _production_model(production, "image", settings.vertex_gemini_image_model)
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
        # A prompt-only AI Prop Pack can lock an original recurring object. A
        # supplied image is only mandatory when the contract explicitly asks
        # to reproduce a branded product asset.
        if not reference_bytes and sheet.asset_pack_type == "prop" and sheet.source_mode == "brand_asset":
            raise RuntimeError(
                "Attach an image Brand Asset, or refresh Creative Direction so Design can extract approved frames from a Creative Reference video."
            )
        grid_prompt = sheet.prompt if _is_user_authored_sheet(sheet) else _design_sheet_grid_prompt(production, sheet)
        _mark_generation_progress(job, 20, f"Generating {'custom image' if _is_user_authored_sheet(sheet) else 'controlled 2x2 consistency sheet'}: {sheet.title}…")
        response = await _dispatch_generation(
            grid_prompt,
            provider="gemini",
            model=image_model,
            variants=1,
            reference_images=reference_bytes,
            target_size=_design_sheet_size(production, sheet),
            # Asset Packs are visual ingredients, not final still delivery.
            # 2K keeps a 2048px 2x2 board usable while avoiding the long 4K
            # Gemini queue and export time for every reusable Pack.
            image_size="2K",
        )
        # A cancellation cannot interrupt the provider's in-flight request, but
        # it must prevent a late response from changing this Pack afterward.
        if job.status == JobStatus.failed and job.message == "Cancelled by user":
            return
        image = next((item for item in response if item), None)
        if not image:
            raise RuntimeError("Gemini Image returned no custom image." if _is_user_authored_sheet(sheet) else "Gemini Image returned no controlled 2x2 consistency sheet.")
        raw_grid = base64.b64decode(image)
        _mark_generation_progress(job, 82, f"Saving {'custom image' if _is_user_authored_sheet(sheet) else 'controlled 2x2 consistency sheet'}: {sheet.title}…")
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
            model=image_model,
            label=f"{production.title}_{sheet.title}_asset_sheet",
            theme="Video Production Design Asset Sheet",
            requested_sizes=[_design_sheet_size(production, sheet)],
            source_asset=source_asset,
            context_assets=[asset for asset_id in context_asset_ids if (asset := _asset_by_id(asset_id))],
        )
        if len(assets) != 1:
            raise RuntimeError("Could not save the custom image." if _is_user_authored_sheet(sheet) else "Could not save the controlled 2x2 consistency sheet.")
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
        panel_assets: list[Asset] = []
        split_into_panels = _should_split_design_output(sheet)
        if split_into_panels:
            # A generated 2x2 board is a candidate library, not an approval
            # gate. Export every quadrant immediately so Scene Builder can use
            # any combination of A/B/C/D without a separate crop-and-approve
            # loop.
            from io import BytesIO
            from PIL import Image
            with Image.open(BytesIO(raw_grid)) as image:
                image.load()
                width, height = image.size
                raw_panels: list[bytes] = []
                for panel in range(4):
                    column, row = panel % 2, panel // 2
                    cropped = image.crop((
                        round(width * column / 2), round(height * row / 2),
                        round(width * (column + 1) / 2), round(height * (row + 1) / 2),
                    )).convert("RGB")
                    candidate_bytes = BytesIO()
                    cropped.save(candidate_bytes, format="PNG")
                    raw_panels.append(candidate_bytes.getvalue())
            panel_job = job.model_copy(deep=True)
            panel_job.lineage_key = f"{job.lineage_key}_panels"
            panel_assets = await _export_master_images_to_assets(
                job=panel_job,
                raw_outputs=raw_panels,
                workspace_id=production.workspace_id,
                created_by=user.id,
                provider="gemini",
                model=image_model,
                label=f"{production.title}_{sheet.title}_panel",
                theme="Video Production Design Candidate",
                requested_sizes=[f"{max(1, width // 2)}x{max(1, height // 2)}"],
                source_asset=grid_asset,
                context_assets=[grid_asset],
            )
            for panel, candidate_asset in enumerate(panel_assets):
                candidate_asset.analysis = {
                    **(candidate_asset.analysis or {}),
                    "video_production_id": production_id,
                    "design_sheet_id": sheet_id,
                    "kind": "design_sheet_keyframe_reference",
                    "panel": panel,
                    "prompt": grid_prompt,
                    "source_grid_asset_id": grid_asset.id,
                }
                upsert_asset(candidate_asset)
        job.output_asset_ids = [grid_asset.id, *[asset.id for asset in panel_assets]]
        _record_usage(
            job,
            _production_image_request(
                production,
                prompt=grid_prompt,
                output_size=_design_sheet_size(production, sheet),
                user=user,
            ),
            user,
            image_model,
            "",
            utcnow_naive(),
        )
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"{'Custom image' if _is_user_authored_sheet(sheet) else 'Controlled 2x2 consistency sheet'} ready: {sheet.title}."
        job.updated_at = utcnow_naive()
        upsert_job(job)
        sheet.panel_asset_ids = [asset.id for asset in panel_assets]
        sheet.grid_asset_id = grid_asset.id
        sheet.selected_panel = 0 if not split_into_panels else None
        sheet.selected_asset_id = grid_asset.id if not split_into_panels else None
        sheet.approved_panel_asset_ids = (
            {str(index): asset.id for index, asset in enumerate(panel_assets)}
            if split_into_panels else {"0": grid_asset.id}
        )
        sheet.approved_asset_ids = [asset.id for asset in panel_assets] if split_into_panels else [grid_asset.id]
        sheet.status = "approved"
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text=(
                f"The 2x2 asset sheet for '{sheet.title}' is ready. A, B, C, and D are now all available as approved visual ingredients in Scene Builder."
                if split_into_panels
                else f"The image for '{sheet.title}' is ready and available in Storyboard."
            ),
        ))
        _save(production)
    except Exception as exc:
        logger.exception("Video production design sheet failed for %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"Design asset sheet generation failed: {exc}"[:500]
        job.updated_at = utcnow_naive()
        upsert_job(job)
        sheet.status = "failed"
        sheet.failure_reason = job.message
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
        now = utcnow_naive()
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

    if _is_user_authored_sheet(sheet):
        if not sheet.grid_asset_id:
            raise ValueError("Generate the custom image before selecting it.")
        source_asset = _asset_by_id(sheet.grid_asset_id)
        if not source_asset:
            raise KeyError("The custom design image could not be found.")
        sheet.selected_panel = 0
        sheet.selected_asset_id = source_asset.id
        sheet.approved_panel_asset_ids = {"0": source_asset.id}
        sheet.approved_asset_ids = [source_asset.id]
        sheet.status = "approved"
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text=f"Selected the exact user-authored image for '{sheet.title}'.",
        ))
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

    now = utcnow_naive()
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
        model=_production_model(production, "image", get_settings().vertex_gemini_image_model),
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
    """Keep the saved Director Prompt as the dominant, editable Veo input.

    Earlier versions re-injected the whole script and design bible here. That
    duplicated multilingual audio instructions and diluted the carefully
    composed English prompt. The images are already sent as API inputs, so
    only add a short continuity guard that the user has not had to repeat.
    """
    guard = (
        "Preserve the supplied visual reference: same subjects, products, setting, lighting, palette, and composition. "
        "Do not introduce extra people, logos, on-screen copy, wardrobe changes, or a split screen."
    )
    if shot.end_keyframe_asset_id:
        guard += " Treat the ending image as a hard final composition. Use one continuous physically plausible movement with matching camera tracking; no hard cut, teleportation, or freeze-frame transition."
    return f"{shot.veo_prompt.strip()}\n\n{guard}".strip()


def create_keyframe_job(production_id: str, shot_id: str, user: User) -> GenerationJob:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    if not production.storyboard_approved_at:
        raise ValueError("Approve the reviewed storyboard before generating a keyframe.")
    shot = next((item for item in production.shots if item.id == shot_id), None)
    if not shot:
        raise KeyError("Shot not found")
    assert_image_budget_available(
        _production_image_request(
            production,
            prompt=_keyframe_prompt(production, shot),
            output_size=_keyframe_size(production),
            user=user,
        ),
        user,
    )
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
    image_model = _production_model(production, "image", settings.vertex_gemini_image_model)
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
                model=image_model,
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
            model=image_model,
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
        _record_usage(
            job,
            _production_image_request(
                production,
                prompt=_keyframe_prompt(production, shot),
                output_size=_keyframe_size(production),
                user=user,
            ),
            user,
            image_model,
            "",
            utcnow_naive(),
        )
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Keyframe ready for S{shot.order:02d}. Review and approve it before video generation."
        job.updated_at = utcnow_naive()
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
        job.updated_at = utcnow_naive()
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
        updated_at=utcnow_naive(),
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
    production.stage = VideoProductionStage.audio
    reply = str(payload.get("reply") or "I prepared an instrumental soundtrack blueprint. Review the cue sheet, then generate a Lyria music preview for the edit.")
    production.conversation.append(VideoProductionConversationMessage(role="assistant", text=reply))
    return _save(production)


def _generate_lyria_music(prompt: str, model: str) -> bytes:
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
            "model": model,
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
    now = utcnow_naive()
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
    production.stage = VideoProductionStage.audio
    _save(production)
    return job


async def run_production_audio_background(production_id: str, job_id: str, user: User) -> None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    job = JOBS.get(job_id)
    if not production or not job:
        return
    try:
        _mark_generation_progress(job, 20, "Generating the instrumental soundtrack with Lyria…")
        audio_model = _production_model(production, "audio", get_settings().vertex_lyria_model)
        content = await asyncio.to_thread(_generate_lyria_music, production.audio_plan.music_prompt, audio_model)
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
            model=audio_model,
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
        production.audio_plan.updated_at = utcnow_naive()
        job.output_asset_ids = [asset.id]
        job.status = JobStatus.completed
        job.progress = 100
        job.message = "Soundtrack ready. Preview it in Edit, then render the final cut with music."
        job.updated_at = utcnow_naive()
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
        job.updated_at = utcnow_naive()
        upsert_job(job)
        production.audio_plan.status = "failed"
        production.audio_plan.updated_at = utcnow_naive()
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


def _ffmpeg_path() -> str:
    settings = get_settings()
    configured = settings.playable_capture_ffmpeg_path.strip()
    path = configured if configured and Path(configured).is_file() else shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is required to assemble an edited video timeline.")
    return path


def _trim_timeline_clip(*, content: bytes, trim_in_seconds: float, trim_out_seconds: float | None, fallback_duration: float) -> tuple[bytes, float]:
    """Create a non-destructive trim for one selected take.

    The requested duration is deliberately bounded by the known Veo duration;
    this avoids an invalid timeline when a user types an out point past the
    end of the generated take.
    """
    trim_in = max(0.0, float(trim_in_seconds or 0))
    natural_end = max(trim_in + 0.1, float(fallback_duration or 0.1))
    trim_out = min(max(trim_in + 0.1, float(trim_out_seconds or natural_end)), natural_end)
    duration = max(0.1, trim_out - trim_in)
    if trim_in <= 0.001 and trim_out_seconds is None:
        return content, duration
    with tempfile.TemporaryDirectory(prefix="incept-timeline-trim-") as directory:
        root = Path(directory)
        source = root / "source.mp4"
        output = root / "trimmed.mp4"
        source.write_bytes(content)
        result = subprocess.run(
            [
                _ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{trim_in:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-c:a", "aac",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode != 0 or not output.exists():
            detail = result.stderr.decode("utf-8", errors="replace")[-500:]
            raise RuntimeError(f"Could not trim a selected take. {detail}")
        return output.read_bytes(), duration


def _assemble_timeline(*, clips: list[bytes], durations: list[float], transitions: list[str]) -> tuple[bytes, float]:
    """Join selected takes with cut, match-cut, or a short audiovisual fade."""
    if len(clips) == 1:
        return _concat_video_sequence(clips=clips, target_seconds=max(1, math.ceil(durations[0]))), durations[0]
    if not any(transition == "fade" for transition in transitions[1:]):
        total = sum(durations)
        return _concat_video_sequence(clips=clips, target_seconds=max(1, math.ceil(total))), total

    # xfade/acrossfade gives a real transition, rather than merely labelling a
    # hard cut as a fade. Veo 3.1 takes contain audio; if an unusual take does
    # not, the assembly error explains which take should be regenerated.
    fade_seconds = 0.25
    with tempfile.TemporaryDirectory(prefix="incept-timeline-fade-") as directory:
        root = Path(directory)
        inputs: list[str] = []
        for index, content in enumerate(clips):
            path = root / f"take-{index + 1}.mp4"
            path.write_bytes(content)
            inputs.extend(["-i", str(path)])
        filters: list[str] = []
        previous_video = "0:v"
        previous_audio = "0:a"
        elapsed = durations[0]
        total = durations[0]
        for index in range(1, len(clips)):
            transition = transitions[index] if index < len(transitions) else "cut"
            video_label = f"v{index}"
            audio_label = f"a{index}"
            if transition == "fade":
                overlap = min(fade_seconds, max(0.05, durations[index] / 3), max(0.05, elapsed / 3))
                offset = max(0.0, elapsed - overlap)
                filters.append(f"[{previous_video}][{index}:v]xfade=transition=fade:duration={overlap:.3f}:offset={offset:.3f}[{video_label}]")
                filters.append(f"[{previous_audio}][{index}:a]acrossfade=d={overlap:.3f}[{audio_label}]")
                elapsed = elapsed + durations[index] - overlap
                total += durations[index] - overlap
            else:
                filters.append(f"[{previous_video}][{index}:v]concat=n=2:v=1:a=0[{video_label}]")
                filters.append(f"[{previous_audio}][{index}:a]concat=n=2:v=0:a=1[{audio_label}]")
                elapsed += durations[index]
                total += durations[index]
            previous_video = video_label
            previous_audio = audio_label
        output = root / "timeline.mp4"
        result = subprocess.run(
            [
                _ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", *inputs,
                "-filter_complex", ";".join(filters), "-map", f"[{previous_video}]", "-map", f"[{previous_audio}]",
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-r", "24", "-movflags", "+faststart", str(output),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode != 0 or not output.exists():
            detail = result.stderr.decode("utf-8", errors="replace")[-500:]
            raise RuntimeError(f"Could not apply the selected fade transition. {detail}")
        return output.read_bytes(), total


def _font_for_subtitles() -> str | None:
    for candidate in (
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _escape_drawtext(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("\n", " ")


def _apply_edit_overlays(*, content: bytes, production: VideoProduction) -> bytes:
    """Burn selected real brand assets and captions into the assembled cut."""
    overlays = [overlay for overlay in production.edit_plan.overlays if overlay.text.strip() or overlay.asset_id]
    if not overlays:
        return content
    with tempfile.TemporaryDirectory(prefix="incept-timeline-overlay-") as directory:
        root = Path(directory)
        source = root / "timeline.mp4"
        output = root / "overlaid.mp4"
        source.write_bytes(content)
        inputs: list[str] = ["-i", str(source)]
        filters: list[str] = []
        current = "0:v"
        image_index = 1
        subtitle_font = _font_for_subtitles()
        for index, overlay in enumerate(overlays):
            start = max(0.0, overlay.start_seconds)
            end = overlay.end_seconds if overlay.end_seconds is not None else 99_999.0
            enable = f"between(t,{start:.3f},{max(start, end):.3f})"
            if overlay.kind == "subtitle" and overlay.text.strip():
                font_clause = f":fontfile='{_escape_drawtext(subtitle_font)}'" if subtitle_font else ""
                filters.append(
                    f"[{current}]drawtext=text='{_escape_drawtext(overlay.text)}'{font_clause}:fontcolor=white:fontsize=34:"
                    f"borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-text_h-80:enable='{enable}'[ov{index}]"
                )
                current = f"ov{index}"
                continue
            image = _asset_by_id(overlay.asset_id or "")
            image_bytes = _load_asset_bytes(image) if image else None
            if not image_bytes:
                continue
            image_path = root / f"overlay-{image_index}.png"
            image_path.write_bytes(image_bytes)
            inputs.extend(["-loop", "1", "-i", str(image_path)])
            position = {
                "top_left": "24:24",
                "top_right": "W-w-24:24",
                "bottom_center": "(W-w)/2:H-h-42",
                "center": "(W-w)/2:(H-h)/2",
            }[overlay.position]
            filters.append(f"[{image_index}:v]scale=240:-1[img{image_index}]")
            filters.append(f"[{current}][img{image_index}]overlay={position}:enable='{enable}'[ov{index}]")
            current = f"ov{index}"
            image_index += 1
        if current == "0:v":
            return content
        result = subprocess.run(
            [
                _ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", *inputs,
                "-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", "0:a?",
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode != 0 or not output.exists():
            detail = result.stderr.decode("utf-8", errors="replace")[-500:]
            raise RuntimeError(f"Could not apply timeline overlays. {detail}")
        return output.read_bytes()


def _timeline_overrides(production: VideoProduction) -> dict[str, dict[str, object]]:
    """Read optional explicit timeline JSON without making it mandatory."""
    if not production.edit_plan.timeline_json.get("apply_to_render"):
        return {}
    clips = production.edit_plan.timeline_json.get("clips") if production.edit_plan.timeline_json else None
    if not isinstance(clips, list):
        raise ValueError("Timeline JSON must include a clips array when apply_to_render is true.")
    overrides: dict[str, dict[str, object]] = {}
    for entry in clips:
        if not isinstance(entry, dict) or not isinstance(entry.get("shot_id"), str):
            raise ValueError("Each Timeline JSON clip requires a shot_id.")
        shot_id = str(entry["shot_id"])
        if shot_id in overrides:
            raise ValueError(f"Timeline JSON contains Frame {shot_id} more than once.")
        if entry.get("transition") and str(entry["transition"]) not in {"cut", "fade", "match_cut"}:
            raise ValueError("Timeline JSON transitions must be cut, fade, or match_cut.")
        for field in ("trim_in_seconds", "trim_out_seconds"):
            if entry.get(field) is not None:
                try:
                    if float(entry[field]) < 0:
                        raise ValueError
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Timeline JSON {field} must be a non-negative number.") from exc
        overrides[shot_id] = entry
    return overrides


def create_production_render_job(production_id: str, user: User, *, include_audio: bool = False) -> GenerationJob:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    overrides = _timeline_overrides(production)
    known_shot_ids = {shot.id for shot in production.shots}
    unknown_shot_ids = sorted(set(overrides) - known_shot_ids)
    if unknown_shot_ids:
        raise ValueError("Timeline JSON references a Frame that no longer exists. Refresh the JSON draft before rendering.")
    included_shots = [shot for shot in production.shots if bool(overrides.get(shot.id, {}).get("include", shot.include_in_edit))]
    if not included_shots:
        raise ValueError("Include at least one storyboard frame in the edit before assembling it.")
    missing_takes = []
    for shot in included_shots:
        requested_take_id = overrides.get(shot.id, {}).get("take_id")
        take_id = requested_take_id if isinstance(requested_take_id, str) else shot.selected_video_asset_id
        if not (shot.status == "ready" and take_id and take_id in shot.video_asset_ids and _asset_by_id(take_id)):
            missing_takes.append(shot)
    if missing_takes:
        labels = ", ".join(f"Frame {shot.order}" for shot in missing_takes[:4])
        raise ValueError(f"Generate and select a video take for every included storyboard frame before assembling the edit. Missing: {labels}.")
    if include_audio and not production.audio_plan.music_asset_ids:
        raise ValueError("Generate a soundtrack with the Audio Producer before rendering a cut with music.")
    now = utcnow_naive()
    job = GenerationJob(
        job_id=f"job_{uuid4().hex[:12]}",
        workspace_id=production.workspace_id,
        status=JobStatus.running,
        progress=5,
        lineage_key=f"vprod_{uuid4().hex[:16]}",
        message="Preparing the selected-take edit…",
        tool_id="video-production-edit",
        title=f"{production.title} · selected-take edit",
        created_at=now,
        updated_at=now,
    )
    JOBS[job.job_id] = job
    upsert_job(job)
    production.render_job_id = job.job_id
    production.stage = VideoProductionStage.edit
    _save(production)
    return job


def run_edit_reviewer(production_id: str, request: VideoProductionAgentRequest, user: User) -> VideoProduction:
    """Use Gemini video understanding to propose reviewable take-level edits.

    The model proposes a structured review only. It never chooses a take,
    modifies a timeline, or renders a video without an explicit user action.
    """
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    selected_shot_ids = set(request.shot_ids)
    take_rows: list[dict[str, object]] = []
    parts: list[object] = []
    for shot in sorted(production.shots, key=lambda item: item.order):
        if selected_shot_ids and shot.id not in selected_shot_ids:
            continue
        for take_id in shot.video_asset_ids:
            asset = _asset_by_id(take_id)
            if not asset or asset.type != "video":
                continue
            try:
                parts.append(_asset_part_for_text_model(asset))
            except Exception:
                logger.info("Skipping unreadable video take %s in Edit Reviewer", take_id)
                continue
            take_rows.append({
                "take_id": take_id,
                "shot_id": shot.id,
                "frame_order": shot.order,
                "shot_title": shot.title,
                "duration_seconds": shot.generation_duration_seconds or shot.duration_seconds,
                "start_scene_asset_id": shot.keyframe_asset_id,
                "end_scene_asset_id": shot.end_keyframe_asset_id,
                "director_prompt": shot.veo_prompt,
            })
    if not take_rows:
        raise ValueError("Generate at least one video take before asking the Edit Reviewer.")

    production.edit_plan.review_status = "reviewing"
    _save(production)
    stage_context = (
        "<takes>" + _safe_json(take_rows) + "</takes>\n"
        "<storyboard_context>" + _safe_json([
            {"shot_id": shot.id, "order": shot.order, "title": shot.title, "prompt": shot.veo_prompt}
            for shot in sorted(production.shots, key=lambda item: item.order)
            if not selected_shot_ids or shot.id in selected_shot_ids
        ]) + "</storyboard_context>\n"
        "<review_policy>Review every supplied take. Suggest trims only inside the supplied duration. "
        "A recommendation is advisory; do not create an edit, overlay, or new asset.</review_policy>"
    )
    try:
        payload = _role_payload(
            production,
            role_prompt=EDIT_REVIEWER_PROMPT,
            instruction=request.message or "Review the generated takes and propose the strongest safe edit ranges.",
            include_asset_parts=False,
            include_contracts=False,
            parts_override=parts,
            stage_context=stage_context,
            language_policy=_output_language_policy(production, request.message),
        )
        raw_reviews = _expand_list_value(payload.get("reviews"))
        allowed_take_ids = {str(row["take_id"]) for row in take_rows}
        by_take = {str(row["take_id"]): row for row in take_rows}
        reviews: list[VideoProductionTakeReview] = []
        for item in raw_reviews:
            if not isinstance(item, dict):
                continue
            take_id = str(item.get("take_id") or "")
            if take_id not in allowed_take_ids:
                continue
            row = by_take[take_id]
            duration = float(row["duration_seconds"] or 0)
            trim_in = max(0.0, min(float(item.get("suggested_trim_in_seconds") or 0), duration))
            raw_out = item.get("suggested_trim_out_seconds")
            try:
                trim_out = float(raw_out) if raw_out is not None else None
            except (TypeError, ValueError):
                trim_out = None
            if trim_out is not None:
                trim_out = max(trim_in + 0.1, min(trim_out, duration))
            verdict = str(item.get("verdict") or "trim").lower()
            flags = [str(flag) for flag in _expand_list_value(item.get("flags"))]
            reviews.append(VideoProductionTakeReview(
                take_id=take_id,
                shot_id=str(row["shot_id"]),
                score=max(0, min(100, int(item.get("score") or 0))),
                verdict=verdict if verdict in {"use", "trim", "regenerate", "reject"} else "trim",
                reasons=[str(reason) for reason in _expand_list_value(item.get("reasons")) if str(reason).strip()],
                flags=[flag for flag in flags if flag in {"unreadable_text", "brand_mismatch", "identity_drift", "hard_cut", "bad_motion", "audio_issue"}],
                suggested_trim_in_seconds=trim_in,
                suggested_trim_out_seconds=trim_out,
            ))
        if len({review.take_id for review in reviews}) != len(allowed_take_ids):
            raise ValueError("Edit Reviewer returned an incomplete take review. No recommendations were saved; please try again.")
        production.edit_plan.take_reviews = reviews
        production.edit_plan.timeline_json = {
            "version": 1,
            "apply_to_render": False,
            "clips": [
                {
                    "shot_id": shot.id,
                    "frame_order": shot.order,
                    "take_id": shot.selected_video_asset_id or (shot.video_asset_ids[0] if shot.video_asset_ids else None),
                    "include": shot.include_in_edit,
                    "trim_in_seconds": shot.trim_in_seconds,
                    "trim_out_seconds": shot.trim_out_seconds,
                    "transition": shot.transition or "cut",
                    "reviewed_takes": [review.model_dump(mode="json") for review in reviews if review.shot_id == shot.id],
                }
                for shot in sorted(production.shots, key=lambda item: item.order)
            ],
            "overlays": [overlay.model_dump(mode="json") for overlay in production.edit_plan.overlays],
        }
        production.edit_plan.review_status = "ready"
        production.edit_plan.review_summary = str(payload.get("summary") or "Take review is ready.")
        production.edit_plan.reviewed_at = utcnow_naive()
        production.conversation.append(VideoProductionConversationMessage(role="assistant", text=production.edit_plan.review_summary))
        return _save(production)
    except Exception:
        production.edit_plan.review_status = "failed"
        _save(production)
        raise


async def run_production_render_background(production_id: str, job_id: str, user: User, include_audio: bool = False) -> None:
    production = VIDEO_PRODUCTIONS.get(production_id)
    job = JOBS.get(job_id)
    if not production or not job:
        return
    try:
        overrides = _timeline_overrides(production)
        included_shots = [
            shot for shot in sorted(production.shots, key=lambda item: item.order)
            if bool(overrides.get(shot.id, {}).get("include", shot.include_in_edit))
        ]
        video_assets = []
        raw_clips: list[bytes] = []
        timeline_durations: list[float] = []
        transitions: list[str] = []
        for shot in included_shots:
            entry = overrides.get(shot.id, {})
            requested_take_id = entry.get("take_id") if isinstance(entry.get("take_id"), str) else None
            asset = _asset_by_id(requested_take_id or shot.selected_video_asset_id or "")
            if not asset or asset.type != "video":
                continue
            raw = _load_asset_bytes(asset)
            if not raw:
                continue
            fallback_duration = float(shot.generation_duration_seconds or (4 if shot.duration_seconds <= 4 else 6 if shot.duration_seconds <= 6 else 8))
            trimmed, duration = _trim_timeline_clip(
                content=raw,
                trim_in_seconds=float(entry.get("trim_in_seconds", shot.trim_in_seconds) or 0),
                trim_out_seconds=float(entry["trim_out_seconds"]) if entry.get("trim_out_seconds") is not None else shot.trim_out_seconds,
                fallback_duration=fallback_duration,
            )
            video_assets.append(asset)
            raw_clips.append(trimmed)
            timeline_durations.append(duration)
            transitions.append(str(entry.get("transition") or shot.transition or "cut"))
        clips = raw_clips
        if not clips:
            raise RuntimeError("No readable shot videos are available for the first cut.")
        _mark_generation_progress(job, 25, "Assembling approved shot takes in storyboard order…")
        content, edit_seconds = await asyncio.to_thread(
            _assemble_timeline, clips=clips, durations=timeline_durations, transitions=transitions
        )
        _mark_generation_progress(job, 48, "Applying the selected captions and brand overlays…")
        content = await asyncio.to_thread(_apply_edit_overlays, content=content, production=production)
        if include_audio:
            soundtrack = _asset_by_id(production.audio_plan.music_asset_ids[-1])
            if not soundtrack or soundtrack.type != "audio":
                raise RuntimeError("The approved soundtrack is no longer available for mixing.")
            audio_content = _load_asset_bytes(soundtrack)
            if not audio_content:
                raise RuntimeError("The approved soundtrack could not be read for mixing.")
            _mark_generation_progress(job, 65, "Mixing the approved soundtrack into the final cut…")
            content = await asyncio.to_thread(
                _mix_audio_into_video,
                video_content=content,
                audio_content=audio_content,
                target_seconds=production.target_seconds,
            )
        # QC remains transparent and advisory: it gives the editor a visible
        # checklist without silently deleting a take that the user chose.
        selected_take_ids = {shot.selected_video_asset_id or "" for shot in included_shots}
        review_by_take = {review.take_id: review for review in production.edit_plan.take_reviews}
        qc_issues: list[str] = []
        for take_id in selected_take_ids:
            review = review_by_take.get(take_id)
            if review and review.verdict in {"regenerate", "reject"}:
                qc_issues.append(f"Selected take {take_id} is marked {review.verdict} by the Edit Reviewer.")
            elif review and "unreadable_text" in review.flags:
                qc_issues.append(f"Selected take {take_id} may contain unreadable generated text.")
        if len(video_assets) != len(included_shots):
            qc_issues.append("One or more included Frames had no readable video take.")
        target_delta = abs(edit_seconds - production.target_seconds)
        if target_delta > 0.5:
            qc_issues.append(f"Timeline duration is {edit_seconds:.1f}s versus the project target of {production.target_seconds}s.")
        for overlay in production.edit_plan.overlays:
            if overlay.kind != "subtitle" and overlay.asset_id and not _asset_by_id(overlay.asset_id):
                qc_issues.append(f"Overlay {overlay.id} references a missing Library asset.")
        production.edit_plan.qc_status = "warning" if qc_issues else "pass"
        production.edit_plan.qc_issues = qc_issues
        production.edit_plan.final_duration_seconds = round(edit_seconds, 2)
        _mark_generation_progress(job, 82, "Saving the edited production cut…")
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
                "shot_ids": [
                    shot.id for shot in production.shots
                    if shot.include_in_edit and shot.status == "ready" and (shot.selected_video_asset_id or shot.video_asset_ids)
                ],
                "transitions": transitions,
                "trimmed_durations": timeline_durations,
                "final_duration_seconds": round(edit_seconds, 2),
                "qc_status": production.edit_plan.qc_status,
                "qc_issues": qc_issues,
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
        job.message = "Selected-take edit ready. Review the complete video before delivery QA."
        job.updated_at = utcnow_naive()
        upsert_job(job)
        production.final_asset_id = asset.id
        production.stage = VideoProductionStage.deliver
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text="The selected-take edit is ready for delivery QA.",
        ))
        _save(production)
    except Exception as exc:
        logger.exception("Video production first cut failed for %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"First-cut assembly failed: {exc}"[:500]
        job.updated_at = utcnow_naive()
        upsert_job(job)


def create_shot_video_job(
    production_id: str,
    shot_id: str,
    user: User,
    *,
    variants: int | None = None,
) -> GenerationJob:
    production = get_video_production(production_id, user)
    if not production:
        raise KeyError("Video production not found")
    shot = next((item for item in production.shots if item.id == shot_id), None)
    if not shot:
        raise KeyError("Shot not found")
    if not shot.veo_prompt.strip():
        raise ValueError("Generate or write a Director Veo Prompt before producing this shot.")
    if variants is not None:
        if variants not in {1, 2}:
            raise ValueError("Choose one or two Veo variants per storyboard frame.")
        shot.generation_variants = variants
    if shot.generation_mode == "extend":
        if not shot.extend_source_video_asset_id or shot.extend_source_video_asset_id not in shot.video_asset_ids:
            raise ValueError("Extend mode needs one of this frame's generated Takes as its source.")
    if shot.generation_mode == "first_last_frame" and not shot.end_keyframe_asset_id:
        raise ValueError("First/last-frame mode requires an End Scene image.")
    if shot.generation_mode == "first_last_frame" and shot.end_keyframe_asset_id and shot.first_last_frame_status == "not_set":
        raise ValueError("Regenerate the Director Prompt after choosing an end Scene so it can inspect the first/last-frame pair before Veo runs.")
    if shot.generation_mode == "first_last_frame" and shot.end_keyframe_asset_id and shot.first_last_frame_status == "needs_intermediate":
        raise ValueError("This first/last-frame pair needs an intermediate Scene image before Veo can generate a continuous shot. Review the Director note in Storyboard.")
    if shot.generation_mode != "extend" and not shot.keyframe_asset_id:
        raise ValueError("Generate and approve a keyframe before producing this shot.")
    settings = get_settings()
    video_model = _production_model(production, "video", settings.vertex_veo_fast_model)
    duration = shot.generation_duration_seconds or (4 if shot.duration_seconds <= 4 else 6 if shot.duration_seconds <= 6 else 8)
    assert_video_budget_available(VideoGenerationRequest(
        workspace_id=production.workspace_id,
        prompt=_veo_shot_prompt(production, shot),
        model=video_model,
        created_by=user.id,
        source_asset_id=shot.extend_source_video_asset_id if shot.generation_mode == "extend" else shot.keyframe_asset_id,
        end_frame_asset_id=shot.end_keyframe_asset_id if shot.generation_mode == "first_last_frame" else None,
        video_generation_mode=(
            VideoGenerationMode.extend_video if shot.generation_mode == "extend"
            else VideoGenerationMode.first_last_frame if shot.generation_mode == "first_last_frame" and shot.end_keyframe_asset_id
            else VideoGenerationMode.image_to_video
        ),
        aspect_ratio=production.aspect_ratio,
        duration_seconds=duration,
        resolution=production.resolution,
        variants=shot.generation_variants,
    ), user)
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
    if not shot or (shot.generation_mode != "extend" and not shot.keyframe_asset_id):
        return
    settings = get_settings()
    video_model = _production_model(production, "video", settings.vertex_veo_fast_model)
    try:
        if not video_model:
            raise RuntimeError("No video model is configured for this production.")
        duration = shot.generation_duration_seconds or (4 if shot.duration_seconds <= 4 else 6 if shot.duration_seconds <= 6 else 8)
        request = VideoGenerationRequest(
            workspace_id=production.workspace_id,
            prompt=_veo_shot_prompt(production, shot),
            model=video_model,
            created_by=user.id,
            source_asset_id=shot.extend_source_video_asset_id if shot.generation_mode == "extend" else shot.keyframe_asset_id,
            end_frame_asset_id=shot.end_keyframe_asset_id if shot.generation_mode == "first_last_frame" else None,
            video_generation_mode=(
                VideoGenerationMode.extend_video
                if shot.generation_mode == "extend"
                else VideoGenerationMode.first_last_frame
                if shot.generation_mode == "first_last_frame" and shot.end_keyframe_asset_id
                else VideoGenerationMode.image_to_video
            ),
            aspect_ratio=production.aspect_ratio,
            duration_seconds=duration,
            resolution=production.resolution,
            variants=shot.generation_variants,
        )
        source_label = "selected Take extension" if shot.generation_mode == "extend" else "approved Scene image"
        _mark_generation_progress(job, 20, f"Sending S{shot.order:02d} {source_label} to Veo Fast…")
        assets = await _execute_veo_request(job=job, request=request, user=user, model_id=video_model)
        job.output_asset_ids = [asset.id for asset in assets]
        _record_video_usage(job, request, user, video_model, assets)
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"{len(job.output_asset_ids)} Veo take{'s' if len(job.output_asset_ids) != 1 else ''} ready for S{shot.order:02d}."
        job.updated_at = utcnow_naive()
        upsert_job(job)
        shot.video_asset_ids = list(dict.fromkeys([*shot.video_asset_ids, *job.output_asset_ids]))
        # A generation job creates candidates, not an editorial decision. Keep
        # any previously selected take intact so a new variant cannot silently
        # replace it; when no choice exists, the producer must explicitly make
        # one in Take review before the shot may enter an assembled edit.
        shot.source_signature = _shot_source_signature(shot)
        shot.take_source_signature = shot.source_signature
        shot.take_outdated = False
        shot.status = "ready"
        production.stage = VideoProductionStage.generate
        production.conversation.append(VideoProductionConversationMessage(
            role="assistant",
            text=f"S{shot.order:02d} generated {len(job.output_asset_ids)} Veo take{'s' if len(job.output_asset_ids) != 1 else ''}. Review the alternatives, then select or regenerate only this frame.",
        ))
        _save(production)
    except Exception as exc:
        logger.exception("Video production Veo shot failed for %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"Shot generation failed: {exc}"[:500]
        job.updated_at = utcnow_naive()
        upsert_job(job)
        shot.status = "failed"
        _save(production)
