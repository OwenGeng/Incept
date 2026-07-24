from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.services.auth import require_internal_key
from app.services.bigquery import BigQueryService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/cold-prospects",
    tags=["cold-prospects"],
    dependencies=[Depends(require_internal_key)],
)

_service: BigQueryService | None = None
_service_lock = threading.Lock()

BQ_PROJECT = "ads-bpd-guard-sandbox"
BQ_DATASET = "supply_smb"


def _get_bq() -> BigQueryService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = BigQueryService()
    return _service


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/overview")
async def get_cold_prospect_overview() -> dict[str, Any]:
    """
    Aggregate stats for the cold prospect pipeline.
    Compares the two most recent week_of values in prospect_snapshot for WoW.
    """
    bq = _get_bq()

    # ── summary counts from cold_prospect_app ──
    summary_sql = f"""
    SELECT
      COUNT(*)                                                   AS total_apps,
      COUNTIF(priority = 'P1')                                   AS p1_count,
      COUNTIF(priority = 'P2')                                   AS p2_count,
      COUNTIF(priority = 'P3')                                   AS p3_count,
      ROUND(AVG(IF(priority = 'P1', paid_frac, NULL)), 4)        AS avg_paid_frac_p1,
      ROUND(AVG(IF(priority = 'P2', paid_frac, NULL)), 4)        AS avg_paid_frac_p2,
      MAX(CAST(data_as_of AS STRING))                            AS data_as_of
    FROM `{BQ_PROJECT}.{BQ_DATASET}.cold_prospect_app`
    """

    company_sql = f"""
    SELECT COUNT(*) AS total_companies
    FROM `{BQ_PROJECT}.{BQ_DATASET}.cold_prospect_company`
    """

    # UA network counts across all apps
    ua_sql = f"""
    SELECT active_ua_networks
    FROM `{BQ_PROJECT}.{BQ_DATASET}.cold_prospect_app`
    WHERE active_ua_networks IS NOT NULL AND active_ua_networks != ''
    """

    # WoW: get the two most recent week_of dates
    wow_sql = f"""
    WITH weeks AS (
      SELECT DISTINCT week_of
      FROM `{BQ_PROJECT}.{BQ_DATASET}.prospect_snapshot`
      ORDER BY week_of DESC
      LIMIT 2
    ),
    ordered AS (
      SELECT week_of, ROW_NUMBER() OVER (ORDER BY week_of DESC) AS rn
      FROM weeks
    ),
    current_week AS (
      SELECT app_market_bundle
      FROM `{BQ_PROJECT}.{BQ_DATASET}.prospect_snapshot`
      WHERE week_of = (SELECT week_of FROM ordered WHERE rn = 1)
    ),
    prev_week AS (
      SELECT app_market_bundle
      FROM `{BQ_PROJECT}.{BQ_DATASET}.prospect_snapshot`
      WHERE week_of = (SELECT week_of FROM ordered WHERE rn = 2)
    )
    SELECT
      COUNT(DISTINCT c.app_market_bundle)                           AS wow_new,
      (SELECT COUNT(DISTINCT p.app_market_bundle)
       FROM prev_week p
       WHERE p.app_market_bundle NOT IN (SELECT app_market_bundle FROM current_week)) AS wow_dropped
    FROM current_week c
    WHERE c.app_market_bundle NOT IN (SELECT app_market_bundle FROM prev_week)
    """

    try:
        summary_rows = bq.query(summary_sql)
        summary = summary_rows[0] if summary_rows else {}

        company_rows = bq.query(company_sql)
        total_companies = company_rows[0]["total_companies"] if company_rows else 0

        ua_rows = bq.query(ua_sql)
        # Parse comma-separated network strings and aggregate
        network_counter: Counter = Counter()
        for row in ua_rows:
            nets = row.get("active_ua_networks") or ""
            for net in nets.split(","):
                net = net.strip()
                if net:
                    network_counter[net] += 1
        top_ua = [
            {"network": net, "app_count": count}
            for net, count in network_counter.most_common(10)
        ]

        # WoW (gracefully falls back to 0 if prospect_snapshot doesn't exist yet)
        try:
            wow_rows = bq.query(wow_sql)
            wow_new = int(wow_rows[0].get("wow_new", 0)) if wow_rows else 0
            wow_dropped = int(wow_rows[0].get("wow_dropped", 0)) if wow_rows else 0
        except Exception as exc:
            logger.warning("WoW query failed (prospect_snapshot may be empty): %s", exc)
            wow_new = 0
            wow_dropped = 0

        return {
            "total_apps": int(summary.get("total_apps", 0)),
            "total_companies": int(total_companies),
            "p1_count": int(summary.get("p1_count", 0)),
            "p2_count": int(summary.get("p2_count", 0)),
            "p3_count": int(summary.get("p3_count", 0)),
            "data_as_of": str(summary.get("data_as_of", "")),
            "wow_new": wow_new,
            "wow_dropped": wow_dropped,
            "avg_paid_frac_p1": float(summary.get("avg_paid_frac_p1") or 0),
            "avg_paid_frac_p2": float(summary.get("avg_paid_frac_p2") or 0),
            "top_ua_networks": top_ua,
        }
    except Exception as exc:
        logger.error("cold_prospect_overview failed: %s", exc)
        raise


