import os
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import Response, APIRouter
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/kakao", tags=["kakao"])

W, H = 1029, 258
THUMB_X, THUMB_Y, THUMB_W, THUMB_H = 666, 36, 315, 186
APP_ICON_X, APP_ICON_Y, APP_ICON_SZ = 48, 50, 38
SUBTITLE_X, SUBTITLE_Y = 93, 79
SUBTITLE_ARROW_SIZE = 15.6
SUBTITLE_ARROW_X_PAD = 3
SUBTITLE_ARROW_Y = 75
MAIN_COPY_X, MAIN_COPY_Y = 46, 148
NOTICE_X, NOTICE_Y = 102, 195
ARROW_GLYPH = ""

SUBTITLE_COLOR = "#777777"
MAIN_COPY_COLOR = "#4C4C4C"
NOTICE_COLOR = "#777777"

DEFAULT_FONT_DIR = Path(__file__).parent.parent.parent.parent / "web/public/SpoqaHanSansNeo_all/SpoqaHanSansNeo_TTF_original"
DEFAULT_TEMPLATE_PATH = Path(__file__).parent.parent.parent.parent / "web/public/kakao-bizboard-template.png"


def _font_dir() -> Path:
    env = os.environ.get("KAKAO_FONT_DIR")
    return Path(env) if env else DEFAULT_FONT_DIR


def _template_path() -> Path:
    env = os.environ.get("KAKAO_TEMPLATE_PATH")
    return Path(env) if env else DEFAULT_TEMPLATE_PATH


def _load_font(weight: str, size: float) -> ImageFont.FreeTypeFont:
    name_map = {"regular": "Regular", "bold": "Bold", "medium": "Medium"}
    filename = f"SpoqaHanSansNeo-{name_map[weight]}.ttf"
    return ImageFont.truetype(str(_font_dir() / filename), size=int(size))


def _cover_crop(src: Image.Image, dst_w: int, dst_h: int) -> Image.Image:
    src_w, src_h = src.size
    src_r = src_w / src_h
    dst_r = dst_w / dst_h
    if src_r > dst_r:
        sw = round(src_h * dst_r)
        sx = round((src_w - sw) / 2)
        crop = src.crop((sx, 0, sx + sw, src_h))
    else:
        sh = round(src_w / dst_r)
        sy = round((src_h - sh) / 2)
        crop = src.crop((0, sy, src_w, sy + sh))
    return crop.resize((dst_w, dst_h), Image.LANCZOS)


_STATIC_ROOT = Path(__file__).parent.parent.parent / "static"


async def _fetch_image(client: httpx.AsyncClient, url: str) -> Image.Image:
    import base64 as _b64
    from fastapi import HTTPException
    if not url:
        raise HTTPException(status_code=400, detail="image url is empty")
    if url.startswith("/static/"):
        file_path = _STATIC_ROOT / url[len("/static/"):]
        return Image.open(file_path).convert("RGBA")
    if url.startswith("data:"):
        _, b64 = url.split(",", 1)
        return Image.open(BytesIO(_b64.b64decode(b64))).convert("RGBA")
    # Incept asset content path: /assets/{id}/content or /api/incept/assets/{id}/content
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
            return Image.open(BytesIO(data)).convert("RGBA")
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail=f"unsupported image url scheme: {url!r}")
    resp = await client.get(url)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content)).convert("RGBA")


class ComposeBizboardRequest(BaseModel):
    thumbnailUrl: str
    appIconUrl: str | None = None
    subtitle: str
    mainCopy: str
    gacha: bool = False


@router.post("/compose-bizboard")
async def compose_bizboard(body: ComposeBizboardRequest) -> Response:
    disclosure = "Moloco 광고 · 확률형 아이템 포함" if body.gacha else "Moloco 광고입니다."

    template = Image.open(_template_path()).convert("RGBA")
    canvas = template.copy()

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        thumb_src = await _fetch_image(client, body.thumbnailUrl)
        thumb = _cover_crop(thumb_src, THUMB_W, THUMB_H)

        # Apply template alpha mask to thumbnail region
        mask_alpha = template.getchannel("A").crop((THUMB_X, THUMB_Y, THUMB_X + THUMB_W, THUMB_Y + THUMB_H))
        thumb.putalpha(mask_alpha)
        canvas.paste(thumb, (THUMB_X, THUMB_Y), thumb)

        if body.appIconUrl:
            icon_src = await _fetch_image(client, body.appIconUrl)
            icon = icon_src.resize((APP_ICON_SZ, APP_ICON_SZ), Image.LANCZOS)
            canvas.paste(icon, (APP_ICON_X, APP_ICON_Y), icon)

    draw = ImageDraw.Draw(canvas)

    subtitle_body = body.subtitle.strip() + " "
    font_sub = _load_font("regular", 26)
    draw.text((SUBTITLE_X, SUBTITLE_Y), subtitle_body, font=font_sub, fill=SUBTITLE_COLOR, anchor="ls")

    # Advance width via getlength; falls back to getbbox width on older Pillow
    try:
        body_advance = font_sub.getlength(subtitle_body)
    except AttributeError:
        bb = font_sub.getbbox(subtitle_body)
        body_advance = bb[2] - bb[0]

    font_arrow = _load_font("regular", SUBTITLE_ARROW_SIZE)
    arrow_x = SUBTITLE_X + body_advance + SUBTITLE_ARROW_X_PAD
    draw.text((arrow_x, SUBTITLE_ARROW_Y), ARROW_GLYPH, font=font_arrow, fill=SUBTITLE_COLOR, anchor="ls")

    font_main = _load_font("bold", 48)
    draw.text((MAIN_COPY_X, MAIN_COPY_Y), body.mainCopy, font=font_main, fill=MAIN_COPY_COLOR, anchor="ls")

    font_notice = _load_font("regular", 24)
    draw.text((NOTICE_X, NOTICE_Y), disclosure, font=font_notice, fill=NOTICE_COLOR, anchor="ls")

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
