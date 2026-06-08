# Prospect Engine — Query Reference

## Four-List Overview

| List | Name | Source | Conditions | Target Action | Priority |
|------|------|------|------|---------|--------|
| **List 1** | COLD_PROSPECT | `fact_supply_with_tracking_publisher` + `supply_demand_overlap` | SDK integrated + **company has zero UA across all apps** | Activate UA directly | ⭐⭐⭐ Highest |
| **List 2** | EXPANSION | `fact_supply_with_tracking_publisher` + `supply_demand_overlap` | SDK integrated + company has **partial** UA + still has untapped apps | Cross-app expansion | ⭐⭐ High |
| **List 3** | SUPPLY_PARTNER_UPSDK | `supply_demand_overlap` + ST `dim1_app_v3` | Company is a Supply Partner, but **this specific app has no SDK** and no UA | SDK expansion pitch (existing trust relationship) | ⭐⭐ High |
| **List 4** | IAA Cold Prospect | ST `dim1_app_v3` + `fact_app_v3` + `fact_dsp_publisher` | **Pure IAA** (has_ads=T, has_iap=F) + high downloads + **no Moloco relationship at all** | Start from scratch: SDK integration + UA | ⭐ Medium |
| **List 5** | IAP Cold Prospect | ST `dim1_app_v3` + `fact_app_v3` + `fact_dsp_publisher` | **Pure IAP** (has_ads=F, has_iap=T) + high downloads + **no Moloco relationship at all** | Start from scratch: direct UA | ⭐ Medium |
| **List 6** | Hybrid Cold Prospect | ST `dim1_app_v3` + `fact_app_v3` + `fact_dsp_publisher` | **Hybrid** (has_ads=T, has_iap=T) + high downloads + **no Moloco relationship at all** | AM case-by-case judgment | ⭐ Medium |

**All lists include a `team_routing` field (Gaming / Non-Gaming) for routing to the appropriate sales team.**

---

### monetization_type Classification Logic

```
Gaming (is_gaming = true):
  has_ads=T, has_iap=F                              → IAA        → List 2
  has_ads=F, has_iap=T                              → IAP        → List 3
  has_ads=T, has_iap=T + IAA genre (see allowlist below) → Hybrid-IAA → List 2
  has_ads=T, has_iap=T + other genres               → Hybrid-IAP → List 3
  has_ads=F, has_iap=F                              → Free (excluded from all lists)

Non-Gaming (is_gaming = false):
  has_ads=T (regardless of has_iap)                → IAA        → List 2
  has_ads=F, has_iap=T                              → IAP        → List 3
  has_ads=F, has_iap=F                              → Free (excluded from all lists)

IAA genre allowlist (applies only to Hybrid classification for gaming apps):
  Casual, Puzzle, Hypercasual, Arcade, Word, Board, Card, Trivia, Tabletop
```

---

## Lists 1 & 4: SDK-Based Prospects (Shared CTEs)

> **Full SQL in** `sql/list1_sdk_no_ua.sql`
>
> - List 1 (COLD_PROSPECT): all SDK apps under the company have no UA → `moloco_offices / gms / account_age_groups` are empty, which is expected (no advertiser relationship); `sdk_growth_managers` will have values (SDK-side contact)
> - List 4 (EXPANSION): company has some apps running UA → those fields will have values
> - Both lists share all CTEs and are distinguished by the `list_type` field; can be filtered by column in a spreadsheet

### CTE Structure (9 CTEs)

| CTE | Data Source | Purpose |
|-----|---------|------|
| `sdk_bundles` | `fact_supply_with_tracking_publisher` | SDK app list + `tracking_publisher_name` + `sdk_types` + `impressions_90d` |
| `active_ua` | `fact_dsp_core` | 90-day UA spend; distinguishes COLD from EXPANSION |
| `sdl` | `supply_demand_overlap` | Moloco status flags, eligibility, SDK cost, MMP, internal contacts (36 fields, deduplicated via GROUP BY app_bundle) |
| `meta` | `dim1_app_v3` | ST metadata: company, HQ, genre, `monetization_type`, `st_app_id` (bridge to ST tables) |
| `net_signals` | `sensortower.network_analysis` | Which networks this app is buying UA on (demand-side, weekly update) |
| `geo_raw` + `geo_metrics` | `sensortower.download_revenue_v3` | Top download/revenue countries in the last 30 days (via `st_app_id`) |
| `supply_imp_by_country` + `supply_top_country` | `fact_supply_with_tracking_publisher` | Country with highest Moloco SDK impressions (monetization perspective) |
| `tagged` | All of the above JOINed | App-level summary containing all fields |
| `company_level` | `tagged` | Company-level aggregation; shared by TAB 2 + TAB 3 |

