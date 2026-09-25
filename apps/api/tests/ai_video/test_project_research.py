from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai_video.core.db import Base
from app.ai_video.api.v1.routes.studio.project_agent import _system_prompt
from app.ai_video.main import app as ai_video_app
from app.ai_video.models.studio import ProjectResearch
from app.ai_video.models.studio import Project
from app.ai_video.schemas.studio.research import CreativeBrief, ProjectResearchWrite
from app.ai_video.services.studio.project_research_context import format_approved_creative_brief


def _brief() -> CreativeBrief:
    return CreativeBrief(
        advertiser_vertical="E-commerce / DTC",
        delivery_channel="CTV",
        product_url="https://example.com/product",
        market="US",
    )


def test_research_brief_requires_product_url_or_asset() -> None:
    with pytest.raises(ValidationError):
        CreativeBrief(advertiser_vertical="Gaming", delivery_channel="Mobile in-app")


def test_approval_must_reference_a_direction() -> None:
    with pytest.raises(ValidationError):
        ProjectResearchWrite(
            brief=_brief(),
            status="approved",
            approved_direction_id="missing",
            creative_directions=[],
        )


def test_preset_requires_preapproved_direction() -> None:
    with pytest.raises(ValidationError):
        ProjectResearchWrite(entry_mode="preset", brief=_brief(), status="draft")


def test_approved_context_uses_direction_without_copying_source_urls() -> None:
    research = ProjectResearch(
        project_id="p1",
        entry_mode="research",
        status="approved",
        brief=_brief().model_dump(mode="json"),
        sources=[{"id": "s1", "url": "https://competitor.example/video", "notes": "copy this"}],
        findings=[],
        creative_directions=[{
            "id": "d1",
            "name": "Product proof",
            "creative_format": "Product demo",
            "creative_playbook": "Problem-solution",
            "visual_direction": "Bright tabletop macro photography",
            "script_direction": "Open on the pain point, then prove the benefit",
            "rationale": "The product proof is visible",
            "evidence_finding_ids": [],
        }],
        approved_direction_id="d1",
    )

    rendered = format_approved_creative_brief(research)

    assert "Product demo" in rendered
    assert "Bright tabletop" in rendered
    assert "competitor.example" not in rendered
    assert "copy this" not in rendered


def test_research_and_agent_tables_are_registered() -> None:
    assert "project_research" in Base.metadata.tables
    assert "project_agent_sessions" in Base.metadata.tables
    assert "project_agent_messages" in Base.metadata.tables


def test_agent_prompt_uses_approved_direction_without_raw_reference_sources() -> None:
    project = Project(
        id="p1",
        name="Launch campaign",
        description="CTV product launch",
        style="广告通用",
        visual_style="现实",
        seed=0,
        unify_style=True,
        progress=0,
    )
    research = ProjectResearch(
        project_id="p1",
        entry_mode="research",
        status="approved",
        brief=_brief().model_dump(mode="json"),
        sources=[{"id": "s1", "url": "https://competitor.example/video", "notes": "copy this"}],
        findings=[],
        creative_directions=[{
            "id": "d1",
            "name": "Product proof",
            "creative_format": "Product demo",
            "creative_playbook": "Problem-solution",
            "visual_direction": "Bright tabletop macro photography",
            "script_direction": "Open on the pain point, then prove the benefit",
            "rationale": "The product proof is visible",
            "evidence_finding_ids": [],
        }],
        approved_direction_id="d1",
    )

    rendered = _system_prompt(project, research)

    assert "Product proof" in rendered
    assert "competitor.example" not in rendered
    assert "copy this" not in rendered


def test_research_and_agent_routes_are_registered() -> None:
    paths = {route.path for route in ai_video_app.routes}

    assert "/api/v1/studio/projects/{project_id}/research" in paths
    assert "/api/v1/studio/projects/{project_id}/research/approve" in paths
    assert "/api/v1/studio/projects/{project_id}/agent/chat" in paths
    assert "/api/v1/studio/projects/{project_id}/agent/sessions/{session_id}" in paths
