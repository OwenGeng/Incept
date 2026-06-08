import base64
import logging
import math
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.incept.bigquery_store import persist_generation
from app.incept.config import get_settings
from app.incept.db import delete_asset as db_delete_asset, init_db, load_assets, load_jobs, upsert_asset, upsert_job
from app.incept.guardrails import (
    ClarificationRequired,
    build_anchor_hints_from_manifest,
    build_preservation_manifest,
    clarification_options_for_manifest,
    clarification_for_size,
    ensure_manifest_clarity,
    prompt_preserve_elements,
    prompt_remove_elements,
    validate_output_asset,
)
from app.incept.models import Asset, AssetRole, AddTextRequest, CreativeThread, GenerationJob, GenerationMode, GenerationRequest, ImageEditRequest, JobStatus, OutpaintRequest, RemoveBGRequest, UsageEvent, User, Workspace
from app.incept.orchestrator import detect_layout_anchors, orchestrate
from app.incept.prompt_builder import build_contact_sheet_generation_prompt, build_generation_prompt, build_reference_generation_prompt
from app.incept import thread_store

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent.parent / "static" / "generated"
UPLOAD_DIR = Path(__file__).parent.parent.parent / "static" / "uploads"

# ── Projects (formerly "workspaces") ─────────────────────────────────────────
WORKSPACES: dict[str, Workspace] = {
    "wsp_q2": Workspace(
        id="wsp_q2",
        title="Q2 Campaign Assets",
        description="Lifestyle image variants for skincare launch.",
        owner_user_id="usr_jane",
        team="IM GM",
        status=JobStatus.running,
        updated_at=datetime.utcnow(),
    ),
    "wsp_tiktok": Workspace(
        id="wsp_tiktok",
        title="TikTok Creatives",
        description="Short-form references, hooks, and GIF variants.",
        owner_user_id="usr_jane",
        team="Creative Studio",
        status=JobStatus.pending,
        updated_at=datetime.utcnow(),
    ),
}

JOBS: dict[str, GenerationJob] = {}
ASSETS: dict[str, Asset] = {}
USAGE_EVENTS: dict[str, UsageEvent] = {}
SOURCE_ASSETS: dict[str, Asset] = {}

_LEGACY_ASSET_ROLES = {role.value for role in AssetRole}


def _coerce_asset_role(value: str | None, provider: str = "", theme: str | None = None) -> AssetRole:
    raw = (value or "").strip()
    if raw in _LEGACY_ASSET_ROLES:
        return AssetRole(raw)

    legacy_theme = (theme or "").strip()
    if legacy_theme in _LEGACY_ASSET_ROLES:
        return AssetRole(legacy_theme)

    if provider == "upload":
        return AssetRole.upload
    return AssetRole.generated

