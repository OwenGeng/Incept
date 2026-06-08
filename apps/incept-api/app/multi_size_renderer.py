from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image

from app.anchor_types import classify_size_family
from app.composite import composite_logo
from app.layout_manifest import LayoutAnchor, LayoutManifest
from app.renderer_validation import validate_renderer_output


@dataclass(frozen=True)
class RenderedVariant:
    target_size: str
    image_bytes: bytes
    analysis: dict[str, Any]


def build_layout_plan(target_size: str, layout_manifest: LayoutManifest) -> dict[str, Any]:
    width_text, height_text = target_size.lower().split("x", 1)
    target_w = int(width_text)
    target_h = int(height_text)
    family = classify_size_family(target_w, target_h)
    role_summary = [anchor.role for anchor in layout_manifest.anchors]
    return {
        "target_size": target_size,
        "family": family,
        "canvas": {"w": target_w, "h": target_h},
        "anchor_roles": role_summary,
        "background_mode": "edge_extend_if_needed",
        "analysis_version": layout_manifest.analysis_version,
    }


async def render_multi_size_variants(
    *,
    source_bytes: bytes,
    target_sizes: list[str],
    layout_manifest: LayoutManifest,
    guardrail_manifest: dict[str, Any],
    logo_overlay_bytes: bytes | None,
    detect_fn,
    api_key: str | None,
) -> list[RenderedVariant]:
    outputs: list[RenderedVariant] = []
    source_anchors = layout_manifest.to_detection_payload()
    source_has_logo = any(anchor.get("type") == "logo" for anchor in source_anchors)

    for size in target_sizes:
        target_w, target_h = _parse_size(size)
        if not target_w or not target_h:
            continue
        plan = build_layout_plan(size, layout_manifest)
        rendered, adaptation_report = _render_exact_variant(
            source_bytes=source_bytes,
            target_w=target_w,
            target_h=target_h,
            layout_manifest=layout_manifest,
        )
        overlay_applied = False
        if logo_overlay_bytes and not source_has_logo:
            rendered = composite_logo(
                rendered,
                logo_overlay_bytes,
                position=_logo_position_for_size(target_w, target_h),
                size_ratio=_logo_ratio_for_size(target_w, target_h),
            )
            overlay_applied = True

        validation = await validate_renderer_output(
            output_bytes=rendered,
            target_size=size,
            layout_manifest=layout_manifest,
            guardrail_manifest=guardrail_manifest,
            detect_fn=detect_fn,
            api_key=api_key,
            overlay_applied=overlay_applied,
        )

        outputs.append(
            RenderedVariant(
                target_size=size,
                image_bytes=rendered,
                analysis={
                    "render_mode": "multi_size_renderer_v2",
                    "layout_plan": plan,
                    "layout_manifest": layout_manifest.to_dict(),
                    "adaptation": {
                        **adaptation_report,
                        "logo_overlay_applied": overlay_applied,
                    },
                    "validation": validation,
                },
            )
        )

    return outputs


