import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.ai_video.main import app as ai_video_app, initialize_ai_video_module
from app.core.config import settings
from app.routers import admin, feedback, health, incept, internal, kakao

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the mounted AI Video module in this FastAPI process. Its
    # persistence uses the same Cloud SQL credential contract as Incept.
    await initialize_ai_video_module()
    workflow_worker_started = False
    try:
        # Studio Workflows belongs to the deferred Video Production product.
        # Do not start its worker in the Image + AI Video production profile.
        if settings.video_production_enabled:
            from app.incept.workflow_worker import start_workflow_worker

            start_workflow_worker()
            workflow_worker_started = True

        mcp_server = getattr(app.state, "video_production_mcp_server", None)
        if mcp_server is not None:
            # Mounted Starlette applications do not automatically own their child
            # lifespan. Run the MCP session manager from the API lifespan so the
            # Streamable HTTP transport has its task group before the first call.
            async with mcp_server.session_manager.run():
                yield
        else:
            yield
    finally:
        if workflow_worker_started:
            from app.incept.workflow_worker import stop_workflow_worker

            stop_workflow_worker()


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

    @app.middleware("http")
    async def hide_deferred_product_apis(request: Request, call_next):
        """Return a neutral 404 for product APIs excluded from this release."""
        path = request.url.path
        video_production_paths = ("/video-production", "/video-productions")
        gaming_playable_paths = ("/playable-projects", "/playable-templates")

        if not settings.video_production_enabled and (
            path == "/video-production-capabilities"
            or any(path == prefix or path.startswith(f"{prefix}/") for prefix in video_production_paths)
        ):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        if not settings.gaming_playable_enabled and any(
            path == prefix or path.startswith(f"{prefix}/") for prefix in gaming_playable_paths
        ):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(internal.router)
    app.include_router(admin.router)
    app.include_router(feedback.router)
    app.include_router(incept.router)
    app.include_router(kakao.router)

    # The legacy workflow is now an in-process Linglong Lab module. Mounting
    # preserves its generated-client paths and response envelope without a
    # second Cloud Run service or backend URL.
    app.mount("/ai-video", ai_video_app)

    # The automation endpoint is fail-closed: without an explicit public
    # resource URL and opaque service principals, no MCP route exists at all.
    # It is mounted separately from browser auth and uses bearer credentials.
    if settings.video_production_enabled:
        from app.incept.video_production_mcp import configured_video_production_mcp_server

        video_production_mcp_server = configured_video_production_mcp_server()
        if video_production_mcp_server is not None:
            app.state.video_production_mcp_server = video_production_mcp_server
            app.mount("/video-production/mcp", video_production_mcp_server.streamable_http_app())

    # Serve Incept static files (generated images & uploads)
    _static_root = Path(__file__).parent.parent / "static"
    _static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_static_root)), name="static")

    return app


app = create_app()
