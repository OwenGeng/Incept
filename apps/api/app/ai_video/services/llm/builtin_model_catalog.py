"""Idempotently register the user-approved model catalog without storing secrets."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.models.llm import Model, ModelCategoryKey, ModelSettings, Provider, ProviderStatus
from app.ai_video.services.llm.pricing_catalog import merge_builtin_pricing_params


_PROVIDERS = (
    ("openai", "OpenAI", "https://api.openai.com/v1", "Configure an OpenAI API key in Model Management."),
    ("vertex", "Google Vertex AI", "https://aiplatform.googleapis.com", "Uses server-side ADC and GCP configuration."),
)

_MODELS = (
    ("openai-gpt-5-6-terra", "gpt-5.6-terra", ModelCategoryKey.text, "Balanced text, scripting, and agent reasoning."),
    ("openai-gpt-5-6-sol", "gpt-5.6-sol", ModelCategoryKey.text, "High-end text, scripting, and complex reasoning."),
    ("openai-gpt-image-2-5-sunburst", "gpt-image-2.5-sunburst", ModelCategoryKey.image, "OpenAI image generation."),
    ("openai-gpt-image-2-5-flare", "gpt-image-2.5-flare", ModelCategoryKey.image, "OpenAI image generation."),
    ("openai-gpt-4o-mini-tts", "gpt-4o-mini-tts", ModelCategoryKey.speech, "OpenAI text-to-speech."),
    ("vertex-gemini-3-1-flash-image", "gemini-3.1-flash-image", ModelCategoryKey.image, "Vertex image generation."),
    ("vertex-gemini-3-8-flash", "gemini-3.8-flash", ModelCategoryKey.text, "Vertex multimodal chat and analysis."),
    ("vertex-veo-3-1-fast", "veo-3.1-fast-generate-001", ModelCategoryKey.video, "Vertex text/image-to-video."),
    ("vertex-lyria-3-clip", "lyria-3-clip-preview", ModelCategoryKey.music, "Vertex background-music generation."),
    ("vertex-lyria-3-pro", "lyria-3-pro-preview", ModelCategoryKey.music, "Vertex long-form background-music generation."),
    ("vertex-gemini-omni-1-1-flash", "gemini-omni-1.1-flash-preview", ModelCategoryKey.video, "Default Gemini Omni text-to-video generation."),
)


async def seed_user_approved_models(db: AsyncSession) -> None:
    """Create OpenAI/Vertex defaults and keep the deferred Creatify integration disabled."""
    # Retain prior Creatify records for a later re-enable, but never let an
    # existing deployment select the deferred integration at runtime.
    deferred_creatify = await db.get(Provider, "creatify")
    if deferred_creatify is not None:
        deferred_creatify.status = ProviderStatus.disabled

    for provider_id, name, base_url, description in _PROVIDERS:
        if await db.get(Provider, provider_id) is None:
            db.add(
                Provider(
                    id=provider_id,
                    name=name,
                    base_url=base_url,
                    description=description,
                    status=ProviderStatus.testing,
                    created_by="builtin-model-catalog",
                )
            )
    await db.flush()

    for model_id, name, category, description in _MODELS:
        model = await db.get(Model, model_id)
        if model is None:
            provider_id = "openai" if model_id.startswith("openai-") else "vertex"
            model = Model(
                id=model_id,
                name=name,
                category=category,
                provider_id=provider_id,
                params=merge_builtin_pricing_params(model_id, {"configured_by": "builtin-model-catalog"}),
                description=description,
                created_by="builtin-model-catalog",
            )
            db.add(model)
        else:
            model.params = merge_builtin_pricing_params(model_id, model.params)
    await db.flush()

    settings = await db.get(ModelSettings, 1)
    if settings is None:
        settings = ModelSettings(id=1)
        db.add(settings)
    defaults = {
        "default_text_model_id": "openai-gpt-5-6-terra",
        "default_image_model_id": "vertex-gemini-3-1-flash-image",
        "default_video_model_id": "vertex-gemini-omni-1-1-flash",
        "default_speech_model_id": "openai-gpt-4o-mini-tts",
        "default_music_model_id": "vertex-lyria-3-clip",
    }
    for field, model_id in defaults.items():
        if getattr(settings, field, None) is None:
            setattr(settings, field, model_id)
    await db.flush()
