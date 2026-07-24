"""
SDK Reference Table — full metadata for all SDKs found in cold_prospect_enriched.

Source: GET /v1/sdk/summary_metrics (max 100 sdk_ids per call)
Schema mirrors all fields from the API response + derived type/category name columns.

Run:
  cd /Users/owen.geng/Documents/Projects/Incept/apps/api
  source .venv/bin/activate && set -a && source .env && set +a
  python -m app.incept.sdk_reference_table
"""

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField as F

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ST_BASE  = "https://api.sensortower.com"
ST_TOKEN = os.environ.get("SENSORTOWER_API_KEY") or os.environ.get("SENSOR_TOWER_API_TOKEN", "")

DEST_TABLE = "ads-bpd-guard-sandbox.sensortower_new.sdk_reference"

SCHEMA = [
    # Core identity
    F("sdk_id",              "INTEGER"),
    F("sdk_name",            "STRING"),
    F("enabled",             "BOOLEAN"),
    F("company_name",        "STRING"),
    F("sdk_url",             "STRING"),
    F("icon_url",            "STRING"),
    F("description",         "STRING"),
    F("created_at",          "TIMESTAMP"),
    # Type / OS / Category (raw IDs as JSON, plus human-readable names)
    F("sdk_type_ids",        "STRING"),   # JSON array of int type IDs e.g. [3, 37]
    F("sdk_type_names",      "STRING"),   # comma-separated names e.g. "Ad Mediation, Ad Mediation Adapters"
    F("supported_os",        "STRING"),   # JSON array e.g. ["android","ios"]
    F("top_category_ids",    "STRING"),   # JSON array of app category IDs
    F("top_category_names",  "STRING"),   # comma-separated category names
    # Reach metrics
    F("today_apps",          "INTEGER"),  # current apps with SDK installed
    F("today_apps_average",  "INTEGER"),  # rolling average apps installed
    F("market_share",        "FLOAT64"),  # share of all apps
    F("recent_installs",     "INTEGER"),  # recent new app installs of this SDK
    F("recent_uninstalls",   "INTEGER"),  # recent app uninstalls of this SDK
    F("downloads",           "INTEGER"),  # est. total downloads of apps using this SDK
    F("downloads_share",     "FLOAT64"),  # download share across all apps
    F("revenue",             "INTEGER"),  # est. revenue of apps using this SDK
    # Top apps (app_ids of representative apps)
    F("most_downloaded_app",    "INTEGER"),
    F("highest_grossing_app",   "INTEGER"),
    F("most_active_users_app",  "INTEGER"),
    # Derived
    F("is_ua_relevant",      "BOOLEAN"),  # True if any type is ad/mediation related
    F("data_as_of",          "DATE"),
]

# SDK type IDs relevant to UA buying (from sdk_type_ids.json)
UA_RELEVANT_TYPE_IDS = {1, 2, 3, 5, 8, 24, 25, 37}  # Ad Analytics, Attribution, Mediation, Advertising, Audience, Reward, Rewarded Video, Mediation Adapters

# Static category map from category_ids.json (numeric iOS IDs)
CATEGORY_MAP: dict[int, str] = {
    0: "Overall",
    6000: "Business", 6001: "Weather", 6002: "Utilities", 6003: "Travel",
    6004: "Sports", 6005: "Social Networking", 6006: "Reference", 6007: "Productivity",
    6008: "Photo & Video", 6009: "News", 6010: "Navigation", 6011: "Music",
    6012: "Lifestyle", 6013: "Health & Fitness", 6014: "Games", 6015: "Finance",
    6016: "Entertainment", 6017: "Education", 6018: "Books", 6020: "Medical",
    6021: "Newsstand", 6023: "Food & Drink", 6024: "Shopping",
    6026: "Developer Tools", 6027: "Graphics & Design",
    7001: "Games/Action", 7002: "Games/Adventure", 7003: "Games/Casual",
    7004: "Games/Board", 7005: "Games/Card", 7006: "Games/Casino",
    7009: "Games/Family", 7011: "Games/Music", 7012: "Games/Puzzle",
    7013: "Games/Racing", 7014: "Games/Role Playing", 7015: "Games/Simulation",
    7016: "Games/Sports", 7017: "Games/Strategy", 7018: "Games/Trivia",
    7019: "Games/Word", 9007: "Kids",
    10000: "Kids/Ages 5 & Under", 10001: "Kids/Ages 6-8", 10002: "Kids/Ages 9-11",
}

