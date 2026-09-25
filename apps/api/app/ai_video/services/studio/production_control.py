from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_video.models.production_control import (
    ProductionArtifact,
    ProductionAuditEvent,
    ProductionDelivery,
    ProductionQAReport,
    ProductionRevision,
)
from app.ai_video.models.studio import (
    Chapter,
    FileItem,
    Product,
    Project,
    ProjectResearch,
    Shot,
    ShotDetail,
    ShotDialogLine,
    ShotFrameImage,
)
from app.ai_video.models.task_links import GenerationTaskLink
from app.ai_video.schemas.studio.production_control import (
    ProductionArtifactCreate,
    ProductionDeliveryCreate,
    ProductionQARunRequest,
    ProductionRevisionCreate,
    ProductionWorkflowPlanRead,
    WorkflowArtifactSummary,
    WorkflowNextAction,
    WorkflowProblem,
)
from app.ai_video.schemas.studio.editing import EditDocument
from app.ai_video.services.common import entity_not_found
from app.ai_video.services.studio.media_qa import inspect_media_file


def canonical_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _serialized_enum(value: Any) -> Any:
    return getattr(value, "value", value)


async def _audit(
    db: AsyncSession,
    *,
    project_id: str,
    actor: str | None,
    action: str,
    target_type: str,
    target_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        ProductionAuditEvent(
            id=str(uuid4()),
            project_id=project_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
            created_at=datetime.now(UTC),
        )
    )


async def create_production_revision(
    db: AsyncSession,
    *,
    project_id: str,
    body: ProductionRevisionCreate,
) -> ProductionRevision:
    project = await db.get(Project, project_id, with_for_update=True)
    if project is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Project"))

    scope_id = project_id if body.scope_type == "project" else str(body.scope_id)
    if body.scope_type == "chapter":
        chapter = await db.get(Chapter, scope_id)
        if chapter is None or chapter.project_id != project_id:
            raise HTTPException(status_code=404, detail=entity_not_found("Chapter"))
    elif body.scope_type == "shot":
        shot_stmt = (
            select(Shot)
            .join(Chapter, Chapter.id == Shot.chapter_id)
            .where(Shot.id == scope_id, Chapter.project_id == project_id)
        )
        if (await db.execute(shot_stmt)).scalars().first() is None:
            raise HTTPException(status_code=404, detail=entity_not_found("Shot"))

    if body.parent_revision_id:
        parent = await db.get(ProductionRevision, body.parent_revision_id)
        if parent is None or parent.project_id != project_id:
            raise HTTPException(status_code=404, detail=entity_not_found("Parent revision"))

    version_stmt = select(func.max(ProductionRevision.revision_number)).where(
        ProductionRevision.project_id == project_id,
        ProductionRevision.scope_type == body.scope_type,
        ProductionRevision.scope_id == scope_id,
        ProductionRevision.kind == body.kind,
    )
    revision_number = int(await db.scalar(version_stmt) or 0) + 1
    payload = dict(body.payload)
    research = await db.get(ProjectResearch, project_id)
    upstream_stmt = select(ProductionRevision).where(
        ProductionRevision.project_id == project_id,
        ProductionRevision.state == "approved",
    )
    upstream = list((await db.execute(upstream_stmt)).scalars().all())
    selected_products = list(
        (
            await db.execute(
                select(Product).where(
                    Product.project_id == project_id,
                    Product.selected_asset_id.is_not(None),
                )
            )
        ).scalars().all()
    )
    payload["_lineage"] = {
        "creative_direction_id": (
            research.approved_direction_id
            if research is not None and research.status == "approved"
            else None
        ),
        "approved_upstream_revisions": [
            {
                "id": item.id,
                "kind": item.kind,
                "scope_type": item.scope_type,
                "scope_id": item.scope_id,
                "input_fingerprint": item.input_fingerprint,
            }
            for item in upstream
            if item.kind != body.kind
        ],
        "selected_product_assets": [
            {"product_id": item.id, "asset_id": item.selected_asset_id}
            for item in selected_products
        ],
    }
    fingerprint = canonical_fingerprint(
        {
            "kind": body.kind,
            "scope_type": body.scope_type,
            "scope_id": scope_id,
            "parent_revision_id": body.parent_revision_id,
            "payload": payload,
        }
    )
    revision = ProductionRevision(
        id=str(uuid4()),
        project_id=project_id,
        scope_type=body.scope_type,
        scope_id=scope_id,
        kind=body.kind,
        revision_number=revision_number,
        state="draft",
        parent_revision_id=body.parent_revision_id,
        payload=payload,
        input_fingerprint=fingerprint,
        created_by=body.created_by,
    )
    db.add(revision)
    await _audit(
        db,
        project_id=project_id,
        actor=body.created_by,
        action="revision.created",
        target_type=body.kind,
        target_id=revision.id,
        detail={"scope_type": body.scope_type, "scope_id": scope_id, "revision_number": revision_number},
    )
    await db.flush()
    await db.refresh(revision)
    return revision