### Query A — Company Summary (TAB 2)

**TAB 2 output fields (company level):**

```sql
-- Run the TAB 2 section of sql/list1_sdk_no_ua.sql (default SELECT)
-- Output fields:
list_type                  -- List1_COLD_PROSPECT / List4_EXPANSION
canonical_company          -- Normalized company name
hq_country / hq_region     -- ST company headquarters
china_confidence           -- High / Medium / Low-Review
team_routing               -- Gaming / Non-Gaming
website
tracking_publisher_name    -- GTM-normalized name
monetization_types         -- Aggregated monetization types across all apps under the company
total_sdk_apps             -- Total number of apps with SDK integrated
buying_ua_apps             -- Number of those apps running UA
untapped_apps              -- Number of those apps with no UA (= target)
total_impressions_90d      -- Total 90-day SDK supply impressions
total_sdk_media_cost_usd   -- Total 90-day SDK supply media cost (from supply_demand_overlap)
total_bid_requests         -- Total bid requests
eligibility_statuses       -- Enrolled / Undecided / Ineligible
mmps                       -- MMP platforms (AppsFlyer / Adjust, etc.)
sdk_growth_managers        -- SDK-side contacts (also populated for COLD_PROSPECT)
-- EXPANSION-only fields (empty for COLD_PROSPECT):
moloco_offices             -- Responsible office for existing UA apps
moloco_gms                 -- Responsible GM for existing UA apps
account_age_groups         -- Account age segments
existing_spend_usd_90d     -- 90-day spend across the company's existing UA apps
```

---

### Query B — App Detail (TAB 3)

**In `sql/list1_sdk_no_ua.sql`, uncomment the TAB 3 SELECT block (replacing the TAB 2 SELECT)**

**Additional fields in TAB 3 beyond TAB 2 (app-level granularity):**

```
-- SDK supply activity (from supply_demand_overlap)
sdk_media_cost_usd / sdk_media_cost_usd_7d / sdk_media_cost_rank
bid_requests / media_cost_usd / media_cost_usd_7d / pub_rank_30d

-- Moloco relationship flags (from supply_demand_overlap)
is_moloco_sdk_app / is_moloco_advertiser_app / is_moloco_advertiser_publisher
is_moloco_iaa_app / is_iaa_app_any / is_supply_partner / vertical

-- Spend comparison
gross_spend_usd_30d  (supply_demand_overlap, 30 days)
gross_spend_usd_90d  (fact_dsp_core, 90 days)
gross_spend_usd_iaa

-- Eligibility
eligibility_status / ineligibility_reasons / eligibility_evaluation_date
success_threshold_status

-- MMP
mmp / mmp_event_names

-- Moloco internal contacts
sdl_sdk_growth_managers / sdl_offices / sdl_ads_growth_managers / sdl_advertiser_names

-- Competitor networks (ST network_analysis)
active_ua_networks / competitor_network_count
on_applovin / on_unity / on_ironsource / on_meta / on_tiktok / on_pangle / on_mintegral / on_google

-- ST geographic data
total_downloads_30d / top_dl_country / top_dl_country_downloads
total_revenue_30d / top_rev_country / top_rev_country_revenue

-- Moloco SDK supply geography
top_sdk_impression_country / total_sdk_impressions_30d
```

---

## Lists 2 & 3: IAA / IAP Cold Prospects (Shared CTEs)

> **Notes**:
> - List 2 (IAA): ad-monetized, high downloads, never purchased on Moloco → SDK integration required first
> - List 3 (IAP): paid/subscription monetization, high downloads, never purchased on Moloco → open UA directly
> - Sort order: `competitor_network_count DESC` → `downloads_90d DESC` → `download_growth_rate DESC`
> - `downloads_90d >= 500000` is the initial threshold; **adjust after reviewing actual results from the first run**

