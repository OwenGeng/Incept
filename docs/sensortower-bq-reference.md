# BigQuery Reference — SensorTower & Supply SMB

Quick reference for all BQ tables used in the Incept cold-prospect and Supply SMB pipelines.

---

## Source Tables (read-only, managed by SensorTower ingestion)

### `ads-bpd-guard-china.sensortower.app_iq_v3`

Canonical registry of all SensorTower-tracked apps with their unified IDs.

| Column | Type | Notes |
|--------|------|-------|
| `app_id` | STRING | **Unified app ID** — 24-char MongoDB ObjectID hex (e.g. `64665f59b3ae2712001279ed`) |
| _(other metadata columns)_ | — | Name, publisher, category, etc. |

**Key facts:**
- Has **multiple rows per `app_id`** (one per platform/region variant) — always use `DISTINCT` or `GROUP BY app_id` when pulling IDs
- This is the authoritative source of unified IDs; use it as the join key to all other ST tables
- All SensorTower API endpoints that accept `app_id_type=unified` use this ID format

---

### `ads-bpd-guard-china.sensortower.fact_app_basis_v3`

Daily download, revenue, channel, and usage data. One row per **app × date × OS × country**.

| Column | Type | Notes |
|--------|------|-------|
| `date_utc` | DATE | **Partition key** — must filter on this in every query |
| `unified_app_id` | STRING | Joins to `app_iq_v3.app_id` |
| `os` | STRING | `ios` or `android` — each day has separate iOS and Android rows |
| `country` | STRING | **Full country name** e.g. `"United States"`, NOT ISO code `"US"` |
| `daily.revenue` | NUMERIC | Daily revenue (USD) |
| `daily.download.all` | INTEGER | Daily total downloads ✅ populated every day |
| `daily.download.free` | INTEGER | Free downloads |
| `daily.download.paid` | INTEGER | Paid downloads |
| `daily.channel.paid_ads` | INTEGER | Downloads attributed to paid ads |
| `daily.channel.paid` | INTEGER | Total paid channel downloads |
| `daily.channel.organic` | INTEGER | Organic downloads |
| `daily.channel.organic_search` | INTEGER | Organic search downloads |
| `daily.channel.paid_search` | INTEGER | Paid search downloads |
| `daily.channel.web_browser` | INTEGER | Web/browser downloads |
| `daily.usage.active_users` | INTEGER | DAU |
| `daily.usage.sessions` | INTEGER | Session count |
| `weekly.*` | — | Same sub-fields as `daily.*` — populated on week-start days only |
| `monthly.*` | — | Same sub-fields as `daily.*` — **populated on the 1st of each month only**, NULL all other days |

**Critical gotchas:**
- `monthly.download.all` is **only non-NULL on the 1st of each month** — do NOT use `SUM(monthly.download.all)` over multi-day date ranges, you'll get wildly wrong numbers or accidental correct-looking results
- `SUM(daily.download.all)` over 30 days = effective monthly global downloads (sums iOS + Android + all countries)
- Country is stored as full English name — `country = "United States"` not `"US"`
- Always include a `date_utc` filter or BQ will scan the full table (expensive)

**Standard filter for "top apps by monthly downloads":**
```sql
SELECT unified_app_id, SUM(daily.download.`all`) AS total_dl
FROM `ads-bpd-guard-china.sensortower.fact_app_basis_v3`
WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1
HAVING total_dl > 5000   -- ~167 global downloads/day threshold
ORDER BY total_dl DESC
```

**Join to app_iq_v3 for unified IDs (dedup):**
```sql
SELECT v.app_id
FROM `ads-bpd-guard-china.sensortower.app_iq_v3` v
JOIN (
  SELECT unified_app_id, SUM(daily.download.`all`) AS total_dl
  FROM `ads-bpd-guard-china.sensortower.fact_app_basis_v3`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  GROUP BY 1
  HAVING total_dl > 5000
) d ON v.app_id = d.unified_app_id
GROUP BY v.app_id, d.total_dl   -- GROUP BY deduplicates multi-row app_iq_v3
ORDER BY d.total_dl DESC
```

**Paid UA signal query:**
```sql
SELECT
  unified_app_id,
  country,
  SUM(daily.channel.paid_ads) AS paid_ads_dl,
  SUM(daily.download.all)     AS total_dl,
  SAFE_DIVIDE(SUM(daily.channel.paid_ads), SUM(daily.download.all)) AS paid_frac
FROM `ads-bpd-guard-china.sensortower.fact_app_basis_v3`
WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND country = "United States"
GROUP BY 1, 2
HAVING paid_ads_dl > 10000
ORDER BY paid_ads_dl DESC
```

