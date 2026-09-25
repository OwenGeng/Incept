from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.ai_video.core import storage
from app.ai_video.models.studio import FileItem


async def _run(command: list[str], *, timeout: float = 600.0) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    return (
        int(process.returncode or 0),
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _fraction(value: str | None) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        try:
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else None
        except ValueError:
            return None
    try:
        return float(raw)
    except ValueError:
        return None


async def inspect_local_media(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise RuntimeError("FFmpeg and ffprobe are required for delivery QA")
    code, stdout, stderr = await _run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        timeout=120.0,
    )
    if code != 0:
        raise RuntimeError(f"ffprobe failed: {stderr[-2000:]}")
    payload = json.loads(stdout)
    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    duration = float(format_data.get("duration") or 0)
    if not video:
        raise RuntimeError("Rendered file has no video stream")

    detect_code, _detect_stdout, detect_stderr = await _run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-60dB:d=1",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    if detect_code != 0:
        raise RuntimeError(f"FFmpeg visual QA failed: {detect_stderr[-2000:]}")
    black_segments = [
        {"start": float(start), "end": float(end), "duration": float(segment_duration)}
        for start, end, segment_duration in re.findall(
            r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)",
            detect_stderr,
        )
    ]
    freeze_starts = [float(value) for value in re.findall(r"freeze_start:\s*([0-9.]+)", detect_stderr)]

    max_volume_db: float | None = None
    if audio_streams:
        volume_code, _volume_stdout, volume_stderr = await _run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
        )
        if volume_code == 0:
            match = re.search(r"max_volume:\s*(-?(?:inf|[0-9.]+))\s*dB", volume_stderr)
            if match and match.group(1) != "-inf":
                max_volume_db = float(match.group(1))

    return {
        "duration_seconds": duration,
        "format_name": str(format_data.get("format_name") or ""),
        "size_bytes": int(format_data.get("size") or path.stat().st_size),
        "video": {
            "codec": video.get("codec_name"),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": _fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
            "pixel_format": video.get("pix_fmt"),
        },
        "audio_stream_count": len(audio_streams),
        "max_volume_db": max_volume_db,
        "black_segments": black_segments,
        "freeze_starts": freeze_starts,
    }


async def inspect_media_file(file_obj: FileItem) -> dict[str, Any]:
    content = await storage.download_file(key=file_obj.storage_key)
    suffix = Path(file_obj.storage_key).suffix or ".mp4"
    with tempfile.TemporaryDirectory(prefix="incept-qa-") as temp_dir:
        path = Path(temp_dir) / f"delivery{suffix}"
        path.write_bytes(content)
        return await inspect_local_media(path)


__all__ = ["inspect_local_media", "inspect_media_file"]