```sql
WITH

-- 1. Apps with UA spend in the past 90 days (used for exclusion)
ua_spend AS (
  SELECT
    product.app_market_bundle AS bundle_id,
    SUM(gross_spend_usd)      AS spend_90d
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND product.app_market_bundle IS NOT NULL
    AND product.app_market_bundle != ''
  GROUP BY 1
),

-- 2. App metadata + monetization_type (pre-filter to China-related companies)
meta AS (
  SELECT
    app_market_bundle,
    os,
    sensortower.product.app_id         AS st_app_id,
    sensortower.product.name           AS app_name,
    sensortower.product.has_ads        AS has_ads,
    sensortower.product.has_iap        AS has_iap,
    sensortower.product.category       AS category,
    sensortower.publisher.name         AS publisher_name,
    sensortower.publisher.website      AS publisher_website,
    sensortower.company.name           AS company_name,
    sensortower.company.hq_country     AS hq_country,
    sensortower.company.hq_region      AS hq_region,
    sensortower.company.website        AS company_website,
    sensortower.company.parent.name    AS parent_company,
    sensortower.class.is_gaming        AS is_gaming,
    sensortower.class.genre            AS genre,
    sensortower.class.subgenre         AS subgenre,
    CASE
      WHEN UPPER(sensortower.company.hq_country) IN ('CN','CHN','CHINA')      THEN 'High'
      WHEN UPPER(sensortower.company.hq_country) IN ('HK','HKG','TW','TWN')   THEN 'Medium'
      WHEN UPPER(sensortower.company.hq_country) IN ('SG','SGP')              THEN 'Low-Review'
      ELSE 'Unknown'
    END AS china_confidence,
    CASE
      WHEN sensortower.class.is_gaming = true THEN
        CASE
          WHEN sensortower.product.has_iap = false AND sensortower.product.has_ads = true  THEN 'IAA'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = true  THEN 'IAP'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = false THEN 'Free'
          WHEN sensortower.product.has_ads = true  AND sensortower.product.has_iap = true
           AND sensortower.class.genre IN ('Casual','Puzzle','Hypercasual','Arcade','Word','Board','Card','Trivia','Tabletop')
            THEN 'Hybrid-IAA'
          WHEN sensortower.product.has_ads = true  AND sensortower.product.has_iap = true
            THEN 'Hybrid-IAP'
          ELSE 'Unknown'
        END
      WHEN sensortower.class.is_gaming = false THEN
        CASE
          WHEN sensortower.product.has_ads = true  THEN 'IAA'
          WHEN sensortower.product.has_iap = true  THEN 'IAP'
          ELSE 'Free'
        END
      ELSE 'Unknown'
    END AS monetization_type
  FROM `ads-bpd-guard-china.athena.dim1_app_v3`
  WHERE UPPER(sensortower.company.hq_country) IN (
    'CN','CHN','CHINA','HK','HKG','TW','TWN','SG','SGP'
  )
),

-- 3. Downloads / revenue / growth (aggregated by month, WW)
-- HAVING pre-filters low-download apps to reduce subsequent join volume
-- monthly.download.`all` requires backtick (all is a BQ reserved word)
downloads AS (
  SELECT
    app_market_bundle,
    SUM(CASE
      WHEN date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
      THEN monthly.download.`all` ELSE 0
    END) AS downloads_latest_month,
    SUM(CASE
      WHEN date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH), MONTH)
       AND date_utc  < DATE_TRUNC(CURRENT_DATE(), MONTH)
      THEN monthly.download.`all` ELSE 0
    END) AS downloads_90d,
    SUM(CASE
      WHEN date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH), MONTH)
       AND date_utc  < DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH), MONTH)
      THEN monthly.download.`all` ELSE 0
    END) AS downloads_prior_90d,
    SUM(CASE
      WHEN date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
      THEN monthly.revenue ELSE 0
    END) AS revenue_latest_month,
    SUM(CASE
      WHEN date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
      THEN monthly.channel.paid + monthly.channel.paid_ads ELSE 0
    END) AS paid_downloads_latest_month
  FROM `ads-bpd-guard-china.athena.fact_app_v3`
  WHERE date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH), MONTH)
    AND date_utc  < DATE_TRUNC(CURRENT_DATE(), MONTH)
  GROUP BY 1
  HAVING SUM(CASE
    WHEN date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH), MONTH)
    THEN monthly.download.`all` ELSE 0 END) >= 500000  -- ← adjust after reviewing first-run results
),

-- 4. Competitor network signals (ST network_analysis, demand-side)
-- Shows which networks the app is buying UA on → strong signal of UA budget
net_signals AS (
  SELECT
    app_id,
    MAX(CASE WHEN LOWER(network) LIKE '%applovin%'
              OR LOWER(network) LIKE '%max%'         THEN 1 ELSE 0 END) AS on_applovin,
    MAX(CASE WHEN LOWER(network) LIKE '%unity%'      THEN 1 ELSE 0 END) AS on_unity,
    MAX(CASE WHEN LOWER(network) LIKE '%ironsource%' THEN 1 ELSE 0 END) AS on_ironsource,
    MAX(CASE WHEN LOWER(network) LIKE '%facebook%'
              OR LOWER(network) LIKE '%meta%'        THEN 1 ELSE 0 END) AS on_meta,
    MAX(CASE WHEN LOWER(network) LIKE '%tiktok%'     THEN 1 ELSE 0 END) AS on_tiktok,
    MAX(CASE WHEN LOWER(network) LIKE '%pangle%'     THEN 1 ELSE 0 END) AS on_pangle,
    MAX(CASE WHEN LOWER(network) LIKE '%mintegral%'  THEN 1 ELSE 0 END) AS on_mintegral,
    MAX(CASE WHEN LOWER(network) LIKE '%google%'
              OR LOWER(network) LIKE '%uac%'         THEN 1 ELSE 0 END) AS on_google,
    MAX(CASE WHEN LOWER(network) LIKE '%moloco%'     THEN 1 ELSE 0 END) AS on_moloco_network,
    COUNTIF(LOWER(network) NOT LIKE '%moloco%')                          AS competitor_network_count
  FROM `ads-bpd-guard-china.sensortower.network_analysis`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  GROUP BY app_id
),

-- 5. Publisher exchange SDK signals (supply-side, Moloco DSP data)
-- Shows which exchange SDKs the app has integrated
-- pub_has_moloco_sdk = already has Moloco SDK (via another mediation platform)
-- pub_other_exchange_count > 0 AND pub_has_moloco_sdk = 0 → high-priority SDK pitch target
pub_exchange AS (
  SELECT
    publisher.app_market_bundle                                               AS bundle_id,
    MAX(CASE WHEN STARTS_WITH(exchange, 'MOLOCO_SDK')       THEN 1 ELSE 0 END) AS pub_has_moloco_sdk,
    MAX(CASE WHEN exchange = 'MOLOCO_SDK_MAX'                THEN 1 ELSE 0 END) AS pub_via_applovin_max,
    MAX(CASE WHEN exchange = 'MOLOCO_SDK_ADMOB_MEDIATION'    THEN 1 ELSE 0 END) AS pub_via_admob,
    MAX(CASE WHEN exchange = 'MOLOCO_SDK_LEVELPLAY'          THEN 1 ELSE 0 END) AS pub_via_levelplay,
    MAX(CASE WHEN exchange = 'MOLOCO_SDK_IN_HOUSE_MEDIATION' THEN 1 ELSE 0 END) AS pub_via_inhouse,
    MAX(CASE WHEN exchange = 'APPLOVIN'                      THEN 1 ELSE 0 END) AS pub_on_applovin,
    MAX(CASE WHEN exchange = 'UNITY'                         THEN 1 ELSE 0 END) AS pub_on_unity,
    MAX(CASE WHEN exchange = 'IRONSOURCE'                    THEN 1 ELSE 0 END) AS pub_on_ironsource,
    MAX(CASE WHEN exchange = 'VUNGLE'                        THEN 1 ELSE 0 END) AS pub_on_vungle,
    MAX(CASE WHEN exchange = 'INMOBI'                        THEN 1 ELSE 0 END) AS pub_on_inmobi,
    COUNTIF(NOT STARTS_WITH(exchange, 'MOLOCO'))                                AS pub_other_exchange_count
  FROM `ads-bpd-guard-china.athena.fact_dsp_publisher`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND is_complete_date_utc = true
    AND publisher.app_market_bundle IS NOT NULL
  GROUP BY 1
)

-- ── FINAL: List 2 (IAA) + List 3 (IAP) ─────────────────────────
SELECT
  CASE
    WHEN monetization_type IN ('IAA', 'Hybrid-IAA') THEN 'List2_IAA_NoMoloco'
    WHEN monetization_type IN ('IAP', 'Hybrid-IAP') THEN 'List3_IAP_NoMoloco'
  END AS list_type,

  CASE WHEN is_gaming THEN 'Gaming' ELSE 'Non-Gaming' END AS team_routing,

  -- Priority label
  CASE
    WHEN COALESCE(pe.pub_other_exchange_count, 0) > 0
     AND COALESCE(pe.pub_has_moloco_sdk, 0) = 0
      THEN '🟠 Exchange SDK (no Moloco) — SDK Pitch'
    WHEN COALESCE(n.on_google, 0) + COALESCE(n.on_meta, 0) >= 1
     AND COALESCE(n.competitor_network_count, 0) <= 2
      THEN '🟡 Google+Meta Only — Diversification Pitch'
    WHEN COALESCE(n.competitor_network_count, 0) >= 3
     AND d.paid_downloads_latest_month > 0
      THEN '🟡 Heavy UA Spender — High Intent'
    WHEN COALESCE(n.competitor_network_count, 0) >= 1
      THEN '🟢 Active UA — Mid Intent'
    WHEN d.downloads_90d >= 1000000
      THEN '⚪ Large Organic — Educate First'
    ELSE '⚪ Early Stage'
  END AS prospect_label,

  -- App identity
  m.app_market_bundle,
  m.os,
  m.app_name,
  m.parent_company,
  m.company_name,
  m.publisher_name,
  m.hq_country,
  m.hq_region,
  m.china_confidence,
  COALESCE(m.publisher_website, m.company_website) AS website,

  -- Monetization classification
  m.monetization_type,
  m.genre,
  m.subgenre,
  m.is_gaming,
  m.has_ads,
  m.has_iap,

  -- Scale and growth
  d.downloads_latest_month,
  d.downloads_90d,
  ROUND(SAFE_DIVIDE(
    CAST(d.downloads_90d - d.downloads_prior_90d AS FLOAT64),
    NULLIF(CAST(d.downloads_prior_90d AS FLOAT64), 0)
  ), 4)                                  AS download_growth_rate,
  d.revenue_latest_month,
  d.paid_downloads_latest_month,

  -- Competitor network signals (demand-side)
  COALESCE(n.competitor_network_count, 0) AS competitor_network_count,
  COALESCE(n.on_applovin,  0)             AS on_applovin,
  COALESCE(n.on_unity,     0)             AS on_unity,
  COALESCE(n.on_ironsource,0)             AS on_ironsource,
  COALESCE(n.on_meta,      0)             AS on_meta,
  COALESCE(n.on_tiktok,    0)             AS on_tiktok,
  COALESCE(n.on_pangle,    0)             AS on_pangle,
  COALESCE(n.on_mintegral, 0)             AS on_mintegral,
  COALESCE(n.on_google,    0)             AS on_google,
  CASE WHEN COALESCE(n.on_google,0) + COALESCE(n.on_meta,0) >= 1
        AND COALESCE(n.competitor_network_count,0) <= 2
       THEN true ELSE false END           AS only_google_meta,

  -- Publisher exchange SDK signals (supply-side)
  COALESCE(pe.pub_has_moloco_sdk,      0) AS pub_has_moloco_sdk,
  COALESCE(pe.pub_via_applovin_max,    0) AS pub_via_applovin_max,
  COALESCE(pe.pub_via_admob,           0) AS pub_via_admob,
  COALESCE(pe.pub_via_levelplay,       0) AS pub_via_levelplay,
  COALESCE(pe.pub_on_applovin,         0) AS pub_on_applovin,
  COALESCE(pe.pub_on_unity,            0) AS pub_on_unity,
  COALESCE(pe.pub_on_ironsource,       0) AS pub_on_ironsource,
  COALESCE(pe.pub_on_vungle,           0) AS pub_on_vungle,
  COALESCE(pe.pub_on_inmobi,           0) AS pub_on_inmobi,
  COALESCE(pe.pub_other_exchange_count,0) AS pub_other_exchange_count,
  CASE WHEN COALESCE(pe.pub_other_exchange_count,0) > 0
        AND COALESCE(pe.pub_has_moloco_sdk,0) = 0
       THEN true ELSE false END           AS has_other_exchange_sdk,

  CURRENT_DATE() AS data_as_of

FROM meta m
JOIN downloads d     ON m.app_market_bundle = d.app_market_bundle
LEFT JOIN ua_spend u ON m.app_market_bundle = u.bundle_id
LEFT JOIN net_signals n  ON m.st_app_id = n.app_id
LEFT JOIN pub_exchange pe ON m.app_market_bundle = pe.bundle_id

WHERE
  COALESCE(u.spend_90d, 0) = 0
  AND monetization_type IN ('IAA','Hybrid-IAA','IAP','Hybrid-IAP')
  AND china_confidence IN ('High','Medium','Low-Review')

ORDER BY
  list_type ASC,
  competitor_network_count DESC,
  downloads_90d DESC,
  download_growth_rate DESC
;
```

