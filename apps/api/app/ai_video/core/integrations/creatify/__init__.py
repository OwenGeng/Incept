"""Creatify integration adapters.

Creatify is not OpenAI-compatible: it has catalog-defined schemas, a two-header
credential model, and asynchronous asset jobs.  Keep those semantics isolated
here so the rest of Linglong Lab continues to use its shared task contracts.
"""

from app.ai_video.core.integrations.creatify.asset_generator import CreatifyAssetGeneratorAdapter
from app.ai_video.core.integrations.creatify.text_to_speech import CreatifyTextToSpeechAdapter

__all__ = ["CreatifyAssetGeneratorAdapter", "CreatifyTextToSpeechAdapter"]
