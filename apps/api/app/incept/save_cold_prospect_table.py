"""
Cold prospect pipeline — fully ST API-driven enrichment.  Runs monthly (first Monday of each month).

Steps:
  1. BQ       : cold prospect selection (no Moloco SDK/UA 90d, China HQ, 20K+ DL, company exclusion,
                skip supply team's top-2000 BD targets that already have an assigned rep)
  2. ST API   : overview + SDK    (/v1/{platform}/apps,          batch=100)
  3. ST API   : download channels (/v1/unified/downloads_by_sources, batch=50)
  4. ST API   : MAU               (/v1/unified/usage/active_users,   batch=4)
  5. ST API   : network SOV       (/v1/unified/ad_intel/network_analysis, per-app)
                filtered to top-3 countries from overview + fixed network list → fast & no timeout
  6. BQ       : Moloco supply visibility (supply_demand_overlap)
  7. BQ write : WRITE_TRUNCATE → cold_prospect_app  (entity columns NULL initially)
  8. BQ write : CREATE OR REPLACE → cold_prospect_company  (dedup per company)
  9. Gemini   : Chinese entity + address + background enrichment (cache-first, Google Search grounding)
 10. BQ join  : JOIN cache back into cold_prospect_app + rebuild cold_prospect_company

~1000 apps → ~830 ST API calls → ~5-7 minutes

Run:
  cd /Users/owen.geng/Documents/Projects/Incept/apps/api
  source .venv/bin/activate && set -a && source .env && set +a
  python -m app.incept.save_cold_prospect_table
"""
import asyncio
import json as _json
import logging
import os
import re
import time
from datetime import date, timedelta
from typing import Any

import httpx
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField as F

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEST_DATASET        = "ads-bpd-guard-sandbox.supply_smb"
DEST_APP            = f"{DEST_DATASET}.cold_prospect_app"
DEST_COMPANY        = f"{DEST_DATASET}.cold_prospect_company"
DEST_SNAPSHOT       = f"{DEST_DATASET}.prospect_snapshot"
DEST_CONVERSION     = f"{DEST_DATASET}.prospect_conversion"
DEST_ENTITY_CACHE   = f"{DEST_DATASET}.chinese_entity_cache"
ST_BASE    = "https://api.sensortower.com"
ST_TOKEN   = os.environ.get("SENSORTOWER_API_KEY") or os.environ.get("SENSOR_TOWER_API_TOKEN", "")
RATE_RPS   = 5

GCP_PROJECT      = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_DEPLOY", "ads-bpd-guard-sandbox")
GCP_LOCATION     = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.6-flash")

_today          = date.today()
_lookback_start = (_today - timedelta(days=90)).replace(day=1)
_mau_start      = (_today - timedelta(days=30)).replace(day=1)

# Last complete calendar month (e.g. 2026-05-01 → 2026-05-31)
_last_month_end   = _today.replace(day=1) - timedelta(days=1)
_last_month_start = _last_month_end.replace(day=1)


# ── Chinese entity cache ──────────────────────────────────────────────────────

ENTITY_CACHE_SCHEMA = [
    F("company_key",     "STRING"),  # LOWER(TRIM(company_name))
    F("company_name",    "STRING"),
    F("publisher_name",  "STRING"),
    F("hq_country",      "STRING"),
    F("website",         "STRING"),
    F("app_bundles",     "STRING"),
    F("chinese_entity",      "STRING"),
    F("chinese_address",     "STRING"),
    F("company_background",  "STRING"),
    F("evidence_note",       "STRING"),
    F("confidence",          "STRING"),  # high / medium / low / unknown
    F("needs_review",        "BOOLEAN"),
    F("looked_up_at",        "DATE"),
]


def bq_load_entity_cache(bq: bigquery.Client) -> dict[str, dict]:
    """Load existing cache. Returns {company_key: {chinese_entity, confidence, needs_review}}."""
    try:
        rows = list(bq.query(f"SELECT * FROM `{DEST_ENTITY_CACHE}`").result())
        return {r["company_key"]: dict(r) for r in rows}
    except Exception:
        return {}


def bq_upsert_entity_cache(bq: bigquery.Client, new_rows: list[dict]) -> None:
    if not new_rows:
        return
    job = bq.load_table_from_json(
        new_rows, DEST_ENTITY_CACHE,
        job_config=bigquery.LoadJobConfig(
            schema=ENTITY_CACHE_SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        ),
    )
    job.result()
    log.info("→ %s: %d new entries saved", DEST_ENTITY_CACHE, len(new_rows))


