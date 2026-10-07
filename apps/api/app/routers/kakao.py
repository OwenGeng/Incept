"""Kakao Bizboard composer, 960x300 specification (effective Oct 2026).

Layout values mirror the Moloco MCP generator
(moloco/cloud-appbase go/appbase/handlers/kakao_bizboard_v2.go) so LinglongLab
output matches what the Ads Portal generator and Kakao review expect.
"""

import base64
import binascii
import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.services.auth import require_internal_key

router = APIRouter(
    prefix="/api/v1/kakao",
    tags=["kakao"],
    dependencies=[Depends(require_internal_key)],
)

W, H = 960, 300
MAX_OUTPUT_BYTES = 300_000
MAX_SOURCE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_IMAGE_PIXELS = 40_000_000
TEXT_RIGHT = 569
MIN_COPY_WIDTH = 240
THUMBNAIL_RECT = (601, 39, 921, 261)  # 320x222
THUMBNAIL_RADIUS = 18
OBJECT_X, OBJECT_WIDTH, OBJECT_MIN_WIDTH = 603, 314, 219
ARROW_GAP, ARROW_W, ARROW_H = 9, 10, 18

MAIN_COPY_COLOR = "#191919"
SUB_COPY_COLOR = "#696969"
ADDITIONAL_INFO_COLOR = "#949494"

MAIN_COPY_SIZE, SUB_COPY_SIZE, APP_COPY_SIZE, ADDITIONAL_INFO_SIZE = 46, 38, 29, 22

GACHA_INFO = "확률형 아이템 포함"
APP_TERMS = ("앱", "app", "App", "APP")
BANNED_PATTERN = re.compile(r"\^\^|:D|ð|☞|☑|♨|[\U0001F300-\U0001FAFF☀-➿]")
# The UI pre-fills "APP_NAME ..." defaults; never let one reach Kakao review.
PLACEHOLDER_PATTERN = re.compile(r"APP_NAME", re.IGNORECASE)

Template = Literal[
    "APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL",
    "APP_DOWNLOAD_TWO_LINE_COPY_THUMBNAIL",
    "TWO_LINE_COPY_THUMBNAIL",
    "APP_DOWNLOAD_ONE_LINE_COPY_OBJECT",
]
OBJECT_TEMPLATES = {"APP_DOWNLOAD_ONE_LINE_COPY_OBJECT"}


@dataclass(frozen=True)
class TextSlot:
    x: int
    baseline: int


@dataclass(frozen=True)
class Layout:
    main: TextSlot
    info: TextSlot
    sub: TextSlot | None = None
    app_icon: tuple[int, int, int, int] | None = None
    app_copy: TextSlot | None = None
    app_copy_top: int = 0


def _app_layout(app_top: int, main_baseline: int, sub_baseline: int | None, info_baseline: int) -> Layout:
    return Layout(
        app_icon=(45, app_top - 5, 83, app_top + 33),
        app_copy=TextSlot(91, app_top + 25),
        app_copy_top=app_top,
        main=TextSlot(43, main_baseline),
        sub=TextSlot(43, sub_baseline) if sub_baseline else None,
        info=TextSlot(45, info_baseline),
    )


# Keyed by (template, has_additional_info). "With info" matches the MCP
# generator; "without info" follows the vertically centred "기본" guide in
# Kakao's Oct 2026 PSD, which the generator does not implement.
LAYOUTS: dict[str, dict[bool, Layout]] = {
    "APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL": {
        True: _app_layout(76, 172, None, 221),
        False: _app_layout(96, 195, None, 0),
    },
    "APP_DOWNLOAD_TWO_LINE_COPY_THUMBNAIL": {
        True: _app_layout(54, 149, 203, 246),
        False: _app_layout(67, 166, 226, 0),
    },
    "TWO_LINE_COPY_THUMBNAIL": {
        True: Layout(main=TextSlot(43, 118), sub=TextSlot(43, 174), info=TextSlot(45, 218)),
        False: Layout(main=TextSlot(43, 137), sub=TextSlot(43, 197), info=TextSlot(45, 0)),
    },
}
# Object type shares the App Promo one-line copy guides (same boxes in Kakao's Object PSD).
LAYOUTS["APP_DOWNLOAD_ONE_LINE_COPY_OBJECT"] = LAYOUTS["APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL"]


