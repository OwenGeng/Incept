from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import math
import mimetypes
import re
import shutil
import subprocess
import tempfile
from io import BytesIO
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
from google import genai
from google.genai import types as genai_types

from app.incept import thread_store
from app.incept.bigquery_store import persist_generation
from app.incept.config import get_settings
from app.incept.db import load_video_plans, upsert_asset, upsert_job, upsert_usage_event, upsert_video_plan
from app.incept.models import Asset, AssetRole, CreativeThread, GenerationJob, GenerationMode, JobStatus, UsageEvent, User, VideoBudgetStatus, VideoGenerationBeat, VideoGenerationMode, VideoGenerationPlan, VideoGenerationRequest, VideoPlanConversationMessage, VideoPlanRequest, VideoPlanResponse
from app.incept.playable_capture import capture_playable_to_mp4
from app.incept.store import (
    ASSETS,
    JOBS,
    SOURCE_ASSETS,
    STATIC_DIR,
    USAGE_EVENTS,
    _build_gcs_object_path,
    _download_bytes_from_gcs,
    _guess_content_type,
    _inherit_root_asset_id,
    _normalized_source_title,
    _record_asset_storage_status,
    _upload_bytes_to_gcs,
    build_asset_content_path,
    guess_asset_extension,
    read_asset_bytes,
)
from app.incept.video_prompt_builder import build_video_mock_completion_message

logger = logging.getLogger(__name__)
_DATA_URI_RE = re.compile(r"data:image/(?P<fmt>png|jpeg|jpg|webp);base64,(?P<data>[A-Za-z0-9+/=\\s]+)", re.IGNORECASE)
_MOLOCO_MAX_PLAYABLE_BYTES = 5 * 1024 * 1024
_EXTERNAL_ATTRIBUTE_RE = re.compile(r"\b(?:src|href)\s*=\s*(['\"])(?P<value>.*?)\1", re.IGNORECASE | re.DOTALL)
_CSS_URL_RE = re.compile(r"url\(\s*['\"]?(?P<value>[^)'\"]+)['\"]?\s*\)", re.IGNORECASE)
_EXPLICIT_VIDEO_EXECUTION_RE = re.compile(
    r"(?:\bgenerate\b|\brender\b|\bproduce\b|\bcreate (?:the )?(?:video|playable)\b|"
    r"\bmake (?:the )?(?:video|playable)\b|\bgo ahead\b|\bdo it\b|\byes\b|"
    r"生成(?:视频|吧|它)?|开始生成|执行生成|立即执行|立即生成|开始制作|确认(?:生成|执行)?|可以(?:生成|执行)|"
    r"按(?:这个|此方案)做|就这么做|开始吧)",
    re.IGNORECASE,
)
VIDEO_PLANS: dict[str, VideoGenerationPlan] = {}


def _bootstrap_video_plans() -> None:
    for row in load_video_plans():
        try:
            payload = json.loads(row["payload_json"])
            plan = VideoGenerationPlan.model_validate(payload)
            VIDEO_PLANS[plan.plan_id] = plan
        except Exception:
            logger.warning("Skipping unreadable persisted video plan", exc_info=True)


_bootstrap_video_plans()


def _estimate_video_cost_usd(request: VideoGenerationRequest) -> float:
    settings = get_settings()
    rate = max(0.0, settings.veo_fast_estimated_cost_per_second_usd)
    # Official Veo 3.1 Fast video-only pricing: $0.08/s at 720p, $0.10/s at 1080p.
    if request.resolution == "1080p":
        rate += 0.02
    return round(_estimated_veo_render_seconds(request.duration_seconds) * request.variants * rate, 4)


def _sequence_extension_plan(target_seconds: int) -> tuple[int, int, int]:
    """Return initial duration, fixed 7s extensions, and seconds trimmed at export."""
    if target_seconds <= 8:
        return target_seconds, 0, 0
    extension_count = math.ceil((target_seconds - 8) / 7)
    rendered_seconds = 8 + (extension_count * 7)
    return 8, extension_count, rendered_seconds - target_seconds


def _estimated_veo_render_seconds(target_seconds: int) -> int:
    """Billable footage includes the final Veo extension before export trimming."""
    initial_duration, extension_count, _trim_seconds = _sequence_extension_plan(target_seconds)
    return initial_duration + (extension_count * 7)


def _current_studio_spend_usd_for_user(user: User) -> float:
    total = 0.0
    for event in USAGE_EVENTS.values():
        if event.user_id != user.id:
            continue
        if event.operation not in {"image_generation", "video_generation"}:
            continue
        total += event.actual_cost_usd if event.actual_cost_usd is not None else event.estimated_cost_usd
    return round(total, 4)


def assert_video_budget_available(request: VideoGenerationRequest, user: User) -> None:
    settings = get_settings()
    budget_limit = max(0.0, settings.studio_user_budget_usd)
    estimated_request_cost = _estimate_video_cost_usd(request)
    if budget_limit <= 0:
        return

    current_spend = _current_studio_spend_usd_for_user(user)
    projected_total = round(current_spend + estimated_request_cost, 4)
    if projected_total > budget_limit:
        raise RuntimeError(
            "Video budget exceeded. "
            f"User budget: ${budget_limit:.2f}. "
            f"Current estimated spend: ${current_spend:.2f}. "
            f"This request would add about ${estimated_request_cost:.2f}, reaching ${projected_total:.2f}."
        )


def get_video_budget_status(
    user: User,
    *,
    duration_seconds: int | None = None,
    variants: int | None = None,
) -> VideoBudgetStatus:
    settings = get_settings()
    pricing_enabled = True
    current_spend = _current_studio_spend_usd_for_user(user)
    budget_limit = max(0.0, settings.studio_user_budget_usd)

    request_estimated_cost = 0.0
    if duration_seconds and variants:
        render_seconds = _estimated_veo_render_seconds(max(0, duration_seconds))
        request_estimated_cost = round(render_seconds * max(0, variants) * settings.veo_fast_estimated_cost_per_second_usd, 4)

    projected_total = round(current_spend + request_estimated_cost, 4)
    remaining = round(max(0.0, budget_limit - current_spend), 4)
    return VideoBudgetStatus(
        budget_usd=budget_limit,
        pricing_enabled=pricing_enabled,
        current_estimated_spend_usd=current_spend,
        remaining_estimated_spend_usd=remaining,
        request_estimated_cost_usd=request_estimated_cost,
        projected_total_usd=projected_total,
        would_exceed_budget=pricing_enabled and budget_limit > 0 and projected_total > budget_limit,
    )


def _thread_title_from_video_request(request: VideoGenerationRequest) -> str:
    prompt = " ".join((request.prompt or "").split())
    if prompt:
        return prompt[:72]
    labels = {
        "image_to_video": "Image to Video",
        "playable_to_video": "Playable to Video",
        "competitor_style_transfer": "Video to Video",
        "video_to_playable": "Video to Playable",
        "first_last_frame": "Storyboard Video",
        "extend_video": "Extend Video",
        "reference_character": "Reference Character",
        "prompt_assist": "Prompt Assist",
        "multi_shot_storyboard": "Multi-shot Storyboard",
        "video_remediation": "Video Remediation",
        "synthetic_recast": "Synthetic Recast",
    }
    return labels.get(request.video_generation_mode.value, "Video thread")


def _safe_json_text(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _is_explicit_video_execution_request(text: str) -> bool:
    """Never spend video budget on ordinary acknowledgement or planning chat."""
    normalized = " ".join((text or "").strip().split())
    return bool(normalized and _EXPLICIT_VIDEO_EXECUTION_RE.search(normalized))


def _text_part(value: str) -> genai_types.Part:
    return genai_types.Part(text=value[:12000])


def _extract_text_response(response) -> str:
    chunks: list[str] = []
    for candidate in (response.candidates or []):
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text_value = getattr(part, "text", None)
            if isinstance(text_value, str) and text_value.strip():
                chunks.append(text_value.strip())
    return "\n".join(chunks).strip()


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _call_multimodal_text_model(
    *,
    prompt: str,
    parts: list[genai_types.Part],
    model_id: str | None = None,
) -> str:
    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )
    contents = [genai_types.Content(role="user", parts=[_text_part(prompt), *parts])]
    response = client.models.generate_content(
        model=(model_id or settings.vertex_gemini_model).strip(),
        contents=contents,
    )
    text = _extract_text_response(response)
    if not text:
        raise RuntimeError("Gemini text analysis returned no text.")
    return text


def _video_analysis_model_id() -> str:
    """Return the dedicated model used for every video planning conversation."""
    model_id = get_settings().vertex_video_analysis_model.strip()
    if not model_id:
        raise RuntimeError("VERTEX_VIDEO_ANALYSIS_MODEL is not configured.")
    return model_id


def _asset_part_for_text_model(asset: Asset) -> genai_types.Part:
    asset_bytes = read_asset_bytes(asset)
    if not asset_bytes:
        raise RuntimeError(f"Could not read bytes for asset {asset.id}")
    mime = _guess_content_type(asset.title or asset.id, "application/octet-stream")
    return genai_types.Part.from_bytes(data=asset_bytes, mime_type=mime)


def _persist_generated_report_asset(
    *,
    job: GenerationJob,
    request: VideoGenerationRequest,
    user: User,
    title: str,
    content: str,
    source_asset: Asset | None = None,
) -> Asset:
    asset_id = f"{job.lineage_key}_{uuid4().hex[:6]}_report"
    ext = ".md"
    raw = content.encode("utf-8")
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    local_filename = f"{asset_id}{ext}"
    (STATIC_DIR / local_filename).write_bytes(raw)
    asset = Asset(
        id=asset_id,
        title=title,
        type="report",
        gcs_uri="",
        preview_url=f"/static/generated/{local_filename}",
        provider=request.provider,
        model=get_settings().vertex_gemini_model,
        workspace_id=request.workspace_id,
        job_id=job.job_id,
        prompt_hash="",
        created_by=user.id,
        created_at=datetime.utcnow(),
        asset_role=AssetRole.generated,
        analysis={"report_kind": request.video_generation_mode.value},
        thread_id=job.thread_id,
        parent_asset_id=source_asset.id if source_asset else None,
        root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
    )
    asset.gcs_uri = _upload_bytes_to_gcs(
        content=raw,
        object_path=_build_gcs_object_path(
            category="generated",
            workspace_id=request.workspace_id,
            created_at=asset.created_at,
            job_id=job.job_id,
            filename=local_filename,
        ),
        content_type="text/markdown; charset=utf-8",
    ) or f"local://generated/{local_filename}"
    _record_asset_storage_status(asset, category="generated")
    ASSETS[asset.id] = asset
    upsert_asset(asset)
    return asset


