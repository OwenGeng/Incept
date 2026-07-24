"""
Mini-pipeline: fetch st_app_overview + st_sdk_tags for cold prospect apps only.
Input:  /tmp/cold_prospect_ids.json  (produced by BQ query)
Output: appends/replaces st_app_overview and st_sdk_tags in BQ

Run:
  cd /Users/owen.geng/Documents/Projects/Incept/apps/api
  source .venv/bin/activate && set -a && source .env && set +a
  python -m app.incept.cold_prospect_overview
"""
import asyncio, json, logging, os
from datetime import date

import httpx
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ST_TOKEN = os.environ["SENSORTOWER_API_KEY"]
ST_BASE  = "https://api.sensortower.com"
DATASET  = "ads-bpd-guard-sandbox.sensortower_new"
IDS_FILE = "/tmp/cold_prospect_ids.json"
BATCH    = 25
_fetched = date.today().isoformat()

OVERVIEW_SCHEMA = [
    bigquery.SchemaField("unified_app_id",        "STRING"),
    bigquery.SchemaField("platform_app_id",        "STRING"),
    bigquery.SchemaField("platform",               "STRING"),
    bigquery.SchemaField("name",                   "STRING"),
    bigquery.SchemaField("bundle_id",              "STRING"),
    bigquery.SchemaField("publisher_name",         "STRING"),
    bigquery.SchemaField("publisher_id",           "STRING"),
    bigquery.SchemaField("publisher_country",      "STRING"),
    bigquery.SchemaField("publisher_email",        "STRING"),
    bigquery.SchemaField("active",                 "BOOL"),
    bigquery.SchemaField("release_date",           "DATE"),
    bigquery.SchemaField("updated_date",           "DATE"),
    bigquery.SchemaField("version",                "STRING"),
    bigquery.SchemaField("rating",                 "FLOAT64"),
    bigquery.SchemaField("global_rating_count",    "INTEGER"),
    bigquery.SchemaField("rating_count",           "INTEGER"),
    bigquery.SchemaField("in_app_purchases",       "BOOL"),
    bigquery.SchemaField("price",                  "FLOAT64"),
    bigquery.SchemaField("content_rating",         "STRING"),
    bigquery.SchemaField("top_countries",          "STRING"),
    bigquery.SchemaField("categories",             "STRING"),
    bigquery.SchemaField("supported_languages",    "STRING"),
    bigquery.SchemaField("last_month_downloads",   "INTEGER"),
    bigquery.SchemaField("last_month_revenue",     "INTEGER"),
    bigquery.SchemaField("sdk_insights_supported", "BOOL"),
    bigquery.SchemaField("fetched_at",             "DATE"),
]

SDK_SCHEMA = [
    bigquery.SchemaField("unified_app_id",  "STRING"),
    bigquery.SchemaField("platform",        "STRING"),
    bigquery.SchemaField("sdk_id",          "INTEGER"),
    bigquery.SchemaField("sdk_name",        "STRING"),
    bigquery.SchemaField("company_name",    "STRING"),
    bigquery.SchemaField("sdk_types",       "STRING"),
    bigquery.SchemaField("apps_installed",  "INTEGER"),
    bigquery.SchemaField("install_date",    "DATE"),
    bigquery.SchemaField("uninstall_date",  "DATE"),
    bigquery.SchemaField("days_installed",  "INTEGER"),
    bigquery.SchemaField("sdk_status",      "STRING"),
    bigquery.SchemaField("fetched_at",      "DATE"),
]


async def _get(client, path, params, total_timeout=120.0):
    p = dict(params, auth_token=ST_TOKEN)
    backoff = 1.0
    for attempt in range(5):
        try:
            resp = await asyncio.wait_for(client.get(path, params=p), timeout=total_timeout)
        except asyncio.TimeoutError:
            log.warning("ST %s → TotalTimeout, retry %d/5", path, attempt + 1)
            await asyncio.sleep(backoff); backoff = min(backoff * 2, 16.0); continue
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            log.warning("ST %s → %s, retry %d/5", path, exc.__class__.__name__, attempt + 1)
            await asyncio.sleep(backoff); backoff = min(backoff * 2, 16.0); continue
        if resp.status_code in (429, 500, 502, 503, 504):
            log.warning("ST %s → %d, retry %d/5", path, resp.status_code, attempt + 1)
            await asyncio.sleep(backoff); backoff = min(backoff * 2, 16.0); continue
        if not resp.is_success:
            log.warning("ST %s → %d: %s", path, resp.status_code, resp.text[:200])
            return None
        return resp.json()
    log.error("ST %s → exhausted retries", path)
    return None


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