async def approve_production_revision(
    db: AsyncSession,
    *,
    project_id: str,
    revision_id: str,
    approved_by: str | None,
) -> ProductionRevision:
    revision = await db.get(ProductionRevision, revision_id, with_for_update=True)
    if revision is None or revision.project_id != project_id:
        raise HTTPException(status_code=404, detail=entity_not_found("Production revision"))

    sibling_stmt = (
        select(ProductionRevision)
        .where(
            ProductionRevision.project_id == project_id,
            ProductionRevision.scope_type == revision.scope_type,
            ProductionRevision.scope_id == revision.scope_id,
            ProductionRevision.kind == revision.kind,
            ProductionRevision.state == "approved",
        )
        .with_for_update()
    )
    for sibling in (await db.execute(sibling_stmt)).scalars().all():
        if sibling.id != revision.id:
            sibling.state = "superseded"

    revision.state = "approved"
    revision.approved_by = approved_by
    revision.approved_at = datetime.now(UTC)

    artifact_stmt = select(ProductionArtifact).where(
        ProductionArtifact.project_id == project_id,
        ProductionArtifact.currency == "current",
    )
    if revision.scope_type == "shot":
        artifact_stmt = artifact_stmt.where(ProductionArtifact.shot_id == revision.scope_id)
    if revision.kind in {"script", "shot_plan", "keyframe", "motion_prompt"}:
        for artifact in (await db.execute(artifact_stmt.with_for_update())).scalars().all():
            if artifact.source_revision_id and artifact.source_revision_id != revision.id:
                artifact.currency = "stale"

    await _audit(
        db,
        project_id=project_id,
        actor=approved_by,
        action="revision.approved",
        target_type=revision.kind,
        target_id=revision.id,
        detail={"revision_number": revision.revision_number, "input_fingerprint": revision.input_fingerprint},
    )
    await db.flush()
    await db.refresh(revision)
    return revision


async def snapshot_shot_plan_revision(
    db: AsyncSession,
    *,
    project_id: str,
    created_by: str | None,
) -> ProductionRevision:
    """Create a draft Shot Plan revision from the project's persisted shot cards."""
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Project"))

    rows = list(
        (
            await db.execute(
                select(Shot, Chapter, ShotDetail)
                .join(Chapter, Chapter.id == Shot.chapter_id)
                .outerjoin(ShotDetail, ShotDetail.id == Shot.id)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.index.asc(), Shot.index.asc())
            )
        ).all()
    )
    if not rows:
        raise HTTPException(status_code=409, detail="Create at least one persisted shot before snapshotting a shot plan")

    shot_ids = [shot.id for shot, _, _ in rows]
    dialogue_rows = list(
        (
            await db.execute(
                select(ShotDialogLine)
                .where(ShotDialogLine.shot_detail_id.in_(shot_ids))
                .order_by(ShotDialogLine.shot_detail_id.asc(), ShotDialogLine.index.asc())
            )
        ).scalars().all()
    )
    dialogue_by_shot: dict[str, list[dict[str, Any]]] = {}
    for line in dialogue_rows:
        dialogue_by_shot.setdefault(line.shot_detail_id, []).append(
            {
                "index": line.index,
                "text": line.text,
                "mode": _serialized_enum(line.line_mode),
                "speaker": line.speaker_name,
                "target": line.target_name,
            }
        )

    shots_payload: list[dict[str, Any]] = []
    total_duration_seconds = 0
    for shot, chapter, detail in rows:
        duration = int(detail.duration) if detail is not None else 0
        total_duration_seconds += duration
        shots_payload.append(
            {
                "shot_id": shot.id,
                "chapter_id": chapter.id,
                "chapter_index": chapter.index,
                "shot_index": shot.index,
                "title": shot.title,
                "purpose": detail.description if detail is not None else "",
                "script_excerpt": shot.script_excerpt,
                "duration_seconds": duration,
                "camera": {
                    "shot": _serialized_enum(detail.camera_shot),
                    "angle": _serialized_enum(detail.angle),
                    "movement": _serialized_enum(detail.movement),
                } if detail is not None else None,
                "action_beats": list(detail.action_beats or []) if detail is not None else [],
                "audio_cues": {
                    "has_bgm": bool(detail.has_bgm) if detail is not None else False,
                    "dialogue": dialogue_by_shot.get(shot.id, []),
                },
                "transition_to_next": None,
                "frame_prompts": {
                    "first": detail.first_frame_prompt,
                    "key": detail.key_frame_prompt,
                    "last": detail.last_frame_prompt,
                } if detail is not None else {"first": "", "key": "", "last": ""},
            }
        )

    latest_stmt = (
        select(ProductionRevision)
        .where(
            ProductionRevision.project_id == project_id,
            ProductionRevision.scope_type == "project",
            ProductionRevision.scope_id == project_id,
            ProductionRevision.kind == "shot_plan",
        )
        .order_by(ProductionRevision.revision_number.desc())
    )
    parent = (await db.execute(latest_stmt)).scalars().first()
    return await create_production_revision(
        db,
        project_id=project_id,
        body=ProductionRevisionCreate(
            kind="shot_plan",
            parent_revision_id=parent.id if parent is not None else None,
            created_by=created_by,
            payload={
                "schema_version": 1,
                "format": "persisted_shot_plan_snapshot",
                "shot_count": len(shots_payload),
                "total_duration_seconds": total_duration_seconds,
                "shots": shots_payload,
            },
        ),
    )