# ── App list ─────────────────────────────────────────────────────────────────

@router.get("/apps")
async def get_cold_prospect_apps(
    priority: str = Query(default="all"),
    os: str = Query(default="all"),
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """
    Paginated list of cold prospect apps.
    Sorted by priority ASC (P1 first) then paid_frac DESC.
    """
    bq = _get_bq()

    conditions: list[str] = []
    if priority and priority != "all":
        safe_priority = priority.upper().replace("'", "")
        conditions.append(f"priority = '{safe_priority}'")
    if os and os != "all":
        safe_os = os.lower().replace("'", "")
        conditions.append(f"os = '{safe_os}'")
    if search:
        safe_search = search.replace("'", "\\'").replace("%", "\\%")
        conditions.append(
            f"(LOWER(app_name) LIKE LOWER('%{safe_search}%') "
            f"OR LOWER(company_name) LIKE LOWER('%{safe_search}%'))"
        )

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size

    count_sql = f"""
    SELECT COUNT(*) AS total
    FROM `{BQ_PROJECT}.{BQ_DATASET}.cold_prospect_app`
    {where_clause}
    """

    apps_sql = f"""
    SELECT
      app_market_bundle,
      app_name,
      company_name,
      os,
      priority,
      paid_frac,
      st_last_month_downloads,
      mau_ww,
      active_ua_networks,
      monetization_type,
      genre,
      hq_country
    FROM `{BQ_PROJECT}.{BQ_DATASET}.cold_prospect_app`
    {where_clause}
    ORDER BY
      CASE priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END ASC,
      paid_frac DESC
    LIMIT {page_size} OFFSET {offset}
    """

    count_rows = bq.query(count_sql)
    total = int(count_rows[0]["total"]) if count_rows else 0

    app_rows = bq.query(apps_sql)

    apps = [
        {
            "app_market_bundle": row.get("app_market_bundle"),
            "app_name": row.get("app_name"),
            "company_name": row.get("company_name"),
            "os": row.get("os"),
            "priority": row.get("priority"),
            "paid_frac": float(row["paid_frac"]) if row.get("paid_frac") is not None else None,
            "st_last_month_downloads": (
                int(row["st_last_month_downloads"])
                if row.get("st_last_month_downloads") is not None
                else None
            ),
            "mau_ww": int(row["mau_ww"]) if row.get("mau_ww") is not None else None,
            "active_ua_networks": row.get("active_ua_networks"),
            "monetization_type": row.get("monetization_type"),
            "genre": row.get("genre"),
            "hq_country": row.get("hq_country"),
        }
        for row in app_rows
    ]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "apps": apps,
    }
