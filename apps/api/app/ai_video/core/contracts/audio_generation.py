"""Shared contracts for speech and background-music generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai_video.core.contracts.provider import ProviderKey


AudioFormat = Literal["mp3", "wav", "opus", "aac", "flac", "pcm"]


class AudioGenerationInput(BaseModel):
    """Provider-neutral audio request.

    ``prompt`` is the narration script for speech models and the musical brief
    for music models.  The selected model determines which interpretation is
    valid; that avoids silently inventing a provider-specific API surface.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=1, max_length=8000, description="Speech script or music prompt.")
    model: str | None = Field(None, description="Model selected in Model Management.")
    voice: str | None = Field(None, description="Voice for a speech model, when supported.")
    response_format: AudioFormat = Field("mp3", description="Requested output format, when supported.")
    speed: float | None = Field(None, ge=0.25, le=4.0, description="Speech speed, when supported.")
    provider_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific options; never use this field for credentials.",
    )

    @model_validator(mode="after")
    def _normalize_prompt(self) -> "AudioGenerationInput":
        self.prompt = self.prompt.strip()
        if not self.prompt:
            raise ValueError("prompt must not be blank")
        return self


class AudioGenerationResult(BaseModel):
    """Portable audio result represented as a URL or data URL."""

    model_config = ConfigDict(extra="ignore")

    url: str = Field(..., description="Remote URL or base64 data URL for generated audio.")
    provider: ProviderKey
    provider_task_id: str | None = None
    status: str = "succeeded"
    duration_seconds: int | None = None