async def create_production_artifact(
    db: AsyncSession,
    *,
    project_id: str,
    body: ProductionArtifactCreate,
) -> ProductionArtifact:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Project"))
    if body.source_revision_id:
        revision = await db.get(ProductionRevision, body.source_revision_id)
        if revision is None or revision.project_id != project_id:
            raise HTTPException(status_code=404, detail=entity_not_found("Production revision"))
    artifact = ProductionArtifact(
        id=str(uuid4()),
        project_id=project_id,
        shot_id=body.shot_id,
        artifact_type=body.artifact_type,
        file_id=body.file_id,
        source_revision_id=body.source_revision_id,
        generation_task_id=body.generation_task_id,
        input_fingerprint=body.input_fingerprint,
        currency=body.currency,
        lifecycle=body.lifecycle,
        metadata_json=body.metadata,
    )
    db.add(artifact)
    await _audit(
        db,
        project_id=project_id,
        actor=None,
        action="artifact.created",
        target_type=body.artifact_type,
        target_id=artifact.id,
        detail={"shot_id": body.shot_id, "currency": body.currency, "lifecycle": body.lifecycle},
    )
    await db.flush()
    await db.refresh(artifact)
    return artifact


async def select_production_artifact(
    db: AsyncSession,
    *,
    project_id: str,
    artifact_id: str,
    selected_by: str | None,
) -> ProductionArtifact:
    artifact = await db.get(ProductionArtifact, artifact_id, with_for_update=True)
    if artifact is None or artifact.project_id != project_id:
        raise HTTPException(status_code=404, detail=entity_not_found("Production artifact"))
    if artifact.currency in {"missing", "blocked"} or not artifact.file_id:
        raise HTTPException(status_code=409, detail="Artifact is not selectable")

    sibling_stmt = (
        select(ProductionArtifact)
        .where(
            ProductionArtifact.project_id == project_id,
            ProductionArtifact.artifact_type == artifact.artifact_type,
            ProductionArtifact.shot_id == artifact.shot_id,
        )
        .with_for_update()
    )
    for sibling in (await db.execute(sibling_stmt)).scalars().all():
        if sibling.id == artifact.id:
            sibling.lifecycle = "selected"
            sibling.selected_by = selected_by
            sibling.selected_at = datetime.now(UTC)
        elif sibling.lifecycle == "selected":
            sibling.lifecycle = "candidate"
            sibling.selected_by = None
            sibling.selected_at = None
    if artifact.artifact_type in {"frame_first", "frame_key", "frame_last"}:
        if not artifact.shot_id:
            raise HTTPException(status_code=409, detail="Frame artifact requires a shot_id")
        frame_type = artifact.artifact_type.removeprefix("frame_")
        frame_stmt = (
            select(ShotFrameImage)
            .where(
                ShotFrameImage.shot_detail_id == artifact.shot_id,
                ShotFrameImage.frame_type == frame_type,
            )
            .with_for_update()
        )
        frame_row = (await db.execute(frame_stmt)).scalars().first()
        if frame_row is None:
            raise HTTPException(status_code=404, detail=entity_not_found("Shot frame"))
        frame_row.file_id = artifact.file_id
        if frame_type == "key":
            parent_stmt = (
                select(ProductionRevision)
                .where(
                    ProductionRevision.project_id == project_id,
                    ProductionRevision.kind == "keyframe",
                    ProductionRevision.scope_type == "shot",
                    ProductionRevision.scope_id == artifact.shot_id,
                    ProductionRevision.state == "approved",
                )
                .order_by(ProductionRevision.revision_number.desc())
            )
            parent = (await db.execute(parent_stmt)).scalars().first()
            revision = await create_production_revision(
                db,
                project_id=project_id,
                body=ProductionRevisionCreate(
                    kind="keyframe",
                    scope_type="shot",
                    scope_id=artifact.shot_id,
                    parent_revision_id=parent.id if parent else None,
                    payload={
                        "artifact_id": artifact.id,
                        "file_id": artifact.file_id,
                        "frame_type": frame_type,
                    },
                    created_by=selected_by,
                ),
            )
            await approve_production_revision(
                db,
                project_id=project_id,
                revision_id=revision.id,
                approved_by=selected_by,
            )
    await _audit(
        db,
        project_id=project_id,
        actor=selected_by,
        action="artifact.selected",
        target_type=artifact.artifact_type,
        target_id=artifact.id,
        detail={"shot_id": artifact.shot_id, "currency": artifact.currency},
    )
    await db.flush()
    await db.refresh(artifact)
    return artifact


async def _approved_revision(
    db: AsyncSession,
    *,
    project_id: str,
    kind: str,
    scope_type: str = "project",
    scope_id: str | None = None,
) -> ProductionRevision | None:
    stmt = select(ProductionRevision).where(
        ProductionRevision.project_id == project_id,
        ProductionRevision.kind == kind,
        ProductionRevision.scope_type == scope_type,
        ProductionRevision.scope_id == (scope_id or project_id),
        ProductionRevision.state == "approved",
    )
    return (await db.execute(stmt)).scalars().first()


