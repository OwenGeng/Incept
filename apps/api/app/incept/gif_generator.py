"""
Programmatic GIF generator for ad creatives — no AI models required.

Strategy:
  1. Take a finished static ad image (any size)
  2. Apply a very subtle full-frame breathing pulse
  3. Sweep a wide cinematic highlight across the full composition
  4. Output a looping animated GIF optimised for banner delivery

Supported sizes for GIF output (small enough to be practical):
  Banner: 320x50, 728x90, 1200x222, 640x100
  Medium / portrait: 300x250, 320x480
  Endcard: 360x640, 480x480, 640x360
  (Large landscape 1200x628 is excluded — GIF would be >5 MB)
"""

from __future__ import annotations

import io
import math
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

# ── GIF size limits ───────────────────────────────────────────────────────────

GIF_ALLOWED_SIZES: frozenset[str] = frozenset({
    "320x50", "728x90", "1200x222", "640x100",  # banner
    "300x250", "320x480",                        # medium / portrait
    "360x640", "480x480", "640x360",            # endcard
})

GIF_FRAMES = 16          # frames per loop
GIF_FRAME_MS = 80        # milliseconds per frame (≈12.5 fps)
GIF_PALETTE_COLORS = 128 # colours per frame (GIF max = 256; 128 keeps file small)
GIF_PULSE_AMPLITUDE = 0.035
GIF_SHINE_ALPHA = 56


# ── CTA position estimates (fallback when anchor detection unavailable) ───────

def _estimate_cta_bbox(img_w: int, img_h: int, target_size: str) -> tuple[int, int, int, int]:
    """
    Return an (x1, y1, x2, y2) estimate for where the CTA button lives,
    based purely on the size-family layout rules.

    Used only when no explicit CTA anchor metadata is available.
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
    """Convert an anchor dict to a pixel bounding box."""
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


def _estimate_background_color(region: Image.Image) -> tuple[int, int, int]:
    """Estimate CTA-region background from border pixels."""
    rgb = region.convert("RGB")
    w, h = rgb.size
    if w < 3 or h < 3:
        stat = list(rgb.getdata())
        if not stat:
            return (0, 0, 0)
        r = sum(px[0] for px in stat) // len(stat)
        g = sum(px[1] for px in stat) // len(stat)
        b = sum(px[2] for px in stat) // len(stat)
        return (r, g, b)

    border: list[tuple[int, int, int]] = []
    for x in range(w):
        border.append(rgb.getpixel((x, 0)))
        border.append(rgb.getpixel((x, h - 1)))
    for y in range(1, h - 1):
        border.append(rgb.getpixel((0, y)))
        border.append(rgb.getpixel((w - 1, y)))
    r = sum(px[0] for px in border) // len(border)
    g = sum(px[1] for px in border) // len(border)
    b = sum(px[2] for px in border) // len(border)
    return (r, g, b)


def _extract_cta_mask(region: Image.Image) -> Image.Image:
    """
    Build a tighter CTA foreground mask inside the estimated bbox.

    We approximate the button/text foreground by keeping pixels that differ
    enough from the border-estimated background color, then smooth/fatten the
    result into a usable animation mask.
    """
    rgb = region.convert("RGB")
    w, h = rgb.size
    bg_r, bg_g, bg_b = _estimate_background_color(rgb)

    mask = Image.new("L", (w, h), 0)
    pixels = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b = rgb.getpixel((x, y))
            diff = abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b)
            # Keep strong foreground contrast; this catches buttons/text/logos
            if diff > 72:
                pixels[x, y] = min(255, int((diff - 72) * 2.4))

    # Connect nearby glyph/button fragments and soften hard edges
    grown = mask.filter(ImageFilter.MaxFilter(size=5))
    softened = grown.filter(ImageFilter.GaussianBlur(radius=max(2, min(h // 10, 6))))
    tightened = softened.point(
        lambda v: 255 if v >= 170 else 160 if v >= 110 else 72 if v >= 70 else 0
    )

    # If extraction is too weak, fall back to a smaller rounded mask instead of
    # animating the entire bbox.
    if tightened.getbbox() is None:
        fallback = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(fallback)
        inset_x = max(2, w // 12)
        inset_y = max(2, h // 8)
        draw.rounded_rectangle(
            (inset_x, inset_y, max(inset_x + 1, w - inset_x - 1), max(inset_y + 1, h - inset_y - 1)),
            radius=max(4, min(h // 3, w // 6)),
            fill=255,
        )
        tightened = fallback.filter(ImageFilter.GaussianBlur(radius=max(2, min(h // 10, 6))))

    return tightened


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
    Create an animated GIF with a subtle full-frame cinematic sweep.

    Args:
        image_bytes:     Source PNG/JPEG image (the finished static ad).
        target_size:     e.g. "728x90". Reserved for future per-size tuning.
        anchors:         Optional upstream metadata. Currently unused here.
        frames:          Number of animation frames (default 16 ≈ 1.28 s loop).
        frame_ms:        Duration per frame in milliseconds.
        pulse_amplitude: Max full-frame brightness boost.

    Returns:
        Bytes of an animated GIF.
    """
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img_w, img_h = base.size

    # ── Generate frames ───────────────────────────────────────────────────────
    gif_frames: list[Image.Image] = []
    for i in range(frames):
        t = i / frames
        # Full-frame breathing pulse stays intentionally subtle.
        pulse = 0.5 + 0.5 * math.sin(t * math.pi * 2)
        brightness = 1.0 + pulse_amplitude * pulse
        frame = ImageEnhance.Brightness(base).enhance(brightness).convert("RGBA")

        # Wide, feathered diagonal sweep across the full image.
        shine_overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        shine_draw = ImageDraw.Draw(shine_overlay)
        band_width = max(img_w // 5, img_h // 2, 36)
        sweep_x = int((-band_width * 1.4) + (img_w + band_width * 2.4) * t)
        shine_draw.polygon(
            [
                (sweep_x, -img_h // 3),
                (sweep_x + band_width, -img_h // 3),
                (sweep_x + band_width + img_h // 2, img_h + img_h // 3),
                (sweep_x + img_h // 2, img_h + img_h // 3),
            ],
            fill=(255, 255, 255, int(GIF_SHINE_ALPHA * max(0.0, math.sin(t * math.pi)))),
        )
        shine_overlay = shine_overlay.filter(
            ImageFilter.GaussianBlur(radius=max(10, min(img_w, img_h) // 18))
        )
        frame = Image.alpha_composite(frame, shine_overlay)

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