async def _gemini_lookup_entity(
    semaphore: asyncio.Semaphore,
    company_name: str,
    publisher_name: str,
    hq_country: str | None,
    website: str | None,
    app_bundles: str | None,
) -> dict:
    """Call Gemini with Google Search grounding to find Chinese legal entity name and address."""
    import google.genai as genai
    from google.genai import types as genai_types

    prompt = (
        "You are a business intelligence researcher specializing in Chinese mobile app companies. "
        "Your task is to verify the official Chinese registered entity (工商主体) and base city for one company. "
        "Do NOT fabricate — if you cannot find reliable evidence, say so explicitly.\n\n"
        "## Company to verify\n"
        f"- Company name: {company_name}\n"
        f"- Publisher name: {publisher_name}\n"
        f"- HQ country: {hq_country or 'unknown'}\n"
        f"- Website: {website or 'unknown'}\n"
        f"- App bundle IDs: {app_bundles or 'unknown'}\n\n"
        "## Verification steps — search in this priority order\n"
        "1. **Official website**: Check footer copyright notice, ICP filing number (ICP备案号 can be "
        "reverse-looked-up to find the registered entity and city), Legal/Privacy Policy pages.\n"
        "2. **Listed company records**: A-share (SSE/SZSE), HK Stock Exchange, Taiwan TWSE/TPEx listing codes; "
        "SAMR or CNIPA registration.\n"
        "3. **ICP/APP filing**: Search '企查查', '天眼查', or MIIT ICP filing system for the domain or app name.\n"
        "4. **Authoritative press**: 36Kr, 界面, China Daily, official press releases mentioning HQ city or full company name.\n"
        "5. **App Store / Google Play developer info**: Distinguish between the publishing shell company "
        "(often HK/Cayman/PTE entity) and the actual operating/development entity (usually mainland China). "
        "Note both if different.\n"
        "6. **Name transliteration / inference**: Last resort only — mark as low confidence.\n\n"
        "## Key rules\n"
        "- If the publisher name looks like a shell company (e.g. 'XX Limited Hong Kong', 'XX PTE LTD'), "
        "search for the actual mainland operating entity separately.\n"
        "- If sources conflict, set needs_review=true and explain the conflict in evidence_note.\n"
        "- Perform at least 2 searches with different keyword combinations before concluding.\n"
        "- Write company_background in Chinese, 1-2 sentences: founding year, main products, notable facts.\n\n"
        "## Output — return ONLY valid JSON, no markdown fences\n"
        '{"chinese_entity": "<full Chinese registered company name, or null>", '
        '"chinese_address": "<full Chinese registered city/address, or null>", '
        '"company_background": "<1-2 sentence Chinese background summary, or null>", '
        '"confidence": "<high|medium|low|unknown>", '
        '"needs_review": <true|false>, '
        '"evidence_note": "<source used: e.g. ICP filing XX号, listed code 688615.SH, official website footer, etc.>"}\n\n'
        "Confidence levels:\n"
        "- high ✅ : ICP filing number, stock listing code, SAMR/CNIPA record, or official website with clear legal entity\n"
        "- medium : Publishing shell company identified but mainland entity unconfirmed; or transliteration is highly credible\n"
        "- low : Only brand name or domain available, no corporate registration trace found\n"
        "- unknown: No usable information found at all\n"
        "Set needs_review=true if: confidence is low/unknown, sources conflict, or shell vs operating entity is ambiguous."
    )

    async with semaphore:
        try:
            loop = asyncio.get_event_loop()
            client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)

            def _call():
                return client.models.generate_content(
                    model=GEMINI_TEXT_MODEL,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                        temperature=0.0,
                        max_output_tokens=512,
                    ),
                )

            resp = await loop.run_in_executor(None, _call)
            text = (resp.text or "").strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
            parsed = _json.loads(text)
            return {
                "chinese_entity":     parsed.get("chinese_entity") or None,
                "chinese_address":    parsed.get("chinese_address") or None,
                "company_background": parsed.get("company_background") or None,
                "evidence_note":      parsed.get("evidence_note") or None,
                "confidence":         parsed.get("confidence", "unknown"),
                "needs_review":       bool(parsed.get("needs_review", True)),
            }
        except Exception as exc:
            log.warning("Gemini entity lookup failed for %s: %s", company_name, exc)
            return {"chinese_entity": None, "chinese_address": None, "company_background": None, "evidence_note": None, "confidence": "unknown", "needs_review": True}