async def build_production_workflow_plan(
    db: AsyncSession,
    *,
    project_id: str,
) -> ProductionWorkflowPlanRead:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Project"))

    research = await db.get(ProjectResearch, project_id)
    research_ready = bool(research and research.status == "approved" and research.approved_direction_id)
    script = await _approved_revision(db, project_id=project_id, kind="script")
    shot_plan = await _approved_revision(db, project_id=project_id, kind="shot_plan")
    edit = await _approved_revision(db, project_id=project_id, kind="edit")

    shot_stmt = select(Shot).join(Chapter, Chapter.id == Shot.chapter_id).where(Chapter.project_id == project_id)
    shots = list((await db.execute(shot_stmt)).scalars().all())
    shot_ids = [shot.id for shot in shots]

    keyframe_ids: set[str] = set()
    if shot_ids:
        keyframe_stmt = select(ProductionRevision.scope_id).where(
            ProductionRevision.project_id == project_id,
            ProductionRevision.kind == "keyframe",
            ProductionRevision.scope_type == "shot",
            ProductionRevision.scope_id.in_(shot_ids),
            ProductionRevision.state == "approved",
        )
        keyframe_ids = set((await db.execute(keyframe_stmt)).scalars().all())
    selected_take_ids = {shot.id for shot in shots if shot.generated_video_file_id}
    candidate_take_ids: set[str] = set()
    if shot_ids:
        candidate_stmt = select(GenerationTaskLink.relation_entity_id).where(
            GenerationTaskLink.resource_type == "video",
            GenerationTaskLink.relation_type == "video",
            GenerationTaskLink.relation_entity_id.in_(shot_ids),
            GenerationTaskLink.file_id.is_not(None),
        )
        candidate_take_ids = set((await db.execute(candidate_stmt)).scalars().all())

    qa: ProductionQAReport | None = None
    render_artifact: ProductionArtifact | None = None
    if edit:
        render_stmt = (
            select(ProductionArtifact)
            .where(
                ProductionArtifact.project_id == project_id,
                ProductionArtifact.artifact_type == "render",
                ProductionArtifact.source_revision_id == edit.id,
                ProductionArtifact.file_id.is_not(None),
                ProductionArtifact.currency == "current",
            )
            .order_by(ProductionArtifact.created_at.desc())
        )
        render_artifact = (await db.execute(render_stmt)).scalars().first()
        qa_stmt = (
            select(ProductionQAReport)
            .where(ProductionQAReport.project_id == project_id, ProductionQAReport.edit_revision_id == edit.id)
            .order_by(ProductionQAReport.created_at.desc())
        )
        qa = (await db.execute(qa_stmt)).scalars().first()
    delivery_stmt = (
        select(ProductionDelivery)
        .where(ProductionDelivery.project_id == project_id)
        .order_by(ProductionDelivery.created_at.desc())
    )
    delivery = (await db.execute(delivery_stmt)).scalars().first()

    artifact_rows = list(
        (await db.execute(select(ProductionArtifact).where(ProductionArtifact.project_id == project_id))).scalars().all()
    )
    artifact_counts: dict[str, Counter[str]] = {}
    artifact_selected: Counter[str] = Counter()
    for artifact in artifact_rows:
        artifact_counts.setdefault(artifact.artifact_type, Counter())[artifact.currency] += 1
        if artifact.lifecycle == "selected":
            artifact_selected[artifact.artifact_type] += 1
    artifacts = [
        WorkflowArtifactSummary(
            artifact_type=artifact_type,
            total=sum(counts.values()),
            current=counts["current"],
            stale=counts["stale"],
            missing=counts["missing"],
            blocked=counts["blocked"],
            selected=artifact_selected[artifact_type],
        )
        for artifact_type, counts in sorted(artifact_counts.items())
    ]

    steps = [
        {"key": "brief", "complete": research_ready},
        {"key": "script", "complete": script is not None},
        {"key": "storyboard", "complete": shot_plan is not None and bool(shots)},
        {"key": "keyframes", "complete": bool(shots) and len(keyframe_ids) == len(shots)},
        {"key": "takes", "complete": bool(shots) and len(selected_take_ids) == len(shots)},
        {"key": "edit", "complete": edit is not None},
        {"key": "render", "complete": render_artifact is not None},
        {"key": "qa", "complete": bool(qa and qa.status == "passed")},
        {"key": "delivery", "complete": delivery is not None},
    ]
    blockers: list[WorkflowProblem] = []
    gates: list[dict[str, Any]] = []

    if not research_ready:
        current_step = "brief"
        next_action = WorkflowNextAction(type="approve_research", reason="An approved creative direction is required")
        gates.append({"key": "research_approval", "satisfied": False})
    elif script is None:
        current_step = "script"
        next_action = WorkflowNextAction(type="create_script_revision", reason="No approved script revision exists")
        gates.append({"key": "script_approval", "satisfied": False})
    elif not shots:
        current_step = "storyboard"
        next_action = WorkflowNextAction(type="create_shots", reason="Create persisted shot cards before snapshotting the shot plan")
        gates.append({"key": "persisted_shots", "satisfied": False})
    elif shot_plan is None:
        draft_stmt = (
            select(ProductionRevision)
            .where(
                ProductionRevision.project_id == project_id,
                ProductionRevision.kind == "shot_plan",
                ProductionRevision.scope_type == "project",
                ProductionRevision.scope_id == project_id,
                ProductionRevision.state == "draft",
            )
            .order_by(ProductionRevision.revision_number.desc())
        )
        draft_shot_plan = (await db.execute(draft_stmt)).scalars().first()
        current_step = "storyboard"
        if draft_shot_plan is None:
            next_action = WorkflowNextAction(
                type="snapshot_shot_plan",
                reason="Persisted shots are ready to snapshot into an immutable Shot Plan draft",
            )
        else:
            next_action = WorkflowNextAction(
                type="approve_shot_plan_revision",
                reason="Review and approve the latest Shot Plan snapshot",
                requested_ids=[draft_shot_plan.id],
                requires_confirmation=True,
            )
        gates.append({"key": "shot_plan_approval", "satisfied": False})
    elif len(keyframe_ids) != len(shots):
        missing = [shot_id for shot_id in shot_ids if shot_id not in keyframe_ids]
        current_step = "keyframes"
        next_action = WorkflowNextAction(
            type="approve_keyframes",
            reason="Every shot requires an approved keyframe revision",
            requested_ids=missing,
        )
    elif len(selected_take_ids) != len(shots):
        missing = [shot_id for shot_id in shot_ids if shot_id not in selected_take_ids]
        current_step = "takes"
        candidates = [shot_id for shot_id in missing if shot_id in candidate_take_ids]
        needs_generation = [shot_id for shot_id in missing if shot_id not in candidate_take_ids]
        if candidates:
            next_action = WorkflowNextAction(
                type="select_existing_takes",
                reason="Generated candidate takes are waiting for an explicit selection",
                requested_ids=candidates,
                requires_confirmation=True,
            )
        else:
            next_action = WorkflowNextAction(
                type="generate_takes",
                reason="These shots have no generated video take",
                requested_ids=needs_generation,
                requires_confirmation=True,
            )
    elif edit is None:
        current_step = "edit"
        next_action = WorkflowNextAction(type="create_edit_revision", reason="No approved edit revision exists")
    elif render_artifact is None:
        current_step = "render"
        next_action = WorkflowNextAction(
            type="render_edit",
            reason="The approved edit has not produced a current MP4 render",
            requested_ids=[edit.id],
        )
    elif qa is None or qa.status != "passed":
        current_step = "qa"
        next_action = WorkflowNextAction(type="run_qa", reason="The approved edit requires a passing QA report")
        if qa and qa.status == "failed":
            blockers.extend(
                WorkflowProblem(
                    code=str(item.get("code") or "qa_failed"),
                    message=str(item.get("message") or "QA check failed"),
                    target_type=str(item.get("target_type") or "edit"),
                    target_id=str(item.get("target_id") or edit.id),
                    severity="blocking",
                )
                for item in qa.checks
                if isinstance(item, dict) and item.get("status") == "failed"
            )
    elif delivery is None:
        current_step = "delivery"
        next_action = WorkflowNextAction(
            type="create_delivery",
            reason="QA passed and the project is ready for delivery",
            requires_confirmation=True,
        )
    else:
        current_step = "complete"
        next_action = WorkflowNextAction(type="none", reason="Production is complete")

    for summary in artifacts:
        if summary.blocked:
            blockers.append(
                WorkflowProblem(
                    code="blocked_artifacts",
                    message=f"{summary.blocked} {summary.artifact_type} artifact(s) are blocked",
                    target_type=summary.artifact_type,
                )
            )

    return ProductionWorkflowPlanRead(
        project_id=project_id,
        current_step=current_step,
        steps=steps,
        blockers=blockers,
        gates=gates,
        artifacts=artifacts,
        next_action=next_action,
    )


