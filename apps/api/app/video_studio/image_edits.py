"""Masked image edits: existing configured model plus lossless outside-mask compositing."""

from __future__ import annotations

import base64
import asyncio
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.incept.config import get_settings
from .store import safe_asset_path
from .vertex_media import ImageGenerationInput, ProviderConfig, VertexImageApiAdapter
from .workspace_documents import write_document

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_DIMENSION = 8192


class MaskedEditRequest(BaseModel):
    directory: str
    sourcePath: str = Field(min_length=1, max_length=4096)
    maskPath: str = Field(min_length=1, max_length=4096)
    prompt: str = Field(min_length=1, max_length=3000)
    providerId: str
    modelId: str
    outputDirectory: str | None = Field(default=None, max_length=200)


def _decode_image(payload: bytes) -> Image.Image:
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise ValueError('图片不能为空且不能超过 25 MB')
    try:
        with Image.open(BytesIO(payload)) as image:
            width, height = image.size
            if width < 1 or height < 1 or max(width, height) > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
                raise ValueError('图片不能超过 1600 万像素或 8192 像素边长')
            if image.is_animated:
                raise ValueError('请先将动态图转换为静态图片')
            return ImageOps.exif_transpose(image).convert('RGBA')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError('无法读取图片，请使用有效的静态图片') from error


def _image_file(root: Path, path: str) -> Image.Image:
    target = safe_asset_path(root, path)
    if not target.is_file():
        raise FileNotFoundError(path)
    if target.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError('图片不能超过 25 MB')
    return _decode_image(target.read_bytes())


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def _prepare_images(root: Path, source_path: str, mask_path: str) -> tuple[Image.Image, Image.Image, list[str]]:
    original = _image_file(root, source_path)
    mask_image = _image_file(root, mask_path)
    if original.size != mask_image.size:
        raise ValueError('选区尺寸必须与原图一致')
    mask = ImageChops.multiply(mask_image.convert('L'), mask_image.getchannel('A')).point(lambda value: 255 if value >= 128 else 0)
    if not mask.getbbox():
        raise ValueError('请先涂抹需要修改的区域')
    references = [f'data:image/png;base64,{base64.b64encode(_png(image)).decode()}' for image in [original, mask]]
    return original, mask, references


def _save_composite(target: Path, encoded: str, original: Image.Image, mask: Image.Image) -> None:
    generated = _decode_image(base64.b64decode(encoded, validate=True))
    if generated.size != original.size:
        generated = generated.resize(original.size, Image.Resampling.LANCZOS)
    write_document(target, _png(Image.composite(generated, original, mask)), exclusive=True)


async def masked_image_edit(root: Path, body: MaskedEditRequest) -> dict[str, str]:
    settings = get_settings()
    if body.providerId != 'google-vertex-ai' or body.modelId != settings.vertex_gemini_image_model:
        raise ValueError('局部重绘仅支持当前部署启用的 Vertex 图片模型')
    if not body.prompt.strip():
        raise ValueError('请输入局部重绘提示词')
    directory = body.outputDirectory or f'assets/{uuid.uuid4().hex}'
    parts = directory.split('/')
    if len(parts) != 2 or parts[0] != 'assets' or not parts[1] or parts[1] in {'.', '..'} or any(character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for character in parts[1]):
        raise ValueError('重绘输出必须是新节点的 assets/<nodeId> 目录')
    output_path = f'{directory}/inpaint-{uuid.uuid4().hex}.png'
    target = safe_asset_path(root, output_path)
    original, mask, references = await asyncio.to_thread(_prepare_images, root, body.sourcePath, body.maskPath)
    result = await VertexImageApiAdapter().generate(
        cfg=ProviderConfig(provider='vertex', api_key='', project_id=settings.gcp_project_id, location=settings.gcp_location),
        inp=ImageGenerationInput(model=body.modelId, prompt=f'The first image is the original. The second is a selection mask: white marks the editable region, black must stay unchanged. Return an edited version of the FIRST image with the same composition and aspect ratio, not the mask. Only change the white selected region as follows: {body.prompt.strip()}', images=references, response_format='b64_json'),
        timeout_s=120.0,
    )
    if not result.images or not result.images[0].b64_json:
        raise RuntimeError('图片模型没有返回可用图片')
    await asyncio.to_thread(_save_composite, target, result.images[0].b64_json, original, mask)
    return {'path': output_path, 'mimeType': 'image/png', 'mediaType': 'image'}