---

## Data Dictionary

> Describes the meaning, source table, calculation method, and rationale for each field.

### Common Fields (shared across all 4 lists)

| Field | Source Table | Calculation | Meaning & Rationale |
|------|--------|---------|----------------|
| `list_type` | Computed | CASE on monetization_type + SDK/spend status | Distinguishes the 4 prospect types; entry point for all filtering and routing |
| `team_routing` | `dim1_app_v3` | `IF(is_gaming, 'Gaming', 'Non-Gaming')` | Distinguishes gaming vs non-gaming sales teams |
| `sensortower_hq_country` | `dim1_app_v3` | ST raw `hq_country` | Raw HQ country from ST data; not reliable, used only as a pre-filter reference |
| `final_hq_country` | `hq_country_triage` + fallback | `COALESCE(gtm.final_hq_country, st.hq_country)` | **GTM-validated actual HQ**; preferred source; result of AI + manual review |
| `is_manually_corrected` | `hq_country_triage` | BOOL | true = confirmed by GTM manual review; highest confidence |
| `canonical_company` | Multi-source merge | Lists 1/4: GTM tracking > ST parent > ST company; Lists 2/3: ST parent > ST company | Unique company identifier; core of entity resolution |
| `hq_country` | `dim1_app_v3` | `sensortower.company.hq_country` (to be corrected via GTM table) | ST company HQ country; ST data is unreliable, corrected via `ads-bpd-guard-sandbox.yingzi_uploads.hq_country_triage.final_hq_country` |
| `monetization_type` | `dim1_app_v3` | Three-layer logic: is_gaming → genre → has_ads/has_iap | Determines sales strategy: IAA → SDK first; IAP → open UA directly |
| `active_ua_networks` | `sensortower.network_analysis` | STRING_AGG(DISTINCT network), weekly data, 90-day window | Networks where the app is buying UA; core signal of commercial intent; sorted by impression volume descending |

