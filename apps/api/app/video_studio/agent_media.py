"""Bounded, cancellable analysis copies; originals and cloud settings stay intact."""

from contextlib import contextmanager
from io import BytesIO
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid

from google.genai import types
from PIL import Image, ImageOps, UnidentifiedImageError

from . import store, vertex_media

IMAGE_SOURCE_BYTES = 100 * 1024 * 1024
VIDEO_SOURCE_BYTES = 450_000_000
MAX_PIXELS = 40_000_000
MAX_DURATION = 180
INLINE_VIDEO_BYTES = 8 * 1024 * 1024
IMAGE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_IMAGES = 64
REQUEST_BYTES = {"google-vertex-ai": 24 * 1024 * 1024, "openai": 16 * 1024 * 1024, "anthropic": 12 * 1024 * 1024}
_WORKERS = threading.BoundedSemaphore(2)
_LOG = logging.getLogger(__name__)


class _CancelSignal(BaseException):
    def __init__(self, original):
        self.original = original


def _check(callback):
    if callback:
        try:
            callback()
        except Exception as exc:
            raise _CancelSignal(exc) from exc


@contextmanager
def _worker(cancel):
    while not _WORKERS.acquire(timeout=.1):
        _check(cancel)
    try:
        _check(cancel)
        yield
    finally:
        _WORKERS.release()


def _run(args, *, cancel=None, timeout=30, output_files=()):
    """No shell, no pipes that deadlock, bounded logs and generated files."""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        def check_output_limits():
            if os.fstat(stdout.fileno()).st_size > 128_000 or os.fstat(stderr.fileno()).st_size > 64_000:
                raise ValueError("媒体处理日志超过安全预算")
            if any(path.exists() and path.stat().st_size > limit for path, limit in output_files):
                raise ValueError("媒体分析副本超过安全输出预算")

        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                _check(cancel)
                if time.monotonic() > deadline:
                    raise ValueError("媒体处理超时，请提供更短或较低分辨率的分析副本")
                check_output_limits()
                time.sleep(.05)
            _check(cancel)
            check_output_limits()
            if process.returncode:
                raise ValueError("媒体解码失败，请提供有效的MP4或图片文件")
            stdout.seek(0)
            return stdout.read(128_001)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