# Static type map from sdk_type_ids.json
SDK_TYPE_MAP: dict[int, str] = {
    0: "A/B Testing", 1: "Ad Analytics", 2: "Ad Attribution",
    3: "Ad Mediation", 5: "Advertising Platforms", 6: "App Analytics",
    8: "Audience", 10: "Crash Reporting", 11: "Data Management",
    12: "Deep linking", 13: "Gaming", 14: "Graphics/UI",
    15: "Image Processing", 16: "Location", 17: "Marketing Automation",
    18: "Media", 19: "Networking", 20: "Payments",
    21: "Performance Management", 23: "Push Notifications",
    24: "Reward Systems", 25: "Rewarded Video Advertising",
    26: "Security", 27: "Social", 28: "Tools & Utilities",
    29: "User Authentication", 31: "User Support", 33: "Web Management",
    34: "Developer Framework", 35: "Blockchain", 36: "Augmented Reality",
    37: "Ad Mediation Adapters", 38: "Health and Fitness",
}


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> Any:
    p = dict(params, auth_token=ST_TOKEN)
    backoff = 1.0
    for attempt in range(5):
        try:
            resp = await asyncio.wait_for(client.get(path, params=p), timeout=60.0)
        except (asyncio.TimeoutError, httpx.ReadTimeout, httpx.ConnectTimeout,
                httpx.ReadError, httpx.RemoteProtocolError) as exc:
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


def bq_get_sdk_ids(bq: bigquery.Client) -> list[dict]:
    """Get unique (sdk_id, sdk_name) for SDKs in cold_prospect_enriched via st_sdk_tags join."""
    log.info("Fetching SDK IDs from BQ …")
    sql = """
WITH prospect_sdks AS (
  SELECT DISTINCT TRIM(sdk) AS sdk_name
  FROM `ads-bpd-guard-sandbox.sensortower_new.cold_prospect_enriched`,
  UNNEST(SPLIT(installed_sdks, ', ')) AS sdk
  WHERE installed_sdks IS NOT NULL
)
SELECT DISTINCT t.sdk_id, t.sdk_name
FROM `ads-bpd-guard-sandbox.sensortower_new.st_sdk_tags` t
INNER JOIN prospect_sdks p ON LOWER(TRIM(t.sdk_name)) = LOWER(p.sdk_name)
WHERE t.sdk_id IS NOT NULL AND t.sdk_id > 0
"""
    rows = list(bq.query(sql).result())
    log.info("Found %d unique SDKs with IDs", len(rows))
    return [dict(r) for r in rows]


