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


MOLOCO_DOMAIN = "moloco.com"


@router.get("/check-access", dependencies=[Depends(require_internal_key)])
def check_access(email: str = Query(...)) -> dict:
    email = email.lower().strip()

    # Hardcoded admin — never depends on BQ table
    if email == ADMIN_EMAIL:
        return {"role": "admin", "allowed_projects": None}

    # BQ explicit record takes priority (allows per-user role overrides)
    record = _get_service().get_user_record(email)
    if record and record.get("role"):
        return record

    # All @moloco.com accounts auto-granted admin access
    if email.endswith(f"@{MOLOCO_DOMAIN}"):
        return {"role": "admin", "allowed_projects": None}

    # Non-moloco without explicit record — no access
    return {"role": None, "allowed_projects": None}
