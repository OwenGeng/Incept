from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.config import settings
from app.models.supply import (
    DetailedAnalysisPayload,
    GenericTopListsPayload,
    RefreshSnapshotResponse,
    TopListsPayload,
    WeeklyBriefPayload,
)
from app.services.auth import RoleContext, get_role_context, require_internal_key
from app.services.mock_data import (
    detailed_analysis_mock,
    top_lists_mock,
    weekly_brief_mock,
)
from app.services.supply_smb_live import DATASET_META, DatasetTopListOptions, SupplySmbLiveService, TopListOptions

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
