from __future__ import annotations

from app.ai_video.models.llm import ModelCategoryKey
from app.ai_video.services.llm.provider_registry import ProviderSpec, register_many


def bootstrap_builtin_providers() -> None:
    register_many(
        [
            ProviderSpec(
                key="openai",
                display_name="OpenAI",
                aliases=("openai",),
                supported_categories=(
                    ModelCategoryKey.text,
                    ModelCategoryKey.image,
                    ModelCategoryKey.video,
                    ModelCategoryKey.speech,
                ),
                default_base_url="https://api.openai.com/v1",
            ),
            ProviderSpec(
                key="aliyun_bailian",
                display_name="阿里百炼",
                aliases=("阿里百炼", "aliyun", "bailian", "dashscope"),
                supported_categories=(ModelCategoryKey.text,),
                default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                is_listed=False,
            ),
            # The connector remains registered for backwards-compatible data
            # and a future explicit re-enable, but it is not offered to AI
            # Video users while OpenAI and Vertex are the supported choices.
            ProviderSpec(
                key="creatify",
                display_name="Creatify",
                aliases=("creatify",),
                supported_categories=(ModelCategoryKey.image, ModelCategoryKey.video, ModelCategoryKey.speech),
                default_base_url="https://api.creatify.ai/api",
                requires_api_key=True,
                requires_api_secret=True,
                is_listed=False,
            ),
            ProviderSpec(
                key="vertex",
                display_name="Google Vertex AI",
                aliases=("vertex", "vertex ai", "google vertex", "google vertex ai"),
                supported_categories=(
                    ModelCategoryKey.text,
                    ModelCategoryKey.image,
                    ModelCategoryKey.video,
                    ModelCategoryKey.music,
                ),
                # Vertex uses ADC, not a hand-written OpenAI-compatible base URL.
                default_base_url=None,
                requires_api_key=False,
            ),
        ]
    )
