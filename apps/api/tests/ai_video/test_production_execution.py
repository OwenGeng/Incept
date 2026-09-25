from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai_video.core.db import Base
from app.ai_video.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.ai_video.models.production_execution import (
    GenerationIdempotencyRecord,
    ProviderExecutionCheckpoint,
    UsageLedgerEntry,
)
from app.ai_video.models.studio import (
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    Project,
    ProjectResearch,
    ProjectStyle,
    ProjectVisualStyle,
    Shot,
    ShotDetail,
)
from app.ai_video.models.task import GenerationTask
from app.ai_video.schemas.studio.production_control import ProductionRevisionCreate
from app.ai_video.schemas.studio.production_execution import VideoBatchConfirm, VideoBatchCreate, VideoBatchItemRequest
from app.ai_video.services.studio.production_control import approve_production_revision, create_production_revision
from app.ai_video.services.studio.production_execution import (
    backfill_completed_unpriced_usage_from_catalog,
    confirm_video_batch,
    create_video_batch,
    create_video_task_record,
    fail_video_usage,
    record_provider_completed,
    settle_video_usage,
    update_execution_started,
    usage_summary,
)
from app.ai_video.services.llm.pricing_catalog import pricing_catalog_for_model


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed(db: AsyncSession, *, approve_keyframe: bool, priced: bool = True) -> None:
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
    db.add(Shot(id="shot-1", chapter_id="chapter-1", index=1, title="Shot"))
    db.add(
        ShotDetail(
            id="shot-1",
            camera_shot=CameraShotType.ms,
            angle=CameraAngle.eye_level,
            movement=CameraMovement.static,
            duration=5,
        )
    )
    db.add(Provider(id="provider-1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="test"))
    params = {"pricing": {"currency": "USD", "unit": "second", "amount": "0.25"}} if priced else {}
    db.add(
        Model(
            id="video-model",
            name="configured-video-model",
            category=ModelCategoryKey.video,
            provider_id="provider-1",
            params=params,
        )
    )
    db.add(ModelSettings(id=1, default_video_model_id="video-model"))
    await db.commit()
    if approve_keyframe:
        revision = await create_production_revision(
            db,
            project_id="project-1",
            body=ProductionRevisionCreate(
                kind="keyframe",
                scope_type="shot",
                scope_id="shot-1",
                payload={"approved_file_id": "frame-1"},
            ),
        )
        await approve_production_revision(
            db,
            project_id="project-1",
            revision_id=revision.id,
            approved_by="director",
        )
        await db.commit()


def _batch(*, confirm_cost: bool = False) -> VideoBatchCreate:
    return VideoBatchCreate(
        confirm_cost=confirm_cost,
        confirmed_by="producer" if confirm_cost else None,
        items=[
            VideoBatchItemRequest(
                shot_id="shot-1",
                reference_mode="text_only",
                prompt="A slow dolly toward the subject",
                ratio="16:9",
            )
        ],
    )


def test_batch_creation_rejects_one_step_cost_confirmation() -> None:
    with pytest.raises(ValidationError, match="preflight batch"):
        _batch(confirm_cost=True)


@pytest.mark.asyncio
async def test_batch_admission_failure_creates_zero_generation_tasks() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=False)
        batch = await create_video_batch(db, project_id="project-1", body=_batch())
        await db.commit()

        count = int(await db.scalar(select(func.count(GenerationTask.id))) or 0)
        assert batch.status == "blocked"
        assert batch.admission["all_or_none"] is True
        assert batch.admission["blockers"][0]["code"] == "keyframe_not_approved"
        assert batch.items[0].status == "blocked"
        assert count == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_priced_batch_requires_confirmation_before_tasks_are_created() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        batch = await create_video_batch(db, project_id="project-1", body=_batch())
        await db.commit()

        count = int(await db.scalar(select(func.count(GenerationTask.id))) or 0)
        assert batch.status == "confirmation_required"
        assert batch.estimate["currency"] == "USD"
        assert batch.estimate["total"] == "1.25"
        assert count == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_batch_creates_checkpoint_and_usage_ledger() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        preflight = await create_video_batch(db, project_id="project-1", body=_batch())
        batch, task_ids = await confirm_video_batch(
            db,
            project_id="project-1",
            batch_id=preflight.id,
            body=VideoBatchConfirm(
                quote_fingerprint=preflight.estimate["quote_fingerprint"],
                confirmed_by="producer",
            ),
        )
        await db.commit()

        task_id = batch.items[0].task_id
        checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
        ledger = (await db.execute(select(UsageLedgerEntry).where(UsageLedgerEntry.task_id == task_id))).scalar_one()
        assert batch.status == "queued"
        assert task_ids == [task_id]
        assert batch.confirmed_by == "producer"
        assert task_id
        assert checkpoint is not None and checkpoint.state == "prepared"
        assert ledger.status == "estimated"
        assert ledger.estimated_amount == Decimal("1.250000")
        assert ledger.project_id == "project-1"
        assert ledger.request_summary["quote_fingerprint"] == preflight.estimate["quote_fingerprint"]
        assert ledger.request_summary["confirmed_by"] == "producer"

        repeated, repeated_task_ids = await confirm_video_batch(
            db,
            project_id="project-1",
            batch_id=preflight.id,
            body=VideoBatchConfirm(
                quote_fingerprint=preflight.estimate["quote_fingerprint"],
                confirmed_by="producer",
            ),
        )
        assert repeated.id == batch.id
        assert repeated_task_ids == []
        assert int(await db.scalar(select(func.count(GenerationTask.id))) or 0) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_confirmation_is_bound_to_the_original_quote() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        preflight = await create_video_batch(db, project_id="project-1", body=_batch())

        with pytest.raises(HTTPException) as exc_info:
            await confirm_video_batch(
                db,
                project_id="project-1",
                batch_id=preflight.id,
                body=VideoBatchConfirm(quote_fingerprint="0" * 64, confirmed_by="producer"),
            )

        assert exc_info.value.status_code == 409
        assert int(await db.scalar(select(func.count(GenerationTask.id))) or 0) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_unpriced_batch_cannot_be_confirmed_or_create_tasks() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True, priced=False)
        batch = await create_video_batch(db, project_id="project-1", body=_batch())

        assert batch.status == "blocked"
        assert any(problem["code"] == "pricing_unavailable" for problem in batch.admission["blockers"])
        assert int(await db.scalar(select(func.count(GenerationTask.id))) or 0) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_video_task_idempotency_reuses_same_task_and_rejects_payload_change() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        item = _batch().items[0]
        first_task_id, first_reused = await create_video_task_record(db, item=item, idempotency_key="request-1")
        await db.commit()
        second_task_id, second_reused = await create_video_task_record(db, item=item, idempotency_key="request-1")

        assert first_reused is False
        assert second_reused is True
        assert first_task_id == second_task_id
        assert int(await db.scalar(select(func.count(GenerationTask.id))) or 0) == 1
        assert int(await db.scalar(select(func.count(GenerationIdempotencyRecord.id))) or 0) == 1

        changed = item.model_copy(update={"prompt": "Different request"})
        with pytest.raises(HTTPException) as exc_info:
            await create_video_task_record(db, item=changed, idempotency_key="request-1")
        assert exc_info.value.status_code == 409
    await engine.dispose()


