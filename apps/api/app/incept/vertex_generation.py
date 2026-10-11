"""Shared Vertex AI helpers used by product modules.

This module deliberately contains no video-workbench state or workflow logic.
It keeps the existing Application Default Credentials based Vertex integration
available to the remaining products.
"""

from __future__ import annotations

from google import genai
from google.genai import types as genai_types

from app.incept.config import get_settings
from app.incept.models import Asset
from app.incept.store import _guess_content_type, read_asset_bytes


def _text_part(value: str, limit: int = 12000) -> genai_types.Part:
    return genai_types.Part(text=value[:limit])


def _extract_text_response(response) -> str:
    chunks: list[str] = []
    for candidate in response.candidates or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            text_value = getattr(part, "text", None)
            if isinstance(text_value, str) and text_value.strip():
                chunks.append(text_value.strip())
    return "\n".join(chunks).strip()


def _call_multimodal_text_model(
    *,
    prompt: str,
    parts: list[genai_types.Part],
    model_id: str | None = None,
    json_response: bool = False,
    response_json_schema: dict[str, object] | None = None,
    prompt_char_limit: int = 12000,
) -> str:
    """Call the configured Vertex text model through runtime ADC."""
    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )
    request: dict[str, object] = {
        "model": (model_id or settings.vertex_gemini_model).strip(),
        "contents": [genai_types.Content(role="user", parts=[_text_part(prompt, prompt_char_limit), *parts])],
    }
    if json_response:
        request["config"] = genai_types.GenerateContentConfig(
            response_mime_type="application/json", response_json_schema=response_json_schema,
        )
    response = client.models.generate_content(**request)
    text = _extract_text_response(response)
    if not text:
        raise RuntimeError("Gemini text analysis returned no text.")
    return text


def _text_model_asset_mime_type(asset: Asset) -> str:
    fallback_by_type = {
        "image": "image/png",
        "gif": "image/gif",
        "video": "video/mp4",
        "audio": "audio/mpeg",
        "playable": "text/html",
        "report": "text/plain",
    }
    fallback = fallback_by_type.get(asset.type, "application/octet-stream")
    expected_prefix = {
        "image": "image/",
        "gif": "image/",
        "video": "video/",
        "audio": "audio/",
    }.get(asset.type)
    for candidate in (asset.title, asset.gcs_uri, asset.preview_url):
        guessed = _guess_content_type(candidate or "", "")
        if guessed and (expected_prefix is None or guessed.startswith(expected_prefix)):
            return guessed
    return fallback


def _asset_part_for_text_model(asset: Asset) -> genai_types.Part:
    asset_bytes = read_asset_bytes(asset)
    if not asset_bytes:
        raise RuntimeError(f"Could not read bytes for asset {asset.id}")
    return genai_types.Part.from_bytes(data=asset_bytes, mime_type=_text_model_asset_mime_type(asset))
