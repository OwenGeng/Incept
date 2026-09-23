"""Server-owned model capability catalogue for Video Production.

The browser may choose only an already configured provider/model pair.  This
module intentionally contains no endpoint, credential, project, or location
editing surface; those deployment settings remain server-owned.
"""

from __future__ import annotations

from app.incept.config import Settings, get_settings
from app.incept.models import (
    VideoProductionModelSelection,
    VideoProductionProviderCapabilities,
    VideoProductionProviderOption,
    VideoProductionProviderSelection,
)


VERTEX_PROVIDER = "google-vertex-ai"


def _option(model: str, label: str) -> VideoProductionProviderOption | None:
    clean = model.strip()
    return VideoProductionProviderOption(provider=VERTEX_PROVIDER, model=clean, label=label) if clean else None


def configured_video_production_capabilities(settings: Settings | None = None) -> VideoProductionProviderCapabilities:
    """Return only model IDs already configured by the deployment owner."""
    configured = settings or get_settings()

    text = [_option(configured.vertex_video_analysis_model, "Production planning")]
    image = [_option(configured.vertex_gemini_image_model, "Visual development")]
    video = [
        _option(configured.vertex_veo_fast_model, "Shot generation"),
        _option(configured.vertex_veo_model, "Shot generation"),
    ]
    audio = [_option(configured.vertex_lyria_model, "Soundtrack generation")] if configured.vertex_lyria_enabled else []

    return VideoProductionProviderCapabilities(
        text=[item for item in text if item],
        image=[item for item in image if item],
        video=[item for item in video if item],
        audio=[item for item in audio if item],
    )


def default_video_production_selection(settings: Settings | None = None) -> VideoProductionProviderSelection:
    catalogue = configured_video_production_capabilities(settings)

    def first(options: list[VideoProductionProviderOption]) -> VideoProductionModelSelection:
        if not options:
            return VideoProductionModelSelection()
        return VideoProductionModelSelection(provider=options[0].provider, model=options[0].model)

    return VideoProductionProviderSelection(
        text=first(catalogue.text),
        image=first(catalogue.image),
        video=first(catalogue.video),
        audio=first(catalogue.audio),
    )


def validate_video_production_selection(
    selection: VideoProductionProviderSelection,
    settings: Settings | None = None,
) -> VideoProductionProviderSelection:
    """Reject arbitrary browser-supplied model IDs before project persistence."""
    catalogue = configured_video_production_capabilities(settings)
    expected = {
        "text": catalogue.text,
        "image": catalogue.image,
        "video": catalogue.video,
        "audio": catalogue.audio,
    }
    values = selection.model_dump()
    for operation, options in expected.items():
        chosen = values[operation]
        if not chosen["provider"] and not chosen["model"]:
            values[operation] = default_video_production_selection(settings).model_dump()[operation]
            continue
        if not any(item.provider == chosen["provider"] and item.model == chosen["model"] for item in options):
            raise ValueError(f"The selected {operation} provider/model is not configured for Video Production.")
    return VideoProductionProviderSelection.model_validate(values)