@pytest.mark.asyncio
async def test_download_failure_preserves_provider_result_for_retry_without_resubmission() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        item = _batch().items[0]
        task_id, _ = await create_video_task_record(db, item=item)
        provider_result = {
            "url": "https://provider.invalid/already-generated.mp4",
            "provider": "openai",
            "status": "completed",
            "artifacts": [],
        }
        await record_provider_completed(db, task_id=task_id, result_payload=provider_result)
        await fail_video_usage(db, task_id=task_id, error="temporary object storage outage")
        await db.commit()

        checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
        ledger = (await db.execute(select(UsageLedgerEntry).where(UsageLedgerEntry.task_id == task_id))).scalar_one()
        assert checkpoint is not None
        assert checkpoint.state == "download_failed"
        assert checkpoint.checkpoint["provider_result"] == provider_result
        assert ledger.status == "provider_completed"
        assert ledger.settled_at is None

        await update_execution_started(db, task_id=task_id)
        assert checkpoint.state == "resuming_download"
    await engine.dispose()


@pytest.mark.asyncio
async def test_checkpoint_rejects_inline_video_bytes() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        task_id, _ = await create_video_task_record(db, item=_batch().items[0])

        with pytest.raises(ValueError, match="durable file reference"):
            await record_provider_completed(
                db,
                task_id=task_id,
                result_payload={
                    "url": "data:video/mp4;base64," + ("A" * 100_000),
                    "provider": "vertex",
                    "status": "completed",
                    "artifacts": [],
                },
            )

        checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
        assert checkpoint is not None
        assert "provider_result" not in checkpoint.checkpoint
    await engine.dispose()


