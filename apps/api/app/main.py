from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.video_studio.mcp import configured_video_studio_mcp_app
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="InterSight API",
        version="0.1.0",
        description="Supply SMB and future CTV backend for the InterSight operating system.",
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

    video_mcp_app = configured_video_studio_mcp_app()
    if video_mcp_app is not None:
        app.mount("/video-studio-mcp", video_mcp_app)

    # Serve Incept static files (generated images & uploads)
    _static_root = Path(__file__).parent.parent / "static"
    _static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_static_root)), name="static")

    return app


app = create_app()
