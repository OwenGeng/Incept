import asyncio
import subprocess
import sys
import time
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.models.supply import (
    DetailedAnalysisPayload,
    GenericTopListsPayload,
    RefreshSnapshotResponse,
    TopListsPayload,
    WeeklyBriefPayload,
    WeeklyBriefSummaryPayload,
)
from app.services.auth import RoleContext, get_role_context, require_internal_key
from app.services.mock_data import (
    detailed_analysis_mock,
    top_lists_mock,
    weekly_brief_mock,
)
from app.services.supply_smb_live import DATASET_META, DatasetTopListOptions, SupplySmbLiveService, TopListOptions


class PipelineStatusResponse(BaseModel):
    status: Literal["idle", "running", "success", "failed"]
    started_at: float | None = None
    finished_at: float | None = None
    message: str = ""


# ── Pipeline process state ──────────────────────────────────────────────────
_pipeline_proc: subprocess.Popen | None = None
_pipeline_started_at: float | None = None
_pipeline_finished_at: float | None = None
_pipeline_exit_code: int | None = None


def _pipeline_status() -> PipelineStatusResponse:
    global _pipeline_proc, _pipeline_started_at, _pipeline_finished_at, _pipeline_exit_code
    if _pipeline_proc is None:
        return PipelineStatusResponse(status="idle", message="No pipeline run yet.")
    rc = _pipeline_proc.poll()
    if rc is None:
        return PipelineStatusResponse(
            status="running",
            started_at=_pipeline_started_at,
            message="Pipeline is running…",
        )
    if _pipeline_finished_at is None:
        _pipeline_finished_at = time.time()
        _pipeline_exit_code = rc
    if rc == 0:
        return PipelineStatusResponse(
            status="success",
            started_at=_pipeline_started_at,
            finished_at=_pipeline_finished_at,
            message="Pipeline completed successfully.",
        )
    return PipelineStatusResponse(
        status="failed",
        started_at=_pipeline_started_at,
        finished_at=_pipeline_finished_at,
        message=f"Pipeline exited with code {rc}.",
    )

router = APIRouter(
    prefix="/api/v1/supply-smb",
    tags=["supply-smb"],
    dependencies=[Depends(require_internal_key)],
)

_service: SupplySmbLiveService | None = None


def _get_service() -> SupplySmbLiveService:
    global _service
    if _service is None:
        _service = SupplySmbLiveService()
    return _service


@router.get("/weekly-brief", response_model=WeeklyBriefPayload)
async def get_weekly_brief() -> WeeklyBriefPayload:
    if settings.api_mode == "mock":
        return weekly_brief_mock
    return _get_service().get_weekly_brief()


@router.get("/weekly-brief/summary", response_model=WeeklyBriefSummaryPayload)
async def get_weekly_brief_summary() -> WeeklyBriefSummaryPayload:
    """AI-generated summary — fetched separately so it can stream in after the fast payload."""
    if settings.api_mode == "mock":
        return WeeklyBriefSummaryPayload(
            summary=weekly_brief_mock.summary,
            opportunity=weekly_brief_mock.opportunity,
            big_things=weekly_brief_mock.big_things,
            week_changes=weekly_brief_mock.week_changes,
        )
    return WeeklyBriefSummaryPayload(**_get_service().get_weekly_brief_summary())


@router.get("/top-lists", response_model=TopListsPayload)
async def get_top_lists(
    priority: str = Query(default="all"),
    routing: str = Query(default="all"),
    supply_visibility: str = Query(default="all"),
    search: str = Query(default=""),
    company_sort_by: str = Query(default="company_prospect_label"),
    company_sort_dir: str = Query(default="asc"),
    app_sort_by: str = Query(default="prospect_label"),
    app_sort_dir: str = Query(default="asc"),
    company_page: int = Query(default=1, ge=1),
    app_page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=9999),
    role: RoleContext = Depends(get_role_context),
) -> TopListsPayload:
    if settings.api_mode == "mock":
        return top_lists_mock

    # Agency: override routing to their allowed bucket regardless of query param
    effective_routing = routing
    if role.is_agency() and role.allowed_routing:
        effective_routing = role.allowed_routing

    return _get_service().get_top_lists(
        TopListOptions(
            priority=priority,
            routing=effective_routing,
            supply_visibility=supply_visibility,
            search=search,
            company_sort_by=company_sort_by,
            company_sort_dir=company_sort_dir,
            app_sort_by=app_sort_by,
            app_sort_dir=app_sort_dir,
            company_page=company_page,
            app_page=app_page,
            page_size=page_size,
        )
    )