# ── Bootstrap: init DB and load persisted data into memory ───────────────────
def _bootstrap() -> None:
    init_db()
    for row in load_jobs():
        try:
            job = GenerationJob(
                job_id=row["job_id"],
                workspace_id=row["workspace_id"],
                status=JobStatus(row["status"]),
                progress=row["progress"],
                lineage_key=row["lineage_key"] or "",
                message=row["message"] or "",
                tool_id=row["tool_id"] or "",
                title=row["title"] or "",
                output_asset_ids=__import__("json").loads(row["output_asset_ids"] or "[]"),
                thread_id=row.get("thread_id"),
                source_asset_id=row.get("source_asset_id"),
                clarification_question=row.get("clarification_question"),
                clarification_reason=row.get("clarification_reason"),
                clarification_options=__import__("json").loads(row.get("clarification_options_json") or "[]"),
                clarification_manifest=__import__("json").loads(row["clarification_manifest_json"]) if row.get("clarification_manifest_json") else None,
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            JOBS[job.job_id] = job
        except Exception:
            logger.warning("Skipping corrupt job row: %s", row.get("job_id"))

    for row in load_assets():
        try:
            asset = Asset(
                id=row["id"],
                title=row["title"] or "",
                type=row["type"] or "image",
                gcs_uri=row["gcs_uri"] or "",
                preview_url=row["preview_url"] or "",
                provider=row["provider"] or "",
                model=row["model"] or "",
                workspace_id=row["workspace_id"] or "",
                job_id=row["job_id"] or "",
                prompt_hash=row["prompt_hash"] or "",
                created_by=row["created_by"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
                width=row["width"],
                height=row["height"],
                theme=None if (row["theme"] or "") in _LEGACY_ASSET_ROLES else row["theme"],
                asset_role=_coerce_asset_role(
                    row.get("asset_role") if isinstance(row, dict) else row["asset_role"],
                    provider=row["provider"] or "",
                    theme=row["theme"],
                ),
                analysis=__import__("json").loads(row["analysis_json"]) if row.get("analysis_json") else None,
                thread_id=row.get("thread_id"),
                parent_asset_id=row.get("parent_asset_id"),
                root_asset_id=row.get("root_asset_id"),
            )
            ASSETS[asset.id] = asset
        except Exception:
            logger.warning("Skipping corrupt asset row: %s", row.get("id"))

    thread_store.backfill_legacy_threads(list(JOBS.values()), list(ASSETS.values()) + list(SOURCE_ASSETS.values()))
    for job in JOBS.values():
        if job.thread_id:
            upsert_job(job)
    for asset in list(ASSETS.values()) + list(SOURCE_ASSETS.values()):
        if asset.thread_id or asset.parent_asset_id or asset.root_asset_id:
            upsert_asset(asset)

_bootstrap()


def _parse_size(size: str) -> tuple[int | None, int | None]:
    try:
        width, height = size.lower().split("x", 1)
        return int(width), int(height)
    except ValueError:
        return None, None


def _build_anchor_hints(context_assets: list[Asset]) -> list[str]:
    hints = ["cta button", "headline text block"]
    if any(asset.asset_role == AssetRole.client_logo for asset in context_assets):
        hints.append("brand logo")
    if any(asset.asset_role == AssetRole.client_character for asset in context_assets):
        hints.append("main character face")
    if any(asset.asset_role == AssetRole.client_product for asset in context_assets):
        hints.append("main product packshot")
    return hints


def _select_multi_size_renderer_source_asset(
    request: GenerationRequest,
    context_assets: list[Asset],
) -> Asset | None:
    ordered_ids: list[str] = []
    if request.source_asset_id:
        ordered_ids.append(request.source_asset_id)
    ordered_ids.extend(request.source_asset_ids)
    ordered_ids.extend(request.reference_asset_ids)
    for asset_id in ordered_ids:
        asset = _get_asset(asset_id)
        if asset and asset.asset_role != AssetRole.client_logo:
            return asset

    priority_roles = [
        AssetRole.reference_ad,
        AssetRole.upload,
        AssetRole.client_background,
        AssetRole.client_product,
        AssetRole.client_character,
        AssetRole.generated,
    ]
    for role in priority_roles:
        for asset in context_assets:
            if asset.asset_role == role:
                return asset
    for asset in context_assets:
        if asset.asset_role != AssetRole.client_logo:
            return asset
    return None


def _apply_clarification_failure(
    job: GenerationJob,
    question: str,
    *,
    manifest: dict | None = None,
    reason: str | None = None,
) -> None:
    job.status = JobStatus.needs_clarification
    job.progress = 0
    job.message = f"Clarification needed: {question}"
    job.clarification_question = question
    job.clarification_reason = reason or (manifest or {}).get("clarification_reason")
    job.clarification_manifest = manifest
    job.clarification_options = clarification_options_for_manifest(
        manifest or {},
        reason=job.clarification_reason,
    )
    job.updated_at = datetime.utcnow()
    upsert_job(job)
    if job.thread_id:
        thread_store.add_assistant_message(
            job.thread_id,
            text=job.message,
            asset_ids=[],
            job_id=job.job_id,
        )
        thread_store.touch_thread(
            job.thread_id,
            latest_job_id=job.job_id,
            title="Clarification needed",
        )


def _mark_generation_progress(
    job: GenerationJob,
    progress: int,
    message: str | None = None,
) -> bool:
    """Update a running generation job and return False if it was cancelled."""
    if job.status != JobStatus.running:
        return False
    job.progress = max(0, min(99, progress))
    if message:
        job.message = message
    job.updated_at = datetime.utcnow()
    upsert_job(job)
    return True


def _load_asset_bytes(asset: Asset) -> bytes | None:
    path = _resolve_asset_path(asset)
    if not path or not path.exists():
        return None
    try:
        return path.read_bytes()
    except Exception:
        logger.warning("Could not read bytes for asset %s", asset.id)
        return None


def _effective_output_sizes(
    requested_sizes: list[str] | None,
    fallback_asset: Asset | None = None,
) -> list[str]:
    normalized: list[str] = []
    for size in requested_sizes or []:
        text = (size or "").strip()
        if text and text not in normalized:
            normalized.append(text)

    if normalized:
        return normalized
    if fallback_asset and fallback_asset.width and fallback_asset.height:
        return [f"{fallback_asset.width}x{fallback_asset.height}"]
    return ["1024x1024"]


async def _export_master_images_to_assets(
    *,
    job: GenerationJob,
    raw_outputs: list[bytes],
    workspace_id: str,
    created_by: str,
    provider: str,
    model: str,
    label: str,
    theme: str | None,
    requested_sizes: list[str] | None,
    source_asset: Asset | None,
    context_assets: list[Asset] | None = None,
    logo_overlay_bytes: bytes | None = None,
    api_key: str | None = None,
    created_at: datetime | None = None,
    manifest: dict | None = None,
    use_smart_resize: bool = False,
) -> list[Asset]:
    from app.incept.composite import adapt_image_to_size, composite_logo, resize_to_exact

    target_sizes = _effective_output_sizes(requested_sizes, source_asset)
    active_manifest = manifest or build_preservation_manifest(
        task_type="export",
        prompt=label,
        target_sizes=target_sizes,
        context_assets=context_assets or [],
        directive=None,
    )
    detected_anchors_by_variant: list[list[dict]] = []
    if use_smart_resize:
        ensure_manifest_clarity(active_manifest)
        anchor_hints = build_anchor_hints_from_manifest(active_manifest, context_assets or []) or _build_anchor_hints(context_assets or [])
        for raw in raw_outputs:
            try:
                detected = await detect_layout_anchors(raw, api_key, hints=anchor_hints)
            except Exception:
                detected = []
            detected_anchors_by_variant.append(detected)

    created_assets: list[Asset] = []
    now = created_at or datetime.utcnow()

    for size in target_sizes:
        width, height = _parse_size(size)
        for idx, raw in enumerate(raw_outputs):
            anchors = detected_anchors_by_variant[idx] if idx < len(detected_anchors_by_variant) else []
            output_bytes = raw
            analysis: dict | None = {
                "anchors": anchors,
                "adaptation": {"mode": "original" if use_smart_resize else "direct_output"},
                "guardrail_manifest": active_manifest if use_smart_resize else None,
            }

            if width and height:
                if not use_smart_resize:
                    try:
                        current_w, current_h = _read_image_size(raw)
                        if current_w == width and current_h == height:
                            output_bytes = raw
                            analysis = {
                                "adaptation": {"mode": "direct_output", "smart_resize": False},
                            }
                        else:
                            output_bytes = resize_to_exact(raw, width, height)
                            analysis = {
                                "adaptation": {"mode": "simple_resize", "smart_resize": False},
                            }
                    except Exception:
                        analysis = {
                            "adaptation": {"mode": "fallback_original", "smart_resize": False},
                        }
                else:
                    clarification = clarification_for_size(
                        active_manifest,
                        target_size=size,
                        source_anchors=anchors,
                    )
                    if clarification:
                        raise ClarificationRequired(
                            clarification,
                            reason="size_priority_conflict",
                            manifest=active_manifest,
                        )
                    try:
                        resized, adaptation_report = adapt_image_to_size(
                            raw,
                            width,
                            height,
                            anchors=anchors,
                        )
                        overlay_applied = False
                        if logo_overlay_bytes and not any(anchor.get("type") == "logo" for anchor in anchors):
                            resized = composite_logo(resized, logo_overlay_bytes)
                            overlay_applied = True
                        validation = await validate_output_asset(
                            output_bytes=resized,
                            target_size=size,
                            manifest=active_manifest,
                            source_anchors=anchors,
                            detect_fn=detect_layout_anchors,
                            api_key=api_key,
                            overlay_applied=overlay_applied,
                        )
                        if validation["status"] == "hard_fail":
                            resized, adaptation_report = adapt_image_to_size(
                                raw,
                                width,
                                height,
                                anchors=anchors,
                                force_safe_mode=True,
                            )
                            if logo_overlay_bytes and "logo" in set(active_manifest.get("must_preserve_types", [])):
                                resized = composite_logo(resized, logo_overlay_bytes)
                                overlay_applied = True
                            validation = await validate_output_asset(
                                output_bytes=resized,
                                target_size=size,
                                manifest=active_manifest,
                                source_anchors=anchors,
                                detect_fn=detect_layout_anchors,
                                api_key=api_key,
                                overlay_applied=overlay_applied,
                            )
                        if validation["status"] == "hard_fail":
                            raise ClarificationRequired(
                                f"I couldn't preserve all required elements for {size}. "
                                "Please confirm which elements should take priority.",
                                reason="completeness_validation_failed",
                                manifest=active_manifest,
                            )
                        output_bytes = resized
                        analysis = {
                            "anchors": anchors,
                            "adaptation": {
                                **adaptation_report,
                                "logo_overlay_applied": overlay_applied,
                            },
                            "guardrail_manifest": active_manifest,
                            "validation": validation,
                        }
                    except ClarificationRequired:
                        raise
                    except Exception:
                        analysis = {
                            "anchors": anchors,
                            "adaptation": {"mode": "fallback_original"},
                            "guardrail_manifest": active_manifest,
                            "validation": {
                                "status": "soft_fail",
                                "reasons": ["adaptation_exception_fallback_original"],
                            },
                        }
                        # fallback: use actual image dimensions rather than intended ones
                        fb_w, fb_h = _read_image_size(output_bytes)
                        if fb_w and fb_h:
                            width, height = fb_w, fb_h

            # If dimensions are still missing, read from the final output bytes
            if not width or not height:
                width, height = _read_image_size(output_bytes)

            asset_id = f"{job.lineage_key}_{size}_{idx + 1}_img"
            preview_url = _save_image_file(asset_id, base64.b64encode(output_bytes).decode())
            asset = Asset(
                id=asset_id,
                title=f"{label} {size} v{idx + 1}",
                type="image",
                gcs_uri=f"gs://incept-assets/generated/{workspace_id}/{job.job_id}/{asset_id}.png",
                preview_url=preview_url,
                provider=provider,
                model=model,
                workspace_id=workspace_id,
                job_id=job.job_id,
                prompt_hash="",
                created_by=created_by,
                created_at=now,
                width=width,
                height=height,
                theme=theme,
                asset_role=AssetRole.generated,
                analysis=analysis,
                thread_id=job.thread_id,
                parent_asset_id=source_asset.id if source_asset else None,
                root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
            )
            ASSETS[asset_id] = asset
            upsert_asset(asset)
            created_assets.append(asset)

    return created_assets


async def _export_renderer_outputs_to_assets(
    *,
    job: GenerationJob,
    rendered_outputs,
    workspace_id: str,
    created_by: str,
    provider: str,
    model: str,
    label: str,
    theme: str | None,
    source_asset: Asset | None,
    variants: int = 1,
    created_at: datetime | None = None,
) -> list[Asset]:
    now = created_at or datetime.utcnow()
    created_assets: list[Asset] = []
    total_variants = max(1, variants)
    for variant_idx in range(total_variants):
        for rendered in rendered_outputs:
            size = rendered.target_size
            width, height = _parse_size(size)
            if not width or not height:
                width, height = _read_image_size(rendered.image_bytes)
            asset_id = f"{job.lineage_key}_{size}_{variant_idx + 1}_img"
            preview_url = _save_image_file(asset_id, base64.b64encode(rendered.image_bytes).decode())
            analysis = {
                **(rendered.analysis or {}),
                "renderer_variant_index": variant_idx + 1,
                "renderer_variant_count": total_variants,
            }
            asset = Asset(
                id=asset_id,
                title=f"{label} {size} v{variant_idx + 1}",
                type="image",
                gcs_uri=f"gs://incept-assets/generated/{workspace_id}/{job.job_id}/{asset_id}.png",
                preview_url=preview_url,
                provider=provider,
                model=model,
                workspace_id=workspace_id,
                job_id=job.job_id,
                prompt_hash="",
                created_by=created_by,
                created_at=now,
                width=width,
                height=height,
                theme=theme,
                asset_role=AssetRole.generated,
                analysis=analysis,
                thread_id=job.thread_id,
                parent_asset_id=source_asset.id if source_asset else None,
                root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
            )
            ASSETS[asset_id] = asset
            upsert_asset(asset)
            created_assets.append(asset)
    return created_assets


async def split_saved_contact_sheet_asset(asset_id: str) -> list[Asset]:
    """Split a saved contact-sheet preview into extracted exact-size assets."""
    from app.incept.contact_sheet import split_contact_sheet

    preview_asset = ASSETS.get(asset_id)
    if not preview_asset:
        raise KeyError(f"Asset {asset_id} not found")

    role = (preview_asset.analysis or {}).get("contact_sheet_role")
    if role != "sheet":
        raise ValueError("Asset is not a splittable contact-sheet preview")

    source_url = (preview_asset.analysis or {}).get("contact_sheet_source_url")
    if isinstance(source_url, str) and source_url.startswith("/static/generated/"):
        source_path = STATIC_DIR / source_url[len("/static/generated/"):]
        source_bytes = source_path.read_bytes() if source_path.exists() else None
    else:
        source_bytes = _load_asset_bytes(preview_asset)
    if not source_bytes:
        raise RuntimeError("Could not load contact sheet source bytes")

    split_meta = (preview_asset.analysis or {}).get("contact_sheet_split") or {}
    requested_sizes = split_meta.get("requested_sizes") if isinstance(split_meta, dict) else None
    if not isinstance(requested_sizes, list) or not requested_sizes:
        raise RuntimeError("Missing requested sizes for contact sheet split")

    raw_layout = split_meta.get("panel_layout") if isinstance(split_meta, dict) else None
    panel_layout = None
    if isinstance(raw_layout, dict):
        panel_layout = {}
        for size, box in raw_layout.items():
            if isinstance(size, str) and isinstance(box, list) and len(box) == 4:
                panel_layout[size] = tuple(int(v) for v in box)

    split_panels, split_report = split_contact_sheet(
        source_bytes,
        requested_sizes,
        panel_layout=panel_layout,
    )
    if split_report.get("status") != "passed":
        raise RuntimeError(
            f"Contact sheet split failed: {split_report.get('reason', 'unknown_error')}"
        )

    job = JOBS.get(preview_asset.job_id or "")
    if not job:
        raise RuntimeError("Could not resolve original generation job for this contact sheet")

    extracted_assets: list[Asset] = []
    created_at = datetime.utcnow()
    for size in requested_sizes:
        panel = split_panels.get(size)
        if not panel:
            continue
        created = await _export_master_images_to_assets(
            job=job,
            raw_outputs=[panel.image_bytes],
            workspace_id=preview_asset.workspace_id,
            created_by=preview_asset.created_by,
            provider=preview_asset.provider,
            model=preview_asset.model,
            label=preview_asset.theme or "Generated",
            theme=preview_asset.theme,
            requested_sizes=[size],
            source_asset=preview_asset,
            context_assets=[],
            logo_overlay_bytes=None,
            api_key=None,
            created_at=created_at,
            manifest=None,
            use_smart_resize=False,
        )
        for asset in created:
            asset.analysis = {
                **(asset.analysis or {}),
                "contact_sheet_role": "extracted",
                "contact_sheet_split": split_report,
                "contact_sheet_preview_asset_id": preview_asset.id,
                "contact_sheet_source_url": source_url if isinstance(source_url, str) else None,
            }
            upsert_asset(asset)
        extracted_assets.extend(created)

    preview_asset.analysis = {
        **(preview_asset.analysis or {}),
        "contact_sheet_split_status": "split_completed",
        "contact_sheet_extracted_asset_ids": [asset.id for asset in extracted_assets],
    }
    upsert_asset(preview_asset)
    return extracted_assets


def _thread_title_from_prompt(prompt: str, fallback: str = "New thread") -> str:
    text = " ".join(prompt.strip().split())
    if not text:
        return fallback
    return text[:72]


def _resolve_thread_for_request(
    *,
    workspace_id: str,
    created_by: str,
    generation_mode: GenerationMode,
    thread_id: str | None,
    prompt: str,
    source_asset_id: str | None = None,
) -> CreativeThread:
    source_asset = _get_asset(source_asset_id) if source_asset_id else None
    preferred_thread_id = thread_id or source_asset.thread_id if source_asset else thread_id
    origin_asset_id = source_asset.id if source_asset else None
    return thread_store.ensure_thread(
        workspace_id=workspace_id,
        title=_thread_title_from_prompt(prompt),
        generation_mode=generation_mode,
        created_by=created_by,
        thread_id=preferred_thread_id,
        origin_asset_id=origin_asset_id,
    )


def _inherit_root_asset_id(source_asset: Asset | None, fallback_asset_id: str) -> str:
    if source_asset and source_asset.root_asset_id:
        return source_asset.root_asset_id
    if source_asset:
        return source_asset.id
    return fallback_asset_id


def list_workspaces() -> list[Workspace]:
    return sorted(WORKSPACES.values(), key=lambda item: item.updated_at, reverse=True)


def list_threads(workspace_id: str | None = None) -> list[CreativeThread]:
    assets = list(ASSETS.values()) + list(SOURCE_ASSETS.values())
    jobs = list(JOBS.values())
    threads = thread_store.hydrate_thread_summaries(assets=assets, jobs=jobs)
    if workspace_id:
        threads = [thread for thread in threads if thread.workspace_id == workspace_id]
    return threads


def list_jobs() -> list[GenerationJob]:
    return sorted(JOBS.values(), key=lambda item: item.created_at, reverse=True)


def get_job(job_id: str) -> GenerationJob | None:
    return JOBS.get(job_id)


def delete_asset(asset_id: str) -> bool:
    """Remove asset from memory, disk, and SQLite. Returns True if found."""
    asset = ASSETS.pop(asset_id, None)
    if not asset:
        # also check SOURCE_ASSETS (uploads)
        asset = SOURCE_ASSETS.pop(asset_id, None)
    if not asset:
        return False

    # Delete file from disk
    try:
        if asset.preview_url.startswith("/static/generated/"):
            path = STATIC_DIR / asset.preview_url[len("/static/generated/"):]
        elif asset.preview_url.startswith("/static/uploads/"):
            path = UPLOAD_DIR / asset.preview_url[len("/static/uploads/"):]
        else:
            path = None
        if path and path.exists():
            path.unlink()
    except Exception:
        logger.warning("Could not delete file for asset %s", asset_id)

    db_delete_asset(asset_id)
    return True


def list_assets(workspace_id: str | None = None) -> list[Asset]:
    values = list(ASSETS.values()) + list(SOURCE_ASSETS.values())
    if workspace_id:
        values = [asset for asset in values if asset.workspace_id == workspace_id]
    return sorted(values, key=lambda item: item.created_at, reverse=True)


def list_usage_events(workspace_id: str | None = None) -> list[UsageEvent]:
    values = USAGE_EVENTS.values()
    if workspace_id:
        values = [event for event in values if event.workspace_id == workspace_id]
    return sorted(values, key=lambda item: item.created_at, reverse=True)


def save_uploaded_asset(
    workspace_id: str,
    filename: str,
    content: bytes,
    asset_role: str,
    user_id: str,
) -> Asset:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    asset_id = f"asset_upload_{uuid4().hex[:12]}"
    ext = Path(filename).suffix or ".png"
    dest = UPLOAD_DIR / f"{asset_id}{ext}"
    dest.write_bytes(content)

    # Read actual pixel dimensions so they're available for all downstream ops
    img_w, img_h = _read_image_size(content)

    asset = Asset(
        id=asset_id,
        title=filename,
        type="image",
        gcs_uri=f"local://uploads/{asset_id}{ext}",
        preview_url=f"/static/uploads/{asset_id}{ext}",
        provider="upload",
        model="",
        workspace_id=workspace_id,
        job_id="",
        prompt_hash="",
        created_by=user_id,
        created_at=datetime.utcnow(),
        width=img_w,
        height=img_h,
        theme=None,
        asset_role=_coerce_asset_role(asset_role, provider="upload"),
    )
    SOURCE_ASSETS[asset_id] = asset
    upsert_asset(asset)
    return asset


def _read_image_size(image_bytes: bytes) -> tuple[int | None, int | None]:
    """Return (width, height) by reading the image with Pillow. Never raises."""
    try:
        from PIL import Image
        import io as _io
        with Image.open(_io.BytesIO(image_bytes)) as img:
            return img.width, img.height
    except Exception:
        return None, None


def _aspect_bucket(size: str) -> str:
    width, height = _parse_size(size)
    if not width or not height:
        return "unknown"
    ratio = width / height
    if ratio >= 4:
        return "banner"
    if ratio >= 1.4:
        return "landscape"
    if ratio <= 0.75:
        return "portrait"
    return "standard"


def _single_size_prompt_text(prompt: str, target_size: str, requested_sizes: list[str]) -> str:
    """Remove other target sizes from a per-size model call to avoid contact sheets."""
    import re

    text = prompt or ""
    for size in requested_sizes:
        if size != target_size:
            text = re.sub(rf"(?<!\d){re.escape(size)}(?!\d)", "", text, flags=re.IGNORECASE)

    # Remove generic multi-output language while keeping the user's creative brief.
    text = re.sub(
        r"\b(all|multiple|several|various)\s+(sizes|formats|aspect ratios|versions)\b",
        "this size",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bevery requested size\b", "this size", text, flags=re.IGNORECASE)
    text = re.sub(r"\brequested sizes\b", "this size", text, flags=re.IGNORECASE)
    text = re.sub(r"\bacross\s+this size\b", "for this size", text, flags=re.IGNORECASE)
    text = re.sub(r"\bacross\s+all\s+\w+\b", "for this size", text, flags=re.IGNORECASE)
    text = re.sub(r"\bad set\b", "single ad", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+,", ",", text)
    return text.strip(" ,;") or prompt


def _estimate_provider_generations(request: GenerationRequest) -> int:
    settings = get_settings()
    if (
        settings.contact_sheet_split_enabled
        and request.provider == "openai"
        and request.output_format == "image"
        and request.variants == 1
        and len(request.output_sizes) >= 2
        and (request.reference_asset_ids or request.source_asset_ids or request.client_asset_ids)
        and not request.preserve_layout
    ):
        return 1
    aspect_buckets = {_aspect_bucket(size) for size in request.output_sizes}
    return request.variants * max(1, len(aspect_buckets))


def _estimate_cost_usd(request: GenerationRequest, provider_generations: int) -> float:
    if request.provider == "openai":
        return round(provider_generations * 0.04, 4)
    if request.provider == "gemini":
        return round(provider_generations * 0.04, 4)
    return 0.0


_SUPPORTED_OPENAI_MODELS = frozenset(
    {
        "dall-e-2",
        "dall-e-3",
        "gpt-image-2",          # current default OpenAI model
        "chatgpt-image-latest",
        # Legacy — kept for backward compatibility with existing assets
        "gpt-image-1",
        "gpt-image-1-mini",
        "gpt-image-1.5",
        "gpt-image-2-2026-04-21",
    }
)


async def _generate_images_openai(
    prompt: str,
    model: str,
    variants: int,
    openai_size: str = "1024x1024",
    quality: str | None = None,
) -> list[str]:
    """Call OpenAI and return list of base64 PNG strings."""
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Fall back to the configured default if the model is not recognised
    if model not in _SUPPORTED_OPENAI_MODELS:
        model = settings.openai_image_model

    # gpt-image-1 family does NOT support response_format — it always returns
    # b64_json by default.  Only the legacy dall-e-* models need it specified.
    _LEGACY_DALLE = {"dall-e-2", "dall-e-3"}

    b64_images: list[str] = []

    if model == "dall-e-3":
        # dall-e-3 only supports n=1 per call — loop to produce multiple variants
        for _ in range(min(variants, 4)):
            response = await client.images.generate(
                model="dall-e-3",
                prompt=prompt[:4000],
                n=1,
                size="1024x1024",
                response_format="b64_json",
            )
            if response.data[0].b64_json:
                b64_images.append(response.data[0].b64_json)
    elif model == "dall-e-2":
        response = await client.images.generate(
            model="dall-e-2",
            prompt=prompt[:4000],
            n=min(variants, 4),
            size="1024x1024",
            response_format="b64_json",
        )
        b64_images = [d.b64_json for d in response.data if d.b64_json]
    else:
        # gpt-image-1, gpt-image-1-mini, gpt-image-2 — response_format unsupported;
        # pass the aspect-ratio-matched size for better composition.
        response = await client.images.generate(
            model=model,
            prompt=prompt[:4000],
            n=min(variants, 4),
            size=openai_size,
            **({"quality": quality} if quality else {}),
        )
        b64_images = [d.b64_json for d in response.data if d.b64_json]

    return b64_images


def _normalize_reference_image_for_openai(image_bytes: bytes) -> bytes:
    """Return a PNG version of a reference image for multipart image input."""
    import io as _io
    from PIL import Image

    with Image.open(_io.BytesIO(image_bytes)) as img:
        normalized = img.convert("RGBA")
        buf = _io.BytesIO()
        normalized.save(buf, format="PNG")
        return buf.getvalue()


async def _generate_images_openai_from_references(
    prompt: str,
    reference_images: list[bytes],
    model: str,
    variants: int,
    openai_size: str = "1024x1024",
    quality: str = "high",
) -> list[str]:
    """Generate a new image using one or more image references as conditioning."""
    import io as _io
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    edit_model = model if model in _SUPPORTED_OPENAI_MODELS else settings.openai_image_model
    if edit_model in {"dall-e-2", "dall-e-3"}:
        edit_model = settings.openai_image_model
    if edit_model not in _SUPPORTED_OPENAI_MODELS:
        edit_model = "gpt-image-2"

    image_inputs = []
    for idx, image_bytes in enumerate(reference_images[:8]):
        try:
            png_bytes = _normalize_reference_image_for_openai(image_bytes)
        except Exception:
            logger.warning("Skipping unreadable reference image %s", idx + 1)
            continue
        image_inputs.append((f"reference_{idx + 1}.png", _io.BytesIO(png_bytes), "image/png"))

    if not image_inputs:
        return await _generate_images_openai(prompt, model, variants, openai_size=openai_size)

    try:
        kwargs: dict = {
            "model": edit_model,
            "image": image_inputs,
            "prompt": prompt[:8000],
            "n": min(variants, 4),
            "size": openai_size,
            "quality": quality,
        }
        if edit_model in {"gpt-image-1", "gpt-image-1.5"}:
            kwargs["input_fidelity"] = "high"
        response = await client.images.edit(**kwargs)
    except Exception:
        logger.exception("Reference-conditioned generation failed")
        raise

    return [d.b64_json for d in response.data if d.b64_json]


async def _edit_image_openai(
    original_bytes: bytes,
    mask_bytes: bytes | None,
    prompt: str,
    model: str,
    variants: int,
) -> list[str]:
    """
    Call OpenAI images.edit (inpainting) and return list of base64 PNG strings.

    OpenAI mask convention:
      - Transparent pixels → the model FILLS those areas (edit zone)
      - Opaque pixels      → the model PRESERVES those areas
    """
    import io as _io
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Preserve modern GPT Image edit requests instead of silently downgrading
    # them to older models with weaker editing fidelity.
    edit_model = model if model in _SUPPORTED_OPENAI_MODELS else settings.openai_image_model
    if edit_model == "dall-e-3":
        edit_model = settings.openai_image_model
    if edit_model not in _SUPPORTED_OPENAI_MODELS:
        edit_model = "gpt-image-2"

    img_file = ("original.png", _io.BytesIO(original_bytes), "image/png")
    kwargs: dict = dict(
        model=edit_model,
        image=img_file,
        prompt=prompt[:4000],
        n=min(variants, 4),
        size="auto",
    )
    if mask_bytes:
        kwargs["mask"] = ("mask.png", _io.BytesIO(mask_bytes), "image/png")

    response = await client.images.edit(**kwargs)
    return [d.b64_json for d in response.data if d.b64_json]


def _is_gemini_image_model(model: str) -> bool:
    """Return True for Gemini models that use generate_content instead of generate_images."""
    return model.lower().startswith("gemini-")


async def _generate_images_gemini(
    prompt: str,
    model: str,
    variants: int,
) -> list[str]:
    """
    Call Gemini via generate_content() for text-to-image generation.

    Gemini image models cannot use the Imagen generate_images/edit_image endpoints.
    They must be called via generate_content with response_modalities=["IMAGE"].
    """
    import asyncio as _asyncio
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )

    def _sync() -> list[str]:
        results: list[str] = []
        for _ in range(min(variants, 4)):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt[:4000],
                    config=genai_types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                    ),
                )
                for candidate in (response.candidates or []):
                    for part in (candidate.content.parts if candidate.content else []):
                        inline = getattr(part, "inline_data", None)
                        if inline:
                            raw = inline.data
                            if isinstance(raw, bytes):
                                results.append(base64.b64encode(raw).decode())
                            elif isinstance(raw, str):
                                results.append(raw)  # already base64
            except Exception:
                logger.exception("Gemini image generation failed for one variant")
        return results

    loop = _asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _generate_images_gemini_from_references(
    prompt: str,
    reference_images: list[bytes],
    model: str,
    variants: int,
    target_size: str | None = None,
) -> list[str]:
    """
    Call Gemini via generate_content() for image editing with reference images.

    The model receives the prompt + reference images as inline_data parts and
    returns an edited image in the target aspect ratio.
    """
    import asyncio as _asyncio
    from google import genai
    from google.genai import types as genai_types

    if not reference_images:
        return await _generate_images_gemini(prompt, model, variants)

    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )

    def _sync() -> list[str]:
        results: list[str] = []

        # Build multimodal content: prompt text + reference image(s)
        parts: list[genai_types.Part] = [genai_types.Part(text=prompt[:4000])]
        for img_bytes in reference_images[:4]:
            try:
                png = _normalize_reference_image_for_openai(img_bytes)
                parts.append(genai_types.Part.from_bytes(data=png, mime_type="image/png"))
            except Exception:
                logger.warning("Skipping unreadable reference image for Gemini edit")

        if len(parts) < 2:
            logger.warning("No valid reference images; falling back to text-only Gemini generation")
            return []

        contents = [genai_types.Content(role="user", parts=parts)]

        for _ in range(min(variants, 4)):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=genai_types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                    ),
                )
                for candidate in (response.candidates or []):
                    for part in (candidate.content.parts if candidate.content else []):
                        inline = getattr(part, "inline_data", None)
                        if inline:
                            raw = inline.data
                            if isinstance(raw, bytes):
                                results.append(base64.b64encode(raw).decode())
                            elif isinstance(raw, str):
                                results.append(raw)
            except Exception:
                logger.exception("Gemini image edit failed for one variant")

        return results

    loop = _asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _generate_images_vertex(
    prompt: str,
    model: str,
    variants: int,
) -> list[str]:
    """Call Vertex AI Imagen via ADC and return list of base64 PNG strings.

    Requires:
    - VERTEX_AI_ENABLED=true
    - GCP_PROJECT_ID set
    - ADC configured: `gcloud auth application-default login`
    """
    import asyncio
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()

    # Normalize model name — "gemini-image" is our internal alias
    if model in ("gemini-image", "gemini", ""):
        model = settings.vertex_imagen_model

    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )

    def _sync_generate() -> list[str]:
        response = client.models.generate_images(
            model=model,
            prompt=prompt[:4000],
            config=genai_types.GenerateImagesConfig(
                number_of_images=min(variants, 4),
                output_mime_type="image/png",
            ),
        )
        results: list[str] = []
        for gen_image in response.generated_images:
            img = gen_image.image
            if img is None:
                continue
            # image_bytes is the raw PNG bytes in google-genai >= 1.x
            raw: bytes | None = getattr(img, "image_bytes", None)
            if raw is None:
                # Fallback: save through PIL if available
                try:
                    import io
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")  # type: ignore[arg-type]
                    raw = buf.getvalue()
                except Exception:
                    continue
            results.append(base64.b64encode(raw).decode())
        return results

    # google-genai generate_images is synchronous — run in thread executor
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_generate)


