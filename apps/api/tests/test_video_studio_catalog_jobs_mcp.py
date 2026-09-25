from __future__ import annotations

import asyncio

import pytest

from app.video_studio import store
from app.video_studio.mcp import build_video_studio_mcp_server
from app.video_studio.models import (
    CatalogImport,
    ExportClip,
    ExportJob,
    ExportRequest,
    ProjectCreate,
    ProjectDocument,
    SkillDefinition,
)


def test_document_catalog_and_export_jobs_are_user_scoped(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    owner = "owner@example.com"
    other = "other@example.com"
    project = store.create_project(owner, ProjectCreate(name="Project"))

    document = store.save_document(owner, project.id, ProjectDocument(content="# Brief"))
    assert store.get_document(owner, project.id).content == "# Brief"
    assert document.updated_at is not None
    with pytest.raises(FileNotFoundError):
        store.get_document(other, project.id)

    catalog = store.get_catalog(owner)
    assert {item.id for item in catalog.skills} >= {"canvas", "storyboard", "continuity"}
    updated = store.save_catalog(
        owner,
        CatalogImport(
            skills=[
                SkillDefinition(
                    id="custom-review",
                    name="Custom review",
                    instructions="Check the delivery.",
                )
            ]
        ),
    )
    assert any(item.id == "custom-review" for item in updated.skills)
    assert not any(item.id == "custom-review" for item in store.get_catalog(other).skills)

    request = ExportRequest(clips=[ExportClip(asset_path="clip.png")])
    job = store.save_export_job(owner, ExportJob(id="a" * 32, project_id=project.id, request=request))
    assert store.get_export_job(owner, project.id, job.id).status == "queued"
    assert [item.id for item in store.list_export_jobs(owner, project.id)] == [job.id]


def test_project_archive_round_trip_uses_a_new_user_scoped_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path / "data"))
    owner = "owner@example.com"
    project = store.create_project(owner, ProjectCreate(name="Archive project", description="Round trip"))
    store.save_document(owner, project.id, ProjectDocument(content="# Archived"))
    asset = store.safe_asset_path(store.assets_root(owner, project.id), "refs/example.txt")
    asset.parent.mkdir(parents=True)
    asset.write_text("asset", encoding="utf-8")

    archive = store.export_project_archive(owner, project.id, tmp_path / "project.zip")
    imported = store.import_project_archive(owner, archive)

    assert imported.id != project.id
    assert imported.name == project.name
    assert store.get_document(owner, imported.id).content == "# Archived"
    assert store.safe_asset_path(store.assets_root(owner, imported.id), "refs/example.txt").read_text() == "asset"


def test_video_studio_mcp_is_https_only_and_exposes_workspace_tools() -> None:
    principals = {"token": {"id": "automation", "email": "automation@example.com"}}
    with pytest.raises(ValueError, match="absolute HTTPS"):
        build_video_studio_mcp_server(
            public_url="http://localhost/video-studio-mcp",
            principals=principals,
        )
    server = build_video_studio_mcp_server(
        public_url="https://video.example.test/video-studio-mcp",
        principals=principals,
    )
    tool_names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {
        "list_video_projects",
        "create_video_project",
        "read_video_project",
        "write_video_canvas",
        "read_video_document",
        "write_video_document",
        "list_video_assets",
        "run_video_agent",
        "generate_video_asset",
        "export_video_project",
        "get_video_extension_catalog",
    } <= tool_names
