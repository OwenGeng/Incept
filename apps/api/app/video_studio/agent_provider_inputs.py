"""Translate prepared, bounded media into each text provider's image contract."""
from __future__ import annotations

import base64
from google.genai import types


def provider_content(prompt: str, parts: list[types.Part], provider_id: str) -> list[dict]:
    text_type = 'input_text' if provider_id == 'openai' else 'text'
    content = [{'type': text_type, 'text': prompt}]
    for part in parts:
        if part.text:
            content.append({'type': text_type, 'text': part.text})
        if part.file_data is not None:
            raise ValueError('私有媒体文件引用只能发送到已适配的 Gemini 通道。')
        blob = part.inline_data
        if blob is None:
            continue
        if blob.mime_type not in {'image/png', 'image/jpeg', 'image/webp', 'image/gif'} or not blob.data:
            raise ValueError('该通道只接收准备好的图片或视频采样帧；不能直接发送视频、音频或 PDF。')
        encoded = base64.b64encode(blob.data).decode('ascii')
        if provider_id == 'openai':
            content.append({'type':'input_image', 'image_url':f'data:{blob.mime_type};base64,{encoded}', 'detail':'auto'})
        else:
            content.append({'type':'image', 'source':{'type':'base64', 'media_type':blob.mime_type, 'data':encoded}})
    return content
