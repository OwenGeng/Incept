import logging
import os

from fastapi import Header, HTTPException, status

from app.incept.config import get_settings
from app.incept.models import Role, User

logger = logging.getLogger(__name__)

ROLE_RANK = {
    Role.user: 1,
    Role.manager: 2,
    Role.admin: 3,
}

_bq_service = None


def _get_bq_service():
    global _bq_service
    if _bq_service is not None:
        return _bq_service
    try:
        from app.services.bq_access import BQAccessService
        _bq_service = BQAccessService()
    except Exception:
        pass
    return _bq_service


def _strip_google_identity_prefix(value: str) -> str:
    return value.split(":", 1)[1] if ":" in value else value


def _name_from_email(email: str) -> str:
    local_part = email.split("@", 1)[0]
    return " ".join(part.capitalize() for part in local_part.replace(".", " ").split())


def _role_for_email(email: str) -> Role:
    settings = get_settings()
    normalized = email.lower()

    # Env var overrides — always checked first (fast, works without BQ)
    if normalized in settings.admin_emails:
        return Role.admin
    if normalized in settings.manager_emails:
        return Role.manager

    # BQ config.users table — authoritative source for cloud deployments
    try:
        svc = _get_bq_service()
        if svc is not None:
            record = svc.get_user_record(normalized)
            if record:
                bq_role = record.get("role", "")
                if bq_role in (r.value for r in Role):
                    return Role(bq_role)
    except Exception:
        logger.debug("BQ role lookup failed for %s, defaulting to user", normalized)

    return Role.user


def _require_allowed_domain(email: str) -> None:
    settings = get_settings()
    if not email.lower().endswith(f"@{settings.allowed_email_domain}"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only @{settings.allowed_email_domain} accounts can access LinglongLab",
        )


def _verify_iap_jwt(assertion: str | None) -> None:
    settings = get_settings()
    if not settings.iap_jwt_audience:
        return
    if not assertion:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing IAP JWT assertion",
        )

    try:
        from google.auth.transport import requests
        from google.oauth2 import id_token

        id_token.verify_token(
            assertion,
            requests.Request(),
            audience=settings.iap_jwt_audience,
            certs_url="https://www.gstatic.com/iap/verify/public_key",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid IAP JWT assertion",
        ) from exc


def get_current_user(
    x_internal_api_key: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
    x_incept_user_id: str | None = Header(default=None),
    x_incept_user_email: str | None = Header(default=None),
    x_incept_user_name: str | None = Header(default=None),
    x_incept_user_role: str | None = Header(default=None),
    x_incept_user_team: str | None = Header(default=None),
    x_goog_authenticated_user_email: str | None = Header(default=None),
    x_goog_authenticated_user_id: str | None = Header(default=None),
    x_goog_iap_jwt_assertion: str | None = Header(default=None),
) -> User:
    """Resolve the current user.

    Priority:
      1. X-Internal-API-Key  — trusted call from the Next.js proxy (NBSpark portal)
      2. Google IAP JWT      — production Cloud Run with IAP enabled
      3. Dev mode            — local development only, no real auth required

    Anything that falls through all three (e.g. an unauthenticated request
    hitting the Cloud Run URL directly) is rejected. There is no default user.
    """

    settings = get_settings()

    # ── 1. Internal API key (Next.js proxy) ───────────────────────────────────
    expected_key = os.getenv("INCEPT_INTERNAL_API_KEY", "")
    if expected_key and x_internal_api_key == expected_key:
        email = (x_user_email or "").lower()
        if email:
            _require_allowed_domain(email)
        if x_user_role in (r.value for r in Role):
            role = Role(x_user_role)
        else:
            role = _role_for_email(email) if email else Role.user
        return User(
            id=email or "service",
            name=_name_from_email(email) if email else "NBSpark Service",
            email=email,
            role=role,
            team="nbs",
        )

    # ── 2. Google IAP ─────────────────────────────────────────────────────────
    if settings.auth_mode == "iap":
        _verify_iap_jwt(x_goog_iap_jwt_assertion)
        if not x_goog_authenticated_user_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing IAP authenticated user email",
            )

        email = _strip_google_identity_prefix(x_goog_authenticated_user_email).lower()
        _require_allowed_domain(email)
        user_id = (
            _strip_google_identity_prefix(x_goog_authenticated_user_id)
            if x_goog_authenticated_user_id
            else email
        )
        return User(
            id=user_id,
            name=_name_from_email(email),
            email=email,
            role=_role_for_email(email),
            team="Moloco",
        )

    # ── 3. Dev mode (local development only) ───────────────────────────────────
    if settings.auth_mode == "dev" and settings.environment != "production":
        user_id = x_incept_user_id if isinstance(x_incept_user_id, str) else None
        email = x_incept_user_email if isinstance(x_incept_user_email, str) else None
        name = x_incept_user_name if isinstance(x_incept_user_name, str) else None
        role_value = x_incept_user_role if isinstance(x_incept_user_role, str) else None
        team = x_incept_user_team if isinstance(x_incept_user_team, str) else None

        if email:
            _require_allowed_domain(email)

        role = Role(role_value or Role.manager.value)
        return User(
            id=user_id or "usr_jane",
            name=name or "Jane Cooper",
            email=email or "jane@moloco.com",
            role=role,
            team=team or "IM GM",
        )

    # ── 4. Nothing matched — fail closed ───────────────────────────────────────
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


def require_role(user: User, minimum_role: Role) -> None:
    if ROLE_RANK[user.role] < ROLE_RANK[minimum_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{minimum_role.value} role required",
        )