---

## Pipeline Output Tables (written by `sensortower_pipeline.py`)

**Dataset:** `ads-bpd-guard-sandbox.sensortower_new`  
**Refresh:** Weekly WRITE_TRUNCATE  
**App coverage:** Apps with global monthly downloads > 5,000 (threshold in `APP_IDS_QUERY`)

---

### `st_app_metadata`

Basic app and publisher info from ST `/v1/unified/apps`.

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | Primary key |
| `name` | STRING | App display name |
| `canonical_app_id` | STRING | ST canonical ID |
| `app_id_ios` | STRING | iTunes numeric ID (needed for platform-specific API calls) |
| `app_id_android` | STRING | Android package name (e.g. `com.example.app`) |
| `unified_publisher_id` | STRING | Publisher unified ID |
| `fetched_at` | DATE | Pipeline run date |

---

### `st_unified_id_map`

Derived mapping between unified IDs and platform-specific IDs. No direct API call — extracted from metadata.

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | |
| `app_id_ios` | STRING | iTunes numeric ID |
| `app_id_android` | STRING | Android package name |
| `app_name` | STRING | |
| `fetched_at` | DATE | |

**Use case:** Required before calling any ST API endpoint that doesn't accept `app_id_type=unified` (e.g. `tags_for_apps` SDK detection).

---

### `st_network_sov`

Ad network share-of-voice time series from `/v1/unified/ad_intel/network_analysis`.

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | |
| `country` | STRING | ISO code e.g. `"US"` (ST API returns ISO here, unlike fact_app_basis_v3) |
| `network` | STRING | e.g. `"Facebook"`, `"TikTok"` |
| `period_date` | DATE | Month start date |
| `sov` | FLOAT64 | Share of voice (0–1 fraction) |
| `fetched_at` | DATE | |

**Note:** `WW` (worldwide) is not supported — only specific country codes.

---

### `st_download_channels`

Paid vs organic channel breakdown from `/v1/unified/downloads_by_sources`. Global (WW) supported.

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | |
| `period_date` | DATE | Month start date |
| `paid_abs` | INTEGER | Paid channel absolute downloads |
| `organic_abs` | INTEGER | Organic absolute downloads |
| `paid_search_abs` | INTEGER | Paid search absolute downloads |
| `browser_abs` | INTEGER | Browser/web absolute downloads |
| `paid_frac` | FLOAT64 | Paid fraction (0–1) |
| `organic_frac` | FLOAT64 | Organic fraction (0–1) |
| `paid_search_frac` | FLOAT64 | Paid search fraction (0–1) |
| `browser_frac` | FLOAT64 | Browser fraction (0–1) |
| `fetched_at` | DATE | |

**Cold prospect signal:** `paid_frac > 0.5` = majority of downloads from paid channels = active UA spender.

---

### `st_sdk_tags`

SDK/MMP integration detection from `/v1/app_tag/tags_for_apps`.

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | |
| `platform_app_id` | STRING | The platform-specific ID used for the lookup (iOS numeric or Android package) |
| `platform` | STRING | `"ios"` or `"android"` |
| `tag_name` | STRING | SDK category e.g. `"Moloco"`, `"AppsFlyer"`, `"Adjust"` |
| `tag_value` | STRING | Integration detail / SDK version |
| `fetched_at` | DATE | |

**Note:** This endpoint does NOT accept unified IDs — platform-specific IDs are resolved from `st_unified_id_map` first.

**Check if app has Moloco SDK:**
```sql
SELECT DISTINCT unified_app_id
FROM `ads-bpd-guard-sandbox.sensortower_new.st_sdk_tags`
WHERE LOWER(tag_name) LIKE '%moloco%'
```

---

### `st_creatives_count`

Top advertiser presence per network from `/v1/unified/ad_intel/creatives/top`.

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | |
| `period_start` | DATE | Lookback start |
| `period_end` | DATE | Lookback end |
| `creative_count` | INTEGER | Number of times this app appeared in top-250 creatives across all queried networks |
| `available_network_count` | INTEGER | Number of distinct networks where this app appeared as a top advertiser |
| `available_networks` | STRING | JSON array string e.g. `'["Facebook","TikTok"]'` |
| `fetched_at` | DATE | |

