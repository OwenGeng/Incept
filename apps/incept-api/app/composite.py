"""
Image processing utilities: outpainting, background removal, text overlay.

All functions accept raw bytes and return raw bytes (PNG).
They are called synchronously in background tasks before any AI API call.
"""

from __future__ import annotations

import io
import importlib.util
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Outpainting ───────────────────────────────────────────────────────────────

def create_outpaint_inputs(
    image_bytes: bytes,
    direction: str,     # "left" | "right" | "top" | "bottom" | "all"
    ratio: float = 0.3, # fraction of original dimension to add
) -> tuple[bytes, bytes]:
    """
    Create the padded canvas and the corresponding mask for outpainting.

    Returns (expanded_png, mask_png) where the mask follows OpenAI convention:
      transparent = area to fill, opaque white = area to preserve.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size

    has_x = direction in ("left", "right", "all")
    has_y = direction in ("top", "bottom", "all")
    pad_x = int(w * ratio) if has_x else 0
    pad_y = int(h * ratio) if has_y else 0

    left   = pad_x if direction in ("left",  "all") else 0
    right  = pad_x if direction in ("right", "all") else 0
    top    = pad_y if direction in ("top",   "all") else 0
    bottom = pad_y if direction in ("bottom","all") else 0

    new_w, new_h = w + left + right, h + top + bottom

    # Expanded canvas: original image on transparent background
    canvas = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
    canvas.paste(img, (left, top))

    # Mask: opaque white where original image is, transparent where AI should fill
    from PIL import ImageDraw
    mask = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))  # all transparent
    draw = ImageDraw.Draw(mask)
    draw.rectangle([left, top, left + w - 1, top + h - 1], fill=(255, 255, 255, 255))

    return _to_png(canvas), _to_png(mask)


# ── Background removal ────────────────────────────────────────────────────────

def remove_background(image_bytes: bytes) -> tuple[bytes, bool]:
    """
    Remove the image background.

    Returns (result_png, used_rembg) where used_rembg indicates whether
    the precise ML-based removal was used.  If rembg is unavailable the
    original bytes are returned unchanged and the caller should fall back
    to an images.edit call.
    """
    try:
        from rembg import remove as rembg_remove
        result = rembg_remove(image_bytes)
        logger.info("Background removed with rembg (%d bytes)", len(result))
        return result, True
    except Exception as exc:
        logger.warning("rembg unavailable or failed (%s) — caller will use images.edit", exc)
        return image_bytes, False


# ── Text overlay ──────────────────────────────────────────────────────────────

def add_text_overlay(
    image_bytes: bytes,
    text: str,
    position: str = "bottom",   # "top" | "center" | "bottom"
    font_size_ratio: float = 0.06,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_opacity: int = 160,
) -> bytes:
    """
    Composite readable text onto an image using Pillow.

    A semi-transparent dark strip is placed behind the text for legibility.
    Returns PNG bytes.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    font_size = max(14, int(h * font_size_ratio))

    font = _load_font(font_size)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    bbox   = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad    = int(font_size * 0.4)
    strip_h = text_h + pad * 2

    strip_y = (
        0          if position == "top"
        else (h - strip_h) // 2 if position == "center"
        else h - strip_h
    )

    draw.rectangle([0, strip_y, w, strip_y + strip_h], fill=(0, 0, 0, bg_opacity))
    draw.text(
        ((w - text_w) // 2, strip_y + pad),
        text,
        font=font,
        fill=(*color, 255),
    )

    result = Image.alpha_composite(img, overlay)
    return _to_png(result)


# ── Logo compositing ─────────────────────────────────────────────────────────

_POSITION_MAP = {
    "top-left":      (0.03, 0.03),
    "top-center":    (0.5,  0.03),
    "top-right":     (0.97, 0.03),
    "center-left":   (0.03, 0.5),
    "center":        (0.5,  0.5),
    "center-right":  (0.97, 0.5),
    "bottom-left":   (0.03, 0.97),
    "bottom-center": (0.5,  0.97),
    "bottom-right":  (0.97, 0.97),
}
_LOGO_SIZE_RATIO = 0.22   # logo width ≈ 22% of base image width by default

_ANCHOR_REQUIRED_TYPES = {"logo", "cta", "character_face", "character_head", "product"}
_BANNER_ANCHOR_TYPES = {"logo", "cta", "headline_block", "character_face", "character_head", "product"}
_SCENE_TEXT_TYPES = {"logo", "cta", "headline_block"}
_SCENE_HERO_TYPES = {"character_face", "character_head", "product"}
_TEMPLATE_LIBRARY_PATH = (
    Path(__file__).resolve().parents[3] / "resize_reference" / "derived" / "template_library.json"
)


def composite_logo(
    base_bytes: bytes,
    logo_bytes: bytes,
    position: str = "top-left",
    size_ratio: float = _LOGO_SIZE_RATIO,
) -> bytes:
    """
    Pixel-perfectly composite a logo onto a base image.

    Unlike AI redraw, Pillow preserves the logo's exact colours, text,
    and proportions — it is copied, scaled, and alpha-blended directly.

    position: one of the keys in _POSITION_MAP, or "x_pct,y_pct" (e.g. "0.1,0.08")
    size_ratio: logo width as a fraction of base image width (default 0.22)
    """
    from PIL import Image

    base = Image.open(io.BytesIO(base_bytes)).convert("RGBA")
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    bw, bh = base.size

    # Scale logo so its width = size_ratio * base_width (maintain aspect ratio)
    logo_w = max(16, int(bw * size_ratio))
    logo_h = max(16, int(logo.height * logo_w / logo.width))
    logo_resized = logo.resize((logo_w, logo_h), Image.LANCZOS)

    # Resolve position
    pos_key = position.strip().lower().replace(" ", "-")
    if "," in pos_key:
        # Raw "x_pct,y_pct" format
        try:
            rx, ry = [float(v) for v in pos_key.split(",", 1)]
        except ValueError:
            rx, ry = 0.03, 0.03
    else:
        rx, ry = _POSITION_MAP.get(pos_key, _POSITION_MAP["top-left"])

    # Convert anchor point (rx,ry) to pixel coordinates for top-left of logo
    # Treat (rx,ry) as the anchor corner closest to that position
    if rx < 0.5:
        px = int(bw * rx)
    else:
        px = int(bw * rx) - logo_w

    if ry < 0.5:
        py = int(bh * ry)
    else:
        py = int(bh * ry) - logo_h

    # Clamp to image bounds
    px = max(0, min(bw - logo_w, px))
    py = max(0, min(bh - logo_h, py))

    # Composite using alpha channel of the (scaled) logo as mask
    canvas = base.copy()
    canvas.alpha_composite(logo_resized, dest=(px, py))

    return _to_png(canvas)


# ── Resize to exact dimensions ────────────────────────────────────────────────

def adapt_image_to_size(
    image_bytes: bytes,
    target_w: int,
    target_h: int,
    anchors: list[dict[str, Any]] | None = None,
    force_safe_mode: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    """
    Adapt an image to exact output dimensions while preserving semantic elements.

    The preferred path is adaptive composition: rebuild a background for the
    new aspect ratio, then reposition extracted headline/logo/CTA/character
    crops into a target-size template. Crop-based behavior is now a last resort
    for mild aspect-ratio shifts only.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    iw, ih = img.size
    source_ratio = iw / ih
    target_ratio = target_w / target_h
    normalized_anchors = _normalize_anchors(anchors or [], iw, ih)

    if abs(source_ratio - target_ratio) < 0.02:
        result = img.resize((target_w, target_h), Image.LANCZOS)
        report = {
            "mode": "scale",
            "source_size": {"width": iw, "height": ih},
            "target_size": {"width": target_w, "height": target_h},
            "anchors": normalized_anchors,
        }
        return _to_png(result), report

    ratio_shift = max(source_ratio / target_ratio, target_ratio / source_ratio)
    if normalized_anchors:
        composed, composition_report = _render_adaptive_composition(
            img,
            target_w,
            target_h,
            normalized_anchors,
        )
        if composed is not None:
            report = {
                **composition_report,
                "source_size": {"width": iw, "height": ih},
                "target_size": {"width": target_w, "height": target_h},
                "anchors": normalized_anchors,
            }
            return _to_png(composed), report

    if force_safe_mode:
        safe = _render_safe_contain(img, target_w, target_h, _anchor_union(normalized_anchors))
        report = {
            "mode": "contain",
            "reason": "forced_safe_mode",
            "source_size": {"width": iw, "height": ih},
            "target_size": {"width": target_w, "height": target_h},
            "anchors": normalized_anchors,
        }
        return _to_png(safe), report
    if not normalized_anchors and ratio_shift >= 1.15:
        safe = _render_safe_contain(img, target_w, target_h, None)
        report = {
            "mode": "contain",
            "reason": "no_anchors_for_extreme_aspect_shift",
            "source_size": {"width": iw, "height": ih},
            "target_size": {"width": target_w, "height": target_h},
            "anchors": normalized_anchors,
        }
        return _to_png(safe), report

    if ratio_shift < 1.12:
        crop_box, crop_reason = _compute_anchor_crop_box(iw, ih, target_ratio, normalized_anchors)
        if crop_box is not None:
            result = img.crop(crop_box).resize((target_w, target_h), Image.LANCZOS)
            report = {
                "mode": "anchor_crop" if normalized_anchors else "center_crop",
                "source_size": {"width": iw, "height": ih},
                "target_size": {"width": target_w, "height": target_h},
                "crop_box": _serialize_box(crop_box),
                "anchors": normalized_anchors,
            }
            return _to_png(result), report

    safe = _render_safe_contain(img, target_w, target_h, _anchor_union(normalized_anchors))
    report = {
        "mode": "contain",
        "reason": "fallback_to_safe_contain",
        "source_size": {"width": iw, "height": ih},
        "target_size": {"width": target_w, "height": target_h},
        "anchors": normalized_anchors,
    }
    return _to_png(safe), report


def resize_to_exact(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """
    Resize a generated image to exact pixel dimensions.

    Strategy:
    1. Scale so the image fills the target dimensions (maintaining aspect ratio).
    2. Center-crop any excess to hit the exact target.

    This is better than simple stretch, which would distort the image.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    iw, ih = img.size

    target_ratio = target_w / target_h
    source_ratio = iw / ih

    if abs(source_ratio - target_ratio) < 0.02:
        # Close enough — just scale directly
        result = img.resize((target_w, target_h), Image.LANCZOS)
    elif source_ratio > target_ratio:
        # Source is wider than target → scale to target height then crop sides
        scale_h = target_h
        scale_w = int(iw * target_h / ih)
        scaled = img.resize((scale_w, scale_h), Image.LANCZOS)
        left = (scale_w - target_w) // 2
        result = scaled.crop((left, 0, left + target_w, target_h))
    else:
        # Source is taller than target → scale to target width then crop top/bottom
        scale_w = target_w
        scale_h = int(ih * target_w / iw)
        scaled = img.resize((scale_w, scale_h), Image.LANCZOS)
        top = (scale_h - target_h) // 2
        result = scaled.crop((0, top, target_w, top + target_h))

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


def compose_narrow_banner(
    image_bytes: bytes,
    target_w: int,
    target_h: int,
    anchors: list[dict] | None = None,
    reference_layers: list[tuple[bytes, list[dict]]] | None = None,
) -> tuple[bytes, dict]:
    """
    Compose ultra-wide banners from detected elements instead of center-cropping.

    For 320x50 / 728x90 / 1200x222, direct center crops often miss logo and CTA.
    This deterministic layout keeps logo left, visual content center, and CTA right.
    """
    from PIL import Image, ImageFilter

    anchors = anchors or []
    reference_layers = reference_layers or []
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Use a softened cover background so the banner always fills the exact size.
    bg_bytes = resize_to_exact(image_bytes, target_w, target_h)
    background = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
    background = background.filter(ImageFilter.GaussianBlur(radius=max(0.6, target_h * 0.012)))
    overlay = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 28))
    canvas = Image.alpha_composite(background, overlay)

    layers: list[tuple[Image.Image, list[dict], str]] = [(base, anchors, "generated")]
    for idx, (layer_bytes, layer_anchors) in enumerate(reference_layers):
        try:
            layer_img = Image.open(io.BytesIO(layer_bytes)).convert("RGBA")
        except Exception:
            continue
        layers.append((layer_img, layer_anchors or [], f"reference_{idx + 1}"))

    logo = _find_anchor_crop(layers, ["logo", "headline_block"])
    cta = _find_anchor_crop(layers, ["cta"])

    # A center hero slice keeps the ad visually rich when there is room.
    hero = _center_hero_crop(base)

    margin_x = max(4, int(target_w * 0.025))
    gap = max(3, int(target_w * 0.012))
    max_logo_w = int(target_w * 0.22)
    max_logo_h = int(target_h * 0.76)
    max_cta_w = int(target_w * 0.26)
    max_cta_h = int(target_h * 0.72)

    used: list[str] = []
    left_cursor = margin_x
    right_cursor = target_w - margin_x

    if logo is not None:
        logo_img, logo_source = logo
        fitted = _fit_layer(logo_img, max_logo_w, max_logo_h)
        y = (target_h - fitted.height) // 2
        canvas.alpha_composite(fitted, (left_cursor, y))
        left_cursor += fitted.width + gap
        used.append(f"logo:{logo_source}")

    if cta is not None:
        cta_img, cta_source = cta
        fitted = _fit_layer(cta_img, max_cta_w, max_cta_h)
        x = right_cursor - fitted.width
        y = (target_h - fitted.height) // 2
        canvas.alpha_composite(fitted, (x, y))
        right_cursor = x - gap
        used.append(f"cta:{cta_source}")

    if hero is not None and right_cursor > left_cursor + max(24, int(target_w * 0.18)):
        hero_w = right_cursor - left_cursor
        hero_h = int(target_h * 0.9)
        fitted = _cover_layer(hero, hero_w, hero_h)
        y = (target_h - fitted.height) // 2
        canvas.alpha_composite(fitted, (left_cursor, y))
        used.append("hero:center")

    report = {
        "mode": "narrow_banner_composite",
        "source_size": {"width": base.width, "height": base.height},
        "target_size": {"width": target_w, "height": target_h},
        "used_layers": used,
        "has_logo": logo is not None,
        "has_cta": cta is not None,
    }
    return _to_png(canvas), report


