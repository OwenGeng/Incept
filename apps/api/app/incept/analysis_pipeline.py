from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Iterable
from typing import Any

from PIL import Image

from app.incept.anchor_types import normalize_anchor_role
from app.incept.config import get_settings
from app.incept.guardrails import build_anchor_hints_from_manifest
from app.incept.layout_manifest import LayoutManifest, build_layout_manifest
from app.incept.models import Asset
from app.incept.orchestrator import detect_layout_anchors


def _read_image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(image_bytes)) as img:
        return img.width, img.height


def _existing_anchor_candidates(asset: Asset | None) -> list[dict[str, Any]]:
    if not asset or not isinstance(asset.analysis, dict):
        return []
    anchors = asset.analysis.get("anchors")
    if isinstance(anchors, list):
        return [item for item in anchors if isinstance(item, dict)]
    manifest = asset.analysis.get("layout_manifest")
    if isinstance(manifest, dict) and isinstance(manifest.get("anchors"), list):
        candidates: list[dict[str, Any]] = []
        for item in manifest.get("anchors", []):
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            if isinstance(bbox, dict):
                candidates.append(
                    {
                        "type": normalize_anchor_role(str(item.get("role") or item.get("type") or item.get("label") or "")),
                        "label": item.get("label") or item.get("role") or "anchor",
                        "confidence": item.get("confidence") or "medium",
                        "required": bool(item.get("must_preserve", True)),
                        "bbox": bbox,
                    }
                )
        return candidates
    return []


async def analyze_source_creative(
    *,
    source_bytes: bytes,
    source_asset: Asset | None,
    context_assets: list[Asset],
    api_key: str | None,
    task_manifest: dict[str, Any] | None = None,
) -> tuple[LayoutManifest, dict[str, Any]]:
    settings = get_settings()
    source_w, source_h = _read_image_size(source_bytes)
    hints = build_anchor_hints_from_manifest(task_manifest or {}, context_assets)

    existing_detected = _existing_anchor_candidates(source_asset)
    ocr_blocks, ocr_candidates, ocr_report = await _detect_ocr_candidates_gcp(
        source_bytes,
        settings=settings,
        source_width=source_w,
        source_height=source_h,
    )
    gemini_detected, gemini_report = await _detect_layout_anchors_gemini(
        source_bytes,
        hints=hints,
        settings=settings,
    )
    openai_detected: list[dict[str, Any]] = []
    if not gemini_detected:
        openai_detected = await detect_layout_anchors(source_bytes, api_key, hints=hints)

    detected = _merge_anchor_candidates(
        source_width=source_w,
        source_height=source_h,
        existing=existing_detected,
        gemini=gemini_detected,
        openai=openai_detected,
        ocr=ocr_candidates,
        ocr_blocks=ocr_blocks,
    )
    if gemini_detected and ocr_candidates:
        detection_source = "gemini_bbox_plus_gcp_vision_ocr"
    elif gemini_detected:
        detection_source = "gemini_bbox"
    elif openai_detected and ocr_candidates:
        detection_source = "openai_vision_plus_gcp_vision_ocr"
    elif openai_detected:
        detection_source = "openai_vision_detection"
    elif existing_detected:
        detection_source = "existing_asset_analysis"
    else:
        detection_source = "fallback_full_scene"

    manifest = build_layout_manifest(
        source_asset_id=source_asset.id if source_asset else None,
        source_width=source_w,
        source_height=source_h,
        detected_anchors=detected,
        task_manifest=task_manifest,
        detection_source=detection_source,
        ocr_status=ocr_report.get("status", "unknown"),
    )
    manifest.ocr = ocr_report
    manifest.detection = {
        "source": detection_source,
        "gemini": gemini_report,
        "openai_fallback_used": bool(openai_detected),
        "existing_asset_anchor_count": len(existing_detected),
    }
    report = {
        "source_asset_id": source_asset.id if source_asset else None,
        "source_size": {"w": source_w, "h": source_h},
        "detection_source": detection_source,
        "anchor_hints": hints,
        "existing_anchor_count": len(existing_detected),
        "gemini_anchor_count": len(gemini_detected),
        "openai_anchor_count": len(openai_detected),
        "ocr_candidate_count": len(ocr_candidates),
        "detected_anchor_count": len(detected),
        "manifest_anchor_count": len(manifest.anchors),
        "ocr": ocr_report,
        "gemini": gemini_report,
    }
    return manifest, report


