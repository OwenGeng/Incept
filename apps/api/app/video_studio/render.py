from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from . import store
from .models import ExportRequest, ExportResponse


_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _run(command: list[str], *, timeout: int = 1_800) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"Required media executable is unavailable: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "Media command failed")[-2_000:]
        raise RuntimeError(detail) from error


def probe_asset(email: str, project_id: str, relative_path: str) -> dict[str, Any]:
    root = store.assets_root(email, project_id)
    source = store.safe_asset_path(root, relative_path)
    if not source.is_file():
        raise FileNotFoundError(relative_path)
    result = _run(
        [
            os.getenv("FFPROBE_PATH", "ffprobe"),
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(source),
        ],
        timeout=60,
    )
    return json.loads(result.stdout)


def _normalize_clip(
    *,
    source: Path,
    output: Path,
    duration: float | None,
    width: int,
    height: int,
    fps: int,
) -> None:
    mime_type = store.asset_mime_type(source)
    filter_value = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps},format=yuv420p"
    )
    command = [os.getenv("FFMPEG_PATH", "ffmpeg"), "-y"]
    if mime_type.startswith("image/"):
        command.extend(["-loop", "1", "-t", str(duration or 3), "-i", str(source)])
    elif mime_type.startswith("video/"):
        command.extend(["-i", str(source)])
        if duration:
            command.extend(["-t", str(duration)])
    else:
        raise ValueError(f"Unsupported export clip type: {mime_type}")
    command.extend(
        [
            "-vf",
            filter_value,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command)


def _clip_duration(path: Path) -> float:
    result = _run(
        [
            os.getenv("FFPROBE_PATH", "ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=60,
    )
    try:
        return max(0.01, float(result.stdout.strip()))
    except ValueError as error:
        raise RuntimeError(f"Could not determine clip duration: {path.name}") from error


def _join_clips(normalized: list[Path], request: ExportRequest, output: Path, temporary_root: Path) -> None:
    if len(normalized) == 1:
        output.write_bytes(normalized[0].read_bytes())
        return
    if not any(clip.transition == "crossfade" for clip in request.clips[1:]):
        concat_file = temporary_root / "clips.txt"
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in normalized),
            encoding="utf-8",
        )
        _run(
            [
                os.getenv("FFMPEG_PATH", "ffmpeg"),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output),
            ]
        )
        return

    durations = [_clip_duration(path) for path in normalized]
    command = [os.getenv("FFMPEG_PATH", "ffmpeg"), "-y"]
    for path in normalized:
        command.extend(["-i", str(path)])
    filters: list[str] = []
    current = "0:v"
    elapsed = durations[0]
    for index in range(1, len(normalized)):
        fade = min(0.5, durations[index - 1] / 3, durations[index] / 3) if request.clips[index].transition == "crossfade" else 0.001
        offset = max(0, elapsed - fade)
        output_label = f"v{index}"
        filters.append(
            f"[{current}][{index}:v]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}[{output_label}]"
        )
        current = output_label
        elapsed += durations[index] - fade
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{current}]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command)


def export_project(
    email: str,
    project_id: str,
    request: ExportRequest,
    *,
    progress: Callable[[int, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ExportResponse:
    root = store.assets_root(email, project_id)
    sources: list[tuple[Path, float | None]] = []
    for clip in request.clips:
        source = store.safe_asset_path(root, clip.asset_path)
        if not source.is_file():
            raise FileNotFoundError(clip.asset_path)
        sources.append((source, clip.duration))

    safe_name = _SAFE_NAME.sub("-", request.name.strip()).strip(".-") or "video-export"
    relative_output = f"exports/{safe_name}-{uuid.uuid4().hex[:8]}.mp4"
    output = store.safe_asset_path(root, relative_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_suffix(".tmp.mp4")

    with tempfile.TemporaryDirectory(prefix="linglong-video-export-") as temporary:
        temporary_root = Path(temporary)
        normalized: list[Path] = []
        for index, (source, duration) in enumerate(sources):
            if cancelled and cancelled():
                raise InterruptedError("Export cancelled")
            clip_output = temporary_root / f"clip-{index:04d}.mp4"
            _normalize_clip(
                source=source,
                output=clip_output,
                duration=duration,
                width=request.width,
                height=request.height,
                fps=request.fps,
            )
            normalized.append(clip_output)
            if progress:
                progress(
                    10 + int(((index + 1) / len(sources)) * 55),
                    f"Prepared clip {index + 1} of {len(sources)}",
                )
        concatenated = temporary_root / "concatenated.mp4"
        _join_clips(normalized, request, concatenated, temporary_root)
        if progress:
            progress(75, "Joined clips")
        if cancelled and cancelled():
            raise InterruptedError("Export cancelled")
        if request.soundtrack_path:
            soundtrack = store.safe_asset_path(root, request.soundtrack_path)
            if not soundtrack.is_file():
                raise FileNotFoundError(request.soundtrack_path)
            _run(
                [
                    os.getenv("FFMPEG_PATH", "ffmpeg"),
                    "-y",
                    "-i",
                    str(concatenated),
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(soundtrack),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(temporary_output),
                ]
            )
            if progress:
                progress(92, "Mixed soundtrack")
        else:
            temporary_output.write_bytes(concatenated.read_bytes())
    temporary_output.replace(output)
    if progress:
        progress(100, "Export complete")
    return ExportResponse(asset_path=relative_output, size=output.stat().st_size)