def _find_anchor_crop(
    layers: list[tuple["Image.Image", list[dict], str]],
    types: list[str],
) -> tuple["Image.Image", str] | None:
    for img, anchors, source in layers:
        for anchor in anchors:
            if anchor.get("type") not in types:
                continue
            bbox = anchor.get("bbox") or {}
            crop = _crop_bbox_pct(img, bbox, pad=0.08)
            if crop is not None:
                return crop, source
    return None


def _crop_bbox_pct(img: "Image.Image", bbox: dict, pad: float = 0.0) -> "Image.Image | None":
    try:
        x = float(bbox.get("x_pct", 0.0))
        y = float(bbox.get("y_pct", 0.0))
        w = float(bbox.get("w_pct", 0.0))
        h = float(bbox.get("h_pct", 0.0))
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    px = w * pad
    py = h * pad
    x1 = max(0, int((x - px) * img.width))
    y1 = max(0, int((y - py) * img.height))
    x2 = min(img.width, int((x + w + px) * img.width))
    y2 = min(img.height, int((y + h + py) * img.height))
    if x2 <= x1 or y2 <= y1:
        return None
    return img.crop((x1, y1, x2, y2))


def _center_hero_crop(img: "Image.Image") -> "Image.Image | None":
    if img.width <= 0 or img.height <= 0:
        return None
    crop_w = int(img.width * 0.56)
    crop_h = int(img.height * 0.42)
    x1 = max(0, (img.width - crop_w) // 2)
    y1 = max(0, int(img.height * 0.30))
    x2 = min(img.width, x1 + crop_w)
    y2 = min(img.height, y1 + crop_h)
    if x2 <= x1 or y2 <= y1:
        return None
    return img.crop((x1, y1, x2, y2))


def _fit_layer(img: "Image.Image", max_w: int, max_h: int) -> "Image.Image":
    from PIL import Image

    if img.width <= 0 or img.height <= 0:
        return img
    scale = min(max_w / img.width, max_h / img.height, 1.0)
    new_w = max(1, int(img.width * scale))
    new_h = max(1, int(img.height * scale))
    return img.resize((new_w, new_h), Image.LANCZOS)


def _cover_layer(img: "Image.Image", target_w: int, target_h: int) -> "Image.Image":
    from PIL import Image

    if img.width <= 0 or img.height <= 0:
        return img
    scale = max(target_w / img.width, target_h / img.height)
    scaled_w = max(1, int(img.width * scale))
    scaled_h = max(1, int(img.height * scale))
    scaled = img.resize((scaled_w, scaled_h), Image.LANCZOS)
    left = max(0, (scaled_w - target_w) // 2)
    top = max(0, (scaled_h - target_h) // 2)
    return scaled.crop((left, top, left + target_w, top + target_h))


def get_openai_size(w: int, h: int, model: str) -> str:
    """
    Map requested pixel dimensions to the nearest OpenAI-supported size string.

    OpenAI gpt-image-2 / gpt-image-1 supports:
      1024x1024  (square)
      1536x1024  (landscape 3:2)
      1024x1536  (portrait 2:3)

    dall-e-2 and dall-e-3 only support square sizes.
    """
    if model in {"dall-e-2", "dall-e-3"}:
        return "1024x1024"

    ratio = w / h
    if ratio >= 1.4:      # Wide landscape (1200x628=1.91, 1200x222=5.4, 728x90=8.1)
        return "1536x1024"
    elif ratio <= 0.72:   # Portrait (320x480=0.67)
        return "1024x1536"
    else:
        return "1024x1024"  # Square-ish (300x250=1.2, 720x720=1.0)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normalize_anchors(
    anchors: list[dict[str, Any]],
    image_w: int,
    image_h: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for anchor in anchors:
        bbox = anchor.get("bbox") if isinstance(anchor.get("bbox"), dict) else anchor
        kind = _normalize_anchor_type(
            str(anchor.get("type") or anchor.get("kind") or anchor.get("label") or "")
        )
        x_pct = _clamp_pct(bbox.get("x_pct", 0.0))
        y_pct = _clamp_pct(bbox.get("y_pct", 0.0))
        w_pct = _clamp_pct(bbox.get("w_pct", 0.0))
        h_pct = _clamp_pct(bbox.get("h_pct", 0.0))
        if w_pct <= 0 or h_pct <= 0:
            continue
        x1 = int(round(x_pct * image_w))
        y1 = int(round(y_pct * image_h))
        x2 = int(round((x_pct + w_pct) * image_w))
        y2 = int(round((y_pct + h_pct) * image_h))
        if x2 <= x1 or y2 <= y1:
            continue
        normalized.append(
            {
                "type": kind,
                "label": anchor.get("label") or kind,
                "confidence": anchor.get("confidence") or "medium",
                "required": bool(anchor.get("required", kind in _ANCHOR_REQUIRED_TYPES)),
                "bbox": {"x_pct": x_pct, "y_pct": y_pct, "w_pct": w_pct, "h_pct": h_pct},
                "x1": max(0, x1),
                "y1": max(0, y1),
                "x2": min(image_w, x2),
                "y2": min(image_h, y2),
            }
        )
    return normalized


def _normalize_anchor_type(value: str) -> str:
    raw = value.strip().lower().replace("-", "_").replace(" ", "_")
    if "logo" in raw or "wordmark" in raw or "brand" in raw:
        return "logo"
    if "cta" in raw or "button" in raw or "call_to_action" in raw:
        return "cta"
    if "face" in raw:
        return "character_face"
    if "head" in raw or "character" in raw:
        return "character_head"
    if "product" in raw or "packshot" in raw or "hero_item" in raw:
        return "product"
    if "headline" in raw or "text_block" in raw or "copy_block" in raw or raw == "text":
        return "headline_block"
    return raw or "anchor"


def _compute_anchor_crop_box(
    image_w: int,
    image_h: int,
    target_ratio: float,
    anchors: list[dict[str, Any]],
) -> tuple[tuple[int, int, int, int] | None, str | None]:
    source_ratio = image_w / image_h
    default_box = _center_crop_box(image_w, image_h, target_ratio)
    required = [anchor for anchor in anchors if anchor.get("required")]
    if not required:
        return default_box, None

    union = _anchor_union(required)
    if not union:
        return default_box, None

    if source_ratio > target_ratio:
        crop_h = image_h
        crop_w = max(1, int(round(image_h * target_ratio)))
        if (union["x2"] - union["x1"]) > crop_w:
            return None, "required_anchors_too_wide_for_target"
        min_left = max(0, int(round(union["x2"] - crop_w)))
        max_left = min(int(round(union["x1"])), image_w - crop_w)
        if min_left > max_left:
            return None, "no_horizontal_crop_window"
        preferred_left = int(round(((union["x1"] + union["x2"]) / 2) - (crop_w / 2)))
        left = _clamp(preferred_left, min_left, max_left)
        crop_box = (left, 0, left + crop_w, image_h)
    else:
        crop_w = image_w
        crop_h = max(1, int(round(image_w / target_ratio)))
        if (union["y2"] - union["y1"]) > crop_h:
            return None, "required_anchors_too_tall_for_target"
        min_top = max(0, int(round(union["y2"] - crop_h)))
        max_top = min(int(round(union["y1"])), image_h - crop_h)
        if min_top > max_top:
            return None, "no_vertical_crop_window"
        preferred_top = int(round(((union["y1"] + union["y2"]) / 2) - (crop_h / 2)))
        top = _clamp(preferred_top, min_top, max_top)
        crop_box = (0, top, image_w, top + crop_h)

    if not _crop_preserves_required_anchors(crop_box, required):
        return None, "anchor_validation_failed"
    return crop_box, None


def _crop_preserves_required_anchors(
    crop_box: tuple[int, int, int, int],
    anchors: list[dict[str, Any]],
) -> bool:
    for anchor in anchors:
        area = max(1, (anchor["x2"] - anchor["x1"]) * (anchor["y2"] - anchor["y1"]))
        inter_w = max(0, min(crop_box[2], anchor["x2"]) - max(crop_box[0], anchor["x1"]))
        inter_h = max(0, min(crop_box[3], anchor["y2"]) - max(crop_box[1], anchor["y1"]))
        coverage = (inter_w * inter_h) / area
        threshold = 0.98 if anchor["type"] in {"logo", "cta"} else 0.94
        if coverage < threshold:
            return False
    return True


def _center_crop_box(image_w: int, image_h: int, target_ratio: float) -> tuple[int, int, int, int]:
    source_ratio = image_w / image_h
    if source_ratio > target_ratio:
        crop_w = max(1, int(round(image_h * target_ratio)))
        left = max(0, (image_w - crop_w) // 2)
        return (left, 0, left + crop_w, image_h)
    crop_h = max(1, int(round(image_w / target_ratio)))
    top = max(0, (image_h - crop_h) // 2)
    return (0, top, image_w, top + crop_h)


def _render_safe_contain(img, target_w: int, target_h: int, focus_box: dict[str, int] | None):
    from PIL import Image, ImageFilter

    iw, ih = img.size
    bg_scale = max(target_w / iw, target_h / ih)
    bg_w = max(target_w, int(round(iw * bg_scale)))
    bg_h = max(target_h, int(round(ih * bg_scale)))
    bg = img.resize((bg_w, bg_h), Image.LANCZOS)

    if focus_box:
        focus_cx = ((focus_box["x1"] + focus_box["x2"]) / 2) * bg_scale
        focus_cy = ((focus_box["y1"] + focus_box["y2"]) / 2) * bg_scale
        bg_left = _clamp(int(round(focus_cx - (target_w / 2))), 0, max(0, bg_w - target_w))
        bg_top = _clamp(int(round(focus_cy - (target_h / 2))), 0, max(0, bg_h - target_h))
    else:
        bg_left = max(0, (bg_w - target_w) // 2)
        bg_top = max(0, (bg_h - target_h) // 2)

    background = bg.crop((bg_left, bg_top, bg_left + target_w, bg_top + target_h))
    background = background.filter(
        ImageFilter.GaussianBlur(radius=max(10, int(min(target_w, target_h) * 0.03)))
    )
    scrim = Image.new("RGBA", (target_w, target_h), (10, 10, 10, 76))
    background = Image.alpha_composite(background, scrim)

    fg_scale = min(target_w / iw, target_h / ih)
    fg_w = max(1, int(round(iw * fg_scale)))
    fg_h = max(1, int(round(ih * fg_scale)))
    foreground = img.resize((fg_w, fg_h), Image.LANCZOS)

    if focus_box:
        focus_cx = ((focus_box["x1"] + focus_box["x2"]) / 2) * fg_scale
        focus_cy = ((focus_box["y1"] + focus_box["y2"]) / 2) * fg_scale
        fg_left = _clamp(int(round((target_w / 2) - focus_cx)), 0, max(0, target_w - fg_w))
        fg_top = _clamp(int(round((target_h / 2) - focus_cy)), 0, max(0, target_h - fg_h))
    else:
        fg_left = max(0, (target_w - fg_w) // 2)
        fg_top = max(0, (target_h - fg_h) // 2)

    canvas = background.copy()
    canvas.alpha_composite(foreground, (fg_left, fg_top))
    return canvas


def _render_ultra_wide_banner(img, target_w: int, target_h: int, anchors: list[dict[str, Any]]):
    from PIL import Image, ImageFilter

    iw, ih = img.size
    banner_anchors = [anchor for anchor in anchors if anchor["type"] in _BANNER_ANCHOR_TYPES]
    focus_box = _anchor_union(banner_anchors) or _anchor_union(anchors)

    bg_scale = max(target_w / iw, target_h / ih)
    bg_w = max(target_w, int(round(iw * bg_scale)))
    bg_h = max(target_h, int(round(ih * bg_scale)))
    bg = img.resize((bg_w, bg_h), Image.LANCZOS)
    bg_left = max(0, (bg_w - target_w) // 2)
    bg_top = max(0, (bg_h - target_h) // 2)
    background = bg.crop((bg_left, bg_top, bg_left + target_w, bg_top + target_h))
    background = background.filter(
        ImageFilter.GaussianBlur(radius=max(12, int(target_h * 0.24)))
    )
    background = Image.alpha_composite(
        background,
        Image.new("RGBA", (target_w, target_h), (6, 8, 12, 96)),
    )

    fg_scale = min((target_w * 0.92) / iw, (target_h * 0.86) / ih)
    fg_w = max(1, int(round(iw * fg_scale)))
    fg_h = max(1, int(round(ih * fg_scale)))
    foreground = img.resize((fg_w, fg_h), Image.LANCZOS)

    if focus_box:
        focus_cx = ((focus_box["x1"] + focus_box["x2"]) / 2) * fg_scale
        focus_cy = ((focus_box["y1"] + focus_box["y2"]) / 2) * fg_scale
        fg_left = _clamp(int(round((target_w / 2) - focus_cx)), 0, max(0, target_w - fg_w))
        fg_top = _clamp(int(round((target_h / 2) - focus_cy)), 0, max(0, target_h - fg_h))
    else:
        fg_left = max(0, (target_w - fg_w) // 2)
        fg_top = max(0, (target_h - fg_h) // 2)

    canvas = background.copy()
    canvas.alpha_composite(foreground, (fg_left, fg_top))
    return canvas


def _render_adaptive_composition(
    img,
    target_w: int,
    target_h: int,
    anchors: list[dict[str, Any]],
) -> tuple[Any | None, dict[str, Any]]:
    from PIL import Image

    elements = _extract_scene_elements(img, anchors)
    if not any(
        [
            elements["logos"],
            elements["ctas"],
            elements["headlines"],
            elements["characters"],
            elements["products"],
        ]
    ):
        return None, {"mode": "adaptive_composition_unavailable", "reason": "no_scene_elements"}

    family = _classify_layout_family(target_w, target_h)
    focus_box = _anchor_union(anchors)
    background = _build_adaptive_background(
        img,
        target_w,
        target_h,
        focus_box,
        family=family,
    )
    canvas = background.copy()
    placements: list[dict[str, Any]] = []

    template_report = _apply_reference_template_layout(
        canvas,
        elements,
        target_w,
        target_h,
        family=family,
        placements=placements,
    )
    if template_report is not None and placements:
        report = {
            "mode": "adaptive_composition",
            "layout_family": family,
            "layout_source": "resize_reference_template",
            "placed_elements": placements,
            **template_report,
        }
        return canvas, report

    if family == "ultra_banner":
        _compose_ultra_banner_layout(canvas, elements, target_w, target_h, placements)
    elif family == "banner":
        _compose_banner_layout(canvas, elements, target_w, target_h, placements)
    elif family == "portrait":
        _compose_portrait_layout(canvas, elements, target_w, target_h, placements)
    elif family == "square":
        _compose_square_layout(canvas, elements, target_w, target_h, placements)
    else:
        _compose_landscape_layout(canvas, elements, target_w, target_h, placements)

    if not placements:
        return None, {
            "mode": "adaptive_composition_unavailable",
            "reason": "no_elements_placed",
            "layout_family": family,
        }

    report = {
        "mode": "adaptive_composition",
        "layout_family": family,
        "layout_source": "built_in_fallback",
        "placed_elements": placements,
    }
    return canvas, report


def _extract_scene_elements(img, anchors: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    elements = {
        "logos": [],
        "ctas": [],
        "headlines": [],
        "characters": [],
        "products": [],
        "hero_scenes": [],
        "hero_banners": [],
    }
    if not anchors:
        return elements

    image_w, image_h = img.size
    logos = [anchor for anchor in anchors if anchor["type"] == "logo"]
    ctas = [anchor for anchor in anchors if anchor["type"] == "cta"]
    headlines = [anchor for anchor in anchors if anchor["type"] == "headline_block"]
    characters = [
        anchor for anchor in anchors if anchor["type"] in {"character_face", "character_head"}
    ]
    products = [anchor for anchor in anchors if anchor["type"] == "product"]

    primary_logo = _pick_primary_anchor(logos) if logos else None
    primary_headline = _pick_primary_anchor(headlines) if headlines else None
    if primary_logo:
        elements["logos"].append(_scene_element_from_anchor(img, primary_logo, image_w, image_h))
    if ctas:
        elements["ctas"].append(_scene_element_from_anchor(img, _pick_primary_anchor(ctas), image_w, image_h))
    if primary_headline and (
        not primary_logo or _box_overlap_ratio(primary_logo, primary_headline) < 0.7
    ):
        elements["headlines"].append(
            _scene_element_from_anchor(img, primary_headline, image_w, image_h)
        )
    picked_characters = _pick_distinct_anchors(characters, limit=2)
    picked_products = _pick_distinct_anchors(products, limit=1)
    for anchor in picked_characters:
        elements["characters"].append(_scene_element_from_anchor(img, anchor, image_w, image_h))
    for anchor in picked_products:
        elements["products"].append(_scene_element_from_anchor(img, anchor, image_w, image_h))
    hero_members = picked_characters + picked_products
    if hero_members:
        elements["hero_scenes"].append(
            _scene_element_from_box(
                img,
                _expanded_union_crop_box(hero_members, image_w, image_h),
                kind="hero_scene",
            )
        )
        elements["hero_banners"].append(
            _scene_element_from_box(
                img,
                _expanded_union_banner_crop_box(hero_members, image_w, image_h),
                kind="hero_banner",
            )
        )
    return elements


@lru_cache(maxsize=1)
def _load_reference_templates() -> list[dict[str, Any]]:
    if not _TEMPLATE_LIBRARY_PATH.exists():
        return []
    try:
        payload = json.loads(_TEMPLATE_LIBRARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load resize reference template library")
        return []
    templates = payload.get("templates")
    if isinstance(templates, list):
        return templates
    return []


def _apply_reference_template_layout(
    canvas,
    elements: dict[str, list[dict[str, Any]]],
    target_w: int,
    target_h: int,
    *,
    family: str,
    placements: list[dict[str, Any]],
) -> dict[str, Any] | None:
    template = _select_reference_template(
        family=family,
        target_w=target_w,
        target_h=target_h,
        elements=elements,
    )
    if template is None:
        return None

    executable_slots = template.get("executable_slots") or {}
    placed_count = 0
    for slot_name, details in executable_slots.items():
        rect_pct = details.get("box_pct") if isinstance(details, dict) else None
        rect = _pct_rect_to_pixels(rect_pct, target_w, target_h)
        if rect is None:
            continue
        element = _element_for_template_slot(elements, slot_name, family=family)
        if element is None:
            continue
        if slot_name == "hero":
            before = len(placements)
            _place_hero(canvas, element, rect, placements, soften=True)
            placed_count += len(placements) - before
        else:
            before = len(placements)
            _place_textish(canvas, element, rect, placements)
            placed_count += len(placements) - before

    if placed_count == 0:
        return None
    return {
        "template_id": template.get("id"),
        "template_sizes": template.get("sizes", []),
        "template_slot_positions": template.get("slot_positions", {}),
    }


def _select_reference_template(
    *,
    family: str,
    target_w: int,
    target_h: int,
    elements: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    target_size = f"{target_w}x{target_h}"
    reference_family = _reference_family_name(family)
    templates = [
        template for template in _load_reference_templates() if template.get("family") == reference_family
    ]
    if not templates:
        return None

    available = _available_template_slots(elements, family=family)
    best_template: dict[str, Any] | None = None
    best_score = float("-inf")
    for template in templates:
        slots = template.get("executable_slots") or {}
        slot_names = set(slots.keys())
        if not slot_names:
            continue
        overlap = available & slot_names
        if len(overlap) < 2:
            continue
        score = 0.0
        if target_size in set(template.get("sizes") or []):
            score += 120
        elif any(size.endswith(target_size.split("x", 1)[1]) for size in template.get("sizes", [])):
            score += 15
        score += len(overlap) * 18
        score -= len(slot_names - available) * 8
        score += len(slot_names) * 2
        if score > best_score:
            best_score = score
            best_template = template
    return best_template


def _reference_family_name(family: str) -> str:
    return {
        "landscape": "landscape_native",
        "square": "compact_square",
        "portrait": "portrait_stack",
        "banner": "banner_horizontal",
        "ultra_banner": "ultra_banner_horizontal",
    }.get(family, family)


def _available_template_slots(
    elements: dict[str, list[dict[str, Any]]],
    *,
    family: str,
) -> set[str]:
    available: set[str] = set()
    if elements.get("logos"):
        available.add("logo")
    if elements.get("headlines"):
        available.add("headline")
    if elements.get("ctas"):
        available.add("cta")
    if _element_for_template_slot(elements, "hero", family=family) is not None:
        available.add("hero")
    return available


def _element_for_template_slot(
    elements: dict[str, list[dict[str, Any]]],
    slot_name: str,
    *,
    family: str,
) -> dict[str, Any] | None:
    if slot_name == "logo":
        return _first(elements.get("logos", []))
    if slot_name == "headline":
        return _first(elements.get("headlines", []))
    if slot_name == "cta":
        return _first(elements.get("ctas", []))
    if slot_name == "hero":
        if family in {"banner", "ultra_banner"}:
            return _first(elements.get("hero_banners", [])) or _first(elements.get("hero_scenes", []))
        return _first(elements.get("hero_scenes", [])) or _first(elements.get("hero_banners", []))
    return None


def _pct_rect_to_pixels(box_pct: Any, target_w: int, target_h: int) -> tuple[int, int, int, int] | None:
    if not isinstance(box_pct, list) or len(box_pct) != 4:
        return None
    try:
        x_pct, y_pct, w_pct, h_pct = [float(value) for value in box_pct]
    except (TypeError, ValueError):
        return None
    x = int(round(target_w * x_pct))
    y = int(round(target_h * y_pct))
    width = max(1, int(round(target_w * w_pct)))
    height = max(1, int(round(target_h * h_pct)))
    x = max(0, min(target_w - 1, x))
    y = max(0, min(target_h - 1, y))
    width = min(width, target_w - x)
    height = min(height, target_h - y)
    return (x, y, width, height)


def _scene_element_from_anchor(img, anchor: dict[str, Any], image_w: int, image_h: int) -> dict[str, Any]:
    crop_box = _expanded_anchor_crop_box(anchor, image_w, image_h)
    return _scene_element_from_box(img, crop_box, kind=anchor["type"])


def _scene_element_from_box(
    img,
    crop_box: tuple[int, int, int, int],
    *,
    kind: str,
) -> dict[str, Any]:
    crop = img.crop(crop_box).convert("RGBA")
    if kind in {"character_face", "character_head", "product", "hero_scene", "hero_banner"}:
        crop = _extract_foreground_crop(crop)
    return {
        "type": kind,
        "anchor": None,
        "source_box": _serialize_box(crop_box),
        "image": crop,
    }


def _expanded_anchor_crop_box(
    anchor: dict[str, Any],
    image_w: int,
    image_h: int,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = anchor["x1"], anchor["y1"], anchor["x2"], anchor["y2"]
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    kind = anchor["type"]

    if kind == "logo":
        left = x1 - int(width * 0.04)
        right = x2 + int(width * 0.04)
        top = y1 - int(height * 0.08)
        bottom = y2 + int(height * 0.08)
    elif kind == "cta":
        left = x1 - int(width * 0.16)
        right = x2 + int(width * 0.16)
        top = y1 - int(height * 0.18)
        bottom = y2 + int(height * 0.18)
    elif kind == "headline_block":
        left = x1 - int(width * 0.08)
        right = x2 + int(width * 0.08)
        top = y1 - int(height * 0.1)
        bottom = y2 + int(height * 0.1)
    elif kind in {"character_face", "character_head"}:
        left = x1 - int(width * 1.35)
        right = x2 + int(width * 1.35)
        top = y1 - int(height * 0.75)
        bottom = y2 + int(height * 3.8)
    elif kind == "product":
        left = x1 - int(width * 0.45)
        right = x2 + int(width * 0.45)
        top = y1 - int(height * 0.45)
        bottom = y2 + int(height * 0.9)
    else:
        left = x1 - int(width * 0.2)
        right = x2 + int(width * 0.2)
        top = y1 - int(height * 0.2)
        bottom = y2 + int(height * 0.2)

    return (
        _clamp(left, 0, image_w - 1),
        _clamp(top, 0, image_h - 1),
        _clamp(right, 1, image_w),
        _clamp(bottom, 1, image_h),
    )


def _expanded_union_crop_box(
    anchors: list[dict[str, Any]],
    image_w: int,
    image_h: int,
) -> tuple[int, int, int, int]:
    union = _anchor_union(anchors)
    if not union:
        return (0, 0, image_w, image_h)
    width = max(1, union["x2"] - union["x1"])
    height = max(1, union["y2"] - union["y1"])
    return (
        _clamp(union["x1"] - int(width * 0.24), 0, image_w - 1),
        _clamp(union["y1"] - int(height * 0.2), 0, image_h - 1),
        _clamp(union["x2"] + int(width * 0.24), 1, image_w),
        _clamp(union["y2"] + int(height * 0.22), 1, image_h),
    )


def _expanded_union_banner_crop_box(
    anchors: list[dict[str, Any]],
    image_w: int,
    image_h: int,
) -> tuple[int, int, int, int]:
    union = _anchor_union(anchors)
    if not union:
        return (0, 0, image_w, image_h)
    width = max(1, union["x2"] - union["x1"])
    height = max(1, union["y2"] - union["y1"])
    return (
        _clamp(union["x1"] - int(width * 1.1), 0, image_w - 1),
        _clamp(union["y1"] - int(height * 0.22), 0, image_h - 1),
        _clamp(union["x2"] + int(width * 0.42), 1, image_w),
        _clamp(union["y2"] + int(height * 0.18), 1, image_h),
    )


def _pick_primary_anchor(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        anchors,
        key=lambda anchor: (
            0 if anchor["type"] in _SCENE_TEXT_TYPES else 1,
            -_anchor_area(anchor),
            anchor["x1"],
        ),
    )[0]


def _pick_distinct_anchors(anchors: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    for anchor in sorted(anchors, key=lambda item: (-_anchor_area(item), item["x1"])):
        if all(_box_overlap_ratio(anchor, existing) < 0.45 for existing in picked):
            picked.append(anchor)
        if len(picked) >= limit:
            break
    return sorted(picked, key=lambda item: item["x1"])


def _anchor_area(anchor: dict[str, Any]) -> int:
    return max(1, (anchor["x2"] - anchor["x1"]) * (anchor["y2"] - anchor["y1"]))


def _box_overlap_ratio(a: dict[str, Any], b: dict[str, Any]) -> float:
    inter_w = max(0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]))
    inter_h = max(0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
    inter_area = inter_w * inter_h
    return inter_area / max(1, min(_anchor_area(a), _anchor_area(b)))


def _classify_layout_family(target_w: int, target_h: int) -> str:
    ratio = target_w / max(1, target_h)
    if target_h <= 60 or ratio >= 5.0:
        return "ultra_banner"
    if ratio >= 2.6:
        return "banner"
    if ratio <= 0.8:
        return "portrait"
    if ratio <= 1.35:
        return "square"
    return "landscape"


def _build_adaptive_background(
    img,
    target_w: int,
    target_h: int,
    focus_box: dict[str, int] | None,
    *,
    family: str,
):
    from PIL import Image, ImageFilter

    iw, ih = img.size
    bg_scale = max(target_w / iw, target_h / ih)
    bg_w = max(target_w, int(round(iw * bg_scale)))
    bg_h = max(target_h, int(round(ih * bg_scale)))
    scaled = img.resize((bg_w, bg_h), Image.LANCZOS)

    if focus_box:
        focus_cx = ((focus_box["x1"] + focus_box["x2"]) / 2) * bg_scale
        focus_cy = ((focus_box["y1"] + focus_box["y2"]) / 2) * bg_scale
        left = _clamp(int(round(focus_cx - (target_w / 2))), 0, max(0, bg_w - target_w))
        top = _clamp(int(round(focus_cy - (target_h / 2))), 0, max(0, bg_h - target_h))
    else:
        left = max(0, (bg_w - target_w) // 2)
        top = max(0, (bg_h - target_h) // 2)

    sharp = scaled.crop((left, top, left + target_w, top + target_h)).convert("RGBA")
    blur_strength = {
        "ultra_banner": max(10, int(target_h * 0.24)),
        "banner": max(9, int(target_h * 0.18)),
        "portrait": max(8, int(target_w * 0.045)),
        "square": max(8, int(min(target_w, target_h) * 0.04)),
        "landscape": max(7, int(min(target_w, target_h) * 0.032)),
    }[family]
    blurred = sharp.filter(ImageFilter.GaussianBlur(radius=blur_strength))
    atmosphere = _with_alpha(sharp, 54 if family in {"banner", "ultra_banner"} else 72)
    background = Image.alpha_composite(blurred, atmosphere)
    scrim_alpha = 74 if family in {"banner", "ultra_banner"} else 44
    return Image.alpha_composite(
        background,
        Image.new("RGBA", (target_w, target_h), (8, 10, 14, scrim_alpha)),
    )


def _compose_landscape_layout(canvas, elements, target_w: int, target_h: int, placements: list[dict[str, Any]]):
    pad = max(18, int(min(target_w, target_h) * 0.035))
    _place_textish(canvas, _first(elements["logos"]), (pad, pad, int(target_w * 0.22), int(target_h * 0.15)), placements)
    hero_scene = _first(elements["hero_scenes"])
    if hero_scene:
        _place_hero(canvas, hero_scene, (int(target_w * 0.55), int(target_h * 0.32), int(target_w * 0.34), int(target_h * 0.5)), placements, soften=True)
    else:
        _place_character_stack(canvas, elements["characters"], target_w, target_h, placements, left_box=(pad, int(target_h * 0.08), int(target_w * 0.3), int(target_h * 0.84)), right_box=(int(target_w * 0.63), int(target_h * 0.06), int(target_w * 0.26), int(target_h * 0.86)))
    _place_textish(canvas, _first(elements["headlines"]), (int(target_w * 0.26), int(target_h * 0.52), int(target_w * 0.3), int(target_h * 0.18)), placements)
    _place_textish(canvas, _first(elements["ctas"]), (int(target_w * 0.39), int(target_h * 0.76), int(target_w * 0.22), int(target_h * 0.12)), placements)


def _compose_square_layout(canvas, elements, target_w: int, target_h: int, placements: list[dict[str, Any]]):
    pad = max(10, int(min(target_w, target_h) * 0.04))
    _place_textish(canvas, _first(elements["logos"]), (int(target_w * 0.22), pad, int(target_w * 0.56), int(target_h * 0.18)), placements)
    hero_scene = _first(elements["hero_scenes"])
    if hero_scene:
        _place_hero(canvas, hero_scene, (int(target_w * 0.12), int(target_h * 0.28), int(target_w * 0.76), int(target_h * 0.42)), placements, soften=True)
    else:
        _place_character_stack(canvas, elements["characters"], target_w, target_h, placements, left_box=(0, int(target_h * 0.1), int(target_w * 0.46), int(target_h * 0.62)), right_box=(int(target_w * 0.48), int(target_h * 0.08), int(target_w * 0.44), int(target_h * 0.62)))
    _place_textish(canvas, _first(elements["headlines"]), (int(target_w * 0.08), int(target_h * 0.54), int(target_w * 0.84), int(target_h * 0.18)), placements)
    _place_textish(canvas, _first(elements["ctas"]), (int(target_w * 0.23), int(target_h * 0.81), int(target_w * 0.54), int(target_h * 0.11)), placements)


def _compose_portrait_layout(canvas, elements, target_w: int, target_h: int, placements: list[dict[str, Any]]):
    pad = max(12, int(target_w * 0.04))
    _place_textish(canvas, _first(elements["logos"]), (int(target_w * 0.22), pad, int(target_w * 0.56), int(target_h * 0.12)), placements)
    hero_scene = _first(elements["hero_scenes"])
    if hero_scene:
        _place_hero(canvas, hero_scene, (int(target_w * 0.06), int(target_h * 0.2), int(target_w * 0.88), int(target_h * 0.46)), placements, soften=True)
    else:
        _place_character_stack(canvas, elements["characters"], target_w, target_h, placements, left_box=(0, int(target_h * 0.12), int(target_w * 0.56), int(target_h * 0.58)), right_box=(int(target_w * 0.42), int(target_h * 0.12), int(target_w * 0.56), int(target_h * 0.56)))
    _place_textish(canvas, _first(elements["headlines"]), (int(target_w * 0.08), int(target_h * 0.68), int(target_w * 0.84), int(target_h * 0.12)), placements)
    _place_textish(canvas, _first(elements["ctas"]), (int(target_w * 0.22), int(target_h * 0.86), int(target_w * 0.56), int(target_h * 0.08)), placements)


def _compose_banner_layout(canvas, elements, target_w: int, target_h: int, placements: list[dict[str, Any]]):
    pad = max(8, int(target_h * 0.09))
    cta_width = int(target_w * 0.19) if elements["ctas"] else 0
    _place_textish(canvas, _first(elements["logos"]), (pad, pad, int(target_w * 0.2), int(target_h * 0.26)), placements)
    hero_scene = _first(elements["hero_banners"]) or _first(elements["hero_scenes"])
    if hero_scene:
        _place_hero(canvas, hero_scene, (int(target_w * 0.33), 0, int(target_w * 0.50), int(target_h * 0.98)), placements, soften=True)
    else:
        _place_character_stack(canvas, elements["characters"], target_w, target_h, placements, left_box=(int(target_w * 0.28), 0, int(target_w * 0.24), int(target_h * 0.95)), right_box=(int(target_w * 0.53), 0, int(target_w * 0.2), int(target_h * 0.95)))
    headline_left = int(target_w * 0.16)
    headline_right = target_w - cta_width - pad * 2
    _place_textish(canvas, _first(elements["headlines"]), (headline_left, int(target_h * 0.08), max(20, headline_right - headline_left), int(target_h * 0.36)), placements)
    _place_textish(canvas, _first(elements["ctas"]), (target_w - cta_width - pad, int(target_h * 0.24), cta_width, int(target_h * 0.48)), placements)


def _compose_ultra_banner_layout(canvas, elements, target_w: int, target_h: int, placements: list[dict[str, Any]]):
    pad = max(4, int(target_h * 0.08))
    cta_width = int(target_w * 0.22) if elements["ctas"] else int(target_w * 0.14)
    cta_left = target_w - cta_width - pad
    _place_textish(canvas, _first(elements["logos"]), (pad, int(target_h * 0.08), int(target_w * 0.24), int(target_h * 0.84)), placements)
    hero_scene = _first(elements["hero_banners"]) or _first(elements["hero_scenes"])
    if hero_scene:
        hero_width = int(target_w * 0.52) if elements["headlines"] else int(target_w * 0.62)
        hero_left = max(int(target_w * 0.26), target_w - cta_width - hero_width - pad * 2)
        _place_hero(canvas, hero_scene, (hero_left, 0, hero_width, target_h), placements, soften=True)
    else:
        _place_character_stack(canvas, elements["characters"], target_w, target_h, placements, left_box=(int(target_w * 0.18), 0, int(target_w * 0.24), target_h), right_box=(int(target_w * 0.64), 0, int(target_w * 0.14), target_h))
    headline_left = int(target_w * 0.16)
    headline_width = max(24, cta_left - headline_left - pad)
    _place_textish(canvas, _first(elements["headlines"]), (headline_left, pad, headline_width, int(target_h * 0.42)), placements)
    _place_textish(canvas, _first(elements["ctas"]), (cta_left, int(target_h * 0.17), cta_width, int(target_h * 0.58)), placements)


def _place_character_stack(
    canvas,
    characters: list[dict[str, Any]],
    target_w: int,
    target_h: int,
    placements: list[dict[str, Any]],
    *,
    left_box: tuple[int, int, int, int],
    right_box: tuple[int, int, int, int],
):
    if characters:
        _place_hero(canvas, characters[0], left_box, placements, soften=True)
    if len(characters) > 1:
        _place_hero(canvas, characters[1], right_box, placements, soften=True)


def _place_textish(canvas, element: dict[str, Any] | None, rect: tuple[int, int, int, int], placements: list[dict[str, Any]]):
    if not element:
        return
    _place_element(canvas, element, rect, placements, soften=False)


def _place_hero(
    canvas,
    element: dict[str, Any] | None,
    rect: tuple[int, int, int, int],
    placements: list[dict[str, Any]],
    *,
    soften: bool,
):
    if not element:
        return
    _place_element(canvas, element, rect, placements, soften=soften)


def _place_element(
    canvas,
    element: dict[str, Any],
    rect: tuple[int, int, int, int],
    placements: list[dict[str, Any]],
    *,
    soften: bool,
):
    from PIL import Image

    x, y, box_w, box_h = rect
    if box_w <= 0 or box_h <= 0:
        return

    source = element["image"]
    scale = min(box_w / max(1, source.width), box_h / max(1, source.height))
    target_w = max(1, int(round(source.width * scale)))
    target_h = max(1, int(round(source.height * scale)))
    resized = source.resize((target_w, target_h), Image.LANCZOS)

    paste_x = x + max(0, (box_w - target_w) // 2)
    paste_y = y + max(0, (box_h - target_h) // 2)

    if soften:
        resized = _apply_soft_mask(resized)
    canvas.alpha_composite(resized, (paste_x, paste_y))
    placements.append(
        {
            "element": element["type"],
            "source_box": element["source_box"],
            "target_box": {
                "left": paste_x,
                "top": paste_y,
                "right": paste_x + target_w,
                "bottom": paste_y + target_h,
            },
        }
    )


def _apply_soft_mask(img):
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    inset_x = max(2, int(img.width * 0.05))
    inset_y = max(2, int(img.height * 0.03))
    draw.rounded_rectangle(
        (inset_x, inset_y, max(inset_x + 1, img.width - inset_x), max(inset_y + 1, img.height - inset_y)),
        radius=max(4, int(min(img.width, img.height) * 0.08)),
        fill=255,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(3, int(min(img.width, img.height) * 0.03))))
    softened = img.copy()
    alpha = softened.getchannel("A")
    softened.putalpha(ImageChops.multiply(alpha, mask))
    return softened


def _extract_foreground_crop(img):
    extracted = _try_rembg_extract(img)
    if extracted is not None:
        return extracted
    return _edge_key_extract(img)


def _try_rembg_extract(img):
    if importlib.util.find_spec("onnxruntime") is None:
        return None
    try:
        from rembg import remove as rembg_remove
    except Exception:
        return None

    try:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = rembg_remove(buf.getvalue())
        from PIL import Image

        extracted = Image.open(io.BytesIO(result)).convert("RGBA")
        alpha = extracted.getchannel("A")
        bbox = alpha.getbbox()
        if not bbox:
            return None
        coverage = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / max(1, extracted.width * extracted.height)
        if coverage < 0.06:
            return None
        return extracted
    except Exception:
        return None


def _edge_key_extract(img):
    from collections import deque
    from PIL import Image, ImageChops, ImageFilter

    rgba = img.convert("RGBA")
    w, h = rgba.size
    pixels = rgba.load()
    visited = [[False] * h for _ in range(w)]
    mask = Image.new("L", (w, h), 255)
    mask_px = mask.load()
    queue: deque[tuple[int, int]] = deque()

    border_samples = []
    step_x = max(1, w // 16)
    step_y = max(1, h // 16)
    for x in range(0, w, step_x):
        border_samples.append(pixels[x, 0][:3])
        border_samples.append(pixels[x, h - 1][:3])
    for y in range(0, h, step_y):
        border_samples.append(pixels[0, y][:3])
        border_samples.append(pixels[w - 1, y][:3])

    avg = tuple(sum(sample[idx] for sample in border_samples) / max(1, len(border_samples)) for idx in range(3))
    threshold = 58

    for x in range(w):
        queue.append((x, 0))
        queue.append((x, h - 1))
    for y in range(h):
        queue.append((0, y))
        queue.append((w - 1, y))

    while queue:
        x, y = queue.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or visited[x][y]:
            continue
        visited[x][y] = True
        r, g, b, a = pixels[x, y]
        if a == 0:
            mask_px[x, y] = 0
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                queue.append((nx, ny))
            continue
        dist = abs(r - avg[0]) + abs(g - avg[1]) + abs(b - avg[2])
        if dist <= threshold:
            mask_px[x, y] = 0
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                queue.append((nx, ny))

    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(2, int(min(w, h) * 0.025))))
    result = rgba.copy()
    result.putalpha(ImageChops.multiply(result.getchannel("A"), mask))
    return result


def _with_alpha(img, alpha: int):
    from PIL import Image

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    layer = img.copy()
    layer.putalpha(max(0, min(255, alpha)))
    return layer


def _first(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return items[0] if items else None


def _anchor_union(anchors: list[dict[str, Any]]) -> dict[str, int] | None:
    if not anchors:
        return None
    return {
        "x1": min(anchor["x1"] for anchor in anchors),
        "y1": min(anchor["y1"] for anchor in anchors),
        "x2": max(anchor["x2"] for anchor in anchors),
        "y2": max(anchor["y2"] for anchor in anchors),
    }


def _serialize_box(box: tuple[int, int, int, int]) -> dict[str, int]:
    return {"left": box[0], "top": box[1], "right": box[2], "bottom": box[3]}


def _is_ultra_wide_banner(target_w: int, target_h: int) -> bool:
    return target_h <= 100 or (target_w / max(1, target_h)) >= 4


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _clamp_pct(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _to_png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_FONT_CANDIDATES = [
    "arial.ttf",
    "Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()