def _persist_generated_image_asset(
    *,
    workspace_id: str,
    user_id: str,
    thread_id: str | None,
    parent_asset: Asset | None,
    title: str,
    content: bytes,
) -> Asset:
    from PIL import Image

    created_at = datetime.utcnow()
    asset_id = f"asset_video_src_{uuid4().hex[:12]}"
    extension = ".png"
    filename = f"{asset_id}{extension}"
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / filename).write_bytes(content)
    with Image.open(BytesIO(content)) as img:
        width, height = img.width, img.height

    asset = Asset(
        id=asset_id,
        title=title,
        type="image",
        gcs_uri="",
        preview_url=f"/static/generated/{filename}",
        provider="internal",
        model="derived",
        workspace_id=workspace_id,
        job_id="",
        prompt_hash="",
        created_by=user_id,
        created_at=created_at,
        width=width,
        height=height,
        asset_role=AssetRole.working,
        thread_id=thread_id,
        parent_asset_id=parent_asset.id if parent_asset else None,
        root_asset_id=_inherit_root_asset_id(parent_asset, asset_id),
    )
    asset.gcs_uri = _upload_bytes_to_gcs(
        content=content,
        object_path=_build_gcs_object_path(
            category="generated",
            workspace_id=workspace_id,
            created_at=created_at,
            filename=filename,
        ),
        content_type="image/png",
    ) or f"local://generated/{filename}"
    _record_asset_storage_status(asset, category="generated")
    ASSETS[asset.id] = asset
    upsert_asset(asset)
    return asset


def _data_uri_for_asset(asset: Asset) -> str | None:
    """Return a compact inline media URI when an asset is safe to embed."""
    content = read_asset_bytes(asset)
    if not content:
        return None
    mime = _guess_content_type(asset.title or asset.id, "application/octet-stream")
    if not mime.startswith(("image/", "video/", "audio/")):
        return None
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _moloco_playable_validation(html_text: str) -> dict[str, object]:
    """Static checks for Moloco standalone HTML delivery requirements."""
    lowered = html_text.lower()
    errors: list[str] = []
    warnings: list[str] = []
    byte_size = len(html_text.encode("utf-8"))

    if byte_size >= _MOLOCO_MAX_PLAYABLE_BYTES:
        errors.append("HTML exceeds Moloco's 5 MB file-size limit.")
    if "xmlhttprequest" in lowered:
        errors.append("XMLHttpRequest is not allowed in Moloco playables.")
    if "mraid.js" in lowered or "<script src=\"mraid" in lowered or "<script src='mraid" in lowered:
        errors.append("mraid.js is not allowed in Moloco playables.")
    if re.search(r"(?:window|document)\.location(?:\.href)?\s*=|location\.href\s*=|window\.open\s*\(", lowered):
        errors.append("JavaScript redirects are not allowed in Moloco playables.")
    if not re.search(r"fbplayablead\.onctaclick\s*\(\s*\)", lowered):
        errors.append("CTA must call FbPlayableAd.onCTAClick() with no parameters.")
    if "<meta name=\"viewport\"" not in lowered and "<meta name='viewport'" not in lowered:
        errors.append("Responsive viewport metadata is required.")

    for pattern in (_EXTERNAL_ATTRIBUTE_RE, _CSS_URL_RE):
        for match in pattern.finditer(html_text):
            value = match.group("value").strip().lower()
            if not value or value.startswith(("data:", "#", "javascript:void")):
                continue
            # Flag actual network URLs and conventional relative asset paths,
            # but ignore non-URL values from inline SVG/CSS expressions.
            is_network_url = value.startswith(("http://", "https://", "//"))
            is_relative_asset = bool(re.match(r"(?:\.?\.?/)?[\w./-]+\.(?:js|css|png|jpe?g|webp|gif|svg|mp3|wav|ogg|mp4|webm)(?:[?#].*)?$", value))
            if is_network_url or is_relative_asset:
                errors.append(f"External asset reference is not allowed: {value[:120]}")

    if "<button" not in lowered:
        warnings.append("No semantic button was found; verify the CTA path in Moloco Ads Manager preview.")
    if "data:" not in lowered:
        warnings.append("No inline data URI asset was found; the generated playable uses code-only visuals.")

    return {
        "valid": not errors,
        "byte_size": byte_size,
        "size_limit_bytes": _MOLOCO_MAX_PLAYABLE_BYTES,
        "errors": errors,
        "warnings": warnings,
    }


def _persist_generated_playable_asset(
    *,
    job: GenerationJob,
    request: VideoGenerationRequest,
    user: User,
    title: str,
    html_text: str,
    source_asset: Asset,
    analysis: dict[str, object],
) -> Asset:
    raw = html_text.encode("utf-8")
    validation = _moloco_playable_validation(html_text)
    if not validation["valid"]:
        errors = validation["errors"]
        raise RuntimeError(f"Generated playable failed Moloco validation: {' '.join(errors)}")

    asset_id = f"{job.lineage_key}_{uuid4().hex[:6]}_playable"
    filename = f"{asset_id}.html"
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / filename).write_bytes(raw)
    asset = Asset(
        id=asset_id,
        title=title,
        type="playable",
        gcs_uri="",
        preview_url=f"/static/generated/{filename}",
        provider="gemini",
        model=get_settings().vertex_playable_model,
        workspace_id=request.workspace_id,
        job_id=job.job_id,
        prompt_hash="",
        created_by=user.id,
        created_at=datetime.utcnow(),
        asset_role=AssetRole.generated,
        analysis={
            "playable": {
                "schema": analysis,
                "moloco_validation": validation,
            }
        },
        thread_id=job.thread_id,
        parent_asset_id=source_asset.id,
        root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
    )
    asset.gcs_uri = _upload_bytes_to_gcs(
        content=raw,
        object_path=_build_gcs_object_path(
            category="generated",
            workspace_id=request.workspace_id,
            created_at=asset.created_at,
            job_id=job.job_id,
            filename=filename,
        ),
        content_type="text/html; charset=utf-8",
    ) or f"local://generated/{filename}"
    _record_asset_storage_status(asset, category="generated")
    ASSETS[asset.id] = asset
    upsert_asset(asset)
    return asset


def _largest_embedded_image_from_html(html_text: str) -> bytes | None:
    from PIL import Image

    best_bytes: bytes | None = None
    best_area = 0
    for match in _DATA_URI_RE.finditer(html_text):
        try:
            raw = base64.b64decode(re.sub(r"\s+", "", match.group("data")))
            with Image.open(BytesIO(raw)) as img:
                area = img.width * img.height
            if area > best_area:
                best_area = area
                best_bytes = raw
        except Exception:
            continue
    return best_bytes


def _summarize_playable_html_locally(asset: Asset) -> dict[str, object]:
    asset_bytes = read_asset_bytes(asset)
    if not asset_bytes:
        raise RuntimeError("Could not read playable HTML bytes.")
    html_text = asset_bytes.decode("utf-8", errors="ignore")
    lowered = html_text.lower()
    return {
        "title": asset.title,
        "html_bytes": len(asset_bytes),
        "canvas_count": lowered.count("<canvas"),
        "button_count": lowered.count("<button"),
        "script_count": lowered.count("<script"),
        "contains_mraid": "mraid" in lowered,
        "contains_fb_cta": "fbplayablead.onctaclick" in lowered,
        "contains_base64_images": "data:image/" in lowered,
        "contains_pointer_events": any(token in lowered for token in ["touchstart", "pointerdown", "mousedown"]),
        "contains_audio": any(token in lowered for token in ["<audio", "howler", "webaudio", "audiocontext"]),
        "contains_physics": any(token in lowered for token in ["matter.js", "phaser", "pixi", "spine", "dragonbones"]),
        "html_excerpt": html_text[:1600],
    }


def _parse_json_loose(text: str) -> dict[str, object]:
    cleaned = _strip_code_fences(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"raw": cleaned}


def _normalize_playable_asset_manifest(value: object) -> list[dict[str, object]]:
    """Keep model-proposed asset requirements compact and safe for the client."""
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value[:24]:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name", "")).split())[:80]
        category = " ".join(str(item.get("category", "asset")).split())[:32]
        if not name:
            continue
        try:
            count = max(1, min(int(item.get("count", 1) or 1), 20))
        except (TypeError, ValueError):
            count = 1
        normalized.append(
            {
                "name": name,
                "category": category or "asset",
                "required": bool(item.get("required", False)),
                "count": count,
                "preferred_format": " ".join(str(item.get("preferred_format", "PNG")).split())[:40],
                "minimum_size_px": " ".join(str(item.get("minimum_size_px", "Provide at native game resolution")).split())[:60],
                "aspect_ratio": " ".join(str(item.get("aspect_ratio", "As used in the playable")).split())[:40],
                "purpose": " ".join(str(item.get("purpose", "")).split())[:180],
                "library_fallback": bool(item.get("library_fallback", False)),
            }
        )
    return normalized


def _playable_asset_brief(manifest: list[dict[str, object]]) -> str:
    if not manifest:
        return ""
    rows = ["\n\nTo build this playable, please provide this asset pack:"]
    for item in manifest:
        required = "Required" if item["required"] else "Optional"
        fallback = " Generic library fallback is available." if item["library_fallback"] else ""
        rows.append(
            f"- {required}: {item['name']} ({item['count']}x, {item['preferred_format']}, "
            f"minimum {item['minimum_size_px']}, {item['aspect_ratio']}). {item['purpose']}{fallback}"
        )
    return "\n".join(rows)


def _resolve_thread_for_video_request(request: VideoGenerationRequest, user: User) -> CreativeThread:
    source_asset_id = request.source_asset_id or request.end_frame_asset_id
    return thread_store.ensure_thread(
        workspace_id=request.workspace_id,
        title=_thread_title_from_video_request(request),
        generation_mode=GenerationMode.video,
        created_by=user.id,
        thread_id=request.thread_id,
        origin_asset_id=source_asset_id,
    )


def _resolve_thread_for_video_plan_request(request: VideoPlanRequest, user: User) -> CreativeThread:
    title = " ".join(request.prompt.split())[:72] or {
        VideoGenerationMode.image_to_video: "Image to Video plan",
        VideoGenerationMode.competitor_style_transfer: "Video to Video plan",
        VideoGenerationMode.video_to_playable: "Video to Playable plan",
    }.get(request.video_generation_mode, "Video plan")
    return thread_store.ensure_thread(
        workspace_id=request.workspace_id,
        title=title,
        generation_mode=GenerationMode.video,
        created_by=user.id,
        thread_id=request.thread_id,
        origin_asset_id=request.source_asset_id,
    )