def _qa_check(
    code: str,
    status: str,
    message: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "status": status,
        "message": message,
        "target_type": target_type,
        "target_id": target_id,
        "detail": detail or {},
    }


async def run_production_qa(
    db: AsyncSession,
    *,
    project_id: str,
    body: ProductionQARunRequest,
) -> ProductionQAReport:
    edit = await db.get(ProductionRevision, body.edit_revision_id)
    if edit is None or edit.project_id != project_id or edit.kind != "edit":
        raise HTTPException(status_code=404, detail=entity_not_found("Edit revision"))

    checks: list[dict[str, Any]] = []
    checks.append(
        _qa_check(
            "edit_revision_approved",
            "passed" if edit.state == "approved" else "failed",
            "Edit revision is approved" if edit.state == "approved" else "Edit revision must be approved",
            target_type="edit",
            target_id=edit.id,
        )
    )

    shot_stmt = select(Shot).join(Chapter, Chapter.id == Shot.chapter_id).where(Chapter.project_id == project_id)
    shots = list((await db.execute(shot_stmt)).scalars().all())
    missing_take_ids = [shot.id for shot in shots if not shot.generated_video_file_id]
    checks.append(
        _qa_check(
            "selected_take_coverage",
            "passed" if shots and not missing_take_ids else "failed",
            "Every shot has a selected take" if shots and not missing_take_ids else "Some shots have no selected take",
            target_type="shot",
            detail={"missing_shot_ids": missing_take_ids, "shot_count": len(shots)},
        )
    )

    selected_artifact_stmt = select(ProductionArtifact).where(
        ProductionArtifact.project_id == project_id,
        ProductionArtifact.lifecycle == "selected",
    )
    selected_artifacts = list((await db.execute(selected_artifact_stmt)).scalars().all())
    blocked = [artifact.id for artifact in selected_artifacts if artifact.currency == "blocked"]
    stale = [artifact.id for artifact in selected_artifacts if artifact.currency == "stale"]
    checks.append(
        _qa_check(
            "selected_artifacts_unblocked",
            "passed" if not blocked else "failed",
            "Selected artifacts are readable" if not blocked else "Selected artifacts include blocked items",
            target_type="artifact",
            detail={"blocked_artifact_ids": blocked},
        )
    )
    checks.append(
        _qa_check(
            "selected_artifacts_current",
            "passed" if not stale else "warning",
            "Selected artifacts are current" if not stale else "Selected artifacts include stale items",
            target_type="artifact",
            detail={"stale_artifact_ids": stale},
        )
    )

    timeline_payload = edit.payload.get("timeline")
    document: EditDocument | None = None
    try:
        document = EditDocument.model_validate(timeline_payload)
    except Exception:  # noqa: BLE001
        document = None
    checks.append(
        _qa_check(
            "timeline_present",
            "passed" if document and document.video_clips else "failed",
            "Edit timeline contains validated clips" if document and document.video_clips else "Edit timeline is missing or invalid",
            target_type="edit",
            target_id=edit.id,
        )
    )

    render_stmt = (
        select(ProductionArtifact)
        .where(
            ProductionArtifact.project_id == project_id,
            ProductionArtifact.artifact_type == "render",
            ProductionArtifact.source_revision_id == edit.id,
            ProductionArtifact.file_id.is_not(None),
            ProductionArtifact.currency == "current",
        )
        .order_by(ProductionArtifact.created_at.desc())
    )
    render_artifact = (await db.execute(render_stmt)).scalars().first()
    render_file = await db.get(FileItem, render_artifact.file_id) if render_artifact and render_artifact.file_id else None
    checks.append(
        _qa_check(
            "render_present",
            "passed" if render_file else "failed",
            "A rendered MP4 is linked to the approved edit" if render_file else "Render the approved edit before QA",
            target_type="render",
            target_id=render_artifact.id if render_artifact else None,
        )
    )

    media_info: dict[str, Any] | None = None
    if render_file:
        try:
            media_info = await inspect_media_file(render_file)
            checks.append(_qa_check("render_playable", "passed", "Rendered media is readable", target_type="file", target_id=render_file.id))
        except Exception as exc:  # noqa: BLE001
            checks.append(
                _qa_check(
                    "render_playable",
                    "failed",
                    "Rendered media could not be inspected",
                    target_type="file",
                    target_id=render_file.id,
                    detail={"error": str(exc)},
                )
            )

    if document and media_info:
        expected_duration = (
            sum(clip.source_out_ms - clip.source_in_ms for clip in document.video_clips)
            - sum(clip.transition_to_next.duration_ms for clip in document.video_clips[:-1])
        ) / 1000
        actual_duration = float(media_info.get("duration_seconds") or 0)
        delta = abs(expected_duration - actual_duration)
        checks.append(
            _qa_check(
                "duration_matches_edit",
                "passed" if delta <= 0.5 else "failed",
                "Rendered duration matches the edit" if delta <= 0.5 else "Rendered duration differs from the edit",
                target_type="file",
                target_id=render_file.id if render_file else None,
                detail={"expected": expected_duration, "actual": actual_duration, "delta": delta},
            )
        )
        video_info = media_info.get("video") if isinstance(media_info.get("video"), dict) else {}
        dimensions_match = (
            int(video_info.get("width") or 0) == document.canvas.width
            and int(video_info.get("height") or 0) == document.canvas.height
        )
        checks.append(
            _qa_check(
                "resolution_matches_edit",
                "passed" if dimensions_match else "failed",
                "Rendered resolution matches the edit canvas" if dimensions_match else "Rendered resolution differs from the edit canvas",
                target_type="file",
                target_id=render_file.id if render_file else None,
                detail={"expected": [document.canvas.width, document.canvas.height], "actual": [video_info.get("width"), video_info.get("height")]},
            )
        )
        actual_fps = float(video_info.get("fps") or 0)
        fps_matches = abs(actual_fps - document.canvas.fps) <= 0.1
        checks.append(
            _qa_check(
                "frame_rate_matches_edit",
                "passed" if fps_matches else "failed",
                "Rendered frame rate matches the edit" if fps_matches else "Rendered frame rate differs from the edit",
                target_type="file",
                target_id=render_file.id if render_file else None,
                detail={"expected": document.canvas.fps, "actual": actual_fps},
            )
        )
        audio_expected = bool(document.audio_clips) or any(clip.use_source_audio for clip in document.video_clips)
        has_expected_audio = not audio_expected or int(media_info.get("audio_stream_count") or 0) > 0
        checks.append(
            _qa_check(
                "expected_audio_present",
                "passed" if has_expected_audio else "failed",
                "Expected audio state is present" if has_expected_audio else "The edit contains audio clips but the render has no audio track",
                target_type="file",
                target_id=render_file.id if render_file else None,
            )
        )
        black_segments = media_info.get("black_segments") if isinstance(media_info.get("black_segments"), list) else []
        freeze_starts = media_info.get("freeze_starts") if isinstance(media_info.get("freeze_starts"), list) else []
        checks.append(
            _qa_check(
                "no_unintended_black_frames",
                "passed" if not black_segments else "failed",
                "No unintended black segments detected" if not black_segments else "Black video segments were detected",
                target_type="file",
                target_id=render_file.id if render_file else None,
                detail={"segments": black_segments},
            )
        )
        checks.append(
            _qa_check(
                "no_long_freeze",
                "passed" if not freeze_starts else "warning",
                "No long freeze detected" if not freeze_starts else "Long static segments were detected; review intent",
                target_type="file",
                target_id=render_file.id if render_file else None,
                detail={"freeze_starts": freeze_starts},
            )
        )
        max_volume_db = media_info.get("max_volume_db")
        if max_volume_db is not None:
            checks.append(
                _qa_check(
                    "audio_peak_not_clipping",
                    "passed" if float(max_volume_db) <= 0 else "failed",
                    "Audio peak is within digital ceiling" if float(max_volume_db) <= 0 else "Audio peak exceeds digital ceiling",
                    target_type="file",
                    target_id=render_file.id if render_file else None,
                    detail={"max_volume_db": max_volume_db},
                )
            )

    research = await db.get(ProjectResearch, project_id)
    ad_brief = research.brief if research and isinstance(research.brief, dict) else {}
    target_duration = ad_brief.get("target_duration_seconds") if isinstance(ad_brief, dict) else None
    if document and isinstance(target_duration, (int, float)):
        edit_duration = (
            sum(clip.source_out_ms - clip.source_in_ms for clip in document.video_clips)
            - sum(clip.transition_to_next.duration_ms for clip in document.video_clips[:-1])
        ) / 1000
        target_delta = abs(float(target_duration) - edit_duration)
        checks.append(
            _qa_check(
                "duration_matches_brief",
                "passed" if target_delta <= 0.5 else "failed",
                "Edit duration matches the advertising brief" if target_delta <= 0.5 else "Edit duration differs from the advertising brief",
                target_type="edit",
                target_id=edit.id,
                detail={"target": target_duration, "edit_duration": edit_duration, "delta": target_delta},
            )
        )
    required_overlays = ad_brief.get("required_overlays") if isinstance(ad_brief, dict) else []
    required_overlay_items = required_overlays if isinstance(required_overlays, list) else []
    overlay_items = document.overlays if document else []
    required_names = {
        str(item).strip()
        for item in required_overlay_items
        if str(item).strip()
    }
    present_names = {
        item.type
        for item in overlay_items
    }
    missing_overlays = sorted(required_names - present_names)
    checks.append(
        _qa_check(
            "required_overlays_present",
            "passed" if not missing_overlays else "failed",
            "Required overlays are present" if not missing_overlays else "Required overlays are missing",
            target_type="edit",
            target_id=edit.id,
            detail={"missing": missing_overlays},
        )
    )
    if document:
        checks.append(
            _qa_check(
                "deterministic_safe_area",
                "passed",
                "Subtitles and brand overlays use the deterministic canvas safe area",
                target_type="edit",
                target_id=edit.id,
                detail={"safe_area_percent": document.canvas.safe_area_percent},
            )
        )
    exact_copy = {
        "cta": str(ad_brief.get("cta") or "").strip(),
        "legal": str(ad_brief.get("legal") or "").strip(),
    }
    for overlay_type, expected_text in exact_copy.items():
        if not expected_text:
            continue
        matching = [item for item in overlay_items if item.type == overlay_type]
        exact_match = any(item.text.strip() == expected_text for item in matching)
        checks.append(
            _qa_check(
                f"{overlay_type}_copy_matches_brief",
                "passed" if exact_match else "failed",
                f"{overlay_type.upper()} copy matches the approved brief" if exact_match else f"{overlay_type.upper()} copy differs from the approved brief",
                target_type="edit",
                target_id=edit.id,
                detail={"expected": expected_text, "actual": [item.text for item in matching]},
            )
        )
    prohibited = [str(item).strip().lower() for item in ad_brief.get("prohibited_claims", []) if str(item).strip()]
    rendered_copy = [item.text for item in overlay_items if item.type != "logo"]
    if document:
        rendered_copy.extend(item.text for item in document.subtitles)
    violations = sorted({phrase for phrase in prohibited if any(phrase in text.lower() for text in rendered_copy)})
    checks.append(
        _qa_check(
            "prohibited_claims_absent",
            "passed" if not violations else "failed",
            "No prohibited claim appears in deterministic copy" if not violations else "Prohibited claims appear in delivery copy",
            target_type="edit",
            target_id=edit.id,
            detail={"violations": violations},
        )
    )

    report_status = "failed" if any(check["status"] == "failed" for check in checks) else "passed"
    report = ProductionQAReport(
        id=str(uuid4()),
        project_id=project_id,
        edit_revision_id=edit.id,
        status=report_status,
        checks=checks,
        waivers=[],
        run_by=body.run_by,
    )
    db.add(report)
    await _audit(
        db,
        project_id=project_id,
        actor=body.run_by,
        action="qa.completed",
        target_type="qa_report",
        target_id=report.id,
        detail={"status": report_status, "edit_revision_id": edit.id},
    )
    await db.flush()
    await db.refresh(report)
    return report