def _vertex_aspect_ratio_for_size(size: str | None) -> str | None:
    if not size:
        return None
    width, height = _parse_size(size)
    if not width or not height:
        return None
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


async def _generate_images_vertex_from_references(
    prompt: str,
    reference_images: list[bytes],
    model: str,
    variants: int,
    target_size: str | None = None,
) -> list[str]:
    """Call Vertex AI Imagen edit with uploaded references and return base64 PNG strings."""
    import asyncio
    import tempfile
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()

    requested_model = model
    if requested_model in ("gemini-image", "gemini", ""):
        requested_model = settings.vertex_imagen_model
    if "generate" in requested_model or requested_model == settings.vertex_imagen_model:
        model = settings.vertex_imagen_edit_model
    else:
        model = requested_model

    normalized_references: list[genai_types.RawReferenceImage] = []
    temp_paths: list[str] = []
    for idx, image_bytes in enumerate(reference_images[:8]):
        try:
            png_bytes = _normalize_reference_image_for_openai(image_bytes)
        except Exception:
            logger.warning("Skipping unreadable Vertex reference image %s", idx + 1)
            continue
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        temp_file.write(png_bytes)
        temp_file.flush()
        temp_file.close()
        temp_paths.append(temp_file.name)
        normalized_references.append(
            genai_types.RawReferenceImage(
                reference_id=idx + 1,
                reference_image=genai_types.Image.from_file(location=temp_file.name),
            )
        )

    if not normalized_references:
        return await _generate_images_vertex(prompt, model, variants)

    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )
    aspect_ratio = _vertex_aspect_ratio_for_size(target_size)

    def _sync_edit() -> list[str]:
        try:
            config_kwargs: dict[str, object] = {
                "number_of_images": min(variants, 4),
                "output_mime_type": "image/png",
            }
            if aspect_ratio:
                config_kwargs["aspect_ratio"] = aspect_ratio
            response = client.models.edit_image(
                model=model,
                prompt=prompt[:4000],
                reference_images=normalized_references,
                config=genai_types.EditImageConfig(**config_kwargs),
            )
            results: list[str] = []
            for gen_image in response.generated_images:
                img = gen_image.image
                if img is None:
                    continue
                raw: bytes | None = getattr(img, "image_bytes", None)
                if raw is None:
                    try:
                        import io

                        buf = io.BytesIO()
                        img.save(buf, format="PNG")  # type: ignore[arg-type]
                        raw = buf.getvalue()
                    except Exception:
                        continue
                results.append(base64.b64encode(raw).decode())
            return results
        finally:
            for temp_path in temp_paths:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_edit)