def _plan_request_as_generation_request(request: VideoPlanRequest, thread_id: str) -> VideoGenerationRequest:
    return VideoGenerationRequest(
        workspace_id=request.workspace_id,
        prompt=request.prompt,
        created_by=request.created_by or "",
        thread_id=thread_id,
        source_asset_id=request.source_asset_id,
        reference_asset_ids=request.reference_asset_ids,
        video_generation_mode=request.video_generation_mode,
        aspect_ratio=request.aspect_ratio,
        duration_seconds=request.duration_seconds,
        resolution=request.resolution,
        variants=request.variants,
        include_audio=request.include_audio,
    )


def _lookup_video_plan(plan_id: str) -> VideoGenerationPlan | None:
    return VIDEO_PLANS.get(plan_id)


def _persist_video_plan(plan: VideoGenerationPlan) -> None:
    VIDEO_PLANS[plan.plan_id] = plan
    upsert_video_plan(plan)


def list_video_generation_plans(thread_id: str, user: User) -> list[VideoGenerationPlan]:
    return sorted(
        [plan for plan in VIDEO_PLANS.values() if plan.thread_id == thread_id and plan.created_by == user.id],
        key=lambda plan: plan.updated_at,
        reverse=True,
    )


def _video_plan_payload(
    *,
    request: VideoPlanRequest,
    source_asset: Asset,
    reference_assets: list[Asset],
    previous_plan: VideoGenerationPlan | None,
) -> dict[str, object]:
    parts = [_asset_part_for_text_model(source_asset)]
    parts.extend(_asset_part_for_text_model(asset) for asset in reference_assets[:3])
    mode = request.video_generation_mode
    if mode == VideoGenerationMode.image_to_video:
        task = (
            "Analyze the source image and any attached supporting images, then prepare a production plan for an image-to-video ad. "
            "The first image is the primary Veo frame; supporting images are visual references, not additional start frames. "
            "Identify the focal subject, what must remain stable, camera movement, motion scale, pacing, and atmosphere."
        )
    elif mode == VideoGenerationMode.competitor_style_transfer:
        task = (
            "Compare the source video with the attached reference assets for a video-to-video regeneration plan. "
            "Separate what to keep from the source, what visual or motion qualities to adopt from references, and what must not be copied."
        )
    elif mode == VideoGenerationMode.video_to_playable:
        task = (
            "Analyze the source video as the gameplay reference for a high-fidelity, Moloco-compliant HTML5 playable. "
            "Do not propose copying the video's artwork. Infer the gameplay loop, state transitions, interaction types, "
            "success/failure feedback, end-card CTA, and the most suitable runtime template. Then create a precise asset handoff "
            "for the advertiser: list every image, logo, UI, optional audio, and animation asset needed to faithfully produce the playable. "
            "For each item, specify a practical minimum pixel size, aspect ratio, count, preferred file format, whether it is required, "
            "and whether it can be filled from a generic asset library."
        )
    else:
        raise RuntimeError("Planning is available for Image to Video, Video to Video, and Video to Playable.")

    previous = previous_plan.model_dump(mode="json") if previous_plan else None
    prompt = (
        "You are a senior creative strategist. " + task + " "
        "Return JSON only, with exactly: objective, summary, keep, change, avoid, recommended_settings, "
        "generation_prompt, beats, questions, interaction_concept, asset_manifest, execution_intent. "
        "keep/change/avoid/questions must be short arrays of strings. recommended_settings must be an object. "
        "generation_prompt must be a concise executable instruction for the downstream generator, not a discussion. "
        "beats must be an ordered array of time-boxed visual beats. Every beat must contain id, title, purpose, start_state, end_state, "
        "duration_seconds, and veo_brief. The beat durations must add up exactly to the requested duration. veo_brief must describe only that beat; "
        "do not restate the full video prompt in every beat. A beat must advance the story rather than restart a prior scene. "
        "summary is the user-facing assistant reply. Write it as a helpful, natural conversational response, not a report or a list of field labels. "
        "Directly answer the user's question, explain what the supplied assets are sufficient for, and name only genuinely helpful missing optional assets. "
        "Conversation history is authoritative. Reply to the latest user message while retaining every previously agreed creative decision unless the user explicitly changes it. "
        "Treat a direct user response to a prior question as a locked decision. Apply that decision to keep/change/generation_prompt, "
        "and never repeat, paraphrase, or reopen that same question in summary or questions. "
        "Ask at most one question only when a genuinely unresolved choice would materially change the execution; do not ask optional taste questions after the user has already given a usable direction. "
        "This Veo model does not generate native audio. If the user asks about audio or has no audio asset, explain that this output will be silent and that audio can be added in a separate post-production step. "
        "End with at most one concise follow-up question when it would materially improve the result. "
        "Set execution_intent to 'generate' only when the latest user message explicitly asks to generate, render, produce, or execute now. "
        "For all discussion, questions, refinements, acknowledgements, and ambiguous statements, set execution_intent to 'chat'. "
        "When execution is explicitly requested, do not ask a follow-up question; summarize the locked direction and provide the final executable prompt. "
        "Do not claim to preserve unreadable text or unauthorized likenesses. "
        "For video_to_playable, asset_manifest must be an array. Every entry must include: name, category, required, count, "
        "preferred_format, minimum_size_px, aspect_ratio, purpose, and library_fallback. Categories may be background, tile, character, "
        "logo, ui, cta, effect, audio, or endcard. Prefer concrete, production-ready asset names. "
        f"User direction: {request.prompt.strip() or 'No additional direction.'}. "
        f"Current settings: aspect ratio {request.aspect_ratio}, duration {request.duration_seconds}s, resolution {request.resolution}, variants {request.variants}. "
        f"Previous plan, if any: {_safe_json_text(previous or {})}."
    )
    response_text = _call_multimodal_text_model(
        prompt=prompt,
        parts=parts,
        model_id=_video_analysis_model_id(),
    )
    payload = _parse_json_loose(response_text)
    if "raw" in payload:
        raise RuntimeError("Gemini video analysis did not return a structured video plan.")
    return payload


def _fallback_video_beats(target_seconds: int) -> list[VideoGenerationBeat]:
    """Provide a dependable commercial arc when planning returns incomplete JSON."""
    if target_seconds <= 8:
        blueprint = [(target_seconds, "Hook and proof", "Establish the product or gameplay and demonstrate its key action.")]
    elif target_seconds <= 15:
        blueprint = [
            (3, "Hook", "Establish the hero product, game state, or customer tension immediately."),
            (7, "Core demonstration", "Show one readable action and its visible result."),
            (target_seconds - 10, "Payoff", "Land the benefit or rewarding outcome with a clear, stable close."),
        ]
    elif target_seconds <= 30:
        blueprint = [
            (3, "Hook", "Establish the product, game state, or customer tension immediately."),
            (7, "Setup", "Clarify the goal, obstacle, or key feature without repeating the opening."),
            (9, "Demonstration", "Show the core action progressing through a meaningful state change."),
            (7, "Proof and payoff", "Show the benefit, win state, reward, or credible product result."),
            (target_seconds - 26, "Brand-ready close", "Resolve on a clean, stable end state with room for brand messaging."),
        ]
    else:
        blueprint = [
            (3, "Hook", "Establish the product, game state, or customer tension immediately."),
            (9, "Setup", "Clarify the goal, obstacle, or key feature without restarting the scene."),
            (12, "Demonstration one", "Show the first clear interaction and visible outcome."),
            (12, "Demonstration two", "Advance into a second outcome, escalation, or use case."),
            (10, "Proof", "Show a concrete benefit, progression, or reward."),
            (8, "Payoff", "Deliver the strongest visual result and emotional resolution."),
            (target_seconds - 54, "Brand-ready close", "Hold a stable, polished final state for brand messaging."),
        ]
    beats: list[VideoGenerationBeat] = []
    for index, (duration, title, purpose) in enumerate(blueprint, start=1):
        if duration <= 0:
            continue
        beats.append(
            VideoGenerationBeat(
                id=f"beat_{index}",
                title=title,
                purpose=purpose,
                start_state="Continue naturally from the previous beat without a scene reset.",
                end_state="End on a visually clear state that can lead into the next beat.",
                duration_seconds=duration,
                veo_brief=purpose,
            )
        )
    return beats


def _normalize_video_beats(value: object, target_seconds: int) -> list[VideoGenerationBeat]:
    if not isinstance(value, list):
        return _fallback_video_beats(target_seconds)
    beats: list[VideoGenerationBeat] = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            continue
        try:
            beat = VideoGenerationBeat.model_validate(
                {
                    "id": str(raw.get("id") or f"beat_{index}"),
                    "title": str(raw.get("title") or f"Beat {index}"),
                    "purpose": str(raw.get("purpose") or raw.get("veo_brief") or "Advance the commercial story."),
                    "start_state": str(raw.get("start_state") or ""),
                    "end_state": str(raw.get("end_state") or ""),
                    "duration_seconds": int(raw.get("duration_seconds") or 0),
                    "veo_brief": str(raw.get("veo_brief") or raw.get("purpose") or ""),
                }
            )
        except (TypeError, ValueError):
            continue
        beats.append(beat)
    return beats if beats and sum(beat.duration_seconds for beat in beats) == target_seconds else _fallback_video_beats(target_seconds)


