from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai_video.core.db import Base
from app.ai_video.models.production_control import ProductionRevision
from app.ai_video.models.studio import (
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    FileItem,
    FileType,
    Project,
    ProjectResearch,
    ProjectStyle,
    ProjectVisualStyle,
    Shot,
    ShotDetail,
)
from app.ai_video.models.task import GenerationTask
from app.ai_video.schemas.studio.editing import EditDocument
from app.ai_video.services.studio.editing import (
    build_ass_document,
    build_default_edit_document,
    build_ffmpeg_command,
    create_edit_revision,
    create_timeline_render_task,
)
from app.ai_video.services.studio.production_control import approve_production_revision


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed(db: AsyncSession) -> None:
    db.add(
        Project(
            id="project-1",
            name="Project",
            description="",
            style=ProjectStyle.real_people_city,
            visual_style=ProjectVisualStyle.live_action,
        )
    )
    db.add(Chapter(id="chapter-1", project_id="project-1", index=1, title="Chapter"))
    for index in (1, 2):
        file_id = f"video-{index}"
        shot_id = f"shot-{index}"
        db.add(FileItem(id=file_id, type=FileType.video, name=file_id, thumbnail="", tags=[], storage_key=f"videos/{file_id}.mp4"))
        db.add(
            Shot(
                id=shot_id,
                chapter_id="chapter-1",
                index=index,
                title=f"Shot {index}",
                generated_video_file_id=file_id,
            )
        )
        db.add(
            ShotDetail(
                id=shot_id,
                camera_shot=CameraShotType.ms,
                angle=CameraAngle.eye_level,
                movement=CameraMovement.static,
                duration=4 + index,
            )
        )
    db.add(FileItem(id="audio-1", type=FileType.audio, name="music", thumbnail="", tags=[], storage_key="audio/music.mp3"))
    await db.commit()


@pytest.mark.asyncio
async def test_default_edit_uses_selected_takes_in_story_order() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        document = await build_default_edit_document(db, project_id="project-1")
        assert [clip.shot_id for clip in document.video_clips] == ["shot-1", "shot-2"]
        assert [clip.file_id for clip in document.video_clips] == ["video-1", "video-2"]
        assert [clip.source_out_ms for clip in document.video_clips] == [5000, 6000]
    await engine.dispose()


@pytest.mark.asyncio
async def test_default_edit_applies_approved_ad_brand_rules() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        db.add(FileItem(id="logo-1", type=FileType.image, name="logo", thumbnail="", tags=[], storage_key="brand/logo.png"))
        db.add(
            ProjectResearch(
                project_id="project-1",
                entry_mode="preset",
                status="approved",
                approved_direction_id="direction-1",
                creative_directions=[{"id": "direction-1"}],
                sources=[],
                findings=[],
                brief={
                    "product_name": "Acme",
                    "aspect_ratios": ["9:16"],
                    "cta": "Buy now",
                    "legal": "Terms apply",
                    "required_overlays": ["logo", "cta", "legal", "end_card"],
                    "logo_file_id": "logo-1",
                    "brand_colors": ["#12AB34"],
                    "brand_font_family": "Inter",
                    "safe_area_percent": 8,
                },
            )
        )
        await db.commit()

        document = await build_default_edit_document(db, project_id="project-1")
        assert (document.canvas.width, document.canvas.height) == (1080, 1920)
        assert document.canvas.safe_area_percent == 8
        assert document.canvas.font_family == "Inter"
        assert document.canvas.primary_text_color == "#12AB34"
        assert {item.type for item in document.overlays} == {"logo", "cta", "legal", "end_card"}
        assert next(item for item in document.overlays if item.type == "logo").file_id == "logo-1"
        assert "Inter" in build_ass_document(document)
        assert "&H0034AB12" in build_ass_document(document)
    await engine.dispose()