def _render_exact_variant(
    *,
    source_bytes: bytes,
    target_w: int,
    target_h: int,
    layout_manifest: LayoutManifest,
) -> tuple[bytes, dict[str, Any]]:
    with Image.open(io.BytesIO(source_bytes)) as source_img:
        img = source_img.convert("RGBA")
    iw, ih = img.size
    target_ratio = target_w / max(1, target_h)
    source_ratio = iw / max(1, ih)
    anchors = _usable_anchors(layout_manifest)
    family = classify_size_family(target_w, target_h)

    if _use_forced_banner_layout(target_w, target_h, family):
        banner = _render_banner_variant(
            img=img,
            target_w=target_w,
            target_h=target_h,
            anchors=anchors,
        )
        if banner is not None:
            return _to_png(banner), {
                "mode": "banner_layout",
                "source_size": {"width": iw, "height": ih},
                "target_size": {"width": target_w, "height": target_h},
                "anchor_count": len(anchors),
            }

    if abs(source_ratio - target_ratio) < 0.02:
        resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        return _to_png(resized), {
            "mode": "scale",
            "source_size": {"width": iw, "height": ih},
            "target_size": {"width": target_w, "height": target_h},
            "anchor_count": len(anchors),
        }

    crop_box = _compute_preserve_crop_box(iw, ih, target_ratio, anchors)
    if crop_box is not None:
        cropped = img.crop(crop_box).resize((target_w, target_h), Image.Resampling.LANCZOS)
        return _to_png(cropped), {
            "mode": "preserve_crop",
            "source_size": {"width": iw, "height": ih},
            "target_size": {"width": target_w, "height": target_h},
            "crop_box": _serialize_box(crop_box),
            "anchor_count": len(anchors),
        }

    contained = _render_edge_extend_contain(
        img=img,
        target_w=target_w,
        target_h=target_h,
        focus_box=_anchor_union(anchors),
    )
    return _to_png(contained), {
        "mode": "edge_extend_contain",
        "source_size": {"width": iw, "height": ih},
        "target_size": {"width": target_w, "height": target_h},
        "anchor_count": len(anchors),
    }


def _usable_anchors(layout_manifest: LayoutManifest) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    source_w = max(1, int(layout_manifest.source_size.get("w", 1)))
    source_h = max(1, int(layout_manifest.source_size.get("h", 1)))
    for anchor in sorted(layout_manifest.anchors, key=lambda item: (-item.priority, item.id)):
        if anchor.role == "hero_subject":
            continue
        box = _anchor_to_pixels(anchor, source_w, source_h)
        if box is None:
            continue
        anchors.append(
            {
                "type": anchor.role,
                "required": anchor.must_preserve,
                "priority": anchor.priority,
                **box,
            }
        )
    return anchors