def _save_image_file(asset_id: str, b64_data: str) -> str:
    """Save base64 PNG to disk and return preview URL path."""
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    image_bytes = base64.b64decode(b64_data)
    dest = STATIC_DIR / f"{asset_id}.png"
    dest.write_bytes(image_bytes)
    return f"/static/generated/{asset_id}.png"


def create_image_generation_job(request: GenerationRequest, user: User) -> GenerationJob:
    """Create job record synchronously and return immediately.

    Returns status=running when a real provider is available (background task will
    do the actual generation). Returns status=completed with mock assets otherwise.
    """
    settings = get_settings()
    job_id = f"job_{uuid4().hex[:12]}"
    lineage_key = f"llg_ast_{uuid4().hex[:16]}"
    now = datetime.utcnow()

    is_openai_real = bool(settings.openai_api_key and request.provider == "openai")
    is_vertex_real = bool(
        settings.vertex_ai_enabled
        and settings.gcp_project_id
        and request.provider == "gemini"
    )
    is_real = is_openai_real or is_vertex_real
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=request.generation_mode,
        thread_id=request.thread_id,
        prompt=request.theme or request.prompt,
        source_asset_id=request.source_asset_id,
    )

    if is_openai_real:
        model = request.model if request.model not in ("gemini-image", "gemini", "") else settings.openai_image_model
        if model not in _SUPPORTED_OPENAI_MODELS:
            model = settings.openai_image_model
        tool_id = "openai-gpt-image-1"
        message = f"Generating images with OpenAI {model}…"
    elif is_vertex_real:
        model = request.model or settings.vertex_imagen_model
        tool_id = "vertex-imagen-3"
        message = f"Generating images with Vertex AI Imagen ({model})…"
    else:
        model = request.model or settings.openai_image_model
        tool_id = "openai-gpt-image-1" if request.provider == "openai" else "vertex-imagen-3"
        message = _build_mock_message(request)

    job = GenerationJob(
        job_id=job_id,
        workspace_id=request.workspace_id,
        status=JobStatus.running if is_real else JobStatus.completed,
        progress=0 if is_real else 100,
        lineage_key=lineage_key,
        message=message,
        tool_id=tool_id,
        title=f"Image generation — {request.provider}",
        output_asset_ids=[],
        thread_id=thread.thread_id,
        source_asset_id=request.source_asset_id,
        created_at=now,
        updated_at=now,
    )
    JOBS[job_id] = job

    if not is_real:
        _fill_mock_assets(job, request, user, lineage_key, model, now)

    return job


def _build_mock_message(request: GenerationRequest) -> str:
    total = len(request.output_sizes) * request.variants
    if request.provider == "gemini":
        hint = "Set VERTEX_AI_ENABLED=true + GCP_PROJECT_ID and run `gcloud auth application-default login`."
    else:
        hint = "Set OPENAI_API_KEY to generate real images."
    return f"Mock: {total} outputs — {request.variants} variants × {len(request.output_sizes)} sizes. {hint}"


def _fill_mock_assets(
    job: GenerationJob,
    request: GenerationRequest,
    user: User,
    lineage_key: str,
    model: str,
    now: datetime,
) -> None:
    prompt_hash = sha256(request.prompt.encode()).hexdigest()[:16]
    output_types = ["image", "gif"] if request.output_format == "image_and_gif" else [request.output_format]
    asset_ids: list[str] = []
    source_asset = _get_asset(request.source_asset_id) if request.source_asset_id else None

    for size in request.output_sizes:
        width, height = _parse_size(size)
        for idx in range(request.variants):
            for output_type in output_types:
                suffix = "gif" if output_type == "gif" else "img"
                asset_id = f"{lineage_key}_{size}_{idx + 1}_{suffix}"
                asset = Asset(
                    id=asset_id,
                    title=f"{request.theme} {size} v{idx + 1}",
                    type=output_type,
                    gcs_uri=f"gs://incept-assets/generated/{request.workspace_id}/{job.job_id}/{asset_id}.png",
                    preview_url="/static/placeholder.png",
                    provider=request.provider,
                    model=model,
                    workspace_id=request.workspace_id,
                    job_id=job.job_id,
                    prompt_hash=prompt_hash,
                    created_by=user.id,
                    created_at=now,
                    width=width,
                    height=height,
                    theme=request.theme,
                    thread_id=job.thread_id,
                    parent_asset_id=source_asset.id if source_asset else None,
                    root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
                )
                ASSETS[asset_id] = asset
                asset_ids.append(asset_id)

    job.output_asset_ids = asset_ids
    _record_usage(job, request, user, model, prompt_hash, now)


def _record_usage(
    job: GenerationJob,
    request: GenerationRequest,
    user: User,
    model: str,
    prompt_hash: str,
    now: datetime,
) -> None:
    provider_generations = _estimate_provider_generations(request)
    usage_id = f"use_{uuid4().hex[:12]}"
    usage_event = UsageEvent(
        id=usage_id,
        job_id=job.job_id,
        workspace_id=request.workspace_id,
        user_id=user.id,
        user_email=user.email,
        provider=request.provider,
        model=model,
        operation="image_generation",
        prompt_hash=prompt_hash,
        variants=request.variants,
        output_size_count=len(request.output_sizes),
        output_format=request.output_format,
        estimated_provider_generations=provider_generations,
        output_asset_count=len(job.output_asset_ids),
        estimated_cost_usd=_estimate_cost_usd(request, provider_generations),
        created_at=now,
    )
    USAGE_EVENTS[usage_id] = usage_event

    workspace = WORKSPACES.get(request.workspace_id)
    if workspace:
        workspace.status = JobStatus.completed
        workspace.updated_at = now

    # Persist job + assets to SQLite so history survives restarts
    upsert_job(job)
    for aid in job.output_asset_ids:
        if aid in ASSETS:
            upsert_asset(ASSETS[aid])

    if job.thread_id:
        latest_asset_id = job.output_asset_ids[-1] if job.output_asset_ids else None
        cover_asset_id = job.output_asset_ids[0] if job.output_asset_ids else None
        thread_store.touch_thread(
            job.thread_id,
            latest_job_id=job.job_id,
            latest_asset_id=latest_asset_id,
            cover_asset_id=cover_asset_id,
            title=request.theme or None,
        )

    persist_generation(job, [ASSETS[aid] for aid in job.output_asset_ids if aid in ASSETS], usage_event)


async def _dispatch_generation(
    prompt: str,
    *,
    provider: str,
    model: str,
    variants: int,
    reference_images: list[bytes],
    openai_size: str = "1024x1024",
    target_size: str | None = None,
) -> list[str]:
    """
    Unified dispatch for image generation.

    Routes to the correct API based on provider + model:
      - provider="gemini" + Gemini model  → generate_content (Gemini native API)
      - provider="gemini" + Imagen model  → generate_images / edit_image (Vertex Imagen API)
      - provider="openai"                 → OpenAI images API
    """
    if provider == "gemini":
        if _is_gemini_image_model(model):
            # Gemini image models use generate_content, NOT generate_images/edit_image
            if reference_images:
                return await _generate_images_gemini_from_references(
                    prompt,
                    reference_images=reference_images,
                    model=model,
                    variants=variants,
                    target_size=target_size,
                )
            return await _generate_images_gemini(prompt, model, variants)
        else:
            # Imagen models use the Vertex Predict endpoint
            if reference_images:
                return await _generate_images_vertex_from_references(
                    prompt,
                    reference_images=reference_images,
                    model=model,
                    variants=variants,
                    target_size=target_size,
                )
            return await _generate_images_vertex(prompt, model, variants)
    else:
        # OpenAI
        if reference_images:
            return await _generate_images_openai_from_references(
                prompt,
                reference_images=reference_images,
                model=model,
                variants=variants,
                openai_size=openai_size,
            )
        return await _generate_images_openai(prompt, model, variants, openai_size=openai_size)


