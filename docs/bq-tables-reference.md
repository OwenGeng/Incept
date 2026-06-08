# BigQuery Tables Reference (Prospect Engine)

## Overview

| Table | Dataset | Refresh Frequency | Primary Key | Purpose |
|----|--------|----------|------|------|
| `gtm.supply_demand_overlap` | `ads-bpd-guard-china` | Daily (triggered by upstream table refresh) | `app_bundle` | SDK + UA status; core source for Tier 1/2/3 |
| `athena.dim1_app_v3` | `ads-bpd-guard-china` | Daily at 06:00 UTC | `app_market_bundle` | App / company metadata; China identification |
| `athena.fact_app_v3` | `ads-bpd-guard-china` | Daily (triggered downstream of dim1_app_v3) | `app_market_bundle` + `date_utc` + `country` | Download volume, revenue, paid channel trends |
| `sensortower.network_analysis` | `ads-bpd-guard-china` | Refreshed every Wednesday (source data updates daily with ~2-day lag) | `app_id` + `date_utc` | Competitor ad network activity signals |

---

## Join Path

```
supply_demand_overlap.app_bundle
        │
        ▼  (app_bundle = app_market_bundle)
dim1_app_v3.app_market_bundle
        │
        ├──▶ fact_app_v3.app_market_bundle
        │
        └──▶ sensortower.network_analysis.app_id
              (via dim1_app_v3.sensortower.product.app_id)
```

`app_market_bundle` is the primary join key across the three Moloco internal tables.
`network_analysis` uses Sensor Tower's `app_id` and requires bridging through `dim1_app_v3`.

---

## 1. `gtm.supply_demand_overlap`

**Retain all fields** (this is Moloco internal data; field count is small but every field is meaningful)

| Field | Description |
|------|------|
| `app_bundle` | **Core join key** — same format as `app_market_bundle` |
| `publisher_name` | Publisher name |
| `bid_requests` | Supply-side request volume (supply signal strength) |
| `gross_spend_usd_iaa` | IAA demand-side spend (demand signal strength) |
| `eligibility_status` | Moloco eligibility evaluation result |
| `ineligibility_reasons` | Reasons for ineligibility (qualification evidence) |
| `eligibility_evaluation_date` | Evaluation date |
| SDK-related fields | SDK integration status (field names to be confirmed via inspection) |
| UA / Advertiser-related fields | Whether an active advertiser relationship exists (field names to be confirmed) |

> **Note**: Fields like `eligibility_status` serve as the **evidence layer** for qualification — they do not directly equal the final qualification conclusion.

---

## 2. `athena.dim1_app_v3`

**Retain only the following fields** (`dataai.*`, `matters42.*`, `moloco.*` sub-structures not needed for now)

| Field | Type | Purpose |
|------|------|------|
| `app_market_bundle` | string | Join key |
| `os` | string | `ios` / `android` |
| `sensortower.product.app_id` | string | **Key for bridging to network_analysis** |
| `sensortower.product.name` | string | App name |
| `sensortower.product.has_ads` | bool | Whether the app has ad monetization (IAA signal) |
| `sensortower.product.has_iap` | bool | Whether the app has in-app purchases (IAP signal) |
| `sensortower.product.category` | string | App category |
| `sensortower.publisher.name` | string | Publisher name |
| `sensortower.publisher.website` | string | Publisher website (for outreach) |
| `sensortower.company.name` | string | Company name |
| `sensortower.company.hq_country` | string | **Core field for China identification Layer 1** |
| `sensortower.company.hq_region` | string | Region |
| `sensortower.company.website` | string | Company website |
| `sensortower.company.parent.id` | string | Parent company ID |
| `sensortower.company.parent.name` | string | Parent company name (used for entity resolution) |
| `sensortower.class.is_gaming` | bool | Whether the app is a game |
| `sensortower.class.genre` | string | Game genre / non-gaming category |
| `sensortower.class.subgenre` | string | Sub-category |

**Excluded**: `sensortower.product.install_country`, `store_url`, release dates (queryable but not core to scoring); `dataai`, `matters42`, `moloco` sub-structures (not needed for now).

---

## 3. `athena.fact_app_v3`

**Recommended approach: do not use raw rows directly — aggregate into derived fields in SQL.**

### Raw Fields (which ones to read)

| Field | Description |
|------|------|
| `app_market_bundle` | Join key |
| `os` | `ios` / `android` |
| `date_utc` | Monthly date (use the 1st of each month as the monthly representative) |
| `country` | Country code (sum across countries when aggregating to WW) |
| `unified_app_id` | Moloco internal unified ID (retain as a backup for internal joins) |
| `monthly.download.all` | Total monthly downloads |
| `monthly.download.paid` | Paid downloads |
| `monthly.channel.paid` | Paid channel downloads |
| `monthly.channel.paid_ads` | Paid ads channel downloads |
| `monthly.revenue` | Monthly revenue estimate |