### List 1 & 4 Exclusive Fields (`list1_sdk_no_ua.sql`)

#### SDK Supply Signals (from `fact_supply_with_tracking_publisher`)

| Field | Source Table | Calculation | Meaning & Rationale |
|------|--------|---------|----------------|
| `sdk_types` | `fact_supply_with_tracking_publisher` | `STRING_AGG(DISTINCT exchange)`, 90-day window, `exchange LIKE 'MOLOCO_SDK%'` | Specific integration type (MAX=AppLovin MAX/AdMob/LevelPlay/In-House); guides how to reach this publisher |
| `impressions_90d` | `fact_supply_with_tracking_publisher` | `SUM(impressions)`, 90 days, SDK exchanges only | Proxy for SDK supply activity level; higher values indicate larger monetization scale; used for List 1 company-level sorting |
| `top_sdk_impression_country` | `fact_supply_with_tracking_publisher` | ROW_NUMBER + MAX, 30 days, sorted by country impressions | Country with highest SDK monetization concentration; helps sales understand the publisher's core monetization market |
| `tracking_publisher_name` | `fact_supply_with_tracking_publisher` | `MAX(tracking_publisher_name)`, GTM-maintained | GTM-normalized publisher name with parent-level merging applied (VOODOO→BeReal, etc.); preferred for entity resolution |