def create_or_update_video_plan(request: VideoPlanRequest, user: User) -> VideoPlanResponse:
    source_asset = _asset_by_id(request.source_asset_id)
    if not source_asset:
        raise RuntimeError("A source asset is required before creating a video plan.")
    if request.video_generation_mode == VideoGenerationMode.image_to_video and source_asset.type != "image":
        raise RuntimeError("Image to Video planning requires an image source.")
    if request.video_generation_mode in {VideoGenerationMode.competitor_style_transfer, VideoGenerationMode.video_to_playable} and source_asset.type != "video":
        raise RuntimeError("This video plan requires a video source.")

    thread = _resolve_thread_for_video_plan_request(request, user)
    previous_plan = _lookup_video_plan(request.plan_id) if request.plan_id else None
    if request.action in {"refine", "confirm"} and not previous_plan:
        raise RuntimeError("The video plan could not be found. Analyze the source again before continuing.")
    if previous_plan and (previous_plan.workspace_id != request.workspace_id or previous_plan.created_by != user.id):
        raise RuntimeError("This video plan is not available to the current user.")

    if request.action == "confirm":
        assert previous_plan is not None
        override = (request.generation_prompt_override or "").strip()
        if override:
            previous_plan.generation_prompt = override
        previous_plan.status = "confirmed"
        previous_plan.updated_at = datetime.utcnow()
        previous_plan.conversation.extend(
            [
                VideoPlanConversationMessage(role="user", text="Confirm the current plan."),
                VideoPlanConversationMessage(
                    role="assistant",
                    text="Execution prompt and settings confirmed. Starting the requested generation now.",
                ),
            ]
        )
        _persist_video_plan(previous_plan)
        thread_store.add_user_message(thread.thread_id, "Confirm the current plan.")
        thread_store.add_assistant_message(
            thread.thread_id,
            "Execution prompt and settings confirmed. Starting the requested generation now.",
            asset_ids=[],
            job_id="",
        )
        return VideoPlanResponse(plan=previous_plan)

    reference_assets = [_asset_by_id(asset_id) for asset_id in request.reference_asset_ids]
    reference_assets = [asset for asset in reference_assets if asset is not None]
    payload = _video_plan_payload(
        request=request,
        source_asset=source_asset,
        reference_assets=reference_assets,
        previous_plan=previous_plan,
    )
    beats = _normalize_video_beats(payload.get("beats"), request.duration_seconds)
    summary = str(payload.get("summary", "")).strip()
    playable_asset_manifest = _normalize_playable_asset_manifest(payload.get("asset_manifest"))
    if request.video_generation_mode == VideoGenerationMode.video_to_playable:
        payload["asset_manifest"] = playable_asset_manifest
    requested_execution = _is_explicit_video_execution_request(request.prompt)
    # A video alone is enough to analyze the mechanic, but not enough to render a
    # faithful playable. Keep the conversation in asset-brief mode until a future
    # build step maps advertiser-provided assets into a selected runtime template.
    if request.video_generation_mode == VideoGenerationMode.video_to_playable:
        requested_execution = False
    questions = [str(item) for item in payload.get("questions", []) if str(item).strip()] if isinstance(payload.get("questions"), list) else []
    if requested_execution:
        questions = []
    assistant_reply = summary or str(payload.get("objective", "I have prepared a video generation plan based on the supplied assets.")).strip()
    if request.video_generation_mode == VideoGenerationMode.video_to_playable:
        assistant_reply = f"{assistant_reply}{_playable_asset_brief(playable_asset_manifest)}".strip()
    if not requested_execution and questions and questions[0] not in assistant_reply:
        assistant_reply = f"{assistant_reply}\n\n{questions[0]}".strip()
    conversation = [*(previous_plan.conversation if previous_plan else [])]
    if request.prompt.strip():
        conversation.append(VideoPlanConversationMessage(role="user", text=request.prompt.strip()))
    if assistant_reply:
        conversation.append(VideoPlanConversationMessage(role="assistant", text=assistant_reply))

    plan = VideoGenerationPlan(
        plan_id=previous_plan.plan_id if previous_plan else f"vplan_{uuid4().hex[:12]}",
        workspace_id=request.workspace_id,
        thread_id=thread.thread_id,
        created_by=user.id,
        mode=request.video_generation_mode,
        source_asset_id=source_asset.id,
        reference_asset_ids=[asset.id for asset in reference_assets],
        status="confirmed" if requested_execution else "draft",
        objective=str(payload.get("objective", "Video generation plan")),
        summary=summary,
        keep=[str(item) for item in payload.get("keep", []) if str(item).strip()] if isinstance(payload.get("keep"), list) else [],
        change=[str(item) for item in payload.get("change", []) if str(item).strip()] if isinstance(payload.get("change"), list) else [],
        avoid=[str(item) for item in payload.get("avoid", []) if str(item).strip()] if isinstance(payload.get("avoid"), list) else [],
        recommended_settings={str(key): str(value) for key, value in payload.get("recommended_settings", {}).items()} if isinstance(payload.get("recommended_settings"), dict) else {},
        generation_prompt=str(payload.get("generation_prompt", request.prompt)).strip(),
        beats=beats,
        questions=questions,
        interaction_concept={
            **(payload.get("interaction_concept", {}) if isinstance(payload.get("interaction_concept"), dict) else {}),
            **({"asset_manifest": playable_asset_manifest} if playable_asset_manifest else {}),
        },
        execution_intent="generate" if requested_execution else "chat",
        conversation=conversation,
        created_at=previous_plan.created_at if previous_plan else datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    _persist_video_plan(plan)
    # Attach source material exactly once per thread. Later turns inherit the
    # persisted plan and should remain clean text messages.
    attached_asset_ids = {asset_id for message in thread.messages for asset_id in message.asset_ids}
    candidate_asset_ids = [source_asset.id, *[asset.id for asset in reference_assets]]
    message_asset_ids = candidate_asset_ids if not any(
        asset_id in attached_asset_ids for asset_id in candidate_asset_ids
    ) else []
    thread_store.add_user_message(
        thread.thread_id,
        request.prompt or "Analyze the attached assets and propose a video generation plan.",
        reference_asset_ids=message_asset_ids,
    )
    thread_store.add_assistant_message(
        thread.thread_id,
        assistant_reply,
        asset_ids=[],
        job_id="",
    )
    thread_store.touch_thread(thread.thread_id, title=_thread_title_from_video_request(_plan_request_as_generation_request(request, thread.thread_id)))
    return VideoPlanResponse(plan=plan)


def confirm_video_generation_plan_for_request(request: VideoGenerationRequest, user: User) -> VideoGenerationRequest:
    if request.video_generation_mode not in {
        VideoGenerationMode.image_to_video,
        VideoGenerationMode.competitor_style_transfer,
        VideoGenerationMode.video_to_playable,
    }:
        return request
    if request.video_generation_mode == VideoGenerationMode.video_to_playable:
        raise RuntimeError(
            "Video to Playable first produces an asset brief. Upload the requested advertiser assets and select a runtime template before building a playable."
        )
    if not request.plan_id:
        raise RuntimeError("Analyze and confirm a video generation plan before generating.")
    plan = _lookup_video_plan(request.plan_id)
    if not plan or plan.status != "confirmed":
        raise RuntimeError("Confirm the current video plan before generating.")
    if plan.workspace_id != request.workspace_id or plan.created_by != user.id:
        raise RuntimeError("This video plan is not available to the current user.")
    if plan.mode != request.video_generation_mode or plan.source_asset_id != request.source_asset_id:
        raise RuntimeError("The confirmed plan does not match the selected video workflow or source asset.")
    return request.model_copy(
        update={
            "prompt": plan.generation_prompt,
            "thread_id": plan.thread_id,
            "sequence_beats": plan.beats,
        }
    )


def _resolve_veo_model_id(request: VideoGenerationRequest) -> str:
    settings = get_settings()
    requested = (request.model or "").strip()
    if requested in {"veo-3.1-fast", "veo-3.1", ""}:
        return (settings.vertex_veo_fast_model or "").strip()
    return requested


def _guess_video_dimensions(aspect_ratio: str, resolution: str = "1080p") -> tuple[int, int]:
    if resolution == "720p":
        return (720, 1280) if aspect_ratio == "9:16" else (1280, 720)
    return (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)


def _asset_by_id(asset_id: str | None) -> Asset | None:
    if not asset_id:
        return None
    return ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)


def _image_from_asset(asset: Asset) -> genai_types.Image:
    image_bytes = read_asset_bytes(asset)
    if not image_bytes:
        raise RuntimeError(f"Could not read image bytes for asset {asset.id}")
    mime = _guess_content_type(asset.title or f"{asset.id}{guess_asset_extension(asset)}", "image/png")
    return genai_types.Image(image_bytes=image_bytes, mime_type=mime)


def _video_from_asset(asset: Asset) -> genai_types.Video:
    video_bytes = read_asset_bytes(asset)
    if not video_bytes:
        raise RuntimeError(f"Could not read video bytes for asset {asset.id}")
    mime = _guess_content_type(asset.title or f"{asset.id}{guess_asset_extension(asset)}", "video/mp4")
    return genai_types.Video(video_bytes=video_bytes, mime_type=mime)