async def enrich_chinese_entities(bq: bigquery.Client, rows: list[dict]) -> dict[str, dict]:
    """
    For each unique company in rows, look up Chinese entity + address via cache then Gemini.
    rows must have: company_name, publisher_name, hq_country, website, app_bundles.
    Returns {company_key: {chinese_entity, chinese_address, confidence, needs_review}}.
    """
    cache = bq_load_entity_cache(bq)
    log.info("Chinese entity cache: %d existing entries", len(cache))

    # Deduplicate: one lookup per unique company_name
    seen: dict[str, dict] = {}  # company_key → meta
    for r in rows:
        key = (r.get("company_name") or "").lower().strip()
        if not key or key in cache or key in seen:
            continue
        seen[key] = {
            "company_name":   r.get("company_name") or "",
            "publisher_name": r.get("publisher_name") or "",
            "hq_country":     r.get("hq_country") or None,
            "website":        r.get("website") or None,
            "app_bundles":    r.get("app_bundles") or None,
        }

    log.info("Chinese entity lookup: %d companies to query (skipping %d cached)", len(seen), len(cache))

    if not seen:
        return cache

    semaphore = asyncio.Semaphore(4)  # max 4 concurrent Gemini calls
    today_str = _today.isoformat()

    tasks = {
        key: _gemini_lookup_entity(
            semaphore,
            meta["company_name"],
            meta["publisher_name"],
            meta["hq_country"],
            meta["website"],
            meta["app_bundles"],
        )
        for key, meta in seen.items()
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    new_cache_rows: list[dict] = []
    for key, result in zip(tasks.keys(), results):
        meta = seen[key]
        if isinstance(result, Exception):
            result = {"chinese_entity": None, "chinese_address": None, "company_background": None, "evidence_note": None, "confidence": "unknown", "needs_review": True}
        entry = {
            "company_key":       key,
            "company_name":      meta["company_name"],
            "publisher_name":    meta["publisher_name"],
            "hq_country":        meta["hq_country"],
            "website":           meta["website"],
            "app_bundles":       meta["app_bundles"],
            "chinese_entity":    result["chinese_entity"],
            "chinese_address":   result["chinese_address"],
            "company_background":result["company_background"],
            "evidence_note":     result["evidence_note"],
            "confidence":        result["confidence"],
            "needs_review":      result["needs_review"],
            "looked_up_at":      today_str,
        }
        cache[key] = entry
        new_cache_rows.append(entry)
        log.info(
            "  %s → %s / %s (%s)",
            meta["company_name"],
            result["chinese_entity"] or "N/A",
            result["chinese_address"] or "N/A",
            result["confidence"],
        )

    bq_upsert_entity_cache(bq, new_cache_rows)
    return cache


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


async def _get(client: httpx.AsyncClient, path: str, params: dict, timeout: float = 120.0) -> Any:
    p = dict(params, auth_token=ST_TOKEN)
    backoff = 1.0
    for attempt in range(5):
        try:
            resp = await asyncio.wait_for(client.get(path, params=p), timeout=timeout)
        except (asyncio.TimeoutError, httpx.ReadTimeout, httpx.ConnectTimeout,
                httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
            log.warning("ST %s → %s, retry %d/5", path, type(exc).__name__, attempt + 1)
            await asyncio.sleep(backoff); backoff = min(backoff * 2, 16.0); continue
        if resp.status_code in (429, 500, 502, 503, 504):
            log.warning("ST %s → %d, retry %d/5", path, resp.status_code, attempt + 1)
            await asyncio.sleep(backoff); backoff = min(backoff * 2, 16.0); continue
        if not resp.is_success:
            log.error("ST %s → %d: %s", path, resp.status_code, resp.text[:300])
            return None
        return resp.json()
    log.error("ST %s → exhausted retries", path)
    return None


async def _sleep():
    await asyncio.sleep(1.0 / RATE_RPS)


# ── BQ: cold prospect selection ───────────────────────────────────────────────

COLD_APPS_SQL = """
WITH moloco_known_companies AS (
  SELECT DISTINCT LOWER(TRIM(publisher_name)) AS company_key
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  WHERE (is_moloco_sdk_app = true OR is_moloco_advertiser_app = true)
    AND publisher_name IS NOT NULL
  UNION DISTINCT
  SELECT DISTINCT LOWER(TRIM(product.company_name)) AS company_key
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND gross_spend_usd > 0
    AND product.company_name IS NOT NULL
),

-- Supply team's global top-2000 BD target list (ranked by L90D media cost across
-- all exchanges, not just Moloco). Used only to (a) skip publishers supply already
-- assigned a BD rep to, and (b) flag the unassigned ones still inside the top 2000.
supply_top2000 AS (
  SELECT
    LOWER(TRIM(publisher_name)) AS publisher_key,
    l90d_rank,
    bd AS supply_bd_rep
  FROM `moloco-data-prod.jinju.sdk_bd_target_setting_26q3_0624`
  WHERE l90d_rank <= 2000
)

SELECT DISTINCT
  m.app_market_bundle,
  m.os,
  m.sensortower.product.app_name       AS app_name,
  m.sensortower.product.has_ads        AS has_ads,
  m.sensortower.product.has_iap        AS has_iap,
  m.sensortower.class.is_gaming        AS is_gaming,
  m.sensortower.company.name           AS company_name,
  m.sensortower.company.hq_country     AS hq_country,
  m.sensortower.publisher.name         AS publisher_name,
  m.sensortower.publisher.website      AS website,
  m.sensortower.class.genre            AS genre,
  st2k.l90d_rank IS NOT NULL           AS is_supply_top2000,
  st2k.l90d_rank                       AS supply_top2000_rank,
  st2k.supply_bd_rep                   AS supply_bd_rep
FROM `ads-bpd-guard-china.athena.dim1_app_v3` m
LEFT JOIN supply_top2000 st2k
  ON LOWER(TRIM(m.sensortower.publisher.name)) = st2k.publisher_key
INNER JOIN (
  SELECT app_market_bundle
  FROM `ads-bpd-guard-china.sensortower.fact_app_basis_v3`
  WHERE date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
  GROUP BY app_market_bundle HAVING SUM(monthly.download.`all`) >= 20000
) d ON m.app_market_bundle = d.app_market_bundle
LEFT JOIN (
  SELECT DISTINCT app_bundle
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  WHERE is_moloco_sdk_app = true
) sdk ON m.app_market_bundle = sdk.app_bundle
LEFT JOIN (
  SELECT DISTINCT product.app_market_bundle AS bundle
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND gross_spend_usd > 0 AND product.app_market_bundle IS NOT NULL
) ua ON m.app_market_bundle = ua.bundle
LEFT JOIN (
  SELECT app_market_bundle FROM (
    SELECT app_market_bundle, country,
      ROW_NUMBER() OVER (PARTITION BY app_market_bundle ORDER BY SUM(monthly.download.`all`) DESC) AS rn
    FROM `ads-bpd-guard-china.sensortower.fact_app_basis_v3`
    WHERE date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
      AND monthly.download.`all` > 0 AND country IS NOT NULL
    GROUP BY app_market_bundle, country
  ) WHERE rn = 1 AND UPPER(country) IN ('CN','CHN','CHINA','IN','IND')
) domestic ON m.app_market_bundle = domestic.app_market_bundle
WHERE UPPER(m.sensortower.company.hq_country) IN ('CN','CHN','CHINA','HK','HKG','TW','TWN')
  AND sdk.app_bundle IS NULL
  AND ua.bundle IS NULL
  AND domestic.app_market_bundle IS NULL
  AND LOWER(TRIM(m.sensortower.company.name))   NOT IN (SELECT company_key FROM moloco_known_companies)
  AND LOWER(TRIM(m.sensortower.publisher.name)) NOT IN (SELECT company_key FROM moloco_known_companies)
  -- Skip publishers supply team already assigned a BD rep to (top 2000 + owned).
  -- Top-2000-but-unassigned publishers stay in and get flagged via is_supply_top2000.
  AND NOT (st2k.l90d_rank IS NOT NULL AND st2k.supply_bd_rep IS NOT NULL)
"""


def bq_get_cold_apps(bq: bigquery.Client) -> list[dict]:
    log.info("Running cold prospect selection SQL …")
    rows = list(bq.query(COLD_APPS_SQL).result())
    result = [dict(r) for r in rows]
    log.info("Cold prospect apps: %d", len(result))
    return result


def bq_get_supply(bq: bigquery.Client, bundles: list[str]) -> dict[str, dict]:
    if not bundles:
        return {}
    placeholders = ", ".join(f"'{b}'" for b in bundles)
    sql = f"""
    SELECT
      app_bundle,
      MAX(is_supply_partner)  AS is_supply_partner,
      MAX(media_cost_usd)     AS moloco_media_cost_30d,
      MAX(bid_requests)       AS moloco_bid_requests,
      MAX(eligibility_status) AS eligibility_status
    FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
    WHERE app_bundle IN ({placeholders})
    GROUP BY app_bundle
    """
    rows = list(bq.query(sql).result())
    return {r["app_bundle"]: dict(r) for r in rows}


def bq_get_moloco_history(bq: bigquery.Client, bundles: list[str]) -> dict[str, dict]:
    """Return most-recent Moloco DSP advertiser title + platform per bundle (24-month lookback)."""
    if not bundles:
        return {}
    placeholders = ", ".join(f"'{b}'" for b in bundles)
    sql = f"""
    SELECT
      product.app_market_bundle AS bundle,
      advertiser.title          AS moloco_advertiser_title,
      platform_id               AS moloco_platform_id,
      advertiser.gm             AS moloco_advertiser_gm,
      advertiser.nbs            AS moloco_advertiser_nbs,
      MAX(date_utc)             AS moloco_last_active
    FROM `ads-bpd-guard-china.athena.fact_dsp_core`
    WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 24 MONTH)
      AND product.app_market_bundle IN ({placeholders})
    GROUP BY 1, 2, 3, 4, 5
    QUALIFY ROW_NUMBER() OVER (
      PARTITION BY product.app_market_bundle
      ORDER BY MAX(date_utc) DESC
    ) = 1
    """
    rows = list(bq.query(sql).result())
    return {
        r["bundle"]: {
            "moloco_advertiser_title": r["moloco_advertiser_title"],
            "moloco_platform_id":      r["moloco_platform_id"],
            "moloco_advertiser_gm":    r["moloco_advertiser_gm"],
            "moloco_advertiser_nbs":   r["moloco_advertiser_nbs"],
            "moloco_last_active":      r["moloco_last_active"].isoformat() if r["moloco_last_active"] else None,
        }
        for r in rows
    }


# ── BQ output schema ──────────────────────────────────────────────────────────

SCHEMA = [
    # Identity (from Moloco BQ)
    F("app_market_bundle",     "STRING"),
    F("os",                    "STRING"),
    F("unified_app_id",        "STRING"),
    F("app_name",              "STRING"),
    F("company_name",          "STRING"),
    F("publisher_name",        "STRING"),
    F("hq_country",            "STRING"),
    F("website",               "STRING"),
    F("team_routing",          "STRING"),
    F("genre",                 "STRING"),
    F("monetization_type",     "STRING"),
    F("has_ads",               "BOOLEAN"),
    F("has_iap",               "BOOLEAN"),
    # ST overview (from ST API)
    F("publisher_email",       "STRING"),
    F("publisher_country",     "STRING"),
    F("rating",                "FLOAT64"),
    F("global_rating_count",   "INTEGER"),
    F("top_countries",         "STRING"),
    F("sdk_insights_supported","BOOLEAN"),
    F("release_date",          "DATE"),
    F("updated_date",          "DATE"),
    # Downloads
    F("st_last_month_downloads","INTEGER"),
    F("st_daily_downloads_avg", "INTEGER"),
    # MAU (from ST API)
    F("mau_ww",                "INTEGER"),
    # Download channels (from ST API)
    F("paid_frac",             "FLOAT64"),
    F("organic_frac",          "FLOAT64"),
    F("paid_abs",              "INTEGER"),
    F("organic_abs",           "INTEGER"),
    F("paid_search_frac",      "FLOAT64"),
    F("paid_search_abs",       "INTEGER"),
    # SDKs (from ST API)
    F("installed_sdk_count",   "INTEGER"),
    F("installed_sdks",        "STRING"),
    F("uninstalled_sdks",      "STRING"),
    # Network SOV (from ST API — top-3 countries × fixed networks)
    F("active_ua_networks",    "STRING"),
    F("peak_sov",              "FLOAT64"),
    # Moloco supply (from BQ)
    F("is_moloco_supply_visible","BOOLEAN"),
    F("moloco_media_cost_30d", "FLOAT64"),
    F("moloco_bid_requests",   "INTEGER"),
    F("eligibility_status",    "STRING"),
    F("priority",              "STRING"),   # P1 / P2 / P3
    F("data_as_of",            "DATE"),
    # Supply team's top-2000 BD target list (unassigned-only; assigned ones are excluded upstream)
    F("is_supply_top2000",     "BOOLEAN"),
    F("supply_top2000_rank",   "INTEGER"),
    F("supply_bd_rep",         "STRING"),
    # Moloco historical advertiser (from fact_dsp_core, 24-month lookback)
    F("moloco_advertiser_title","STRING"),
    F("moloco_platform_id",    "STRING"),
    F("moloco_advertiser_gm",  "STRING"),
    F("moloco_advertiser_nbs", "STRING"),
    F("moloco_last_active",    "DATE"),
    # Chinese entity lookup (Gemini + Google Search, cached in chinese_entity_cache)
    F("chinese_entity",            "STRING"),
    F("chinese_address",           "STRING"),
    F("company_background",        "STRING"),
    F("evidence_note",             "STRING"),
    F("chinese_entity_confidence", "STRING"),
    F("chinese_entity_needs_review","BOOLEAN"),
]

# UA SDK regex — apps with any of these are eligible for P1/P2 (no IAP required at this stage)
_TARGET_UA_SDK_RE = (
    r"AppLovin MAX|Applovin|ironSource|LevelPlay|UnityAds|"
    r"Mintegral|Pangle|TopOn|Appodeal|Bidmachine|AdMob"
)


# ── Monetization type helper ──────────────────────────────────────────────────

def _mon_type(has_ads: bool | None, has_iap: bool | None) -> str:
    if has_ads and not has_iap:  return "IAA"
    if has_iap and not has_ads:  return "IAP"
    if has_ads and has_iap:      return "Hybrid"
    return "Free"


# ── ST API: step 2 — overview + SDK ──────────────────────────────────────────

async def fetch_overview_and_sdk(
    client: httpx.AsyncClient,
    apps: list[dict],
) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Calls /v1/{platform}/apps?include_sdk_data=true for iOS and Android separately.

    Returns:
      overview_map : bundle → {unified_app_id, publisher_email, rating, …}
      sdk_map      : unified_app_id → {installed_sdks, uninstalled_sdks, installed_sdk_count}
    """
    ios_bundles     = [a["app_market_bundle"] for a in apps if a["os"].upper() == "IOS"]
    android_bundles = [a["app_market_bundle"] for a in apps if a["os"].upper() == "ANDROID"]

    overview_map: dict[str, dict] = {}
    sdk_map: dict[str, dict] = {}

    for platform, bundles in [("ios", ios_bundles), ("android", android_bundles)]:
        if not bundles:
            continue
        log.info("ST overview+SDK [%s]: %d apps → %d calls",
                 platform, len(bundles), (len(bundles) + 99) // 100)
        done = 0
        for batch in _chunks(bundles, 100):
            data = await _get(client, f"/v1/{platform}/apps", {
                "app_ids":          ",".join(batch),
                "include_sdk_data": "true",
            })
            for app in (data or {}).get("apps") or []:
                pid = str(app.get("app_id") or "")
                uid = str(app.get("unified_app_id") or "")

                hd = app.get("humanized_worldwide_last_month_downloads") or {}
                overview_map[pid] = {
                    "unified_app_id":          uid,
                    "publisher_email":          str(app.get("publisher_email") or "") or None,
                    "publisher_country":        str(app.get("publisher_country") or "") or None,
                    "rating":                   float(app.get("rating") or 0.0),
                    "global_rating_count":      int(app.get("global_rating_count") or 0),
                    "top_countries":            _json.dumps(app.get("top_countries") or []),
                    "sdk_insights_supported":   bool(app.get("sdk_insights_supported")),
                    "release_date":             (app.get("release_date") or "")[:10] or None,
                    "updated_date":             (app.get("updated_date") or "")[:10] or None,
                    "st_last_month_downloads":  int(hd.get("downloads") or 0) or None,
                }

                if uid:
                    installed   = [s["sdk_name"] for s in (app.get("sdks_installed")   or []) if s.get("sdk_name")]
                    uninstalled = [s["sdk_name"] for s in (app.get("sdks_uninstalled") or []) if s.get("sdk_name")]
                    sdk_map[uid] = {
                        "installed_sdk_count": len(installed),
                        "installed_sdks":      ", ".join(sorted(set(installed))) or None,
                        "uninstalled_sdks":    ", ".join(sorted(set(uninstalled))) or None,
                    }

            done += len(batch)
            log.info("  [%s] %d/%d done", platform, done, len(bundles))
            await _sleep()

    return overview_map, sdk_map


# ── ST API: step 3 — download channels ───────────────────────────────────────

async def fetch_channels(
    client: httpx.AsyncClient,
    unified_ids: list[str],
) -> dict[str, dict]:
    """Returns uid → latest-month channel breakdown."""
    log.info("ST channels: %d apps → %d calls", len(unified_ids), (len(unified_ids) + 49) // 50)
    # uid → {date, paid_frac, organic_frac, …} — keep only the latest period
    latest: dict[str, dict] = {}

    for batch in _chunks(unified_ids, 50):
        data = await _get(client, "/v1/unified/downloads_by_sources", {
            "app_ids":          ",".join(batch),
            "app_id_type":      "unified",
            "countries":        "WW",
            "start_date":       _last_month_start.isoformat(),
            "end_date":         _last_month_end.isoformat(),
            "date_granularity": "monthly",
        })
        for app_data in ((data or {}).get("data") or []):
            uid = str(app_data.get("app_id") or "")
            if not uid:
                continue
            for pt in (app_data.get("breakdown") or []):
                period = (pt.get("date") or "")[:10]
                if not period:
                    continue
                existing = latest.get(uid, {})
                if period >= existing.get("_date", ""):
                    latest[uid] = {
                        "_date":           period,
                        "paid_frac":       float(pt.get("paid_frac")       or 0.0),
                        "organic_frac":    float(pt.get("organic_frac")    or 0.0),
                        "paid_abs":        int(pt.get("paid_abs")          or 0),
                        "organic_abs":     int(pt.get("organic_abs")       or 0),
                        "paid_search_frac":float(pt.get("paid_search_frac")or 0.0),
                        "paid_search_abs": int(pt.get("paid_search_abs")   or 0),
                    }
        await _sleep()

    # Strip the internal _date key
    return {uid: {k: v for k, v in rec.items() if k != "_date"}
            for uid, rec in latest.items()}


# ── ST API: step 4 — MAU ─────────────────────────────────────────────────────

async def fetch_mau(
    client: httpx.AsyncClient,
    unified_ids: list[str],
) -> dict[str, int]:
    """Returns uid → MAU (latest monthly, WW). Batch=4 due to API limit."""
    log.info("ST MAU: %d apps → %d calls", len(unified_ids), (len(unified_ids) + 3) // 4)
    mau_map: dict[str, int] = {}

    for batch in _chunks(unified_ids, 4):
        data = await _get(client, "/v1/unified/usage/active_users", {
            "app_ids":          ",".join(batch),
            "app_id_type":      "unified",
            "countries":        "WW",
            "start_date":       _last_month_start.isoformat(),
            "end_date":         _last_month_end.isoformat(),
            "date_granularity": "monthly",
        })
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("app_usage_data") or data.get("data") or []
        else:
            items = []
        for item in items:
            uid = str(item.get("app_id") or "")
            if not uid:
                continue
            active = int(
                (item.get("android_users") or 0) +
                (item.get("ipad_users")    or 0) +
                (item.get("iphone_users")  or 0)
            ) or int(item.get("active_users") or item.get("mau") or 0)
            # Keep max across dates
            if active > mau_map.get(uid, 0):
                mau_map[uid] = active
        await _sleep()

    return mau_map


# ── ST API: step 5 — network SOV (per-app, filtered) ─────────────────────────

# Fixed network list — major UA networks relevant to China GTM apps.
# Keeping to ~10 avoids the huge WW×all-networks aggregation that causes timeouts.
_SOV_NETWORKS = ",".join([
    "Admob", "Applovin", "Facebook", "Instagram",
    "Meta Audience Network", "Mintegral",
    "Pangle", "TikTok", "Unity", "Vungle",
])

# Countries supported by /v1/unified/ad_intel/network_analysis (from API error response).
# Filters out unsupported codes (e.g. KZ, BY, UA, VN, PK) to avoid 422 errors.
_SOV_VALID_COUNTRIES = {
    "US","AU","CA","CN","FR","DE","GB","IT","JP","KR","RU",
    "AR","AT","BE","BR","CL","CO","CZ","DK","EC","GR","HK",
    "IN","ID","IL","LU","MY","MX","NG","NL","NZ","NO","PA",
    "PE","PH","PL","PT","RO","SA","SG","ZA","ES","SE","CH",
    "TW","TH","TR","AE","VN","UA",
}


async def fetch_network_sov(
    client: httpx.AsyncClient,
    uid_countries: list[tuple[str, list[str]]],
) -> dict[str, dict]:
    """
    Per-app network SOV query filtered to top-3 countries + fixed network list.
    One call per app — avoids the massive WW×all-networks timeout issue.
    Timeout=20s per call; on timeout the app gets empty SOV (skipped, not crashed).

    uid_countries: [(unified_app_id, [country1, country2, country3]), ...]
    Returns: uid → {active_ua_networks: str, peak_sov: float}
    """
    log.info("ST network SOV: %d apps (per-app, filtered networks)", len(uid_countries))
    result: dict[str, dict] = {}
    skipped = 0

    for uid, countries in uid_countries:
        if not countries:
            countries = ["US"]
        data = await _get(client, "/v1/unified/ad_intel/network_analysis", {
            "app_ids":     uid,
            "app_id_type": "unified",
            "start_date":  _last_month_start.isoformat(),
            "end_date":    _last_month_end.isoformat(),
            "period":      "month",
            "networks":    _SOV_NETWORKS,
            "countries":   ",".join(countries[:3]),
        }, timeout=20.0)

        if data is None:
            skipped += 1
            await _sleep()
            continue

        networks_sov: dict[str, float] = {}
        peak = 0.0
        for item in (data or []):
            sov = float(item.get("sov") or 0.0)
            network = str(item.get("network") or "")
            if sov > 0 and network:
                networks_sov[network] = max(networks_sov.get(network, 0.0), sov)
            if sov > peak:
                peak = sov

        # Sort networks by SOV descending so the highest-spend network appears first
        sorted_nets = sorted(networks_sov, key=lambda n: -networks_sov[n])
        result[uid] = {
            "active_ua_networks": ", ".join(sorted_nets) or None,
            "peak_sov":           peak if peak > 0 else None,
        }
        await _sleep()

    if skipped:
        log.warning("Network SOV: %d apps skipped (timeout/error)", skipped)
    log.info("Network SOV: %d apps enriched", len(result))
    return result


# ── Final merge + BQ write ────────────────────────────────────────────────────

def build_rows(
    cold_apps: list[dict],
    overview_map: dict[str, dict],
    sdk_map: dict[str, dict],
    channels_map: dict[str, dict],
    mau_map: dict[str, int],
    supply_map: dict[str, dict],
    network_map: dict[str, dict] | None = None,
    history_map: dict[str, dict] | None = None,
) -> list[dict]:
    today_str = _today.isoformat()
    rows = []
    for app in cold_apps:
        bundle = app["app_market_bundle"]
        ov  = overview_map.get(bundle, {})
        uid = ov.get("unified_app_id") or ""
        sdk = sdk_map.get(uid, {}) if uid else {}
        ch  = channels_map.get(uid, {}) if uid else {}
        sv  = supply_map.get(bundle, {})
        nw  = (network_map or {}).get(uid, {}) if uid else {}
        hist = (history_map or {}).get(bundle, {})

        has_ads = app.get("has_ads")
        has_iap = app.get("has_iap")
        is_gaming = bool(app.get("is_gaming"))

        mon_type = _mon_type(has_ads, has_iap)

        # Free apps (no ads, no IAP) → skip entirely, not worth targeting
        if mon_type == "Free":
            continue

        # Priority
        installed = sdk.get("installed_sdks") or ""
        paid_frac_val = ch.get("paid_frac") or 0.0
        active_nets   = nw.get("active_ua_networks")
        has_ua_sdk    = bool(re.search(_TARGET_UA_SDK_RE, installed, re.IGNORECASE))
        if has_ua_sdk and paid_frac_val >= 0.50 and active_nets:
            priority = "P1"
        elif has_ua_sdk and paid_frac_val >= 0.20:
            priority = "P2"
        else:
            priority = "P3"

        # IAP-only apps cannot be P1 (no ad inventory to monetize) → cap at P2
        if mon_type == "IAP" and priority == "P1":
            priority = "P2"

        # Demote P1/P2 apps whose #1 download country is IN or PK → P3 (still enriched, not excluded)
        if priority in {"P1", "P2"}:
            _tc_raw = ov.get("top_countries") or "[]"
            try:
                _tc_list = _json.loads(_tc_raw) if isinstance(_tc_raw, str) else (_tc_raw or [])
                _top_country = str(_tc_list[0]).upper() if _tc_list else ""
            except Exception:
                _top_country = ""
            if _top_country in {"IN", "IND", "PK", "PAK"}:
                priority = "P3"

        rows.append({
            # Identity
            "app_market_bundle":     bundle,
            "os":                    app["os"],
            "unified_app_id":        uid,
            "app_name":              app.get("app_name") or "",
            "company_name":          app.get("company_name") or "",
            "publisher_name":        app.get("publisher_name") or "",
            "hq_country":            app.get("hq_country") or "",
            "website":               app.get("website") or None,
            "team_routing":          "Gaming" if is_gaming else "Non-Gaming",
            "genre":                 app.get("genre") or None,
            "monetization_type":     mon_type,
            "has_ads":               bool(has_ads) if has_ads is not None else None,
            "has_iap":               bool(has_iap) if has_iap is not None else None,
            # ST overview
            "publisher_email":       ov.get("publisher_email"),
            "publisher_country":     ov.get("publisher_country"),
            "rating":                ov.get("rating"),
            "global_rating_count":   ov.get("global_rating_count"),
            "top_countries":         ov.get("top_countries"),
            "sdk_insights_supported":ov.get("sdk_insights_supported"),
            "release_date":          ov.get("release_date"),
            "updated_date":          ov.get("updated_date"),
            # Downloads
            "st_last_month_downloads":ov.get("st_last_month_downloads"),
            "st_daily_downloads_avg": round(ov["st_last_month_downloads"] / _last_month_end.day) if ov.get("st_last_month_downloads") else None,
            # MAU
            "mau_ww":                mau_map.get(uid) if uid else None,
            # Channels
            "paid_frac":             ch.get("paid_frac"),
            "organic_frac":          ch.get("organic_frac"),
            "paid_abs":              ch.get("paid_abs"),
            "organic_abs":           ch.get("organic_abs"),
            "paid_search_frac":      ch.get("paid_search_frac"),
            "paid_search_abs":       ch.get("paid_search_abs"),
            # SDKs
            "installed_sdk_count":   sdk.get("installed_sdk_count"),
            "installed_sdks":        sdk.get("installed_sdks"),
            "uninstalled_sdks":      sdk.get("uninstalled_sdks"),
            # Network SOV (last complete month, top-3 countries, fixed networks)
            "active_ua_networks":    nw.get("active_ua_networks"),
            "peak_sov":              nw.get("peak_sov"),
            # Moloco supply
            "is_moloco_supply_visible": bool(sv.get("is_supply_partner")) if sv else False,
            "moloco_media_cost_30d":    float(sv.get("moloco_media_cost_30d") or 0) if sv else 0.0,
            "moloco_bid_requests":      int(sv.get("moloco_bid_requests") or 0) if sv else 0,
            "eligibility_status":       sv.get("eligibility_status") if sv else None,
            "priority":                 priority,
            "data_as_of":               today_str,
            # Supply team's top-2000 BD target list (already-assigned ones excluded in COLD_APPS_SQL)
            "is_supply_top2000":        bool(app.get("is_supply_top2000")),
            "supply_top2000_rank":      app.get("supply_top2000_rank"),
            "supply_bd_rep":            app.get("supply_bd_rep"),
            # Moloco historical advertiser (24-month lookback)
            "moloco_advertiser_title":  hist.get("moloco_advertiser_title"),
            "moloco_platform_id":       hist.get("moloco_platform_id"),
            "moloco_advertiser_gm":     hist.get("moloco_advertiser_gm"),
            "moloco_advertiser_nbs":    hist.get("moloco_advertiser_nbs"),
            "moloco_last_active":       hist.get("moloco_last_active"),
            # Chinese entity — populated later by enrich_and_join_entities()
            "chinese_entity":             None,
            "chinese_address":            None,
            "company_background":         None,
            "evidence_note":              None,
            "chinese_entity_confidence":  None,
            "chinese_entity_needs_review":None,
        })
    return rows


def bq_write(bq: bigquery.Client, rows: list[dict]) -> None:
    job = bq.load_table_from_json(
        rows, DEST_APP,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        ),
    )
    job.result()
    log.info("→ %s: %d rows (WRITE_TRUNCATE)", DEST_APP, len(rows))


SNAPSHOT_SCHEMA = SCHEMA + [F("week_of", "DATE")]


def bq_append_snapshot(bq: bigquery.Client, rows: list[dict]) -> None:
    from datetime import date
    week_of = date.today().strftime("%Y-%m-%d")
    snapshot_rows = [{**r, "week_of": week_of} for r in rows]
    job = bq.load_table_from_json(
        snapshot_rows, DEST_SNAPSHOT,
        job_config=bigquery.LoadJobConfig(
            schema=SNAPSHOT_SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        ),
    )
    job.result()
    log.info("→ %s: %d rows appended (week_of=%s)", DEST_SNAPSHOT, len(snapshot_rows), week_of)


def bq_write_company(bq: bigquery.Client) -> None:
    sql = f"""
CREATE OR REPLACE TABLE `{DEST_COMPANY}` AS
WITH ranked AS (
  SELECT *,
    CASE priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END AS priority_num
  FROM `{DEST_APP}`
)
SELECT
  company_name,
  ANY_VALUE(hq_country)                                          AS hq_country,
  ANY_VALUE(website)                                             AS website,
  ANY_VALUE(team_routing)                                        AS team_routing,
  COUNT(*)                                                       AS app_count,
  STRING_AGG(DISTINCT os ORDER BY os)                           AS os_mix,
  STRING_AGG(DISTINCT genre ORDER BY genre)                      AS genres,
  SUM(st_last_month_downloads)                                   AS total_downloads,
  SUM(mau_ww)                                                    AS total_mau,
  ROUND(MAX(paid_frac), 4)                                       AS max_paid_frac,
  CASE MIN(priority_num)
    WHEN 1 THEN 'P1' WHEN 2 THEN 'P2' ELSE 'P3'
  END                                                            AS best_priority,
  STRING_AGG(DISTINCT app_market_bundle ORDER BY app_market_bundle) AS app_bundles,
  STRING_AGG(DISTINCT monetization_type ORDER BY monetization_type) AS monetization_types,
  LOGICAL_OR(active_ua_networks IS NOT NULL)                     AS any_active_ua,
  STRING_AGG(DISTINCT active_ua_networks)                        AS all_ua_networks,
  LOGICAL_OR(is_moloco_supply_visible)                           AS any_moloco_supply,
  SUM(moloco_media_cost_30d)                                     AS total_moloco_cost_30d,
  ANY_VALUE(publisher_name)                                      AS publisher_name,
  -- Supply team's top-2000 BD target list (unassigned-only, see COLD_APPS_SQL)
  LOGICAL_OR(is_supply_top2000)                                  AS is_supply_top2000,
  MIN(supply_top2000_rank)                                       AS supply_top2000_rank,
  ANY_VALUE(installed_sdks HAVING MIN priority_num)              AS installed_sdks,
  ANY_VALUE(data_as_of)                                          AS data_as_of,
  -- Moloco historical advertiser (from best-priority app)
  ANY_VALUE(moloco_advertiser_title HAVING MIN priority_num)     AS moloco_advertiser_title,
  ANY_VALUE(moloco_platform_id HAVING MIN priority_num)          AS moloco_platform_id,
  ANY_VALUE(moloco_advertiser_gm HAVING MIN priority_num)        AS moloco_advertiser_gm,
  ANY_VALUE(moloco_advertiser_nbs HAVING MIN priority_num)       AS moloco_advertiser_nbs,
  MAX(moloco_last_active)                                        AS moloco_last_active,
  -- Chinese entity (from cache, populated after enrichment)
  ANY_VALUE(chinese_entity HAVING MIN priority_num)              AS chinese_entity,
  ANY_VALUE(chinese_address HAVING MIN priority_num)             AS chinese_address,
  ANY_VALUE(company_background HAVING MIN priority_num)          AS company_background,
  ANY_VALUE(evidence_note HAVING MIN priority_num)               AS evidence_note
FROM ranked
WHERE company_name IS NOT NULL AND TRIM(company_name) != ''
GROUP BY company_name
ORDER BY total_downloads DESC
"""
    bq.query(sql).result()
    log.info("→ %s: refreshed (WRITE_REPLACE)", DEST_COMPANY)


async def enrich_and_join_entities(bq: bigquery.Client) -> None:
    """
    Read cold_prospect_company (deduplicated, full info), look up Chinese entities
    via cache + Gemini, then JOIN results back into cold_prospect_app.
    """
    # Read company rows from BQ (already deduplicated per company)
    log.info("Reading cold_prospect_company for Chinese entity enrichment …")
    company_rows = [
        dict(r)
        for r in bq.query(
            f"SELECT company_name, publisher_name, hq_country, website, app_bundles"
            f" FROM `{DEST_COMPANY}`"
            f" WHERE company_name IS NOT NULL AND TRIM(company_name) != ''"
        ).result()
    ]
    log.info("  %d companies to process", len(company_rows))

    await enrich_chinese_entities(bq, company_rows)

    # JOIN cache back into cold_prospect_app via CREATE OR REPLACE TABLE
    log.info("Joining Chinese entity cache back into cold_prospect_app …")
    join_sql = f"""
CREATE OR REPLACE TABLE `{DEST_APP}` AS
SELECT
  a.* EXCEPT(chinese_entity, chinese_address, company_background, evidence_note, chinese_entity_confidence, chinese_entity_needs_review),
  c.chinese_entity,
  c.chinese_address,
  c.company_background,
  c.evidence_note,
  c.confidence    AS chinese_entity_confidence,
  c.needs_review  AS chinese_entity_needs_review
FROM `{DEST_APP}` a
LEFT JOIN `{DEST_ENTITY_CACHE}` c
  ON LOWER(TRIM(a.company_name)) = c.company_key
"""
    bq.query(join_sql).result()
    log.info("→ %s: Chinese entity columns updated", DEST_APP)


def bq_ensure_conversion_view(bq: bigquery.Client) -> None:
    sql = f"""
CREATE OR REPLACE VIEW `{DEST_CONVERSION}` AS
WITH
prospect_history AS (
  SELECT DISTINCT
    app_market_bundle,
    app_name,
    company_name,
    MIN(week_of) AS first_seen_week,
    MAX(week_of) AS last_seen_week,
    COUNT(DISTINCT week_of) AS weeks_in_list
  FROM `{DEST_SNAPSHOT}`
  GROUP BY 1, 2, 3
),
moloco_state AS (
  SELECT
    app_bundle,
    is_moloco_sdk_app,
    is_moloco_advertiser_app
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  WHERE is_moloco_sdk_app = true OR is_moloco_advertiser_app = true
)
SELECT
  h.app_market_bundle,
  h.app_name,
  h.company_name,
  h.first_seen_week,
  h.last_seen_week,
  h.weeks_in_list,
  CASE
    WHEN m.is_moloco_sdk_app AND m.is_moloco_advertiser_app THEN 'SDK+UA'
    WHEN m.is_moloco_sdk_app                                THEN 'SDK'
    WHEN m.is_moloco_advertiser_app                         THEN 'UA'
  END AS conversion_type,
  DATE_DIFF(CURRENT_DATE(), h.first_seen_week, WEEK) AS weeks_to_convert
FROM prospect_history h
INNER JOIN moloco_state m ON h.app_market_bundle = m.app_bundle
"""
    bq.query(sql).result()
    log.info("→ %s: view refreshed", DEST_CONVERSION)


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run() -> None:
    bq = bigquery.Client(project="ads-bpd-guard-sandbox")
    t0 = time.time()

    # 1. Cold prospect app list from BQ
    cold_apps = bq_get_cold_apps(bq)
    if not cold_apps:
        log.warning("No cold prospect apps found — aborting.")
        return

    bundles = [a["app_market_bundle"] for a in cold_apps]

    async with httpx.AsyncClient(base_url=ST_BASE, timeout=httpx.Timeout(120.0)) as client:

        # 2. Overview + SDK → also extracts unified_app_id per bundle
        overview_map, sdk_map = await fetch_overview_and_sdk(client, cold_apps)

        # Collect all unified_app_ids (apps ST knows about)
        unified_ids = sorted({
            ov["unified_app_id"]
            for ov in overview_map.values()
            if ov.get("unified_app_id")
        })
        log.info("Resolved %d / %d apps to unified_app_id", len(unified_ids), len(cold_apps))

        # 3–4. Enrichment via unified endpoints
        channels_map = await fetch_channels(client, unified_ids)
        mau_map      = await fetch_mau(client, unified_ids)

        # 5. Network SOV — per-app, filtered to top-3 countries + fixed networks
        #    Uses last complete month to avoid partial-month bias and keep payloads small
        uid_countries: list[tuple[str, list[str]]] = []
        for bundle, ov in overview_map.items():
            uid = ov.get("unified_app_id") or ""
            if not uid:
                continue
            raw = ov.get("top_countries") or "[]"
            try:
                countries = _json.loads(raw) if isinstance(raw, str) else (raw or [])
            except Exception:
                countries = []
            valid = [c for c in countries if c in _SOV_VALID_COUNTRIES]
            uid_countries.append((uid, valid[:3]))
        network_map = await fetch_network_sov(client, uid_countries)

    # 6. Moloco supply data from BQ
    log.info("Loading Moloco supply data from BQ …")
    supply_map  = bq_get_supply(bq, bundles)
    history_map = bq_get_moloco_history(bq, bundles)
    log.info("Moloco history (24mo): %d apps matched", len(history_map))

    # 7. Merge + write cold_prospect_app (entity columns NULL initially)
    rows = build_rows(cold_apps, overview_map, sdk_map, channels_map, mau_map, supply_map, network_map, history_map)

    bq_write(bq, rows)                   # cold_prospect_app (WRITE_TRUNCATE, entity NULL)
    bq_append_snapshot(bq, rows)         # prospect_snapshot (WRITE_APPEND)
    bq_write_company(bq)                 # cold_prospect_company v1 (for enrichment to read from)

    # 8. Chinese entity enrichment: read from cold_prospect_company → Gemini → join back to cold_prospect_app
    await enrich_and_join_entities(bq)

    bq_write_company(bq)                 # cold_prospect_company v2 (pick up enriched entity fields)
    bq_ensure_conversion_view(bq)        # prospect_conversion view

    elapsed = time.time() - t0
    st_hit = sum(1 for a in cold_apps if overview_map.get(a["app_market_bundle"], {}).get("unified_app_id"))
    log.info(
        "Pipeline complete in %.1fs — %d apps total, %d ST enriched, %d no ST match",
        elapsed, len(rows), st_hit, len(rows) - st_hit,
    )


if __name__ == "__main__":
    asyncio.run(run())