async def create_production_delivery(
    db: AsyncSession,
    *,
    project_id: str,
    body: ProductionDeliveryCreate,
) -> ProductionDelivery:
    edit = await db.get(ProductionRevision, body.edit_revision_id)
    if edit is None or edit.project_id != project_id or edit.kind != "edit" or edit.state != "approved":
        raise HTTPException(status_code=409, detail="Delivery requires an approved edit revision")
    qa = await db.get(ProductionQAReport, body.qa_report_id)
    if qa is None or qa.project_id != project_id or qa.edit_revision_id != edit.id:
        raise HTTPException(status_code=404, detail=entity_not_found("QA report"))
    if body.delivery_type == "final" and qa.status != "passed":
        raise HTTPException(status_code=409, detail="Final delivery requires a passing QA report")

    for file_id in body.file_ids:
        if await db.get(FileItem, file_id) is None:
            raise HTTPException(status_code=404, detail=entity_not_found(f"Delivery file {file_id}"))

    render_stmt = select(ProductionArtifact).where(
        ProductionArtifact.project_id == project_id,
        ProductionArtifact.artifact_type == "render",
        ProductionArtifact.source_revision_id == edit.id,
        ProductionArtifact.currency == "current",
        ProductionArtifact.file_id.in_(body.file_ids),
    )
    delivery_render = (await db.execute(render_stmt)).scalars().first()
    if body.delivery_type == "final" and delivery_render is None:
        raise HTTPException(
            status_code=409,
            detail="Final delivery must include a current render produced from the approved edit revision",
        )

    approved_stmt = select(ProductionRevision).where(
        ProductionRevision.project_id == project_id,
        ProductionRevision.state == "approved",
    )
    approved = list((await db.execute(approved_stmt)).scalars().all())
    shot_stmt = select(Shot).join(Chapter, Chapter.id == Shot.chapter_id).where(Chapter.project_id == project_id)
    shots = list((await db.execute(shot_stmt)).scalars().all())
    selected_takes = [
        {"shot_id": shot.id, "file_id": shot.generated_video_file_id}
        for shot in shots
        if shot.generated_video_file_id
    ]
    delivery_id = str(uuid4())
    timeline_payload = edit.payload.get("timeline") if isinstance(edit.payload, dict) else None
    subtitle_count = len(timeline_payload.get("subtitles", [])) if isinstance(timeline_payload, dict) else 0
    manifest = {
        "schema_version": 1,
        "project_id": project_id,
        "delivery_type": body.delivery_type,
        "edit_revision_id": edit.id,
        "qa_report_id": qa.id,
        "approved_revisions": [
            {
                "id": revision.id,
                "kind": revision.kind,
                "scope_type": revision.scope_type,
                "scope_id": revision.scope_id,
                "revision_number": revision.revision_number,
                "input_fingerprint": revision.input_fingerprint,
            }
            for revision in approved
        ],
        "selected_takes": selected_takes,
        "qa_status": qa.status,
        "qa_checks": qa.checks,
        "file_ids": body.file_ids,
        "render_artifact_id": delivery_render.id if delivery_render else None,
        "sidecars": {
            "manifest": f"/api/v1/studio/projects/{project_id}/production/deliveries/{delivery_id}/manifest.json",
            "subtitles": (
                f"/api/v1/studio/projects/{project_id}/production/deliveries/{delivery_id}/subtitles.srt"
                if subtitle_count
                else None
            ),
            "subtitle_count": subtitle_count,
        },
        "created_at": datetime.now(UTC).isoformat(),
    }
    delivery = ProductionDelivery(
        id=delivery_id,
        project_id=project_id,
        edit_revision_id=edit.id,
        qa_report_id=qa.id,
        delivery_type=body.delivery_type,
        status="ready",
        file_ids=body.file_ids,
        manifest=manifest,
        delivered_by=body.delivered_by,
    )
    db.add(delivery)
    await _audit(
        db,
        project_id=project_id,
        actor=body.delivered_by,
        action="delivery.created",
        target_type="delivery",
        target_id=delivery.id,
        detail={"delivery_type": body.delivery_type, "qa_report_id": qa.id},
    )
    await db.flush()
    await db.refresh(delivery)
    return delivery