def _first_frame_from_video_asset(asset: Asset) -> genai_types.Image:
    """Extract a visual anchor so Veo can regenerate a source video via I2V."""
    source_bytes = read_asset_bytes(asset)
    if not source_bytes:
        raise RuntimeError(f"Could not read video bytes for asset {asset.id}")
    settings = get_settings()
    configured_ffmpeg = settings.playable_capture_ffmpeg_path.strip()
    ffmpeg_path = configured_ffmpeg if configured_ffmpeg and Path(configured_ffmpeg).is_file() else shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("Video to Video requires FFmpeg to extract the source visual anchor.")

    source_ext = Path(asset.title or "source.mp4").suffix or ".mp4"
    with tempfile.TemporaryDirectory(prefix="incept-video-anchor-") as temp_dir:
        source_path = Path(temp_dir) / f"source{source_ext}"
        frame_path = Path(temp_dir) / "anchor.jpg"
        source_path.write_bytes(source_bytes)
        completed = subprocess.run(
            [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source_path), "-frames:v", "1", "-q:v", "2", str(frame_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0 or not frame_path.is_file():
            details = completed.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"Could not extract a visual anchor from the source video. {details[-500:]}")
        return genai_types.Image(image_bytes=frame_path.read_bytes(), mime_type="image/jpeg")


def _reference_images_from_assets(asset_ids: list[str]) -> list[genai_types.VideoGenerationReferenceImage]:
    references: list[genai_types.VideoGenerationReferenceImage] = []
    for asset_id in asset_ids:
        asset = _asset_by_id(asset_id)
        if not asset:
            continue
        if asset.type != "image":
            continue
        references.append(
            genai_types.VideoGenerationReferenceImage(
                image=_image_from_asset(asset),
                reference_type=genai_types.VideoGenerationReferenceType.ASSET,
            )
        )
    return references


def _build_generate_video_kwargs(
    request: VideoGenerationRequest,
    *,
    model_id: str,
    source_image_override: genai_types.Image | None = None,
) -> dict:
    source_asset = _asset_by_id(request.source_asset_id)
    end_frame_asset = _asset_by_id(request.end_frame_asset_id)
    # Veo rejects a request containing both an image anchor and referenceImages.
    # Supporting assets still inform the Flash-Lite plan and its final prompt, but
    # the Veo request uses the single primary image anchor for these workflows.
    uses_image_anchor = source_image_override is not None or (
        source_asset is not None
        and source_asset.type == "image"
        and request.video_generation_mode.value
        in {
            "image_to_video",
            "competitor_style_transfer",
            "reference_character",
            "prompt_assist",
            "video_remediation",
            "synthetic_recast",
            "playable_to_video",
        }
    )
    config_kwargs: dict[str, object] = {
        "number_of_videos": request.variants,
        "duration_seconds": request.duration_seconds,
        "aspect_ratio": request.aspect_ratio,
        "resolution": request.resolution,
        "generate_audio": False,
        "enhance_prompt": True,
        "negative_prompt": (
            "warped face, broken anatomy, inconsistent identity, extra limbs, "
            "flickering background, corrupted text, low quality motion"
        ),
    }
    if uses_image_anchor:
        if request.reference_asset_ids:
            logger.info(
                "Veo request uses an image anchor; omitting %d reference image(s) from the API call. "
                "They remain available to the Flash-Lite planning pass.",
                len(request.reference_asset_ids),
            )
    else:
        reference_images = _reference_images_from_assets(request.reference_asset_ids)
        if reference_images:
            config_kwargs["reference_images"] = reference_images

    config = genai_types.GenerateVideosConfig(**config_kwargs)

    mode = request.video_generation_mode.value
    kwargs: dict = {
        "model": model_id,
        "prompt": request.prompt or "",
        "config": config,
    }

    if mode in {
        "image_to_video",
        "competitor_style_transfer",
        "reference_character",
        "prompt_assist",
        "video_remediation",
        "synthetic_recast",
        "playable_to_video",
    }:
        if not source_asset:
            raise RuntimeError("A source image is required for this video mode.")
        if source_image_override is not None:
            kwargs["image"] = source_image_override
            return kwargs
        if source_asset.type != "image":
            raise RuntimeError("The selected source asset must be an image for this video mode.")
        kwargs["image"] = _image_from_asset(source_asset)
        return kwargs

    if mode in {"first_last_frame", "multi_shot_storyboard"}:
        if not source_asset or source_asset.type != "image":
            raise RuntimeError("A start-frame image is required for storyboard video generation.")
        if not end_frame_asset or end_frame_asset.type != "image":
            raise RuntimeError("An end-frame image is required for storyboard video generation.")
        config.lastFrame = _image_from_asset(end_frame_asset)
        kwargs["image"] = _image_from_asset(source_asset)
        return kwargs

    if mode == "extend_video":
        if not source_asset:
            raise RuntimeError("A source video is required to extend a shot.")
        if source_asset.type != "video":
            raise RuntimeError("Extend Video currently requires a video asset as the source.")
        kwargs["video"] = _video_from_asset(source_asset)
        return kwargs

    raise RuntimeError(f"Unsupported video generation mode: {mode}")


async def _wait_for_operation(client: genai.Client, operation) -> genai_types.GenerateVideosResponse:
    current = operation
    for _ in range(120):
        if getattr(current, "done", False):
            if getattr(current, "error", None):
                raise RuntimeError(str(current.error))
            result = getattr(current, "result", None) or getattr(current, "response", None)
            if result is None:
                raise RuntimeError("Veo operation completed without a result payload.")
            return result
        await asyncio.sleep(5)
        current = client.operations.get(current)
    raise RuntimeError("Timed out while waiting for Veo video generation to complete.")


async def _download_generated_video_bytes(uri: str) -> bytes | None:
    if uri.startswith("gs://"):
        return _download_bytes_from_gcs(uri)
    if uri.startswith("http://") or uri.startswith("https://"):
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(uri)
            response.raise_for_status()
            return response.content
    return None


async def _request_veo_videos(
    *,
    client: genai.Client,
    kwargs: dict,
    job: GenerationJob,
    progress: int,
    message: str,
) -> list[genai_types.Video]:
    """Submit one Veo operation and normalize every result to in-memory bytes."""
    operation = client.models.generate_videos(**kwargs)
    job.progress = progress
    job.message = message
    job.updated_at = datetime.utcnow()
    upsert_job(job)

    response = await _wait_for_operation(client, operation)
    generated_videos = response.generated_videos or []
    if not generated_videos:
        raise RuntimeError("Veo completed but returned no generated videos.")

    normalized: list[genai_types.Video] = []
    for generated_video in generated_videos:
        video = generated_video.video
        if video is None:
            continue
        content = video.video_bytes
        if content is None and video.uri:
            try:
                content = await _download_generated_video_bytes(video.uri)
            except Exception as exc:
                raise RuntimeError(f"Could not download generated video output: {exc}") from exc
        if not content:
            raise RuntimeError("Generated video payload contained neither downloadable bytes nor a GCS uri.")
        normalized.append(
            genai_types.Video(
                uri=video.uri,
                video_bytes=content,
                mime_type=video.mime_type or "video/mp4",
            )
        )
    if not normalized:
        raise RuntimeError("Veo completed without usable video data.")
    return normalized


def _beats_for_sequence_window(
    beats: list[VideoGenerationBeat],
    *,
    start_seconds: int,
    end_seconds: int,
) -> list[VideoGenerationBeat]:
    selected: list[VideoGenerationBeat] = []
    cursor = 0
    for beat in beats:
        beat_end = cursor + beat.duration_seconds
        if beat_end > start_seconds and cursor < end_seconds:
            selected.append(beat)
        cursor = beat_end
    return selected


def _sequence_segment_prompt(
    *,
    master_prompt: str,
    beats: list[VideoGenerationBeat],
    start_seconds: int,
    end_seconds: int,
    is_initial: bool,
) -> str:
    selected = _beats_for_sequence_window(beats, start_seconds=start_seconds, end_seconds=end_seconds)
    beat_lines = "\n".join(
        (
            f"- {beat.title}: {beat.purpose} "
            f"Start: {beat.start_state or 'continue the established scene.'} "
            f"End: {beat.end_state or 'leave a clear handoff to the next beat.'} "
            f"Direction: {beat.veo_brief or beat.purpose}"
        )
        for beat in selected
    )
    phase = "opening" if is_initial else "continuation"
    return (
        f"Master creative direction:\n{master_prompt.strip()}\n\n"
        f"This is the {phase} window from {start_seconds}s to {end_seconds}s of one continuous commercial. "
        "Advance only the planned beats below. Do not replay the opening, restart the scene, or introduce unrelated actions.\n"
        f"{beat_lines or '- Continue the next natural action without repeating the previous moment.'}\n\n"
        "Continuity requirements: preserve the established subject identity, scene layout, lighting, lens, camera direction, "
        "motion direction, and color grade. End in a state that naturally hands off to the next window."
    )


def _stage_sequence_clip_in_gcs(
    *,
    content: bytes,
    job: GenerationJob,
    request: VideoGenerationRequest,
    variant_index: int,
    segment_index: int,
) -> str:
    object_path = _build_gcs_object_path(
        category="video-sequences",
        workspace_id=request.workspace_id,
        created_at=job.created_at,
        job_id=job.job_id,
        filename=f"{job.lineage_key}_v{variant_index + 1}_segment{segment_index + 1}.mp4",
    )
    gcs_uri = _upload_bytes_to_gcs(content=content, object_path=object_path, content_type="video/mp4")
    if not gcs_uri:
        raise RuntimeError(
            "Veo videos longer than 8 seconds require a working INCEPT_ASSET_BUCKET. "
            "Configure GCS write access so each segment can be passed to Veo Extend."
        )
    return gcs_uri


def _concat_video_sequence(*, clips: list[bytes], target_seconds: int) -> bytes:
    settings = get_settings()
    configured_ffmpeg = settings.playable_capture_ffmpeg_path.strip()
    ffmpeg_path = configured_ffmpeg if configured_ffmpeg and Path(configured_ffmpeg).is_file() else shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg is required to assemble multi-segment Veo videos.")

    with tempfile.TemporaryDirectory(prefix="incept-veo-sequence-") as temp_dir:
        root = Path(temp_dir)
        manifest = root / "segments.txt"
        clip_paths: list[Path] = []
        for index, content in enumerate(clips):
            path = root / f"segment-{index + 1}.mp4"
            path.write_bytes(content)
            clip_paths.append(path)
        manifest.write_text("".join(f"file '{path.as_posix()}'\n" for path in clip_paths), encoding="utf-8")

        joined = root / "joined.mp4"
        concat = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "24",
                "-movflags",
                "+faststart",
                str(joined),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if concat.returncode != 0 or not joined.is_file():
            details = concat.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"Could not assemble the Veo sequence. {details[-500:]}")

        output = root / "final.mp4"
        # Veo extends in fixed 7s increments. Export the exact requested duration
        # by trimming the final continuous segment instead of holding a still frame.
        finalize = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(joined),
                "-t",
                str(target_seconds),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "24",
                "-movflags",
                "+faststart",
                str(output),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if finalize.returncode != 0 or not output.is_file():
            details = finalize.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"Could not finalize the Veo sequence. {details[-500:]}")
        return output.read_bytes()


def _save_local_video_file(asset_id: str, content: bytes, extension: str) -> str:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    normalized_ext = extension if extension.startswith(".") else f".{extension}"
    dest = STATIC_DIR / f"{asset_id}{normalized_ext}"
    dest.write_bytes(content)
    return f"/static/generated/{asset_id}{normalized_ext}"


def _persist_generated_video_asset(
    *,
    job: GenerationJob,
    request: VideoGenerationRequest,
    user: User,
    model_id: str,
    idx: int,
    generated_video: genai_types.GeneratedVideo,
) -> Asset:
    video = generated_video.video
    if video is None:
        raise RuntimeError("Generated video payload is empty.")

    extension = ".mp4"
    if video.mime_type:
        guessed_ext = mimetypes.guess_extension(video.mime_type, strict=False)
        if guessed_ext:
            extension = guessed_ext
    elif video.uri:
        uri_suffix = Path(video.uri.split("?")[0]).suffix
        if uri_suffix:
            extension = uri_suffix

    content: bytes | None = video.video_bytes
    width, height = _guess_video_dimensions(request.aspect_ratio, request.resolution)
    asset_id = f"{job.lineage_key}_{request.aspect_ratio.replace(':', 'x')}_{idx + 1}_vid"
    preview_url = build_asset_content_path(asset_id)
    gcs_uri = ""

    if content is not None:
        preview_url = _save_local_video_file(asset_id, content, extension)
        object_path = _build_gcs_object_path(
            category="generated",
            workspace_id=request.workspace_id,
            created_at=job.created_at,
            job_id=job.job_id,
            filename=f"{asset_id}{extension}",
        )
        gcs_uri = _upload_bytes_to_gcs(
            content=content,
            object_path=object_path,
            content_type=video.mime_type or _guess_content_type(f"video{extension}", "video/mp4"),
        )
    elif video.uri and video.uri.startswith("gs://"):
        gcs_uri = video.uri
    else:
        raise RuntimeError("Generated video payload contained neither downloadable bytes nor a GCS uri.")

    source_asset = _asset_by_id(request.source_asset_id)
    if source_asset and source_asset.title:
        base_title = _normalized_source_title(source_asset.title) or "generated_video"
    else:
        base_title = "_".join(_thread_title_from_video_request(request).split()).strip("._-") or "generated_video"
    asset = Asset(
        id=asset_id,
        title=f"{base_title}_video{idx + 1}",
        type="video",
        gcs_uri=gcs_uri,
        preview_url=preview_url,
        provider=request.provider,
        model=model_id,
        workspace_id=request.workspace_id,
        job_id=job.job_id,
        prompt_hash="",
        created_by=user.id,
        created_at=job.created_at,
        width=width,
        height=height,
        theme=None,
        asset_role=AssetRole.generated,
        analysis={
            "video": {
                "mode": request.video_generation_mode.value,
                "aspect_ratio": request.aspect_ratio,
                "duration_seconds": request.duration_seconds,
                "include_audio": request.include_audio,
                "camera_preset": request.camera_preset,
                "variants": request.variants,
                "mime_type": video.mime_type or _guess_content_type(f"video{extension}", "video/mp4"),
            }
        },
        thread_id=job.thread_id,
        parent_asset_id=source_asset.id if source_asset else None,
        root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
    )
    _record_asset_storage_status(asset, category="generated")
    ASSETS[asset_id] = asset
    upsert_asset(asset)
    return asset