def layout_for(template: str, info: str) -> Layout:
    return LAYOUTS[template][bool(info)]

_API_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FONT_DIR = _API_ROOT.parent / "web/public/Pretendard"
_STATIC_ROOT = _API_ROOT / "static"


def _load_font(weight: Literal["Regular", "Bold"], size: int) -> ImageFont.FreeTypeFont:
    font_dir = Path(os.environ.get("KAKAO_FONT_DIR") or _DEFAULT_FONT_DIR)
    for ext in ("otf", "ttf"):
        path = font_dir / f"Pretendard-{weight}.{ext}"
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    raise HTTPException(status_code=500, detail=f"Pretendard-{weight} font not found in {font_dir}")


def build_additional_info(additional_info: str, gacha: bool) -> str:
    info = _normalize(additional_info)
    if gacha and GACHA_INFO not in info:
        return f"{GACHA_INFO} · {info}" if info else GACHA_INFO
    return info


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


class ComposeBizboardRequest(BaseModel):
    template: Template = "APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL"
    thumbnailUrl: str = Field(max_length=14_000_000)  # data URLs include base64 overhead
    appIconUrl: str | None = Field(default=None, max_length=14_000_000)
    appCopy: str = Field(default="", max_length=200)
    mainCopy: str = Field(max_length=200)
    subCopy: str = Field(default="", max_length=200)
    additionalInfo: str = Field(default="", max_length=500)
    gacha: bool = False


def validate_copy(body: ComposeBizboardRequest) -> list[str]:
    """Kakao copy rules from the Oct 2026 Bizboard guideline, sections 2.1-2.4."""
    errors: list[str] = []
    main, sub, app = _normalize(body.mainCopy), _normalize(body.subCopy), _normalize(body.appCopy)
    info = build_additional_info(body.additionalInfo, body.gacha)
    layout = layout_for(body.template, info)
    max_width = TEXT_RIGHT - layout.main.x

    def width(text: str, weight: Literal["Regular", "Bold"], size: int) -> float:
        return _load_font(weight, size).getlength(text) if text else 0

    main_w = width(main, "Bold", MAIN_COPY_SIZE)
    if not main:
        errors.append("Main copy is required.")
    elif main_w > max_width:
        errors.append(f"Main copy is too long ({round(main_w)}px, max {max_width}px).")

    if layout.sub:
        sub_w = width(sub, "Regular", SUB_COPY_SIZE)
        if not sub:
            errors.append("Sub copy is required for this template.")
        elif sub_w > max_width:
            errors.append(f"Sub copy is too long ({round(sub_w)}px, max {max_width}px).")
        if main and sub and main == sub:
            errors.append("Main copy and sub copy cannot be the same.")
        if main and sub and max(main_w, sub_w) < MIN_COPY_WIDTH:
            errors.append(f"Main copy or sub copy must be at least {MIN_COPY_WIDTH}px wide.")
    elif main and main_w < MIN_COPY_WIDTH:
        errors.append(f"Main copy is too short ({round(main_w)}px, min {MIN_COPY_WIDTH}px).")

    if layout.app_copy:
        if not body.appIconUrl:
            errors.append("App icon is required for this template.")
        if not app:
            errors.append("App download copy is required for this template.")
        elif not any(term in app for term in APP_TERMS):
            errors.append('App download copy must include "앱" or "App".')
        elif layout.app_copy.x + width(app, "Regular", APP_COPY_SIZE) + ARROW_GAP + ARROW_W > TEXT_RIGHT:
            errors.append("App download copy is too long for the fixed Bizboard slot.")

    if info and width(info, "Regular", ADDITIONAL_INFO_SIZE) > TEXT_RIGHT - layout.info.x:
        errors.append("Additional info is too long for the fixed Bizboard slot.")

    for label, text in (("Main copy", main), ("Sub copy", sub), ("App download copy", app), ("Additional info", info)):
        if text and BANNED_PATTERN.search(text):
            errors.append(f"{label} contains emoji or special characters Kakao does not allow.")
        if text and PLACEHOLDER_PATTERN.search(text):
            errors.append(f"{label} still contains the APP_NAME placeholder. Replace it with the real app name.")
    return errors


