from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai_video.core.db import Base
from app.ai_video.models.production_control import ProductionArtifact, ProductionRevision
from app.ai_video.models.studio import (
    Chapter,
    FileItem,
    FileType,
    Project,
    ProjectResearch,
    ProjectStyle,
    ProjectVisualStyle,
    Shot,
    ShotDetail,
    ShotFrameImage,
    ShotFrameType,
)
from app.ai_video.schemas.studio.production_control import (
    ProductionArtifactCreate,
    ProductionDeliveryCreate,
    ProductionQARunRequest,
    ProductionRevisionCreate,
)
from app.ai_video.services.studio.production_control import (
    approve_production_revision,
    build_delivery_subtitles_srt,
    build_production_workflow_plan,
    create_production_artifact,
    create_production_delivery,
    create_production_revision,
    run_production_qa,
    select_production_artifact,
    snapshot_shot_plan_revision,
)


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_project(db: AsyncSession) -> None:
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
    db.add_all(
        [
            Shot(id="shot-1", chapter_id="chapter-1", index=1, title="Shot 1", script_excerpt="one"),
            Shot(id="shot-2", chapter_id="chapter-1", index=2, title="Shot 2", script_excerpt="two"),
        ]
    )
    await db.commit()


@pytest.mark.asyncio
async def test_revision_approval_supersedes_previous_revision() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_project(db)
        first = await create_production_revision(
            db,
            project_id="project-1",
            body=ProductionRevisionCreate(kind="script", payload={"title": "v1"}, created_by="producer"),
        )
        await approve_production_revision(
            db,
            project_id="project-1",
            revision_id=first.id,
            approved_by="reviewer",
        )
        second = await create_production_revision(
            db,
            project_id="project-1",
            body=ProductionRevisionCreate(
                kind="script",
                payload={"title": "v2"},
                parent_revision_id=first.id,
                created_by="producer",
            ),
        )
        await approve_production_revision(
            db,
            project_id="project-1",
            revision_id=second.id,
            approved_by="reviewer",
        )
        await db.commit()

        assert first.revision_number == 1
        assert second.revision_number == 2
        assert first.state == "superseded"
        assert second.state == "approved"
        assert first.input_fingerprint != second.input_fingerprint
        assert second.approved_by == "reviewer"
        assert "_lineage" in second.payload
    await engine.dispose()