def _image(path):
    with Image.open(path) as image:
        if image.width * image.height > MAX_PIXELS or image.format not in {"JPEG", "PNG", "WEBP", "GIF", "AVIF", "ICO"}:
            raise ValueError("图片格式不支持或解码像素超过40MP，请提供缩小副本")
        original = image.size
        image.seek(0)
        image.load()
        image = ImageOps.exif_transpose(image)
        image.thumbnail((1536, 1536))
        # PNG preserves transparent client logos; opaque pictures use JPEG.
        transparent = image.mode in {"RGBA", "LA"} or "transparency" in image.info
        image = image.convert("RGBA" if transparent else "RGB")
        while True:
            data = BytesIO()
            image.save(data, format="PNG" if transparent else "JPEG", **({} if transparent else {"quality": 85}))
            if data.tell() <= IMAGE_BYTES:
                return data.getvalue(), "image/png" if transparent else "image/jpeg", original, image.size
            image.thumbnail((max(1, image.width // 2), max(1, image.height // 2)))


def _container(path):
    with path.open("rb") as file:
        prefix = file.read(32)
    if prefix[4:8] in {b"ftyp", b"moov", b"mdat", b"wide"}:
        return "video/mp4", ["-enable_drefs", "0", "-use_absolute_path", "0"]
    if prefix[:4] == b"\x1aE\xdf\xa3":
        return "video/webm", []
    if prefix[:4] == b"RIFF" and prefix[8:12] == b"AVI ":
        return "video/avi", []
    raise ValueError("视频不是支持的本地二进制容器；不解析播放列表或外部引用")


def _input(path, extra):
    return ["-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,avi", *extra, "-i", str(path)]


def _probe(path, extra, cancel):
    raw = _run([os.getenv("FFPROBE_PATH", "ffprobe"), "-v", "error", *_input(path, extra),
                "-show_entries", "format=duration:stream=codec_type,width,height,duration", "-of", "json"], cancel=cancel)
    metadata = json.loads(raw)
    video = next((stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"), None)
    if not video or not isinstance(video.get("width"), int) or not isinstance(video.get("height"), int):
        raise ValueError("未检测到有效的视频轨道")
    if not 0 < video["width"] * video["height"] <= MAX_PIXELS:
        raise ValueError("视频帧解码像素超过40MP，请提供缩小副本")
    duration = float(metadata.get("format", {}).get("duration", video.get("duration", "nan")))
    if not math.isfinite(duration) or not 0 < duration <= MAX_DURATION:
        raise ValueError("视频分析范围必须在180秒内，请提供明确选定范围的剪辑副本")
    return duration, any(stream.get("codec_type") == "audio" for stream in metadata.get("streams", []))


def _delete_blob(blob, token):
    try:
        if blob.generation is None:
            blob.reload(timeout=15)
            if (blob.metadata or {}).get("linglonglab-agent-input") != token:
                return
        blob.delete(if_generation_match=blob.generation, timeout=15)
    except Exception as exc:
        from google.api_core.exceptions import NotFound
        if isinstance(exc, NotFound):
            return
        # Never hide an orphan as a successful cleanup or expose its URI in logs.
        _LOG.error("Agent temporary media cleanup failed; configured storage needs operator review")


def _video(path, entry, provider, cancel, resources, deadline):
    mime, extra = _container(path)
    duration, has_audio = _probe(path, extra, cancel)
    entry.update(duration_seconds=duration, inspected_range_seconds=[0, duration], no_audio=not has_audio)
    if provider == "google-vertex-ai" and mime == "video/mp4" and path.stat().st_size <= INLINE_VIDEO_BYTES:
        entry.update(mode="video-proxy", notes=["原视频直接发送；未转码，模型可能内部采样，并非逐帧检测"])
        return [types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)]
    if provider == "google-vertex-ai" and resources is not None and mime == "video/mp4":
        try:
            bucket = vertex_media._asset_bucket()
        except RuntimeError:
            bucket = None
        if bucket:
            try:
                token = uuid.uuid4().hex
                key = f"video/agent-inputs/{token}/input.mp4"
                storage_bucket = vertex_media._gcs_client().bucket(bucket)
                storage_bucket.reload(timeout=15)
                if not storage_bucket.iam_configuration.uniform_bucket_level_access_enabled:
                    raise ValueError("存储未启用统一桶权限，无法保证分析引用隐私")
                policy = storage_bucket.get_iam_policy(requested_policy_version=3, timeout=15)
                if any(member in {"allUsers", "allAuthenticatedUsers"} for binding in policy.get("bindings", []) for member in binding.get("members", [])):
                    raise ValueError("配置存储存在公开权限，禁止上传分析引用")
                blob = storage_bucket.blob(key)
                blob.metadata = {"linglonglab-agent-input": token}
                resources.callback(_delete_blob, blob, token)
                _check(cancel)
                blob.upload_from_filename(str(path), content_type=mime, if_generation_match=0, timeout=60)
                _check(cancel)
                entry.update(mode="video-reference", notes=["已配置存储临时引用；已核验桶统一权限与无公开IAM，未设置公开权限；请求结束后尝试清理，失败会触发服务端告警；模型可能内部采样"])
                return [types.Part.from_uri(file_uri=f"gs://{bucket}/{key}", mime_type=mime)]
            except _CancelSignal:
                raise
            except Exception:
                entry.setdefault("notes", []).append("配置存储引用失败，改用本地有界分析副本")
    with tempfile.TemporaryDirectory(prefix="linglonglab-agent-media-") as directory:
        workspace = Path(directory)
        base = [os.getenv("FFMPEG_PATH", "ffmpeg"), "-v", "error", "-nostdin", "-threads", "1", *_input(path, extra)]
        if provider == "google-vertex-ai":
            proxy = workspace / "proxy.mp4"
            _run([*base, "-map", "0:v:0", "-map", "0:a:0?", "-t", str(duration), "-vf", "scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=12",
                  "-c:v", "libx264", "-threads", "1", "-preset", "veryfast", "-b:v", "240k", "-maxrate", "280k", "-bufsize", "560k",
                  "-c:a", "aac", "-b:a", "48k", "-ac", "1", "-movflags", "+faststart", str(proxy)],
                 cancel=cancel, timeout=max(.01, min(90, deadline - time.monotonic())), output_files=[(proxy, INLINE_VIDEO_BYTES)])
            if proxy.stat().st_size > INLINE_VIDEO_BYTES:
                raise ValueError("视频分析副本超过8MiB预算，请提供较短片段")
            audio_note = "保留原片音轨但压缩为单声道" if has_audio else "原片没有音轨，副本不含音频"
            entry.update(mode="video-proxy", notes=[*entry.get("notes", []), f"分析副本降至最长边约640px、12FPS；{audio_note}，原件不变"])
            return [types.Part.from_bytes(data=proxy.read_bytes(), mime_type="video/mp4")]
        count = min(12, max(2, math.ceil(duration / 15)))
        timestamps = [round((duration * .95) * index / (count - 1), 3) for index in range(count)]
        parts = []
        for index, timestamp in enumerate(timestamps):
            _check(cancel)
            frame = workspace / f"frame-{index}.jpg"
            _run([*base, "-ss", str(timestamp), "-map", "0:v:0", "-frames:v", "1", "-vf", "scale=1024:1024:force_original_aspect_ratio=decrease:force_divisible_by=2", "-q:v", "3", "-threads", "1", str(frame)],
                 cancel=cancel, timeout=max(.01, min(30, deadline - time.monotonic())), output_files=[(frame, IMAGE_BYTES)])
            data, image_mime, _, _ = _image(frame)
            parts.extend([types.Part(text=f"Video {entry['path']}: sampled frame at {timestamp:.3f}s; no audio; not full-frame coverage."),
                          types.Part.from_bytes(data=data, mime_type=image_mime)])
        entry.update(mode="sampled-frames", timestamps_seconds=timestamps, no_audio=True,
                     notes=["仅分布采样全片画面，不代表看过所有帧；没有音频，不得推断对白或配音内容"])
        return parts


def prepare_assets(email, project_id, asset_paths, *, provider_id="google-vertex-ai", check_cancel=None, progress=None, resources=None):
    """Provider-neutral parts plus truthful manifests; lifetime belongs to caller."""
    if provider_id not in REQUEST_BYTES:
        raise ValueError("Unsupported media preparation provider")
    parts, manifest, used, image_count = [], [], 0, 0
    deadline = time.monotonic() + 180
    try:
        for index, relative in enumerate(dict.fromkeys(asset_paths)):
            _check(check_cancel)
            entry = {"path": relative, "name": Path(relative).name, "size": 0, "inspection": "metadata-only"}
            manifest.append(entry)
            try:
                if index >= 20 or time.monotonic() > deadline:
                    raise ValueError("附件处理数量或总时间预算已达上限，请分批分析")
                path = store.safe_asset_path(store.assets_root(email, project_id), relative)
                if not path.is_file():
                    raise ValueError("附件已移动或删除，未分析")
                entry.update(size=path.stat().st_size, mime_type=store.asset_mime_type(path))
                if progress:
                    progress(f"正在准备附件：{entry['name']}")
                with _worker(check_cancel):
                    mime = entry["mime_type"]
                    if mime.startswith("image/"):
                        if entry["size"] > IMAGE_SOURCE_BYTES:
                            raise ValueError("图片源文件超过100MiB，请提供分析副本")
                        data, prepared_mime, original, dimensions = _image(path)
                        prepared = [types.Part.from_bytes(data=data, mime_type=prepared_mime)]
                        entry.update(mode="image", original_dimensions=list(original), prepared_dimensions=list(dimensions),
                                     notes=["只发送首帧分析副本，可能降采样/压缩，原始素材不变"])
                    elif mime.startswith("video/"):
                        if entry["size"] > VIDEO_SOURCE_BYTES:
                            raise ValueError("视频源文件超过450MB，请提供合规原件或剪辑副本")
                        prepared = _video(path, entry, provider_id, check_cancel, resources, deadline)
                    elif mime.startswith("text/") or mime in {"application/json", "application/xml"}:
                        with path.open("rb") as file:
                            text = file.read(100_000).decode("utf-8", errors="replace")[:50_000]
                        prepared = [types.Part(text=f"Project asset {relative}:\n{text}")]
                        entry.update(mode="text", notes=["文本最多读取100KB、发送50000字符"])
                    elif provider_id == "google-vertex-ai" and (mime.startswith("audio/") or mime == "application/pdf"):
                        if entry["size"] > 8 * 1024 * 1024:
                            raise ValueError("当前音频/PDF原生输入预算8MiB，请提供较短副本")
                        prepared = [types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)]
                        entry.update(mode="native", notes=["仅发送附件，模型解读能力以实际返回为准"])
                    else:
                        raise ValueError("此类型尚无该提供商的分析适配器，请提供图片或文本")
                _check(check_cancel)
                payload_size = sum(len(part.inline_data.data) if part.inline_data else len((part.text or "").encode()) for part in prepared)
                prepared_image_count = sum(1 for part in prepared if part.inline_data and part.inline_data.mime_type.startswith("image/"))
                if image_count + prepared_image_count > MAX_REQUEST_IMAGES:
                    raise ValueError(f"本次分析请求图片数量超过{MAX_REQUEST_IMAGES}张（包括视频采样帧），请分批发送")
                if used + payload_size > REQUEST_BYTES[provider_id]:
                    raise ValueError(f"{provider_id}本次分析请求预算不足，请分批发送附件")
                parts.extend(prepared)
                used += payload_size
                image_count += prepared_image_count
                entry.update(inspection="attached", prepared_bytes=payload_size)
            except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                entry["reason"] = str(exc) if isinstance(exc, ValueError) else "附件解码或本地媒体处理不可用，请提供有效副本并确认FFmpeg部署"
                entry.pop("mode", None)
        return parts, manifest
    except _CancelSignal as signal:
        raise signal.original
