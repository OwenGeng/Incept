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