@router.get("/detailed-analysis", response_model=DetailedAnalysisPayload)
async def get_detailed_analysis(
    role: RoleContext = Depends(get_role_context),
) -> DetailedAnalysisPayload:
    if settings.api_mode == "mock":
        return detailed_analysis_mock
    return _get_service().get_detailed_analysis(
        routing_filter=role.allowed_routing if role.is_agency() else None
    )


@router.get("/datasets/{dataset_key}/top-lists", response_model=GenericTopListsPayload)
async def get_dataset_top_lists(
    dataset_key: str,
    search: str = Query(default=""),
    routing: str = Query(default="all"),
    hq_country: str = Query(default="all"),
    monetization: str = Query(default="all"),
    company_sort_by: str = Query(default="company_name"),
    company_sort_dir: str = Query(default="asc"),
    app_sort_by: str = Query(default="company_name"),
    app_sort_dir: str = Query(default="asc"),
    company_page: int = Query(default=1, ge=1),
    app_page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=9999),
    role: RoleContext = Depends(get_role_context),
) -> GenericTopListsPayload:
    if dataset_key not in DATASET_META:
        raise HTTPException(status_code=404, detail=f"Unknown dataset_key: {dataset_key}")

    effective_routing = routing
    if role.is_agency() and role.allowed_routing:
        effective_routing = role.allowed_routing

    return _get_service().get_dataset_top_lists(
        dataset_key,
        DatasetTopListOptions(
            search=search,
            routing=effective_routing,
            hq_country=hq_country,
            monetization=monetization,
            company_sort_by=company_sort_by,
            company_sort_dir=company_sort_dir,
            app_sort_by=app_sort_by,
            app_sort_dir=app_sort_dir,
            company_page=company_page,
            app_page=app_page,
            page_size=page_size,
        ),
    )


@router.get("/datasets/{dataset_key}/detailed-analysis", response_model=DetailedAnalysisPayload)
async def get_dataset_detailed_analysis(
    dataset_key: str,
    role: RoleContext = Depends(get_role_context),
) -> DetailedAnalysisPayload:
    if dataset_key not in DATASET_META:
        raise HTTPException(status_code=404, detail=f"Unknown dataset_key: {dataset_key}")
    return _get_service().get_dataset_detailed_analysis(
        dataset_key,
        routing_filter=role.allowed_routing if role.is_agency() else None,
    )


@router.post("/refresh-snapshot", response_model=RefreshSnapshotResponse)
async def refresh_snapshot() -> RefreshSnapshotResponse:
    """
    Pull fresh BQ data and write a weekly snapshot to intersight.supply_smb_snapshot.
    Run once per week (manually or via Cloud Scheduler).
    """
    if settings.api_mode == "mock":
        from datetime import date
        return RefreshSnapshotResponse(
            week_start_date=date.today().isoformat(),
            snapshot_written=False,
            message="Mock mode — no BQ write performed.",
        )
    return _get_service().refresh_snapshot()


@router.post("/enrich-bundles")
async def enrich_bundles(
    file: UploadFile = File(...),
    bundle_id_column: str = Form(default="bundle_id"),
) -> list[dict]:
    """
    Upload a CSV file, match each bundle_id against Moloco BQ data, and return
    the original rows enriched with Moloco diagnosis columns.
    """
    if settings.api_mode == "mock":
        return []
    content = await file.read()
    try:
        return _get_service().enrich_bundles(content, bundle_id_column)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run-pipeline", response_model=PipelineStatusResponse)
async def run_pipeline() -> PipelineStatusResponse:
    """Trigger save_cold_prospect_table pipeline in background. Fire-and-forget."""
    global _pipeline_proc, _pipeline_started_at, _pipeline_finished_at, _pipeline_exit_code
    if settings.api_mode == "mock":
        return PipelineStatusResponse(status="idle", message="Mock mode — pipeline not started.")
    current = _pipeline_status()
    if current.status == "running":
        return current
    _pipeline_finished_at = None
    _pipeline_exit_code = None
    _pipeline_started_at = time.time()
    _pipeline_proc = subprocess.Popen(
        [sys.executable, "-m", "app.incept.save_cold_prospect_table"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return PipelineStatusResponse(
        status="running",
        started_at=_pipeline_started_at,
        message="Pipeline started.",
    )


@router.get("/pipeline-status", response_model=PipelineStatusResponse)
async def get_pipeline_status() -> PipelineStatusResponse:
    """Return current pipeline run status."""
    return _pipeline_status()
