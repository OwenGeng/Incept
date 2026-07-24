from __future__ import annotations

from app.incept.models import VideoGenerationRequest


def build_video_prompt_summary(request: VideoGenerationRequest) -> dict[str, str | int | bool | list[str]]:
    prompt = " ".join((request.prompt or "").split())
    return {
        "mode": request.video_generation_mode.value,
        "prompt": prompt,
        "aspect_ratio": request.aspect_ratio,
        "duration_seconds": request.duration_seconds,
        "resolution": request.resolution,
        "variants": request.variants,
        "include_audio": request.include_audio,
        "camera_preset": (request.camera_preset or "").strip(),
        "reference_asset_ids": request.reference_asset_ids,
        "enhance_with_veo_fast": request.enhance_with_veo_fast,
    }


def build_video_mock_completion_message(request: VideoGenerationRequest) -> str:
    mode_labels = {
        "image_to_video": "Image to Video",
        "playable_to_video": "Playable to Video",
        "competitor_style_transfer": "Video to Video",
        "video_to_playable": "Video to Playable",
        "first_last_frame": "First + Last Frame",
        "extend_video": "Extend Video",
        "reference_character": "Reference Character",
        "prompt_assist": "Prompt Assist",
        "multi_shot_storyboard": "Multi-shot Storyboard",
        "video_remediation": "Video Remediation",
        "synthetic_recast": "Synthetic Recast",
    }
    mode = mode_labels.get(request.video_generation_mode.value, request.video_generation_mode.value)
    prompt = " ".join((request.prompt or "").split())
    return (
        f"Video request prepared. Mode: {mode}. "
        f"Prepared a {request.duration_seconds}s {request.aspect_ratio} {request.resolution} request with "
        f"{request.variants} variant(s)"
        f"{' and audio enabled' if request.include_audio else ''}. "
        f"{'Prompt captured: ' + prompt if prompt else 'No user prompt was provided.'} "
        "If generation did not start, check the configured Veo model IDs and runtime credentials."
    )