async def fetch_summary_metrics(
    client: httpx.AsyncClient,
    sdk_ids: list[int],
) -> dict[int, dict]:
    """Returns sdk_id → full metrics dict from /v1/sdk/summary_metrics."""
    log.info("ST summary_metrics: %d SDKs → %d calls", len(sdk_ids), (len(sdk_ids) + 99) // 100)
    result: dict[int, dict] = {}

    for batch in _chunks(sdk_ids, 100):
        data = await _get(client, "/v1/sdk/summary_metrics", {
            "sdk_ids": ",".join(str(i) for i in batch),
        })
        # Response is either a plain list or {"data": [...]}
        items = data if isinstance(data, list) else (data or {}).get("data") or []
        for item in items:
            sid = item.get("id")
            if sid:
                result[int(sid)] = item
        await asyncio.sleep(0.5)

    log.info("Summary metrics fetched for %d SDKs", len(result))
    return result


def build_rows(
    sdk_list: list[dict],
    metrics_map: dict[int, dict],
) -> list[dict]:
    from datetime import date, datetime, timezone
    today = date.today().isoformat()
    rows = []

    for sdk in sdk_list:
        sdk_id = int(sdk["sdk_id"])
        m = metrics_map.get(sdk_id, {})

        type_ids   = [int(t) for t in (m.get("sdk_types") or []) if t is not None]
        type_names = [SDK_TYPE_MAP.get(t, str(t)) for t in type_ids]
        is_ua      = bool(set(type_ids) & UA_RELEVANT_TYPE_IDS)

        # Parse created_at to BQ TIMESTAMP format
        created_raw = m.get("created_at")
        created_at  = None
        if created_raw:
            try:
                created_at = datetime.fromisoformat(
                    created_raw.replace("Z", "+00:00")
                ).strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:
                created_at = None

        rows.append({
            "sdk_id":              sdk_id,
            "sdk_name":            m.get("name") or sdk.get("sdk_name") or "",
            "enabled":             bool(m.get("enabled")) if m.get("enabled") is not None else None,
            "company_name":        m.get("company_name") or "",
            "sdk_url":             m.get("sdk_url") or None,
            "icon_url":            m.get("icon_url") or None,
            "description":         m.get("description") or None,
            "created_at":          created_at,
            "sdk_type_ids":        json.dumps(type_ids) if type_ids else None,
            "sdk_type_names":      ", ".join(type_names) if type_names else None,
            "supported_os":        json.dumps(m["supported_os"]) if m.get("supported_os") else None,
            "top_category_ids":    json.dumps(m["top_categories"]) if m.get("top_categories") else None,
            "top_category_names":  ", ".join(CATEGORY_MAP.get(int(c), str(c)) for c in (m.get("top_categories") or [])) or None,
            "today_apps":          int(m["today_apps"]) if m.get("today_apps") is not None else None,
            "today_apps_average":  int(m["today_apps_average"]) if m.get("today_apps_average") is not None else None,
            "market_share":        float(m["market_share"]) if m.get("market_share") is not None else None,
            "recent_installs":     int(m["recent_installs"]) if m.get("recent_installs") is not None else None,
            "recent_uninstalls":   int(m["recent_uninstalls"]) if m.get("recent_uninstalls") is not None else None,
            "downloads":           int(m["downloads"]) if m.get("downloads") is not None else None,
            "downloads_share":     float(m["downloads_share"]) if m.get("downloads_share") is not None else None,
            "revenue":             int(m["revenue"]) if m.get("revenue") is not None else None,
            "most_downloaded_app":    int(m["most_downloaded_app"]) if m.get("most_downloaded_app") is not None else None,
            "highest_grossing_app":   int(m["highest_grossing_app"]) if m.get("highest_grossing_app") is not None else None,
            "most_active_users_app":  int(m["most_active_users_app"]) if m.get("most_active_users_app") is not None else None,
            "is_ua_relevant":      is_ua,
            "data_as_of":          today,
        })

    return rows


def bq_write(bq: bigquery.Client, rows: list[dict]) -> None:
    job = bq.load_table_from_json(
        rows, DEST_TABLE,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        ),
    )
    job.result()
    log.info("→ %s: %d rows (WRITE_TRUNCATE)", DEST_TABLE, len(rows))


async def run() -> None:
    bq = bigquery.Client(project="ads-bpd-guard-sandbox")

    sdk_list = bq_get_sdk_ids(bq)
    if not sdk_list:
        log.warning("No SDKs found — aborting.")
        return

    sdk_ids = list({int(s["sdk_id"]) for s in sdk_list})
    log.info("Unique SDK IDs: %d", len(sdk_ids))

    async with httpx.AsyncClient(base_url=ST_BASE, timeout=httpx.Timeout(60.0)) as client:
        metrics_map = await fetch_summary_metrics(client, sdk_ids)

    rows = build_rows(sdk_list, metrics_map)
    bq_write(bq, rows)
    log.info("Done. %d SDK records written.", len(rows))


if __name__ == "__main__":
    asyncio.run(run())
