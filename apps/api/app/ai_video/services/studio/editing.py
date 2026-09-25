from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.core import storage
from app.ai_video.core.db import async_session_maker
from app.ai_video.core.task_manager import DeliveryMode, SqlAlchemyTaskStore
from app.ai_video.core.task_manager.types import TaskStatus
from app.ai_video.models.production_control import ProductionArtifact, ProductionRevision
from app.ai_video.models.studio import Chapter, FileItem, FileType, Project, ProjectResearch, Shot, ShotDetail
from app.ai_video.schemas.studio.editing import EditDocument
from app.ai_video.schemas.studio.production_control import ProductionRevisionCreate
from app.ai_video.services.studio.file_usages import upsert_file_usage
from app.ai_video.services.studio.production_control import canonical_fingerprint, create_production_revision
from app.ai_video.services.worker.task_logging import log_task_event, log_task_failure


async def build_default_edit_document(db: AsyncSession, *, project_id: str) -> EditDocument:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    stmt = (
        select(Shot, ShotDetail)
        .join(Chapter, Chapter.id == Shot.chapter_id)
        .join(ShotDetail, ShotDetail.id == Shot.id)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.index.asc(), Shot.index.asc())
    )
    rows = (await db.execute(stmt)).all()
    missing = [shot.id for shot, _detail in rows if not shot.generated_video_file_id]
    if missing:
        raise HTTPException(
            status_code=409,
            detail={"code": "selected_takes_missing", "shot_ids": missing},
        )
    if not rows:
        raise HTTPException(status_code=409, detail="Project has no shots")
    research = await db.get(ProjectResearch, project_id)
    brief = research.brief if research is not None and isinstance(research.brief, dict) else {}
    ratio = next(iter(brief.get("aspect_ratios") or []), "16:9")
    canvas_sizes = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "4:3": (1440, 1080),
        "3:4": (1080, 1440),
        "21:9": (2560, 1080),
    }
    width, height = canvas_sizes.get(str(ratio), canvas_sizes["16:9"])
    duration_ms = sum(int(detail.duration) * 1000 for _shot, detail in rows)
    end_card_start_ms = max(0, duration_ms - min(3000, duration_ms))
    required_overlays = set(brief.get("required_overlays") or [])
    overlays: list[dict[str, Any]] = []
    logo_file_id = brief.get("logo_file_id")
    if "logo" in required_overlays and isinstance(logo_file_id, str) and logo_file_id:
        overlays.append({
            "id": "brand-logo",
            "type": "logo",
            "file_id": logo_file_id,
            "start_ms": 0,
            "end_ms": duration_ms,
            "position": "top",
            "width_percent": 18,
        })
    cta = str(brief.get("cta") or "").strip()
    if "cta" in required_overlays and cta:
        overlays.append({
            "id": "brand-cta",
            "type": "cta",
            "text": cta,
            "start_ms": end_card_start_ms,
            "end_ms": duration_ms,
            "position": "bottom",
        })
    legal = str(brief.get("legal") or "").strip()
    if "legal" in required_overlays and legal:
        overlays.append({
            "id": "brand-legal",
            "type": "legal",
            "text": legal,
            "start_ms": 0,
            "end_ms": duration_ms,
            "position": "bottom",
        })
    product_name = str(brief.get("product_name") or "").strip()
    if "end_card" in required_overlays and (product_name or cta):
        overlays.append({
            "id": "brand-end-card",
            "type": "end_card",
            "text": " · ".join(item for item in (product_name, cta) if item),
            "start_ms": end_card_start_ms,
            "end_ms": duration_ms,
            "position": "center",
        })
    colors = brief.get("brand_colors") or []
    primary_text_color = next(
        (str(item) for item in colors if isinstance(item, str) and len(item) == 7 and item.startswith("#")),
        "#FFFFFF",
    )
    return EditDocument.model_validate(
        {
            "schema_version": 1,
            "canvas": {
                "width": width,
                "height": height,
                "safe_area_percent": int(brief.get("safe_area_percent") or 5),
                "font_family": str(brief.get("brand_font_family") or "Arial"),
                "primary_text_color": primary_text_color,
            },
            "video_clips": [
                {
                    "id": f"clip-{shot.id}",
                    "shot_id": shot.id,
                    "file_id": shot.generated_video_file_id,
                    "source_in_ms": 0,
                    "source_out_ms": int(detail.duration) * 1000,
                    "use_source_audio": False,
                    "source_audio_volume_db": 0,
                    "transition_to_next": {"type": "cut", "duration_ms": 0},
                }
                for shot, detail in rows
            ],
            "overlays": overlays,
        }
    )