def _open_source_image(data: bytes) -> Image.Image:
    if len(data) > MAX_SOURCE_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="source image is too large")
    try:
        image = Image.open(BytesIO(data))
        if image.width * image.height > MAX_SOURCE_IMAGE_PIXELS:
            raise HTTPException(status_code=413, detail="source image has too many pixels")
        image.load()
        return image.convert("RGBA")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=400, detail="source data is not a valid image") from error


def validate_remote_image_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("remote images must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("remote image URLs must not contain credentials")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or 443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise ValueError("remote image hostname could not be resolved") from error
    if not addresses:
        raise ValueError("remote image hostname did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("remote image hostname resolves to a private or reserved address")
    return url


def _static_image_path(url: str) -> Path:
    root = _STATIC_ROOT.resolve()
    candidate = (root / url[len("/static/"):]).resolve()
    if candidate == root or root not in candidate.parents:
        raise HTTPException(status_code=400, detail="invalid static image path")
    return candidate


async def _fetch_image(client: httpx.AsyncClient, url: str) -> Image.Image:
    if not url:
        raise HTTPException(status_code=400, detail="image url is empty")
    if url.startswith("/static/"):
        return _open_source_image(_static_image_path(url).read_bytes())
    if url.startswith("data:"):
        try:
            _, encoded = url.split(",", 1)
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise HTTPException(status_code=400, detail="invalid image data URL") from error
        return _open_source_image(data)
    for prefix in ("/api/incept/assets/", "/assets/"):
        if url.startswith(prefix) and url.endswith("/content"):
            from app.incept.store import ASSETS, SOURCE_ASSETS, read_asset_bytes

            asset_id = url[len(prefix):-len("/content")]
            asset = ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)
            if asset is None:
                raise HTTPException(status_code=404, detail=f"asset not found: {asset_id}")
            data = read_asset_bytes(asset)
            if data is None:
                raise HTTPException(status_code=404, detail=f"asset content not readable: {asset_id}")
            return _open_source_image(data)
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail=f"unsupported image url scheme: {url!r}")
    try:
        safe_url = validate_remote_image_url(url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    async with client.stream("GET", safe_url) as response:
        if response.is_redirect:
            raise HTTPException(status_code=400, detail="remote image redirect is not allowed")
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError as error:
                raise HTTPException(status_code=400, detail="remote image has an invalid content length") from error
            if declared_size < 0:
                raise HTTPException(status_code=400, detail="remote image has an invalid content length")
            if declared_size > MAX_SOURCE_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="remote image is too large")
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > MAX_SOURCE_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="remote image is too large")
    return _open_source_image(bytes(data))


def _cover(src: Image.Image, dst_w: int, dst_h: int) -> Image.Image:
    src_w, src_h = src.size
    if src_w / src_h > dst_w / dst_h:
        crop_w = round(src_h * dst_w / dst_h)
        left = round((src_w - crop_w) / 2)
        box = (left, 0, left + crop_w, src_h)
    else:
        crop_h = round(src_w * dst_h / dst_w)
        top = round((src_h - crop_h) / 2)
        box = (0, top, src_w, top + crop_h)
    return src.crop(box).resize((dst_w, dst_h), Image.LANCZOS)


def _rounded_thumbnail(src: Image.Image) -> Image.Image:
    left, top, right, bottom = THUMBNAIL_RECT
    size = (right - left, bottom - top)
    # Kakao rejects transparent thumbnails, so flatten onto white first.
    flat = Image.new("RGBA", src.size, (255, 255, 255, 255))
    flat.alpha_composite(src)
    thumb = _cover(flat, *size)
    scale = 4
    mask = Image.new("L", (size[0] * scale, size[1] * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] * scale - 1, size[1] * scale - 1), radius=THUMBNAIL_RADIUS * scale, fill=255
    )
    thumb.putalpha(mask.resize(size, Image.LANCZOS))
    return thumb