async def run_generation_background(job_id: str, request: GenerationRequest, user: User) -> None:
    """Background task — dispatches to OpenAI or Vertex AI and updates job state."""
    job = JOBS.get(job_id)
    if not job:
        return

    settings = get_settings()
    lineage_key = job.lineage_key
    now = datetime.utcnow()
    prompt_hash = sha256(request.prompt.encode()).hexdigest()[:16]

    # Resolve the effective model for each provider
    if request.provider == "gemini":
        model = request.model or settings.vertex_imagen_model
        provider_label = f"Vertex AI Imagen ({model})"
    else:
        model = request.model if request.model not in ("gemini-image", "gemini", "") else settings.openai_image_model
        if model not in _SUPPORTED_OPENAI_MODELS:
            model = settings.openai_image_model
        provider_label = f"OpenAI {model}"

    try:
        if not _mark_generation_progress(job, 10, f"Preparing {provider_label} generation..."):
            return

        # ── Orchestrator: GPT-4o understands intent + enhances prompt ──────────
        session_history = thread_store.get_context_messages(job.thread_id or "", n=6)
        context_asset_ids = list(dict.fromkeys(
            request.reference_asset_ids + request.source_asset_ids + request.client_asset_ids
        ))
        context_assets = [asset for aid in context_asset_ids if (asset := _get_asset(aid))]
        reference_assets = [
            asset for asset in context_assets
            if asset.asset_role != AssetRole.client_logo
        ]
        logo_assets = [
            asset for asset in context_assets
            if asset.asset_role == AssetRole.client_logo
        ]

        preserve_elements: list[str] = []
        if any(asset.asset_role == AssetRole.client_logo for asset in context_assets):
            preserve_elements.append("brand logo")
        if any(asset.asset_role == AssetRole.client_character for asset in context_assets):
            preserve_elements.append("main character identity")
        if any(asset.asset_role == AssetRole.client_product for asset in context_assets):
            preserve_elements.append("product packshot")
        if request.generation_mode == GenerationMode.style_match:
            preserve_elements.append("reference layout hierarchy")
        elif request.generation_mode == GenerationMode.theme_create:
            preserve_elements.append("theme readability")

        primary_size = request.output_sizes[0] if request.output_sizes else "1200x628"
        requested_sizes = request.output_sizes or [primary_size]
        primary_w, primary_h = _parse_size(primary_size)
        generation_session_history = session_history if request.preserve_layout else []
        orchestrator_target_sizes = requested_sizes if request.preserve_layout else []

        directive = await orchestrate(
            user_prompt=request.prompt,
            reference_assets=reference_assets,
            session_history=generation_session_history,
            target_sizes=orchestrator_target_sizes,
            static_dir=STATIC_DIR,
            upload_dir=UPLOAD_DIR,
            api_key=settings.openai_api_key,
            logo_assets=logo_assets or None,
        )
        manifest = build_preservation_manifest(
            task_type=request.generation_mode.value,
            prompt=request.prompt,
            target_sizes=requested_sizes,
            context_assets=context_assets,
            directive=directive,
            clarification_note=request.clarification_note,
        )
        ensure_manifest_clarity(manifest)
        if not _mark_generation_progress(job, 15, "Planning resize-safe prompts..."):
            return

        from app.incept.composite import get_openai_size
        reference_image_bytes = [
            data
            for asset in context_assets[:8]
            if (data := _load_asset_bytes(asset))
        ]
        renderer_source_asset = _select_multi_size_renderer_source_asset(request, context_assets)
        renderer_source_bytes = _load_asset_bytes(renderer_source_asset) if renderer_source_asset else None
        renderer_source_candidates = [
            asset for asset in context_assets if asset.asset_role != AssetRole.client_logo
        ]
        # Use the orchestrator's enhanced_prompt when reference images are present
        # (gives the model proper context about what style/content to produce).
        # For pure free-create with no reference, the raw prompt is sufficient.
        generation_prompt_base = (
            directive.get("enhanced_prompt", request.prompt)
            if (request.preserve_layout or bool(reference_image_bytes))
            else request.prompt
        )
        generation_preserve_elements = (
            (directive.get("preserve_elements") or [])
            + preserve_elements
            + prompt_preserve_elements(manifest)
        ) or None

        generated_raw_by_size: dict[str, list[bytes]] = {}
        contact_sheet_reports: list[dict] = []
        contact_sheet_source_raws: list[bytes] = []
        contact_sheet_preview_bytes_list: list[bytes] = []
        contact_sheet_preview_size: str | None = None
        renderer_rendered_outputs = []
        renderer_manifest_snapshot: dict | None = None

        if request.preserve_layout:
            if not _mark_generation_progress(job, 25, f"Generating master image for {primary_size}..."):
                return
            openai_size = get_openai_size(primary_w or 1024, primary_h or 1024, model)
            prompt_builder = (
                build_reference_generation_prompt if reference_image_bytes else build_generation_prompt
            )
            enriched_prompt = prompt_builder(
                user_request=generation_prompt_base,
                target_size=primary_size,
                style_hint=directive.get("style_description") or request.theme or None,
                preserve_elements=generation_preserve_elements,
            )
            b64_images = await _dispatch_generation(
                enriched_prompt,
                provider=request.provider,
                model=model,
                variants=request.variants,
                reference_images=reference_image_bytes,
                openai_size=openai_size,
                target_size=primary_size,
            )
            generated_raw_by_size[primary_size] = [
                base64.b64decode(b64) for b64 in b64_images if b64
            ]
            if not _mark_generation_progress(job, 65, f"Master image generated for {primary_size}."):
                return
        else:
            use_multi_size_renderer = (
                settings.multi_size_renderer_enabled
                and len(requested_sizes) >= 2
                and request.output_format == "image"
                and request.generation_mode == GenerationMode.free_create
                and len(renderer_source_candidates) == 1
                and renderer_source_asset is not None
                and renderer_source_bytes is not None
            )
            use_contact_sheet_split = (
                settings.contact_sheet_split_enabled
                and request.provider == "openai"
                and len(requested_sizes) >= 2
                and request.output_format == "image"
            )
            if use_multi_size_renderer:
                from app.incept.analysis_pipeline import analyze_source_creative
                from app.incept.multi_size_renderer import render_multi_size_variants

                if not _mark_generation_progress(job, 25, "Analyzing source creative for multi-size renderer..."):
                    return
                layout_manifest, renderer_analysis_report = await analyze_source_creative(
                    source_bytes=renderer_source_bytes,
                    source_asset=renderer_source_asset,
                    context_assets=context_assets,
                    api_key=settings.openai_api_key,
                    task_manifest=manifest,
                )
                renderer_manifest_snapshot = layout_manifest.to_dict()
                renderer_source_asset.analysis = {
                    **(renderer_source_asset.analysis or {}),
                    "layout_manifest": renderer_manifest_snapshot,
                    "renderer_analysis": renderer_analysis_report,
                }
                upsert_asset(renderer_source_asset)

                if not settings.multi_size_renderer_validate_only:
                    if not _mark_generation_progress(job, 38, "Rendering exact outputs with multi-size renderer..."):
                        return
                    renderer_rendered_outputs = await render_multi_size_variants(
                        source_bytes=renderer_source_bytes,
                        target_sizes=requested_sizes,
                        layout_manifest=layout_manifest,
                        guardrail_manifest=manifest,
                        logo_overlay_bytes=_load_asset_bytes(logo_assets[0]) if logo_assets else None,
                        detect_fn=detect_layout_anchors,
                        api_key=settings.openai_api_key,
                    )
                    if not renderer_rendered_outputs:
                        raise RuntimeError("Multi-size renderer produced no outputs")
                    if not _mark_generation_progress(
                        job,
                        68,
                        f"Rendered {len(renderer_rendered_outputs)} exact-size outputs with multi-size renderer.",
                    ):
                        return
            elif use_contact_sheet_split:
                from app.incept.contact_sheet import (
                    CONTACT_SHEET_QUALITY,
                    CONTACT_SHEET_SIZE,
                    build_contact_sheet_plans,
                    split_contact_sheet,
                )
                sheet_plans = build_contact_sheet_plans(requested_sizes)
                total_plan_count = max(1, len(sheet_plans))
                if not _mark_generation_progress(
                    job,
                    25,
                    f"Generating {total_plan_count} structured contact sheet plan(s)...",
                ):
                    return
                preview_sheets: list[bytes] = []
                reports: list[dict] = []
                all_sheet_raws: list[bytes] = []
                for plan_index, sheet_plan in enumerate(sheet_plans):
                    if not _mark_generation_progress(
                        job,
                        28 + int((plan_index / total_plan_count) * 20),
                        f"Generating {sheet_plan.title} ({plan_index + 1}/{total_plan_count})...",
                    ):
                        return
                    sheet_prompt = build_contact_sheet_generation_prompt(
                        user_request=generation_prompt_base,
                        target_sizes=sheet_plan.target_sizes,
                        style_hint=directive.get("style_description") or request.theme or None,
                        preserve_elements=generation_preserve_elements,
                        panel_layout=sheet_plan.panel_layout,
                        has_reference=bool(reference_image_bytes),
                        sheet_title=sheet_plan.title,
                    )
                    if reference_image_bytes:
                        sheet_b64_images = await _generate_images_openai_from_references(
                            sheet_prompt,
                            reference_images=reference_image_bytes,
                            model=model,
                            variants=request.variants,
                            openai_size=CONTACT_SHEET_SIZE,
                            quality=CONTACT_SHEET_QUALITY,
                        )
                    else:
                        sheet_b64_images = await _generate_images_openai(
                            sheet_prompt,
                            model,
                            request.variants,
                            openai_size=CONTACT_SHEET_SIZE,
                            quality=CONTACT_SHEET_QUALITY,
                        )
                    sheet_raws = [base64.b64decode(b64) for b64 in sheet_b64_images if b64]
                    if not sheet_raws:
                        raise RuntimeError(f"{sheet_plan.title} generation returned no image data")
                    total_sheets = max(1, len(sheet_raws))
                    for sheet_index, sheet_raw in enumerate(sheet_raws):
                        detect_progress = 46 + int(
                            ((plan_index + ((sheet_index + 1) / total_sheets)) / total_plan_count) * 18
                        )
                        if not _mark_generation_progress(
                            job,
                            detect_progress,
                            f"Inspecting {sheet_plan.title} {sheet_index + 1}/{total_sheets} layout...",
                        ):
                            return
                        _, split_report = split_contact_sheet(
                            sheet_raw,
                            sheet_plan.target_sizes,
                            panel_layout=sheet_plan.panel_layout,
                        )
                        if split_report.get("status") != "passed":
                            logger.warning("Contact sheet split preview warning: %s", split_report)
                        preview_report = {
                            **split_report,
                            "requested_sizes": sheet_plan.target_sizes,
                            "quality": CONTACT_SHEET_QUALITY,
                            "sheet_title": sheet_plan.title,
                            "panel_layout": {
                                size: list(box) for size, box in sheet_plan.panel_layout.items()
                            },
                        }
                        preview_sheets.append(sheet_raw)
                        reports.append(preview_report)
                        all_sheet_raws.append(sheet_raw)
                contact_sheet_source_raws = all_sheet_raws
                contact_sheet_preview_bytes_list = preview_sheets
                contact_sheet_reports = reports
                contact_sheet_preview_size = CONTACT_SHEET_SIZE
                generated_raw_by_size[CONTACT_SHEET_SIZE] = preview_sheets
                if not _mark_generation_progress(
                    job,
                    68,
                    f"Generated {len(preview_sheets)} contact sheet preview(s).",
                ):
                    return

            if not generated_raw_by_size and not renderer_rendered_outputs:
                total_sizes = max(1, len(requested_sizes))
                for size_index, size in enumerate(requested_sizes):
                    start_progress = 20 + int((size_index / total_sizes) * 45)
                    if not _mark_generation_progress(
                        job,
                        start_progress,
                        f"Generating {size_index + 1}/{total_sizes}: {size}...",
                    ):
                        return
                    target_w, target_h = _parse_size(size)
                    openai_size = get_openai_size(target_w or 1024, target_h or 1024, model)
                    # ── Resize mode: use dedicated per-size resize prompt ────────
                    if request.generation_mode == GenerationMode.resize:
                        from app.incept.prompt_builder import build_resize_prompt
                        _user_note = request.prompt if request.prompt.strip() else ""
                        enriched_prompt = build_resize_prompt(
                            target_size=size,
                            user_note=_user_note,
                            is_endcard=(size in {"360x640", "480x480", "640x360"}),
                            preserve_elements=generation_preserve_elements or None,
                        )
                    else:
                        size_prompt_base = _single_size_prompt_text(
                            generation_prompt_base,
                            target_size=size,
                            requested_sizes=requested_sizes,
                        )
                        prompt_builder = (
                            build_reference_generation_prompt if reference_image_bytes else build_generation_prompt
                        )
                        enriched_prompt = prompt_builder(
                            user_request=size_prompt_base,
                            target_size=size,
                            style_hint=directive.get("style_description") or request.theme or None,
                            preserve_elements=generation_preserve_elements,
                        )
                    b64_images = await _dispatch_generation(
                        enriched_prompt,
                        provider=request.provider,
                        model=model,
                        variants=request.variants,
                        reference_images=reference_image_bytes,
                        openai_size=openai_size,
                        target_size=size,
                    )
                    generated_raw_by_size[size] = [
                        base64.b64decode(b64) for b64 in b64_images if b64
                    ]
                    done_progress = 20 + int(((size_index + 1) / total_sizes) * 45)
                    if not _mark_generation_progress(
                        job,
                        done_progress,
                        f"Generated {size_index + 1}/{total_sizes}: {size}.",
                    ):
                        return

        if not _mark_generation_progress(job, 70, "Preparing exact-size assets..."):
            return

        output_types = (
            ["image", "gif"] if request.output_format == "image_and_gif" else [request.output_format]
        )
        asset_ids: list[str] = []
        created_assets: list[Asset] = []

        logo_overlay_bytes = None
        if logo_assets:
            logo_overlay_bytes = _load_asset_bytes(logo_assets[0])
        source_asset = _get_asset(job.source_asset_id) if job.source_asset_id else None
        if not source_asset and renderer_source_asset:
            source_asset = renderer_source_asset
        if "image" in output_types:
            if renderer_rendered_outputs:
                if not _mark_generation_progress(job, 76, "Saving multi-size renderer outputs..."):
                    return
                created_assets.extend(
                    await _export_renderer_outputs_to_assets(
                        job=job,
                        rendered_outputs=renderer_rendered_outputs,
                        workspace_id=request.workspace_id,
                        created_by=user.id,
                        provider=request.provider,
                        model=model,
                        label=request.theme or "Generated",
                        theme=request.theme,
                        source_asset=source_asset,
                        variants=request.variants,
                        created_at=now,
                    )
                )
                for asset in created_assets:
                    asset.analysis = {
                        **(asset.analysis or {}),
                        "renderer_branch": True,
                        "renderer_source_asset_id": renderer_source_asset.id if renderer_source_asset else None,
                        "layout_manifest": renderer_manifest_snapshot,
                    }
            elif request.preserve_layout:
                if not _mark_generation_progress(job, 76, "Exporting smart resize variants..."):
                    return
                created_assets.extend(
                    await _export_master_images_to_assets(
                        job=job,
                        raw_outputs=generated_raw_by_size.get(primary_size, []),
                        workspace_id=request.workspace_id,
                        created_by=user.id,
                        provider=request.provider,
                        model=model,
                        label=request.theme or "Generated",
                        theme=request.theme,
                        requested_sizes=requested_sizes,
                        source_asset=source_asset,
                        context_assets=context_assets,
                        logo_overlay_bytes=logo_overlay_bytes,
                        api_key=settings.openai_api_key,
                        created_at=now,
                        manifest=manifest,
                        use_smart_resize=True,
                    )
                )
            elif contact_sheet_preview_bytes_list and contact_sheet_preview_size:
                if not _mark_generation_progress(job, 76, "Saving contact sheet previews..."):
                    return
                source_urls: list[str] = []
                for idx, raw in enumerate(contact_sheet_source_raws):
                    source_asset_id = f"{job.lineage_key}_{contact_sheet_preview_size}_{idx + 1}_sheet_src"
                    source_urls.append(_save_image_file(source_asset_id, base64.b64encode(raw).decode()))
                preview_assets = await _export_master_images_to_assets(
                    job=job,
                    raw_outputs=contact_sheet_preview_bytes_list,
                    workspace_id=request.workspace_id,
                    created_by=user.id,
                    provider=request.provider,
                    model=model,
                    label=(request.theme or "Generated") + " Contact Sheet",
                    theme=request.theme,
                    requested_sizes=[contact_sheet_preview_size],
                    source_asset=source_asset,
                    context_assets=context_assets,
                    logo_overlay_bytes=None,
                    api_key=None,
                    created_at=now,
                    manifest=manifest,
                    use_smart_resize=False,
                )
                for idx, asset in enumerate(preview_assets):
                    report = contact_sheet_reports[idx] if idx < len(contact_sheet_reports) else {}
                    source_url = source_urls[idx] if idx < len(source_urls) else None
                    asset.analysis = {
                        **(asset.analysis or {}),
                        "contact_sheet_role": "sheet",
                        "contact_sheet_title": report.get("sheet_title"),
                        "contact_sheet_split": report,
                        "contact_sheet_source_url": source_url,
                    }
                created_assets.extend(preview_assets)
            else:
                total_sizes = max(1, len(requested_sizes))
                for size_index, size in enumerate(requested_sizes):
                    export_progress = 74 + int((size_index / total_sizes) * 18)
                    if not _mark_generation_progress(
                        job,
                        export_progress,
                        f"Rendering output {size_index + 1}/{total_sizes}: {size}...",
                    ):
                        return
                    created_assets.extend(
                        await _export_master_images_to_assets(
                            job=job,
                            raw_outputs=generated_raw_by_size.get(size, []),
                            workspace_id=request.workspace_id,
                            created_by=user.id,
                            provider=request.provider,
                            model=model,
                            label=request.theme or "Generated",
                            theme=request.theme,
                            requested_sizes=[size],
                            source_asset=source_asset,
                            context_assets=context_assets,
                            logo_overlay_bytes=logo_overlay_bytes,
                            api_key=settings.openai_api_key,
                            created_at=now,
                            manifest=manifest,
                            use_smart_resize=False,
                        )
                    )
                    done_progress = 74 + int(((size_index + 1) / total_sizes) * 18)
                    if not _mark_generation_progress(
                        job,
                        done_progress,
                        f"Rendered output {size_index + 1}/{total_sizes}: {size}.",
                    ):
                        return
            for asset in created_assets:
                asset.prompt_hash = prompt_hash
                asset.analysis = {
                    **(asset.analysis or {}),
                    "source_prompt": request.prompt,
                }
                upsert_asset(asset)
                asset_ids.append(asset.id)
            output_types = [output_type for output_type in output_types if output_type != "image"]

        if not _mark_generation_progress(job, 94, "Finalizing generated assets..."):
            return

        for size in requested_sizes:
            width, height = _parse_size(size)
            for idx in range(request.variants):
                for output_type in output_types:
                    suffix = "gif" if output_type == "gif" else "img"
                    asset_id = f"{lineage_key}_{size}_{idx + 1}_{suffix}"

                    if output_type == "image" and idx < len(generated_raw):
                        # Resize to exact target dimensions
                        anchors = detected_anchors_by_variant[idx] if idx < len(detected_anchors_by_variant) else []
                        analysis: dict | None = None
                        if width and height:
                            try:
                                resized, adaptation_report = adapt_image_to_size(
                                    generated_raw[idx],
                                    width,
                                    height,
                                    anchors=anchors,
                                )
                                overlay_applied = False
                                if logo_overlay_bytes and not any(
                                    anchor.get("type") == "logo" for anchor in anchors
                                ):
                                    resized = composite_logo(resized, logo_overlay_bytes)
                                    overlay_applied = True
                                analysis = {
                                    "anchors": anchors,
                                    "adaptation": {
                                        **adaptation_report,
                                        "logo_overlay_applied": overlay_applied,
                                    },
                                }
                                resized_b64 = base64.b64encode(resized).decode()
                            except Exception:
                                # adapt_image_to_size failed — use simple center-crop resize
                                # as a guaranteed fallback so we always hit the exact size
                                logger.warning(
                                    "adapt_image_to_size failed for %s %s, using simple resize",
                                    asset_id, size, exc_info=True,
                                )
                                try:
                                    from app.incept.composite import resize_to_exact
                                    simple_resized = resize_to_exact(generated_raw[idx], width, height)
                                    resized_b64 = base64.b64encode(simple_resized).decode()
                                except Exception:
                                    resized_b64 = b64_images[idx]  # last resort: original
                                analysis = {"anchors": anchors, "adaptation": {"mode": "fallback_simple_resize"}}
                        else:
                            resized_b64 = b64_images[idx]
                            analysis = {"anchors": anchors, "adaptation": {"mode": "original"}}
                        preview_url = _save_image_file(asset_id, resized_b64)
                    else:
                        preview_url = "/static/placeholder.png"
                        analysis = None

                    asset = Asset(
                        id=asset_id,
                        title=f"{request.theme} {size} v{idx + 1}",
                        type=output_type,
                        gcs_uri=f"gs://incept-assets/generated/{request.workspace_id}/{job_id}/{asset_id}.png",
                        preview_url=preview_url,
                        provider=request.provider,
                        model=model,
                        workspace_id=request.workspace_id,
                        job_id=job_id,
                        prompt_hash=prompt_hash,
                        created_by=user.id,
                        created_at=now,
                        width=width,
                        height=height,
                        theme=request.theme,
                        asset_role=AssetRole.generated,
                        analysis={
                            **(analysis or {}),
                            "source_prompt": request.prompt,
                        },
                        thread_id=job.thread_id,
                        parent_asset_id=source_asset.id if source_asset else None,
                        root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
                    )
                    ASSETS[asset_id] = asset
                    created_assets.append(asset)
                    asset_ids.append(asset_id)

        if job.status != JobStatus.running:
            return

        # ── GIF generation (resize mode with include_gif=True) ───────────────
        if request.include_gif and asset_ids:
            try:
                from app.incept.gif_generator import generate_cta_pulse_gif, is_gif_allowed_for_size
                gif_asset_ids: list[str] = []
                for asset_id in asset_ids:
                    asset_obj = ASSETS.get(asset_id)
                    if not asset_obj or not asset_obj.preview_url:
                        continue
                    size_str = f"{asset_obj.width}x{asset_obj.height}" if asset_obj.width and asset_obj.height else ""
                    if not is_gif_allowed_for_size(size_str):
                        continue
                    img_path = _resolve_asset_path(asset_obj)
                    if not img_path or not img_path.exists():
                        continue
                    img_bytes = img_path.read_bytes()
                    gif_bytes = generate_cta_pulse_gif(
                        image_bytes=img_bytes,
                        target_size=size_str,
                        anchors=(asset_obj.analysis or {}).get("anchors") if asset_obj.analysis else None,
                    )
                    gif_asset_id = f"{asset_id}_gif"
                    gif_path = STATIC_DIR / f"{gif_asset_id}.gif"
                    gif_path.write_bytes(gif_bytes)
                    gif_preview_url = f"/static/generated/{gif_asset_id}.gif"
                    gif_asset = Asset(
                        id=gif_asset_id,
                        title=f"{asset_obj.title} (GIF)",
                        type="gif",
                        gcs_uri=f"gs://incept-assets/generated/{request.workspace_id}/{job_id}/{gif_asset_id}.gif",
                        preview_url=gif_preview_url,
                        provider=request.provider,
                        model=model,
                        workspace_id=request.workspace_id,
                        job_id=job_id,
                        prompt_hash=prompt_hash,
                        created_by=user.id,
                        created_at=now,
                        width=asset_obj.width,
                        height=asset_obj.height,
                        theme=asset_obj.theme,
                        asset_role=AssetRole.generated,
                        thread_id=job.thread_id,
                        parent_asset_id=asset_id,
                        root_asset_id=asset_id,
                    )
                    ASSETS[gif_asset_id] = gif_asset
                    upsert_asset(gif_asset)
                    gif_asset_ids.append(gif_asset_id)
                if gif_asset_ids:
                    asset_ids = asset_ids + gif_asset_ids
                    logger.info("Generated %d GIF(s) for job %s", len(gif_asset_ids), job_id)
            except Exception:
                logger.warning("GIF generation failed for job %s — skipping", job_id, exc_info=True)

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        generation_mode_note = ""
        reported_variant_count = request.variants
        if renderer_rendered_outputs:
            generation_mode_note = " via multi-size renderer"
        elif contact_sheet_reports:
            generation_mode_note = " as contact sheet previews"
        job.message = (
            f"Generated {len(asset_ids)} assets with {provider_label}{generation_mode_note}: "
            f"{reported_variant_count} variants × {len(request.output_sizes)} sizes."
        )
        job.updated_at = datetime.utcnow()

        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Generated images: {request.prompt}",
                asset_ids=asset_ids,
                job_id=job_id,
            )

        _record_usage(job, request, user, model, prompt_hash, now)

    except ClarificationRequired as exc:
        _apply_clarification_failure(job, exc.question, manifest=exc.manifest, reason=exc.reason)
    except Exception as exc:
        logger.exception("Image generation failed for job %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        error_summary = f"{exc.__class__.__name__}: {str(exc)}"[:500]
        job.message = (
            f"Image generation failed: {error_summary}"
        )
        job.updated_at = datetime.utcnow()
        upsert_job(job)


# ── Inpainting / image-edit background task ───────────────────────────────────

def _parse_targets(directive: dict, fallback_prompt: str) -> list[str]:
    """
    Extract the list of elements to detect and mask.

    Examples:
      "去掉 PlayNow 按钮和 logo" → ["PlayNow button", "logo"]
      directive target: "PlayNow button and logo" → ["PlayNow button", "logo"]
    """
    target = directive.get("target", "").strip()
    if not target:
        target = fallback_prompt

    # Split on common conjunctions to handle multi-element targets
    import re
    parts = re.split(r"\band\b|,|、|和|与|以及", target, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _detection_candidates(target: str) -> list[str]:
    """Expand a user-visible target description into better vision-detection candidates."""
    import re

    raw = (target or "").strip()
    if not raw:
        return []

    normalized = re.sub(r"\s+", " ", raw).strip()
    lowered = normalized.lower()
    candidates: list[str] = [normalized]

    if "playnow" in lowered:
        candidates.extend(["Play Now", "Play Now button", "CTA button"])
    if "play now" in lowered:
        candidates.extend(["Play Now button", "CTA button", "green Play Now button"])
    if "cta" in lowered or "button" in lowered:
        candidates.extend(["CTA button", "call to action button", normalized.replace("cta", "button")])
    if "logo" in lowered:
        candidates.extend(["logo", "brand logo", "game logo"])
    if "text" in lowered or "headline" in lowered or "title" in lowered:
        candidates.extend(["text overlay", "headline text", normalized])

    cleaned = re.sub(
        r"\b(remove|delete|erase|take off|take out|get rid of|replace|change)\b",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip(" '\"-:,")
    if cleaned and cleaned.lower() != lowered:
        candidates.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = candidate.strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            deduped.append(value)
    return deduped


def _merge_masks(existing: "bytes | None", new_mask: bytes, ref_image: bytes) -> bytes:
    """
    Merge two masks: combined transparent area = union of both edit zones.
    (transparent = edit; opaque = preserve)
    """
    from PIL import Image
    import io

    if existing is None:
        return new_mask

    img_a = Image.open(io.BytesIO(existing)).convert("RGBA")
    img_b = Image.open(io.BytesIO(new_mask)).convert("RGBA")

    # Make combined mask opaque (preserve) everywhere
    w, h = img_a.size
    merged = Image.new("RGBA", (w, h), (255, 255, 255, 255))

    pa = img_a.load()
    pb = img_b.load()
    pm = merged.load()

    for y in range(h):
        for x in range(w):
            # If EITHER mask is transparent here → mark as edit zone
            if pa[x, y][3] == 0 or pb[x, y][3] == 0:
                pm[x, y] = (0, 0, 0, 0)

    buf = io.BytesIO()
    merged.save(buf, format="PNG")
    return buf.getvalue()


def _build_inpaint_prompt(directive: dict, original_theme: str | None) -> str:
    """
    Build a focused prompt for images.edit.

    CRITICAL RULE: images.edit prompt must describe what the MASKED AREA
    should look like AFTER editing — NOT what operation to perform.
    A long instruction prompt causes the model to ignore the original image
    and regenerate everything from scratch.
    """
    operation = directive.get("operation", "edit")
    target    = directive.get("target", "")
    style     = directive.get("style_description") or original_theme or "matching the surrounding art style"

    if operation == "remove":
        return (
            f"The area where {target} was is now filled with the natural background "
            f"seamlessly continuing from the surrounding scene. "
            f"{style}. No button, no logo, no text overlay — just clean background "
            f"matching the surrounding colors, textures, and lighting exactly."
        )

    if operation == "replace":
        replacement = directive.get("target", "the replacement element")
        return (
            f"{replacement}. Rendered in {style}. "
            f"Same lighting, perspective, and scale as the surrounding context. "
            f"Blends naturally with the rest of the image."
        )

    if operation == "edit_text":
        new_text = directive.get("target_text", "")
        return (
            f'The text now reads: "{new_text}". '
            f"Same font, size, colour, and position as the original text."
        )

    # Generic / fallback — keep it short
    enhanced = directive.get("enhanced_prompt", "")
    # Strip any instruction-style language that confuses the model
    for bad_prefix in ["OPERATION:", "RULES:", "CRITICAL:"]:
        if bad_prefix in enhanced:
            enhanced = enhanced.split(bad_prefix)[0].strip()
    return enhanced or target or "seamless background matching surrounding area"


def create_edit_job(request: "ImageEditRequest", user: User) -> GenerationJob:
    """Create a job record for an inpainting edit. Background task fills it."""
    job_id = f"job_{uuid4().hex[:12]}"
    lineage_key = f"llg_edit_{uuid4().hex[:16]}"
    now = datetime.utcnow()
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.theme or request.prompt,
        source_asset_id=source_asset.id if source_asset else None,
    )

    job = GenerationJob(
        job_id=job_id,
        workspace_id=request.workspace_id,
        status=JobStatus.running,
        progress=0,
        lineage_key=lineage_key,
        message="Editing image…",
        tool_id="openai-image-edit",
        title=f"Image edit — {request.prompt[:40]}",
        output_asset_ids=[],
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
        created_at=now,
        updated_at=now,
    )
    JOBS[job_id] = job
    upsert_job(job)
    return job


async def run_edit_background(
    job_id: str,
    request: "ImageEditRequest",
    user: User,
) -> None:
    """Background task: run inpainting via images.edit and save result."""
    job = JOBS.get(job_id)
    if not job:
        return

    settings = get_settings()
    lineage_key = job.lineage_key
    now = datetime.utcnow()

    try:
        # ── Resolve original image ──────────────────────────────────────────
        original_asset = _get_asset(request.asset_id)
        if not original_asset:
            raise ValueError(f"Asset {request.asset_id} not found")

        img_path: Path | None = None
        if original_asset.preview_url.startswith("/static/generated/"):
            img_path = STATIC_DIR / original_asset.preview_url[len("/static/generated/"):]
        elif original_asset.preview_url.startswith("/static/uploads/"):
            img_path = UPLOAD_DIR / original_asset.preview_url[len("/static/uploads/"):]

        if not img_path or not img_path.exists():
            raise FileNotFoundError(f"Image file not found for {request.asset_id}")

        original_bytes = img_path.read_bytes()

        # ── Decode mask if provided (from inpainting canvas) ───────────────
        mask_bytes: bytes | None = None
        if request.mask_data:
            mask_b64 = request.mask_data
            if "," in mask_b64:
                mask_b64 = mask_b64.split(",", 1)[1]
            mask_bytes = base64.b64decode(mask_b64)

        job.progress = 15
        job.updated_at = datetime.utcnow()

        # ── Resolve extra reference assets (logos etc.) ─────────────────────
        logo_assets = [_get_asset(aid) for aid in (request.extra_asset_ids or []) if _get_asset(aid)]

        # ── Orchestrate: classify intent + enhance prompt ───────────────────
        from app.incept.orchestrator import orchestrate, auto_detect_and_mask, build_operation_prompt
        session_history = thread_store.get_context_messages(job.thread_id or "", n=4)

        directive = await orchestrate(
            user_prompt=request.prompt,
            reference_assets=[original_asset],
            session_history=session_history,
            target_sizes=_effective_output_sizes(request.output_sizes, original_asset),
            static_dir=STATIC_DIR,
            upload_dir=UPLOAD_DIR,
            api_key=settings.openai_api_key,
            logo_assets=logo_assets or None,
        )
        manifest = build_preservation_manifest(
            task_type="edit",
            prompt=request.prompt,
            target_sizes=_effective_output_sizes(request.output_sizes, original_asset),
            context_assets=[original_asset, *logo_assets],
            directive=directive,
            clarification_note=request.clarification_note,
        )
        ensure_manifest_clarity(manifest)

        operation = directive.get("operation", "edit")
        job.progress = 25
        job.updated_at = datetime.utcnow()

        # ── LOGO PLACEMENT: skip AI, use Pillow direct compositing ──────────
        if operation == "logo_placement" and logo_assets:
            logo_path = _resolve_asset_path(logo_assets[0])
            if logo_path and logo_path.exists():
                from app.incept.composite import composite_logo
                logo_bytes = logo_path.read_bytes()
                position = directive.get("position", "top-left")
                result_bytes = composite_logo(original_bytes, logo_bytes, position)

                created_assets = await _export_master_images_to_assets(
                    job=job,
                    raw_outputs=[result_bytes],
                    workspace_id=request.workspace_id,
                    created_by=user.id,
                    provider="pillow",
                    model="pillow",
                    label=f"Logo placed: {position}",
                    theme=request.theme or "logo-composite",
                    requested_sizes=request.output_sizes,
                    source_asset=original_asset,
                    context_assets=[original_asset, *logo_assets],
                    api_key=settings.openai_api_key,
                    created_at=now,
                    manifest=manifest,
                    use_smart_resize=False,
                )
                asset_ids = [asset.id for asset in created_assets]
                job.output_asset_ids = asset_ids
                job.status = JobStatus.completed
                job.progress = 100
                job.message = f"Logo composited at {position}."
                job.updated_at = datetime.utcnow()
                upsert_job(job)
                if job.thread_id:
                    thread_store.add_assistant_message(
                        job.thread_id,
                        text=f"Placed logo at {position}",
                        asset_ids=asset_ids,
                        job_id=job_id,
                    )
                    thread_store.touch_thread(
                        job.thread_id,
                        latest_job_id=job.job_id,
                        latest_asset_id=asset_ids[-1] if asset_ids else None,
                        cover_asset_id=asset_ids[0] if asset_ids else None,
                        title=request.theme or original_asset.theme or None,
                    )
                return   # ← done, no AI call needed

        # ── Auto-detect element mask (if no manual mask) ──────────────────────
        # CRITICAL: images.edit REQUIRES a mask to work correctly.
        # Without a mask, OpenAI edits the entire image and produces a completely
        # different result — it does NOT preserve the original.
        if not mask_bytes and settings.openai_api_key:
            # Detect one or more elements to mask.
            # If the user said "去掉 PlayNow 和 logo", detect each separately.
            elements_to_mask = _parse_targets(directive, request.prompt)
            combined_mask: bytes | None = None

            for element in elements_to_mask:
                detected = None
                for candidate in _detection_candidates(element):
                    detected = await auto_detect_and_mask(
                        image_bytes=original_bytes,
                        element_description=candidate,
                        api_key=settings.openai_api_key,
                    )
                    if detected:
                        combined_mask = _merge_masks(combined_mask, detected, original_bytes)
                        logger.info(
                            "Detected mask for '%s' via candidate '%s' job=%s",
                            element,
                            candidate,
                            job_id,
                        )
                        break

            mask_bytes = combined_mask

        # If still no mask at all, we cannot safely edit without destroying the image
        if not mask_bytes:
            unresolved_targets = _parse_targets(directive, request.prompt)
            unresolved_text = ", ".join(unresolved_targets[:2]) or "the target element"
            _apply_clarification_failure(
                job,
                (
                    f"I couldn't automatically locate {unresolved_text}. "
                    "Please paint a mask over the area to change, or describe the target more specifically."
                ),
                manifest=manifest,
                reason="Auto-detection could not confidently locate the requested edit target.",
            )
            return

        job.progress = 40
        job.updated_at = datetime.utcnow()

        # ── Build the inpainting prompt ────────────────────────────────────────
        # IMPORTANT: images.edit prompt describes what to PUT IN the masked area,
        # NOT what operation to perform. Keep it short and visual.
        edit_prompt = _build_inpaint_prompt_v2(directive, original_asset.theme)

        # ── Call images.edit ────────────────────────────────────────────────
        b64_images = await _edit_image_openai(
            original_bytes=original_bytes,
            mask_bytes=mask_bytes,
            prompt=edit_prompt,
            model=request.model,
            variants=request.variants,
        )

        job.progress = 80
        job.updated_at = datetime.utcnow()

        # ── Save output assets ──────────────────────────────────────────────
        prompt_hash = sha256(request.prompt.encode()).hexdigest()[:16]
        raw_outputs: list[bytes] = []
        for b64 in b64_images:
            try:
                raw_outputs.append(base64.b64decode(b64))
            except Exception:
                logger.warning("Could not decode edited output for job %s", job_id)

        created_assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=raw_outputs,
            workspace_id=request.workspace_id,
            created_by=user.id,
            provider="openai",
            model=request.model,
            label=request.theme or "Edit",
            theme=request.theme or original_asset.theme,
            requested_sizes=request.output_sizes,
            source_asset=original_asset,
            context_assets=[original_asset, *logo_assets],
            api_key=settings.openai_api_key,
            created_at=now,
            manifest=manifest,
            use_smart_resize=False,
        )
        asset_ids = [asset.id for asset in created_assets]
        for asset in created_assets:
            asset.prompt_hash = prompt_hash
            upsert_asset(asset)

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Edited {len(asset_ids)} image(s)."
        job.updated_at = datetime.utcnow()
        upsert_job(job)

        # ── Update session ──────────────────────────────────────────────────
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Edited image: {request.prompt}",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title=request.theme or original_asset.theme or None,
            )

    except ClarificationRequired as exc:
        _apply_clarification_failure(job, exc.question, manifest=exc.manifest, reason=exc.reason)
    except Exception:
        logger.exception("Image edit failed for job %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = "Image edit failed. Check OPENAI_API_KEY and logs."
        job.updated_at = datetime.utcnow()
        upsert_job(job)


# ── Shared helper ─────────────────────────────────────────────────────────────

def _get_asset(asset_id: str) -> "Asset | None":
    """Look up asset in both ASSETS and SOURCE_ASSETS (uploads)."""
    return ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)