async def validate_edit_document(
    db: AsyncSession,
    *,
    project_id: str,
    document: EditDocument,
) -> None:
    shot_ids = [clip.shot_id for clip in document.video_clips]
    stmt = (
        select(Shot)
        .join(Chapter, Chapter.id == Shot.chapter_id)
        .where(Chapter.project_id == project_id, Shot.id.in_(shot_ids))
    )
    shots = {shot.id: shot for shot in (await db.execute(stmt)).scalars().all()}
    problems: list[dict[str, Any]] = []
    for clip in document.video_clips:
        shot = shots.get(clip.shot_id)
        if shot is None:
            problems.append({"code": "shot_not_in_project", "clip_id": clip.id, "shot_id": clip.shot_id})
        elif shot.generated_video_file_id != clip.file_id:
            problems.append(
                {
                    "code": "clip_not_selected_take",
                    "clip_id": clip.id,
                    "shot_id": clip.shot_id,
                    "expected_file_id": shot.generated_video_file_id,
                    "file_id": clip.file_id,
                }
            )
    referenced_file_ids = {
        *[clip.file_id for clip in document.video_clips],
        *[clip.file_id for clip in document.audio_clips],
        *[overlay.file_id for overlay in document.overlays if overlay.file_id],
    }
    files = {
        row.id: row
        for row in (
            await db.execute(select(FileItem).where(FileItem.id.in_(referenced_file_ids)))
        ).scalars().all()
    }
    for clip in document.video_clips:
        file_obj = files.get(clip.file_id)
        if file_obj is None or file_obj.type != FileType.video:
            problems.append({"code": "invalid_video_file", "clip_id": clip.id, "file_id": clip.file_id})
    for clip in document.audio_clips:
        file_obj = files.get(clip.file_id)
        if file_obj is None or file_obj.type != FileType.audio:
            problems.append({"code": "invalid_audio_file", "clip_id": clip.id, "file_id": clip.file_id})
    for overlay in document.overlays:
        if overlay.type != "logo":
            continue
        file_obj = files.get(overlay.file_id or "")
        if file_obj is None or file_obj.type != FileType.image:
            problems.append({"code": "invalid_logo_file", "overlay_id": overlay.id, "file_id": overlay.file_id})
    if problems:
        raise HTTPException(status_code=409, detail={"code": "invalid_edit_document", "problems": problems})


async def create_edit_revision(
    db: AsyncSession,
    *,
    project_id: str,
    document: EditDocument,
    created_by: str | None,
) -> ProductionRevision:
    await validate_edit_document(db, project_id=project_id, document=document)
    return await create_production_revision(
        db,
        project_id=project_id,
        body=ProductionRevisionCreate(
            kind="edit",
            scope_type="project",
            payload={"schema_version": 1, "timeline": document.model_dump(mode="json")},
            created_by=created_by,
        ),
    )


async def create_timeline_render_task(
    db: AsyncSession,
    *,
    project_id: str,
    edit_revision_id: str,
    output_name: str,
) -> tuple[str, str]:
    revision = await db.get(ProductionRevision, edit_revision_id)
    if revision is None or revision.project_id != project_id or revision.kind != "edit":
        raise HTTPException(status_code=404, detail="Edit revision not found")
    if revision.state != "approved":
        raise HTTPException(status_code=409, detail="Only an approved edit revision can be rendered")
    document = EditDocument.model_validate((revision.payload or {}).get("timeline"))
    await validate_edit_document(db, project_id=project_id, document=document)
    manifest = {
        "schema_version": 1,
        "project_id": project_id,
        "edit_revision_id": edit_revision_id,
        "edit_fingerprint": revision.input_fingerprint,
        "document": document.model_dump(mode="json"),
        "output": {"container": "mp4", "video_codec": "h264", "audio_codec": "aac"},
    }
    fingerprint = canonical_fingerprint(manifest)
    store = SqlAlchemyTaskStore(db)
    task = await store.create(
        payload={
            "task_class": "_CreateOnlyTask",
            "task_kind": "timeline_render",
            "run_args": {
                "project_id": project_id,
                "edit_revision_id": edit_revision_id,
                "output_name": output_name,
                "manifest": manifest,
                "manifest_fingerprint": fingerprint,
            },
        },
        mode=DeliveryMode.async_polling,
        task_kind="timeline_render",
    )
    return task.id, fingerprint


def _seconds(milliseconds: int) -> str:
    return f"{milliseconds / 1000:.3f}"


