#!/usr/bin/env python3
"""
SensorTower → BigQuery weekly pipeline.
9 tables, WRITE_TRUNCATE (full refresh) into ads-bpd-guard-sandbox.sensortower_new.

App ID source: ads-bpd-guard-china.sensortower.app_iq_v3 (unified IDs)
NOTE: fact_app_basis_v3 already contains daily.channel.paid_ads / download data.
      This pipeline fills the gaps: SDK tags, network SOV, creative count,
      metadata (publisher, app name), and advertiser rank.

Required env vars:
  SENSORTOWER_API_KEY          SensorTower API token
  (fallback: SENSOR_TOWER_API_TOKEN)

Optional env vars:
  ST_BQ_DATASET                default: ads-bpd-guard-sandbox.sensortower_new
  ST_APP_IDS_QUERY             override default source query
  ST_LOOKBACK_DAYS             default: 90
  ST_RANK_PAGES                leaderboard pages to fetch per country (default: 4 = 1000 apps)
  ST_AU_SAMPLE                 max apps for active_users lookup, default: 2000 (batch=4, ~13 min)

Run locally:
  cd apps/api && source venv/bin/activate
  python -m app.incept.sensortower_pipeline

Confirmed API behaviors (from probe_st.py 2026-06-21):
  - All unified endpoints require app_id_type=unified
  - downloads_by_sources: paid_abs, paid_frac, organic_abs, organic_frac, etc.
  - network_analysis: per app+country+network+date, field "sov"
  - top_apps/search: returns {page, rank, sov}; no "WW" country, use specific ISO codes
  - tags_for_apps: requires platform-specific IDs (iOS int or Android package); not unified
  - creatives: requires "networks" param listing specific networks
"""

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Any

import httpx
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField as F

# ─── Configuration ────────────────────────────────────────────────────────────

DATASET       = os.getenv("ST_BQ_DATASET", "ads-bpd-guard-sandbox.sensortower_new")
ST_BASE       = "https://api.sensortower.com"
ST_TOKEN      = os.environ.get("SENSORTOWER_API_KEY") or os.environ["SENSOR_TOWER_API_TOKEN"]
LOOKBACK_DAYS = int(os.getenv("ST_LOOKBACK_DAYS", "90"))
RANK_SAMPLE   = int(os.getenv("ST_RANK_SAMPLE", "300"))   # legacy, unused
RANK_PAGES    = int(os.getenv("ST_RANK_PAGES", "4"))       # leaderboard pages (×250 apps each)
# Per-app detail endpoints (download_channels, sdk_tags, downloads_monthly) are
# expensive: only run for the top N apps by download order from APP_IDS_QUERY.
DETAIL_SAMPLE = int(os.getenv("ST_DETAIL_SAMPLE", "5000"))
# Active users uses batch=4 (API limit); cap separately to avoid 30+ min runtime.
AU_SAMPLE     = int(os.getenv("ST_AU_SAMPLE", "2000"))
RATE_RPS      = 5

# SDK IDs for /v1/facets/metrics?sdk_list_of_apps (confirmed via /v1/sdk/summary_metrics scan)
# Approach: per-SDK call returns ALL apps with that SDK → join with our app list
SDK_IDS = {
    # MMP / Attribution
    60100000000007: "Adjust",
    60100000000008: "AppsFlyer",
    60100000000494: "Kochava",
    60100000000714: "Singular",
    60100000000241: "Branch",
    60100000000776: "Tenjin",
    # Ad networks / mediation
    60100000000049: "Admob",
    60100000000182: "Applovin",
    60100000001883: "AppLovin MAX",
    60100000000456: "ironSource",
    60100000001683: "Mintegral",
    60100000000821: "Vungle",
    60100000000343: "Facebook Audience Network",
    60100000002022: "Moloco Ads",
    # Analytics
    60100000000400: "Google Firebase",
}

APP_IDS_QUERY = os.getenv(
    "ST_APP_IDS_QUERY",
    """
    SELECT v.app_id
    FROM `ads-bpd-guard-china.sensortower.app_iq_v3` v
    JOIN (
      SELECT unified_app_id, SUM(daily.download.`all`) AS total_dl
      FROM `ads-bpd-guard-china.sensortower.fact_app_basis_v3`
      WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      GROUP BY 1
      HAVING total_dl > 5000
    ) d ON v.app_id = d.unified_app_id
    GROUP BY v.app_id, d.total_dl
    ORDER BY d.total_dl DESC
    """,
)