@pytest.mark.asyncio
async def test_artifact_selection_keeps_previous_artifact_as_candidate() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_project(db)
        db.add_all(
            [
                FileItem(
                    id="file-1",
                    type=FileType.image,
                    name="one",
                    thumbnail="",
                    tags=[],
                    storage_key="files/one.png",
                ),
                FileItem(
                    id="file-2",
                    type=FileType.image,
                    name="two",
                    thumbnail="",
                    tags=[],
                    storage_key="files/two.png",
                ),
            ]
        )
        await db.flush()
        first = await create_production_artifact(
            db,
            project_id="project-1",
            body=ProductionArtifactCreate(
                shot_id="shot-1",
                artifact_type="keyframe",
                file_id="file-1",
            ),
        )
        second = await create_production_artifact(
            db,
            project_id="project-1",
            body=ProductionArtifactCreate(
                shot_id="shot-1",
                artifact_type="keyframe",
                file_id="file-2",
            ),
        )
        await select_production_artifact(
            db,
            project_id="project-1",
            artifact_id=first.id,
            selected_by="producer",
        )
        await select_production_artifact(
            db,
            project_id="project-1",
            artifact_id=second.id,
            selected_by="producer",
        )
        await db.commit()

        assert first.lifecycle == "candidate"
        assert first.selected_at is None
        assert second.lifecycle == "selected"
        assert second.selected_by == "producer"
        assert await db.get(ProductionArtifact, first.id) is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_keyframe_selection_updates_authoritative_frame_and_approves_revision() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_project(db)
        db.add(
            ShotDetail(
                id="shot-1",
                camera_shot="MS",
                angle="EYE_LEVEL",
                movement="STATIC",
                duration=5,
            )
        )
        db.add_all(
            [
                ShotFrameImage(shot_detail_id="shot-1", frame_type=ShotFrameType.key, file_id=None, format="png"),
                FileItem(id="key-1", type=FileType.image, name="key one", thumbnail="", tags=[], storage_key="keys/one.png"),
                FileItem(id="key-2", type=FileType.image, name="key two", thumbnail="", tags=[], storage_key="keys/two.png"),
            ]
        )
        await db.flush()
        first = await create_production_artifact(
            db,
            project_id="project-1",
            body=ProductionArtifactCreate(shot_id="shot-1", artifact_type="frame_key", file_id="key-1"),
        )
        second = await create_production_artifact(
            db,
            project_id="project-1",
            body=ProductionArtifactCreate(shot_id="shot-1", artifact_type="frame_key", file_id="key-2"),
        )

        await select_production_artifact(db, project_id="project-1", artifact_id=first.id, selected_by="producer")
        await select_production_artifact(db, project_id="project-1", artifact_id=second.id, selected_by="producer")
        await db.commit()

        frame = (
            await db.execute(
                select(ShotFrameImage).where(
                    ShotFrameImage.shot_detail_id == "shot-1",
                    ShotFrameImage.frame_type == ShotFrameType.key,
                )
            )
        ).scalars().first()
        assert frame is not None and frame.file_id == "key-2"
        assert first.lifecycle == "candidate"
        assert second.lifecycle == "selected"
        revisions = list(
            (
                await db.execute(
                    select(ProductionRevision).where(
                        ProductionRevision.project_id == "project-1",
                        ProductionRevision.kind == "keyframe",
                        ProductionRevision.scope_id == "shot-1",
                    )
                )
            ).scalars().all()
        )
        revisions.sort(key=lambda item: item.revision_number)
        assert [item.state for item in revisions] == ["superseded", "approved"]
        assert revisions[-1].payload["file_id"] == "key-2"
    await engine.dispose()


