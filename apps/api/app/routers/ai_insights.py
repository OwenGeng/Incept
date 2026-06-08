import logging
import threading
import time

from fastapi import APIRouter, Depends

from app.models.ai_insights import AiInsightsPayload
from app.services.ai_insights import AiInsightsService
from app.services.auth import require_internal_key
from app.services.supply_smb_live import SupplySmbLiveService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/ai-insights",
    tags=["ai-insights"],
    dependencies=[Depends(require_internal_key)],
)

_supply_service: SupplySmbLiveService | None = None
_insights_service: AiInsightsService | None = None

# ── Leads cache (separate from the main BQ dataset cache) ─────────────────────
_leads_cache: list[dict] = []
_leads_cache_ts: float = 0.0
_leads_cache_lock = threading.Lock()
_LEADS_TTL = 3_600  # 1 hour — leads don't change minute-to-minute


def _get_supply() -> SupplySmbLiveService:
    global _supply_service
    if _supply_service is None:
        _supply_service = SupplySmbLiveService()
    return _supply_service


def _get_insights() -> AiInsightsService:
    global _insights_service
    if _insights_service is None:
        _insights_service = AiInsightsService()
    return _insights_service


def _get_leads(supply: SupplySmbLiveService) -> list[dict]:
    """Return cached leads, refreshing from BQ at most once per hour."""
    global _leads_cache, _leads_cache_ts
    now = time.monotonic()
    with _leads_cache_lock:
        if _leads_cache and now - _leads_cache_ts < _LEADS_TTL:
            logger.debug("[ai_insights] leads cache hit")
            return _leads_cache

    # Cache miss — query BQ
    try:
        fresh = supply.bigquery.list_leads()
        with _leads_cache_lock:
            _leads_cache = fresh
            _leads_cache_ts = time.monotonic()
        logger.info("[ai_insights] leads cache refreshed (%d rows)", len(fresh))
        return fresh
    except Exception as exc:
        logger.warning("[ai_insights] list_leads failed, using stale cache: %s", exc)
        with _leads_cache_lock:
            return _leads_cache  # return whatever we had (possibly [])


@router.get("", response_model=AiInsightsPayload)
async def get_ai_insights() -> AiInsightsPayload:
    """
    Returns real-data AI insights:
    - Rule-based insights from companies + leads
    - Live dataset cache status
    - Recent lead activity
    - Gemini-generated memory summary (cached inside AiInsightsService)
    """
    supply = _get_supply()
    insights = _get_insights()

    dataset = supply._get_dataset()          # fast — uses supply_smb_live cache
    companies = dataset["companies"]
    leads = _get_leads(supply)               # fast — cached 1 h

    return insights.get_payload(companies, leads)
