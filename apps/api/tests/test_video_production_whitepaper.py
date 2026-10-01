from __future__ import annotations

import sqlite3

import pytest

from datetime import datetime

from app.incept.models import (
    GenerationJob,
    JobStatus,
    Role,
    User,
    VideoProductionBridgeFrameRequest,
    VideoProductionCreateRequest,
    VideoProduction,
    VideoProductionShot,
    VideoProductionShotRenderRequest,
    VideoProductionUpdateRequest,
    VideoProductionProviderSelection,
)
from app.incept.config import Settings
from app.incept.datetime_utils import utcnow_naive
from app.incept import db as incept_db
from app.incept.video_production_capabilities import (
    configured_video_production_capabilities,
    default_video_production_selection,
    validate_video_production_selection,
)
from app.incept.video_production_store import (
    VIDEO_PRODUCTIONS,
    JOBS,
    _refresh_shot_preflight,
    _script_hash,
    _shot_source_signature,
    approve_storyboard,
    archive_video_production,
    create_video_production,
    create_keyframe_job,
    create_production_render_job,
    lock_script_and_create_storyboard,
    list_video_productions,
    list_video_production_events,
    delete_video_production,
    recover_interrupted_video_production_jobs,
    restore_video_production,
    restore_video_production_script_revision,
    update_video_production,
)
from app.incept.store import _uploaded_asset_type


def test_video_shots_default_to_two_alternatives() -> None:
    """A costly generation should offer comparison by default, not a blind retry."""
    shot = VideoProductionShot(id="shot_1", order=1, title="Hook")
    assert shot.generation_variants == 2
    assert VideoProductionShotRenderRequest().variants == 2


def test_uploaded_audio_keeps_its_media_type_for_production_asset_preview() -> None:
    assert _uploaded_asset_type("voiceover.mp3", "audio/mpeg") == "audio"
    assert _uploaded_asset_type("cut.mp4", "video/mp4") == "video"
    assert _uploaded_asset_type("logo.png", "image/png") == "image"


