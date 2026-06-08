from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.supply import LeadCreate, LeadListPayload, LeadRecord, LeadStatusUpdate
from app.services.auth import RoleContext, get_role_context, require_internal_key
from app.services.lead_tracking_service import LeadTrackingService

router = APIRouter(
    prefix="/api/v1/leads",
    tags=["leads"],
    dependencies=[Depends(require_internal_key)],
)

_service: LeadTrackingService | None = None


def _get_service() -> LeadTrackingService:
    global _service
    if _service is None:
        _service = LeadTrackingService()
    return _service


@router.post("", response_model=LeadRecord, status_code=201)
async def create_lead(
    payload: LeadCreate,
    role: RoleContext = Depends(get_role_context),
) -> LeadRecord:
    """Mark a company as contacted / sent to agency."""
    # Agency users can only create leads attributed to themselves
    if role.is_agency() and role.email:
        payload = payload.model_copy(update={"activated_by": role.email})
    return _get_service().create_lead(payload)


@router.get("", response_model=LeadListPayload)
async def list_leads(
    attribution: bool = Query(default=False, description="Run attribution check against fact_dsp_core"),
    role: RoleContext = Depends(get_role_context),
) -> LeadListPayload:
    """List leads. Agency users see only leads they activated."""
    email_filter = role.email if role.is_agency() else None
    return _get_service().list_leads(run_attribution=attribution, email_filter=email_filter)


@router.patch("/{lead_id}", response_model=dict)
async def update_lead_status(
    lead_id: str,
    update: LeadStatusUpdate,
    role: RoleContext = Depends(get_role_context),
) -> dict:
    """Update the status of a lead (sent → opened → spending)."""
    if update.status not in ("sent", "opened", "spending"):
        raise HTTPException(status_code=400, detail="status must be one of: sent, opened, spending")
    return _get_service().update_status(lead_id, update)
