import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import admin, agent, ai_insights, cold_prospects, feedback, health, incept, internal, kakao, leads, supply_smb

logger = logging.getLogger(__name__)


def _fill_all_caches() -> None:
    """
    Pull every BQ dataset into the in-memory cache.
    Safe to call from any thread; individual BQ errors are caught per-dataset.
    """
    try:
        from app.services.supply_smb_live import DATASET_META, SupplySmbLiveService

        svc = SupplySmbLiveService()

        logger.info("[cache] Warming main dataset (List 4/5/6)…")
        svc._get_dataset()
        logger.info("[cache] Main dataset ready.")

        for key in DATASET_META:
            try:
                logger.info(f"[cache] Warming dataset {key}…")
                svc._get_custom_dataset_rows(key)
                logger.info(f"[cache] Dataset {key} ready.")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[cache] Failed to warm {key}: {exc}")

        logger.info("[cache] All datasets warm ✓")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[cache] Warm cycle aborted: {exc}")


def _prewarm_caches() -> None:
    """Startup thread: wait for uvicorn to bind, then fill caches."""
    time.sleep(4)
    logger.info("[prewarm] Starting initial cache warm…")
    _fill_all_caches()


_REFRESH_INTERVAL_SECONDS = 3 * 3600  # 3 h — refresh before 4-h TTL expires


def _periodic_refresh_loop() -> None:
    """
    Background thread: re-warm all BQ caches every 3 hours so users never
    hit a cold cache during the working day. Runs forever (daemon thread).
    """
    while True:
        time.sleep(_REFRESH_INTERVAL_SECONDS)
        logger.info("[refresh] Periodic cache refresh starting…")
        _fill_all_caches()
        logger.info("[refresh] Periodic cache refresh complete.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Initial warm — runs once shortly after startup
    t_warm = threading.Thread(target=_prewarm_caches, daemon=True, name="cache-prewarm")
    t_warm.start()
    # Periodic refresh — keeps cache alive every 3 h
    t_refresh = threading.Thread(target=_periodic_refresh_loop, daemon=True, name="cache-refresh")
    t_refresh.start()
    yield
    # Daemon threads stop automatically with the process


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
    app.include_router(supply_smb.router)
    app.include_router(cold_prospects.router)
    app.include_router(leads.router)
    app.include_router(ai_insights.router)
    app.include_router(agent.router)
    app.include_router(feedback.router)
    app.include_router(incept.router)
    app.include_router(kakao.router)

    # Serve Incept static files (generated images & uploads)
    _static_root = Path(__file__).parent.parent / "static"
    _static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_static_root)), name="static")

    return app


app = create_app()