**How it works:** Pipeline calls `creatives/top` (market-wide top-250) for each of 12 major networks and checks if the target app appears. `creative_count > 0` = confirmed top advertiser on at least one network.

**Networks checked:** Facebook, Instagram, TikTok, Applovin, Admob, Unity, Mintegral, Moloco, Pangle, Vungle, Meta Audience Network, Snapchat

---

### `st_downloads_monthly`

Monthly download + revenue estimates from `/v1/unified/sales_report_estimates`.

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | |
| `period_date` | DATE | Month start date |
| `downloads` | INTEGER | Monthly downloads (unified iOS + Android) |
| `revenue_usd` | FLOAT64 | Monthly revenue (USD) |
| `fetched_at` | DATE | |

---

### `st_active_users`

DAU/MAU data from `/v1/unified/usage/active_users`. **Currently skipped in pipeline** (batch=4 makes it very slow; ~77 min for 43K apps).

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | |
| `country` | STRING | ISO code |
| `period_date` | DATE | |
| `granularity` | STRING | `"daily"` (API ignores monthly requests, always returns daily) |
| `active_users` | INTEGER | Sum of `android_users + ipad_users + iphone_users` |
| `fetched_at` | DATE | |

---

### `st_advertiser_rank`

Advertiser rank among peers from `/v1/unified/ad_intel/top_apps/search`.

| Column | Type | Notes |
|--------|------|-------|
| `unified_app_id` | STRING | |
| `country` | STRING | ISO code |
| `period_date` | DATE | Month start |
| `rank` | INTEGER | Advertiser rank (lower = bigger spender) |
| `page` | INTEGER | Which page of results this rank was found on |
| `sov` | FLOAT64 | Share of voice |
| `fetched_at` | DATE | |

**Coverage:** Sampled to top 300 apps by download (configurable via `ST_RANK_SAMPLE` env var) × 7 countries: US, CN, JP, KR, DE, GB, FR. WW not supported by this endpoint.

---

## Cold Prospect Scoring Reference

### Approach 1 — Paid UA heavy hitters

```sql
SELECT
  m.name,
  c.paid_frac,
  c.paid_abs,
  cr.available_networks,
  s.tag_name AS sdk
FROM `ads-bpd-guard-sandbox.sensortower_new.st_download_channels` c
JOIN `ads-bpd-guard-sandbox.sensortower_new.st_app_metadata` m USING (unified_app_id)
LEFT JOIN `ads-bpd-guard-sandbox.sensortower_new.st_creatives_count` cr USING (unified_app_id)
LEFT JOIN `ads-bpd-guard-sandbox.sensortower_new.st_sdk_tags` s
  ON c.unified_app_id = s.unified_app_id AND LOWER(s.tag_name) LIKE '%moloco%'
WHERE c.paid_frac > 0.5
  AND c.paid_abs > 20000
  AND s.unified_app_id IS NULL  -- no Moloco SDK
ORDER BY c.paid_abs DESC
```

### Approach 2 — Top advertiser rank

```sql
SELECT
  m.name,
  r.country,
  r.rank,
  r.sov
FROM `ads-bpd-guard-sandbox.sensortower_new.st_advertiser_rank` r
JOIN `ads-bpd-guard-sandbox.sensortower_new.st_app_metadata` m USING (unified_app_id)
LEFT JOIN `ads-bpd-guard-sandbox.sensortower_new.st_sdk_tags` s
  ON r.unified_app_id = s.unified_app_id AND LOWER(s.tag_name) LIKE '%moloco%'
WHERE r.rank <= 50
  AND r.country = 'US'
  AND s.unified_app_id IS NULL  -- no Moloco SDK
ORDER BY r.rank ASC
```

---

## Pipeline Config

| Env var | Default | Description |
|---------|---------|-------------|
| `ST_BQ_DATASET` | `ads-bpd-guard-sandbox.sensortower_new` | Output dataset |
| `ST_APP_IDS_QUERY` | See pipeline file | BQ query to load app IDs |
| `ST_LOOKBACK_DAYS` | `90` | API lookback window |
| `ST_RANK_SAMPLE` | `300` | Max apps for advertiser rank (slow endpoint) |
| `SENSORTOWER_API_KEY` | — | Required in `.env` |

---

---

# Supply SMB Tables

Tables used in the cold-prospect SQL pipeline (`sql/list*.sql`, `sql/no_sdk_no_ua_*.sql`).

---

## Internal Moloco Tables

### `ads-bpd-guard-china.athena.dim1_app_v3`

App metadata enriched with SensorTower data. One row per **app_bundle × OS**.