async def get_production_delivery(
    db: AsyncSession,
    *,
    project_id: str,
    delivery_id: str,
) -> ProductionDelivery:
    delivery = await db.get(ProductionDelivery, delivery_id)
    if delivery is None or delivery.project_id != project_id:
        raise HTTPException(status_code=404, detail=entity_not_found("Delivery"))
    return delivery


def _srt_timestamp(milliseconds: int) -> str:
    total_ms = max(0, int(milliseconds))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


async def build_delivery_subtitles_srt(
    db: AsyncSession,
    *,
    project_id: str,
    delivery_id: str,
) -> str:
    delivery = await get_production_delivery(db, project_id=project_id, delivery_id=delivery_id)
    edit = await db.get(ProductionRevision, delivery.edit_revision_id)
    if edit is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Edit revision"))
    payload = edit.payload.get("timeline") if isinstance(edit.payload, dict) else None
    document = EditDocument.model_validate(payload)
    blocks: list[str] = []
    for index, cue in enumerate(sorted(document.subtitles, key=lambda item: (item.start_ms, item.end_ms)), start=1):
        speaker = f"{cue.speaker}: " if cue.speaker else ""
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_srt_timestamp(cue.start_ms)} --> {_srt_timestamp(cue.end_ms)}",
                    f"{speaker}{cue.text}",
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


__all__ = [
    "approve_production_revision",
    "build_production_workflow_plan",
    "canonical_fingerprint",
    "create_production_artifact",
    "create_production_delivery",
    "create_production_revision",
    "build_delivery_subtitles_srt",
    "get_production_delivery",
    "run_production_qa",
    "select_production_artifact",
]