def test_video_production_schema_migration_upgrades_a_legacy_sqlite_database(tmp_path, monkeypatch) -> None:
    """An old project DB receives the activity table and one durable version row."""
    database_path = tmp_path / "legacy-incept.db"
    with sqlite3.connect(database_path) as legacy:
        legacy.execute(
            """CREATE TABLE video_productions (
                production_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
    monkeypatch.setattr(incept_db, "_DB_PATH", database_path)
    monkeypatch.setattr(incept_db, "_LOCAL_DB_SNAPSHOT_DIR", tmp_path / "backups")

    incept_db.init_db()
    first = incept_db.video_production_schema_migration_status()
    incept_db.init_db()
    second = incept_db.video_production_schema_migration_status()

    assert first["ready"] is True
    assert first["missing"] == []
    assert second["applied"] == first["applied"]
    with sqlite3.connect(database_path) as upgraded:
        tables = {
            row[0]
            for row in upgraded.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        applied_count = upgraded.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
    assert "video_production_events" in tables
    assert applied_count == len(incept_db.VIDEO_PRODUCTION_SCHEMA_MIGRATIONS)


def test_first_last_mode_is_downgraded_when_end_scene_is_removed() -> None:
    shot = VideoProductionShot(
        id="shot_1",
        order=1,
        title="Hook",
        keyframe_asset_id="start",
        generation_mode="first_last_frame",
    )
    _refresh_shot_preflight(shot)
    assert shot.generation_mode == "image_to_video"
    assert shot.recommended_transition_strategy == "cut"


def test_end_scene_does_not_force_first_last_interpolation() -> None:
    """Editors may keep an end image for a later cut while using I2V now."""
    shot = VideoProductionShot(
        id="shot_1",
        order=1,
        title="Hook",
        keyframe_asset_id="start",
        end_keyframe_asset_id="possible-next-scene",
        generation_mode="image_to_video",
    )
    _refresh_shot_preflight(shot)
    assert shot.generation_mode == "image_to_video"
    assert shot.motion_feasibility == "not_checked"


def test_generation_signature_tracks_continuity_inputs() -> None:
    shot = VideoProductionShot(id="shot_1", order=1, title="Hook", keyframe_asset_id="start")
    first = _shot_source_signature(shot)
    shot.bridge_source_video_asset_id = "take_1"
    shot.bridge_timestamp_seconds = 3.8
    second = _shot_source_signature(shot)
    assert first != second


def test_bridge_frame_request_requires_a_nonnegative_timestamp() -> None:
    assert VideoProductionBridgeFrameRequest(timestamp_seconds=0).timestamp_seconds == 0
    with pytest.raises(ValueError):
        VideoProductionBridgeFrameRequest(timestamp_seconds=-0.1)


def test_render_requires_an_explicitly_selected_take() -> None:
    """A new candidate cannot enter an edit merely because it is listed first."""
    production = VideoProduction(
        production_id="vprod_selected_take_test",
        workspace_id="workspace_test",
        created_by="user_test",
        shots=[VideoProductionShot(
            id="shot_1",
            order=1,
            title="Hook",
            status="ready",
            video_asset_ids=["take_1"],
            selected_video_asset_id=None,
        )],
    )
    user = User(id="user_test", name="Test User", email="test@example.com", role=Role.user, team="test")
    VIDEO_PRODUCTIONS[production.production_id] = production
    try:
        with pytest.raises(ValueError, match="Generate and select a video take"):
            create_production_render_job(production.production_id, user)
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)


def test_create_persists_intake_in_the_initial_project_record() -> None:
    """Draft setup must not depend on a second write after project creation."""
    user = User(id="create_test_user", name="Test User", email="test@example.com", role=Role.user, team="test")
    request = VideoProductionCreateRequest(
        workspace_id="workspace_test",
        title="CTV launch",
        target_seconds=30,
        aspect_ratio="16:9",
        resolution="1080p",
        brief="Launch spot with approved product stills.",
        video_setup={"video_type": "CTV composition", "platform": "CTV"},
    )
    production = create_video_production(request, user)
    try:
        assert production.brief == "Launch spot with approved product stills."
        assert production.video_setup.video_type == "CTV composition"
        assert production.video_setup.platform == "CTV"
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)


def test_project_visibility_and_mutation_are_owner_scoped() -> None:
    owner = User(id="owner_user", name="Owner", email="owner@example.com", role=Role.user, team="test")
    other = User(id="other_user", name="Other", email="other@example.com", role=Role.user, team="test")
    manager = User(id="manager_user", name="Manager", email="manager@example.com", role=Role.manager, team="test")
    production = create_video_production(
        VideoProductionCreateRequest(workspace_id="access_workspace", title="Owner-only production"), owner,
    )
    try:
        assert list_video_productions("access_workspace", other) == []
        with pytest.raises(PermissionError, match="Only workspace operators"):
            list_video_productions("access_workspace", other, scope="all")
        with pytest.raises(PermissionError, match="not available"):
            archive_video_production(production.production_id, other)
        assert production.production_id in {
            item.production_id for item in list_video_productions("access_workspace", manager, scope="all")
        }
        archived = archive_video_production(production.production_id, manager)
        assert archived.archived_at is not None
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)


def test_project_activity_events_are_durable_revision_receipts_and_owner_scoped() -> None:
    owner = User(id="event_owner", name="Owner", email="owner@example.com", role=Role.user, team="test")
    other = User(id="event_other", name="Other", email="other@example.com", role=Role.user, team="test")
    production = create_video_production(
        VideoProductionCreateRequest(workspace_id="event_workspace", title="Event record"), owner,
    )
    try:
        updated = update_video_production(
            production.production_id,
            VideoProductionUpdateRequest(title="Updated event record", expected_revision=production.state_revision),
            owner,
        )
        events = list_video_production_events(updated.production_id, owner)
        assert [event.event_type for event in events[:2]] == ["project.updated", "project.created"]
        assert events[0].state_revision == updated.state_revision
        assert events[1].actor_user_id == owner.id
        with pytest.raises(PermissionError, match="not available"):
            list_video_production_events(updated.production_id, other)
    finally:
        delete_video_production(production.production_id, owner)


def test_provider_catalogue_only_exposes_deployment_owned_models() -> None:
    settings = Settings(
        vertex_video_analysis_model="text-confirmed",
        vertex_gemini_image_model="image-confirmed",
        vertex_veo_fast_model="video-fast-confirmed",
        vertex_veo_model="video-quality-confirmed",
        vertex_lyria_model="audio-confirmed",
        vertex_lyria_enabled=True,
    )
    catalogue = configured_video_production_capabilities(settings)
    assert [option.model for option in catalogue.text] == ["text-confirmed"]
    assert [option.model for option in catalogue.video] == ["video-fast-confirmed", "video-quality-confirmed"]
    selection = default_video_production_selection(settings)
    assert selection.image.model == "image-confirmed"
    assert validate_video_production_selection(selection, settings) == selection
    with pytest.raises(ValueError, match="not configured"):
        validate_video_production_selection(
            VideoProductionProviderSelection.model_validate({
                "text": {"provider": "google-vertex-ai", "model": "unapproved-browser-value"},
            }),
            settings,
        )


def test_create_rejects_unconfigured_provider_model_pairs() -> None:
    user = User(id="provider_validation_user", name="Test User", email="test@example.com", role=Role.user, team="test")
    request = VideoProductionCreateRequest(
        workspace_id="workspace_test",
        title="Rejected provider selection",
        video_setup={
            "provider_selection": {
                "video": {"provider": "unknown", "model": "not-approved"},
            },
        },
    )
    with pytest.raises(ValueError, match="not configured"):
        create_video_production(request, user)


def test_project_model_selection_can_be_saved_and_tampering_is_rejected() -> None:
    user = User(id="provider_update_user", name="Test User", email="test@example.com", role=Role.user, team="test")
    production = create_video_production(VideoProductionCreateRequest(workspace_id="workspace_test", title="Model update"), user)
    try:
        saved = update_video_production(
            production.production_id,
            VideoProductionUpdateRequest(
                video_setup={
                    **production.video_setup.model_dump(),
                    "provider_selection": production.video_setup.provider_selection.model_dump(),
                },
                expected_revision=production.state_revision,
            ),
            user,
        )
        assert saved.video_setup.provider_selection.video.model == production.video_setup.provider_selection.video.model
        with pytest.raises(ValueError, match="not configured"):
            update_video_production(
                production.production_id,
                VideoProductionUpdateRequest(
                    video_setup={
                        **saved.video_setup.model_dump(),
                        "provider_selection": {
                            **saved.video_setup.provider_selection.model_dump(),
                            "video": {"provider": "tampered", "model": "not-approved"},
                        },
                    },
                    expected_revision=saved.state_revision,
                ),
                user,
            )
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)


def test_archive_hides_a_project_without_destroying_it_and_restore_recovers_it() -> None:
    user = User(id="archive_test_user", name="Test User", email="test@example.com", role=Role.user, team="test")
    production = create_video_production(
        VideoProductionCreateRequest(workspace_id="archive_workspace", title="Retain this production"),
        user,
    )
    try:
        archived = archive_video_production(production.production_id, user)
        assert archived.archived_at is not None
        assert archived.archived_by == user.id
        assert production.production_id not in {
            item.production_id for item in list_video_productions("archive_workspace", user)
        }
        assert production.production_id in {
            item.production_id
            for item in list_video_productions("archive_workspace", user, include_archived=True)
        }
        restored = restore_video_production(production.production_id, user)
        assert restored.archived_at is None
        assert restored.archived_by is None
        assert production.production_id in {
            item.production_id for item in list_video_productions("archive_workspace", user)
        }
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)


def test_restart_marks_interrupted_production_job_retryable_without_selecting_output(monkeypatch) -> None:
    job = GenerationJob(
        job_id="job_interrupted_production",
        workspace_id="workspace_test",
        status=JobStatus.running,
        progress=62,
        lineage_key="uat-interrupted-keyframe",
        message="Generating visual-development frame",
        tool_id="video-production-keyframe",
        title="Interrupted visual-development frame",
        output_asset_ids=[],
        created_at=utcnow_naive(),
        updated_at=utcnow_naive(),
    )
    JOBS[job.job_id] = job
    monkeypatch.setattr("app.incept.video_production_store.upsert_job", lambda _job: None)
    try:
        assert recover_interrupted_video_production_jobs() == [job.job_id]
        assert job.status == JobStatus.failed
        assert job.progress == 0
        assert "retry this exact operation" in job.message
        assert job.output_asset_ids == []
    finally:
        JOBS.pop(job.job_id, None)


def test_lock_rejects_a_working_copy_that_diverged_from_structured_script() -> None:
    user = User(id="script_sync_user", name="Test User", email="test@example.com", role=Role.user, team="test")
    production = VideoProduction(
        production_id="vprod_script_sync_test",
        workspace_id="workspace_test",
        created_by=user.id,
    )
    production.script.raw_script = "Human-reviewed working copy"
    production.script.structured_raw_script_hash = _script_hash("Earlier structured copy")
    VIDEO_PRODUCTIONS[production.production_id] = production
    try:
        with pytest.raises(ValueError, match="Restructure draft"):
            lock_script_and_create_storyboard(production.production_id, user)
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)


def test_keyframe_requires_explicit_storyboard_approval() -> None:
    user = User(id="storyboard_gate_user", name="Test User", email="test@example.com", role=Role.user, team="test")
    production = VideoProduction(
        production_id="vprod_storyboard_gate_test",
        workspace_id="workspace_test",
        created_by=user.id,
        shots=[VideoProductionShot(id="shot_1", order=1, title="Hook", visual="Product enters frame", action="Camera pushes in")],
    )
    production.script.status = "locked"
    VIDEO_PRODUCTIONS[production.production_id] = production
    try:
        with pytest.raises(ValueError, match="Approve the reviewed storyboard"):
            create_keyframe_job(production.production_id, "shot_1", user)
        approved = approve_storyboard(production.production_id, user)
        assert approved.storyboard_approved_at is not None
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)


def test_script_edit_revokes_storyboard_approval() -> None:
    user = User(id="approval_revoke_user", name="Test User", email="test@example.com", role=Role.user, team="test")
    production = VideoProduction(
        production_id="vprod_approval_revoke_test",
        workspace_id="workspace_test",
        created_by=user.id,
    )
    production.storyboard_approved_at = production.created_at
    production.storyboard_approved_revision = production.state_revision
    VIDEO_PRODUCTIONS[production.production_id] = production
    try:
        updated = update_video_production(
            production.production_id,
            VideoProductionUpdateRequest(script=production.script),
            user,
        )
        assert updated.storyboard_approved_at is None
        assert updated.storyboard_approved_revision is None
        assert updated.script_revisions[-1].reason == "Manual working-script save"
        assert updated.script_revisions[-1].actor_user_id == user.id
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)


def test_script_checkpoint_restore_creates_a_new_draft_and_revokes_approval() -> None:
    """A receipt is a real restorable checkpoint, never an in-place rewind."""
    user = User(id="checkpoint_restore_user", name="Test User", email="test@example.com", role=Role.user, team="test")
    production = VideoProduction(
        production_id="vprod_checkpoint_restore_test",
        workspace_id="workspace_test",
        created_by=user.id,
    )
    production.script.raw_script = "Checkpoint reading copy"
    production.script.creative_goal = "Introduce the product clearly"
    production.script.revision = 2
    production.script.status = "locked"
    VIDEO_PRODUCTIONS[production.production_id] = production
    try:
        saved = update_video_production(
            production.production_id,
            VideoProductionUpdateRequest(script=production.script),
            user,
        )
        checkpoint = saved.script_revisions[-1]
        assert checkpoint.script is not None
        assert checkpoint.script.raw_script == "Checkpoint reading copy"

        # Simulate a later, approved production baseline. Restoring must leave
        # the old snapshot intact and produce a fresh editable revision.
        saved.script.raw_script = "Later baseline"
        saved.script.revision = 5
        saved.script.status = "locked"
        saved.storyboard_approved_at = utcnow_naive()
        saved.storyboard_approved_revision = saved.state_revision
        restored = restore_video_production_script_revision(
            saved.production_id,
            checkpoint.revision_id,
            user,
        )

        assert restored.script.raw_script == "Checkpoint reading copy"
        assert restored.script.creative_goal == "Introduce the product clearly"
        assert restored.script.status == "draft"
        assert restored.script.revision == 6
        assert restored.storyboard_approved_at is None
        assert restored.storyboard_approved_revision is None
        assert restored.script_revisions[-1].reason == "Restored checkpoint r2"
        assert restored.script_revisions[-1].script is not None
        assert restored.script_revisions[-1].script.raw_script == "Checkpoint reading copy"
    finally:
        VIDEO_PRODUCTIONS.pop(production.production_id, None)