def _ass_time(milliseconds: int) -> str:
    total_centiseconds = max(0, milliseconds // 10)
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def _ass_color(hex_color: str) -> str:
    red, green, blue = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H00{blue}{green}{red}".upper()


def build_ass_document(document: EditDocument) -> str:
    width = document.canvas.width
    height = document.canvas.height
    safe_x = max(20, round(width * document.canvas.safe_area_percent / 100))
    safe_y = max(20, round(height * document.canvas.safe_area_percent / 100))
    font_family = document.canvas.font_family
    primary_color = _ass_color(document.canvas.primary_text_color)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Subtitle,{font_family},{max(24, height // 24)},{primary_color},&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,{safe_x},{safe_x},{safe_y},1",
        f"Style: CTA,{font_family},{max(28, height // 18)},{primary_color},&H000000FF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,3,1,0,2,{safe_x},{safe_x},{safe_y},1",
        f"Style: Legal,{font_family},{max(16, height // 42)},{primary_color},&H000000FF,&H00101010,&H90000000,0,0,0,0,100,100,0,0,1,1,0,2,{safe_x},{safe_x},{safe_y},1",
        f"Style: EndCard,{font_family},{max(32, height // 14)},{primary_color},&H000000FF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,3,1,0,5,{safe_x},{safe_x},{safe_y},1",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for cue in document.subtitles:
        lines.append(
            f"Dialogue: 0,{_ass_time(cue.start_ms)},{_ass_time(cue.end_ms)},Subtitle,,0,0,0,,{_ass_escape(cue.text)}"
        )
    style_map = {"cta": "CTA", "legal": "Legal", "end_card": "EndCard"}
    position_override = {"top": r"{\an8}", "center": r"{\an5}", "bottom": r"{\an2}"}
    for overlay in document.overlays:
        if overlay.type == "logo":
            continue
        text = position_override[overlay.position] + _ass_escape(overlay.text)
        lines.append(
            f"Dialogue: 1,{_ass_time(overlay.start_ms)},{_ass_time(overlay.end_ms)},{style_map[overlay.type]},,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def build_ffmpeg_command(
    *,
    ffmpeg_path: str,
    document: EditDocument,
    video_paths: list[Path],
    audio_paths: list[Path],
    logo_paths: list[Path],
    video_has_audio: list[bool],
    ass_path: Path | None,
    output_path: Path,
) -> list[str]:
    args = [ffmpeg_path, "-y"]
    for path in video_paths:
        args.extend(["-i", str(path)])
    for path in audio_paths:
        args.extend(["-i", str(path)])
    for path in logo_paths:
        args.extend(["-i", str(path)])
    filters: list[str] = []
    for index, clip in enumerate(document.video_clips):
        filters.append(
            f"[{index}:v]trim=start={_seconds(clip.source_in_ms)}:end={_seconds(clip.source_out_ms)},"
            f"setpts=PTS-STARTPTS,scale={document.canvas.width}:{document.canvas.height}:force_original_aspect_ratio=decrease,"
            f"pad={document.canvas.width}:{document.canvas.height}:(ow-iw)/2:(oh-ih)/2:color={document.canvas.background},"
            f"setsar=1,fps={document.canvas.fps},format=yuv420p[v{index}]"
        )
    current = "v0"
    current_duration_ms = document.video_clips[0].source_out_ms - document.video_clips[0].source_in_ms
    for index in range(1, len(document.video_clips)):
        outgoing = document.video_clips[index - 1].transition_to_next
        next_duration = document.video_clips[index].source_out_ms - document.video_clips[index].source_in_ms
        joined = f"vj{index}"
        if outgoing.type == "cut":
            filters.append(f"[{current}][v{index}]concat=n=2:v=1:a=0[{joined}]")
            current_duration_ms += next_duration
        else:
            offset_ms = current_duration_ms - outgoing.duration_ms
            filters.append(
                f"[{current}][v{index}]xfade=transition={outgoing.type}:duration={_seconds(outgoing.duration_ms)}:"
                f"offset={_seconds(offset_ms)}[{joined}]"
            )
            current_duration_ms += next_duration - outgoing.duration_ms
        current = joined
    if ass_path is not None:
        escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"[{current}]ass='{escaped}'[vout]")
        current = "vout"

    logo_input_start = len(video_paths) + len(audio_paths)
    logo_overlays = [overlay for overlay in document.overlays if overlay.type == "logo"]
    for index, overlay in enumerate(logo_overlays):
        scaled = f"logo{index}"
        output = f"vlo{index}"
        width = max(1, round(document.canvas.width * overlay.width_percent / 100))
        safe_y = max(0, round(document.canvas.height * document.canvas.safe_area_percent / 100))
        y = {
            "top": str(safe_y),
            "center": "(H-h)/2",
            "bottom": f"H-h-{safe_y}",
        }[overlay.position]
        filters.append(f"[{logo_input_start + index}:v]scale={width}:-1[{scaled}]")
        filters.append(
            f"[{current}][{scaled}]overlay=x=(W-w)/2:y={y}:"
            f"enable='between(t\\,{_seconds(overlay.start_ms)}\\,{_seconds(overlay.end_ms)})':"
            f"eof_action=repeat:shortest=0[{output}]"
        )
        current = output

    audio_labels: list[str] = []
    audio_start = len(video_paths)
    for index, clip in enumerate(document.audio_clips):
        label = f"a{index}"
        delay = clip.timeline_start_ms
        filters.append(
            f"[{audio_start + index}:a]atrim=start={_seconds(clip.source_in_ms)}:end={_seconds(clip.source_out_ms)},"
            f"asetpts=PTS-STARTPTS,volume={clip.volume_db}dB,adelay={delay}|{delay}[{label}]"
        )
        audio_labels.append(label)
    duck_indices = [
        index
        for index, clip in enumerate(document.audio_clips)
        if clip.role == "music" and clip.duck_under_dialogue
    ]
    dialogue_indices = [
        index
        for index, clip in enumerate(document.audio_clips)
        if clip.role in {"dialogue", "voice_over"}
    ]
    if duck_indices and dialogue_indices:
        side_labels: list[str] = []
        for index in dialogue_indices:
            main_label = f"a{index}main"
            side_label = f"a{index}side"
            filters.append(f"[{audio_labels[index]}]asplit=2[{main_label}][{side_label}]")
            audio_labels[index] = main_label
            side_labels.append(side_label)
        if len(side_labels) == 1:
            sidechain_base = side_labels[0]
        else:
            sidechain_base = "dialogueside"
            filters.append(
                f"{''.join(f'[{label}]' for label in side_labels)}"
                f"amix=inputs={len(side_labels)}:duration=longest:normalize=0[{sidechain_base}]"
            )
        if len(duck_indices) > 1:
            split_labels = [f"duckside{index}" for index in range(len(duck_indices))]
            filters.append(
                f"[{sidechain_base}]asplit={len(split_labels)}"
                f"{''.join(f'[{label}]' for label in split_labels)}"
            )
        else:
            split_labels = [sidechain_base]
        for side_index, audio_index in enumerate(duck_indices):
            ducked_label = f"a{audio_index}ducked"
            filters.append(
                f"[{audio_labels[audio_index]}][{split_labels[side_index]}]"
                "sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300"
                f"[{ducked_label}]"
            )
            audio_labels[audio_index] = ducked_label
    for index, clip in enumerate(document.video_clips):
        if not clip.use_source_audio or index >= len(video_has_audio) or not video_has_audio[index]:
            continue
        label = f"asource{index}"
        filters.append(
            f"[{index}:a]atrim=start={_seconds(clip.source_in_ms)}:end={_seconds(clip.source_out_ms)},"
            f"asetpts=PTS-STARTPTS,volume={clip.source_audio_volume_db}dB[{label}]"
        )
        audio_labels.append(label)
    if audio_labels:
        inputs = "".join(f"[{label}]" for label in audio_labels)
        filters.append(f"{inputs}amix=inputs={len(audio_labels)}:duration=longest:normalize=0[aout]")

    args.extend(["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"])
    if audio_labels:
        args.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    else:
        args.append("-an")
    args.extend(["-movflags", "+faststart", str(output_path)])
    return args


async def _download_to(path: Path, file_obj: FileItem) -> None:
    path.write_bytes(await storage.download_file(key=file_obj.storage_key))


async def _has_audio_stream(path: Path) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return False
    process = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await process.communicate()
    return process.returncode == 0 and bool(stdout.strip())


async def run_timeline_render_task(task_id: str, run_args: dict[str, Any]) -> None:
    async with async_session_maker() as db:
        try:
            store = SqlAlchemyTaskStore(db)
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 5)
            await db.commit()
            manifest = dict(run_args.get("manifest") or {})
            document = EditDocument.model_validate(manifest.get("document"))
            project_id = str(run_args.get("project_id") or "")
            edit_revision_id = str(run_args.get("edit_revision_id") or "")
            fingerprint = str(run_args.get("manifest_fingerprint") or "")
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                raise RuntimeError("FFmpeg is required for deterministic timeline rendering")

            file_ids = (
                [clip.file_id for clip in document.video_clips]
                + [clip.file_id for clip in document.audio_clips]
                + [overlay.file_id for overlay in document.overlays if overlay.type == "logo" and overlay.file_id]
            )
            file_rows = {
                row.id: row
                for row in (await db.execute(select(FileItem).where(FileItem.id.in_(file_ids)))).scalars().all()
            }
            if len(file_rows) != len(set(file_ids)):
                raise RuntimeError("One or more timeline source files are unavailable")
            await store.set_progress(task_id, 15)
            await db.commit()

            with tempfile.TemporaryDirectory(prefix="incept-render-") as temp_dir:
                root = Path(temp_dir)
                video_paths: list[Path] = []
                for index, clip in enumerate(document.video_clips):
                    suffix = Path(file_rows[clip.file_id].storage_key).suffix or ".mp4"
                    path = root / f"video-{index}{suffix}"
                    await _download_to(path, file_rows[clip.file_id])
                    video_paths.append(path)
                video_has_audio = [await _has_audio_stream(path) for path in video_paths]
                audio_paths: list[Path] = []
                for index, clip in enumerate(document.audio_clips):
                    suffix = Path(file_rows[clip.file_id].storage_key).suffix or ".mp3"
                    path = root / f"audio-{index}{suffix}"
                    await _download_to(path, file_rows[clip.file_id])
                    audio_paths.append(path)
                logo_paths: list[Path] = []
                for index, overlay in enumerate(item for item in document.overlays if item.type == "logo"):
                    assert overlay.file_id is not None
                    suffix = Path(file_rows[overlay.file_id].storage_key).suffix or ".png"
                    path = root / f"logo-{index}{suffix}"
                    await _download_to(path, file_rows[overlay.file_id])
                    logo_paths.append(path)
                ass_path: Path | None = None
                if document.subtitles or document.overlays:
                    ass_path = root / "captions.ass"
                    ass_path.write_text(build_ass_document(document), encoding="utf-8")
                output_path = root / "render.mp4"
                command = build_ffmpeg_command(
                    ffmpeg_path=ffmpeg_path,
                    document=document,
                    video_paths=video_paths,
                    audio_paths=audio_paths,
                    logo_paths=logo_paths,
                    video_has_audio=video_has_audio,
                    ass_path=ass_path,
                    output_path=output_path,
                )
                await store.set_progress(task_id, 35)
                await db.commit()
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _stdout, stderr = await process.communicate()
                if process.returncode != 0:
                    detail = stderr.decode("utf-8", errors="replace")[-4000:]
                    raise RuntimeError(f"FFmpeg render failed: {detail}")
                output_bytes = output_path.read_bytes()

            file_id = str(uuid4())
            storage_key = f"renders/{project_id}/{edit_revision_id}/{fingerprint}.mp4"
            await storage.upload_file(key=storage_key, data=output_bytes, content_type="video/mp4")
            file_obj = FileItem(
                id=file_id,
                type=FileType.video,
                name=str(run_args.get("output_name") or "final-render"),
                thumbnail=file_id,
                tags=["timeline-render", f"edit:{edit_revision_id}"],
                storage_key=storage_key,
            )
            db.add(file_obj)
            await db.flush()
            await upsert_file_usage(
                db,
                file_id=file_id,
                project_id=project_id,
                chapter_id=None,
                shot_id=None,
                usage_kind="api",
                source_ref=f"edit-render:{edit_revision_id}",
            )
            db.add(
                ProductionArtifact(
                    id=str(uuid4()),
                    project_id=project_id,
                    shot_id=None,
                    artifact_type="render",
                    file_id=file_id,
                    source_revision_id=edit_revision_id,
                    generation_task_id=task_id,
                    input_fingerprint=fingerprint,
                    currency="current",
                    lifecycle="candidate",
                    metadata_json={"manifest": manifest},
                )
            )
            result = {
                "file_id": file_id,
                "edit_revision_id": edit_revision_id,
                "manifest_fingerprint": fingerprint,
                "manifest": manifest,
            }
            await store.set_result(task_id, result)
            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await db.commit()
            log_task_event("timeline_render", task_id, "succeeded", file_id=file_id)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            async with async_session_maker() as failure_db:
                store = SqlAlchemyTaskStore(failure_db)
                await store.set_error(task_id, str(exc))
                await store.set_status(task_id, TaskStatus.failed)
                await failure_db.commit()
            log_task_failure("timeline_render", task_id, str(exc))


__all__ = [
    "build_ass_document",
    "build_default_edit_document",
    "build_ffmpeg_command",
    "create_edit_revision",
    "create_timeline_render_task",
    "run_timeline_render_task",
    "validate_edit_document",
]