# Countries for the advertiser leaderboard — passed as combined `countries[]` array (single query)
# Americas + APAC + Europe + Middle East + RU
RANK_LEADERBOARD_COUNTRIES = [
    # Americas
    "US", "CA", "BR",
    # APAC
    "JP", "KR", "AU", "TW", "SG",
    # Europe
    "GB", "DE", "FR", "IT", "ES", "NL", "SE", "NO", "PL", "RU",
    # Middle East
    "AE", "SA", "TR", "IL",
]

# Networks to query for creatives (all major DSPs)
CREATIVE_NETWORKS = (
    "Facebook,Instagram,TikTok,Applovin,Admob,Unity,Mintegral,"
    "Moloco,Pangle,Vungle,Meta Audience Network,Snapchat"
)

_today   = date.today()
_start   = (_today - timedelta(days=LOOKBACK_DAYS)).replace(day=1)
_fetched = _today.isoformat()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─── BigQuery schemas ─────────────────────────────────────────────────────────

SCHEMAS: dict[str, list[F]] = {
    # 1. Unified app metadata — minimal, used to resolve platform IDs for downstream steps
    "st_app_metadata": [
        F("unified_app_id",       "STRING"),
        F("name",                 "STRING"),
        F("canonical_app_id",     "STRING"),
        F("app_id_ios",           "STRING"),
        F("app_id_android",       "STRING"),
        F("unified_publisher_id", "STRING"),
        F("fetched_at",           "DATE"),
    ],
    # 2. Unified ↔ platform ID mapping — master lookup table for all joins
    #    bundle_id_ios / bundle_id_android populated after st_app_overview is fetched
    "st_unified_id_map": [
        F("unified_app_id",   "STRING"),
        F("app_id_ios",       "STRING"),   # numeric App Store ID
        F("app_id_android",   "STRING"),   # Android package name (= bundle_id_android)
        F("bundle_id_ios",    "STRING"),   # iOS bundle identifier e.g. com.facebook.Facebook
        F("bundle_id_android","STRING"),   # same as app_id_android, duplicated for easy lookup
        F("app_name",         "STRING"),
        F("fetched_at",       "DATE"),
    ],
    # 2b. Full app overview from /v1/{os}/apps?include_sdk_data=true
    #     One row per (unified_app_id, platform). ~850 calls for 63K apps, ~3 min.
    "st_app_overview": [
        F("unified_app_id",       "STRING"),
        F("platform_app_id",      "STRING"),
        F("platform",             "STRING"),
        F("name",                 "STRING"),
        F("bundle_id",            "STRING"),
        F("publisher_name",       "STRING"),
        F("publisher_id",         "STRING"),
        F("publisher_country",    "STRING"),
        F("publisher_email",      "STRING"),
        F("active",               "BOOL"),
        F("release_date",         "DATE"),
        F("updated_date",         "DATE"),
        F("version",              "STRING"),
        F("rating",               "FLOAT64"),
        F("global_rating_count",  "INTEGER"),
        F("rating_count",         "INTEGER"),
        F("in_app_purchases",     "BOOL"),
        F("price",                "FLOAT64"),
        F("content_rating",       "STRING"),
        F("top_countries",        "STRING"),   # JSON ["US","VN","BR"]
        F("categories",           "STRING"),   # JSON [6005]
        F("supported_languages",  "STRING"),   # JSON ["en","zh",...]
        F("last_month_downloads", "INTEGER"),
        F("last_month_revenue",   "INTEGER"),  # cents
        F("sdk_insights_supported", "BOOL"),
        F("fetched_at",           "DATE"),
    ],
    # 3. Ad network share-of-voice time series
    #    Fields confirmed: app_id, country, network, date, sov
    "st_network_sov": [
        F("unified_app_id", "STRING"),
        F("country",        "STRING"),
        F("network",        "STRING"),
        F("period_date",    "DATE"),
        F("sov",            "FLOAT64"),
        F("fetched_at",     "DATE"),
    ],
    # 4. Paid vs organic download channel breakdown
    #    Fields confirmed: paid_abs, paid_frac, organic_abs, organic_frac,
    #                      paid_search_abs, paid_search_frac, browser_abs, browser_frac
    "st_download_channels": [
        F("unified_app_id",    "STRING"),
        F("period_date",       "DATE"),
        F("paid_abs",          "INTEGER"),
        F("organic_abs",       "INTEGER"),
        F("paid_search_abs",   "INTEGER"),
        F("browser_abs",       "INTEGER"),
        F("paid_frac",         "FLOAT64"),
        F("organic_frac",      "FLOAT64"),
        F("paid_search_frac",  "FLOAT64"),
        F("browser_frac",      "FLOAT64"),
        F("fetched_at",        "DATE"),
    ],
    # 5. SDK integration data — app-centric via /v1/{os}/apps?include_sdk_data=true
    #    Returns ALL SDKs per app (not just our 15 tracked ones).
    #    Covers both sdks_installed and sdks_uninstalled.
    #    100 apps/call → ~50 iOS + ~50 Android = ~100 calls for DETAIL_SAMPLE=5000.
    "st_sdk_tags": [
        F("unified_app_id",  "STRING"),
        F("platform",        "STRING"),   # ios | android
        F("sdk_id",          "INTEGER"),
        F("sdk_name",        "STRING"),
        F("company_name",    "STRING"),
        F("sdk_types",       "STRING"),   # JSON array string, e.g. '["Attribution","MMP"]'
        F("apps_installed",  "INTEGER"),  # how many apps globally have this SDK
        F("install_date",    "DATE"),
        F("uninstall_date",  "DATE"),     # null = currently installed
        F("days_installed",  "INTEGER"),
        F("sdk_status",      "STRING"),   # "installed" | "uninstalled"
        F("fetched_at",      "DATE"),
    ],
    # 6. Creative count per app — UA activity proxy
    #    fields confirmed: count, available_networks[], ad_units[]
    "st_creatives_count": [
        F("unified_app_id",      "STRING"),
        F("period_start",        "DATE"),
        F("period_end",          "DATE"),
        F("creative_count",      "INTEGER"),
        F("available_network_count", "INTEGER"),
        F("available_networks",  "STRING"),  # JSON array string
        F("fetched_at",          "DATE"),
    ],
    # 7. Monthly download + revenue (ST API — complements fact_app_basis_v3)
    "st_downloads_monthly": [
        F("unified_app_id", "STRING"),
        F("period_date",    "DATE"),
        F("downloads",      "INTEGER"),
        F("revenue_usd",    "FLOAT64"),
        F("fetched_at",     "DATE"),
    ],
    # 8. DAU/MAU engagement metrics
    "st_active_users": [
        F("unified_app_id", "STRING"),
        F("country",        "STRING"),
        F("period_date",    "DATE"),
        F("granularity",    "STRING"),
        F("active_users",   "INTEGER"),
        F("fetched_at",     "DATE"),
    ],
    # 9. Advertiser leaderboard — global top advertisers by SOV (not per-app lookup)
    #    Fields from /v1/unified/ad_intel/top_apps + custom_tags
    "st_advertiser_rank": [
        F("unified_app_id",            "STRING"),
        F("app_name",                  "STRING"),
        F("publisher_name",            "STRING"),
        F("rank",                      "INTEGER"),
        F("sov",                       "FLOAT64"),
        F("prev_sov",                  "FLOAT64"),
        F("sov_delta",                 "FLOAT64"),
        F("downloads_30d_ww",          "INTEGER"),
        F("most_popular_country",      "STRING"),
        F("advertised_on_any_network", "STRING"),
        F("contains_ads",              "STRING"),
        F("country",                   "STRING"),
        F("network",                   "STRING"),
        F("period_date",               "DATE"),
        F("fetched_at",                "DATE"),
    ],
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


async def _get(
    client: httpx.AsyncClient,
    path: str,
    params: dict,
    retries: int = 5,
    total_timeout: float = 90.0,
) -> Any:
    p = dict(params, auth_token=ST_TOKEN)
    backoff = 1.0
    for attempt in range(retries):
        try:
            resp = await asyncio.wait_for(
                client.get(path, params=p),
                timeout=total_timeout,
            )
        except asyncio.TimeoutError:
            log.warning("ST %s → TotalTimeout(%.0fs), retry %d/%d", path, total_timeout, attempt + 1, retries)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 16.0)
            continue
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
            log.warning("ST %s → %s, retry %d/%d", path, exc.__class__.__name__, attempt + 1, retries)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 16.0)
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            log.warning("ST %s → %d, retry %d/%d", path, resp.status_code, attempt + 1, retries)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 16.0)
            continue
        if not resp.is_success:
            log.warning("ST %s → %d: %s", path, resp.status_code, resp.text[:200])
            return None
        return resp.json()
    log.error("ST %s → exhausted %d retries, skipping", path, retries)
    return None