async def _detect_layout_anchors_gemini(
    source_bytes: bytes,
    *,
    hints: list[str],
    settings,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not settings.vertex_gemini_enabled or not settings.gcp_project_id:
        return [], {
            "status": "disabled" if not settings.vertex_gemini_enabled else "missing_project_id",
            "model": settings.vertex_gemini_model,
        }

    try:
        from google import genai
        from google.genai import types as genai_types
    except Exception as exc:
        return [], {
            "status": "package_unavailable",
            "model": settings.vertex_gemini_model,
            "reason": str(exc),
        }

    def _call() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
        hint_text = ", ".join(hints or []) or "none"
        prompt = f"""
Detect the important ad layout anchors in this creative.

Priority hints: {hint_text}

Return strict JSON only:
{{
  "anchors": [
    {{
      "type": "logo" | "cta" | "headline_block" | "character_face" | "character_head" | "product",
      "label": "<short label>",
      "confidence": "high" | "medium" | "low",
      "required": true,
      "bbox": {{
        "x_pct": 0.0,
        "y_pct": 0.0,
        "w_pct": 0.0,
        "h_pct": 0.0
      }}
    }}
  ]
}}

Rules:
- Return at most one primary logo.
- Return at most one primary CTA button.
- Return at most one main headline block.
- For CTA, capture the full button, not only the text.
- For logo, capture the full visible brand mark/wordmark.
- For character/product, capture the full visible subject needed for resize-safe layouts.
- Omit uncertain anchors rather than guessing.
""".strip()
        mime = _detect_image_mime(source_bytes)
        response = client.models.generate_content(
            model=settings.vertex_gemini_model,
            contents=[
                genai_types.Part.from_bytes(data=source_bytes, mime_type=mime),
                prompt,
            ],
            config=genai_types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        text = getattr(response, "text", "") or ""
        payload = json.loads(text) if text else {}
        anchors = _normalize_candidate_list(payload.get("anchors") or [])
        return anchors, {
            "status": "ok",
            "model": settings.vertex_gemini_model,
            "raw_anchor_count": len(payload.get("anchors") or []),
        }

    try:
        anchors, report = await asyncio.to_thread(_call)
        return anchors, report
    except Exception as exc:
        return [], {
            "status": "error",
            "model": settings.vertex_gemini_model,
            "reason": str(exc),
        }


async def _detect_ocr_candidates_gcp(
    source_bytes: bytes,
    *,
    settings,
    source_width: int,
    source_height: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not settings.gcp_vision_enabled:
        return [], [], {"status": "disabled"}

    try:
        from google.cloud import vision
    except Exception as exc:
        return [], [], {"status": "package_unavailable", "reason": str(exc)}

    def _call() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=source_bytes)
        response = client.document_text_detection(image=image)
        if response.error.message:
            raise RuntimeError(response.error.message)

        blocks: list[dict[str, Any]] = []
        full = response.full_text_annotation
        for page in full.pages:
            for block in page.blocks:
                text = _block_text_from_vision_block(block)
                bbox = _vision_vertices_to_bbox(
                    block.bounding_box.vertices,
                    source_width=source_width,
                    source_height=source_height,
                )
                if not text or not bbox:
                    continue
                blocks.append(
                    {
                        "text": text,
                        "confidence": float(getattr(block, "confidence", 0.0) or 0.0),
                        "bbox": bbox,
                    }
                )

        candidates = _infer_ocr_anchor_candidates(blocks)
        return blocks, candidates, {
            "status": "ok",
            "block_count": len(blocks),
            "candidate_count": len(candidates),
        }

    try:
        blocks, candidates, report = await asyncio.to_thread(_call)
        return blocks, candidates, report
    except Exception as exc:
        return [], [], {"status": "error", "reason": str(exc)}


def _merge_anchor_candidates(
    *,
    source_width: int,
    source_height: int,
    existing: list[dict[str, Any]],
    gemini: list[dict[str, Any]],
    openai: list[dict[str, Any]],
    ocr: list[dict[str, Any]],
    ocr_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_pool: list[dict[str, Any]] = []
    for source_name, items in (
        ("existing", existing),
        ("gemini", gemini),
        ("openai", openai),
        ("ocr", ocr),
    ):
        for item in items:
            normalized = _normalize_candidate(item)
            if not normalized:
                continue
            normalized["source"] = source_name
            merged_pool.append(normalized)

    merged_pool = _coalesce_similar_candidates(merged_pool)
    merged_pool = _refine_textual_anchors_with_ocr(merged_pool, ocr_blocks)
    merged_pool = _apply_role_specific_bbox_adjustments(merged_pool)

    result: list[dict[str, Any]] = []
    singleton_roles = ["logo", "cta", "headline_block", "product"]
    for role in singleton_roles:
        picked = _pick_best_candidate_for_role(merged_pool, role, source_width, source_height)
        if picked:
            result.append(_candidate_to_output(picked))

    if not any(item["type"] == "logo" for item in result):
        promoted_logo = _promote_headline_like_logo(merged_pool)
        if promoted_logo:
            result = [item for item in result if item["type"] != "headline_block"]
            result.append(_candidate_to_output(promoted_logo, role_override="logo", required_override=True))

    for role in ("character_face", "character_head"):
        role_candidates = [item for item in merged_pool if item["type"] == role]
        role_candidates.sort(key=lambda item: _candidate_score(item, role, source_width, source_height), reverse=True)
        for item in role_candidates:
            if any(
                existing_item["type"] == role and _bbox_iou(existing_item["bbox"], item["bbox"]) > 0.5
                for existing_item in result
            ):
                continue
            result.append(_candidate_to_output(item))
            break
    return _dedupe_semantic_overlaps(result)


def _normalize_candidate(item: dict[str, Any]) -> dict[str, Any] | None:
    bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else item
    role = normalize_anchor_role(str(item.get("type") or item.get("role") or item.get("label") or ""))
    try:
        x_pct = max(0.0, min(1.0, float(bbox.get("x_pct", 0.0))))
        y_pct = max(0.0, min(1.0, float(bbox.get("y_pct", 0.0))))
        w_pct = max(0.0, min(1.0, float(bbox.get("w_pct", 0.0))))
        h_pct = max(0.0, min(1.0, float(bbox.get("h_pct", 0.0))))
    except (TypeError, ValueError):
        return None
    if w_pct <= 0 or h_pct <= 0:
        return None
    return {
        "type": role,
        "label": str(item.get("label") or role),
        "confidence": str(item.get("confidence") or "medium"),
        "required": bool(item.get("required", role in {"logo", "cta"})),
        "bbox": {
            "x_pct": x_pct,
            "y_pct": y_pct,
            "w_pct": w_pct,
            "h_pct": h_pct,
        },
    }


def _normalize_candidate_list(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = _normalize_candidate(item)
        if candidate:
            normalized.append(candidate)
    return normalized


def _refine_textual_anchors_with_ocr(
    candidates: list[dict[str, Any]],
    ocr_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not ocr_blocks:
        return candidates
    refined: list[dict[str, Any]] = []
    for item in candidates:
        if item["type"] not in {"cta", "headline_block"}:
            refined.append(item)
            continue
        best_block = max(
            ocr_blocks,
            key=lambda block: _text_block_match_score(item, block),
            default=None,
        )
        if best_block and _text_block_match_score(item, best_block) >= 0.35:
            replacement_bbox = best_block["bbox"]
            if item["type"] == "cta":
                replacement_bbox = _union_bbox(item["bbox"], _expand_bbox(best_block["bbox"], role="cta"))
            refined.append(
                {
                    **item,
                    "bbox": replacement_bbox,
                    "confidence": "high" if item["confidence"] != "low" else "medium",
                    "label": best_block["text"][:80],
                }
            )
        else:
            refined.append(item)
    return refined


def _pick_best_candidate_for_role(
    candidates: list[dict[str, Any]],
    role: str,
    source_width: int,
    source_height: int,
) -> dict[str, Any] | None:
    role_candidates = [item for item in candidates if item["type"] == role]
    if not role_candidates:
        return None
    role_candidates.sort(
        key=lambda item: _candidate_score(item, role, source_width, source_height),
        reverse=True,
    )
    return role_candidates[0]


def _candidate_score(
    candidate: dict[str, Any],
    role: str,
    source_width: int,
    source_height: int,
) -> float:
    bbox = candidate["bbox"]
    area = max(0.0001, bbox["w_pct"] * bbox["h_pct"])
    aspect = bbox["w_pct"] / max(0.0001, bbox["h_pct"])
    confidence = {"high": 1.0, "medium": 0.6, "low": 0.2}.get(candidate["confidence"], 0.2)
    source_bonus = {
        "gemini": 1.2,
        "ocr": 1.05 if role in {"cta", "headline_block"} else 0.4,
        "existing": 0.6,
        "openai": 0.75,
    }.get(candidate.get("source"), 0.0)
    score = confidence + source_bonus

    if role == "logo":
        score += 1.4 if 1.2 <= aspect <= 8.0 else 0.1
        score += 0.7 if bbox["y_pct"] <= 0.35 else 0.0
        score += 0.5 if bbox["x_pct"] <= 0.35 or (bbox["x_pct"] + bbox["w_pct"]) >= 0.65 else 0.0
    elif role == "cta":
        score += 1.5 if 1.5 <= aspect <= 6.5 else 0.1
        score += 0.8 if (bbox["x_pct"] + bbox["w_pct"]) >= 0.55 or bbox["y_pct"] >= 0.55 else 0.0
        score += 0.4 if area <= 0.12 else -0.2
    elif role == "headline_block":
        score += 1.0 if aspect >= 1.2 else 0.0
        score += 0.6 if bbox["y_pct"] <= 0.55 else 0.0
    elif role == "product":
        score += 0.7 if area <= 0.35 else 0.0
    elif role in {"character_face", "character_head"}:
        score += 0.8 if area <= 0.2 else 0.0

    score += min(area * 3.0, 0.8)
    return score


def _coalesce_similar_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        existing = next(
            (
                item for item in merged
                if item["type"] == candidate["type"] and _bbox_iou(item["bbox"], candidate["bbox"]) >= 0.45
            ),
            None,
        )
        if not existing:
            merged.append(candidate)
            continue
        existing["bbox"] = _union_bbox(existing["bbox"], candidate["bbox"])
        existing["required"] = bool(existing["required"] or candidate["required"])
        if _confidence_rank(candidate["confidence"]) >= _confidence_rank(existing["confidence"]):
            existing["confidence"] = candidate["confidence"]
            if len(candidate["label"]) > len(existing["label"]):
                existing["label"] = candidate["label"]
        source_a = _source_rank(existing.get("source"))
        source_b = _source_rank(candidate.get("source"))
        if source_b > source_a:
            existing["source"] = candidate.get("source")
    return merged


def _apply_role_specific_bbox_adjustments(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    for candidate in candidates:
        adjusted.append(
            {
                **candidate,
                "bbox": _expand_bbox(
                    candidate["bbox"],
                    role=candidate["type"],
                    label=candidate.get("label", ""),
                    source=candidate.get("source", ""),
                ),
            }
        )
    return adjusted


def _dedupe_semantic_overlaps(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    logo = next((item for item in candidates if item["type"] == "logo"), None)
    headline = next((item for item in candidates if item["type"] == "headline_block"), None)
    if not logo or not headline:
        return candidates

    logo_text = str(logo.get("label") or "").lower().strip()
    headline_text = str(headline.get("label") or "").lower().strip()
    if _bbox_iou(logo["bbox"], headline["bbox"]) >= 0.5 or (logo_text and headline_text and logo_text == headline_text):
        return [item for item in candidates if item is not headline]
    return candidates


def _expand_bbox(
    bbox: dict[str, float],
    *,
    role: str,
    label: str = "",
    source: str = "",
) -> dict[str, float]:
    x = bbox["x_pct"]
    y = bbox["y_pct"]
    w = bbox["w_pct"]
    h = bbox["h_pct"]

    if role == "cta":
        pad_x = max(w * (0.55 if source == "ocr" else 0.24), 0.025)
        pad_y = max(h * (1.2 if source == "ocr" else 0.4), 0.02)
        return _bbox_from_edges(x - pad_x, y - pad_y, x + w + pad_x, y + h + pad_y)
    if role == "logo":
        pad_x = max(w * 0.18, 0.012)
        pad_y = max(h * 0.22, 0.012)
        return _bbox_from_edges(x - pad_x, y - pad_y, x + w + pad_x, y + h + pad_y)
    if role == "headline_block":
        pad_x = max(w * 0.08, 0.008)
        pad_y = max(h * 0.12, 0.008)
        return _bbox_from_edges(x - pad_x, y - pad_y, x + w + pad_x, y + h + pad_y)
    return dict(bbox)


def _text_block_match_score(candidate: dict[str, Any], block: dict[str, Any]) -> float:
    overlap = _bbox_iou(candidate["bbox"], block["bbox"])
    candidate_label = " ".join(str(candidate.get("label") or "").lower().split())
    block_text = " ".join(str(block.get("text") or "").lower().split())
    text_bonus = 0.0
    if candidate_label and block_text:
        if candidate_label == block_text:
            text_bonus = 0.5
        elif candidate_label in block_text or block_text in candidate_label:
            text_bonus = 0.25
    return overlap + text_bonus


def _union_bbox(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    x1 = min(a["x_pct"], b["x_pct"])
    y1 = min(a["y_pct"], b["y_pct"])
    x2 = max(a["x_pct"] + a["w_pct"], b["x_pct"] + b["w_pct"])
    y2 = max(a["y_pct"] + a["h_pct"], b["y_pct"] + b["h_pct"])
    return _bbox_from_edges(x1, y1, x2, y2)


def _bbox_from_edges(x1: float, y1: float, x2: float, y2: float) -> dict[str, float]:
    left = max(0.0, min(1.0, x1))
    top = max(0.0, min(1.0, y1))
    right = max(left + 0.0001, min(1.0, x2))
    bottom = max(top + 0.0001, min(1.0, y2))
    return {
        "x_pct": left,
        "y_pct": top,
        "w_pct": max(0.0, min(1.0 - left, right - left)),
        "h_pct": max(0.0, min(1.0 - top, bottom - top)),
    }


def _confidence_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 0)


def _source_rank(value: str | None) -> int:
    return {
        "gemini": 4,
        "ocr": 3,
        "openai": 2,
        "existing": 1,
    }.get(value or "", 0)


def _promote_headline_like_logo(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    headline_candidates = [item for item in candidates if item["type"] == "headline_block"]
    if not headline_candidates:
        return None

    def _score(item: dict[str, Any]) -> float:
        bbox = item["bbox"]
        area = bbox["w_pct"] * bbox["h_pct"]
        score = _confidence_rank(item["confidence"]) + _source_rank(item.get("source"))
        if bbox["y_pct"] <= 0.35:
            score += 2.0
        if bbox["x_pct"] <= 0.22 or (bbox["x_pct"] + bbox["w_pct"]) >= 0.72:
            score += 1.4
        if 0.03 <= area <= 0.22:
            score += 1.2
        if len(str(item.get("label") or "")) <= 48:
            score += 0.6
        return score

    promoted = max(headline_candidates, key=_score, default=None)
    if not promoted:
        return None
    bbox = promoted["bbox"]
    if bbox["y_pct"] > 0.45:
        return None
    return {
        **promoted,
        "required": True,
        "bbox": _tighten_promoted_logo_bbox(bbox),
    }


def _tighten_promoted_logo_bbox(bbox: dict[str, float]) -> dict[str, float]:
    x1 = bbox["x_pct"]
    y1 = bbox["y_pct"]
    x2 = bbox["x_pct"] + bbox["w_pct"]
    y2 = bbox["y_pct"] + bbox["h_pct"]
    width = max(0.0001, x2 - x1)
    height = max(0.0001, y2 - y1)

    trimmed_top = y1 - min(0.012, height * 0.04)
    trimmed_bottom = y1 + min(height * 0.84, 0.34)
    trimmed_left = x1 - min(0.01, width * 0.04)
    trimmed_right = x2 + min(0.014, width * 0.05)
    return _bbox_from_edges(trimmed_left, trimmed_top, trimmed_right, trimmed_bottom)


def _candidate_to_output(
    candidate: dict[str, Any],
    *,
    role_override: str | None = None,
    required_override: bool | None = None,
) -> dict[str, Any]:
    return {
        "type": role_override or candidate["type"],
        "label": candidate["label"],
        "confidence": candidate["confidence"],
        "required": candidate["required"] if required_override is None else required_override,
        "bbox": dict(candidate["bbox"]),
    }


def _bbox_iou(a: dict[str, float], b: dict[str, float]) -> float:
    ax1, ay1 = a["x_pct"], a["y_pct"]
    ax2, ay2 = a["x_pct"] + a["w_pct"], a["y_pct"] + a["h_pct"]
    bx1, by1 = b["x_pct"], b["y_pct"]
    bx2, by2 = b["x_pct"] + b["w_pct"], b["y_pct"] + b["h_pct"]
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter_area = inter_w * inter_h
    a_area = max(0.0001, a["w_pct"] * a["h_pct"])
    b_area = max(0.0001, b["w_pct"] * b["h_pct"])
    return inter_area / max(0.0001, a_area + b_area - inter_area)


def _block_text_from_vision_block(block: Any) -> str:
    pieces: list[str] = []
    for paragraph in getattr(block, "paragraphs", []):
        words: list[str] = []
        for word in getattr(paragraph, "words", []):
            text = "".join(symbol.text for symbol in getattr(word, "symbols", []))
            if text:
                words.append(text)
        if words:
            pieces.append(" ".join(words))
    return " ".join(pieces).strip()


def _vision_vertices_to_bbox(
    vertices: Any,
    *,
    source_width: int,
    source_height: int,
) -> dict[str, float] | None:
    coords = [(getattr(v, "x", 0) or 0, getattr(v, "y", 0) or 0) for v in vertices or []]
    if not coords:
        return None
    xs = [point[0] for point in coords]
    ys = [point[1] for point in coords]
    if source_width <= 0 or source_height <= 0:
        return None
    min_x = min(xs)
    min_y = min(ys)
    width = max(xs) - min_x
    height = max(ys) - min_y
    return {
        "x_pct": max(0.0, min(1.0, min_x / source_width)),
        "y_pct": max(0.0, min(1.0, min_y / source_height)),
        "w_pct": max(0.0, min(1.0, width / source_width)),
        "h_pct": max(0.0, min(1.0, height / source_height)),
    }


def _infer_ocr_anchor_candidates(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    cta_terms = (
        "play now",
        "install now",
        "shop now",
        "learn more",
        "download",
        "sign up",
        "log in",
        "login",
        "book now",
        "join now",
    )
    for block in blocks:
        text = " ".join(str(block.get("text") or "").lower().split())
        if not text:
            continue
        bbox = block["bbox"]
        words = text.split()
        if any(term in text for term in cta_terms):
            candidates.append(
                {
                    "type": "cta",
                    "label": block["text"][:80],
                    "confidence": "high",
                    "required": True,
                    "bbox": bbox,
                }
            )
            continue
        if len(words) <= 8 and bbox["w_pct"] >= 0.16 and bbox["h_pct"] >= 0.04:
            candidates.append(
                {
                    "type": "headline_block",
                    "label": block["text"][:120],
                    "confidence": "medium",
                    "required": False,
                    "bbox": bbox,
                }
            )
    return candidates


def _detect_image_mime(source_bytes: bytes) -> str:
    try:
        with Image.open(io.BytesIO(source_bytes)) as img:
            fmt = (img.format or "").upper()
    except Exception:
        return "image/png"
    if fmt == "JPEG":
        return "image/jpeg"
    if fmt == "WEBP":
        return "image/webp"
    if fmt == "GIF":
        return "image/gif"
    return "image/png"