def _persist_browser_capture_video_asset(
    *,
    job: GenerationJob,
    request: VideoGenerationRequest,
    user: User,
    source_asset: Asset,
    content: bytes,
    capture_analysis: dict[str, object],
) -> Asset:
    asset_id = f"{job.lineage_key}_{request.aspect_ratio.replace(':', 'x')}_capture"
    extension = ".mp4"
    preview_url = _save_local_video_file(asset_id, content, extension)
    object_path = _build_gcs_object_path(
        category="generated",
        workspace_id=request.workspace_id,
        created_at=job.created_at,
        job_id=job.job_id,
        filename=f"{asset_id}{extension}",
    )
    gcs_uri = _upload_bytes_to_gcs(content=content, object_path=object_path, content_type="video/mp4")
    width, height = _guess_video_dimensions(request.aspect_ratio, request.resolution)
    base_title = _normalized_source_title(source_asset.title) or "playable"
    llm_summary = capture_analysis.get("llm_summary")
    interaction_plan = llm_summary.get("interaction_plan", []) if isinstance(llm_summary, dict) else []
    asset = Asset(
        id=asset_id,
        title=f"{base_title}_video1",
        type="video",
        gcs_uri=gcs_uri or f"local://generated/{asset_id}{extension}",
        preview_url=preview_url,
        provider="internal",
        model="creative-core-browser-capture",
        workspace_id=request.workspace_id,
        job_id=job.job_id,
        prompt_hash="",
        created_by=user.id,
        created_at=job.created_at,
        width=width,
        height=height,
        asset_role=AssetRole.generated,
        analysis={
            "video": {
                "mode": "playable_to_video",
                "aspect_ratio": request.aspect_ratio,
                "duration_seconds": request.duration_seconds,
                "capture_engine": "creative-core-chrome-cdp",
                "interaction_plan": interaction_plan,
            }
        },
        thread_id=job.thread_id,
        parent_asset_id=source_asset.id,
        root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
    )
    _record_asset_storage_status(asset, category="generated")
    ASSETS[asset.id] = asset
    upsert_asset(asset)
    return asset


def create_video_generation_job(request: VideoGenerationRequest, user: User) -> GenerationJob:
    thread = _resolve_thread_for_video_request(request, user)
    now = datetime.utcnow()
    job = GenerationJob(
        job_id=f"job_{uuid4().hex[:12]}",
        workspace_id=request.workspace_id,
        status=JobStatus.running,
        progress=5,
        lineage_key=f"llg_vid_{uuid4().hex[:16]}",
        message="Preparing video workflow…",
        tool_id="veo-video",
        title=f"Video generation — {request.video_generation_mode.value}",
        output_asset_ids=[],
        thread_id=thread.thread_id,
        source_asset_id=request.source_asset_id,
        created_at=now,
        updated_at=now,
    )
    JOBS[job.job_id] = job
    upsert_job(job)
    thread_store.touch_thread(
        job.thread_id,
        latest_job_id=job.job_id,
        title=_thread_title_from_video_request(request),
    )
    return job


async def _execute_veo_generation(
    *,
    job: GenerationJob,
    request: VideoGenerationRequest,
    user: User,
    model_id: str,
    source_image_override: genai_types.Image | None = None,
) -> list[Asset]:
    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.vertex_veo_location,
    )
    kwargs = _build_generate_video_kwargs(
        request,
        model_id=model_id,
        source_image_override=source_image_override,
    )
    generated_videos = await _request_veo_videos(
        client=client,
        kwargs=kwargs,
        job=job,
        progress=35,
        message="Veo accepted the request. Waiting for generation to finish…",
    )

    created_assets: list[Asset] = []
    for idx, video in enumerate(generated_videos):
        created_assets.append(
            _persist_generated_video_asset(
                job=job,
                request=request,
                user=user,
                model_id=model_id,
                idx=idx,
                generated_video=genai_types.GeneratedVideo(video=video),
            )
        )
    return created_assets


async def _execute_veo_sequence(
    *,
    job: GenerationJob,
    request: VideoGenerationRequest,
    user: User,
    model_id: str,
    source_image_override: genai_types.Image | None = None,
) -> list[Asset]:
    """Generate a beat-driven Veo sequence and trim its final continuous clip."""
    initial_duration, extension_count, trim_seconds = _sequence_extension_plan(request.duration_seconds)
    beats = request.sequence_beats or _fallback_video_beats(request.duration_seconds)
    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.vertex_veo_location,
    )
    initial_request = request.model_copy(
        update={
            "duration_seconds": initial_duration,
            "prompt": _sequence_segment_prompt(
                master_prompt=request.prompt,
                beats=beats,
                start_seconds=0,
                end_seconds=initial_duration,
                is_initial=True,
            ),
        }
    )
    initial_kwargs = _build_generate_video_kwargs(
        initial_request,
        model_id=model_id,
        source_image_override=source_image_override,
    )
    initial_videos = await _request_veo_videos(
        client=client,
        kwargs=initial_kwargs,
        job=job,
        progress=25,
        message="Generating the first Veo shot for a continuous sequence…",
    )

    created_assets: list[Asset] = []
    for variant_index, initial_video in enumerate(initial_videos):
        clips = [initial_video.video_bytes]
        if not clips[0]:
            raise RuntimeError("The initial Veo shot did not return video bytes.")
        current_uri = _stage_sequence_clip_in_gcs(
            content=clips[0],
            job=job,
            request=request,
            variant_index=variant_index,
            segment_index=0,
        )

        for extension_index in range(extension_count):
            step = extension_index + 1
            segment_start = initial_duration + ((step - 1) * 7)
            continuation_prompt = _sequence_segment_prompt(
                master_prompt=request.prompt,
                beats=beats,
                start_seconds=segment_start,
                end_seconds=segment_start + 7,
                is_initial=False,
            )
            extension_kwargs = {
                "model": model_id,
                "prompt": continuation_prompt,
                "video": genai_types.Video(uri=current_uri, mime_type="video/mp4"),
                "config": genai_types.GenerateVideosConfig(
                    number_of_videos=1,
                    aspect_ratio=request.aspect_ratio,
                    resolution=request.resolution,
                    generate_audio=False,
                    enhance_prompt=True,
                    negative_prompt=(
                        "scene restart, repeated opening, hard cut, unrelated new scene, character change, "
                        "wardrobe change, camera jump, flickering background, corrupted text, low quality motion"
                    ),
                ),
            }
            progress = min(88, 30 + int(((variant_index * extension_count + step) / max(1, len(initial_videos) * extension_count)) * 55))
            extension_videos = await _request_veo_videos(
                client=client,
                kwargs=extension_kwargs,
                job=job,
                progress=progress,
                message=f"Extending continuous Veo sequence: segment {step}/{extension_count}…",
            )
            extension_video = extension_videos[0]
            if not extension_video.video_bytes:
                raise RuntimeError("A Veo extension did not return video bytes.")
            clips.append(extension_video.video_bytes)
            current_uri = _stage_sequence_clip_in_gcs(
                content=extension_video.video_bytes,
                job=job,
                request=request,
                variant_index=variant_index,
                segment_index=step,
            )

        job.progress = 92
        job.message = "Assembling the continuous Veo sequence…"
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        final_video = _concat_video_sequence(clips=clips, target_seconds=request.duration_seconds)
        asset = _persist_generated_video_asset(
            job=job,
            request=request,
            user=user,
            model_id=model_id,
            idx=variant_index,
            generated_video=genai_types.GeneratedVideo(
                video=genai_types.Video(video_bytes=final_video, mime_type="video/mp4")
            ),
        )
        asset.analysis = {
            **(asset.analysis or {}),
            "video": {
                **((asset.analysis or {}).get("video") or {}),
                "sequence": {
                    "initial_duration_seconds": initial_duration,
                    "extension_count": extension_count,
                    "trim_seconds": trim_seconds,
                    "target_duration_seconds": request.duration_seconds,
                    "assembly": "beat_driven_veo_extend_then_ffmpeg_trim",
                    "beats": [beat.model_dump() for beat in beats],
                },
            },
        }
        ASSETS[asset.id] = asset
        upsert_asset(asset)
        created_assets.append(asset)
    return created_assets


async def _execute_veo_request(
    *,
    job: GenerationJob,
    request: VideoGenerationRequest,
    user: User,
    model_id: str,
    source_image_override: genai_types.Image | None = None,
) -> list[Asset]:
    if request.duration_seconds > 8:
        return await _execute_veo_sequence(
            job=job,
            request=request,
            user=user,
            model_id=model_id,
            source_image_override=source_image_override,
        )
    return await _execute_veo_generation(
        job=job,
        request=request,
        user=user,
        model_id=model_id,
        source_image_override=source_image_override,
    )


def _build_playable_to_video_prompt(
    *,
    playable_summary: dict[str, object],
    llm_summary: dict[str, object],
    user_prompt: str,
) -> str:
    guidance = llm_summary.get("video_prompt_guidance") or llm_summary.get("summary") or ""
    return (
        "Create a polished mobile ad video based on the uploaded playable. "
        "Preserve the core game fantasy, UI mood, palette, and interaction energy inferred from the playable. "
        "Show the gameplay clearly, keep motion readable, and make the result feel like a premium ad cut. "
        f"Playable summary: {_safe_json_text(playable_summary)}. "
        f"LLM gameplay guidance: {guidance}. "
        f"User direction: {user_prompt.strip() or 'No extra user direction.'}"
    )


