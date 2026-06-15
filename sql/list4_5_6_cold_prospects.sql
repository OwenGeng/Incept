-- =============================================================================
-- Prospect Engine — List 4 / 5 / 6: Cold Prospects (No Prior Moloco Relationship)
-- =============================================================================
-- List 4 (IAA_Cold):
--   Pure IAA monetization (has_ads=T, has_iap=F) + scale threshold + no Moloco relationship
--   Goal: pitch Moloco SDK integration → run display UA campaigns
--   Typical: Casual / Hypercasual games, ad-supported non-gaming apps
--
-- List 5 (IAP_Cold):
--   Pure IAP monetization (has_ads=F, has_iap=T) + scale threshold + no Moloco relationship
--   Goal: direct UA campaign without SDK, ROAS-focused
--   Typical: Strategy / RPG / subscription apps
--
-- List 6 (Hybrid_Cold):
--   Dual monetization (has_ads=T, has_iap=T) + scale threshold + no Moloco relationship
--   monetization_type sub-types: Hybrid-IAA / Hybrid-IAP / Hybrid (non-gaming)
--   Goal: AM case-by-case judgment — dual SDK + UA opportunity
--   Typical: Merge games, casual RPGs, utility apps with subscriptions
--
-- ⚠️ Difference from List 3:
--   List 3: Company already has a Moloco supply relationship (is_supply_partner=true),
--           but this specific app hasn't integrated the SDK yet.
--   List 4/5/6: Company has NO prior Moloco relationship at all → pure cold outreach.
-- =============================================================================
-- Data sources:
--   fact_dsp_core                     → 90d UA spend (to exclude existing advertisers)
--   dim1_app_v3                       → ST app/company metadata + monetization_type
--   sensortower.fact_app_basis_v3     → Monthly downloads (scale threshold + primary market check)
--   sensortower.network_analysis      → Competitor UA networks (via st_app_id)
--   fact_dsp_publisher                → Publisher exchange SDK signals (sorted by impression volume)
--   sensortower.download_revenue_v3   → 30d top download/revenue country (via st_app_id)
--   gtm.supply_demand_overlap         → Moloco supply visibility signal (positive signal: IAA confirmation)
--   yingzi_uploads.hq_country_triage  → GTM-validated HQ country override
-- =============================================================================
-- monetization_type logic (is_gaming is the prerequisite; same rules for gaming and non-gaming):
--
--   Gaming (is_gaming = true):
--     has_ads=T, has_iap=F                          → IAA        → List 4
--     has_ads=F, has_iap=T                          → IAP        → List 5
--     has_ads=T, has_iap=T + IAA genre (whitelist)  → Hybrid-IAA → List 6
--     has_ads=T, has_iap=T + other genre            → Hybrid-IAP → List 6
--     has_ads=F, has_iap=F                          → Free (excluded from all lists)
--
--   Non-Gaming (is_gaming = false):
--     has_ads=T, has_iap=F                          → IAA        → List 4
--     has_ads=F, has_iap=T                          → IAP        → List 5
--     has_ads=T, has_iap=T                          → Hybrid     → List 6
--     has_ads=F, has_iap=F                          → Free (excluded from all lists)
--
-- IAA genre whitelist (only applies to gaming Hybrid tiebreaker; non-gaming uses has_ads directly):
--   Casual, Hypercasual, Puzzle, Brain & Puzzle,
--   Arcade, Arcade & Action,
--   Word, Board, Tabletop, Trivia,
--   Match, Party, Adventure,
--   Cards & Casino, Casino,
--   Kids, Kids & Family, Education
-- =============================================================================
-- Ranking (within each list):
--   Key 1: is_moloco_supply_visible DESC  (Moloco DSP already reaches this app → easiest SDK pitch)
--   Key 2: moloco_media_cost_usd_30d DESC (higher spend = better inventory quality signal)
--   Key 3: competitor_network_count DESC  (more active UA networks = stronger buying intent)
--   Key 4: downloads_latest_month DESC    (scale)
--   Key 5: download_growth_rate_mom DESC  (month-over-month momentum)
-- =============================================================================
WITH