#### Moloco Relationship Status (from `supply_demand_overlap`, 30-day rolling window)

| Field | Source Table | Calculation | Meaning & Rationale |
|------|--------|---------|----------------|
| `is_moloco_sdk_app` | `supply_demand_overlap` | `MAX(is_moloco_sdk_app)`, deduplicated across offices | Whether Moloco Publisher SDK is integrated; cross-validates with sdk_bundles (based on exchange LIKE 'MOLOCO_SDK%') |
| `is_moloco_advertiser_app` | `supply_demand_overlap` | `MAX(is_moloco_advertiser_app)` | Whether there is a Moloco UA campaign relationship; cross-validates with active_ua (based on fact_dsp_core spend > 0) |
| `sdk_media_cost_usd_30d` | `supply_demand_overlap` | `MAX(sdk_media_cost_usd)`, 30 days (not 90 days) | SDK supply-side media cost; measures publisher monetization revenue through Moloco SDK; more precise than impressions |
| `total_sdk_media_cost_usd_30d` | `supply_demand_overlap` | `SUM(sdk_media_cost_usd_30d)` at company level | Total 30-day monetization revenue across all SDK apps under the company; sorting basis for company summary TAB 2 |
| `bid_requests` | `supply_demand_overlap` | `MAX(bid_requests)`, 30 days | Supply-side request volume; reflects the app's ad inventory scale |
| `pub_rank_30d` | `supply_demand_overlap` | `MAX(pub_rank_30d)` | Publisher supply-side rank; lower number = higher rank |
| `eligibility_status` | `supply_demand_overlap` | `MAX(eligibility_status)` | Enrolled/Undecided/Ineligible; core qualification field; Enrolled = passed Moloco eligibility review |
| `ineligibility_reasons` | `supply_demand_overlap` | `MAX(ineligibility_reasons)` | Reasons for ineligibility, multiple values separated by `/`; helps sales understand blockers |
| `success_threshold_status` | `supply_demand_overlap` | `MAX(success_threshold_status)` | `✅ Above Success Threshold` = above monetization success threshold; `🔻Below Threshold` = below threshold, volume increase needed |
| `mmp` | `supply_demand_overlap` | `MAX(mmp)` | Attribution platform in use (AppsFlyer / Adjust, etc.); affects campaign trackability |
| `sdl_sdk_growth_managers` | `supply_demand_overlap` | `STRING_AGG(DISTINCT sdk_growth_manager)` | SDK-side contacts; **also populated for COLD_PROSPECT**; the person to contact for SDK activation |
| `sdl_advertiser_names` | `supply_demand_overlap` | `STRING_AGG` of non-'Not Moloco Advertiser' entries | Moloco advertiser names; only populated for EXPANSION |