| Column | Type | Notes |
|--------|------|-------|
| `app_market_bundle` | STRING | Primary key (with `os`) — bundle ID e.g. `com.example.app` or iTunes numeric |
| `os` | STRING | `ios` or `android` |
| `sensortower.product.app_id` | STRING | **ST platform-specific app ID** — used to join `network_analysis` and `download_revenue_v3` |
| `sensortower.product.unified_app_id` | STRING | ST unified ID — joins `sensortower_new.*` pipeline tables |
| `sensortower.product.app_name` | STRING | App display name |
| `sensortower.product.has_ads` | BOOLEAN | Has in-app advertising |
| `sensortower.product.has_iap` | BOOLEAN | Has in-app purchases |
| `sensortower.product.unified_category_name` | STRING | App store category |
| `sensortower.product.store_url` | STRING | App store URL |
| `sensortower.publisher.name` | STRING | Publisher name |
| `sensortower.publisher.website` | STRING | Publisher website |
| `sensortower.company.name` | STRING | Company name (ST-sourced) |
| `sensortower.company.hq_country` | STRING | Company HQ country (ISO code) |
| `sensortower.company.hq_region` | STRING | Region e.g. `"Greater China"` |
| `sensortower.company.parent.name` | STRING | Parent company name |
| `sensortower.class.is_gaming` | BOOLEAN | Gaming vs non-gaming classification |
| `sensortower.class.genre` | STRING | Genre e.g. `"Casual"`, `"Strategy"`, `"Utility"` |
| `sensortower.class.subgenre` | STRING | Sub-genre |
| `moloco.is_gaming` | BOOLEAN | Moloco's own gaming classification (may differ from ST) |

**Critical gotchas:**
- Join key is `(app_market_bundle, os)` — NOT `app_id`. A single app has two rows (iOS + Android)
- `sensortower.product.app_id` is the **platform-specific ST ID** — different from `unified_app_id`. Use this to join `sensortower.network_analysis` and `sensortower.download_revenue_v3`
- `sensortower.company.hq_country` may be wrong for some Chinese companies — override with `yingzi_uploads.hq_country_triage`
- `monetization_type` is not stored here — must be derived from `has_ads` + `has_iap` + `is_gaming` + `genre` in SQL logic

**Monetization type derivation logic (from list1_cold_prospect.sql):**
```sql
-- Gaming apps
CASE
  WHEN has_iap = false AND has_ads = true  THEN 'IAA'
  WHEN has_ads = false AND has_iap = true  THEN 'IAP'
  WHEN has_ads = false AND has_iap = false THEN 'Free'
  WHEN has_ads = true  AND has_iap = true
   AND genre IN ('Casual','Hypercasual','Puzzle','Arcade','Word','Casino',...) THEN 'Hybrid-IAA'
  WHEN has_ads = true  AND has_iap = true  THEN 'Hybrid-IAP'
END
-- Non-gaming apps: IAA if has_ads, IAP if has_iap, else Free
```

---

### `ads-bpd-guard-china.athena.fact_dsp_core`

Moloco DSP campaign performance — one row per **campaign × date**.

| Column | Type | Notes |
|--------|------|-------|
| `date_utc` | DATE | Partition key — always filter |
| `product.app_market_bundle` | STRING | Bundle ID — joins `dim1_app_v3` |
| `product.app_name` | STRING | App name (denormalized) |
| `product.company_name` | STRING | Company name (denormalized) |
| `gross_spend_usd` | NUMERIC | **Use this for UA spend** — total billed spend |
| `media_cost_usd` | NUMERIC | Net media cost (after discounts) — smaller than gross |
| `advertiser.office` | STRING | Moloco office e.g. `"China"`, `"Korea"` |
| `advertiser.gm` | STRING | Growth Manager name |
| `advertiser.growth_pod` | STRING | Growth pod |
| `advertiser.tier` | STRING | Advertiser tier |
| `campaign.country` | STRING | Target country ISO code |
| `campaign.os` | STRING | `ios` or `android` |
| `campaign.goal` | STRING | Campaign goal e.g. `"CPI"`, `"ROAS"` |
| `impressions` | INTEGER | |
| `clicks` | INTEGER | |
| `installs` | INTEGER | |
| `platform_id` | STRING | Moloco platform ID |

**Critical gotchas:**
- Use `gross_spend_usd` (not `pb_revenue_usd` or `media_cost_usd`) to measure UA spend — it's the billed amount and used consistently in all prospect SQL
- `date_utc` is partitioned — always include a date filter
- One campaign can span multiple rows (daily granularity)

