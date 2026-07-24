"""
Admin-only endpoints for user management.
All routes require the internal API key + admin role.
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)

from app.incept.auth import get_current_user, require_role
from app.incept.models import Role, User
from app.models.admin import (
    VALID_ROLES,
    UserBulkCreate,
    UserCreate,
    UserListPayload,
    UserRecord,
    UserUpdate,
)
from app.services.bq_access import BQAccessService

ADMIN_EMAIL = os.getenv("INCEPT_ADMIN_EMAIL", "owen.geng@moloco.com")

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
)

_service: BQAccessService | None = None


def _get_service() -> BQAccessService:
    global _service
    if _service is None:
        _service = BQAccessService()
    return _service


def _require_admin(user: User = Depends(get_current_user)) -> User:
    require_role(user, Role.admin)
    return user


def _validate_role(role: str) -> None:
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{role}'. Must be one of: {sorted(VALID_ROLES)}",
        )


def _row_to_record(row: dict) -> UserRecord:
    return UserRecord(
        email=row["email"],
        role=row["role"],
        routing_bucket=row.get("routing_bucket"),
        agency_company=row.get("agency_company"),
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/users", response_model=UserListPayload, dependencies=[Depends(_require_admin)])
def list_users() -> UserListPayload:
    try:
        rows = _get_service().list_users()
        records = [_row_to_record(r) for r in rows]
        return UserListPayload(users=records, total=len(records))
    except Exception as exc:
        logger.error("[admin] list_users BQ query failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"User list unavailable — BigQuery query failed: {exc}. "
                "Check BQ_WRITE_PROJECT / GCP_PROJECT_DEPLOY env vars and that "
                "the `Incept.users` table exists with columns (email, role, allowed_projects ARRAY<STRING>)."
            ),
        ) from exc


@router.post("/users", response_model=UserRecord, status_code=201, dependencies=[Depends(_require_admin)])
def add_user(payload: UserCreate) -> UserRecord:
    _validate_role(payload.role)
    if payload.email == ADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="Cannot modify the admin account.")
    _get_service().upsert_user(
        email=payload.email,
        role=payload.role,
        routing_bucket=payload.routing_bucket,
        agency_company=payload.agency_company,
    )
    return UserRecord(
        email=payload.email,
        role=payload.role,
        routing_bucket=payload.routing_bucket,
        agency_company=payload.agency_company,
    )


@router.post("/users/bulk", response_model=dict, status_code=201, dependencies=[Depends(_require_admin)])
def bulk_add_users(payload: UserBulkCreate) -> dict:
    _validate_role(payload.role)
    emails = [e.strip().lower() for e in payload.emails if e.strip() and e.strip() != ADMIN_EMAIL]
    if not emails:
        raise HTTPException(status_code=400, detail="No valid emails provided.")
    count = _get_service().bulk_upsert_users(
        emails=emails,
        role=payload.role,
        routing_bucket=payload.routing_bucket,
        agency_company=payload.agency_company,
    )
    return {"added": count, "emails": emails}


@router.patch("/users/{email:path}", response_model=UserRecord, dependencies=[Depends(_require_admin)])
def update_user(email: str, payload: UserUpdate) -> UserRecord:
    _validate_role(payload.role)
    if email == ADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="Cannot modify the admin account.")
    _get_service().upsert_user(
        email=email,
        role=payload.role,
        routing_bucket=payload.routing_bucket,
        agency_company=payload.agency_company,
    )
    return UserRecord(
        email=email,
        role=payload.role,
        routing_bucket=payload.routing_bucket,
        agency_company=payload.agency_company,
    )


@router.delete("/users/{email:path}", status_code=204, dependencies=[Depends(_require_admin)])
def delete_user(email: str) -> None:
    if email == ADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="Cannot delete the admin account.")
    _get_service().delete_user(email)