async def _sleep():
    await asyncio.sleep(1.0 / RATE_RPS)


# ─── BQ helpers ───────────────────────────────────────────────────────────────

def bq_ensure_tables(bq: bigquery.Client) -> None:
    project, dataset_id = DATASET.split(".", 1)
    ds = bigquery.Dataset(f"{project}.{dataset_id}")
    ds.location = "US"
    bq.create_dataset(ds, exists_ok=True)
    for table_id, schema in SCHEMAS.items():
        tbl = bigquery.Table(f"{DATASET}.{table_id}", schema=schema)
        bq.create_table(tbl, exists_ok=True)
    log.info("BQ tables ready in %s", DATASET)


def bq_write(bq: bigquery.Client, table_id: str, rows: list[dict]) -> None:
    if not rows:
        log.warning("No rows for %s — skipping", table_id)
        return
    job = bq.load_table_from_json(
        rows,
        f"{DATASET}.{table_id}",
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMAS[table_id],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        ),
    )
    job.result()
    log.info("→ %s: %d rows", table_id, len(rows))


def bq_load_app_ids(bq: bigquery.Client) -> list[str]:
    rows = list(bq.query(APP_IDS_QUERY).result())
    ids = [str(r["app_id"]) for r in rows]
    log.info("Loaded %d unified app_ids", len(ids))
    return ids