**Standard UA spend check (90d):**
```sql
SELECT product.app_market_bundle, SUM(gross_spend_usd) AS spend_90d
FROM `ads-bpd-guard-china.athena.fact_dsp_core`
WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND gross_spend_usd > 0
GROUP BY 1
```

---

### `ads-bpd-guard-china.gtm.supply_demand_overlap`

Pre-computed Moloco relationship flags per app bundle. Has **multiple rows per `app_bundle`** (one per office/advertiser relationship) — always `GROUP BY app_bundle` with `MAX`/`STRING_AGG`.

| Column | Type | Notes |
|--------|------|-------|
| `app_bundle` | STRING | Bundle ID — joins `dim1_app_v3.app_market_bundle` |
| `is_moloco_sdk_app` | BOOLEAN | App has Moloco SDK integrated |
| `is_moloco_advertiser_app` | BOOLEAN | App is actively buying UA on Moloco |
| `is_moloco_advertiser_publisher` | BOOLEAN | Publisher is a Moloco advertiser (via another app) |
| `is_supply_partner` | BOOLEAN | App is a Moloco supply partner |
| `sdk_media_cost_usd` | FLOAT | SDK media cost (30d rolling) |
| `sdk_media_cost_rank` | INTEGER | Rank among SDK apps by media cost |
| `pub_rank_30d` | INTEGER | Publisher rank by bid requests (30d) |
| `eligibility_status` | STRING | e.g. `"Eligible"`, `"Ineligible"` |
| `ineligibility_reasons` | STRING | Why ineligible if applicable |
| `eligibility_evaluation_date` | DATE | When eligibility was last evaluated |
| `success_threshold_status` | STRING | Whether success threshold has been met |
| `mmp` | STRING | Attributed MMP e.g. `"Adjust"`, `"AppsFlyer"` |
| `mmp_event_names` | STRING | MMP events tracked |
| `office` | STRING | Moloco office managing this relationship |
| `ads_growth_manager` | STRING | Ads growth manager |
| `ads_growth_pod` | STRING | Ads growth pod |
| `sdk_growth_manager` | STRING | SDK growth manager |
| `gross_spend_usd` | NUMERIC | Total Moloco spend for this app |

**Critical gotchas:**
- **Multiple rows per `app_bundle`** — one per office/advertiser/relationship combination. Always GROUP BY and use MAX/STRING_AGG
- `sdk_media_cost_usd` is **30-day rolling** (not 90d)
- A bundle with `is_moloco_advertiser_app = false` but `gross_spend_usd > 0` may have historical spend — check both flags

**Standard deduplication pattern:**
```sql
SELECT
  app_bundle,
  MAX(is_moloco_sdk_app)              AS is_moloco_sdk_app,
  MAX(is_moloco_advertiser_app)       AS is_moloco_advertiser_app,
  MAX(sdk_media_cost_usd)             AS sdk_media_cost_usd,
  MAX(pub_rank_30d)                   AS pub_rank_30d,
  MAX(eligibility_status)             AS eligibility_status,
  MAX(mmp)                            AS mmp,
  STRING_AGG(DISTINCT ads_growth_pod, ', ')     AS ads_growth_pods,
  STRING_AGG(DISTINCT sdk_growth_manager, ', ') AS sdk_growth_managers
FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
GROUP BY app_bundle
```

---

### `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`

SDK supply traffic — one row per **ad request event × date**. Superset of `fact_supply` with `tracking_publisher_name` added.

| Column | Type | Notes |
|--------|------|-------|
| `date_utc` | DATE | Partition key |
| `exchange` | STRING | Exchange/SDK source — filter `LIKE 'MOLOCO_SDK%'` for SDK-only traffic |
| `req.app_bundle` | STRING | Bundle ID |
| `req.app_name` | STRING | App name |
| `req.app_is_gaming` | BOOLEAN | |
| `req.app_genre` | STRING | |
| `req.app_company_name` | STRING | Company name from supply signal |
| `req.app_parent_company_name` | STRING | |
| `req.country` | STRING | ISO country code |
| `req.os` | STRING | `ios` or `android` |
| `tracking_publisher_name` | STRING | Canonical publisher name (enriched — more reliable than `req.app_company_name`) |
| `impressions` | INTEGER | |
| `bid_requests` | INTEGER | |
| `media_cost_usd` | FLOAT | |
| `sdk_name` | STRING | SDK name |
| `sdk_version` | STRING | |

