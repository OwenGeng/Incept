from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_internal_key(x_internal_api_key: str = Header(default="")) -> None:
    if not settings.internal_api_key:
        return
    if x_internal_api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )


# ── Role context ───────────────────────────────────────────────────────────────

# Roles that have unrestricted access to Supply SMB data
NBS_ROLES = {"admin", "moloco_nbs", "user"}
# All roles with any Supply SMB access
SUPPLY_ROLES = NBS_ROLES | {"agency"}


@dataclass
class RoleContext:
    """Extracted from request headers by get_role_context()."""
    role: str
    email: str
    # For agency: the routing bucket they are restricted to (e.g. "Qipeng").
    # None means unrestricted.
    allowed_routing: str | None

    def is_agency(self) -> bool:
        return self.role == "agency"

    def is_nbs_or_admin(self) -> bool:
        return self.role in NBS_ROLES


def get_role_context(
    x_user_role: str = Header(default=""),
    x_user_email: str = Header(default=""),
    x_allowed_routing: str = Header(default=""),
) -> RoleContext:
    routing = x_allowed_routing.strip() or None
    return RoleContext(
        role=x_user_role.strip(),
        email=x_user_email.strip(),
        allowed_routing=routing,
    )
