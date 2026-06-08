from __future__ import annotations

from pydantic import BaseModel, EmailStr

# All valid roles in the system
VALID_ROLES = {
    "admin",
    "moloco_nbs",
    "moloco_ctv",
    "moloco_growth",
    "moloco_gtm",
    "moloco_supply",
    "agency",
    "user",  # legacy alias for moloco_nbs
}

AGENCY_COMPANIES = ["Madhouse", "Gatherone", "Bluevision", "Globaloneclick"]


class UserRecord(BaseModel):
    email: str
    role: str
    routing_bucket: str | None = None   # allowed_projects[0]
    agency_company: str | None = None   # allowed_projects[1]


class UserCreate(BaseModel):
    email: str
    role: str
    routing_bucket: str | None = None
    agency_company: str | None = None


class UserBulkCreate(BaseModel):
    """Add multiple users at once with the same role settings."""
    emails: list[str]
    role: str
    routing_bucket: str | None = None
    agency_company: str | None = None


class UserUpdate(BaseModel):
    role: str
    routing_bucket: str | None = None
    agency_company: str | None = None


class UserListPayload(BaseModel):
    users: list[UserRecord]
    total: int
