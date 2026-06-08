from __future__ import annotations

import io
from typing import Any

from PIL import Image

from app.incept.guardrails import validate_output_asset
from app.incept.layout_manifest import LayoutManifest


async def validate_renderer_output(
    *,
    output_bytes: bytes,
    target_size: str,
    layout_manifest: LayoutManifest,
    guardrail_manifest: dict[str, Any],
    detect_fn,
    api_key: str | None,
    overlay_applied: bool = False,
) -> dict[str, Any]:
    source_anchors = layout_manifest.to_detection_payload()
    if not source_anchors:
        with Image.open(io.BytesIO(output_bytes)) as img:
            width, height = img.size
        target_w, target_h = (int(part) for part in target_size.lower().split("x", 1))
        source_w = max(1, int(layout_manifest.source_size.get("w", 1)))
        source_h = max(1, int(layout_manifest.source_size.get("h", 1)))
        source_ratio = source_w / source_h
        target_ratio = target_w / target_h
        ratio_shift = max(source_ratio / target_ratio, target_ratio / source_ratio)
        if ratio_shift >= 1.12:
            return {
                "status": "hard_fail",
                "target_size": target_size,
                "measured_size": {"width": width, "height": height},
                "required_hard_types": [],
                "required_soft_types": [],
                "present_anchor_types": [],
                "source_anchor_types": [],
                "missing_hard_types": [],
                "missing_soft_types": [],
                "unexpected_removed_types": [],
                "reasons": ["no_detected_anchors_for_aspect_shift"],
                "render_mode": "multi_size_renderer_v2",
                "analysis_version": layout_manifest.analysis_version,
                "validation_mode": "anchors_required_for_relayout",
            }
        return {
            "status": "pass" if (width == target_w and height == target_h) else "hard_fail",
            "target_size": target_size,
            "measured_size": {"width": width, "height": height},
            "required_hard_types": [],
            "required_soft_types": [],
            "present_anchor_types": [],
            "source_anchor_types": [],
            "missing_hard_types": [],
            "missing_soft_types": [],
            "unexpected_removed_types": [],
            "reasons": [] if (width == target_w and height == target_h) else ["size_mismatch"],
            "render_mode": "multi_size_renderer_v2",
            "analysis_version": layout_manifest.analysis_version,
            "validation_mode": "deterministic_size_only",
        }
    validation = await validate_output_asset(
        output_bytes=output_bytes,
        target_size=target_size,
        manifest=guardrail_manifest,
        source_anchors=source_anchors,
        detect_fn=detect_fn,
        api_key=api_key,
        overlay_applied=overlay_applied,
    )
    validation["render_mode"] = "multi_size_renderer_v2"
    validation["analysis_version"] = layout_manifest.analysis_version
    return validation