@pytest.mark.asyncio
async def test_workflow_plan_routes_through_approved_revisions_and_selected_takes() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_project(db)

        plan = await build_production_workflow_plan(db, project_id="project-1")
        assert plan.current_step == "brief"
        assert plan.next_action.type == "approve_research"

        db.add(
            ProjectResearch(
                project_id="project-1",
                entry_mode="preset",
                status="approved",
                brief={},
                sources=[],
                findings=[],
                creative_directions=[{"id": "direction-1"}],
                approved_direction_id="direction-1",
            )
        )
        await db.flush()
        plan = await build_production_workflow_plan(db, project_id="project-1")
        assert plan.next_action.type == "create_script_revision"

        script = await create_production_revision(
            db,
            project_id="project-1",
            body=ProductionRevisionCreate(kind="script", payload={"script": "approved"}),
        )
        await approve_production_revision(db, project_id="project-1", revision_id=script.id, approved_by="reviewer")
        plan = await build_production_workflow_plan(db, project_id="project-1")
        assert plan.next_action.type == "snapshot_shot_plan"

        db.add(
            ShotDetail(
                id="shot-1",
                camera_shot="MS",
                angle="EYE_LEVEL",
                movement="STATIC",
                duration=4,
                description="Demonstrate the product benefit",
                action_beats=["Reveal", "Proof"],
                has_bgm=True,
            )
        )
        await db.flush()
        shot_plan = await snapshot_shot_plan_revision(db, project_id="project-1", created_by="producer")
        assert shot_plan.payload["format"] == "persisted_shot_plan_snapshot"
        assert [item["shot_id"] for item in shot_plan.payload["shots"]] == ["shot-1", "shot-2"]
        assert shot_plan.payload["shots"][0]["camera"] == {
            "shot": "MS",
            "angle": "EYE_LEVEL",
            "movement": "STATIC",
        }
        assert shot_plan.payload["shots"][0]["audio_cues"]["has_bgm"] is True
        assert shot_plan.payload["total_duration_seconds"] == 4
        plan = await build_production_workflow_plan(db, project_id="project-1")
        assert plan.next_action.type == "approve_shot_plan_revision"
        assert plan.next_action.requested_ids == [shot_plan.id]
        await approve_production_revision(
            db,
            project_id="project-1",
            revision_id=shot_plan.id,
            approved_by="reviewer",
        )
        plan = await build_production_workflow_plan(db, project_id="project-1")
        assert plan.next_action.type == "approve_keyframes"
        assert plan.next_action.requested_ids == ["shot-1", "shot-2"]

        for shot_id in ["shot-1", "shot-2"]:
            keyframe = await create_production_revision(
                db,
                project_id="project-1",
                body=ProductionRevisionCreate(
                    kind="keyframe",
                    scope_type="shot",
                    scope_id=shot_id,
                    payload={"file_id": f"keyframe-{shot_id}"},
                ),
            )
            await approve_production_revision(
                db,
                project_id="project-1",
                revision_id=keyframe.id,
                approved_by="reviewer",
            )
        plan = await build_production_workflow_plan(db, project_id="project-1")
        assert plan.next_action.type == "generate_takes"
        assert plan.next_action.requires_confirmation is True

        db.add_all(
            [
                FileItem(
                    id="video-1",
                    type=FileType.video,
                    name="one",
                    thumbnail="",
                    tags=[],
                    storage_key="videos/one.mp4",
                ),
                FileItem(
                    id="video-2",
                    type=FileType.video,
                    name="two",
                    thumbnail="",
                    tags=[],
                    storage_key="videos/two.mp4",
                ),
            ]
        )
        shot_one = await db.get(Shot, "shot-1")
        shot_two = await db.get(Shot, "shot-2")
        assert shot_one is not None and shot_two is not None
        shot_one.generated_video_file_id = "video-1"
        shot_two.generated_video_file_id = "video-2"
        await db.flush()

        plan = await build_production_workflow_plan(db, project_id="project-1")
        assert plan.current_step == "edit"
        assert plan.next_action.type == "create_edit_revision"
    await engine.dispose()