def _build_competitor_style_prompt(
    *,
    style_summary: dict[str, object],
    user_prompt: str,
) -> str:
    return (
        "Create a branded video that keeps the source content but borrows the reference video's visual DNA. "
        "Match the reference video's pacing, lighting, framing, texture, and motion energy while avoiding direct copying. "
        f"Reference style summary: {_safe_json_text(style_summary)}. "
        f"User direction: {user_prompt.strip() or 'No extra user direction.'}"
    )


def _report_markdown(title: str, payload: dict[str, object]) -> str:
    return f"# {title}\n\n```json\n{_safe_json_text(payload)}\n```"


def _analyze_playable_for_video(asset: Asset, user_prompt: str) -> dict[str, object]:
    local_summary = _summarize_playable_html_locally(asset)
    asset_bytes = read_asset_bytes(asset) or b""
    html_text = asset_bytes.decode("utf-8", errors="ignore")
    prompt = (
        "You are analyzing an HTML5 playable creative so it can be converted into a short ad video. "
        "Read the playable metadata and return compact JSON with these keys: "
        "gameplay_type, visual_style, likely_actions, cta_style, motion_plan, interaction_plan, video_prompt_guidance, risks. "
        "interaction_plan must be an array of 1-8 actions with type wait|click|drag|swipe, normalized x/y values "
        "from 0 to 1, optional normalized to_x/to_y for drag/swipe, and ms delay. "
        "Do not mention implementation details unless they affect the video. "
        f"User direction: {user_prompt.strip() or 'None'}. "
        f"Playable metadata: {_safe_json_text(local_summary)}"
    )
    response_text = _call_multimodal_text_model(
        prompt=prompt,
        parts=[],
        model_id=_video_analysis_model_id(),
    )
    return {
        "local_summary": local_summary,
        "moloco_validation": _moloco_playable_validation(html_text),
        "llm_summary": _parse_json_loose(response_text),
    }


def _analyze_reference_assets_for_style(reference_assets: list[Asset], user_prompt: str) -> dict[str, object]:
    if not reference_assets:
        return {
            "direction": "Preserve the source creative's core visual language unless the user direction says otherwise.",
            "user_direction": user_prompt.strip() or "None",
        }
    parts = [_asset_part_for_text_model(asset) for asset in reference_assets[:3]]
    prompt = (
        "Analyze the attached reference creative assets and extract only their visual style DNA for a new branded video. "
        "Return compact JSON with keys: color_palette, lighting, framing, motion_energy, transitions, cta_style, texture, "
        "mood, voice_of_motion, do_not_copy. Keep it style-only. "
        f"User direction: {user_prompt.strip() or 'None'}."
    )
    response_text = _call_multimodal_text_model(
        prompt=prompt,
        parts=parts,
        model_id=_video_analysis_model_id(),
    )
    return _parse_json_loose(response_text)


def _analyze_video_for_playable(asset: Asset, user_prompt: str) -> dict[str, object]:
    parts = [_asset_part_for_text_model(asset)]
    prompt = (
        "Analyze the attached video for a high-fidelity HTML5 playable production brief. "
        "Return compact JSON with keys: gameplay_category, interaction_loop, state_machine, main_reward_hook, cta_strategy, "
        "recommended_template, reusable_assets, asset_manifest, constraints. "
        "asset_manifest is an array of production assets. Each entry must include name, category, required, count, preferred_format, "
        "minimum_size_px, aspect_ratio, purpose, and library_fallback. The asset list must cover backgrounds, interactive objects, logo, UI, CTA, "
        "end card, visual effects, and optional audio when applicable. Do not copy artwork from the source video; describe authorized assets the advertiser should provide. "
        f"User direction: {user_prompt.strip() or 'None'}."
    )
    response_text = _call_multimodal_text_model(
        prompt=prompt,
        parts=parts,
        model_id=_video_analysis_model_id(),
    )
    return _parse_json_loose(response_text)


def _build_playable_draft(
    *,
    source_video: Asset,
    reference_assets: list[Asset],
    analysis: dict[str, object],
    user_prompt: str,
) -> dict[str, object]:
    """Ask the playable model for creative data, never executable JavaScript."""
    settings = get_settings()
    if not settings.vertex_playable_model.strip():
        raise RuntimeError("VERTEX_PLAYABLE_MODEL is not configured.")
    prompt = (
        "You are a playable-ad creative director. Turn the attached source video analysis into a compact "
        "Moloco standalone playable draft. Return JSON only with exactly these keys: "
        "template (tap_choice|swipe_collect|drag_and_drop), title, headline, instruction, cta_label, "
        "reward_label, primary_color, secondary_color, accent_color, visual_direction, and choices. "
        "choices must be an array of exactly two short strings. Do not return HTML, CSS, JavaScript, URLs, "
        "brand claims you cannot infer, real-person likenesses, or copyrighted characters. The output is "
        "creative configuration for a fixed runtime, not code. "
        f"Source analysis: {_safe_json_text(analysis)}. "
        f"User direction: {user_prompt.strip() or 'None'}."
    )
    parts = [_asset_part_for_text_model(source_video)]
    parts.extend(_asset_part_for_text_model(asset) for asset in reference_assets[:2])
    response_text = _call_multimodal_text_model(
        prompt=prompt,
        parts=parts,
        model_id=settings.vertex_playable_model,
    )
    draft = _parse_json_loose(response_text)
    if "raw" in draft:
        raise RuntimeError("Gemini playable draft did not return structured JSON.")
    return draft


def _draft_text(draft: dict[str, object], key: str, fallback: str, max_length: int = 80) -> str:
    value = draft.get(key)
    if not isinstance(value, str) or not value.strip():
        return fallback
    return " ".join(value.split())[:max_length]


def _draft_color(draft: dict[str, object], key: str, fallback: str) -> str:
    value = draft.get(key)
    if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()):
        return value.strip()
    return fallback


def _draft_choices(draft: dict[str, object]) -> tuple[str, str]:
    value = draft.get("choices")
    if isinstance(value, list):
        choices = [" ".join(str(item).split())[:36] for item in value if str(item).strip()]
        if len(choices) >= 2:
            return choices[0], choices[1]
    return "Try it", "Play now"


def _inline_reference_visual(reference_assets: list[Asset]) -> str:
    """Use a compact reference image when present; never embed an oversized source video."""
    for asset in reference_assets:
        if asset.type != "image":
            continue
        content = read_asset_bytes(asset)
        if not content or len(content) > 1_500_000:
            continue
        data_uri = _data_uri_for_asset(asset)
        if data_uri:
            return data_uri
    return ""


