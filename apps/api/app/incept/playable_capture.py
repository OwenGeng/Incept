from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.incept.config import get_settings
from PIL import Image, ImageStat


@dataclass(frozen=True)
class PlayableCaptureResult:
    video_path: Path
    stdout: str


def _create_webgl_chrome_wrapper(chrome_path: str, project_root: Path) -> Path:
    """Keep WebGL available for canvas/WebGL playables in headless Chrome.

    Creative Core's generic exporter disables GPU by default. Many production
    playables use a WebGL canvas, which renders as a black frame under that
    flag. Appending SwiftShader options after the Core flags keeps capture
    portable on local macOS Chrome and Cloud Run Chromium.
    """
    wrapper = project_root / "chrome-webgl-wrapper.sh"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"exec {json.dumps(chrome_path)} \"$@\" "
        "--enable-webgl --enable-unsafe-swiftshader "
        "--use-angle=swiftshader --ignore-gpu-blocklist\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def _validate_capture_has_visible_frames(output_path: Path, ffmpeg_path: str, duration_seconds: int) -> None:
    """Reject a recording when every sampled frame is effectively black."""
    sample_points = sorted({max(1, duration_seconds // 4), max(1, duration_seconds // 2), max(1, duration_seconds - 2)})
    samples: list[tuple[float, float]] = []
    with tempfile.TemporaryDirectory(prefix="incept-playable-frames-") as directory:
        for index, second in enumerate(sample_points):
            frame_path = Path(directory) / f"frame-{index}.png"
            extraction = subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-ss",
                    str(second),
                    "-i",
                    str(output_path),
                    "-frames:v",
                    "1",
                    str(frame_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if extraction.returncode != 0 or not frame_path.is_file():
                continue
            with Image.open(frame_path).convert("RGB") as image:
                stats = ImageStat.Stat(image)
                samples.append((sum(stats.mean) / 3, sum(stats.var) / 3))

    # A real playable frame should have both visible luminance and scene detail.
    if not samples or not any(mean > 8 and variance > 12 for mean, variance in samples):
        raise RuntimeError(
            "Browser capture produced blank frames. The playable did not render in headless Chrome; "
            "check WebGL/canvas compatibility and bundled assets."
        )


def _resolve_core_home() -> Path:
    settings = get_settings()
    configured = settings.creative_core_home.strip()
    root = Path(configured).expanduser() if configured else Path.home() / ".moloco" / "cr-agent" / "creative-core"
    if not (root / "package.json").is_file() or not (root / "scripts" / "cr-agent-core.sh").is_file():
        raise RuntimeError(
            "Creative Core is not available for browser capture. Set CREATIVE_CORE_HOME to a prepared Creative Core installation."
        )
    return root


def _resolve_executable(configured: str, candidates: list[str], label: str) -> str:
    if configured.strip():
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        raise RuntimeError(f"Configured {label} executable does not exist: {path}")
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError(f"{label} is required for Playable to Video capture but was not found.")


def _sanitize_actions(raw_actions: object) -> list[dict[str, int | float | str]]:
    actions: list[dict[str, int | float | str]] = []
    if isinstance(raw_actions, list):
        for raw in raw_actions[:12]:
            if not isinstance(raw, dict):
                continue
            action_type = str(raw.get("type", "")).strip().lower()
            if action_type == "wait":
                delay = raw.get("ms", 600)
                if isinstance(delay, (int, float)):
                    actions.append({"type": "wait", "ms": max(100, min(5000, int(delay)))})
                continue
            if action_type not in {"click", "drag", "swipe"}:
                continue
            x = raw.get("x", raw.get("from_x", 0.5))
            y = raw.get("y", raw.get("from_y", 0.65))
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                continue
            action: dict[str, int | float | str] = {
                "type": action_type,
                "x": max(0.02, min(0.98, float(x))),
                "y": max(0.02, min(0.98, float(y))),
                "ms": 650,
            }
            if action_type in {"drag", "swipe"}:
                to_x = raw.get("to_x", 0.72)
                to_y = raw.get("to_y", y)
                if isinstance(to_x, (int, float)) and isinstance(to_y, (int, float)):
                    action["to_x"] = max(0.02, min(0.98, float(to_x)))
                    action["to_y"] = max(0.02, min(0.98, float(to_y)))
            actions.append(action)
    if actions:
        return actions
    # Safe best-effort fallback for common playables with an initial CTA and a central game action.
    return [
        {"type": "wait", "ms": 900},
        {"type": "click", "x": 0.5, "y": 0.72, "ms": 900},
        {"type": "click", "x": 0.5, "y": 0.55, "ms": 1100},
        {"type": "click", "x": 0.5, "y": 0.78, "ms": 900},
    ]


def _inject_capture_harness(html_text: str, actions: list[dict[str, int | float | str]], duration_ms: int) -> str:
    body_match = re.search(r"<body\b(?P<attrs>[^>]*)>", html_text, flags=re.IGNORECASE)
    if body_match:
        attrs = body_match.group("attrs")
        if re.search(r"\bclass\s*=", attrs, flags=re.IGNORECASE):
            attrs = re.sub(
                r"\bclass\s*=\s*(['\"])(.*?)\1",
                lambda match: f'class={match.group(1)}{match.group(2)} moloco-playable-root{match.group(1)}',
                attrs,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            attrs = f'{attrs} class="moloco-playable-root"'
        html_text = f"{html_text[:body_match.start()]}<body{attrs}>{html_text[body_match.end():]}"
    else:
        html_text = f'<body class="moloco-playable-root">{html_text}</body>'

    action_json = json.dumps(actions, separators=(",", ":"))
    harness = f"""
<script data-incept-capture-harness="true">
(function () {{
  var plan = {action_json};
  window.__creativeCoreDemoFlow = {{ done: false, source: 'incept-browser-capture' }};
  function point(x, y) {{ return {{ x: Math.round(window.innerWidth * x), y: Math.round(window.innerHeight * y) }}; }}
  function dispatch(target, type, x, y) {{
    target.dispatchEvent(new PointerEvent(type, {{ bubbles: true, cancelable: true, clientX: x, clientY: y, pointerType: 'touch' }}));
  }}
  function click(action) {{
    var p = point(action.x, action.y);
    var target = document.elementFromPoint(p.x, p.y) || document.body;
    dispatch(target, 'pointerdown', p.x, p.y); dispatch(target, 'pointerup', p.x, p.y);
    if (typeof target.click === 'function') target.click();
  }}
  function drag(action) {{
    var from = point(action.x, action.y); var to = point(action.to_x || .72, action.to_y || action.y);
    var target = document.elementFromPoint(from.x, from.y) || document.body;
    dispatch(target, 'pointerdown', from.x, from.y); dispatch(target, 'pointermove', to.x, to.y); dispatch(target, 'pointerup', to.x, to.y);
  }}
  var delay = 0;
  plan.forEach(function (action) {{
    delay += Number(action.ms || 600);
    window.setTimeout(function () {{
      if (action.type === 'click') click(action);
      if (action.type === 'drag' || action.type === 'swipe') drag(action);
    }}, delay);
  }});
  window.setTimeout(function () {{ window.__creativeCoreDemoFlow.done = true; }}, {duration_ms - 250});
}}());
</script>"""
    if re.search(r"</body\s*>", html_text, flags=re.IGNORECASE):
        return re.sub(r"</body\s*>", f"{harness}</body>", html_text, count=1, flags=re.IGNORECASE)
    return f"{html_text}{harness}"


def capture_playable_to_mp4(
    *,
    html_text: str,
    interaction_actions: object,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    output_path: Path,
) -> PlayableCaptureResult:
    """Run a self-contained playable through Creative Core's Chrome/FFmpeg exporter."""
    settings = get_settings()
    core_home = _resolve_core_home()
    chrome_path = _resolve_executable(
        settings.playable_capture_chrome_path,
        ["google-chrome", "chromium", "chromium-browser", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "Chrome",
    )
    ffmpeg_path = _resolve_executable(settings.playable_capture_ffmpeg_path, ["ffmpeg"], "FFmpeg")
    slug = f"incept-capture-{uuid4().hex[:12]}"
    project_root = core_home / "playables" / slug
    artifact_path = project_root / "dist" / "standalone" / "index.html"
    setup_path = project_root / "video-export.json"
    if resolution == "720p":
        width, height = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)
    else:
        width, height = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    duration_ms = duration_seconds * 1000

    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        (project_root / "adforge.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "id": slug,
                    "name": "Incept Browser Capture",
                    "version": "1.0.0",
                    "kind": "creative-template",
                    "sourceType": "local",
                    "schema": "schema.json",
                    "outputs": [
                        {
                            "target": "standalone-html",
                            "entry": "src/index.html",
                            "outDir": "dist/standalone",
                            "artifact": "dist/standalone/index.html",
                            "inlineAssets": True,
                            "script": "build",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (project_root / "schema.json").write_text("{}", encoding="utf-8")
        chrome_wrapper = _create_webgl_chrome_wrapper(chrome_path, project_root)
        artifact_path.write_text(
            _inject_capture_harness(html_text, _sanitize_actions(interaction_actions), duration_ms),
            encoding="utf-8",
        )
        setup_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "id": "incept-browser-capture",
                    "name": "Incept Browser Capture",
                    "video": {
                        "width": width,
                        "height": height,
                        "viewportWidth": width,
                        "viewportHeight": height,
                        "fps": 30,
                        "durationMs": duration_ms,
                        "completionPolicy": "fixed-duration-ignore-complete",
                        "format": "mp4",
                    },
                    "templateConfig": {
                        "inceptCapture": {
                            "source": "browser-recording",
                            "interactionWarmupMs": 1200,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "bash",
            str(core_home / "scripts" / "cr-agent-core.sh"),
            "export-video",
            slug,
            "--no-build",
            "--setup-file",
            str(setup_path),
            "--out",
            str(output_path),
            "--chrome",
            str(chrome_wrapper),
            "--ffmpeg",
            ffmpeg_path,
        ]
        completed = subprocess.run(
            command,
            cwd=core_home,
            env={**os.environ, "CREATIVES_CORE_HOME": str(core_home)},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=duration_seconds + 180,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Creative Core browser capture failed.\n{completed.stdout[-4000:]}")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError("Creative Core browser capture did not produce an MP4 output.")
        _validate_capture_has_visible_frames(output_path, ffmpeg_path, duration_seconds)
        return PlayableCaptureResult(video_path=output_path, stdout=completed.stdout)
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