async def fetch_overview_sdk(client, unified_ids, ios_map, android_map):
    import json as _json
    overview_rows, sdk_rows = [], []

    def _parse(app, platform, uid):
        hd = app.get("humanized_worldwide_last_month_downloads") or {}
        hr = app.get("humanized_worldwide_last_month_revenue") or {}
        overview_rows.append({
            "unified_app_id":        uid,
            "platform_app_id":       str(app.get("app_id") or ""),
            "platform":              platform,
            "name":                  str(app.get("name") or ""),
            "bundle_id":             str(app.get("bundle_id") or ""),
            "publisher_name":        str(app.get("publisher_name") or ""),
            "publisher_id":          str(app.get("publisher_id") or ""),
            "publisher_country":     str(app.get("publisher_country") or ""),
            "publisher_email":       str(app.get("publisher_email") or "") or None,
            "active":                bool(app.get("active")),
            "release_date":          (app.get("release_date") or "")[:10] or None,
            "updated_date":          (app.get("updated_date") or "")[:10] or None,
            "version":               str(app.get("version") or "") or None,
            "rating":                float(app.get("rating") or 0.0),
            "global_rating_count":   int(app.get("global_rating_count") or 0),
            "rating_count":          int(app.get("rating_count") or 0),
            "in_app_purchases":      bool(app.get("in_app_purchases")),
            "price":                 float(app.get("price") or 0.0),
            "content_rating":        str(app.get("content_rating") or "") or None,
            "top_countries":         _json.dumps(app.get("top_countries") or []),
            "categories":            _json.dumps(app.get("categories") or []),
            "supported_languages":   _json.dumps(app.get("supported_languages") or []),
            "last_month_downloads":  int(hd.get("downloads") or 0) or None,
            "last_month_revenue":    int(hr.get("revenue") or 0) or None,
            "sdk_insights_supported": bool(app.get("sdk_insights_supported")),
            "fetched_at":            _fetched,
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
        ids = list(id_map.keys())
        log.info("%s: %d apps → %d calls", platform, len(ids), (len(ids) + BATCH - 1) // BATCH)
        done = 0
        for batch in _chunks(ids, BATCH):
            data = await _get(client, f"/v1/{platform}/apps", {
                "app_ids":          ",".join(batch),
                "country":          "US",
                "include_sdk_data": "true",
            }, total_timeout=120.0)
            for app in (data or {}).get("apps") or []:
                pid = str(app.get("app_id") or "")
                uid = id_map.get(pid) or ""
                if uid:
                    _parse(app, platform, uid)
            done += len(batch)
            log.info("  %s %d/%d apps processed", platform, done, len(ids))
            await asyncio.sleep(0.2)

    return overview_rows, sdk_rows


def bq_write_append(bq, table_id, rows, schema, truncate=False):
    if not rows:
        log.warning("No rows for %s", table_id); return
    disposition = (bigquery.WriteDisposition.WRITE_TRUNCATE if truncate
                   else bigquery.WriteDisposition.WRITE_APPEND)
    job = bq.load_table_from_json(
        rows, f"{DATASET}.{table_id}",
        job_config=bigquery.LoadJobConfig(
            schema=schema,
            write_disposition=disposition,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        ),
    )
    job.result()
    mode = "truncate+write" if truncate else "append"
    log.info("→ %s: %d rows (%s)", table_id, len(rows), mode)


async def main():
    with open(IDS_FILE) as f:
        records = json.load(f)

    ios_map:     dict[str, str] = {}
    android_map: dict[str, str] = {}
    for r in records:
        uid = r["unified_app_id"]
        if r.get("app_id_ios"):
            ios_map[r["app_id_ios"]] = uid
        if r.get("app_id_android"):
            android_map[r["app_id_android"]] = uid

    log.info("Cold prospect apps: %d total, %d iOS, %d Android",
             len(records), len(ios_map), len(android_map))

    bq = bigquery.Client(project="ads-bpd-guard-sandbox")

    # Clear existing cold prospect rows first (delete by unified_app_id)
    uids = "', '".join(r["unified_app_id"] for r in records)
    for table in ["st_app_overview", "st_sdk_tags"]:
        try:
            bq.query(f"DELETE FROM `{DATASET}.{table}` WHERE unified_app_id IN ('{uids}')").result()
            log.info("Cleared existing rows from %s", table)
        except Exception as e:
            log.warning("Could not clear %s: %s", table, e)

    async with httpx.AsyncClient(base_url=ST_BASE, timeout=httpx.Timeout(60.0)) as client:
        overview_rows, sdk_rows = await fetch_overview_sdk(client, records, ios_map, android_map)

    log.info("Fetched: %d overview rows, %d SDK rows", len(overview_rows), len(sdk_rows))
    bq_write_append(bq, "st_app_overview", overview_rows, OVERVIEW_SCHEMA)
    # WRITE_TRUNCATE: old st_sdk_tags has incompatible schema (tag_name/tag_value);
    # truncate replaces it entirely with new schema (sdk_id, sdk_name, sdk_status, ...)
    bq_write_append(bq, "st_sdk_tags",     sdk_rows,     SDK_SCHEMA, truncate=True)
    log.info("Cold prospect overview pipeline complete.")


if __name__ == "__main__":
    asyncio.run(main())