def _resolve_asset_path(asset: Asset) -> "Path | None":
    if asset.preview_url.startswith("/static/generated/"):
        return STATIC_DIR / asset.preview_url[len("/static/generated/"):]
    if asset.preview_url.startswith("/static/uploads/"):
        return UPLOAD_DIR / asset.preview_url[len("/static/uploads/"):]
    return None


def _make_simple_job(
    tool_id: str,
    title: str,
    workspace_id: str,
    thread_id: str | None = None,
    source_asset_id: str | None = None,
) -> GenerationJob:
    job_id = f"job_{uuid4().hex[:12]}"
    lineage_key = f"llg_{tool_id}_{uuid4().hex[:12]}"
    now = datetime.utcnow()
    job = GenerationJob(
        job_id=job_id,
        workspace_id=workspace_id,
        status=JobStatus.running,
        progress=0,
        lineage_key=lineage_key,
        message=f"{title}…",
        tool_id=tool_id,
        title=title,
        output_asset_ids=[],
        thread_id=thread_id,
        source_asset_id=source_asset_id,
        created_at=now,
        updated_at=now,
    )
    JOBS[job_id] = job
    upsert_job(job)
    return job


def _save_output_asset(
    job: GenerationJob,
    b64: str,
    label: str,
    provider: str,
    model: str,
    workspace_id: str,
    created_by: str,
    width: "int | None" = None,
    height: "int | None" = None,
    theme: "str | None" = None,
    idx: int = 0,
    parent_asset_id: str | None = None,
    root_asset_id: str | None = None,
) -> Asset:
    asset_id = f"{job.lineage_key}_out_{idx + 1}_img"
    preview_url = _save_image_file(asset_id, b64)

    # Auto-detect dimensions if not provided by the caller
    if width is None or height is None:
        try:
            raw = base64.b64decode(b64)
            width, height = _read_image_size(raw)
        except Exception:
            pass

    now = datetime.utcnow()
    asset = Asset(
        id=asset_id,
        title=label,
        type="image",
        gcs_uri=f"gs://incept-assets/{workspace_id}/{job.job_id}/{asset_id}.png",
        preview_url=preview_url,
        provider=provider,
        model=model,
        workspace_id=workspace_id,
        job_id=job.job_id,
        prompt_hash="",
        created_by=created_by,
        created_at=now,
        width=width,
        height=height,
        theme=theme,
        asset_role=AssetRole.generated,
        thread_id=job.thread_id,
        parent_asset_id=parent_asset_id,
        root_asset_id=root_asset_id or asset_id,
    )
    ASSETS[asset_id] = asset
    upsert_asset(asset)
    return asset


