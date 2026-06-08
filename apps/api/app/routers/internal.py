from fastapi import APIRouter, Depends, Query

from app.services.auth import require_internal_key
from app.services.bq_access import BQAccessService

# Admin email is hardcoded — always resolves to "admin" role without BQ lookup
ADMIN_EMAIL = "owen.geng@moloco.com"

router = APIRouter(prefix="/api/internal", tags=["internal"])

_service: BQAccessService | None = None


def _get_service() -> BQAccessService:
    global _service
    if _service is None:
        _service = BQAccessService()
    return _service


@router.get("/check-access", dependencies=[Depends(require_internal_key)])
def check_access(email: str = Query(...)) -> dict:
    # Hardcoded admin — never depends on BQ table
    if email.lower().strip() == ADMIN_EMAIL:
        return {"role": "admin", "allowed_projects": None}

    record = _get_service().get_user_record(email)
    if not record:
        # No record = no access; frontend will redirect to /unauthorized
        return {"role": None, "allowed_projects": None}

    return record
