from __future__ import annotations

import asyncio
import base64
import sqlite3

from app.routers.video_runtime import ManagedMediaResponse
from app.video_studio.models import (
    CanvasCreate,
    CanvasDocument,
    CanvasUpdate,
    MediaJobCreate,
    ProductionKeyframe,
    ProductionShot,
    ProductionState,
    ProductionTake,
    TimelineClip,
    TimelineCommit,
    ScriptCommit,
    DeliveryCreate,
    ProjectCreate,
    ProjectUpdate,
    VideoNode,
)
from app.video_studio import store
from app.video_studio import media_jobs
from app.video_studio import metadata_repository


def test_project_crud_and_canvas_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))

    created = store.create_project("creator@example.com", ProjectCreate(name="Launch film"))
    assert created.name == "Launch film"
    assert store.list_projects("creator@example.com")[0].id == created.id

    canvas = CanvasDocument(
        nodes=[VideoNode(id="brief", type="text", data={"text": "Make it cinematic"})]
    )
    saved = store.save_canvas("creator@example.com", created.id, canvas)
    assert saved.nodes[0].data["text"] == "Make it cinematic"
    assert store.get_project("creator@example.com", created.id).node_count == 1

    updated = store.update_project(
        "creator@example.com", created.id, ProjectUpdate(name="Launch film v2")
    )
    assert updated.name == "Launch film v2"

    store.delete_project("creator@example.com", created.id)
    assert store.list_projects("creator@example.com") == []


def test_projects_are_isolated_by_user(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    store.create_project("one@example.com", ProjectCreate(name="One"))
    store.create_project("two@example.com", ProjectCreate(name="Two"))

    assert [item.name for item in store.list_projects("one@example.com")] == ["One"]
    assert [item.name for item in store.list_projects("two@example.com")] == ["Two"]


def test_asset_paths_cannot_escape_project(tmp_path):
    root = tmp_path.resolve()
    assert store.safe_asset_path(root, "shots/one.png") == root / "shots" / "one.png"

    try:
        store.safe_asset_path(root, "../secret")
    except ValueError as error:
        assert "escapes" in str(error)
    else:
        raise AssertionError("Path traversal must be rejected")


def test_multiple_canvases_are_durable_and_keep_one_active(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project("creator@example.com", ProjectCreate(name="Campaign"))

    second = store.create_canvas(
        "creator@example.com",
        project.id,
        CanvasCreate(name="Storyboard"),
    )
    assert len(second.canvases) == 2
    assert second.active_canvas_id != "main"

    store.save_project_canvas(
        "creator@example.com",
        project.id,
        second.active_canvas_id,
        CanvasDocument(nodes=[VideoNode(id="shot-1", type="text")]),
    )
    store.update_canvas(
        "creator@example.com",
        project.id,
        second.active_canvas_id,
        CanvasUpdate(name="Shot plan"),
    )
    activated = store.activate_canvas("creator@example.com", project.id, "main")
    assert activated.active_canvas_id == "main"
    assert activated.canvas.nodes == []

    restored = store.activate_canvas("creator@example.com", project.id, second.active_canvas_id)
    assert restored.canvas.nodes[0].id == "shot-1"
    assert next(item.name for item in restored.canvases if item.id == second.active_canvas_id) == "Shot plan"

    remaining = store.delete_canvas("creator@example.com", project.id, second.active_canvas_id)
    assert [item.id for item in remaining.canvases] == ["main"]


def test_media_job_writes_generated_asset_without_browser_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project("creator@example.com", ProjectCreate(name="Campaign"))

    async def fake_generate(_request):
        return ManagedMediaResponse(
            media_type="image",
            mime_type="image/png",
            data=base64.b64encode(b"generated-image").decode("ascii"),
        )

    monkeypatch.setattr(media_jobs, "generate_media", fake_generate)

    async def run_job():
        job = media_jobs.create_media_job(
            "creator@example.com",
            project.id,
            MediaJobCreate(media_type="image", prompt="A clean product frame"),
        )
        for _ in range(100):
            await asyncio.sleep(0.01)
            job = store.get_media_job("creator@example.com", project.id, job.id)
            if job.status not in {"queued", "running"}:
                return job
        raise AssertionError("Media job did not finish")

    completed = asyncio.run(run_job())
    assert completed.status == "completed"
    assert completed.result_asset_path
    target = store.safe_asset_path(
        store.assets_root("creator@example.com", project.id),
        completed.result_asset_path,
    )
    assert target.read_bytes() == b"generated-image"


def test_project_metadata_is_read_from_database_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path / "files"))
    monkeypatch.setenv("VIDEO_STUDIO_METADATA_DATABASE", "1")
    database_path = tmp_path / "metadata.db"

    def connect():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(metadata_repository, "_connect", connect)
    monkeypatch.setattr(metadata_repository, "_schema_ready", False)

    project = store.create_project("creator@example.com", ProjectCreate(name="Cloud metadata"))
    project_root = store._project_root("creator@example.com", project.id)
    (project_root / "project.json").unlink()
    (project_root / "canvas.json").unlink()
    (project_root / "canvases" / "main.json").unlink()

    restored = store.get_project("creator@example.com", project.id)
    assert restored.name == "Cloud metadata"
    assert restored.active_canvas_id == "main"

    store.delete_project("creator@example.com", project.id)
    with connect() as connection:
        count = connection.execute("SELECT count(*) FROM video_studio_metadata").fetchone()[0]
    assert count == 0


def test_production_timeline_qa_revision_and_delivery_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    project = store.create_project("producer@example.com", ProjectCreate(name="Campaign"))
    asset = store.safe_asset_path(store.assets_root("producer@example.com", project.id), "takes/shot-1.mp4")
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"video-bytes")
    take = ProductionTake(id="take-1", asset_path="takes/shot-1.mp4")
    keyframe_asset = store.safe_asset_path(store.assets_root("producer@example.com", project.id), "keyframes/shot-1.png")
    keyframe_asset.parent.mkdir(parents=True)
    keyframe_asset.write_bytes(b"image-bytes")
    keyframe = ProductionKeyframe(id="keyframe-1", asset_path="keyframes/shot-1.png", status="approved")
    state = store.save_production_state(
        "producer@example.com",
        project.id,
        ProductionState(
            shots=[ProductionShot(id="shot-1", title="Opening", status="approved", keyframes=[keyframe], selected_keyframe_id=keyframe.id, takes=[take], selected_take_id=take.id)],
            timeline=[TimelineClip(shot_id="shot-1", duration=4)],
        ),
    )
    assert state.shots[0].selected_take_id == "take-1"

    store.commit_script("producer@example.com", project.id, ScriptCommit(content="# Locked script"))
    committed = store.commit_timeline("producer@example.com", project.id, TimelineCommit(label="Client cut"))
    assert committed.revision == 1
    assert committed.timeline_revisions[0].label == "Client cut"
    checked = store.run_production_qa("producer@example.com", project.id)
    assert checked.qa.status == "pass"

    delivered = store.record_delivery(
        "producer@example.com",
        project.id,
        DeliveryCreate(asset_path="takes/shot-1.mp4"),
    )
    assert delivered.deliveries[0].size == len(b"video-bytes")
    assert len(delivered.deliveries[0].sha256) == 64
