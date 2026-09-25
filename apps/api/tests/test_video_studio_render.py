from __future__ import annotations

import shutil

import pytest

from app.video_studio import render, store
from app.video_studio.models import ExportClip, ExportRequest, ProjectCreate


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_export_images_to_mp4(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path / "data"))
    project = store.create_project("render@example.com", ProjectCreate(name="Render"))
    assets = store.assets_root("render@example.com", project.id)
    # Portable pixmap keeps the fixture dependency-free while remaining a real image.
    (assets / "red.ppm").write_bytes(b"P6\n2 2\n255\n" + bytes([255, 0, 0] * 4))
    (assets / "blue.ppm").write_bytes(b"P6\n2 2\n255\n" + bytes([0, 0, 255] * 4))

    result = render.export_project(
        "render@example.com",
        project.id,
        ExportRequest(
            name="preview",
            clips=[
                ExportClip(asset_path="red.ppm", duration=0.2),
                ExportClip(asset_path="blue.ppm", duration=0.2),
            ],
            width=320,
            height=240,
            fps=12,
        ),
    )

    output = store.safe_asset_path(assets, result.asset_path)
    assert output.is_file()
    assert output.stat().st_size > 0
    metadata = render.probe_asset("render@example.com", project.id, result.asset_path)
    assert any(stream["codec_type"] == "video" for stream in metadata["streams"])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_export_supports_crossfade_timeline_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path / "data"))
    project = store.create_project("render@example.com", ProjectCreate(name="Render"))
    assets = store.assets_root("render@example.com", project.id)
    (assets / "red.ppm").write_bytes(b"P6\n2 2\n255\n" + bytes([255, 0, 0] * 4))
    (assets / "blue.ppm").write_bytes(b"P6\n2 2\n255\n" + bytes([0, 0, 255] * 4))

    result = render.export_project(
        "render@example.com",
        project.id,
        ExportRequest(
            name="crossfade",
            clips=[
                ExportClip(asset_path="red.ppm", duration=0.5),
                ExportClip(asset_path="blue.ppm", duration=0.5, transition="crossfade"),
            ],
            width=320,
            height=240,
            fps=12,
        ),
    )

    metadata = render.probe_asset("render@example.com", project.id, result.asset_path)
    assert float(metadata["format"]["duration"]) > 0.5
