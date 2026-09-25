from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EditCanvas(BaseModel):
    width: int = Field(1920, ge=320, le=7680)
    height: int = Field(1080, ge=320, le=7680)
    fps: int = Field(30, ge=1, le=120)
    background: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    safe_area_percent: int = Field(5, ge=3, le=20)
    font_family: str = Field("Arial", min_length=1, max_length=128, pattern=r"^[^,\r\n]+$")
    primary_text_color: str = Field("#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")


class EditTransition(BaseModel):
    type: Literal["cut", "fade", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright"] = "cut"
    duration_ms: int = Field(0, ge=0, le=3000)

    @model_validator(mode="after")
    def validate_duration(self) -> "EditTransition":
        if self.type == "cut" and self.duration_ms != 0:
            raise ValueError("Cut transitions must have duration_ms=0")
        if self.type != "cut" and self.duration_ms <= 0:
            raise ValueError("Non-cut transitions require duration_ms>0")
        return self


class EditVideoClip(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    shot_id: str = Field(min_length=1, max_length=64)
    file_id: str = Field(min_length=1, max_length=64)
    source_in_ms: int = Field(0, ge=0)
    source_out_ms: int = Field(gt=0)
    use_source_audio: bool = False
    source_audio_volume_db: float = Field(0, ge=-60, le=12)
    transition_to_next: EditTransition = Field(default_factory=EditTransition)

    @model_validator(mode="after")
    def validate_trim(self) -> "EditVideoClip":
        if self.source_out_ms <= self.source_in_ms:
            raise ValueError("source_out_ms must be greater than source_in_ms")
        if self.transition_to_next.duration_ms >= self.source_out_ms - self.source_in_ms:
            raise ValueError("Transition duration must be shorter than the clip")
        return self


class EditAudioClip(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    file_id: str = Field(min_length=1, max_length=64)
    role: Literal["dialogue", "voice_over", "music", "sfx"]
    timeline_start_ms: int = Field(0, ge=0)
    source_in_ms: int = Field(0, ge=0)
    source_out_ms: int = Field(gt=0)
    volume_db: float = Field(0, ge=-60, le=12)
    duck_under_dialogue: bool = False

    @model_validator(mode="after")
    def validate_trim(self) -> "EditAudioClip":
        if self.source_out_ms <= self.source_in_ms:
            raise ValueError("source_out_ms must be greater than source_in_ms")
        return self


class EditSubtitleCue(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=1000)
    speaker: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def validate_range(self) -> "EditSubtitleCue":
        if self.end_ms <= self.start_ms:
            raise ValueError("Subtitle end_ms must be greater than start_ms")
        return self


class EditOverlay(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: Literal["logo", "cta", "legal", "end_card"]
    text: str = Field("", max_length=2000)
    file_id: str | None = Field(None, max_length=64)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    position: Literal["top", "center", "bottom"] = "bottom"
    width_percent: int = Field(20, ge=5, le=80)

    @model_validator(mode="after")
    def validate_range(self) -> "EditOverlay":
        if self.end_ms <= self.start_ms:
            raise ValueError("Overlay end_ms must be greater than start_ms")
        if self.type == "logo" and not self.file_id:
            raise ValueError("Logo overlays require file_id")
        if self.type != "logo" and not self.text.strip():
            raise ValueError("Text overlays require text")
        return self


class EditDocument(BaseModel):
    schema_version: Literal[1] = 1
    canvas: EditCanvas = Field(default_factory=EditCanvas)
    video_clips: list[EditVideoClip] = Field(min_length=1, max_length=500)
    audio_clips: list[EditAudioClip] = Field(default_factory=list, max_length=500)
    subtitles: list[EditSubtitleCue] = Field(default_factory=list, max_length=5000)
    overlays: list[EditOverlay] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_ids_and_ranges(self) -> "EditDocument":
        ids = [item.id for item in [*self.video_clips, *self.audio_clips, *self.subtitles, *self.overlays]]
        if len(ids) != len(set(ids)):
            raise ValueError("Timeline item IDs must be unique")
        duration_ms = sum(clip.source_out_ms - clip.source_in_ms for clip in self.video_clips)
        duration_ms -= sum(clip.transition_to_next.duration_ms for clip in self.video_clips[:-1])
        for cue in [*self.subtitles, *self.overlays]:
            if cue.end_ms > duration_ms:
                raise ValueError(f"Timeline item {cue.id} exceeds edit duration")
        return self


class EditRevisionRequest(BaseModel):
    document: EditDocument
    created_by: str | None = Field(None, max_length=255)


class TimelineRenderRequest(BaseModel):
    edit_revision_id: str = Field(min_length=1, max_length=64)
    output_name: str = Field("final-render", min_length=1, max_length=255)


class TimelineRenderCreated(BaseModel):
    task_id: str
    edit_revision_id: str
    manifest_fingerprint: str


__all__ = [
    "EditDocument",
    "EditRevisionRequest",
    "TimelineRenderCreated",
    "TimelineRenderRequest",
]