# ── Outpaint ──────────────────────────────────────────────────────────────────

def create_outpaint_job(request: OutpaintRequest, user: User) -> GenerationJob:
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.prompt or "Outpainting",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "outpaint",
        "Outpainting",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


async def run_outpaint_background(job_id: str, request: OutpaintRequest, user: User) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    try:
        original = _get_asset(request.asset_id)
        if not original:
            raise ValueError(f"Asset {request.asset_id} not found")

        img_path = _resolve_asset_path(original)
        if not img_path or not img_path.exists():
            raise FileNotFoundError("Image file not found on disk")

        job.progress = 15
        job.updated_at = datetime.utcnow()

        from app.incept.composite import create_outpaint_inputs
        expanded_bytes, mask_bytes = create_outpaint_inputs(
            img_path.read_bytes(), request.direction, request.ratio
        )

        job.progress = 30
        job.updated_at = datetime.utcnow()

        prompt = request.prompt or (
            f"Seamlessly extend this image {request.direction}ward. "
            "Match the existing art style, lighting, colors, characters, and scene. "
            "Continue any elements at the edges naturally."
        )
        manifest = build_preservation_manifest(
            task_type="outpaint",
            prompt=prompt,
            target_sizes=_effective_output_sizes(request.output_sizes, original),
            context_assets=[original],
            directive={"operation": "outpaint"},
            clarification_note=request.clarification_note,
        )
        ensure_manifest_clarity(manifest)

        b64_list = await _edit_image_openai(
            original_bytes=expanded_bytes,
            mask_bytes=mask_bytes,
            prompt=prompt,
            model=request.model,
            variants=1,
        )

        job.progress = 80
        raw_outputs = [base64.b64decode(b64) for b64 in b64_list]
        created_assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=raw_outputs,
            workspace_id=request.workspace_id,
            created_by=user.id,
            provider="openai",
            model=request.model,
            label=f"Outpaint {request.direction}",
            theme="outpaint",
            requested_sizes=request.output_sizes,
            source_asset=original,
            context_assets=[original],
            api_key=get_settings().openai_api_key,
            manifest=manifest,
            use_smart_resize=False,
        )
        asset_ids = [asset.id for asset in created_assets]

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Outpainted {request.direction}."
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Outpainted image {request.direction}",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title=original.theme or None,
            )

    except ClarificationRequired as exc:
        _apply_clarification_failure(job, exc.question, manifest=exc.manifest, reason=exc.reason)
    except Exception:
        logger.exception("Outpaint failed for job %s", job_id)
        job.status = JobStatus.failed
        job.message = "Outpaint failed. Check OPENAI_API_KEY and logs."
        job.updated_at = datetime.utcnow()
        upsert_job(job)


