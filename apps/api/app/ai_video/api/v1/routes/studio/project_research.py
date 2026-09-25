"""Project-scoped advertising research and creative-direction approval."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.dependencies import get_db
from app.ai_video.models.studio import Project, ProjectResearch
from app.ai_video.schemas.common import ApiResponse, success_response
from app.ai_video.schemas.studio.research import (
    CreativeBrief,
    ProjectResearchRead,
    ProjectResearchWrite,
    ResearchApprovalRequest,
)
from app.ai_video.services.common import entity_not_found, get_or_404

router = APIRouter()


def _missing_research(project_id: str) -> ProjectResearchRead:
    return ProjectResearchRead.model_construct(
        project_id=project_id,
        exists=False,
        entry_mode="research",
        status="draft",
        brief=CreativeBrief.model_construct(
            advertiser_vertical="",
            delivery_channel="",
            product_url=None,
            product_asset_file_ids=[],
            market=None,
            creative_format=None,
            creative_playbook=None,
            visual_direction=None,
            script_direction=None,
        ),
        sources=[],
        findings=[],
        creative_directions=[],
        approved_direction_id=None,
    )


@router.get(
    "/projects/{project_id}/research",
    response_model=ApiResponse[ProjectResearchRead],
    summary="Get project advertising research",
)
async def get_project_research(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectResearchRead]:
    await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    obj = await db.get(ProjectResearch, project_id)
    if obj is None:
        return success_response(_missing_research(project_id))
    return success_response(ProjectResearchRead.model_validate(obj))


@router.put(
    "/projects/{project_id}/research",
    response_model=ApiResponse[ProjectResearchRead],
    summary="Save project advertising research",
)
async def save_project_research(
    project_id: str,
    body: ProjectResearchWrite,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectResearchRead]:
    await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    obj = await db.get(ProjectResearch, project_id)
    values = body.model_dump(mode="json")
    if obj is None:
        obj = ProjectResearch(project_id=project_id, **values)
        db.add(obj)
    else:
        for key, value in values.items():
            setattr(obj, key, value)
    await db.flush()
    await db.refresh(obj)
    return success_response(ProjectResearchRead.model_validate(obj))


@router.post(
    "/projects/{project_id}/research/approve",
    response_model=ApiResponse[ProjectResearchRead],
    summary="Approve a project creative direction",
)
async def approve_project_direction(
    project_id: str,
    body: ResearchApprovalRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectResearchRead]:
    await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    obj = await db.get(ProjectResearch, project_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project research has not been created")
    direction_ids = {item.get("id") for item in obj.creative_directions if isinstance(item, dict)}
    if body.direction_id not in direction_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Creative direction not found")
    obj.approved_direction_id = body.direction_id
    obj.status = "approved"
    await db.flush()
    await db.refresh(obj)
    return success_response(ProjectResearchRead.model_validate(obj))


__all__ = ["router"]