**Critical gotchas:**
- Always filter `exchange LIKE 'MOLOCO_SDK%'` to get SDK inventory only
- Use `tracking_publisher_name` (not `req.app_company_name`) for canonical publisher name — it's more complete and deduped
- Partition by `date_utc` — always include a date range filter

**Standard SDK app inventory query:**
```sql
SELECT
  req.app_bundle,
  MAX(req.app_name)            AS app_name,
  MAX(tracking_publisher_name) AS tracking_publisher_name,
  MAX(req.os)                  AS os
FROM `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`
WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND exchange LIKE 'MOLOCO_SDK%'
  AND req.app_bundle IS NOT NULL
GROUP BY req.app_bundle
```

---

## SensorTower Legacy Tables (ads-bpd-guard-china.sensortower.*)

These are **different** from `fact_app_basis_v3` and the pipeline output tables. They use `app_id` = the ST platform-specific ID from `dim1_app_v3.sensortower.product.app_id`, NOT the unified ID.

---

### `ads-bpd-guard-china.sensortower.network_analysis`

Ad network share-of-voice. Simple flat table.

| Column | Type | Notes |
|--------|------|-------|
| `app_id` | STRING | **ST platform-specific ID** — join via `dim1_app_v3.sensortower.product.app_id` |
| `country` | STRING | ISO code |
| `network` | STRING | Ad network name |
| `date_utc` | DATE | Partition key |
| `sov` | NUMERIC | Share of voice |

**Critical gotcha:** `app_id` here is the platform-specific ST ID — NOT `unified_app_id`. Join via `dim1_app_v3`:
```sql
JOIN `ads-bpd-guard-china.athena.dim1_app_v3` d ON n.app_id = d.sensortower.product.app_id
```

---

### `ads-bpd-guard-china.sensortower.download_revenue_v3`

Per-country download and revenue data. Granularity: **app × date × country × device**.

| Column | Type | Notes |
|--------|------|-------|
| `date_utc` | DATE | Partition key |
| `app_id` | STRING | **ST platform-specific ID** — same join path as `network_analysis` |
| `country_code` | STRING | ISO code (unlike `fact_app_basis_v3` which uses full country names) |
| `device_code` | STRING | Device type |
| `download` | INTEGER | Total downloads |
| `free_download` | INTEGER | Free downloads |
| `paid_download` | INTEGER | Paid downloads |
| `revenue` | NUMERIC | Revenue (USD) |

---

## Reference / Override Tables

### `ads-bpd-guard-sandbox.yingzi_uploads.hq_country_triage`

GTM-verified HQ country overrides for Chinese companies where SensorTower data is wrong.

| Column | Type | Notes |
|--------|------|-------|
| `company_name` | STRING | Matches `dim1_app_v3.sensortower.company.name` or `parent.name` |
| `hq_country` | STRING | Original ST HQ country |
| `final_hq_country` | STRING | **Use this** — GTM-verified correct country |
| `is_manually_corrected` | BOOLEAN | Whether manually reviewed |
| `manus_suggested_hq_country` | STRING | AI suggestion |
| `manus_rationale` | STRING | Rationale for suggestion |
| `moloco_spend_6mo` | STRING | Moloco spend context |
| `total_download_2025` | STRING | Download context |

**Usage:** Left join on company name, then `COALESCE(triage.final_hq_country, dim1.sensortower.company.hq_country)`. Join key is parent company name when available, otherwise company name.

---

## ID / Join Key Cheat Sheet

| From table | Field | Joins to |
|------------|-------|----------|
| `fact_supply_with_tracking_publisher` | `req.app_bundle` | `dim1_app_v3.app_market_bundle` |
| `fact_supply_with_tracking_publisher` | `req.app_bundle` | `fact_dsp_core.product.app_market_bundle` |
| `fact_supply_with_tracking_publisher` | `req.app_bundle` | `supply_demand_overlap.app_bundle` |
| `dim1_app_v3` | `sensortower.product.app_id` | `network_analysis.app_id` |
| `dim1_app_v3` | `sensortower.product.app_id` | `download_revenue_v3.app_id` |
| `dim1_app_v3` | `sensortower.product.unified_app_id` | `sensortower_new.st_*.unified_app_id` |
| `app_iq_v3` | `app_id` | `fact_app_basis_v3.unified_app_id` |
| `app_iq_v3` | `app_id` | `sensortower_new.st_*.unified_app_id` |