**Excluded**: `daily.*`, `weekly.*` (monthly granularity is sufficient); `monthly.usage.*` (sessions, duration, devices); `monthly.channel.web_browser`, `organic_search` (low contribution to prospect scoring); `monthly.download.free`, `paid` (`all` is sufficient).

### Aggregation Recommendation

Do not retain raw rows by day or country. Compute derived fields directly in SQL, with **one row per app** in the final output:

```sql
-- Goal: one row per app_market_bundle containing key scoring metrics
SELECT
  app_market_bundle,
  os,

  -- Scale
  SUM(CASE WHEN date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
       THEN monthly.download.all END) AS downloads_latest_month,
  SUM(CASE WHEN date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH), MONTH)
       THEN monthly.download.all END) AS downloads_90d,
  SUM(CASE WHEN date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
       THEN monthly.revenue END)      AS revenue_latest_month,

  -- Growth (90d vs prior 90d comparison)
  SUM(CASE WHEN date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH), MONTH)
       THEN monthly.download.all END)
  - SUM(CASE WHEN date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH), MONTH)
              AND date_utc < DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH), MONTH)
       THEN monthly.download.all END) AS download_growth_90d_vs_prior,

  -- Commercial Activity (paid UA signal)
  SUM(CASE WHEN date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
       THEN monthly.channel.paid + monthly.channel.paid_ads END) AS paid_downloads_30d

FROM `ads-bpd-guard-china.athena.fact_app_v3`
WHERE date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH), MONTH)
  -- Use explicit literal dates to avoid dry-run timeout; in production replace with literal date values
GROUP BY app_market_bundle, os
```

**Date query note**: `CURRENT_DATE()` and `DATE_SUB` on the `ads-bpd-guard-china` cross-project view can trigger a 30-second dry-run timeout. **In production, use literal dates**, e.g. `date_utc >= DATE '2025-12-01'`.

---

## 4. `sensortower.network_analysis`

**Recommended approach: aggregate into a per-app competitor signal wide table** rather than retaining the full time series.

### Raw Fields

| Field | Description |
|------|------|
| `app_id` | ST app ID (joined via `dim1_app_v3.sensortower.product.app_id`) |
| `date_utc` | Weekly dimension (week starts on Sunday) |
| `network` | Ad network name — values include `Moloco`, `AppLovin`, `Unity`, `ironSource`, `Facebook`, `TikTok`, `Mintegral`, `Google UAC`, `Pangle`, `Vungle`, etc. |
| `sov` | Share of Voice (numeric value) |
| `country` | Country |

### Aggregation Recommendation

```sql
-- Goal: one row per app_id — whether each network was active in the last 90 days
SELECT
  app_id,
  MAX(CASE WHEN network = 'Moloco'     THEN 1 ELSE 0 END) AS on_moloco,
  MAX(CASE WHEN network = 'AppLovin'   THEN 1 ELSE 0 END) AS on_applovin,
  MAX(CASE WHEN network = 'Unity'      THEN 1 ELSE 0 END) AS on_unity,
  MAX(CASE WHEN network = 'ironSource' THEN 1 ELSE 0 END) AS on_ironsource,
  MAX(CASE WHEN network = 'Facebook'   THEN 1 ELSE 0 END) AS on_facebook,
  MAX(CASE WHEN network = 'TikTok'     THEN 1 ELSE 0 END) AS on_tiktok,
  MAX(CASE WHEN network = 'Mintegral'  THEN 1 ELSE 0 END) AS on_mintegral,
  MAX(CASE WHEN network = 'Google UAC' THEN 1 ELSE 0 END) AS on_google_uac,
  MAX(CASE WHEN network = 'Pangle'     THEN 1 ELSE 0 END) AS on_pangle,
  COUNTIF(network != 'Moloco' AND sov > 0) AS competitor_network_count
FROM `ads-bpd-guard-china.sensortower.network_analysis`
WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY app_id
```

`competitor_network_count` is used directly as input to the Commercial Activity scoring dimension.
`on_moloco = 0` can serve as a Tier 2 signal indicator for apps running on competitor networks but not on Moloco.

---

## Full Join Overview SQL (skeleton)

