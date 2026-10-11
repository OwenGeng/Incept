from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.video_studio.mcp import configured_video_studio_mcp_app
from app.video_studio.native_host import shutdown_host
from app.core.config import settings
from app.routers import (
    admin,
    feedback,
    health,
    incept,
    internal,
    kakao,
    video_studio,
    video_runtime,
    video_legacy,
)


_RETIRED_RELEASE_ROUTE_PREFIXES = (
    "/video-productions",
    "/video-production-capabilities",
)


def _remove_retired_release_routes(app: FastAPI) -> None:
    """Keep legacy implementation code importable without publishing it."""
    app.router.routes = [
        route
        for route in app.router.routes
        if not any(
            str(getattr(route, "path", "")).startswith(prefix)
            for prefix in _RETIRED_RELEASE_ROUTE_PREFIXES
        )
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        shutdown_host()


def create_app() -> FastAPI:
    app = FastAPI(
        title="LinglongLab API",
        version="0.1.0",
        description="Image and video production backend for LinglongLab.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(internal.router)
    app.include_router(admin.router)
    app.include_router(feedback.router)
    app.include_router(incept.router)
    app.include_router(kakao.router)
    app.include_router(video_studio.router)
    app.include_router(video_runtime.router)
    app.include_router(video_legacy.router)
    _remove_retired_release_routes(app)

    video_mcp_app = configured_video_studio_mcp_app()
    if video_mcp_app is not None:
        app.mount("/video-studio-mcp", video_mcp_app)

    # Serve LinglongLab static files (generated images & uploads)
    _static_root = Path(__file__).parent.parent / "static"
    _static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_static_root)), name="static")

    return app


app = create_app()