def _object_image(src: Image.Image) -> tuple[Image.Image, int]:
    """Place a background-free object per Kakao's Object guide.

    Trimmed to its visible pixels, scaled to 314px wide; vertically centred when
    at most 300px tall, otherwise centre-cropped (matches the MCP generator).
    """
    alpha = src.getchannel("A")
    if alpha.getextrema()[0] > 250:
        raise HTTPException(
            status_code=422,
            detail=["Object image must have a transparent background. Remove the background or upload a transparent PNG."],
        )
    bbox = alpha.point(lambda a: 255 if a > 10 else 0).getbbox()
    if bbox is None:
        raise HTTPException(status_code=422, detail=["Object image is fully transparent."])
    obj = src.crop(bbox)
    if obj.width < OBJECT_MIN_WIDTH:
        raise HTTPException(
            status_code=422,
            detail=[f"Object is {obj.width}px wide after trimming; Kakao needs at least {OBJECT_MIN_WIDTH}px."],
        )
    height = round(obj.height * OBJECT_WIDTH / obj.width)
    obj = obj.resize((OBJECT_WIDTH, height), Image.LANCZOS)
    if height <= H:
        return obj, (H - height) // 2
    top = (height - H) // 2
    return obj.crop((0, top, OBJECT_WIDTH, top + H)), 0


def _draw_arrow(draw: ImageDraw.ImageDraw, x: float, top: int) -> None:
    # Chevron within the 10x18 PSD bounds used by the MCP generator.
    draw.line(
        [(x + 1.5, top + 1.5), (x + ARROW_W - 1.5, top + ARROW_H / 2), (x + 1.5, top + ARROW_H - 1.5)],
        fill=SUB_COPY_COLOR,
        width=2,
        joint="curve",
    )


@router.post("/compose-bizboard")
async def compose_bizboard(body: ComposeBizboardRequest) -> Response:
    errors = validate_copy(body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    info = build_additional_info(body.additionalInfo, body.gacha)
    layout = layout_for(body.template, info)

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    async with httpx.AsyncClient(follow_redirects=False, timeout=30) as client:
        image = await _fetch_image(client, body.thumbnailUrl)
        if body.template in OBJECT_TEMPLATES:
            obj, top = _object_image(image)
            canvas.alpha_composite(obj, (OBJECT_X, top))
        else:
            canvas.alpha_composite(_rounded_thumbnail(image), THUMBNAIL_RECT[:2])
        if layout.app_icon and body.appIconUrl:
            l, t, r, b = layout.app_icon
            icon = _cover(await _fetch_image(client, body.appIconUrl), r - l, b - t)
            canvas.alpha_composite(icon, (l, t))

    draw = ImageDraw.Draw(canvas)
    if layout.app_copy:
        app_copy = _normalize(body.appCopy)
        font = _load_font("Regular", APP_COPY_SIZE)
        draw.text((layout.app_copy.x, layout.app_copy.baseline), app_copy, font=font, fill=SUB_COPY_COLOR, anchor="ls")
        _draw_arrow(draw, layout.app_copy.x + font.getlength(app_copy) + ARROW_GAP, layout.app_copy_top + 5)

    draw.text(
        (layout.main.x, layout.main.baseline), _normalize(body.mainCopy),
        font=_load_font("Bold", MAIN_COPY_SIZE), fill=MAIN_COPY_COLOR, anchor="ls",
    )
    if layout.sub:
        draw.text(
            (layout.sub.x, layout.sub.baseline), _normalize(body.subCopy),
            font=_load_font("Regular", SUB_COPY_SIZE), fill=SUB_COPY_COLOR, anchor="ls",
        )
    if info:
        draw.text(
            (layout.info.x, layout.info.baseline), info,
            font=_load_font("Regular", ADDITIONAL_INFO_SIZE), fill=ADDITIONAL_INFO_COLOR, anchor="ls",
        )

    buf = BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    if buf.tell() > MAX_OUTPUT_BYTES:
        raise HTTPException(
            status_code=422,
            detail=[f"Composed Bizboard is {buf.tell() // 1000}KB; Kakao allows at most 300KB. Use a simpler thumbnail."],
        )
    return Response(content=buf.getvalue(), media_type="image/png")
