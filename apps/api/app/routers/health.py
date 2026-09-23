from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.incept.postgres import check_postgres_ready, postgres_enabled

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": settings.api_mode,
    }


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    if postgres_enabled() and not check_postgres_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is unavailable",
        )
    return {"status": "ok", "database": "postgres" if postgres_enabled() else "sqlite"}