@pytest.mark.asyncio
async def test_local_estimate_is_not_recorded_as_provider_actual_cost() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        task_id, _ = await create_video_task_record(db, item=_batch().items[0])
        await settle_video_usage(db, task_id=task_id, result_payload={"file_id": "file-1", "metadata": {}})
        await db.commit()

        ledger = (await db.execute(select(UsageLedgerEntry).where(UsageLedgerEntry.task_id == task_id))).scalar_one()
        assert ledger.estimated_amount == Decimal("1.250000")
        assert ledger.actual_amount is None
        assert ledger.status == "completed_estimated"
        assert ledger.settled_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_reported_actual_cost_overrides_local_estimate() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        task_id, _ = await create_video_task_record(db, item=_batch().items[0])
        await settle_video_usage(
            db,
            task_id=task_id,
            result_payload={"file_id": "file-1", "metadata": {"cost": "1.10", "currency": "USD"}},
        )
        await db.commit()

        ledger = (await db.execute(select(UsageLedgerEntry).where(UsageLedgerEntry.task_id == task_id))).scalar_one()
        assert ledger.estimated_amount == Decimal("1.250000")
        assert ledger.actual_amount == Decimal("1.100000")
        assert ledger.status == "settled"
    await engine.dispose()


@pytest.mark.asyncio
async def test_completed_unpriced_usage_can_be_backfilled_without_inventing_actual_cost() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True, priced=False)
        item = _batch().items[0].model_copy(update={"provider_params": {"resolution": "360p"}})
        task_id, _ = await create_video_task_record(db, item=item)
        await settle_video_usage(db, task_id=task_id, result_payload={"file_id": "file-1", "metadata": {}})
        model = await db.get(Model, "video-model")
        assert model is not None
        model.params = {"pricing_catalog": pricing_catalog_for_model("vertex-gemini-omni-1-1-flash")}

        updated = await backfill_completed_unpriced_usage_from_catalog(db, task_id=task_id)
        await db.commit()

        ledger = (await db.execute(select(UsageLedgerEntry).where(UsageLedgerEntry.task_id == task_id))).scalar_one()
        assert updated == 1
        assert ledger.status == "completed_estimated"
        assert ledger.estimated_amount == Decimal("0.168962")
        assert ledger.actual_amount is None
        assert ledger.request_summary["pricing_snapshot"]["matched_rule"]["selectors"] == {"resolution": "360p"}
        assert ledger.request_summary["pricing_backfilled_at"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_admission_blocks_when_project_budget_would_be_exceeded() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db, approve_keyframe=True)
        db.add(
            ProjectResearch(
                project_id="project-1",
                entry_mode="research",
                status="draft",
                brief={
                    "product_asset_file_ids": ["asset-1"],
                    "budget_amount": "1.00",
                    "budget_currency": "USD",
                },
                sources=[],
                findings=[],
                creative_directions=[],
            )
        )
        await db.commit()

        batch = await create_video_batch(db, project_id="project-1", body=_batch())
        await db.commit()
        summary = await usage_summary(db, project_id="project-1")

        assert batch.status == "blocked"
        assert any(item["code"] == "budget_exceeded" for item in batch.admission["blockers"])
        assert int(await db.scalar(select(func.count(GenerationTask.id))) or 0) == 0
        assert summary["budget"]["remaining"] == Decimal("1.00")
    await engine.dispose()
