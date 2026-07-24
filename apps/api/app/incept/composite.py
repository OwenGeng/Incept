"""Minimal image processing helpers used by the active Studio backend."""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_POSITION_MAP = {
    "top-left": (0.03, 0.03),
    "top-center": (0.5, 0.03),
    "top-right": (0.97, 0.03),
    "center-left": (0.03, 0.5),
    "center": (0.5, 0.5),
    "center-right": (0.97, 0.5),
    "bottom-left": (0.03, 0.97),
    "bottom-center": (0.5, 0.97),
    "bottom-right": (0.97, 0.97),
}
_LOGO_SIZE_RATIO = 0.22
_FONT_CANDIDATES = [
    "arial.ttf",
    "Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_KAKAO_GACHA_DISCLOSURE = "확률형 아이템 포함"


def _load_kakao_font(size: int):
    """Load the bundled Spoqa font so Korean disclosure text renders reliably."""
    from PIL import ImageFont

    font_dir = os.getenv("KAKAO_FONT_DIR")
    candidates = []
    if font_dir:
        candidates.append(Path(font_dir) / "SpoqaHanSansNeo-Regular.ttf")
    candidates.append(
        Path(__file__).resolve().parents[3]
        / "web/public/SpoqaHanSansNeo_all/SpoqaHanSansNeo_TTF_original/SpoqaHanSansNeo-Regular.ttf"
    )
    for path in candidates:
        try:
            return ImageFont.truetype(str(path), size)
        except (IOError, OSError):
            continue
    return _load_font(size)


def create_outpaint_inputs(
    image_bytes: bytes,
    direction: str,
    ratio: float = 0.3,
) -> tuple[bytes, bytes]:
    """Create an expanded canvas plus preservation mask for outpainting."""
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size

    has_x = direction in {"left", "right", "all"}
    has_y = direction in {"top", "bottom", "all"}
    pad_x = int(w * ratio) if has_x else 0
    pad_y = int(h * ratio) if has_y else 0

    left = pad_x if direction in {"left", "all"} else 0
    right = pad_x if direction in {"right", "all"} else 0
    top = pad_y if direction in {"top", "all"} else 0
    bottom = pad_y if direction in {"bottom", "all"} else 0

    new_w, new_h = w + left + right, h + top + bottom

    canvas = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
    canvas.paste(img, (left, top))

    mask = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)
    draw.rectangle([left, top, left + w - 1, top + h - 1], fill=(255, 255, 255, 255))

    return _to_png(canvas), _to_png(mask)


def remove_background(image_bytes: bytes) -> tuple[bytes, bool]:
    """Try `rembg`, otherwise return the original bytes unchanged."""
    try:
        from rembg import remove as rembg_remove

        result = rembg_remove(image_bytes)
        logger.info("Background removed with rembg (%d bytes)", len(result))
        return result, True
    except Exception as exc:
        logger.warning("rembg unavailable or failed (%s)", exc)
        return image_bytes, False


def add_text_overlay(
    image_bytes: bytes,
    text: str,
    position: str = "bottom",
    font_size_ratio: float = 0.06,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_opacity: int = 160,
) -> bytes:
    """Overlay readable text using Pillow."""
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    font_size = max(14, int(h * font_size_ratio))
    font = _load_font(font_size)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad = int(font_size * 0.4)
    strip_h = text_h + pad * 2

    strip_y = (
        0
        if position == "top"
        else (h - strip_h) // 2 if position == "center" else h - strip_h
    )

    draw.rectangle([0, strip_y, w, strip_y + strip_h], fill=(0, 0, 0, bg_opacity))
    draw.text(((w - text_w) // 2, strip_y + pad), text, font=font, fill=(*color, 255))

    return _to_png(Image.alpha_composite(img, overlay))


def add_kakao_gacha_disclosure(image_bytes: bytes) -> bytes:
    """Add the required gacha disclosure as unobtrusive text on a Kakao source creative."""
    from PIL import Image, ImageDraw

    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = image.size
    font_size = max(18, round(height * 0.035))
    font = _load_kakao_font(font_size)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    text_box = draw.textbbox((0, 0), _KAKAO_GACHA_DISCLOSURE, font=font)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    margin = max(20, round(width * 0.025))
    left = margin
    top = height - margin - text_height
    draw.text(
        (left, top - text_box[1]),
        _KAKAO_GACHA_DISCLOSURE,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=max(1, round(font_size * 0.08)),
        stroke_fill=(0, 0, 0, 190),
    )
    return _to_png(Image.alpha_composite(image, overlay))


def composite_logo(
    base_bytes: bytes,
    logo_bytes: bytes,
    position: str = "top-left",
    size_ratio: float = _LOGO_SIZE_RATIO,
) -> bytes:
    """Composite a logo onto a base image without redrawing it."""
    from PIL import Image

    base = Image.open(io.BytesIO(base_bytes)).convert("RGBA")
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    bw, bh = base.size

    logo_w = max(16, int(bw * size_ratio))
    logo_h = max(16, int(logo.height * logo_w / logo.width))
    logo_resized = logo.resize((logo_w, logo_h), Image.LANCZOS)

    pos_key = position.strip().lower().replace(" ", "-")
    if "," in pos_key:
        try:
            rx, ry = [float(v) for v in pos_key.split(",", 1)]
        except ValueError:
            rx, ry = 0.03, 0.03
    else:
        rx, ry = _POSITION_MAP.get(pos_key, _POSITION_MAP["top-left"])

    px = int(bw * rx) if rx < 0.5 else int(bw * rx) - logo_w
    py = int(bh * ry) if ry < 0.5 else int(bh * ry) - logo_h
    px = max(0, min(bw - logo_w, px))
    py = max(0, min(bh - logo_h, py))

    canvas = base.copy()
    canvas.alpha_composite(logo_resized, dest=(px, py))
    return _to_png(canvas)


def resize_to_exact(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """Resize with aspect-ratio-preserving cover crop to exact dimensions."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    iw, ih = img.size
    target_ratio = target_w / target_h
    source_ratio = iw / ih

    if abs(source_ratio - target_ratio) < 0.02:
        result = img.resize((target_w, target_h), Image.LANCZOS)
    elif source_ratio > target_ratio:
        scale_h = target_h
        scale_w = int(iw * target_h / ih)
        scaled = img.resize((scale_w, scale_h), Image.LANCZOS)
        left = (scale_w - target_w) // 2
        result = scaled.crop((left, 0, left + target_w, target_h))
    else:
        scale_w = target_w
        scale_h = int(ih * target_w / iw)
        scaled = img.resize((scale_w, scale_h), Image.LANCZOS)
        top = (scale_h - target_h) // 2
        result = scaled.crop((0, top, target_w, top + target_h))

    return _to_png(result)


def split_728x180_into_two_728x90(image_bytes: bytes) -> tuple[bytes, bytes]:
    """Resize/crop to 728x180 first, then split into top and bottom 728x90 halves."""
    from PIL import Image

    prepared = resize_to_exact(image_bytes, 728, 180)
    img = Image.open(io.BytesIO(prepared)).convert("RGBA")
    top = img.crop((0, 0, 728, 90))
    bottom = img.crop((0, 90, 728, 180))
    return _to_png(top), _to_png(bottom)


def get_openai_size(w: int, h: int, model: str) -> str:
    """Map requested dimensions to an OpenAI-supported image size."""
    if model in {"dall-e-2", "dall-e-3"}:
        return "1024x1024"

    ratio = w / h
    if ratio >= 1.4:
        return "1536x1024"
    if ratio <= 0.72:
        return "1024x1536"
    return "1024x1024"


def _to_png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _load_font(size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()
