"""
Programmatic GIF generator for ad creatives — no AI models required.

Strategy:
  1. Take a finished static ad image (any size)
  2. Detect or estimate the CTA bounding box
  3. Apply a brightness-pulse animation to the CTA region across 16 frames
  4. Output a looping animated GIF optimised for banner delivery

Supported sizes for GIF output (small enough to be practical):
  Banner: 320x50, 728x90, 1200x222, 640x100
  Medium: 300x250
  Endcard: 360x640, 480x480, 640x360
  (Large landscape 1200x628 is excluded — GIF would be >5 MB)
"""

from __future__ import annotations

import io
import math
from typing import Any

from PIL import Image, ImageEnhance

# ── GIF size limits ───────────────────────────────────────────────────────────

GIF_ALLOWED_SIZES: frozenset[str] = frozenset({
    "320x50", "728x90", "1200x222", "640x100",  # banner
    "300x250",                                     # medium rectangle
    "360x640", "480x480", "640x360",               # endcard
})

GIF_FRAMES = 16          # frames per loop
GIF_FRAME_MS = 80        # milliseconds per frame (≈12.5 fps)
GIF_PALETTE_COLORS = 128 # colours per frame (GIF max = 256; 128 keeps file small)
GIF_PULSE_AMPLITUDE = 0.28  # CTA brightens by up to +28 %


# ── CTA position estimates (fallback when anchor detection unavailable) ───────

def _estimate_cta_bbox(img_w: int, img_h: int, target_size: str) -> tuple[int, int, int, int]:
    """
    Return an (x1, y1, x2, y2) estimate for where the CTA button lives,
    based purely on the size-family layout rules.

    Used only when detect_layout_anchors has no result.
    """
    ratio = img_w / max(img_h, 1)

    # ── Banner family (ultra-wide) → CTA on the RIGHT ────────────────────────
    if ratio >= 4.0 or img_h <= 140:
        x1 = int(img_w * 0.75)
        x2 = int(img_w * 0.97)
        pad = max(4, int(img_h * 0.12))
        return x1, pad, x2, img_h - pad

    # ── Endcard landscape (640x360) → CTA on the RIGHT ───────────────────────
    if target_size == "640x360":
        x1 = int(img_w * 0.68)
        x2 = int(img_w * 0.96)
        y1 = int(img_h * 0.30)
        y2 = int(img_h * 0.70)
        return x1, y1, x2, y2

    # ── Portrait / square / endcard portrait → CTA near BOTTOM ───────────────
    x1 = int(img_w * 0.15)
    x2 = int(img_w * 0.85)
    y1 = int(img_h * 0.80)
    y2 = int(img_h * 0.92)
    return x1, y1, x2, y2


def _anchor_to_bbox(
    anchor: dict[str, Any],
    img_w: int,
    img_h: int,
) -> tuple[int, int, int, int] | None:
    """Convert a detect_layout_anchors anchor dict to pixel bbox."""
    bbox = anchor.get("bbox") or {}
    # Anchors may use percentage-based or pixel-based coords
    if isinstance(bbox, dict):
        x = bbox.get("x", 0)
        y = bbox.get("y", 0)
        w = bbox.get("w", 0)
        h = bbox.get("h", 0)
        # If values are fractions (0–1), convert to pixels
        if 0 < x <= 1.0 and 0 < y <= 1.0:
            x1 = int(x * img_w)
            y1 = int(y * img_h)
            x2 = int((x + w) * img_w)
            y2 = int((y + h) * img_h)
        else:
            x1, y1, x2, y2 = int(x), int(y), int(x + w), int(y + h)
        if x2 > x1 and y2 > y1:
            return x1, y1, x2, y2
    return None


# ── Core GIF generation ───────────────────────────────────────────────────────

def generate_cta_pulse_gif(
    image_bytes: bytes,
    target_size: str,
    anchors: list[dict[str, Any]] | None = None,
    frames: int = GIF_FRAMES,
    frame_ms: int = GIF_FRAME_MS,
    pulse_amplitude: float = GIF_PULSE_AMPLITUDE,
) -> bytes:
    """
    Create an animated GIF where the CTA button pulses with a brightness effect.

    Args:
        image_bytes:     Source PNG/JPEG image (the finished static ad).
        target_size:     e.g. "728x90" — used for CTA position estimation.
        anchors:         Optional list of anchor dicts from detect_layout_anchors.
                         If a CTA anchor is found its bbox is used; otherwise
                         the position is estimated from the size family.
        frames:          Number of animation frames (default 16 ≈ 1.28 s loop).
        frame_ms:        Duration per frame in milliseconds.
        pulse_amplitude: Max brightness boost (0.28 → peaks at ×1.28 original).

    Returns:
        Bytes of an animated GIF.
    """
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img_w, img_h = base.size

    # ── Find CTA bbox ─────────────────────────────────────────────────────────
    cta_bbox: tuple[int, int, int, int] | None = None
    for anchor in (anchors or []):
        role = str(anchor.get("type") or anchor.get("role") or "").lower()
        if "cta" in role or "button" in role or "play" in role:
            cta_bbox = _anchor_to_bbox(anchor, img_w, img_h)
            if cta_bbox:
                break

    if cta_bbox is None:
        cta_bbox = _estimate_cta_bbox(img_w, img_h, target_size)

    x1, y1, x2, y2 = cta_bbox
    # Clamp to image bounds
    x1 = max(0, min(x1, img_w - 2))
    y1 = max(0, min(y1, img_h - 2))
    x2 = max(x1 + 2, min(x2, img_w))
    y2 = max(y1 + 2, min(y2, img_h))

    # ── Generate frames ───────────────────────────────────────────────────────
    gif_frames: list[Image.Image] = []
    for i in range(frames):
        t = i / frames
        # Sine-wave brightness pulse: smooth 0 → peak → 0 per loop
        brightness = 1.0 + pulse_amplitude * math.sin(t * math.pi * 2)

        frame = base.copy()
        cta_region = frame.crop((x1, y1, x2, y2)).convert("RGB")
        brightened = ImageEnhance.Brightness(cta_region).enhance(brightness)
        frame.paste(brightened.convert("RGBA"), (x1, y1))

        # Convert to palette mode for GIF (RGBA → RGB → palette)
        gif_frames.append(
            frame.convert("RGB").quantize(
                colors=GIF_PALETTE_COLORS,
                method=Image.Quantize.MEDIANCUT,
                dither=Image.Dither.FLOYDSTEINBERG,
            )
        )

    # ── Save as animated GIF ──────────────────────────────────────────────────
    buf = io.BytesIO()
    gif_frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=gif_frames[1:],
        loop=0,            # loop forever
        duration=frame_ms,
        optimize=True,
    )
    return buf.getvalue()


def is_gif_allowed_for_size(target_size: str) -> bool:
    """Return True if GIF generation is supported for this ad size."""
    return target_size in GIF_ALLOWED_SIZES
