"""Project-scoped production revisions, artifacts and authoritative workflow plan."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.dependencies import get_db
from app.ai_video.models.production_control import ProductionArtifact, ProductionDelivery, ProductionQAReport, ProductionRevision
from app.ai_video.schemas.common import ApiResponse, created_response, success_response
from app.ai_video.schemas.studio.production_control import (
    ProductionArtifactCreate,
    ProductionArtifactRead,
    ProductionArtifactSelectRequest,
    ProductionDeliveryCreate,
    ProductionDeliveryRead,
    ProductionQAReportRead,
    ProductionQARunRequest,
    ProductionRevisionApprovalRequest,
    ProductionRevisionCreate,
    ProductionRevisionRead,
    ProductionWorkflowPlanRead,
    ShotPlanSnapshotRequest,
)
from app.ai_video.services.studio.production_control import (
    approve_production_revision,
    build_delivery_subtitles_srt,
    build_production_workflow_plan,
    create_production_artifact,
    create_production_delivery,
    create_production_revision,
    get_production_delivery,
    run_production_qa,
    select_production_artifact,
    snapshot_shot_plan_revision,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/production/plan",
    response_model=ApiResponse[ProductionWorkflowPlanRead],
    summary="Get the authoritative production workflow plan",
)
async def get_production_plan(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionWorkflowPlanRead]:
    return success_response(await build_production_workflow_plan(db, project_id=project_id))


@router.post(
    "/projects/{project_id}/production/revisions",
    response_model=ApiResponse[ProductionRevisionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an immutable production revision",
)
async def create_revision(
    project_id: str,
    body: ProductionRevisionCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionRevisionRead]:
    revision = await create_production_revision(db, project_id=project_id, body=body)
    return created_response(ProductionRevisionRead.model_validate(revision))


@router.post(
    "/projects/{project_id}/production/shot-plan/snapshot",
    response_model=ApiResponse[ProductionRevisionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Snapshot persisted shot cards into an immutable Shot Plan draft",
)
async def snapshot_shot_plan(
    project_id: str,
    body: ShotPlanSnapshotRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionRevisionRead]:
    revision = await snapshot_shot_plan_revision(
        db,
        project_id=project_id,
        created_by=body.created_by,
    )
    return created_response(ProductionRevisionRead.model_validate(revision))


@router.get(
    "/projects/{project_id}/production/revisions",
    response_model=ApiResponse[list[ProductionRevisionRead]],
    summary="List production revisions",
)
async def list_revisions(
    project_id: str,
    kind: str | None = Query(None),
    scope_type: str | None = Query(None),
    scope_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ProductionRevisionRead]]:
    stmt = select(ProductionRevision).where(ProductionRevision.project_id == project_id)
    if kind:
        stmt = stmt.where(ProductionRevision.kind == kind)
    if scope_type:
        stmt = stmt.where(ProductionRevision.scope_type == scope_type)
    if scope_id:
        stmt = stmt.where(ProductionRevision.scope_id == scope_id)
    stmt = stmt.order_by(
        ProductionRevision.kind.asc(),
        ProductionRevision.scope_type.asc(),
        ProductionRevision.scope_id.asc(),
        ProductionRevision.revision_number.desc(),
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return success_response([ProductionRevisionRead.model_validate(row) for row in rows])


@router.post(
    "/projects/{project_id}/production/revisions/{revision_id}/approve",
    response_model=ApiResponse[ProductionRevisionRead],
    summary="Approve a production revision and supersede the previous approved revision",
)
async def approve_revision(
    project_id: str,
    revision_id: str,
    body: ProductionRevisionApprovalRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionRevisionRead]:
    revision = await approve_production_revision(
        db,
        project_id=project_id,
        revision_id=revision_id,
        approved_by=body.approved_by,
    )
    return success_response(ProductionRevisionRead.model_validate(revision))


@router.post(
    "/projects/{project_id}/production/artifacts",
    response_model=ApiResponse[ProductionArtifactRead],
    status_code=status.HTTP_201_CREATED,
    summary="Register a production artifact",
)
async def create_artifact(
    project_id: str,
    body: ProductionArtifactCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionArtifactRead]:
    artifact = await create_production_artifact(db, project_id=project_id, body=body)
    return created_response(ProductionArtifactRead.model_validate(artifact))


@router.get(
    "/projects/{project_id}/production/artifacts",
    response_model=ApiResponse[list[ProductionArtifactRead]],
    summary="List production artifacts with lifecycle and currency",
)
async def list_artifacts(
    project_id: str,
    artifact_type: str | None = Query(None),
    shot_id: str | None = Query(None),
    currency: str | None = Query(None),
    lifecycle: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ProductionArtifactRead]]:
    stmt = select(ProductionArtifact).where(ProductionArtifact.project_id == project_id)
    if artifact_type:
        stmt = stmt.where(ProductionArtifact.artifact_type == artifact_type)
    if shot_id:
        stmt = stmt.where(ProductionArtifact.shot_id == shot_id)
    if currency:
        stmt = stmt.where(ProductionArtifact.currency == currency)
    if lifecycle:
        stmt = stmt.where(ProductionArtifact.lifecycle == lifecycle)
    stmt = stmt.order_by(ProductionArtifact.created_at.desc())
    rows = list((await db.execute(stmt)).scalars().all())
    return success_response([ProductionArtifactRead.model_validate(row) for row in rows])


@router.post(
    "/projects/{project_id}/production/artifacts/{artifact_id}/select",
    response_model=ApiResponse[ProductionArtifactRead],
    summary="Explicitly select one artifact without deleting its siblings",
)
async def select_artifact(
    project_id: str,
    artifact_id: str,
    body: ProductionArtifactSelectRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionArtifactRead]:
    artifact = await select_production_artifact(
        db,
        project_id=project_id,
        artifact_id=artifact_id,
        selected_by=body.selected_by,
    )
    return success_response(ProductionArtifactRead.model_validate(artifact))


@router.post(
    "/projects/{project_id}/production/qa/run",
    response_model=ApiResponse[ProductionQAReportRead],
    summary="Run deterministic production QA for an approved edit revision",
)
async def run_qa(
    project_id: str,
    body: ProductionQARunRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionQAReportRead]:
    report = await run_production_qa(db, project_id=project_id, body=body)
    return success_response(ProductionQAReportRead.model_validate(report))


@router.get(
    "/projects/{project_id}/production/qa",
    response_model=ApiResponse[list[ProductionQAReportRead]],
    summary="List production QA reports",
)
async def list_qa_reports(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ProductionQAReportRead]]:
    stmt = (
        select(ProductionQAReport)
        .where(ProductionQAReport.project_id == project_id)
        .order_by(ProductionQAReport.created_at.desc())
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return success_response([ProductionQAReportRead.model_validate(row) for row in rows])


@router.post(
    "/projects/{project_id}/production/deliveries",
    response_model=ApiResponse[ProductionDeliveryRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a project-linked delivery with a source manifest",
)
async def create_delivery(
    project_id: str,
    body: ProductionDeliveryCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProductionDeliveryRead]:
    delivery = await create_production_delivery(db, project_id=project_id, body=body)
    return created_response(ProductionDeliveryRead.model_validate(delivery))


@router.get(
    "/projects/{project_id}/production/deliveries",
    response_model=ApiResponse[list[ProductionDeliveryRead]],
    summary="List project deliveries",
)
async def list_deliveries(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ProductionDeliveryRead]]:
    stmt = (
        select(ProductionDelivery)
        .where(ProductionDelivery.project_id == project_id)
        .order_by(ProductionDelivery.created_at.desc())
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return success_response([ProductionDeliveryRead.model_validate(row) for row in rows])


@router.get(
    "/projects/{project_id}/production/deliveries/{delivery_id}/manifest.json",
    summary="Download a durable production manifest",
)
async def download_delivery_manifest(
    project_id: str,
    delivery_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    delivery = await get_production_delivery(db, project_id=project_id, delivery_id=delivery_id)
    content = json.dumps(delivery.manifest, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{delivery.id}-manifest.json"'},
    )


@router.get(
    "/projects/{project_id}/production/deliveries/{delivery_id}/subtitles.srt",
    summary="Download SRT subtitles from the approved edit revision",
)
async def download_delivery_subtitles(
    project_id: str,
    delivery_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    content = await build_delivery_subtitles_srt(db, project_id=project_id, delivery_id=delivery_id)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-subrip; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{delivery_id}-subtitles.srt"'},
    )


__all__ = ["router"]