@pytest.mark.asyncio
async def test_passing_qa_allows_project_linked_final_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_project(db)
        db.add(
            ProjectResearch(
                project_id="project-1",
                entry_mode="preset",
                status="approved",
                brief={},
                sources=[],
                findings=[],
                creative_directions=[{"id": "direction-1"}],
                approved_direction_id="direction-1",
            )
        )
        for kind, payload in [
            ("script", {"script": "approved"}),
            ("shot_plan", {"shot_ids": ["shot-1", "shot-2"]}),
        ]:
            revision = await create_production_revision(
                db,
                project_id="project-1",
                body=ProductionRevisionCreate(kind=kind, payload=payload),
            )
            await approve_production_revision(
                db,
                project_id="project-1",
                revision_id=revision.id,
                approved_by="reviewer",
            )
        for shot_id in ["shot-1", "shot-2"]:
            revision = await create_production_revision(
                db,
                project_id="project-1",
                body=ProductionRevisionCreate(
                    kind="keyframe",
                    scope_type="shot",
                    scope_id=shot_id,
                    payload={"file_id": f"keyframe-{shot_id}"},
                ),
            )
            await approve_production_revision(
                db,
                project_id="project-1",
                revision_id=revision.id,
                approved_by="reviewer",
            )

        files = [
            FileItem(
                id="video-1",
                type=FileType.video,
                name="one",
                thumbnail="",
                tags=[],
                storage_key="videos/one.mp4",
            ),
            FileItem(
                id="video-2",
                type=FileType.video,
                name="two",
                thumbnail="",
                tags=[],
                storage_key="videos/two.mp4",
            ),
            FileItem(
                id="final-video",
                type=FileType.video,
                name="final",
                thumbnail="",
                tags=[],
                storage_key="deliveries/final.mp4",
            ),
        ]
        db.add_all(files)
        shot_one = await db.get(Shot, "shot-1")
        shot_two = await db.get(Shot, "shot-2")
        assert shot_one is not None and shot_two is not None
        shot_one.generated_video_file_id = "video-1"
        shot_two.generated_video_file_id = "video-2"
        await db.flush()

        edit = await create_production_revision(
            db,
            project_id="project-1",
            body=ProductionRevisionCreate(
                kind="edit",
                payload={
                    "schema_version": 1,
                    "timeline": {
                        "schema_version": 1,
                        "canvas": {"width": 1920, "height": 1080, "fps": 30, "background": "#000000"},
                        "video_clips": [
                            {"id": "c1", "shot_id": "shot-1", "file_id": "video-1", "source_in_ms": 0, "source_out_ms": 5000, "transition_to_next": {"type": "cut", "duration_ms": 0}},
                            {"id": "c2", "shot_id": "shot-2", "file_id": "video-2", "source_in_ms": 0, "source_out_ms": 5000, "transition_to_next": {"type": "cut", "duration_ms": 0}},
                        ],
                        "audio_clips": [],
                        "subtitles": [{"id": "s1", "start_ms": 500, "end_ms": 2500, "text": "Meet Bottle", "speaker": "VO"}],
                        "overlays": [{"id": "cta", "type": "cta", "text": "Buy now", "start_ms": 8000, "end_ms": 10000, "position": "bottom"}],
                    },
                },
            ),
        )
        await approve_production_revision(
            db,
            project_id="project-1",
            revision_id=edit.id,
            approved_by="reviewer",
        )
        db.add(
            ProductionArtifact(
                id="render-artifact",
                project_id="project-1",
                artifact_type="render",
                file_id="final-video",
                source_revision_id=edit.id,
                input_fingerprint="render-fingerprint",
                currency="current",
                lifecycle="candidate",
                metadata_json={},
            )
        )
        await db.flush()

        async def fake_inspect_media_file(_file: FileItem) -> dict:
            return {
                "duration_seconds": 10.0,
                "video": {"width": 1920, "height": 1080, "fps": 30.0},
                "audio_stream_count": 0,
                "max_volume_db": None,
                "black_segments": [],
                "freeze_starts": [],
            }

        monkeypatch.setattr(
            "app.ai_video.services.studio.production_control.inspect_media_file",
            fake_inspect_media_file,
        )
        qa = await run_production_qa(
            db,
            project_id="project-1",
            body=ProductionQARunRequest(edit_revision_id=edit.id, run_by="qa"),
        )
        assert qa.status == "passed"
        assert all(check["status"] != "failed" for check in qa.checks)

        delivery = await create_production_delivery(
            db,
            project_id="project-1",
            body=ProductionDeliveryCreate(
                edit_revision_id=edit.id,
                qa_report_id=qa.id,
                delivery_type="final",
                file_ids=["final-video"],
                delivered_by="producer",
            ),
        )
        await db.commit()

        assert delivery.status == "ready"
        assert delivery.manifest["project_id"] == "project-1"
        assert delivery.manifest["qa_status"] == "passed"
        assert len(delivery.manifest["selected_takes"]) == 2
        assert delivery.manifest["sidecars"]["subtitle_count"] == 1
        subtitles = await build_delivery_subtitles_srt(
            db,
            project_id="project-1",
            delivery_id=delivery.id,
        )
        assert "00:00:00,500 --> 00:00:02,500" in subtitles
        assert "VO: Meet Bottle" in subtitles
        plan = await build_production_workflow_plan(db, project_id="project-1")
        assert plan.current_step == "complete"
        assert plan.next_action.type == "none"
    await engine.dispose()