#### UA Campaign Dimension (from `fact_dsp_core`)

| Field | Source Table | Calculation | Meaning & Rationale |
|------|--------|---------|----------------|
| `gross_spend_usd_90d` | `fact_dsp_core` | `SUM(gross_spend_usd)`, 90 days, spend > 0 | App's total Moloco UA spend; always 0 for COLD_PROSPECT (filtered by is_buying_ua = false) |
| `advertiser_offices` | `fact_dsp_core` | `STRING_AGG(DISTINCT advertiser.office)` | Office responsible for UA; only populated for EXPANSION |
| `gms` | `fact_dsp_core` | `STRING_AGG(DISTINCT advertiser.gm)` | GM responsible for UA; only populated for EXPANSION |
| `existing_spend_usd_90d` | `fact_dsp_core` | `SUM(CASE WHEN is_buying_ua THEN spend)` | Total 90-day spend across the company's existing UA apps; only populated for EXPANSION |

#### Geographic Data (from `sensortower.download_revenue_v3`, 30 days)

| Field | Source Table | Calculation | Meaning & Rationale |
|------|--------|---------|----------------|
| `top_dl_country` | `download_revenue_v3` | ROW_NUMBER by SUM(download) DESC, 30 days | Country with highest user download volume (user market); helps sales understand primary markets |
| `top_rev_country` | `download_revenue_v3` | ROW_NUMBER by SUM(revenue) DESC, 30 days | Country with highest revenue; core paying market for IAP apps |
| `top_sdk_impression_country` | `fact_supply_with_tracking_publisher` | ROW_NUMBER by SUM(impressions) DESC, 30 days, SDK only | Country with highest Moloco SDK monetization concentration (monetization market); may differ from top_dl_country |

### List 2 & 3 Exclusive Fields (`list2_3_cold_prospects.sql`)

