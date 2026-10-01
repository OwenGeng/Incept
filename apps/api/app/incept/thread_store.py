from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from app.incept.db import init_db, load_threads, upsert_thread
from app.incept.datetime_utils import utcnow_naive
from app.incept.models import Asset, CreativeThread, GenerationJob, GenerationMode, ThreadMessage

THREADS: dict[str, CreativeThread] = {}


def _bootstrap() -> None:
    init_db()  # Ensure tables exist before reading (safe to call multiple times)
    for row in load_threads():
        try:
            thread = CreativeThread(
                thread_id=row["thread_id"],
                workspace_id=row["workspace_id"] or "",
                title=row["title"] or "Untitled thread",
                generation_mode=GenerationMode(row["generation_mode"] or GenerationMode.free_create.value),
                created_by=row["created_by"] or "",
                origin_asset_id=row["origin_asset_id"],
                cover_asset_id=row["cover_asset_id"],
                latest_asset_id=row["latest_asset_id"],
                latest_job_id=row["latest_job_id"],
                messages=[
                    ThreadMessage.model_validate(message)
                    for message in json.loads(row.get("messages_json") or "[]")
                ],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            THREADS[thread.thread_id] = thread
        except Exception:
            continue


_bootstrap()


def list_threads(workspace_id: str | None = None) -> list[CreativeThread]:
    values = list(THREADS.values())
    if workspace_id:
        values = [thread for thread in values if thread.workspace_id == workspace_id]
    return sorted(values, key=lambda item: item.updated_at, reverse=True)


def get_thread(thread_id: str) -> CreativeThread | None:
    return THREADS.get(thread_id)


def delete_thread(thread_id: str) -> bool:
    """Remove a thread from memory and SQLite. Returns True if it existed."""
    thread = THREADS.pop(thread_id, None)
    if not thread:
        return False
    from app.incept.db import delete_thread as db_delete_thread
    db_delete_thread(thread_id)
    return True


def rename_thread(thread_id: str, new_title: str) -> CreativeThread | None:
    thread = THREADS.get(thread_id)
    if not thread:
        return None
    thread.title = new_title.strip() or thread.title
    from app.incept.db import upsert_thread
    upsert_thread(thread)
    return thread


def delete_empty_threads() -> int:
    """
    Delete threads that have no assets AND no jobs AND are older than 1 day.

    The 1-day cutoff prevents accidental deletion of:
    - threads whose assets pre-date the thread_id field (thread_id=None on old assets)
    - threads that were just created but haven't received a generation yet
    """
    from datetime import datetime, timedelta
    from app.incept.db import delete_thread as db_delete_thread
    from app.incept.store import ASSETS, JOBS  # avoid circular at import time

    cutoff = utcnow_naive() - timedelta(days=1)
    asset_thread_ids = {a.thread_id for a in ASSETS.values() if a.thread_id}
    job_thread_ids   = {j.thread_id for j in JOBS.values() if j.thread_id}
    used_thread_ids  = asset_thread_ids | job_thread_ids

    empty = [
        t for t in list(THREADS.values())
        if t.thread_id not in used_thread_ids
        and t.updated_at < cutoff
    ]
    for thread in empty:
        THREADS.pop(thread.thread_id, None)
        db_delete_thread(thread.thread_id)
    return len(empty)


def create_thread(
    workspace_id: str,
    title: str,
    generation_mode: GenerationMode = GenerationMode.free_create,
    created_by: str = "",
    origin_asset_id: str | None = None,
) -> CreativeThread:
    now = utcnow_naive()
    thread = CreativeThread(
        thread_id=f"thr_{uuid4().hex[:12]}",
        workspace_id=workspace_id,
        title=title.strip() or "Untitled thread",
        generation_mode=generation_mode,
        created_by=created_by,
        origin_asset_id=origin_asset_id,
        created_at=now,
        updated_at=now,
    )
    THREADS[thread.thread_id] = thread
    upsert_thread(thread)
    return thread


def ensure_thread(
    workspace_id: str,
    title: str,
    generation_mode: GenerationMode = GenerationMode.free_create,
    created_by: str = "",
    thread_id: str | None = None,
    origin_asset_id: str | None = None,
) -> CreativeThread:
    if thread_id and thread_id in THREADS:
        thread = THREADS[thread_id]
        changed = False
        if generation_mode and thread.generation_mode != generation_mode:
            thread.generation_mode = generation_mode
            changed = True
        if origin_asset_id and not thread.origin_asset_id:
            thread.origin_asset_id = origin_asset_id
            changed = True
        normalized_title = title.strip()
        if normalized_title and thread.title.lower() in {"untitled thread", "new thread"}:
            thread.title = normalized_title
            changed = True
        if changed:
            thread.updated_at = utcnow_naive()
            upsert_thread(thread)
        return thread
    return create_thread(
        workspace_id=workspace_id,
        title=title,
        generation_mode=generation_mode,
        created_by=created_by,
        origin_asset_id=origin_asset_id,
    )


def touch_thread(
    thread_id: str,
    *,
    latest_job_id: str | None = None,
    latest_asset_id: str | None = None,
    cover_asset_id: str | None = None,
    title: str | None = None,
) -> CreativeThread | None:
    thread = THREADS.get(thread_id)
    if not thread:
        return None
    if latest_job_id:
        thread.latest_job_id = latest_job_id
    if latest_asset_id:
        thread.latest_asset_id = latest_asset_id
    if cover_asset_id:
        thread.cover_asset_id = cover_asset_id
    if title and title.strip():
        thread.title = title.strip()
    thread.updated_at = utcnow_naive()
    upsert_thread(thread)
    return thread


def hydrate_thread_summaries(
    *,
    assets: list[Asset],
    jobs: list[GenerationJob],
) -> list[CreativeThread]:
    assets_by_thread: dict[str, list[Asset]] = {}
    jobs_by_thread: dict[str, list[GenerationJob]] = {}

    for asset in assets:
        if asset.thread_id:
            assets_by_thread.setdefault(asset.thread_id, []).append(asset)
    for job in jobs:
        if job.thread_id:
            jobs_by_thread.setdefault(job.thread_id, []).append(job)

    summaries: list[CreativeThread] = []
    for thread in list_threads():
        thread_assets = sorted(
            assets_by_thread.get(thread.thread_id, []),
            key=lambda item: item.created_at,
            reverse=True,
        )
        thread_jobs = sorted(
            jobs_by_thread.get(thread.thread_id, []),
            key=lambda item: item.created_at,
            reverse=True,
        )
        enriched = thread.model_copy(deep=True)
        enriched.asset_count = len(thread_assets)
        enriched.job_count = len(thread_jobs)
        if not enriched.latest_asset_id and thread_assets:
            enriched.latest_asset_id = thread_assets[0].id
        if not enriched.cover_asset_id and thread_assets:
            enriched.cover_asset_id = thread_assets[-1].id
        cover_asset = next((asset for asset in thread_assets if asset.id == enriched.cover_asset_id), None)
        if not cover_asset and thread_assets:
            cover_asset = thread_assets[-1]
        enriched.preview_url = cover_asset.preview_url if cover_asset else None
        if not enriched.latest_job_id and thread_jobs:
            enriched.latest_job_id = thread_jobs[0].job_id
        if thread_assets or thread_jobs:
            enriched.updated_at = max(
                [thread.updated_at] +
                [asset.created_at for asset in thread_assets] +
                [job.updated_at for job in thread_jobs]
            )
        summaries.append(enriched)
    return sorted(summaries, key=lambda item: item.updated_at, reverse=True)


def backfill_legacy_threads(jobs: list[GenerationJob], assets: list[Asset]) -> None:
    existing_thread_ids = {thread.thread_id for thread in THREADS.values()}
    jobs_by_id = {job.job_id: job for job in jobs}
    assets_by_job: dict[str, list[Asset]] = {}
    for asset in assets:
        if asset.job_id:
            assets_by_job.setdefault(asset.job_id, []).append(asset)

    for job in jobs:
        if job.thread_id and job.thread_id in existing_thread_ids:
            continue
        legacy_assets = sorted(
            assets_by_job.get(job.job_id, []),
            key=lambda item: item.created_at,
        )
        title = (
            legacy_assets[0].theme if legacy_assets and legacy_assets[0].theme
            else job.title
            or "Recovered thread"
        )
        if job.thread_id:
            thread = CreativeThread(
                thread_id=job.thread_id,
                workspace_id=job.workspace_id,
                title=title,
                generation_mode=GenerationMode.free_create,
                created_by=legacy_assets[0].created_by if legacy_assets else "",
                origin_asset_id=None,
                cover_asset_id=legacy_assets[0].id if legacy_assets else None,
                latest_asset_id=legacy_assets[-1].id if legacy_assets else None,
                latest_job_id=job.job_id,
                created_at=job.created_at,
                updated_at=max(
                    [job.updated_at] + [asset.created_at for asset in legacy_assets]
                ),
            )
            THREADS[thread.thread_id] = thread
            upsert_thread(thread)
        else:
            thread = create_thread(
                workspace_id=job.workspace_id,
                title=title,
                generation_mode=GenerationMode.free_create,
                created_by=legacy_assets[0].created_by if legacy_assets else "",
                origin_asset_id=None,
            )
            job.thread_id = thread.thread_id
        existing_thread_ids.add(thread.thread_id)
        for asset in legacy_assets:
            asset.thread_id = thread.thread_id
            asset.root_asset_id = asset.root_asset_id or asset.id
        if legacy_assets:
            touch_thread(
                thread.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=legacy_assets[-1].id,
                cover_asset_id=legacy_assets[0].id,
            )

    # Intentionally do not auto-create threads for upload-only/orphan assets.
    # Threads should only be created by explicit user action (New Thread) or
    # by legacy job recovery above.


def add_user_message(
    thread_id: str,
    text: str,
    reference_asset_ids: list[str] | None = None,
) -> None:
    thread = THREADS.get(thread_id)
    if not thread:
        return
    thread.messages.append(
        ThreadMessage(role="user", text=text, asset_ids=reference_asset_ids or [])
    )
    if reference_asset_ids:
        known = set(thread.reference_asset_ids)
        thread.reference_asset_ids = list(known | set(reference_asset_ids))
    thread.updated_at = utcnow_naive()
    upsert_thread(thread)


def add_assistant_message(
    thread_id: str,
    text: str,
    asset_ids: list[str],
    job_id: str,
) -> None:
    thread = THREADS.get(thread_id)
    if not thread:
        return
    thread.messages.append(
        ThreadMessage(role="assistant", text=text, asset_ids=asset_ids, job_id=job_id)
    )
    thread.updated_at = utcnow_naive()
    upsert_thread(thread)


def get_context_messages(thread_id: str, n: int = 6) -> list[dict]:
    thread = THREADS.get(thread_id)
    if not thread:
        return []
    result: list[dict] = []
    for msg in thread.messages[-n:]:
        content = msg.text
        if msg.role == "assistant" and msg.asset_ids:
            content += f"\n[Generated {len(msg.asset_ids)} image(s), job_id={msg.job_id}]"
        result.append({"role": msg.role, "content": content})
    return result