# ─── Fetchers ─────────────────────────────────────────────────────────────────

async def fetch_app_metadata(client: httpx.AsyncClient, unified_ids: list[str]) -> list[dict]:
    """
    Returns metadata rows AND a side-channel dict for resolving platform IDs.
    confirmed response: apps[].{unified_app_id, name, canonical_app_id,
                                 itunes_apps[].app_id, android_apps[].app_id,
                                 unified_publisher_ids[]}
    """
    rows = []
    for batch in _chunks(unified_ids, 100):
        data = await _get(client, "/v1/unified/apps", {
            "app_ids":     ",".join(batch),
            "app_id_type": "unified",
            "country":     "US",
        })
        for app in ((data or {}).get("apps") or []):
            uid       = str(app.get("unified_app_id") or "")
            ios_ids   = app.get("itunes_apps") or []
            android_ids = app.get("android_apps") or []
            rows.append({
                "unified_app_id":      uid,
                "name":                app.get("name") or "",
                "canonical_app_id":    str(app.get("canonical_app_id") or ""),
                "app_id_ios":          str(ios_ids[0]["app_id"]) if ios_ids else "",
                "app_id_android":      str(android_ids[0]["app_id"]) if android_ids else "",
                "unified_publisher_id": str((app.get("unified_publisher_ids") or [""])[0]),
                "fetched_at":          _fetched,
            })
        await _sleep()
    return rows


def build_unified_map(
    meta_rows: list[dict],
    overview_rows: list[dict] | None = None,
) -> list[dict]:
    # Build bundle_id lookups from overview (iOS bundle_id isn't in unified metadata)
    ios_bundle:     dict[str, str] = {}   # unified_app_id → bundle_id_ios
    android_bundle: dict[str, str] = {}   # unified_app_id → bundle_id_android
    for r in (overview_rows or []):
        uid = r["unified_app_id"]
        bid = r.get("bundle_id") or ""
        if r.get("platform") == "ios" and bid:
            ios_bundle[uid] = bid
        elif r.get("platform") == "android" and bid:
            android_bundle[uid] = bid

    seen: set[str] = set()
    rows = []
    for r in meta_rows:
        uid = r["unified_app_id"]
        if uid and uid not in seen:
            seen.add(uid)
            android_pkg = r.get("app_id_android") or ""
            rows.append({
                "unified_app_id":    uid,
                "app_id_ios":        r.get("app_id_ios") or "",
                "app_id_android":    android_pkg,
                "bundle_id_ios":     ios_bundle.get(uid) or "",
                "bundle_id_android": android_bundle.get(uid) or android_pkg,
                "app_name":          r.get("name") or "",
                "fetched_at":        _fetched,
            })
    return rows


