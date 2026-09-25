from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai_video.core.task_manager import DeliveryMode, SqlAlchemyTaskStore
from app.ai_video.models.llm import Model
from app.ai_video.models.production_control import ProductionRevision
from app.ai_video.models.production_execution import (
    GenerationBatch,
    GenerationBatchItem,
    GenerationIdempotencyRecord,
    ProviderExecutionCheckpoint,
    UsageLedgerEntry,
)
from app.ai_video.models.studio import Chapter, Project, ProjectResearch, Shot, ShotDetail
from app.ai_video.models.task import GenerationTask, GenerationTaskStatus
from app.ai_video.models.task_links import GenerationTaskLink
from app.ai_video.schemas.studio.production_execution import VideoBatchConfirm, VideoBatchCreate, VideoBatchItemRequest
from app.ai_video.services.film.generated_video import build_run_args
from app.ai_video.services.llm.pricing_catalog import estimate_video_price
from app.ai_video.services.studio.production_control import canonical_fingerprint
from app.ai_video.services.studio.shot_status import mark_shot_generating


ACTIVE_TASK_STATUSES = {
    GenerationTaskStatus.pending,
    GenerationTaskStatus.running,
    GenerationTaskStatus.streaming,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def project_id_for_shot(db: AsyncSession, *, shot_id: str) -> str | None:
    stmt = (
        select(Chapter.project_id)
        .join(Shot, Shot.chapter_id == Chapter.id)
        .where(Shot.id == shot_id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def find_idempotent_video_task(
    db: AsyncSession,
    *,
    shot_id: str,
    idempotency_key: str | None,
    request_payload: dict[str, Any],
) -> tuple[str | None, str]:
    fingerprint = canonical_fingerprint(request_payload)
    key = (idempotency_key or "").strip()
    if not key:
        return None, fingerprint
    if len(key) > 128:
        raise HTTPException(status_code=400, detail="Idempotency-Key must be at most 128 characters")
    stmt = (
        select(GenerationIdempotencyRecord)
        .where(
            GenerationIdempotencyRecord.scope_type == "shot",
            GenerationIdempotencyRecord.scope_id == shot_id,
            GenerationIdempotencyRecord.operation == "video_generation",
            GenerationIdempotencyRecord.idempotency_key == key,
        )
        .with_for_update()
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is None:
        return None, fingerprint
    if existing.request_fingerprint != fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used with a different video request",
        )
    return existing.task_id, fingerprint


async def register_video_task_controls(
    db: AsyncSession,
    *,
    task_id: str,
    shot_id: str,
    run_args: dict[str, Any],
    request_fingerprint: str,
    idempotency_key: str | None = None,
    quote_fingerprint: str | None = None,
    confirmed_by: str | None = None,
) -> None:
    provider = str(run_args.get("provider") or "")
    model_id = str(run_args.get("model_id") or "") or None
    project_id = await project_id_for_shot(db, shot_id=shot_id)
    db.add(
        ProviderExecutionCheckpoint(
            task_id=task_id,
            provider=provider,
            model_id=model_id,
            state="prepared",
            request_fingerprint=canonical_fingerprint(run_args),
            checkpoint={
                "shot_id": shot_id,
                "quote_fingerprint": quote_fingerprint,
                "confirmed_by": confirmed_by,
            },
        )
    )
    model = await db.get(Model, model_id) if model_id else None
    seconds = int(((run_args.get("input") or {}).get("seconds") or 0))
    provider_params = ((run_args.get("input") or {}).get("provider_params") or {})
    price = estimate_video_price(model, seconds=seconds, provider_params=provider_params) if model else {"complete": False, "reason": "model_not_found"}
    db.add(
        UsageLedgerEntry(
            id=_new_id("usage"),
            project_id=project_id,
            task_id=task_id,
            provider=provider,
            model_id=model_id,
            operation="video_generation",
            status="estimated" if price.get("complete") else "unpriced",
            quantity=price.get("quantity") if price.get("complete") else Decimal(seconds),
            unit=price.get("unit") if price.get("complete") else "second",
            currency=price.get("currency"),
            estimated_amount=price.get("amount"),
            request_summary={
                "shot_id": shot_id,
                "pricing_source": price.get("estimate_kind") if price.get("complete") else None,
                "pricing_reason": price.get("reason"),
                "pricing_snapshot": price.get("pricing_snapshot"),
                "estimate_scope": price.get("estimate_scope"),
                "estimate_exclusions": price.get("exclusions") or [],
                "quote_fingerprint": quote_fingerprint,
                "confirmed_by": confirmed_by,
            },
        )
    )
    key = (idempotency_key or "").strip()
    if key:
        db.add(
            GenerationIdempotencyRecord(
                id=_new_id("idem"),
                scope_type="shot",
                scope_id=shot_id,
                operation="video_generation",
                idempotency_key=key,
                request_fingerprint=request_fingerprint,
                task_id=task_id,
            )
        )


async def create_video_task_record(
    db: AsyncSession,
    *,
    item: VideoBatchItemRequest,
    idempotency_key: str | None = None,
    quote_fingerprint: str | None = None,
    confirmed_by: str | None = None,
) -> tuple[str, bool]:
    payload = item.model_dump(mode="json")
    existing_task_id, request_fingerprint = await find_idempotent_video_task(
        db,
        shot_id=item.shot_id,
        idempotency_key=idempotency_key,
        request_payload=payload,
    )
    if existing_task_id:
        return existing_task_id, True
    run_args = await build_run_args(
        db,
        shot_id=item.shot_id,
        reference_mode=item.reference_mode,
        prompt=item.prompt,
        images=item.images,
        ratio=item.ratio,
        model_id=item.model_id,
        provider_params=item.provider_params,
    )
    store = SqlAlchemyTaskStore(db)
    task = await store.create(
        payload={
            "task_class": "_CreateOnlyTask",
            "task_kind": "video_generation",
            "run_args": run_args,
        },
        mode=DeliveryMode.async_polling,
        task_kind="video_generation",
    )
    db.add(
        GenerationTaskLink(
            task_id=task.id,
            resource_type="video",
            relation_type="video",
            relation_entity_id=item.shot_id,
        )
    )
    await register_video_task_controls(
        db,
        task_id=task.id,
        shot_id=item.shot_id,
        run_args=run_args,
        request_fingerprint=request_fingerprint,
        idempotency_key=idempotency_key,
        quote_fingerprint=quote_fingerprint,
        confirmed_by=confirmed_by,
    )
    await mark_shot_generating(db, shot_id=item.shot_id)
    return task.id, False


async def _batch_blockers(
    db: AsyncSession,
    *,
    project_id: str,
    items: list[VideoBatchItemRequest],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    shot_ids = [item.shot_id for item in items]
    member_stmt = (
        select(Shot.id)
        .join(Chapter, Chapter.id == Shot.chapter_id)
        .where(Chapter.project_id == project_id, Shot.id.in_(shot_ids))
    )
    member_ids = set((await db.execute(member_stmt)).scalars().all())
    for shot_id in shot_ids:
        if shot_id not in member_ids:
            blockers.append({"code": "shot_not_in_project", "shot_id": shot_id, "message": "Shot does not belong to project"})
    if not member_ids:
        return blockers

    keyframe_stmt = select(ProductionRevision.scope_id).where(
        ProductionRevision.project_id == project_id,
        ProductionRevision.kind == "keyframe",
        ProductionRevision.scope_type == "shot",
        ProductionRevision.scope_id.in_(member_ids),
        ProductionRevision.state == "approved",
    )
    approved_keyframes = set((await db.execute(keyframe_stmt)).scalars().all())
    for shot_id in sorted(member_ids):
        if shot_id not in approved_keyframes:
            blockers.append({"code": "keyframe_not_approved", "shot_id": shot_id, "message": "Shot requires an approved keyframe revision"})

    duration_stmt = select(ShotDetail.id, ShotDetail.duration).where(ShotDetail.id.in_(member_ids))
    durations = {row.id: row.duration for row in (await db.execute(duration_stmt)).all()}
    for shot_id in sorted(member_ids):
        if int(durations.get(shot_id) or 0) <= 0:
            blockers.append({"code": "duration_missing", "shot_id": shot_id, "message": "Shot duration must be greater than zero"})

    active_stmt = (
        select(GenerationTaskLink.relation_entity_id, GenerationTask.id)
        .join(GenerationTask, GenerationTask.id == GenerationTaskLink.task_id)
        .where(
            GenerationTaskLink.resource_type == "video",
            GenerationTaskLink.relation_type == "video",
            GenerationTaskLink.relation_entity_id.in_(member_ids),
            GenerationTask.status.in_(ACTIVE_TASK_STATUSES),
        )
    )
    for shot_id, task_id in (await db.execute(active_stmt)).all():
        blockers.append({"code": "generation_in_flight", "shot_id": shot_id, "task_id": task_id, "message": "Shot already has an active video generation task"})
    return blockers


async def _price_video_item(
    db: AsyncSession,
    *,
    item: VideoBatchItemRequest,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_args = await build_run_args(
        db,
        shot_id=item.shot_id,
        reference_mode=item.reference_mode,
        prompt=item.prompt,
        images=item.images,
        ratio=item.ratio,
        model_id=item.model_id,
        provider_params=item.provider_params,
    )
    model = await db.get(Model, str(run_args.get("model_id") or ""))
    seconds = int(((run_args.get("input") or {}).get("seconds") or 0))
    provider_params = ((run_args.get("input") or {}).get("provider_params") or {})
    price = (
        estimate_video_price(model, seconds=seconds, provider_params=provider_params)
        if model
        else {"complete": False, "reason": "model_not_found"}
    )
    estimate = {
        "shot_id": item.shot_id,
        "model_id": run_args.get("model_id"),
        **{key: str(value) if isinstance(value, Decimal) else value for key, value in price.items()},
    }
    return run_args, estimate


async def quote_video_item(
    db: AsyncSession,
    *,
    item: VideoBatchItemRequest,
) -> dict[str, Any]:
    """Return a complete quote bound to the exact request and resolved model."""

    _run_args, estimate = await _price_video_item(db, item=item)
    if not estimate.get("complete"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pricing_unavailable",
                "message": "A complete local price is required before video generation",
                "reason": estimate.get("reason") or "unknown",
            },
        )
    quote = {
        "complete": True,
        "currency": estimate.get("currency"),
        "amount": estimate.get("amount"),
        "quantity": estimate.get("quantity"),
        "unit": estimate.get("unit"),
        "unit_amount": estimate.get("unit_amount"),
        "model_id": estimate.get("model_id"),
        "estimate_kind": estimate.get("estimate_kind"),
        "estimate_scope": estimate.get("estimate_scope"),
        "exclusions": estimate.get("exclusions") or [],
        "pricing_snapshot": estimate.get("pricing_snapshot"),
    }
    quote["quote_fingerprint"] = canonical_fingerprint(
        {
            "item": item.model_dump(mode="json"),
            "quote": quote,
        }
    )
    return quote


async def _video_batch_preflight(
    db: AsyncSession,
    *,
    project_id: str,
    items: list[VideoBatchItemRequest],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    blockers = await _batch_blockers(db, project_id=project_id, items=items)
    estimates: list[dict[str, Any]] = []
    if not blockers:
        for item in items:
            try:
                _run_args, estimate = await _price_video_item(db, item=item)
                estimates.append(estimate)
            except HTTPException as exc:
                blockers.append(
                    {
                        "code": "preflight_failed",
                        "shot_id": item.shot_id,
                        "message": str(exc.detail),
                    }
                )

    complete = bool(estimates) and all(item.get("complete") for item in estimates)
    currencies = {str(item.get("currency")) for item in estimates if item.get("complete")}
    total = sum((Decimal(str(item["amount"])) for item in estimates if item.get("complete")), Decimal("0"))
    estimate: dict[str, Any] = {
        "complete": complete and len(currencies) == 1,
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "total": str(total) if complete and len(currencies) == 1 else None,
        "items": estimates,
        "pricing_contract": "versioned models.params.pricing_catalog; legacy models.params.pricing remains supported",
    }

    if estimates and not estimate["complete"]:
        blockers.append(
            {
                "code": "pricing_unavailable",
                "message": "Every item requires a complete price before the batch can be confirmed",
                "items": [
                    {"shot_id": item.get("shot_id"), "reason": item.get("reason") or "currency_mismatch"}
                    for item in estimates
                    if not item.get("complete")
                ],
            }
        )

    research = await db.get(ProjectResearch, project_id)
    brief = research.brief if research and isinstance(research.brief, dict) else {}
    raw_budget = brief.get("budget_amount") if isinstance(brief, dict) else None
    budget_currency = str(brief.get("budget_currency") or "").strip().upper() if isinstance(brief, dict) else ""
    if raw_budget is not None and budget_currency:
        try:
            budget_amount = Decimal(str(raw_budget))
        except InvalidOperation:
            budget_amount = None
        if budget_amount is not None:
            ledger_rows = list(
                (
                    await db.execute(
                        select(UsageLedgerEntry).where(
                            UsageLedgerEntry.project_id == project_id,
                            UsageLedgerEntry.currency == budget_currency,
                            UsageLedgerEntry.status.not_in({"failed", "refunded"}),
                        )
                    )
                ).scalars().all()
            )
            committed = sum(
                (row.actual_amount if row.actual_amount is not None else row.estimated_amount or Decimal("0") for row in ledger_rows),
                Decimal("0"),
            )
            remaining = budget_amount - committed
            estimate["budget"] = {
                "currency": budget_currency,
                "amount": str(budget_amount),
                "committed": str(committed),
                "remaining_before_batch": str(remaining),
            }
            if estimate["complete"] and estimate["currency"] != budget_currency:
                blockers.append(
                    {
                        "code": "budget_currency_mismatch",
                        "message": "Batch estimate currency does not match the project budget currency",
                        "budget_currency": budget_currency,
                        "estimate_currency": estimate["currency"],
                    }
                )
            elif estimate["complete"] and total > remaining:
                blockers.append(
                    {
                        "code": "budget_exceeded",
                        "message": "Batch estimate exceeds the remaining project generation budget",
                        "budget": str(budget_amount),
                        "committed": str(committed),
                        "remaining": str(remaining),
                        "batch_estimate": str(total),
                        "currency": budget_currency,
                    }
                )

    if estimate["complete"]:
        estimate["quote_fingerprint"] = canonical_fingerprint(
            {
                "project_id": project_id,
                "items": [item.model_dump(mode="json") for item in items],
                "estimate": estimate,
            }
        )
    return blockers, estimate


async def create_video_batch(
    db: AsyncSession,
    *,
    project_id: str,
    body: VideoBatchCreate,
) -> GenerationBatch:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    batch = GenerationBatch(
        id=_new_id("batch"),
        project_id=project_id,
        kind="video_generation",
        status="admission_pending",
        requested_ids=[item.shot_id for item in body.items],
        admission={},
        estimate={},
    )
    db.add(batch)
    await db.flush()

    blockers, estimate = await _video_batch_preflight(db, project_id=project_id, items=body.items)
    batch.admission = {
        "admitted": not blockers,
        "blockers": blockers,
        "all_or_none": True,
        "request_items": [item.model_dump(mode="json") for item in body.items],
    }
    batch.estimate = estimate

    item_status = "blocked" if blockers else "confirmation_required"
    for item in body.items:
        db.add(
            GenerationBatchItem(
                id=_new_id("batchitem"),
                batch_id=batch.id,
                target_type="shot",
                target_id=item.shot_id,
                status=item_status,
                error_code="batch_admission_failed" if blockers else None,
                error_message="; ".join(
                    str(problem["message"]) for problem in blockers if problem.get("shot_id") == item.shot_id
                ),
            )
        )
    await db.flush()

    batch.status = "blocked" if blockers else "confirmation_required"
    await db.flush()
    refreshed = (
        await db.execute(
            select(GenerationBatch)
            .options(selectinload(GenerationBatch.items))
            .where(GenerationBatch.id == batch.id)
        )
    ).scalar_one()
    return refreshed


async def confirm_video_batch(
    db: AsyncSession,
    *,
    project_id: str,
    batch_id: str,
    body: VideoBatchConfirm,
) -> tuple[GenerationBatch, list[str]]:
    stmt = (
        select(GenerationBatch)
        .options(selectinload(GenerationBatch.items))
        .where(GenerationBatch.id == batch_id, GenerationBatch.project_id == project_id)
        .with_for_update()
    )
    batch = (await db.execute(stmt)).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Generation batch not found")
    stored_fingerprint = str((batch.estimate or {}).get("quote_fingerprint") or "")
    if body.quote_fingerprint != stored_fingerprint:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote does not match the preflight batch")
    if batch.status == "queued":
        return batch, []
    if batch.status != "confirmation_required":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Batch is not awaiting confirmation")

    raw_items = (batch.admission or {}).get("request_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Batch request snapshot is unavailable; run preflight again")
    items = [VideoBatchItemRequest.model_validate(item) for item in raw_items]
    blockers, refreshed_estimate = await _video_batch_preflight(db, project_id=project_id, items=items)
    refreshed_fingerprint = str(refreshed_estimate.get("quote_fingerprint") or "")
    if blockers or refreshed_fingerprint != stored_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Price, budget, or generation inputs changed; run preflight again",
        )

    by_target = {row.target_id: row for row in batch.items}
    new_task_ids: list[str] = []
    for item in items:
        task_id, reused = await create_video_task_record(
            db,
            item=item,
            quote_fingerprint=stored_fingerprint,
            confirmed_by=body.confirmed_by,
        )
        row = by_target[item.shot_id]
        row.task_id = task_id
        row.status = "reused" if reused else "queued"
        if not reused:
            new_task_ids.append(task_id)
    batch.status = "queued"
    batch.confirmed_by = body.confirmed_by
    batch.confirmed_at = _utcnow()
    batch.estimate = refreshed_estimate
    await db.flush()
    return batch, new_task_ids


async def update_execution_started(db: AsyncSession, *, task_id: str) -> None:
    checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
    if checkpoint is not None:
        checkpoint.state = (
            "resuming_download"
            if checkpoint.state in {"provider_completed", "download_failed", "resuming_download"}
            and isinstance(checkpoint.checkpoint.get("provider_result"), dict)
            else "running"
        )
        checkpoint.last_error_code = None
        checkpoint.last_error_message = ""


async def update_execution_external_pending(
    db: AsyncSession,
    *,
    task_id: str,
    run_args: dict[str, Any],
) -> None:
    checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
    if checkpoint is None:
        return
    checkpoint.state = "provider_pending"
    checkpoint.poll_attempts += 1
    provider_state = run_args.get("creatify") if isinstance(run_args.get("creatify"), dict) else {}
    checkpoint.external_job_id = str(provider_state.get("job_id") or checkpoint.external_job_id or "") or None
    checkpoint.checkpoint = {**checkpoint.checkpoint, "provider_state": provider_state}


async def record_provider_completed(
    db: AsyncSession,
    *,
    task_id: str,
    result_payload: dict[str, Any],
) -> None:
    inline_url = str(result_payload.get("url") or "")
    if inline_url.startswith("data:"):
        raise ValueError("Provider checkpoint requires a durable file reference instead of inline media bytes")
    checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
    if checkpoint is None:
        return
    checkpoint.state = "provider_completed"
    checkpoint.provider_completed_at = checkpoint.provider_completed_at or _utcnow()
    checkpoint.checkpoint = {**checkpoint.checkpoint, "provider_result": result_payload}


async def settle_video_usage(
    db: AsyncSession,
    *,
    task_id: str,
    result_payload: dict[str, Any],
) -> None:
    checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
    if checkpoint is not None:
        checkpoint.state = "downloaded"
        checkpoint.provider_completed_at = checkpoint.provider_completed_at or _utcnow()
        checkpoint.downloaded_at = _utcnow()
        checkpoint.billing_settlement_key = checkpoint.billing_settlement_key or f"video:{task_id}"
        checkpoint.checkpoint = {**checkpoint.checkpoint, "file_id": result_payload.get("file_id")}
    stmt = select(UsageLedgerEntry).where(UsageLedgerEntry.task_id == task_id).with_for_update()
    ledger = (await db.execute(stmt)).scalar_one_or_none()
    if ledger is None or ledger.settled_at is not None:
        return
    metadata = result_payload.get("metadata") if isinstance(result_payload.get("metadata"), dict) else {}
    actual = metadata.get("cost")
    actual_currency = str(metadata.get("currency") or "").strip().upper()
    if actual is not None and actual_currency:
        try:
            ledger.actual_amount = Decimal(str(actual))
            ledger.currency = actual_currency
            ledger.status = "settled"
        except InvalidOperation:
            ledger.status = "completed_unpriced"
    elif ledger.estimated_amount is not None:
        # A local catalog estimate is not a provider-reported charge.
        ledger.actual_amount = None
        ledger.status = "completed_estimated"
    else:
        ledger.status = "completed_unpriced"
    ledger.response_summary = {"file_id": result_payload.get("file_id"), "provider_metadata": metadata}
    ledger.settled_at = _utcnow()


async def backfill_completed_unpriced_usage_from_catalog(
    db: AsyncSession,
    *,
    task_id: str | None = None,
) -> int:
    """Attach catalog estimates to completed rows that lack provider billing.

    This intentionally leaves ``actual_amount`` empty.  The persisted snapshot
    makes the historical estimate reproducible without rewriting it as a bill.
    """
    await db.flush()
    stmt = select(UsageLedgerEntry).where(
        UsageLedgerEntry.operation == "video_generation",
        UsageLedgerEntry.status == "completed_unpriced",
        UsageLedgerEntry.actual_amount.is_(None),
    )
    if task_id:
        stmt = stmt.where(UsageLedgerEntry.task_id == task_id)
    rows = list((await db.execute(stmt.with_for_update())).scalars().all())
    updated = 0
    for ledger in rows:
        task = await db.get(GenerationTask, ledger.task_id)
        payload = task.payload if task is not None and isinstance(task.payload, dict) else {}
        run_args = payload.get("run_args") if isinstance(payload.get("run_args"), dict) else {}
        input_payload = run_args.get("input") if isinstance(run_args.get("input"), dict) else {}
        model_id = str(run_args.get("model_id") or ledger.model_id or "")
        model = await db.get(Model, model_id) if model_id else None
        try:
            seconds = int(input_payload.get("seconds") or ledger.quantity or 0)
        except (TypeError, ValueError):
            continue
        provider_params = input_payload.get("provider_params") if isinstance(input_payload.get("provider_params"), dict) else {}
        price = estimate_video_price(model, seconds=seconds, provider_params=provider_params) if model else {"complete": False}
        if not price.get("complete") or price.get("estimate_kind") != "catalog_output_estimate":
            continue
        ledger.quantity = price["quantity"]
        ledger.unit = price["unit"]
        ledger.currency = price["currency"]
        ledger.estimated_amount = price["amount"]
        ledger.status = "completed_estimated"
        ledger.request_summary = {
            **(ledger.request_summary or {}),
            "pricing_source": price["estimate_kind"],
            "pricing_reason": None,
            "pricing_snapshot": price["pricing_snapshot"],
            "estimate_scope": price.get("estimate_scope"),
            "estimate_exclusions": price.get("exclusions") or [],
            "pricing_backfilled_at": _utcnow().isoformat(),
        }
        updated += 1
    await db.flush()
    return updated


async def fail_video_usage(db: AsyncSession, *, task_id: str, error: str) -> None:
    checkpoint = await db.get(ProviderExecutionCheckpoint, task_id)
    provider_already_completed = bool(
        checkpoint is not None
        and checkpoint.provider_completed_at is not None
        and isinstance(checkpoint.checkpoint.get("provider_result"), dict)
    )
    if checkpoint is not None:
        checkpoint.state = "download_failed" if provider_already_completed else "failed"
        checkpoint.last_error_code = "download_failed" if provider_already_completed else "execution_failed"
        checkpoint.last_error_message = error
    stmt = select(UsageLedgerEntry).where(UsageLedgerEntry.task_id == task_id).with_for_update()
    ledger = (await db.execute(stmt)).scalar_one_or_none()
    if ledger is not None and ledger.settled_at is None:
        ledger.status = "provider_completed" if provider_already_completed else "failed"
        ledger.error_code = "download_failed" if provider_already_completed else "execution_failed"
        ledger.error_message = error
        if not provider_already_completed:
            ledger.settled_at = _utcnow()


async def usage_summary(db: AsyncSession, *, project_id: str) -> dict[str, Any]:
    rows = list(
        (
            await db.execute(
                select(UsageLedgerEntry).where(UsageLedgerEntry.project_id == project_id)
            )
        ).scalars().all()
    )
    by_currency: dict[str, dict[str, Decimal]] = {}
    unpriced = 0
    for row in rows:
        if not row.currency:
            unpriced += 1
            continue
        bucket = by_currency.setdefault(row.currency, {"estimated": Decimal("0"), "actual": Decimal("0")})
        bucket["estimated"] += row.estimated_amount or Decimal("0")
        bucket["actual"] += row.actual_amount or Decimal("0")
    research = await db.get(ProjectResearch, project_id)
    brief = research.brief if research and isinstance(research.brief, dict) else {}
    budget: dict[str, Any] | None = None
    raw_budget = brief.get("budget_amount") if isinstance(brief, dict) else None
    budget_currency = str(brief.get("budget_currency") or "").strip().upper() if isinstance(brief, dict) else ""
    if raw_budget is not None and budget_currency:
        amount = Decimal(str(raw_budget))
        bucket = by_currency.get(budget_currency, {"estimated": Decimal("0"), "actual": Decimal("0")})
        committed = max(bucket["estimated"], bucket["actual"])
        budget = {
            "currency": budget_currency,
            "amount": amount,
            "committed": committed,
            "remaining": amount - committed,
        }
    return {
        "project_id": project_id,
        "by_currency": by_currency,
        "unpriced_entries": unpriced,
        "total_entries": len(rows),
        "budget": budget,
    }


__all__ = [
    "create_video_batch",
    "create_video_task_record",
    "fail_video_usage",
    "find_idempotent_video_task",
    "record_provider_completed",
    "register_video_task_controls",
    "settle_video_usage",
    "update_execution_external_pending",
    "update_execution_started",
    "usage_summary",
]