def _anchor_to_pixels(anchor: LayoutAnchor, source_w: int, source_h: int) -> dict[str, int] | None:
    x1 = int(round(anchor.bbox.x_pct * source_w))
    y1 = int(round(anchor.bbox.y_pct * source_h))
    x2 = int(round((anchor.bbox.x_pct + anchor.bbox.w_pct) * source_w))
    y2 = int(round((anchor.bbox.y_pct + anchor.bbox.h_pct) * source_h))
    x1 = max(0, min(source_w - 1, x1))
    y1 = max(0, min(source_h - 1, y1))
    x2 = max(x1 + 1, min(source_w, x2))
    y2 = max(y1 + 1, min(source_h, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _compute_preserve_crop_box(
    image_w: int,
    image_h: int,
    target_ratio: float,
    anchors: list[dict[str, Any]],
) -> tuple[int, int, int, int] | None:
    if not anchors:
        return None

    required = [anchor for anchor in anchors if anchor["required"]]
    focus = required or anchors
    union = _anchor_union(focus)
    if not union:
        return None

    source_ratio = image_w / max(1, image_h)
    if source_ratio > target_ratio:
        crop_w = max(1, int(round(image_h * target_ratio)))
        if crop_w > image_w:
            return None
        min_left = max(0, union["x2"] - crop_w)
        max_left = min(image_w - crop_w, union["x1"])
        if min_left > max_left:
            return None
        desired_left = int(round(((union["x1"] + union["x2"]) / 2) - (crop_w / 2)))
        left = _clamp(desired_left, min_left, max_left)
        crop_box = (left, 0, left + crop_w, image_h)
    else:
        crop_h = max(1, int(round(image_w / target_ratio)))
        if crop_h > image_h:
            return None
        min_top = max(0, union["y2"] - crop_h)
        max_top = min(image_h - crop_h, union["y1"])
        if min_top > max_top:
            return None
        desired_top = int(round(((union["y1"] + union["y2"]) / 2) - (crop_h / 2)))
        top = _clamp(desired_top, min_top, max_top)
        crop_box = (0, top, image_w, top + crop_h)

    return crop_box if _crop_preserves_required_anchors(crop_box, required or focus) else None


def _crop_preserves_required_anchors(
    crop_box: tuple[int, int, int, int],
    anchors: list[dict[str, Any]],
) -> bool:
    for anchor in anchors:
        area = max(1, (anchor["x2"] - anchor["x1"]) * (anchor["y2"] - anchor["y1"]))
        inter_w = max(0, min(crop_box[2], anchor["x2"]) - max(crop_box[0], anchor["x1"]))
        inter_h = max(0, min(crop_box[3], anchor["y2"]) - max(crop_box[1], anchor["y1"]))
        coverage = (inter_w * inter_h) / area
        threshold = 0.99 if anchor["type"] in {"logo", "cta"} else 0.94
        if coverage < threshold:
            return False
    return True


def _render_edge_extend_contain(
    *,
    img: Image.Image,
    target_w: int,
    target_h: int,
    focus_box: dict[str, int] | None,
) -> Image.Image:
    scale = min(target_w / max(1, img.width), target_h / max(1, img.height))
    fitted_w = max(1, int(round(img.width * scale)))
    fitted_h = max(1, int(round(img.height * scale)))
    fitted = img.resize((fitted_w, fitted_h), Image.Resampling.LANCZOS)

    paste_x, paste_y = _contained_offsets(
        focus_box=focus_box,
        source_w=img.width,
        source_h=img.height,
        fitted_w=fitted_w,
        fitted_h=fitted_h,
        target_w=target_w,
        target_h=target_h,
    )

    canvas = Image.new("RGBA", (target_w, target_h))
    _fill_canvas_with_edge_extensions(canvas, fitted, paste_x, paste_y)
    canvas.alpha_composite(fitted, (paste_x, paste_y))
    return canvas


def _render_banner_variant(
    *,
    img: Image.Image,
    target_w: int,
    target_h: int,
    anchors: list[dict[str, Any]],
) -> Image.Image | None:
    logo = _select_anchor(anchors, ["logo"])
    cta = _select_anchor(anchors, ["cta"])
    headline = _select_anchor(anchors, ["headline_block"])

    # If we have no structural anchors at all, let the generic renderer decide.
    if not any([logo, cta, headline]):
        return None

    scene_focus = _scene_focus_box(anchors)
    background_source = _extract_banner_background_source(
        img,
        scene_focus,
        logo=logo,
        cta=cta,
        headline=headline,
    )
    canvas = _render_cover_background(
        img=background_source,
        target_w=target_w,
        target_h=target_h,
        focus_box=None,
    )

    margin_x = max(4, int(target_w * 0.025))
    margin_y = max(2, int(target_h * 0.1))
    gap = max(3, int(target_w * 0.012))

    logo_slot_w = int(target_w * (0.18 if target_h <= 60 else 0.17))
    logo_slot_h = int(target_h * 0.7)
    cta_slot_w = int(target_w * (0.22 if target_h <= 60 else 0.2))
    cta_slot_h = int(target_h * 0.68)

    left_cursor = margin_x
    right_cursor = target_w - margin_x

    if logo:
        logo_img = _crop_anchor_image(img, logo, pad_x=0.08, pad_y=0.12, role="logo")
        if logo_img is not None:
            fitted_logo = _fit_image(logo_img, logo_slot_w, logo_slot_h)
            logo_x = left_cursor
            logo_y = max(0, (target_h - fitted_logo.height) // 2)
            canvas.alpha_composite(fitted_logo, (logo_x, logo_y))
            left_cursor = logo_x + fitted_logo.width + gap

    if cta:
        cta_img = _crop_anchor_image(img, cta, pad_x=0.08, pad_y=0.1, role="cta")
        if cta_img is not None:
            fitted_cta = _fit_image(cta_img, cta_slot_w, cta_slot_h)
            cta_x = target_w - margin_x - fitted_cta.width
            cta_y = max(0, (target_h - fitted_cta.height) // 2)
            canvas.alpha_composite(fitted_cta, (cta_x, cta_y))
            right_cursor = cta_x - gap

    if headline and right_cursor - left_cursor > int(target_w * 0.14):
        headline_img = _crop_anchor_image(img, headline, pad_x=0.08, pad_y=0.12, role="headline_block")
        if headline_img is not None:
            max_headline_w = max(24, int((right_cursor - left_cursor) * 0.92))
            max_headline_h = int(target_h * 0.34)
            fitted_headline = _fit_image(headline_img, max_headline_w, max_headline_h)
            hx = left_cursor + max(0, ((right_cursor - left_cursor) - fitted_headline.width) // 2)
            hy = margin_y
            canvas.alpha_composite(fitted_headline, (hx, hy))

    return canvas


def _extract_banner_background_source(
    img: Image.Image,
    scene_focus: dict[str, int] | None,
    *,
    logo: dict[str, Any] | None,
    cta: dict[str, Any] | None,
    headline: dict[str, Any] | None,
) -> Image.Image:
    scrub_anchors = [anchor for anchor in (logo, cta, headline) if anchor]
    if not scene_focus:
        fallback = _fallback_banner_scene_box(
            img.width,
            img.height,
            exclusions=scrub_anchors,
        )
        if not fallback:
            return img
        crop = img.crop((fallback["x1"], fallback["y1"], fallback["x2"], fallback["y2"])).convert("RGBA")
        return _scrub_background_exclusions(crop, fallback, scrub_anchors)
    width = max(1, scene_focus["x2"] - scene_focus["x1"])
    height = max(1, scene_focus["y2"] - scene_focus["y1"])
    pad_x = int(width * 0.18)
    pad_y = int(height * 0.16)
    x1 = _clamp(scene_focus["x1"] - pad_x, 0, img.width - 1)
    y1 = _clamp(scene_focus["y1"] - pad_y, 0, img.height - 1)
    x2 = _clamp(scene_focus["x2"] + pad_x, x1 + 1, img.width)
    y2 = _clamp(scene_focus["y2"] + pad_y, y1 + 1, img.height)
    crop_box = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    crop = img.crop((x1, y1, x2, y2)).convert("RGBA")
    return _scrub_background_exclusions(crop, crop_box, scrub_anchors)


def _fallback_banner_scene_box(
    image_w: int,
    image_h: int,
    *,
    exclusions: list[dict[str, Any]],
) -> dict[str, int] | None:
    left = int(image_w * 0.08)
    right = int(image_w * 0.92)
    for anchor in exclusions:
        center_x = (anchor["x1"] + anchor["x2"]) / 2
        pad = int((anchor["x2"] - anchor["x1"]) * 0.28)
        if center_x <= image_w * 0.45:
            left = max(left, min(image_w - 2, anchor["x2"] + pad))
        elif center_x >= image_w * 0.55:
            right = min(right, max(1, anchor["x1"] - pad))
    if right <= left + max(12, int(image_w * 0.1)):
        center_w = max(24, int(image_w * 0.34))
        center_left = max(0, (image_w - center_w) // 2)
        center_right = min(image_w, center_left + center_w)
        if center_right <= center_left + 12:
            return None
        left, right = center_left, center_right
    top = int(image_h * 0.05)
    bottom = int(image_h * 0.95)
    return {"x1": left, "y1": top, "x2": right, "y2": bottom}


def _scrub_background_exclusions(
    crop: Image.Image,
    crop_box: dict[str, int],
    anchors: list[dict[str, Any]],
) -> Image.Image:
    cleaned = crop.copy()
    for anchor in anchors:
        padded_anchor = _pad_pixel_anchor_box(anchor, image_w=crop_box["x2"], image_h=crop_box["y2"])
        overlap = _intersect_boxes(crop_box, padded_anchor)
        if not overlap:
            continue
        local_x1 = overlap["x1"] - crop_box["x1"]
        local_y1 = overlap["y1"] - crop_box["y1"]
        local_x2 = overlap["x2"] - crop_box["x1"]
        local_y2 = overlap["y2"] - crop_box["y1"]
        if local_x2 <= local_x1 or local_y2 <= local_y1:
            continue

        fill = _neighbor_fill_patch(cleaned, local_x1, local_y1, local_x2, local_y2)
        if fill is None:
            continue
        cleaned.alpha_composite(fill, (local_x1, local_y1))
    return cleaned


def _pad_pixel_anchor_box(
    anchor: dict[str, Any],
    *,
    image_w: int,
    image_h: int,
) -> dict[str, int]:
    width = max(1, anchor["x2"] - anchor["x1"])
    height = max(1, anchor["y2"] - anchor["y1"])
    pad_x = max(4, int(width * 0.18))
    pad_y = max(3, int(height * 0.2))
    return {
        "x1": _clamp(anchor["x1"] - pad_x, 0, max(0, image_w - 1)),
        "y1": _clamp(anchor["y1"] - pad_y, 0, max(0, image_h - 1)),
        "x2": _clamp(anchor["x2"] + pad_x, 1, image_w),
        "y2": _clamp(anchor["y2"] + pad_y, 1, image_h),
    }


def _neighbor_fill_patch(
    img: Image.Image,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> Image.Image | None:
    patch_w = max(1, x2 - x1)
    patch_h = max(1, y2 - y1)
    source = None
    sample_w = max(1, min(6, patch_w // 6 or 1))
    if x1 - sample_w >= 0:
        source = img.crop((x1 - sample_w, y1, x1, y2))
    elif x2 + sample_w <= img.width:
        source = img.crop((x2, y1, x2 + sample_w, y2))
    elif y1 - sample_w >= 0:
        source = img.crop((x1, y1 - sample_w, x2, y1))
    elif y2 + sample_w <= img.height:
        source = img.crop((x1, y2, x2, y2 + sample_w))
    if source is None or source.width <= 0 or source.height <= 0:
        return None
    return source.resize((patch_w, patch_h), Image.Resampling.BILINEAR).convert("RGBA")


def _intersect_boxes(a: dict[str, int], b: dict[str, Any]) -> dict[str, int] | None:
    x1 = max(a["x1"], b["x1"])
    y1 = max(a["y1"], b["y1"])
    x2 = min(a["x2"], b["x2"])
    y2 = min(a["y2"], b["y2"])
    if x2 <= x1 or y2 <= y1:
        return None
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _render_cover_background(
    *,
    img: Image.Image,
    target_w: int,
    target_h: int,
    focus_box: dict[str, int] | None,
) -> Image.Image:
    scale = max(target_w / max(1, img.width), target_h / max(1, img.height))
    scaled_w = max(target_w, int(round(img.width * scale)))
    scaled_h = max(target_h, int(round(img.height * scale)))
    scaled = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    if focus_box:
        focus_cx = ((focus_box["x1"] + focus_box["x2"]) / 2) * scale
        focus_cy = ((focus_box["y1"] + focus_box["y2"]) / 2) * scale
        left = _clamp(int(round(focus_cx - (target_w / 2))), 0, max(0, scaled_w - target_w))
        top = _clamp(int(round(focus_cy - (target_h / 2))), 0, max(0, scaled_h - target_h))
    else:
        left = max(0, (scaled_w - target_w) // 2)
        top = max(0, (scaled_h - target_h) // 2)

    return scaled.crop((left, top, left + target_w, top + target_h)).convert("RGBA")


def _scene_focus_box(anchors: list[dict[str, Any]]) -> dict[str, int] | None:
    scene_anchors = [
        anchor for anchor in anchors if anchor["type"] not in {"logo", "cta", "headline_block"}
    ]
    return _anchor_union(scene_anchors) or None


def _use_forced_banner_layout(target_w: int, target_h: int, family: str) -> bool:
    forced_sizes = {
        (320, 50),
        (728, 90),
        (640, 100),
        (1200, 222),
    }
    return family == "banner" or (target_w, target_h) in forced_sizes


def _select_anchor(anchors: list[dict[str, Any]], types: list[str]) -> dict[str, Any] | None:
    candidates = [anchor for anchor in anchors if anchor["type"] in types]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item["priority"], -_anchor_area(item)))[0]


def _crop_anchor_image(
    img: Image.Image,
    anchor: dict[str, Any],
    *,
    pad_x: float,
    pad_y: float,
    role: str | None = None,
) -> Image.Image | None:
    width = max(1, anchor["x2"] - anchor["x1"])
    height = max(1, anchor["y2"] - anchor["y1"])
    anchor_x1 = anchor["x1"]
    anchor_y1 = anchor["y1"]
    anchor_x2 = anchor["x2"]
    anchor_y2 = anchor["y2"]

    if role == "cta" and (height > width * 0.42 or height > img.height * 0.18):
        anchor_x1 = anchor["x1"] + int(round(width * 0.04))
        anchor_x2 = anchor["x2"] - int(round(width * 0.02))
        anchor_y1 = anchor["y1"] + int(round(height * 0.42))
        anchor_y2 = anchor["y2"] + int(round(height * 0.04))
        width = max(1, anchor_x2 - anchor_x1)
        height = max(1, anchor_y2 - anchor_y1)

    x1 = _clamp(int(round(anchor_x1 - width * pad_x)), 0, img.width - 1)
    y1 = _clamp(int(round(anchor_y1 - height * pad_y)), 0, img.height - 1)
    x2 = _clamp(int(round(anchor_x2 + width * pad_x)), x1 + 1, img.width)
    y2 = _clamp(int(round(anchor_y2 + height * pad_y)), y1 + 1, img.height)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = img.crop((x1, y1, x2, y2)).convert("RGBA")
    refined = _refine_foreground_roi(crop, role=role or "")
    return refined or crop


def _fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    scale = min(max_w / max(1, img.width), max_h / max(1, img.height), 1.0)
    new_w = max(1, int(round(img.width * scale)))
    new_h = max(1, int(round(img.height * scale)))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _refine_foreground_roi(
    img: Image.Image,
    *,
    role: str,
) -> Image.Image | None:
    if role not in {"logo", "cta"}:
        return None
    try:
        import cv2
        import numpy as np
    except Exception:
        return None

    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    if h < 12 or w < 12:
        return None

    mask = np.zeros((h, w), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    margin_x = max(1, int(w * (0.08 if role == "logo" else 0.05)))
    margin_y = max(1, int(h * (0.08 if role == "logo" else 0.12)))
    rect = (
        margin_x,
        margin_y,
        max(1, w - margin_x * 2),
        max(1, h - margin_y * 2),
    )
    try:
        cv2.grabCut(arr, mask, rect, bgd, fgd, 2, cv2.GC_INIT_WITH_RECT)
    except Exception:
        return None

    fg_mask = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype("uint8")
    if role == "cta":
        component = _largest_component_mask(fg_mask)
        if component is not None:
            fg_mask = component
    ys, xs = np.where(fg_mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return None

    x1 = int(xs.min())
    y1 = int(ys.min())
    x2 = int(xs.max()) + 1
    y2 = int(ys.max()) + 1
    fg_area = max(1, (x2 - x1) * (y2 - y1))
    total_area = max(1, w * h)
    if fg_area / total_area < 0.08:
        return None

    pad_x = max(1, int((x2 - x1) * 0.05))
    pad_y = max(1, int((y2 - y1) * 0.06))
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w, x2 + pad_x)
    y2 = min(h, y2 + pad_y)
    if x2 <= x1 or y2 <= y1:
        return None
    return img.crop((x1, y1, x2, y2)).convert("RGBA")


def _largest_component_mask(mask):
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num_labels <= 1:
        return None
    best_label = None
    best_area = 0
    for idx in range(1, num_labels):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area > best_area:
            best_area = area
            best_label = idx
    if best_label is None:
        return None
    return (labels == best_label).astype(np.uint8)


def _contained_offsets(
    *,
    focus_box: dict[str, int] | None,
    source_w: int,
    source_h: int,
    fitted_w: int,
    fitted_h: int,
    target_w: int,
    target_h: int,
) -> tuple[int, int]:
    if not focus_box:
        return max(0, (target_w - fitted_w) // 2), max(0, (target_h - fitted_h) // 2)

    scale_x = fitted_w / max(1, source_w)
    scale_y = fitted_h / max(1, source_h)
    focus_cx = ((focus_box["x1"] + focus_box["x2"]) / 2) * scale_x
    focus_cy = ((focus_box["y1"] + focus_box["y2"]) / 2) * scale_y
    paste_x = int(round((target_w / 2) - focus_cx))
    paste_y = int(round((target_h / 2) - focus_cy))
    paste_x = _clamp(paste_x, 0, max(0, target_w - fitted_w))
    paste_y = _clamp(paste_y, 0, max(0, target_h - fitted_h))
    return paste_x, paste_y


def _fill_canvas_with_edge_extensions(
    canvas: Image.Image,
    fitted: Image.Image,
    paste_x: int,
    paste_y: int,
) -> None:
    edge_thickness = max(1, min(12, max(fitted.width, fitted.height) // 48))

    if paste_x > 0:
        left_strip = fitted.crop((0, 0, edge_thickness, fitted.height)).resize(
            (paste_x, fitted.height),
            Image.Resampling.BICUBIC,
        )
        canvas.alpha_composite(left_strip, (0, paste_y))
    right_gap = canvas.width - (paste_x + fitted.width)
    if right_gap > 0:
        right_strip = fitted.crop((fitted.width - edge_thickness, 0, fitted.width, fitted.height)).resize(
            (right_gap, fitted.height),
            Image.Resampling.BICUBIC,
        )
        canvas.alpha_composite(right_strip, (paste_x + fitted.width, paste_y))

    full_row = canvas.crop((0, paste_y, canvas.width, paste_y + fitted.height))
    if paste_y > 0:
        top_strip = full_row.crop((0, 0, canvas.width, edge_thickness)).resize(
            (canvas.width, paste_y),
            Image.Resampling.BICUBIC,
        )
        canvas.alpha_composite(top_strip, (0, 0))
    bottom_gap = canvas.height - (paste_y + fitted.height)
    if bottom_gap > 0:
        bottom_strip = full_row.crop((0, fitted.height - edge_thickness, canvas.width, fitted.height)).resize(
            (canvas.width, bottom_gap),
            Image.Resampling.BICUBIC,
        )
        canvas.alpha_composite(bottom_strip, (0, paste_y + fitted.height))


def _anchor_union(anchors: list[dict[str, Any]]) -> dict[str, int] | None:
    if not anchors:
        return None
    return {
        "x1": min(anchor["x1"] for anchor in anchors),
        "y1": min(anchor["y1"] for anchor in anchors),
        "x2": max(anchor["x2"] for anchor in anchors),
        "y2": max(anchor["y2"] for anchor in anchors),
    }


def _anchor_area(anchor: dict[str, Any]) -> int:
    return max(1, (anchor["x2"] - anchor["x1"]) * (anchor["y2"] - anchor["y1"]))


def _parse_size(size: str) -> tuple[int | None, int | None]:
    try:
        width_text, height_text = size.lower().split("x", 1)
        return int(width_text), int(height_text)
    except ValueError:
        return None, None


def _serialize_box(box: tuple[int, int, int, int]) -> dict[str, int]:
    return {"left": box[0], "top": box[1], "right": box[2], "bottom": box[3]}


def _logo_position_for_size(target_w: int, target_h: int) -> str:
    family = classify_size_family(target_w, target_h)
    if family == "banner":
        return "top-left"
    if family == "portrait":
        return "top-center"
    return "top-left"


def _logo_ratio_for_size(target_w: int, target_h: int) -> float:
    family = classify_size_family(target_w, target_h)
    if family == "banner":
        return 0.14
    if family == "portrait":
        return 0.18
    if family == "square":
        return 0.2
    return 0.22


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _to_png(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