async def fetch_app_overview_and_sdk(
    client: httpx.AsyncClient,
    meta_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Calls /v1/{os}/apps?include_sdk_data=true for both iOS and Android.
    Returns (overview_rows, sdk_rows) — two tables from one set of API calls.
    100 apps/call → ~850 total calls for 63K apps (~3 min at 5 RPS).
    """
    import json as _json

    ios_map:     dict[str, str] = {}
    android_map: dict[str, str] = {}
    for r in meta_rows:
        uid = r["unified_app_id"]
        if r.get("app_id_ios"):
            ios_map[r["app_id_ios"]] = uid
        if r.get("app_id_android"):
            android_map[r["app_id_android"]] = uid

    overview_rows: list[dict] = []
    sdk_rows:      list[dict] = []

    def _parse_app(app: dict, platform: str, uid: str) -> None:
        pid = str(app.get("app_id") or "")
        hd  = app.get("humanized_worldwide_last_month_downloads") or {}
        hr  = app.get("humanized_worldwide_last_month_revenue") or {}
        overview_rows.append({
            "unified_app_id":       uid,
            "platform_app_id":      pid,
            "platform":             platform,
            "name":                 str(app.get("name") or ""),
            "bundle_id":            str(app.get("bundle_id") or ""),
            "publisher_name":       str(app.get("publisher_name") or ""),
            "publisher_id":         str(app.get("publisher_id") or ""),
            "publisher_country":    str(app.get("publisher_country") or ""),
            "publisher_email":      str(app.get("publisher_email") or "") or None,
            "active":               bool(app.get("active")),
            "release_date":         (app.get("release_date") or "")[:10] or None,
            "updated_date":         (app.get("updated_date") or "")[:10] or None,
            "version":              str(app.get("version") or "") or None,
            "rating":               float(app.get("rating") or 0.0),
            "global_rating_count":  int(app.get("global_rating_count") or 0),
            "rating_count":         int(app.get("rating_count") or 0),
            "in_app_purchases":     bool(app.get("in_app_purchases")),
            "price":                float(app.get("price") or 0.0),
            "content_rating":       str(app.get("content_rating") or "") or None,
            "top_countries":        _json.dumps(app.get("top_countries") or []),
            "categories":           _json.dumps(app.get("categories") or []),
            "supported_languages":  _json.dumps(app.get("supported_languages") or []),
            "last_month_downloads": int(hd.get("downloads") or 0) or None,
            "last_month_revenue":   int(hr.get("revenue") or 0) or None,
            "sdk_insights_supported": bool(app.get("sdk_insights_supported")),
            "fetched_at":           _fetched,
        })
        for status, key in [("installed", "sdks_installed"), ("uninstalled", "sdks_uninstalled")]:
            for sdk in (app.get(key) or []):
                sdk_rows.append({
                    "unified_app_id": uid,
                    "platform":       platform,
                    "sdk_id":         int(sdk.get("sdk_id") or 0),
                    "sdk_name":       str(sdk.get("sdk_name") or ""),
                    "company_name":   str(sdk.get("company_name") or ""),
                    "sdk_types":      _json.dumps(sdk.get("sdk_types") or []),
                    "apps_installed": int(sdk.get("apps_installed") or 0),
                    "install_date":   sdk.get("install_date") or None,
                    "uninstall_date": sdk.get("uninstall_date") or None,
                    "days_installed": int(sdk.get("days_installed") or 0),
                    "sdk_status":     status,
                    "fetched_at":     _fetched,
                })

    for platform, id_map in [("ios", ios_map), ("android", android_map)]:
        for batch in _chunks(list(id_map.keys()), 25):
            data = await _get(client, f"/v1/{platform}/apps", {
                "app_ids":          ",".join(batch),
                "country":          "US",
                "include_sdk_data": "true",
            }, total_timeout=120.0)
            for app in (data or {}).get("apps") or []:
                pid = str(app.get("app_id") or "")
                uid = id_map.get(pid) or ""
                if uid:
                    _parse_app(app, platform, uid)
            await _sleep()
        log.info("  %s app_overview: %d apps", platform, len([r for r in overview_rows if r["platform"] == platform]))

    return overview_rows, sdk_rows


async def fetch_network_sov(client: httpx.AsyncClient, unified_ids: list[str]) -> list[dict]:
    """max 5 unified IDs per call — highest API call count of all fetchers."""
    rows = []
    for batch in _chunks(unified_ids, 5):
        data = await _get(client, "/v1/unified/ad_intel/network_analysis", {
            "app_ids":     ",".join(batch),
            "app_id_type": "unified",
            "start_date":  _start.isoformat(),
            "end_date":    _today.isoformat(),
            "period":      "month",
        })
        for item in (data or []):
            rows.append({
                "unified_app_id": str(item.get("app_id") or ""),
                "country":        item.get("country") or "",
                "network":        item.get("network") or "",
                "period_date":    (item.get("date") or "")[:10],
                "sov":            float(item.get("sov") or 0.0),
                "fetched_at":     _fetched,
            })
        await _sleep()
    return rows


async def fetch_download_channels(client: httpx.AsyncClient, unified_ids: list[str]) -> list[dict]:
    """
    confirmed fields: paid_abs, paid_frac, organic_abs, organic_frac,
                      paid_search_abs, paid_search_frac, browser_abs, browser_frac
    Note: paid_abs = paid display (excludes paid_search).
    """
    rows = []
    for batch in _chunks(unified_ids, 50):
        data = await _get(client, "/v1/unified/downloads_by_sources", {
            "app_ids":          ",".join(batch),
            "app_id_type":      "unified",
            "countries":        "WW",
            "start_date":       _start.isoformat(),
            "end_date":         _today.isoformat(),
            "date_granularity": "monthly",
        })
        for app_data in ((data or {}).get("data") or []):
            uid = str(app_data.get("app_id") or "")
            for pt in (app_data.get("breakdown") or []):
                rows.append({
                    "unified_app_id":   uid,
                    "period_date":      (pt.get("date") or "")[:10],
                    "paid_abs":         int(pt.get("paid_abs") or 0),
                    "organic_abs":      int(pt.get("organic_abs") or 0),
                    "paid_search_abs":  int(pt.get("paid_search_abs") or 0),
                    "browser_abs":      int(pt.get("browser_abs") or 0),
                    "paid_frac":        float(pt.get("paid_frac") or 0.0),
                    "organic_frac":     float(pt.get("organic_frac") or 0.0),
                    "paid_search_frac": float(pt.get("paid_search_frac") or 0.0),
                    "browser_frac":     float(pt.get("browser_frac") or 0.0),
                    "fetched_at":       _fetched,
                })
        await _sleep()
    return rows


async def fetch_sdk_tags(
    client: httpx.AsyncClient,
    meta_rows: list[dict],
) -> list[dict]:
    """
    Uses /v1/{os}/apps?include_sdk_data=true — app-centric SDK lookup.
    Returns ALL SDKs per app (installed + uninstalled), not just our 15 tracked ones.
    Batches 100 apps per call: ~50 iOS + ~50 Android = ~100 calls for 5000 apps.
    Requires platform-specific IDs from st_app_metadata.
    """
    import json as _json

    # Build platform ID → unified_app_id maps
    ios_map:     dict[str, str] = {}
    android_map: dict[str, str] = {}
    for r in meta_rows:
        uid = r["unified_app_id"]
        if r.get("app_id_ios"):
            ios_map[r["app_id_ios"]] = uid
        if r.get("app_id_android"):
            android_map[r["app_id_android"]] = uid

    rows: list[dict] = []

    def _sdk_rows(unified_id: str, platform: str, sdk_list: list, status: str) -> list[dict]:
        out = []
        for sdk in sdk_list:
            out.append({
                "unified_app_id": unified_id,
                "platform":       platform,
                "sdk_id":         int(sdk.get("sdk_id") or 0),
                "sdk_name":       str(sdk.get("sdk_name") or ""),
                "company_name":   str(sdk.get("company_name") or ""),
                "sdk_types":      _json.dumps(sdk.get("sdk_types") or []),
                "apps_installed": int(sdk.get("apps_installed") or 0),
                "install_date":   sdk.get("install_date") or None,
                "uninstall_date": sdk.get("uninstall_date") or None,
                "days_installed": int(sdk.get("days_installed") or 0),
                "sdk_status":     status,
                "fetched_at":     _fetched,
            })
        return out

    for platform, id_map in [("ios", ios_map), ("android", android_map)]:
        platform_ids = list(id_map.keys())
        total_sdks = 0
        for batch in _chunks(platform_ids, 100):
            data = await _get(client, f"/v1/{platform}/apps", {
                "app_ids":          ",".join(batch),
                "country":          "US",
                "include_sdk_data": "true",
            })
            apps = (data or {}).get("apps") or []
            for app in apps:
                pid = str(app.get("app_id") or "")
                uid = id_map.get(pid) or ""
                if not uid:
                    continue
                batch_rows = (
                    _sdk_rows(uid, platform, app.get("sdks_installed") or [], "installed") +
                    _sdk_rows(uid, platform, app.get("sdks_uninstalled") or [], "uninstalled")
                )
                rows.extend(batch_rows)
                total_sdks += len(batch_rows)
            await _sleep()
        log.info("  %s SDK data: %d rows from %d apps", platform, total_sdks, len(platform_ids))

    return rows


async def fetch_creatives_count(client: httpx.AsyncClient, unified_ids: list[str]) -> list[dict]:
    """
    Uses /ad_intel/creatives/top (Top Creatives) — market-wide top advertisers
    per network. We loop each network, collect which target apps appear, and
    build per-app creative presence rows.  One call per network; ~12 calls total.
    """
    import json as _json
    target_set = set(unified_ids)
    app_networks: dict[str, set] = {}      # unified_app_id -> set of networks
    app_creative_count: dict[str, int] = {}  # unified_app_id -> total appearances

    networks = [n.strip() for n in CREATIVE_NETWORKS.split(",") if n.strip()]

    for network in networks:
        data = await _get(client, "/v1/unified/ad_intel/creatives/top", {
            "date":     _start.isoformat(),
            "period":   "month",
            "category": "0",        # 0 = Overall (all categories)
            "country":  "US",
            "network":  network,
            "ad_types": "video,image",
            "limit":    "250",
        })
        if data is None:
            await _sleep()
            continue

        # Response: {ad_units: [...]} or {creatives: [...]} or bare list
        if isinstance(data, list):
            units = data
        else:
            units = data.get("ad_units") or data.get("creatives") or []

        for unit in units:
            uid = str(unit.get("unified_app_id") or unit.get("app_id") or "")
            if uid and uid in target_set:
                app_networks.setdefault(uid, set()).add(network)
                app_creative_count[uid] = app_creative_count.get(uid, 0) + 1

        await _sleep()

    rows = []
    for uid in unified_ids:
        nets = app_networks.get(uid, set())
        rows.append({
            "unified_app_id":          uid,
            "period_start":            _start.isoformat(),
            "period_end":              _today.isoformat(),
            "creative_count":          app_creative_count.get(uid, 0),
            "available_network_count": len(nets),
            "available_networks":      _json.dumps(sorted(nets)),
            "fetched_at":              _fetched,
        })
    return rows


async def fetch_downloads_monthly(client: httpx.AsyncClient, unified_ids: list[str]) -> list[dict]:
    """Downloads & Revenue — complements fact_app_basis_v3 daily data.
    Confirmed response: flat list of {app_id, country, date, unified_units, unified_revenue, ...}
    """
    rows = []
    for batch in _chunks(unified_ids, 50):
        data = await _get(client, "/v1/unified/sales_report_estimates", {
            "app_ids":          ",".join(batch),
            "app_id_type":      "unified",
            "countries":        "WW",
            "start_date":       _start.isoformat(),
            "end_date":         _today.isoformat(),
            "date_granularity": "monthly",
        })
        # API returns a flat list of records (one per app × date period)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # fallback: some wrapper shape
            items = data.get("app_download_data") or data.get("data") or []
        else:
            items = []
        for item in items:
            uid = str(item.get("app_id") or "")
            # Flat record: date + unified_units + unified_revenue at top level
            period = (item.get("date") or "")[:10]
            downloads = int(
                item.get("unified_units") or
                item.get("units") or
                item.get("est_mobile_downloads") or 0
            )
            revenue_cents = float(
                item.get("unified_revenue") or
                item.get("revenue") or
                item.get("est_mobile_revenue") or 0
            )
            if uid and period:
                rows.append({
                    "unified_app_id": uid,
                    "period_date":    period,
                    "downloads":      downloads,
                    "revenue_usd":    revenue_cents / 100,
                    "fetched_at":     _fetched,
                })
        await _sleep()
    return rows


async def fetch_active_users(client: httpx.AsyncClient, unified_ids: list[str]) -> list[dict]:
    """Active Users (DAU) — complements fact_app_basis_v3 daily.usage.active_users.
    Confirmed: API always returns daily granularity regardless of date_granularity param.
    Confirmed fields: android_users, ipad_users, iphone_users (flat list).
    Limit: app_ids × date_periods <= 500, so max 4 apps per call for 90-day window.
    """
    rows = []
    # max 4 apps: 4 × ~113 days = ~452 < 500 limit
    for batch in _chunks(unified_ids, 4):
        data = await _get(client, "/v1/unified/usage/active_users", {
            "app_ids":          ",".join(batch),
            "app_id_type":      "unified",
            "countries":        "WW",
            "start_date":       _start.isoformat(),
            "end_date":         _today.isoformat(),
            "date_granularity": "monthly",
        })
        # API returns a flat list of records (one per app × date)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("app_usage_data") or data.get("data") or []
        else:
            items = []
        for item in items:
            uid = str(item.get("app_id") or "")
            period = (item.get("date") or "")[:10]
            # Sum platform users as total active users
            active = int(
                (item.get("android_users") or 0) +
                (item.get("ipad_users") or 0) +
                (item.get("iphone_users") or 0) or
                item.get("active_users") or item.get("mau") or 0
            )
            if uid and period:
                rows.append({
                    "unified_app_id": uid,
                    "country":        "WW",
                    "period_date":    period,
                    "granularity":    "daily",
                    "active_users":   active,
                    "fetched_at":     _fetched,
                })
        await _sleep()
    return rows


async def fetch_advertiser_rank(client: httpx.AsyncClient) -> list[dict]:
    """
    Fetches the global advertiser leaderboard via /v1/unified/ad_intel/top_apps.
    Uses `countries[]` array param to combine all RANK_LEADERBOARD_COUNTRIES into one SOV ranking.
    Cost: RANK_PAGES calls total (default 4 × 250 = 1000 apps).
    """
    rows = []
    period_date = _today.replace(day=1).isoformat()
    for page in range(1, RANK_PAGES + 1):
        # httpx serialises list values as repeated params: countries=US&countries=CA&...
        params: dict[str, Any] = {
            "role":      "advertisers",
            "date":      period_date,
            "period":    "month",
            "category":  "0",
            "country":   RANK_LEADERBOARD_COUNTRIES[0],   # required fallback
            "countries": RANK_LEADERBOARD_COUNTRIES,       # takes priority per API docs
            "network":   "All Networks",
            "limit":     "250",
            "page":      str(page),
        }
        data = await _get(client, "/v1/unified/ad_intel/top_apps", params)
        apps = (data or {}).get("apps") or []
        if not apps:
            break
        for idx, app in enumerate(apps):
            tags = app.get("custom_tags") or {}
            dl_str = tags.get("Last 30 Days Downloads (WW)", "").replace(",", "")
            try:
                downloads_30d: int | None = int(dl_str) if dl_str else None
            except ValueError:
                downloads_30d = None
            rows.append({
                "unified_app_id":            str(app.get("app_id") or ""),
                "app_name":                  str(app.get("name") or ""),
                "publisher_name":            str(app.get("publisher_name") or ""),
                "rank":                      (page - 1) * 250 + idx + 1,
                "sov":                       float(app.get("sov") or 0.0),
                "prev_sov":                  float(app.get("prev_sov") or 0.0),
                "sov_delta":                 float(app.get("sov_delta") or 0.0),
                "downloads_30d_ww":          downloads_30d,
                "most_popular_country":      tags.get("Most Popular Country by Downloads", ""),
                "advertised_on_any_network": tags.get("Advertised on Any Network", ""),
                "contains_ads":              tags.get("Contains Ads", ""),
                "country":                   "COMBINED",
                "network":                   "All Networks",
                "period_date":               period_date,
                "fetched_at":                _fetched,
            })
        await _sleep()
        log.info("  leaderboard page=%d → %d apps (combined %d countries)",
                 page, len(apps), len(RANK_LEADERBOARD_COUNTRIES))
    return rows


# ─── Pipeline ─────────────────────────────────────────────────────────────────

async def run_pipeline() -> None:
    bq = bigquery.Client(project=DATASET.split(".")[0])
    bq_ensure_tables(bq)

    unified_ids = bq_load_app_ids(bq)
    log.info("Pipeline: %d unified IDs, lookback %d days → %s", len(unified_ids), LOOKBACK_DAYS, DATASET)

    async with httpx.AsyncClient(base_url=ST_BASE, timeout=httpx.Timeout(60.0)) as client:

        # 1. App metadata — must run first; SDK tags need the platform IDs
        log.info("=== [1/9] st_app_metadata ===")
        meta = await fetch_app_metadata(client, unified_ids)
        bq_write(bq, "st_app_metadata", meta)

        # For detail endpoints, only process top DETAIL_SAMPLE apps (already sorted
        # by download volume DESC from APP_IDS_QUERY)
        detail_ids = unified_ids[:DETAIL_SAMPLE]
        detail_meta = [r for r in meta if r["unified_app_id"] in set(detail_ids)]
        log.info("Detail endpoints will run for top %d / %d apps", len(detail_ids), len(unified_ids))

        # 2. App overview + SDK tags — one set of calls fills both tables
        #     All 63K apps; ~850 calls at 5 RPS ≈ 3 min
        log.info("=== [2/10] st_app_overview + st_sdk_tags  [%d apps] ===", len(unified_ids))
        overview_rows, sdk_rows = await fetch_app_overview_and_sdk(client, meta)
        bq_write(bq, "st_app_overview", overview_rows)
        bq_write(bq, "st_sdk_tags", sdk_rows)

        # 3. Unified ID map — built after overview so bundle_id_ios is populated
        log.info("=== [3/10] st_unified_id_map ===")
        bq_write(bq, "st_unified_id_map", build_unified_map(meta, overview_rows))

        # 4. Download channels
        log.info("=== [4/10] st_download_channels ===")
        bq_write(bq, "st_download_channels", await fetch_download_channels(client, detail_ids))

        # 6. Creative count  [market-wide top creatives — only 12 API calls total]
        log.info("=== [6/10] st_creatives_count ===")
        bq_write(bq, "st_creatives_count", await fetch_creatives_count(client, detail_ids))

        # 7. Monthly downloads + revenue
        log.info("=== [7/10] st_downloads_monthly ===")
        bq_write(bq, "st_downloads_monthly", await fetch_downloads_monthly(client, detail_ids))

        # 8. Active users  [batch=4 due to API limit; capped to AU_SAMPLE]
        au_ids = detail_ids[:AU_SAMPLE]
        log.info("=== [8/10] st_active_users  [sample=%d] ===", len(au_ids))
        bq_write(bq, "st_active_users", await fetch_active_users(client, au_ids))

        # 9. Advertiser leaderboard  [RANK_PAGES pages × len(countries) = ~8 calls]
        log.info("=== [9/10] st_advertiser_rank  [pages=%d] ===", RANK_PAGES)
        bq_write(bq, "st_advertiser_rank", await fetch_advertiser_rank(client))

    log.info("Pipeline complete.")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