-- ─────────────────────────────────────────────────────────────────
-- CTE 1a: Apps with Moloco UA spend in last 90 days (excluded)
-- ─────────────────────────────────────────────────────────────────
ua_spend AS (
  SELECT
    product.app_market_bundle    AS bundle_id,
    SUM(gross_spend_usd)         AS spend_90d
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND product.app_market_bundle IS NOT NULL
    AND product.app_market_bundle != ''
  GROUP BY 1
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 1b: Bundle-level exclusion — only exclude apps with Moloco SDK
-- Note: is_supply_partner=true does NOT mean the app has SDK.
-- It means Moloco DSP can reach this app's inventory via open exchange,
-- which is a POSITIVE IAA signal. Do NOT exclude on is_supply_partner.
-- ─────────────────────────────────────────────────────────────────
sdk_bundles_exclude AS (
  SELECT DISTINCT app_bundle
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  WHERE is_moloco_sdk_app = true   -- only exclude apps with actual Moloco SDK integration
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 1c: Company-level exclusion (dual-path match)
-- Fixes cases like ByteDance where a specific new app may not appear in
-- supply_demand_overlap, but the parent company is already a Moloco partner.
-- Path 1: supply_demand_overlap publisher_name (more reliable — GTM-curated)
-- Path 2: fact_dsp_core company_name with spend (catch-all fallback)
-- Match against both meta.company_name and meta.publisher_name for higher recall.
-- ─────────────────────────────────────────────────────────────────
moloco_known_companies AS (
  -- Path 1: companies with SDK or active UA advertiser relationship in supply_demand_overlap
  SELECT DISTINCT LOWER(TRIM(publisher_name)) AS company_key
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  WHERE (is_moloco_sdk_app = true OR is_moloco_advertiser_app = true)
    AND publisher_name IS NOT NULL
    AND TRIM(publisher_name) != ''
  UNION DISTINCT
  -- Path 2: companies with UA spend in fact_dsp_core over last 90 days (fallback)
  SELECT DISTINCT LOWER(TRIM(product.company_name)) AS company_key
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND gross_spend_usd > 0
    AND product.company_name IS NOT NULL
    AND TRIM(product.company_name) != ''
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 1d: Moloco supply visibility signals (positive signal, used in output)
-- is_supply_partner=true: Moloco DSP is already buying this app's inventory
--   via open exchange (not SDK). This CONFIRMS the app has IAA inventory.
-- SDK pitch angle: "We already buy your ad space — integrating our SDK
--   will improve your fill rate and eCPM."
-- ─────────────────────────────────────────────────────────────────
supply_visibility AS (
  SELECT
    app_bundle,
    MAX(is_supply_partner)   AS is_supply_partner,         -- Moloco DSP reachable via open exchange
    MAX(bid_requests)        AS sdl_bid_requests,          -- bid request volume
    MAX(media_cost_usd)      AS sdl_media_cost_usd_30d,    -- 30d media cost Moloco paid via open exchange
    MAX(media_cost_usd_7d)   AS sdl_media_cost_usd_7d,     -- 7d snapshot for recency check
    MAX(eligibility_status)  AS eligibility_status,
    MAX(ineligibility_reasons) AS ineligibility_reasons
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  GROUP BY app_bundle
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 2: App/company metadata + monetization_type
-- hq_country retained for pre-filter; renamed to sensortower_hq_country in output.
-- final_hq_country resolved via gtm_hq JOIN in app_level.
-- ─────────────────────────────────────────────────────────────────
meta AS (
  SELECT
    app_market_bundle,
    os,
    sensortower.product.app_id         AS st_app_id,
    sensortower.product.app_name       AS app_name,
    sensortower.product.has_ads        AS has_ads,
    sensortower.product.has_iap        AS has_iap,
    sensortower.product.unified_category_name AS category,
    sensortower.publisher.name         AS publisher_name,
    sensortower.publisher.website      AS publisher_website,
    sensortower.company.name           AS company_name,
    sensortower.company.hq_country     AS hq_country,
    sensortower.company.hq_region      AS hq_region,
    sensortower.company.website        AS company_website,
    sensortower.class.is_gaming        AS is_gaming,
    sensortower.class.genre            AS genre,
    sensortower.product.last_updated_time  AS app_last_updated_time,
    sensortower.product.first_release_date AS app_first_release_date,

    -- Monetization type classification
    CASE
      WHEN sensortower.class.is_gaming = true THEN
        CASE
          WHEN sensortower.product.has_iap = false AND sensortower.product.has_ads = true  THEN 'IAA'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = true  THEN 'IAP'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = false THEN 'Free'
          WHEN sensortower.product.has_ads = true AND sensortower.product.has_iap = true
           AND sensortower.class.genre IN (
             'Casual','Hypercasual','Puzzle','Brain & Puzzle','Arcade','Arcade & Action',
             'Word','Board','Tabletop','Trivia','Match','Party','Adventure',
             'Cards & Casino','Casino','Kids','Kids & Family','Education'
           ) THEN 'Hybrid-IAA'
          WHEN sensortower.product.has_ads = true AND sensortower.product.has_iap = true THEN 'Hybrid-IAP'
          ELSE 'Unknown'
        END
      WHEN sensortower.class.is_gaming = false THEN
        CASE
          WHEN sensortower.product.has_ads = true  AND sensortower.product.has_iap = false THEN 'IAA'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = true  THEN 'IAP'
          WHEN sensortower.product.has_ads = true  AND sensortower.product.has_iap = true  THEN 'Hybrid'
          ELSE 'Free'
        END
      ELSE 'Unknown'
    END AS monetization_type

  FROM `ads-bpd-guard-china.athena.dim1_app_v3`
  WHERE (
    UPPER(sensortower.company.hq_country) IN ('CN','CHN','CHINA','HK','HKG','TW','TWN','SG','SGP')
    OR sensortower.company.hq_country IS NULL
    OR TRIM(sensortower.company.hq_country) = ''
  )
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 3a: Global monthly downloads (used for scale threshold)
-- Source: fact_app_basis_v3 (has country dimension)
-- ─────────────────────────────────────────────────────────────────
downloads AS (
  SELECT
    app_market_bundle,
    SUM(CASE
          WHEN date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
          THEN monthly.download.`all` ELSE 0
        END) AS downloads_latest_month,
    SUM(CASE
          WHEN date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH), MONTH)
          THEN monthly.download.`all` ELSE 0
        END) AS downloads_prior_month
  FROM `ads-bpd-guard-china.sensortower.fact_app_basis_v3`
  WHERE date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH), MONTH)
    AND date_utc  < DATE_TRUNC(CURRENT_DATE(), MONTH)
  GROUP BY app_market_bundle
  HAVING SUM(CASE
    WHEN date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
    THEN monthly.download.`all` ELSE 0
  END) >= 20000   -- minimum 20K downloads in latest full month
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 3b: Primary market check (key filter — exclude domestic China apps)
-- Logic: find the country with the highest monthly downloads for each app.
-- If that country is CN/HK/TW/MO → the app is domestic-first → excluded.
-- Example: WeChat top country = CN → excluded; SHEIN top country = US → kept.
-- Source: fact_app_basis_v3 (has country + monthly.download.all)
-- ─────────────────────────────────────────────────────────────────
primary_market AS (
  SELECT
    app_market_bundle,
    MAX(CASE WHEN dl_rank = 1 THEN country END) AS top_country_latest_month
  FROM (
    SELECT
      app_market_bundle,
      country,
      ROW_NUMBER() OVER (
        PARTITION BY app_market_bundle
        ORDER BY SUM(monthly.download.`all`) DESC
      ) AS dl_rank
    FROM `ads-bpd-guard-china.sensortower.fact_app_basis_v3`
    WHERE date_utc = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
      AND monthly.download.`all` > 0
      AND country IS NOT NULL
    GROUP BY app_market_bundle, country
  )
  GROUP BY app_market_bundle
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 4: Competitor UA network signals (ST network_analysis, demand-side)
-- Shows which ad networks the app is actively buying UA on.
-- competitor_network_count used internally for prospect_label and ranking.
-- ─────────────────────────────────────────────────────────────────
net_signals AS (
  SELECT
    app_id,
    STRING_AGG(DISTINCT network ORDER BY network)              AS active_ua_networks,
    MAX(CASE WHEN LOWER(network) LIKE '%applovin%' OR LOWER(network) LIKE '%max%' THEN 1 ELSE 0 END) AS on_applovin,
    MAX(CASE WHEN LOWER(network) LIKE '%facebook%' OR LOWER(network) LIKE '%meta%' THEN 1 ELSE 0 END) AS on_meta,
    MAX(CASE WHEN LOWER(network) LIKE '%google%' OR LOWER(network) LIKE '%uac%'    THEN 1 ELSE 0 END) AS on_google,
    COUNTIF(LOWER(network) NOT LIKE '%moloco%')                AS competitor_network_count
  FROM `ads-bpd-guard-china.sensortower.network_analysis`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  GROUP BY app_id
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 5a: Publisher exchange SDK signals (raw, per exchange)
-- Collect impression volume per (bundle, exchange) for downstream sorting.
-- ─────────────────────────────────────────────────────────────────
pub_exchange_raw AS (
  SELECT
    publisher.app_market_bundle  AS bundle_id,
    exchange,
    SUM(impressions)             AS exchange_impressions
  FROM `ads-bpd-guard-china.athena.fact_dsp_publisher`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND is_complete_date_utc = true
    AND publisher.app_market_bundle IS NOT NULL
  GROUP BY publisher.app_market_bundle, exchange
),

-- CTE 5b: Publisher exchange SDK signals (aggregated, sorted by impression volume DESC)
-- active_other_exchange_sdks: non-Moloco exchanges the publisher is connected to,
-- ordered by impression volume (e.g. "APPLOVIN, UNITY, INMOBI" — APPLOVIN has most impressions)
pub_exchange AS (
  SELECT
    bundle_id,
    MAX(CASE WHEN STARTS_WITH(exchange, 'MOLOCO_SDK') THEN 1 ELSE 0 END) AS pub_has_moloco_sdk,
    COUNTIF(NOT STARTS_WITH(exchange, 'MOLOCO'))                          AS pub_other_exchange_count,
    STRING_AGG(
      CASE WHEN NOT STARTS_WITH(exchange, 'MOLOCO') THEN exchange END,
      ', ' ORDER BY exchange_impressions DESC
    )                                                                     AS pub_other_exchange_list
  FROM pub_exchange_raw
  GROUP BY bundle_id
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 6: T1 country downloads (sensortower.download_revenue_v3, 30d window)
-- T1 markets: US, CA, DE, FR, GB, AU, JP, KR, TW
-- t1_downloads_total: sum of downloads across all T1 countries in 30d
-- top_dl_country_T1: which T1 country has the highest 30d downloads
-- ─────────────────────────────────────────────────────────────────
geo_raw AS (
  SELECT
    app_id,
    country_code,
    SUM(download) AS dl_30d
  FROM `ads-bpd-guard-china.sensortower.download_revenue_v3`
  WHERE date_utc >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
    AND date_utc  <  DATE_TRUNC(CURRENT_DATE(), MONTH)
    AND country_code IN ('US','CA','DE','FR','GB','AU','JP','KR','TW')
    AND app_id IS NOT NULL
  GROUP BY app_id, country_code
),

geo_metrics AS (
  SELECT
    app_id,
    SUM(dl_30d)                                                AS t1_downloads_total,
    MAX(CASE WHEN dl_rank = 1 THEN country_code END)           AS top_dl_country_T1,
    MAX(CASE WHEN dl_rank = 1 THEN dl_30d END)                 AS top_dl_country_T1_downloads
  FROM (
    SELECT *,
      ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY dl_30d DESC) AS dl_rank
    FROM geo_raw
  )
  GROUP BY app_id
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 7: GTM-validated HQ country mapping
-- Join key: hq_country_triage.company_name = meta.company_name (ST company name)
-- final_hq_country: GTM team's verified actual country — takes priority over ST value.
-- hq_country_source: 'GTM_triage' = verified; 'ST_original' = unverified ST fallback
-- ─────────────────────────────────────────────────────────────────
gtm_hq AS (
  SELECT
    company_name,
    final_hq_country,
    is_manually_corrected
  FROM `ads-bpd-guard-sandbox.yingzi_uploads.hq_country_triage`
  WHERE final_hq_country IS NOT NULL
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 8: App-level result (intermediate layer for company-level aggregation)
-- ─────────────────────────────────────────────────────────────────
app_level AS (
  SELECT
    CASE
      WHEN m.monetization_type = 'IAA'                                   THEN 'List_IAA_New'
      WHEN m.monetization_type = 'IAP'                                   THEN 'List_IAP_New'
      WHEN m.monetization_type IN ('Hybrid-IAA', 'Hybrid-IAP', 'Hybrid') THEN 'List_Hybrid_New'
    END                                                                AS list_type,
    m.app_market_bundle,
    m.os,
    m.app_name,
    m.company_name,           -- primary company identifier (no tracking_publisher_name available for cold prospects)
    m.publisher_name,
    m.hq_country                                                       AS sensortower_hq_country,  -- ST raw value
    COALESCE(gtm.final_hq_country, m.hq_country)                      AS final_hq_country,         -- GTM override if available
    CASE
      WHEN gtm.final_hq_country IS NOT NULL THEN 'GTM_triage'
      ELSE 'ST_original'
    END                                                                AS hq_country_source,
    gtm.is_manually_corrected,
    m.hq_region,
    COALESCE(m.publisher_website, m.company_website)                  AS website,
    m.app_last_updated_time,
    m.app_first_release_date,
    m.is_gaming,
    CASE WHEN m.is_gaming THEN 'Gaming' ELSE 'Non-Gaming' END         AS team_routing,
    -- Monetization override: Moloco media_cost > 0 proves IAA inventory exists
    -- Overrides ST's has_ads=false when Moloco is actually buying their supply
    CASE
      WHEN COALESCE(sv.sdl_media_cost_usd_30d, 0) > 0
       AND m.monetization_type = 'IAP'
        THEN 'Hybrid-IAP'   -- ST says no ads but Moloco buys supply → hybrid
      WHEN COALESCE(sv.sdl_media_cost_usd_30d, 0) > 0
       AND m.monetization_type = 'Free'
        THEN 'IAA'           -- ST says no monetization but Moloco buys → IAA confirmed
      ELSE m.monetization_type
    END                                                                AS monetization_type,
    m.genre,
    -- Download figures with month labels
    FORMAT_DATE('%Y-%m', DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH))
                                                                       AS downloads_month,              -- e.g. 2026-05
    FORMAT_DATE('%Y-%m', DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH), MONTH))
                                                                       AS downloads_prior_month_label,  -- e.g. 2026-04
    d.downloads_latest_month,
    d.downloads_prior_month,
    CASE
      WHEN d.downloads_prior_month = 0 AND d.downloads_latest_month > 0 THEN 1.0
      ELSE ROUND(SAFE_DIVIDE(
        CAST(d.downloads_latest_month - d.downloads_prior_month AS FLOAT64),
        NULLIF(CAST(d.downloads_prior_month AS FLOAT64), 0)
      ), 4)
    END                                                                AS download_growth_rate_mom,
    -- Competitor UA networks (demand-side)
    COALESCE(n.active_ua_networks, 'No Active Networks')              AS active_ua_networks,
    COALESCE(n.competitor_network_count, 0)                           AS competitor_network_count,  -- used internally for ranking
    -- Publisher exchange SDK signals (supply-side)
    CASE
      WHEN COALESCE(pe.pub_other_exchange_count, 0) > 0
       AND COALESCE(pe.pub_has_moloco_sdk, 0) = 0 THEN true
      ELSE false
    END                                                                AS has_other_exchange_sdk,
    COALESCE(pe.pub_other_exchange_list, 'None')                      AS active_other_exchange_sdks,
    -- Moloco supply visibility (from supply_demand_overlap — positive signal)
    -- is_supply_partner=true → Moloco DSP already buying this app's inventory via open exchange.
    -- Strongest IAA confirmation + best SDK pitch entry point.
    COALESCE(sv.is_supply_partner, false)                             AS is_moloco_supply_visible,
    COALESCE(sv.sdl_bid_requests, 0)                                  AS moloco_bid_requests,
    COALESCE(sv.sdl_media_cost_usd_30d, 0)                           AS moloco_media_cost_usd_30d,   -- 30d media cost Moloco paid via open exchange
    COALESCE(sv.sdl_media_cost_usd_7d, 0)                            AS moloco_media_cost_usd_7d,    -- 7d snapshot
    sv.eligibility_status                                             AS sdl_eligibility_status,
    -- T1 market downloads from sensortower.download_revenue_v3 (30d)
    -- T1: US, CA, DE, FR, GB, AU, JP, KR, TW
    g.t1_downloads_total,           -- total downloads across all T1 countries (30d)
    g.top_dl_country_T1,            -- which T1 country has the highest downloads
    g.top_dl_country_T1_downloads,
    -- Prospect priority label — two independent paths by monetization type:
    --   IAP path  : supply-visibility is always false → rank by download scale + UA market signals
    --   IAA/Hybrid: existing supply-visibility + media-cost logic (unchanged)
    -- _priority_code() reads the P1/P2/P3/P4 prefix, so both paths feed the same filter/sort.
    CASE
      -- ── List 5 (IAP): UA-pitch priority based on download scale ─────────────
      WHEN m.monetization_type = 'IAP' THEN
        CASE
          -- P1: large downloads + already spending on competitor UA + T1 market presence
          WHEN d.downloads_latest_month >= 100000
           AND COALESCE(n.competitor_network_count, 0) > 0
           AND COALESCE(g.t1_downloads_total, 0) > 0           THEN 'P1 — UA Ready'
          -- P2: meaningful scale + T1 presence (not yet on UA networks)
          WHEN d.downloads_latest_month >= 50000
           AND COALESCE(g.t1_downloads_total, 0) > 0            THEN 'P2 — T1 Scale'
          -- P3: growing app, smaller scale
          WHEN d.downloads_latest_month >= 20000                THEN 'P3 — Growing'
          ELSE                                                        'P4 — Cold'
        END
      -- ── List 4/6 (IAA/Hybrid): supply-visibility + media-cost ───────────────
      -- P1: CHN only, all 4 signals — NBS direct priority
      WHEN UPPER(COALESCE(gtm.final_hq_country, m.hq_country)) IN ('CHN','CHINA','CN')
       AND COALESCE(sv.is_supply_partner, false) = true
       AND COALESCE(sv.sdl_media_cost_usd_30d, 0) > 2000
       AND d.downloads_latest_month >= 100000
       AND SAFE_DIVIDE(
             CAST(d.downloads_latest_month - d.downloads_prior_month AS FLOAT64),
             NULLIF(CAST(d.downloads_prior_month AS FLOAT64), 0)
           ) > 0.1
        THEN 'P1 — Prime'
      -- P2: CHN only, sv + mc>$500 + dl>=50K + MoM>-10%
      WHEN UPPER(COALESCE(gtm.final_hq_country, m.hq_country)) IN ('CHN','CHINA','CN')
       AND COALESCE(sv.is_supply_partner, false) = true
       AND COALESCE(sv.sdl_media_cost_usd_30d, 0) > 500
       AND d.downloads_latest_month >= 50000
       AND SAFE_DIVIDE(
             CAST(d.downloads_latest_month - d.downloads_prior_month AS FLOAT64),
             NULLIF(CAST(d.downloads_prior_month AS FLOAT64), 0)
           ) > -0.1
        THEN 'P2 — Strong'
      -- P3: supply visible (CHN remainder + SGP)
      WHEN COALESCE(sv.is_supply_partner, false) = true
       AND COALESCE(sv.sdl_media_cost_usd_30d, 0) > 0
        THEN 'P3 — Visible'
      ELSE 'P4 — Cold'
    END                                                                AS prospect_label,
    -- Numeric score for company-level aggregation (1=best), mirrors prospect_label
    CASE
      -- IAP path
      WHEN m.monetization_type = 'IAP' THEN
        CASE
          WHEN d.downloads_latest_month >= 100000
           AND COALESCE(n.competitor_network_count, 0) > 0
           AND COALESCE(g.t1_downloads_total, 0) > 0           THEN 1
          WHEN d.downloads_latest_month >= 50000
           AND COALESCE(g.t1_downloads_total, 0) > 0            THEN 2
          WHEN d.downloads_latest_month >= 20000                THEN 3
          ELSE                                                        4
        END
      -- IAA/Hybrid path (unchanged)
      WHEN UPPER(COALESCE(gtm.final_hq_country, m.hq_country)) IN ('CHN','CHINA','CN')
       AND COALESCE(sv.is_supply_partner, false) = true
       AND COALESCE(sv.sdl_media_cost_usd_30d, 0) > 2000
       AND d.downloads_latest_month >= 100000
       AND SAFE_DIVIDE(
             CAST(d.downloads_latest_month - d.downloads_prior_month AS FLOAT64),
             NULLIF(CAST(d.downloads_prior_month AS FLOAT64), 0)
           ) > 0.1                                                                THEN 1
      WHEN UPPER(COALESCE(gtm.final_hq_country, m.hq_country)) IN ('CHN','CHINA','CN')
       AND COALESCE(sv.is_supply_partner, false) = true
       AND COALESCE(sv.sdl_media_cost_usd_30d, 0) > 500
       AND d.downloads_latest_month >= 50000
       AND SAFE_DIVIDE(
             CAST(d.downloads_latest_month - d.downloads_prior_month AS FLOAT64),
             NULLIF(CAST(d.downloads_prior_month AS FLOAT64), 0)
           ) > -0.1                                                               THEN 2
      WHEN COALESCE(sv.is_supply_partner, false) = true
       AND COALESCE(sv.sdl_media_cost_usd_30d, 0) > 0                            THEN 3
      ELSE 4
    END                                                                AS priority_score
  FROM meta m
  INNER JOIN downloads d         ON m.app_market_bundle = d.app_market_bundle
  INNER JOIN primary_market pm   ON m.app_market_bundle = pm.app_market_bundle  -- domestic app check
  LEFT JOIN gtm_hq     gtm       ON m.company_name = gtm.company_name
  LEFT JOIN ua_spend u            ON m.app_market_bundle = u.bundle_id
  -- Exclude apps with Moloco SDK (belong to List 1/2/3)
  LEFT JOIN sdk_bundles_exclude  sdk_ex ON m.app_market_bundle = sdk_ex.app_bundle
  LEFT JOIN supply_visibility    sv     ON m.app_market_bundle = sv.app_bundle
  LEFT JOIN net_signals n        ON m.st_app_id = n.app_id
  LEFT JOIN geo_metrics g        ON m.st_app_id = g.app_id
  LEFT JOIN pub_exchange pe      ON m.app_market_bundle = pe.bundle_id
  WHERE
    COALESCE(u.spend_90d, 0) = 0                          -- bundle-level: no Moloco UA spend
    AND sdk_ex.app_bundle IS NULL                         -- bundle-level: no Moloco SDK
    -- Company-level exclusion (dual-path match):
    -- Exclude any app whose company/publisher matches a known Moloco partner.
    -- Covers subsidiaries and new apps from existing partners (e.g. ByteDance).
    AND LOWER(TRIM(m.company_name))   NOT IN (SELECT company_key FROM moloco_known_companies)
    AND LOWER(TRIM(m.publisher_name)) NOT IN (SELECT company_key FROM moloco_known_companies)
    AND m.monetization_type IN ('IAA', 'IAP', 'Hybrid-IAA', 'Hybrid-IAP', 'Hybrid')
    -- Exclude domestic apps: if the #1 download market is China/HK/TW/MO,
    -- the app is primarily domestic-facing — not an overseas UA target.
    AND UPPER(pm.top_country_latest_month) NOT IN (
      'CN','CHN','CHINA','HK','HKG','TW','TWN','MO','MAC'
    )
    -- Country filter (strict positive match only — no null/empty passthrough):
    -- Only include companies positively identified as Greater China / Singapore.
    -- Removed OR IS NULL fallback to prevent non-China companies (e.g. DEU, USA)
    -- from entering the list when both GTM and ST country data are missing.
    AND (
      UPPER(COALESCE(gtm.final_hq_country, m.hq_country)) IN (
        'CN','CHN','CHINA','HK','HKG','TW','TWN','SG','SGP'
      )
      OR (gtm.is_manually_corrected = true
          AND UPPER(gtm.final_hq_country) IN ('CN','CHN','CHINA','HK','HKG','TW','TWN','SG','SGP'))
    )
),

-- ─────────────────────────────────────────────────────────────────
-- CTE 9: Company-level aggregation (TAB 1)
-- ─────────────────────────────────────────────────────────────────
company_level AS (
  SELECT
    -- list_type removed from GROUP BY — one row per company regardless of monetization mix
    company_name,
    STRING_AGG(DISTINCT list_type, ', ' ORDER BY list_type)           AS list_types,   -- e.g. "List4_IAA_New, List6_Hybrid_New"
    MAX(sensortower_hq_country)                                        AS sensortower_hq_country,
    MAX(final_hq_country)                                              AS final_hq_country,
    MAX(hq_country_source)                                             AS hq_country_source,
    MAX(is_manually_corrected)                                         AS is_manually_corrected,
    MAX(hq_region)                                                     AS hq_region,
    MAX(team_routing)                                                  AS team_routing,
    MAX(website)                                                       AS website,
    STRING_AGG(DISTINCT monetization_type, ', ')                      AS monetization_types,  -- e.g. "IAA, Hybrid-IAA"
    -- App counts by monetization type (one company can have multiple types)
    COUNT(DISTINCT app_market_bundle)                                  AS total_apps,
    COUNT(DISTINCT CASE WHEN monetization_type = 'IAA'                THEN app_market_bundle END) AS iaa_app_count,
    COUNT(DISTINCT CASE WHEN monetization_type IN ('IAP')              THEN app_market_bundle END) AS iap_app_count,
    COUNT(DISTINCT CASE WHEN monetization_type IN ('Hybrid-IAA','Hybrid-IAP','Hybrid')
                                                                       THEN app_market_bundle END) AS hybrid_app_count,
    SUM(downloads_latest_month)                                        AS total_downloads_latest_month,
    MAX(downloads_month)                                               AS downloads_month,
    -- Aggregate active UA networks across all apps in the company
    STRING_AGG(DISTINCT active_ua_networks, ', ')                      AS all_active_networks,
    -- Company prospect label: best (lowest score) app tier determines the company tier
    CASE MIN(priority_score)
      WHEN 1 THEN 'P1 — Prime'
      WHEN 2 THEN 'P2 — Strong'
      WHEN 3 THEN 'P3 — Visible'
      ELSE        'P4 — Cold'
    END                                                                AS company_prospect_label,
    MAX(CASE WHEN is_moloco_supply_visible THEN true ELSE false END)   AS is_moloco_supply_visible,
    SUM(moloco_media_cost_usd_30d)                                     AS moloco_media_cost_usd_30d,
    SUM(CASE WHEN has_other_exchange_sdk THEN 1 ELSE 0 END)           AS apps_with_other_exchange_sdk,
    -- Exchange list across all apps with other exchange SDKs
    STRING_AGG(
      DISTINCT CASE WHEN has_other_exchange_sdk THEN active_other_exchange_sdks END,
      ' | '
    )                                                                  AS other_exchange_sdk_detail,
    CURRENT_DATE()                                                     AS data_as_of
  FROM app_level
  WHERE company_name IS NOT NULL AND TRIM(company_name) != ''
  GROUP BY company_name  -- one row per company regardless of monetization mix
)

-- =============================================================================
-- TAB 1: COMPANY SUMMARY (default)
-- To switch to TAB 2 App Detail: comment out this block and uncomment below.
-- =============================================================================
SELECT
  company_name,
  list_types,               -- all lists this company's apps appear in (e.g. "List4_IAA_New, List6_Hybrid_New")
  company_prospect_label,   -- P1/P2/P3/P4 based on best app in company
  sensortower_hq_country,
  final_hq_country,
  hq_region,
  team_routing,
  website,
  monetization_types,       -- all monetization types present (e.g. "IAA, Hybrid-IAA")
  total_apps,
  iaa_app_count,
  hybrid_app_count,
  iap_app_count,
  downloads_month,
  total_downloads_latest_month,
  is_moloco_supply_visible,
  moloco_media_cost_usd_30d,
  all_active_networks,
  apps_with_other_exchange_sdk,
  other_exchange_sdk_detail,
  data_as_of
FROM company_level
WHERE company_name IS NOT NULL AND TRIM(company_name) != ''
ORDER BY
  company_prospect_label ASC,       -- P1 → P2 → P3 → P4
  total_downloads_latest_month DESC
;

-- =============================================================================
-- TAB 2: APP DETAIL (uncomment this block to replace TAB 1)
-- =============================================================================
/*
SELECT
  list_type,
  prospect_label,
  app_market_bundle,
  os,
  app_name,
  company_name,
  publisher_name,
  sensortower_hq_country,         -- ST raw HQ country
  final_hq_country,               -- GTM-verified HQ country (preferred)
  hq_country_source,              -- 'GTM_triage' = verified; 'ST_original' = unverified fallback
  hq_region,
  website,
  team_routing,
  monetization_type,
  genre,
  downloads_month,                -- period label for downloads_latest_month (e.g. 2026-05)
  downloads_prior_month_label,    -- prior month label (e.g. 2026-04)
  downloads_latest_month,         -- latest full month global downloads (domestic apps already excluded)
  downloads_prior_month,          -- prior full month global downloads (MoM denominator)
  download_growth_rate_mom,       -- month-over-month growth rate (latest / prior - 1)
  active_ua_networks,             -- UA networks active in last 90d (comma-separated, sorted by impression vol)
  has_other_exchange_sdk,         -- true = connected to other exchange SDK(s) but no Moloco SDK
  active_other_exchange_sdks,     -- which exchanges (sorted by impression volume, descending)
  -- Moloco supply visibility (from supply_demand_overlap)
  is_moloco_supply_visible,       -- true = Moloco DSP already buying this app's inventory via open exchange
  moloco_media_cost_usd_30d,      -- 30d media cost Moloco paid for this app via open exchange
  moloco_media_cost_usd_7d,       -- 7d snapshot (recency check)
  moloco_bid_requests,            -- bid request volume
  sdl_eligibility_status,         -- Moloco eligibility status
  app_last_updated_time,          -- ST last app update time
  app_first_release_date,         -- ST first release date
  -- T1 market downloads (US, CA, DE, FR, GB, AU, JP, KR, TW) from download_revenue_v3 (30d)
  t1_downloads_total,             -- total downloads across all T1 countries
  top_dl_country_T1,              -- T1 country with highest downloads
  top_dl_country_T1_downloads
FROM app_level
WHERE company_name != 'Unknown'
ORDER BY
  list_type ASC,
  is_moloco_supply_visible DESC,   -- Moloco-visible supply first — easiest SDK pitch
  moloco_media_cost_usd_30d DESC,  -- higher spend = better inventory quality
  competitor_network_count DESC,
  downloads_latest_month DESC,
  download_growth_rate_mom DESC;
*/