```sql
WITH
-- Step 1: Moloco SDK/UA status
moloco AS (
  SELECT * FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
),

-- Step 2: App/Company metadata
meta AS (
  SELECT
    app_market_bundle,
    os,
    sensortower.product.app_id          AS st_app_id,
    sensortower.product.name            AS app_name,
    sensortower.product.has_ads,
    sensortower.product.has_iap,
    sensortower.product.category,
    sensortower.publisher.name          AS publisher_name,
    sensortower.publisher.website       AS publisher_website,
    sensortower.company.name            AS company_name,
    sensortower.company.hq_country,
    sensortower.company.hq_region,
    sensortower.company.parent.name     AS parent_company,
    sensortower.class.is_gaming,
    sensortower.class.genre,
    sensortower.class.subgenre
  FROM `ads-bpd-guard-china.athena.dim1_app_v3`
),

-- Step 3: Downloads / revenue / growth (pre-aggregated, one row per app)
metrics AS (
  SELECT
    app_market_bundle,
    SUM(CASE WHEN date_utc = DATE '2026-05-01' THEN monthly.download.all END)            AS downloads_latest_month,
    SUM(CASE WHEN date_utc >= DATE '2026-03-01' THEN monthly.download.all END)           AS downloads_90d,
    SUM(CASE WHEN date_utc >= DATE '2025-12-01'
             AND date_utc < DATE '2026-03-01'  THEN monthly.download.all END)           AS downloads_prior_90d,
    SUM(CASE WHEN date_utc = DATE '2026-05-01' THEN monthly.revenue END)                AS revenue_latest_month,
    SUM(CASE WHEN date_utc >= DATE '2026-05-01'
              THEN monthly.channel.paid + monthly.channel.paid_ads END)                 AS paid_downloads_30d
  FROM `ads-bpd-guard-china.athena.fact_app_v3`
  WHERE date_utc >= DATE '2025-12-01'
  GROUP BY app_market_bundle
),

-- Step 4: Competitor network signals (pre-aggregated, one row per app)
networks AS (
  SELECT
    app_id,
    MAX(CASE WHEN network = 'Moloco'     THEN 1 ELSE 0 END) AS on_moloco,
    MAX(CASE WHEN network = 'AppLovin'   THEN 1 ELSE 0 END) AS on_applovin,
    MAX(CASE WHEN network = 'Unity'      THEN 1 ELSE 0 END) AS on_unity,
    MAX(CASE WHEN network = 'ironSource' THEN 1 ELSE 0 END) AS on_ironsource,
    MAX(CASE WHEN network = 'Facebook'   THEN 1 ELSE 0 END) AS on_facebook,
    MAX(CASE WHEN network = 'TikTok'     THEN 1 ELSE 0 END) AS on_tiktok,
    MAX(CASE WHEN network = 'Mintegral'  THEN 1 ELSE 0 END) AS on_mintegral,
    MAX(CASE WHEN network = 'Google UAC' THEN 1 ELSE 0 END) AS on_google_uac,
    MAX(CASE WHEN network = 'Pangle'     THEN 1 ELSE 0 END) AS on_pangle,
    COUNTIF(network != 'Moloco')                             AS competitor_network_count
  FROM `ads-bpd-guard-china.sensortower.network_analysis`
  WHERE date_utc >= DATE '2026-03-01'
  GROUP BY app_id
)

-- Final join
SELECT
  m.*,
  meta.* EXCEPT (app_market_bundle),
  met.* EXCEPT (app_market_bundle),
  net.* EXCEPT (app_id)
FROM moloco m
LEFT JOIN meta   ON m.app_bundle = meta.app_market_bundle
LEFT JOIN metrics met ON m.app_bundle = met.app_market_bundle
LEFT JOIN networks net ON meta.st_app_id = net.app_id
```

---

## Field Inclusion Rationale

| Retained | Reason |
|------|------|
| All `supply_demand_overlap` fields | Core Moloco internal signals — small field count but every field is useful |
| All `dim1_app_v3.sensortower.*` fields | Company/China identification and product fit both depend on this layer |
| 5 derived fields from `fact_app_v3` after aggregation | Scale + Growth + Commercial Activity — sufficient for scoring |
| Boolean flags + count from `network_analysis` after aggregation | Used directly in scoring; raw SOV numbers are not needed |

| Excluded | Reason |
|--------|------|
| Raw `fact_app_v3` rows (by day and country) | Information overload; scoring only needs aggregated monthly WW numbers |
| Full `network_analysis` time series | Only "active in last 90 days" is needed; binary flag is sufficient |
| `dim1_app_v3` `dataai`, `moloco`, `matters42` sub-structures | Not needed for v1 |
| `fact_app_v3.monthly.usage.*` | Sessions, duration, devices contribute little to prospect scoring |
