#!/usr/bin/env python3
"""
Quick probe: fetch 5 unified app IDs from app_iq_v3 and print raw API responses
for downloads_by_sources, sdk_tags, creatives, and top_apps_search.
Run: python probe_st.py
"""
import asyncio, json, os
from datetime import date, timedelta
import httpx
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TOKEN = os.environ.get("SENSORTOWER_API_KEY") or os.environ["SENSOR_TOWER_API_TOKEN"]
BASE  = "https://api.sensortower.com"
TODAY = date.today()
START = (TODAY - timedelta(days=90)).replace(day=1)

async def get(client, path, params):
    r = await client.get(path, params=dict(params, auth_token=TOKEN))
    if not r.is_success:
        print(f"  ERROR {r.status_code} {path}: {r.text[:500]}")
        return None
    return r.json()

def pp(label, data):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    # truncate to first 3000 chars so output stays readable
    print(text[:3000] + ("\n... (truncated)" if len(text) > 3000 else ""))

async def main():
    # Top paid-UA apps from fact_app_basis_v3 US (pre-queried, 1.9-2.5M paid_ads_dl/month)
    ids = [
        "662dcccbf7baf07a73491020",
        "613aafdee8b8ad2c7f063b8e",
        "64a72c98ad4adb0e06dbc506",
        "68706c3c80620041196fd150",
        "5deb3ac1a766b862aa66683b",
    ]
    print(f"Probing {len(ids)} known high-UA apps")

    id1 = ids[0]
    ids_str = ",".join(ids)

    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:

        # ── App metadata with app_id_type=unified ────────────────────────────
        pp("1. app metadata (app_id_type=unified)", await get(c, "/v1/unified/apps", {
            "app_ids":     ids_str,
            "app_id_type": "unified",
            "country":     "US",
        }))

        await asyncio.sleep(0.3)

        # ── Downloads by sources ──────────────────────────────────────────────
        pp("2. downloads_by_sources", await get(c, "/v1/unified/downloads_by_sources", {
            "app_ids":          ids_str,
            "app_id_type":      "unified",
            "countries":        "WW",
            "start_date":       START.isoformat(),
            "end_date":         TODAY.isoformat(),
            "date_granularity": "monthly",
        }))
        await asyncio.sleep(0.3)

        # ── SDK tags ──────────────────────────────────────────────────────────
        pp("3. sdk tags (developer_integrations)", await get(c, "/v1/app_tag/tags_for_apps", {
            "app_ids":            ids_str,
            "app_id_type":        "unified",
            "field_categories[]": "developer_integrations",
        }))
        await asyncio.sleep(0.3)

        # ── Top Creatives (market-wide, one network at a time) ───────────────
        pp("4. creatives/top (Facebook, Overall)", await get(c, "/v1/unified/ad_intel/creatives/top", {
            "date":     START.isoformat(),
            "period":   "month",
            "category": "0",
            "country":  "US",
            "network":  "Facebook",
            "ad_types": "video,image",
            "limit":    "10",
        }))
        await asyncio.sleep(0.3)

        # ── Top advertiser rank (WW not supported, use US) ───────────────────
        pp("5. top_apps/search (advertiser rank, US)", await get(c, "/v1/unified/ad_intel/top_apps/search", {
            "app_id":      id1,
            "app_id_type": "unified",
            "role":        "advertisers",
            "date":        TODAY.replace(day=1).isoformat(),
            "period":      "month",
            "country":     "US",
            "network":     "All Networks",
        }))
        await asyncio.sleep(0.3)

        # ── Network analysis ──────────────────────────────────────────────────
        pp("6. network_analysis", await get(c, "/v1/unified/ad_intel/network_analysis", {
            "app_ids":     id1,
            "app_id_type": "unified",
            "start_date":  START.isoformat(),
            "end_date":    TODAY.isoformat(),
            "period":      "month",
        }))

if __name__ == "__main__":
    asyncio.run(main())