# ── Background removal ────────────────────────────────────────────────────────

def create_remove_bg_job(request: RemoveBGRequest, user: User) -> GenerationJob:
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.replacement_prompt or "Background removal",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "remove-bg",
        "Background Removal",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


async def run_remove_bg_background(job_id: str, request: RemoveBGRequest, user: User) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    try:
        original = _get_asset(request.asset_id)
        if not original:
            raise ValueError(f"Asset {request.asset_id} not found")

        img_path = _resolve_asset_path(original)
        if not img_path or not img_path.exists():
            raise FileNotFoundError("Image file not found on disk")

        job.progress = 20
        job.updated_at = datetime.utcnow()

        from app.incept.composite import remove_background
        result_bytes, used_rembg = remove_background(img_path.read_bytes())
        manifest = build_preservation_manifest(
            task_type="remove_bg",
            prompt=request.replacement_prompt or "Remove background",
            target_sizes=_effective_output_sizes(request.output_sizes, original),
            context_assets=[original],
            directive={"operation": "remove_bg"},
            clarification_note=request.clarification_note,
        )
        ensure_manifest_clarity(manifest)

        if not used_rembg or request.replacement_prompt:
            # Fall back to images.edit for replacement or when rembg unavailable
            prompt = (
                request.replacement_prompt
                or "Remove the background completely. Make the background fully transparent."
            )
            b64_list = await _edit_image_openai(
                original_bytes=img_path.read_bytes(),
                mask_bytes=None,
                prompt=prompt,
                model=request.model,
                variants=1,
            )
            job.progress = 80
            raw_outputs = [base64.b64decode(b64) for b64 in b64_list]
            created_assets = await _export_master_images_to_assets(
                job=job,
                raw_outputs=raw_outputs,
                workspace_id=request.workspace_id,
                created_by=user.id,
                provider="openai",
                model=request.model,
                label="Background removed",
                theme="no-bg",
                requested_sizes=request.output_sizes,
                source_asset=original,
                context_assets=[original],
                api_key=get_settings().openai_api_key,
                manifest=manifest,
                use_smart_resize=False,
            )
            asset_ids = [asset.id for asset in created_assets]
        else:
            # rembg succeeded: save result directly without AI call
            job.progress = 80
            created_assets = await _export_master_images_to_assets(
                job=job,
                raw_outputs=[result_bytes],
                workspace_id=request.workspace_id,
                created_by=user.id,
                provider="rembg",
                model="rembg",
                label="Background removed",
                theme="no-bg",
                requested_sizes=request.output_sizes,
                source_asset=original,
                context_assets=[original],
                api_key=get_settings().openai_api_key,
                manifest=manifest,
                use_smart_resize=False,
            )
            asset_ids = [asset.id for asset in created_assets]

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = "Background removed."
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text="Removed background",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title=original.theme or None,
            )

    except ClarificationRequired as exc:
        _apply_clarification_failure(job, exc.question, manifest=exc.manifest, reason=exc.reason)
    except Exception:
        logger.exception("Remove-BG failed for job %s", job_id)
        job.status = JobStatus.failed
        job.message = "Background removal failed."
        job.updated_at = datetime.utcnow()
        upsert_job(job)


# ── Text overlay ──────────────────────────────────────────────────────────────

def create_add_text_job(request: AddTextRequest, user: User) -> GenerationJob:
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.text or "Text overlay",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "add-text",
        f"Text: {request.text[:30]}",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


async def run_add_text_background(job_id: str, request: AddTextRequest, user: User) -> None:
    """Text overlay is pure Pillow — no AI call needed, completes instantly."""
    job = JOBS.get(job_id)
    if not job:
        return

    try:
        original = _get_asset(request.asset_id)
        if not original:
            raise ValueError(f"Asset {request.asset_id} not found")

        img_path = _resolve_asset_path(original)
        if not img_path or not img_path.exists():
            raise FileNotFoundError("Image file not found on disk")

        job.progress = 30
        job.updated_at = datetime.utcnow()

        from app.incept.composite import add_text_overlay
        result_bytes = add_text_overlay(
            image_bytes=img_path.read_bytes(),
            text=request.text,
            position=request.position,
            font_size_ratio=request.font_size_ratio,
        )
        manifest = build_preservation_manifest(
            task_type="add_text",
            prompt=request.text,
            target_sizes=_effective_output_sizes(request.output_sizes, original),
            context_assets=[original],
            directive={"operation": "add_text"},
            clarification_note=request.clarification_note,
        )
        ensure_manifest_clarity(manifest)

        created_assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=[result_bytes],
            workspace_id=request.workspace_id,
            created_by=user.id,
            provider="pillow",
            model="pillow",
            label=f"Text: {request.text[:20]}",
            theme=request.text[:40],
            requested_sizes=request.output_sizes,
            source_asset=original,
            context_assets=[original],
            api_key=get_settings().openai_api_key,
            manifest=manifest,
            use_smart_resize=False,
        )
        asset_ids = [asset.id for asset in created_assets]

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Text added: {request.text[:40]}"
        job.updated_at = datetime.utcnow()
        upsert_job(job)
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Added text: {request.text[:40]}",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title=original.theme or request.text[:40],
            )

    except ClarificationRequired as exc:
        _apply_clarification_failure(job, exc.question, manifest=exc.manifest, reason=exc.reason)
    except Exception:
        logger.exception("Add-text failed for job %s", job_id)
        job.status = JobStatus.failed
        job.message = "Text overlay failed."
        job.updated_at = datetime.utcnow()
        upsert_job(job)


def _build_inpaint_prompt_v2(directive: dict, original_theme: str | None) -> str:
    """
    Build a shorter, edit-focused prompt for images.edit.

    The prompt should describe only what the masked area should look like after
    editing, not a full procedural instruction set.
    """
    operation = directive.get("operation", "edit")
    target = directive.get("target", "")
    style = directive.get("style_description") or original_theme or "matching the surrounding art style"

    if operation == "remove":
        target_note = f" where {target} used to be" if target else ""
        return (
            f"The masked area{target_note} is now seamless natural background that continues "
            f"from the surrounding scene. Render it in {style}. Match the surrounding colors, "
            f"textures, edges, and lighting exactly. Do not add any new object, button, logo, "
            f"or text inside the masked region."
        )

    if operation == "replace":
        replacement = directive.get("target", "the replacement element")
        return (
            f"{replacement}. Rendered in {style}. Same lighting, perspective, and scale as "
            f"the surrounding context. Blends naturally with the rest of the image."
        )

    if operation == "edit_text":
        new_text = directive.get("target_text", "")
        return (
            f'The text now reads: "{new_text}". '
            f"Same font, size, colour, and position as the original text."
        )

    enhanced = directive.get("enhanced_prompt", "")
    for bad_prefix in ["OPERATION:", "RULES:", "CRITICAL:"]:
        if bad_prefix in enhanced:
            enhanced = enhanced.split(bad_prefix)[0].strip()
    return enhanced or target or "seamless background matching surrounding area"