| Field | Source Table | Calculation | Meaning & Rationale |
|------|--------|---------|----------------|
| `downloads_month` | Computed | `FORMAT_DATE('%Y-%m', ...)` | Label for the most recent month (e.g. `2026-05`); clarifies which month downloads_latest_month corresponds to |
| `downloads_prior_month_label` | Computed | `FORMAT_DATE('%Y-%m', ...)` | Previous month label (e.g. `2026-04`); clarifies the baseline month for MoM comparison |
| `downloads_latest_month` | `fact_app_v3` | `SUM(monthly.download.all)`, most recent complete month, WW | Total global downloads in the most recent complete month; threshold 150K; scale signal |
| `downloads_prior_month` | `fact_app_v3` | `SUM(monthly.download.all)`, previous complete month, WW | Denominator for MoM growth rate; set MoM to 1.0 when value is 0 |
| `download_growth_rate_mom` | `fact_app_v3` | `(latest - prior) / prior`, 4 decimal places | Single-month MoM growth rate; more timely than 90-day comparison for recent trend signals |
| `has_other_exchange_sdk` | `fact_dsp_publisher` | `pub_other_exchange_count > 0 AND pub_has_moloco_sdk = 0` | Has other exchange SDKs but no Moloco SDK → priority SDK pitch target |
| `active_other_exchange_sdks` | `fact_dsp_publisher` | `STRING_AGG(exchange ORDER BY impression DESC)`, 90 days, non-Moloco | Which exchanges are integrated (sorted by Moloco DSP-observed impression volume descending); guides SDK integration approach |
| `top_dl_country` / `top_rev_country` | `download_revenue_v3` | Same as Lists 1&4 | Top download/revenue country in the last 30 days |
| TAB 1: `total_downloads_latest_month` | Computed | `SUM(downloads_latest_month)` at company level | Sum of latest-month downloads across all prospect apps under the company |
| TAB 1: `apps_with_other_exchange_sdk` | Computed | `SUM(CASE WHEN has_other_exchange_sdk THEN 1)` | Number of apps with other exchange SDKs but no Moloco SDK |

---

## Recommended Run Order

1. **Run List 1 (TAB 2 Company Summary) first** — verify that the COLD_PROSPECT company count looks reasonable; prioritize by `total_sdk_media_cost_usd_30d` descending
2. **Run Lists 2+3 (TAB 1 Company Summary)** — check the `total_downloads_latest_month` distribution; decide whether to adjust the 150K threshold
3. **List 4 (EXPANSION) last** — combine with `existing_spend_usd_90d` to assess expansion priority

## Data Refresh Schedule

| Data Source | Refresh Frequency | Used In |
|--------|---------|------|
| `fact_supply_with_tracking_publisher` | Daily | Lists 1/4: SDK signal, impression geo |
| `fact_dsp_core` | Daily | Lists 1/4: 90-day UA spend; Lists 2/3: UA spend exclusion |
| `supply_demand_overlap` | Daily (triggered by upstream) | Lists 1/4: Moloco status flags, eligibility, MMP |
| `dim1_app_v3` | Daily at 06:00 UTC | All lists: ST metadata, monetization_type |
| `fact_app_v3` | Daily (triggered downstream of dim1, ~2-day lag) | Lists 2/3: MoM downloads |
| `sensortower.network_analysis` | Every Wednesday | All lists: competitor UA networks |
| `sensortower.download_revenue_v3` | Daily (~2-day lag) | Lists 1/4 & 2/3: top DL/revenue country |
| `fact_dsp_publisher` | Daily | Lists 2/3: publisher exchange SDK signals |

---

## AI Agent Design

### china_confidence Logic and AI Agent Responsibilities

| Value | Condition | Handling |
|----|------|---------|
| `High` | `hq_country` is CN/CHN/CHINA/HK/HKG/TW/TWN | Enters prospect list directly |
| `Low-Review` | `hq_country` is SG/SGP, **or is empty/NULL** | Enters AI Agent review queue |
| `Unknown` | Any other country | Not included in any list |

**Why HK/TW is High**: Greater China registered entities; business falls within the China team's coverage scope.

**Why SG and empty values are Low-Review**:
- Singapore is the most common overseas registration jurisdiction for Chinese companies going global (ByteDance, Sea, and many others are registered in Singapore)
- `hq_country` being empty is a result of incomplete ST data coverage, not an indication that the company is non-Chinese

### AI Agent Review Process (Review Queue)

**Trigger condition**: `china_confidence = 'Low-Review'` (SG or empty value)

**Agent execution steps**:
1. Search company name (`canonical_company` / `company_name`) + keywords "China", "Chinese", "overseas expansion"
2. Check website (`website`) for language, copyright attribution, and ICP registration
3. Look up app store developer info (`bundle_id`)
4. Cross-validate: known attribution of other apps from the same company
5. Output judgment: `is_china_company: true/false` + `confidence_note`

**Concurrent entity resolution**:
- When `tracking_publisher_name` is empty (cold prospect) and similar company names exist
- Agent determines whether multiple `publisher_name` / `company_name` values belong to the same parent company
- Output: `canonical_company` normalized name suggestion

**Columns written to spreadsheet** (written back after manual confirmation):
- `ai_china_verified`: TRUE / FALSE / UNCERTAIN
- `ai_canonical_company`: Agent-suggested normalized company name
- `ai_review_note`: Reasoning behind the judgment (one sentence)
- `ai_reviewed_at`: Review timestamp