@pytest.mark.asyncio
async def test_edit_rejects_non_selected_take_and_render_requires_approval() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        document = await build_default_edit_document(db, project_id="project-1")
        invalid = document.model_copy(deep=True)
        invalid.video_clips[0].file_id = "video-2"
        with pytest.raises(HTTPException) as exc_info:
            await create_edit_revision(db, project_id="project-1", document=invalid, created_by="editor")
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["problems"][0]["code"] == "clip_not_selected_take"

        revision = await create_edit_revision(db, project_id="project-1", document=document, created_by="editor")
        with pytest.raises(HTTPException) as unapproved:
            await create_timeline_render_task(
                db,
                project_id="project-1",
                edit_revision_id=revision.id,
                output_name="Final",
            )
        assert unapproved.value.status_code == 409

        await approve_production_revision(db, project_id="project-1", revision_id=revision.id, approved_by="director")
        task_id, fingerprint = await create_timeline_render_task(
            db,
            project_id="project-1",
            edit_revision_id=revision.id,
            output_name="Final",
        )
        await db.commit()
        task = await db.get(GenerationTask, task_id)
        saved_revision = await db.get(ProductionRevision, revision.id)
        assert task is not None and task.task_kind == "timeline_render"
        assert task.payload["run_args"]["manifest_fingerprint"] == fingerprint
        assert saved_revision is not None and saved_revision.state == "approved"
    await engine.dispose()


def test_ffmpeg_plan_contains_trim_transition_audio_and_deterministic_text() -> None:
    document = EditDocument.model_validate(
        {
            "video_clips": [
                {
                    "id": "v1",
                    "shot_id": "s1",
                    "file_id": "f1",
                    "source_in_ms": 500,
                    "source_out_ms": 4500,
                    "transition_to_next": {"type": "dissolve", "duration_ms": 500},
                },
                {
                    "id": "v2",
                    "shot_id": "s2",
                    "file_id": "f2",
                    "source_in_ms": 0,
                    "source_out_ms": 4000,
                },
            ],
            "audio_clips": [
                {
                    "id": "a1",
                    "file_id": "a1",
                    "role": "music",
                    "timeline_start_ms": 250,
                    "source_in_ms": 0,
                    "source_out_ms": 7000,
                    "volume_db": -6,
                    "duck_under_dialogue": True,
                },
                {
                    "id": "a2",
                    "file_id": "a2",
                    "role": "voice_over",
                    "timeline_start_ms": 0,
                    "source_in_ms": 0,
                    "source_out_ms": 2000,
                    "volume_db": 0,
                }
            ],
            "subtitles": [{"id": "sub1", "start_ms": 0, "end_ms": 1500, "text": "Hello"}],
            "overlays": [{"id": "cta1", "type": "cta", "text": "Buy now", "start_ms": 5000, "end_ms": 7000}],
        }
    )
    ass = build_ass_document(document)
    command = build_ffmpeg_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        document=document,
        video_paths=[Path("/tmp/v1.mp4"), Path("/tmp/v2.mp4")],
        audio_paths=[Path("/tmp/a1.mp3"), Path("/tmp/a2.mp3")],
        logo_paths=[],
        video_has_audio=[False, False],
        ass_path=Path("/tmp/text.ass"),
        output_path=Path("/tmp/out.mp4"),
    )
    joined = " ".join(command)
    assert "trim=start=0.500:end=4.500" in joined
    assert "xfade=transition=dissolve:duration=0.500:offset=3.500" in joined
    assert "adelay=250|250" in joined
    assert "amix=inputs=2" in joined
    assert "sidechaincompress=" in joined
    assert "Dialogue:" in ass and "Hello" in ass and "Buy now" in ass


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg is unavailable")
def test_ffmpeg_command_renders_real_transition_smoke(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg and ffprobe
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    output = tmp_path / "output.mp4"
    for color, path in (("red", first), ("blue", second)):
        subprocess.run(
            [
                ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d=1:r=24",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
            ],
            check=True,
            capture_output=True,
        )
    document = EditDocument.model_validate(
        {
            "canvas": {"width": 320, "height": 320, "fps": 24, "background": "#000000"},
            "video_clips": [
                {
                    "id": "v1", "shot_id": "s1", "file_id": "f1", "source_in_ms": 0, "source_out_ms": 900,
                    "transition_to_next": {"type": "dissolve", "duration_ms": 200},
                },
                {"id": "v2", "shot_id": "s2", "file_id": "f2", "source_in_ms": 0, "source_out_ms": 900},
            ],
        }
    )
    command = build_ffmpeg_command(
        ffmpeg_path=ffmpeg,
        document=document,
        video_paths=[first, second],
        audio_paths=[],
        logo_paths=[],
        video_has_audio=[False, False],
        ass_path=None,
        output_path=output,
    )
    subprocess.run(command, check=True, capture_output=True)
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert output.stat().st_size > 0
    assert 1.4 <= float(probe.stdout.strip()) <= 1.8
