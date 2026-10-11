"""Versioned creative profiles: customer instructions are not exchange approval."""

from copy import deepcopy
from fractions import Fraction
import json
import math
import os
import subprocess

from . import store

MOLOCO_VIDEO_GUIDE = "https://help.moloco.com/hc/en-us/articles/7104841219095-Video-creative-guide"
MOLOCO_CTV_GUIDE = "https://www.moloco.com/capabilities/moloco-ads/performance-ctv"

_PROFILE = {
    "id": "moloco-ctv",
    "name": "Moloco CTV",
    "verified_at": "2026-10-08",
    "format": "mp4",
    "aspect_ratio": "16:9",
    "recommended_resolution": [1920, 1080],
    "accepted_resolutions": [[1920, 1080], [1280, 720]],
    "max_file_bytes": 450_000_000,
    "minimum_fps": 24,
    "duration_seconds": {"minimum": 6, "maximum": 180, "recommended": [15, 30, 60]},
    "source": MOLOCO_VIDEO_GUIDE,
    "configuration_source": "user-provided CTV campaign requirements",
    # The customer has confirmed this campaign's requirements. A different
    # public placement profile must not silently override that contract.
    "approval_status": "customer_configuration_confirmed",
    "warnings": [],
    "ctv_reference": {"url": MOLOCO_CTV_GUIDE, "scope": "background reference; not this campaign's acceptance contract"},
    "end_card": {"formats": ["jpeg", "jpg", "png", "gif"], "minimum_resolution": [320, 320],
                 "max_file_bytes": 500_000, "gif_max_file_bytes": 1_000_000, "orientation": "match video",
                 "scope": "generic video guide; confirm CTV placement separately"},
}


def moloco_ctv_profile() -> dict:
    return deepcopy(_PROFILE)


def moloco_ctv_instructions() -> str:
    return (
        "For Moloco CTV, use the customer's campaign profile: landscape 16:9 MP4, "
        "1920x1080 recommended, 1280x720 accepted, >=24 FPS, <=450 MB (decimal), 6–180 seconds; "
        "recommend 15/30/60 seconds and preserve the user's chosen duration. Shot durations must sum to that duration. "
        "Do not confuse source assets with final ad delivery: product photos/clips need not meet final video specs. "
        "This campaign configuration is customer-confirmed: do not impose a different placement's size or duration limits, "
        "or ask the user to confirm these specifications again. Technical checks establish conformance to this profile, "
        "not advertising rights or platform review approval. Do not assume short videos will be looped. End-card rules from the generic "
        "guide are matching orientation, both dimensions >=320, JPG/PNG/GIF, <=500 KB (GIF <=1 MB); "
        "confirm whether the CTV placement uses a separate end card. Sources: " + MOLOCO_VIDEO_GUIDE + " ; " + MOLOCO_CTV_GUIDE
    )


def check_moloco_ctv_metadata(metadata: dict, *, size: int, is_mp4: bool) -> dict:
    """Check actual probe output, never claim exchange approval from these checks."""
    errors, warnings = [], list(_PROFILE["warnings"])
    streams = metadata.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    measured = {"size_bytes": size, "is_mp4": is_mp4}
    if not is_mp4: errors.append("交付格式必须为MP4")
    if size > _PROFILE["max_file_bytes"]: errors.append("视频超过450MB")
    if video is None:
        errors.append("未检测到视频轨道")
    else:
        width, height = video.get("width"), video.get("height")
        measured.update(width=width, height=height)
        if [width, height] not in _PROFILE["accepted_resolutions"]: errors.append("交付分辨率需为1920×1080或1280×720")
        try:
            fps = float(Fraction(str(video.get("avg_frame_rate", "0"))))
            if not math.isfinite(fps) or fps < 24: raise ValueError()
            measured["fps"] = fps
        except (ValueError, ZeroDivisionError): errors.append("未确认帧率达到24 FPS")
        try:
            duration = float(metadata.get("format", {}).get("duration", video.get("duration", "nan")))
            if not math.isfinite(duration) or not 6 <= duration <= 180: raise ValueError()
            measured["duration_seconds"] = duration
            if not any(abs(duration - target) <= 0.1 for target in (15, 30, 60)): warnings.append("当前时长不在推荐的15/30/60秒档位")
        except (ValueError, TypeError): errors.append("未确认时长在6–180秒范围内")
    return {"profile_id": "moloco-ctv", "status": "invalid" if errors else "technical_pass",
        "technical_checks_passed": not errors, "approved_for_delivery": False,
        "approval_checks": {"advertising_rights": "unverified", "platform_review": "unverified"},
        "measured": measured, "errors": errors, "warnings": warnings}


def validate_moloco_ctv_video(email: str, project_id: str, relative_path: str) -> dict:
    source = store.safe_asset_path(store.assets_root(email, project_id), relative_path)
    if not source.is_file(): raise FileNotFoundError(relative_path)
    with source.open("rb") as file:
        prefix = file.read(32)
    is_mp4 = source.suffix.lower() == ".mp4" and prefix[4:8] == b"ftyp" and prefix[8:12] != b"qt  "
    try:
        # No network protocols: a malicious playlist/container must not turn a
        # local technical check into another URL fetch.
        result = subprocess.run([os.getenv("FFPROBE_PATH", "ffprobe"), "-v", "error",
            "-protocol_whitelist", "file,pipe", "-show_format", "-show_streams", "-of", "json", str(source)],
            check=True, capture_output=True, text=True, timeout=20)
        metadata = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"profile_id": "moloco-ctv", "status": "unverified", "technical_checks_passed": False,
            "approved_for_delivery": False, "errors": ["无法读取视频技术参数；请确认文件有效且部署包含ffprobe"],
            "warnings": list(_PROFILE["warnings"])}
    return validate_metadata_if_valid(metadata, source.stat().st_size, is_mp4)


def validate_metadata_if_valid(metadata: object, size: int, is_mp4: bool) -> dict:
    if not isinstance(metadata, dict) or not isinstance(metadata.get("streams"), list):
        return {"status": "unverified", "technical_checks_passed": False, "approved_for_delivery": False,
            "errors": ["视频探测结果无效"], "warnings": list(_PROFILE["warnings"])}
    return check_moloco_ctv_metadata(metadata, size=size, is_mp4=is_mp4)