def _render_moloco_playable_html(
    *,
    draft: dict[str, object],
    reference_assets: list[Asset],
) -> str:
    """Render a deterministic, self-contained playable from model-provided data."""
    title = html.escape(_draft_text(draft, "title", "Interactive Challenge", 56))
    headline = html.escape(_draft_text(draft, "headline", "Can you beat this challenge?", 72))
    instruction = html.escape(_draft_text(draft, "instruction", "Choose the winning move", 88))
    cta_label = html.escape(_draft_text(draft, "cta_label", "INSTALL NOW", 32))
    reward_label = html.escape(_draft_text(draft, "reward_label", "Great choice!", 48))
    choice_a, choice_b = (html.escape(value) for value in _draft_choices(draft))
    primary = _draft_color(draft, "primary_color", "#101B4D")
    secondary = _draft_color(draft, "secondary_color", "#5D3FD3")
    accent = _draft_color(draft, "accent_color", "#F7C948")
    visual_uri = _inline_reference_visual(reference_assets)
    visual_markup = (
        f'<img class="reference-visual" src="{visual_uri}" alt="" />'
        if visual_uri
        else '<div class="generated-orb orb-one"></div><div class="generated-orb orb-two"></div>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; font-family: Arial, sans-serif; }}
    body {{ background: {primary}; color: #fff; }}
    #playable {{ position: relative; width: 100%; height: 100%; min-height: 100svh; overflow: hidden; background: linear-gradient(160deg, {primary}, {secondary}); display: flex; align-items: stretch; justify-content: center; }}
    .scene {{ position: relative; width: min(100%, 56.25svh); min-width: 320px; max-width: 100vw; height: 100%; padding: max(20px, env(safe-area-inset-top)) 22px max(24px, env(safe-area-inset-bottom)); display: flex; flex-direction: column; align-items: center; text-align: center; isolation: isolate; }}
    .reference-visual {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: .32; z-index: -2; }}
    .scene::after {{ content: ''; position: absolute; inset: 0; z-index: -1; background: linear-gradient(180deg, rgba(8,12,38,.12), rgba(8,12,38,.85)); }}
    .generated-orb {{ position: absolute; border-radius: 999px; filter: blur(2px); opacity: .42; z-index: -2; }}
    .orb-one {{ width: 62vw; height: 62vw; top: -18vw; right: -25vw; background: {accent}; }}
    .orb-two {{ width: 70vw; height: 70vw; bottom: -32vw; left: -32vw; background: #49C6FF; }}
    .brand {{ margin-top: 3vh; border: 1px solid rgba(255,255,255,.38); border-radius: 999px; background: rgba(6,12,36,.28); padding: 7px 12px; font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ margin: 5vh 0 10px; max-width: 10ch; font-size: clamp(30px, 7vw, 54px); line-height: .98; letter-spacing: -.04em; text-shadow: 0 4px 18px rgba(0,0,0,.26); }}
    .instruction {{ margin: 0; max-width: 24ch; font-size: clamp(15px, 3.9vw, 22px); line-height: 1.3; color: rgba(255,255,255,.88); }}
    .play-area {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; width: 100%; margin: auto 0 24px; }}
    .choice {{ min-height: 132px; border: 2px solid rgba(255,255,255,.36); border-radius: 24px; background: rgba(255,255,255,.14); color: #fff; font: inherit; font-size: clamp(18px, 4.5vw, 26px); font-weight: 800; line-height: 1.05; padding: 20px 10px; box-shadow: 0 15px 28px rgba(0,0,0,.18); transition: transform .18s ease, background .18s ease; }}
    .choice:active {{ transform: scale(.96); }}
    .choice.correct {{ background: {accent}; color: #18151C; border-color: #fff; }}
    .result {{ position: absolute; inset: 0; display: none; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 28px; background: rgba(7,12,35,.76); backdrop-filter: blur(8px); }}
    .result.show {{ display: flex; }}
    .result strong {{ font-size: clamp(32px, 9vw, 58px); line-height: .95; }}
    .cta {{ border: 0; border-radius: 999px; background: {accent}; color: #1b1720; padding: 16px 28px; min-width: 190px; font: inherit; font-size: 17px; font-weight: 900; letter-spacing: .04em; box-shadow: 0 10px 0 rgba(0,0,0,.22); }}
  </style>
</head>
<body>
  <main id="playable" role="application" aria-label="{title}">
    <section class="scene">
      {visual_markup}
      <div class="brand">{title}</div>
      <h1>{headline}</h1>
      <p class="instruction">{instruction}</p>
      <div class="play-area" aria-label="Interactive choice">
        <button class="choice" type="button" data-choice="wrong">{choice_a}</button>
        <button class="choice" type="button" data-choice="correct">{choice_b}</button>
      </div>
      <div id="result" class="result" aria-live="polite">
        <strong>{reward_label}</strong>
        <p>Ready for the full experience?</p>
        <button id="cta" class="cta" type="button">{cta_label}</button>
      </div>
    </section>
  </main>
  <script>
    window.FbPlayableAd = window.FbPlayableAd || {{ onCTAClick: function () {{}} }};
    (function () {{
      var result = document.getElementById('result');
      var choices = document.querySelectorAll('.choice');
      for (var i = 0; i < choices.length; i += 1) {{
        choices[i].addEventListener('click', function () {{
          if (this.getAttribute('data-choice') === 'correct') {{
            this.classList.add('correct');
            result.classList.add('show');
          }} else {{
            this.animate([{{ transform: 'translateX(0)' }}, {{ transform: 'translateX(-10px)' }}, {{ transform: 'translateX(8px)' }}, {{ transform: 'translateX(0)' }}], {{ duration: 340 }});
          }}
        }});
      }}
      document.getElementById('cta').addEventListener('click', function () {{
        window.FbPlayableAd.onCTAClick();
      }});
    }}());
  </script>
</body>
</html>"""


def _record_video_usage(
    job: GenerationJob,
    request: VideoGenerationRequest,
    user: User,
    model_id: str,
    created_assets: list[Asset],
) -> None:
    provider_generations = request.variants
    if (
        request.video_generation_mode
        in {VideoGenerationMode.image_to_video, VideoGenerationMode.competitor_style_transfer}
        and request.duration_seconds > 8
    ):
        _initial_duration, extension_count, _tail_hold = _sequence_extension_plan(request.duration_seconds)
        provider_generations *= 1 + extension_count
    usage_id = f"use_{uuid4().hex[:12]}"
    usage_event = UsageEvent(
        id=usage_id,
        job_id=job.job_id,
        workspace_id=request.workspace_id,
        user_id=user.id,
        user_email=user.email,
        provider=request.provider,
        model=model_id,
        operation="video_generation",
        prompt_hash="",
        variants=request.variants,
        output_size_count=1,
        output_format="video",
        estimated_provider_generations=provider_generations,
        output_asset_count=len(created_assets),
        estimated_cost_usd=_estimate_video_cost_usd(request),
        created_at=datetime.utcnow(),
    )
    USAGE_EVENTS[usage_id] = usage_event
    upsert_usage_event(usage_event)
    persist_generation(job, created_assets, usage_event)


async def run_video_generation_background(job_id: str, request: VideoGenerationRequest, user: User) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    settings = get_settings()
    try:
        if not settings.gcp_project_id:
            raise RuntimeError("GCP_PROJECT_ID / GOOGLE_CLOUD_PROJECT is not configured for video workflows.")

        mode = request.video_generation_mode
        job.progress = 8 if mode == VideoGenerationMode.playable_to_video else 15
        job.message = (
            "Preparing playable browser capture…"
            if mode == VideoGenerationMode.playable_to_video
            else f"Preparing {mode.value} pipeline…"
        )
        job.updated_at = datetime.utcnow()
        upsert_job(job)

        created_assets: list[Asset] = []
        source_asset = _asset_by_id(request.source_asset_id)
        model_id = ""
        used_veo = False

        if mode == VideoGenerationMode.playable_to_video:
            if not source_asset:
                raise RuntimeError("Playable to Video requires a source HTML playable asset.")
            analysis = _analyze_playable_for_video(source_asset, request.prompt)
            asset_bytes = read_asset_bytes(source_asset)
            html_text = (asset_bytes or b"").decode("utf-8", errors="ignore")
            llm_summary = analysis.get("llm_summary", {})
            interaction_actions = llm_summary.get("interaction_plan", []) if isinstance(llm_summary, dict) else []
            capture_output = STATIC_DIR / f"{job.lineage_key}_browser_capture.mp4"
            job.progress = 25
            job.message = "Launching the playable in Chrome and starting the automated interaction path…"
            job.updated_at = datetime.utcnow()
            upsert_job(job)
            capture_result = await asyncio.to_thread(
                capture_playable_to_mp4,
                html_text=html_text,
                interaction_actions=interaction_actions,
                duration_seconds=request.duration_seconds,
                aspect_ratio=request.aspect_ratio,
                resolution=request.resolution,
                output_path=capture_output,
            )
            try:
                job.progress = 88
                job.message = "Encoding captured browser frames into MP4 and verifying visible gameplay…"
                job.updated_at = datetime.utcnow()
                upsert_job(job)
                capture_bytes = capture_result.video_path.read_bytes()
                created_assets.append(
                    _persist_browser_capture_video_asset(
                        job=job,
                        request=request,
                        user=user,
                        source_asset=source_asset,
                        content=capture_bytes,
                        capture_analysis=analysis,
                    )
                )
            finally:
                capture_result.video_path.unlink(missing_ok=True)
        elif mode == VideoGenerationMode.competitor_style_transfer:
            if not source_asset or source_asset.type != "video":
                raise RuntimeError("Video to Video requires a source video.")
            reference_assets = [_asset_by_id(asset_id) for asset_id in request.reference_asset_ids]
            reference_assets = [asset for asset in reference_assets if asset is not None]
            style_summary = _analyze_reference_assets_for_style(reference_assets, request.prompt)
            effective_request = request.model_copy(
                update={
                    "video_generation_mode": VideoGenerationMode.image_to_video,
                    "prompt": _build_competitor_style_prompt(
                        style_summary=style_summary,
                        user_prompt=request.prompt,
                    ),
                }
            )
            model_id = _resolve_veo_model_id(effective_request)
            if not model_id:
                raise RuntimeError("VERTEX_VEO_FAST_MODEL is not configured.")
            used_veo = True
            created_assets.extend(
                await _execute_veo_request(
                    job=job,
                    request=effective_request,
                    user=user,
                    model_id=model_id,
                    source_image_override=_first_frame_from_video_asset(source_asset),
                )
            )
        elif mode == VideoGenerationMode.video_to_playable:
            if not source_asset or source_asset.type != "video":
                raise RuntimeError("Video to Playable requires a source video.")
            analysis = _analyze_video_for_playable(source_asset, request.prompt)
            reference_assets = [_asset_by_id(asset_id) for asset_id in request.reference_asset_ids]
            reference_assets = [asset for asset in reference_assets if asset is not None]
            playable_draft = _build_playable_draft(
                source_video=source_asset,
                reference_assets=reference_assets,
                analysis=analysis,
                user_prompt=request.prompt,
            )
            playable_html = _render_moloco_playable_html(
                draft=playable_draft,
                reference_assets=reference_assets,
            )
            validation = _moloco_playable_validation(playable_html)
            report_asset = _persist_generated_report_asset(
                job=job,
                request=request,
                user=user,
                title=f"{Path(source_asset.title).stem}_playable_plan",
                content=_report_markdown(
                    "Video to Playable Analysis",
                    {
                        "analysis": analysis,
                        "playable_draft": playable_draft,
                        "moloco_validation": validation,
                    },
                ),
                source_asset=source_asset,
            )
            created_assets.append(report_asset)
            created_assets.append(
                _persist_generated_playable_asset(
                    job=job,
                    request=request,
                    user=user,
                    title=f"{Path(source_asset.title).stem}_playable_v1",
                    html_text=playable_html,
                    source_asset=source_asset,
                    analysis=playable_draft,
                )
            )
        else:
            model_id = _resolve_veo_model_id(request)
            if not model_id:
                raise RuntimeError("VERTEX_VEO_FAST_MODEL is not configured.")
            used_veo = True
            job.message = f"Submitting Veo job with model {model_id}…"
            job.updated_at = datetime.utcnow()
            upsert_job(job)
            created_assets = await _execute_veo_request(
                job=job,
                request=request,
                user=user,
                model_id=model_id,
            )

        job.output_asset_ids = [asset.id for asset in created_assets]
        job.status = JobStatus.completed
        job.progress = 100
        job.message = (
            f"Completed {request.video_generation_mode.value}. "
            f"Produced {len(created_assets)} output asset(s)."
        )
        job.updated_at = datetime.utcnow()
        upsert_job(job)

        if job.thread_id:
            video_assets = [asset for asset in created_assets if asset.type == "video"]
            non_video_assets = [asset for asset in created_assets if asset.type != "video"]
            latest_asset_id = (video_assets[-1].id if video_assets else created_assets[-1].id) if created_assets else None
            cover_asset_id = (video_assets[0].id if video_assets else created_assets[0].id) if created_assets else None
            if video_assets:
                for index, asset in enumerate(video_assets, start=1):
                    execution_label = (
                        "Browser capture brief used for this video"
                        if mode == VideoGenerationMode.playable_to_video
                        else "Veo prompt used for this video"
                    )
                    thread_store.add_assistant_message(
                        job.thread_id,
                        text=(
                            f"Generated video {index}/{len(video_assets)}: {asset.title}\n\n"
                            f"{execution_label}:\n{request.prompt}"
                        ),
                        asset_ids=[asset.id],
                        job_id=job.job_id,
                    )
            if non_video_assets or not video_assets:
                thread_store.add_assistant_message(
                    job.thread_id,
                    text=job.message,
                    asset_ids=[asset.id for asset in non_video_assets],
                    job_id=job.job_id,
                )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=latest_asset_id,
                cover_asset_id=cover_asset_id,
                title=_thread_title_from_video_request(request),
            )
        if used_veo:
            _record_video_usage(job, request, user, model_id, created_assets)
    except Exception as exc:
        logger.exception("Video generation failed for job %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = str(exc) or build_video_mock_completion_message(request)
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Video task failed: {job.message}",
                asset_ids=[],
                job_id=job.job_id,
            )
        job.updated_at = datetime.utcnow()
        upsert_job(job)
