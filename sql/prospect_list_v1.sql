-- =============================================================================
-- Prospect Engine V1 — Master Prospect List
-- Output: flat table, ready for Google Sheets export
-- Tables used:
--   supply_demand_overlap              → Moloco SDK + 30d UA status
--   dim1_app_v3                        → app/company metadata, China ID
--   fact_app_v3                        → downloads, revenue, growth (ST)
--   network_analysis                   → demand-side competitor signals (ST)
--   fact_dsp_publisher                 → supply-side exchange SDK signals
--   fact_dsp_core                      → 90d advertiser spend (authoritative)
--   fact_supply_with_tracking_publisher → canonical GTM publisher mapping
-- =============================================================================
-- Update these literal dates before running:
--   DATE '2026-05-01'   = first day of last full month
--   DATE '2026-03-01'   = 90d window start (3 months ago)
--   DATE '2025-12-01'   = 180d window start (6 months ago, for growth comparison)
--   DATE '2026-05-19'   = 14d ago (for tracking_publisher lookup)
-- =============================================================================
-- FIELD NOTES (confirmed from BQ Agent investigations):
--   fact_dsp_core.gross_spend_usd    = advertiser UA spend  ← use this
--   fact_dsp_core.pb_revenue_usd     = post-back revenue    ← do NOT use for spend
--   fact_dsp_core: require_filter=true on date_utc, use literal dates
--   fact_dsp_core: only contains apps with campaign activity; absent = truly no UA
--   supply_demand_overlap.gross_spend_usd = 30d rolling window, NOT 90d
--   Moloco SDK in fact_dsp_publisher = STARTS_WITH(exchange, 'MOLOCO_SDK')
--   is_sdk_app_any in supply_demand_overlap = Moloco SDK rollup (not "any exchange")
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- CTE 1: supply_demand_overlap — Moloco SDK/UA status, deduplicated
-- ---------------------------------------------------------------------------
sdl AS (
  SELECT
    app_bundle,
    os,
    MAX(is_moloco_sdk_app)         AS is_moloco_sdk_app,
    MAX(is_moloco_advertiser_app)  AS is_moloco_advertiser_app,
    MAX(is_iaa_app_any)            AS is_iaa_app_any,
    MAX(is_supply_partner)         AS is_supply_partner,
    SUM(gross_spend_usd)           AS gross_spend_usd_30d,   -- 30d only, use fact_dsp_core for 90d
    SUM(gross_spend_usd_iaa)       AS gross_spend_usd_iaa,
    SUM(bid_requests)              AS bid_requests,
    SUM(sdk_media_cost_usd)        AS sdk_media_cost_usd,
    MAX(eligibility_status)        AS eligibility_status,
    MAX(ineligibility_reasons)     AS ineligibility_reasons,
    MAX(success_threshold_status)  AS success_threshold_status,
    MAX(mmp)                       AS mmp,
    MAX(pub_rank_30d)              AS pub_rank_30d,
    MAX(advertiser_name)           AS advertiser_name
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  GROUP BY app_bundle, os
),

-- ---------------------------------------------------------------------------
-- CTE 2: fact_dsp_core — 90-day advertiser UA spend (authoritative)
-- Correct field: gross_spend_usd (NOT pb_revenue_usd which is post-back revenue)
-- Apps absent from this table = truly no UA campaign activity at all.
-- LEFT JOIN in base CTE; filter on IS NULL OR = 0 to catch both cases.
-- ---------------------------------------------------------------------------
ua_spend_90d AS (
  SELECT
    product.app_market_bundle    AS app_market_bundle,
    SUM(gross_spend_usd)         AS ua_spend_usd_90d
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE '2026-03-01'
    AND date_utc <= DATE '2026-05-31'
    AND product.app_market_bundle IS NOT NULL
    AND product.app_market_bundle != ''
  GROUP BY 1
),

-- ---------------------------------------------------------------------------
-- CTE 3: dim1_app_v3 — app and company metadata from Sensor Tower
-- ---------------------------------------------------------------------------
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
    sensortower.company.parent.id      AS parent_company_id,
    sensortower.company.parent.name    AS parent_company_name,
    sensortower.class.is_gaming        AS is_gaming,
    sensortower.class.genre            AS genre,
    sensortower.class.subgenre         AS subgenre
  FROM `ads-bpd-guard-china.athena.dim1_app_v3`
),

-- ---------------------------------------------------------------------------
-- CTE 4: tracking_publisher_name — GTM canonical publisher mapping
-- Only covers apps Moloco DSP has bought supply from.
-- Value: resolves parent-publisher remaps (e.g. BeReal → VOODOO) that
-- Sensor Tower parent_company may miss.
-- Use 14-day window — canonical name doesn't change, small window = cheap.
-- ---------------------------------------------------------------------------
tracking_pub AS (
  SELECT
    req.app_bundle                  AS app_bundle,
    MAX(tracking_publisher_name)    AS tracking_publisher_name
  FROM `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`
  WHERE date_utc >= DATE '2026-05-19'
    AND date_utc <= DATE '2026-06-02'
    AND req.app_bundle IS NOT NULL
    AND tracking_publisher_name IS NOT NULL
  GROUP BY 1
),

-- ---------------------------------------------------------------------------
-- CTE 5: fact_app_v3 — downloads, revenue, growth (WW, monthly aggregated)
-- monthly.download.`all` needs backtick — `all` is a BQ reserved word.
-- ---------------------------------------------------------------------------
fact_agg AS (
  SELECT
    app_market_bundle,
    SUM(CASE WHEN date_utc = DATE '2026-05-01'
        THEN monthly.download.`all` ELSE 0 END)                          AS downloads_latest_month,
    SUM(CASE WHEN date_utc >= DATE '2026-03-01'
        THEN monthly.download.`all` ELSE 0 END)                          AS downloads_90d,
    SUM(CASE WHEN date_utc >= DATE '2025-12-01'
             AND date_utc <  DATE '2026-03-01'
        THEN monthly.download.`all` ELSE 0 END)                          AS downloads_prior_90d,
    SUM(CASE WHEN date_utc = DATE '2026-05-01'
        THEN monthly.revenue ELSE 0 END)                                 AS revenue_latest_month,
    SUM(CASE WHEN date_utc = DATE '2026-05-01'
        THEN monthly.channel.paid + monthly.channel.paid_ads ELSE 0 END) AS paid_downloads_30d
  FROM `ads-bpd-guard-china.athena.fact_app_v3`
  WHERE date_utc >= DATE '2025-12-01'
    AND date_utc <= DATE '2026-05-31'
  GROUP BY app_market_bundle
),

-- ---------------------------------------------------------------------------
-- CTE 6: network_analysis — demand-side competitor signals (last 90 days)
-- Shows which ad networks the app is actively BUYING UA on.
-- ---------------------------------------------------------------------------
net_agg AS (
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
  WHERE date_utc >= DATE '2026-03-01'
  GROUP BY app_id
),

-- ---------------------------------------------------------------------------
-- CTE 7: fact_dsp_publisher — supply-side exchange SDK signals
-- Shows which SSP/exchange Moloco DSP has bought inventory through.
-- publisher.app_market_bundle = the supply-side (publisher) app.
-- Moloco SDK = STARTS_WITH(exchange, 'MOLOCO_SDK') — not bare 'MOLOCO'.
-- ---------------------------------------------------------------------------
pub_exchange AS (
  SELECT
    publisher.app_market_bundle                                               AS app_bundle,
    MAX(CASE WHEN STARTS_WITH(exchange, 'MOLOCO_SDK')       THEN 1 ELSE 0 END) AS pub_has_moloco_sdk,
    MAX(CASE WHEN exchange = 'MOLOCO_SDK_MAX'                THEN 1 ELSE 0 END) AS pub_via_applovin_max,
    MAX(CASE WHEN exchange = 'MOLOCO_SDK_ADMOB_MEDIATION'    THEN 1 ELSE 0 END) AS pub_via_admob,
    MAX(CASE WHEN exchange = 'MOLOCO_SDK_LEVELPLAY'          THEN 1 ELSE 0 END) AS pub_via_levelplay,
    MAX(CASE WHEN exchange = 'MOLOCO_SDK_IN_HOUSE_MEDIATION' THEN 1 ELSE 0 END) AS pub_via_inhouse,
    MAX(CASE WHEN exchange = 'APPLOVIN'                      THEN 1 ELSE 0 END) AS pub_on_applovin_exchange,
    MAX(CASE WHEN exchange = 'UNITY'                         THEN 1 ELSE 0 END) AS pub_on_unity_exchange,
    MAX(CASE WHEN exchange = 'IRONSOURCE'                    THEN 1 ELSE 0 END) AS pub_on_ironsource_exchange,
    MAX(CASE WHEN exchange = 'VUNGLE'                        THEN 1 ELSE 0 END) AS pub_on_vungle_exchange,
    MAX(CASE WHEN exchange = 'FYBER'                         THEN 1 ELSE 0 END) AS pub_on_fyber_exchange,
    MAX(CASE WHEN exchange = 'INMOBI'                        THEN 1 ELSE 0 END) AS pub_on_inmobi_exchange,
    MAX(CASE WHEN exchange = 'APPODEAL'                      THEN 1 ELSE 0 END) AS pub_on_appodeal_exchange,
    COUNTIF(NOT STARTS_WITH(exchange, 'MOLOCO'))                                AS pub_other_exchange_count
  FROM `ads-bpd-guard-china.athena.fact_dsp_publisher`
  WHERE date_utc >= DATE '2026-03-01'
    AND date_utc <= DATE '2026-05-31'
    AND is_complete_date_utc = true
    AND publisher.app_market_bundle IS NOT NULL
  GROUP BY publisher.app_market_bundle
),

-- ---------------------------------------------------------------------------
-- CTE 8: Master join
-- Base = meta (dim1_app_v3 = full ST universe).
-- LEFT JOIN everything else — null = no Moloco/DSP relationship yet.
-- ---------------------------------------------------------------------------
base AS (
  SELECT
    -- Identity
    m.app_market_bundle,
    m.os,
    m.app_name,
    m.st_app_id,

    -- Entity resolution:
    --   tracking_publisher_name = GTM canonical (best for existing Moloco customers)
    --   parent_company_name     = ST parent company (covers cold prospects too)
    --   Use tracking name where available; fall back to ST parent
    tp.tracking_publisher_name,
    COALESCE(tp.tracking_publisher_name, m.parent_company_name) AS canonical_company,
    m.company_name,
    m.parent_company_name         AS st_parent_company,
    m.parent_company_id,
    m.hq_country,
    m.hq_region,
    m.publisher_name,
    COALESCE(m.publisher_website, m.company_website) AS website,

    -- China identification (Layer 1: structured HQ field)
    CASE
      WHEN UPPER(m.hq_country) IN ('CN', 'CHN', 'CHINA')      THEN 'High'
      WHEN UPPER(m.hq_country) IN ('HK', 'HKG', 'TW', 'TWN')  THEN 'Medium'
      WHEN UPPER(m.hq_country) IN ('SG', 'SGP')                THEN 'Low-Review'
      ELSE                                                           'Unknown'
    END AS china_confidence,

    -- Product classification
    m.is_gaming,
    m.genre,
    m.subgenre,
    m.category,
    m.has_ads,
    m.has_iap,
    CASE WHEN m.is_gaming THEN 'Gaming' ELSE 'Non-Gaming' END AS team_routing,

    -- Monetization type (ST has_ads / has_iap — more reliable than genre alone)
    -- Logic:
    --   has_iap = false AND has_ads = true  → pure IAA (no purchase model)
    --   has_ads = false AND has_iap = true  → pure IAP (no ad model)
    --   has_ads = false AND has_iap = false → Free / no monetization signal
    --   Both true → Hybrid; use genre as tiebreaker for UA approach
    CASE
      WHEN m.has_iap = false AND m.has_ads = true
        THEN 'IAA'
      WHEN m.has_ads = false AND m.has_iap = true
        THEN 'IAP'
      WHEN m.has_ads = false AND m.has_iap = false
        THEN 'Free'
      WHEN m.has_ads = true AND m.has_iap = true
       AND m.genre IN ('Casual','Puzzle','Hypercasual','Arcade','Word','Board','Card','Trivia','Tabletop')
        THEN 'Hybrid-IAA'
      WHEN m.has_ads = true AND m.has_iap = true
        THEN 'Hybrid-IAP'
      ELSE 'Unknown'           -- has_ads / has_iap are NULL; fall back to genre in list logic
    END AS monetization_type,

    -- Moloco SDK/UA status (supply_demand_overlap)
    -- Note: supply_demand_overlap.vertical = Gaming/Consumer/Unknown — too coarse for routing.
    -- Use ST genre + monetization_type (above) for list classification instead.
    COALESCE(s.is_moloco_sdk_app,        false) AS is_moloco_sdk_app,
    COALESCE(s.is_moloco_advertiser_app, false) AS is_moloco_advertiser_app,
    COALESCE(s.is_iaa_app_any,           false) AS is_iaa_moloco,
    COALESCE(s.gross_spend_usd_30d,      0)     AS gross_spend_usd_30d,
    COALESCE(s.gross_spend_usd_iaa,      0)     AS gross_spend_usd_iaa,
    COALESCE(s.bid_requests,             0)     AS bid_requests,
    COALESCE(s.sdk_media_cost_usd,       0)     AS sdk_media_cost_usd,
    s.eligibility_status,
    s.ineligibility_reasons,
    s.success_threshold_status,
    s.mmp,
    s.pub_rank_30d,
    s.advertiser_name,

    -- 90-day UA spend (fact_dsp_core — authoritative)
    -- NULL = app has no campaign at all (strongest "no spend" signal)
    -- 0    = app has campaign records but zero spend in window
    ua.ua_spend_usd_90d,
    COALESCE(ua.ua_spend_usd_90d, 0) AS ua_spend_usd_90d_safe,

    -- Publisher exchange SDK signals (fact_dsp_publisher)
    COALESCE(p.pub_has_moloco_sdk,          false) AS pub_has_moloco_sdk,
    COALESCE(p.pub_via_applovin_max,        0)     AS pub_via_applovin_max,
    COALESCE(p.pub_via_admob,               0)     AS pub_via_admob,
    COALESCE(p.pub_via_levelplay,           0)     AS pub_via_levelplay,
    COALESCE(p.pub_via_inhouse,             0)     AS pub_via_inhouse,
    COALESCE(p.pub_on_applovin_exchange,    0)     AS pub_on_applovin_exchange,
    COALESCE(p.pub_on_unity_exchange,       0)     AS pub_on_unity_exchange,
    COALESCE(p.pub_on_ironsource_exchange,  0)     AS pub_on_ironsource_exchange,
    COALESCE(p.pub_on_vungle_exchange,      0)     AS pub_on_vungle_exchange,
    COALESCE(p.pub_on_inmobi_exchange,      0)     AS pub_on_inmobi_exchange,
    COALESCE(p.pub_other_exchange_count,    0)     AS pub_other_exchange_count,

    -- "Has other exchange SDK but NOT Moloco SDK"
    -- Primary: fact_dsp_publisher exchange signal
    -- Fallback: bid_requests > 0 (Moloco DSP can see app via other exchanges)
    -- Note: is_sdk_app_any is a Moloco SDK rollup flag — do NOT use here
    CASE
      WHEN COALESCE(p.pub_other_exchange_count, 0) > 0
       AND COALESCE(p.pub_has_moloco_sdk,        false) = false THEN true
      WHEN COALESCE(s.bid_requests,              0) > 0
       AND COALESCE(s.is_moloco_sdk_app,         false) = false THEN true
      ELSE false
    END AS has_other_exchange_sdk,

    -- Scale & growth (fact_app_v3)
    COALESCE(f.downloads_latest_month, 0) AS downloads_latest_month,
    COALESCE(f.downloads_90d,          0) AS downloads_90d,
    COALESCE(f.revenue_latest_month,   0) AS revenue_latest_month,
    COALESCE(f.paid_downloads_30d,     0) AS paid_downloads_30d,
    ROUND(SAFE_DIVIDE(
      CAST(COALESCE(f.downloads_90d, 0) - COALESCE(f.downloads_prior_90d, 0) AS FLOAT64),
      NULLIF(CAST(COALESCE(f.downloads_prior_90d, 0) AS FLOAT64), 0)
    ), 4) AS download_growth_rate,

    -- Demand-side competitor signals (network_analysis / ST)
    COALESCE(n.on_applovin,              0) AS on_applovin,
    COALESCE(n.on_unity,                 0) AS on_unity,
    COALESCE(n.on_ironsource,            0) AS on_ironsource,
    COALESCE(n.on_meta,                  0) AS on_meta,
    COALESCE(n.on_tiktok,                0) AS on_tiktok,
    COALESCE(n.on_pangle,                0) AS on_pangle,
    COALESCE(n.on_mintegral,             0) AS on_mintegral,
    COALESCE(n.on_google,                0) AS on_google,
    COALESCE(n.on_moloco_network,        0) AS on_moloco_network,
    COALESCE(n.competitor_network_count,  0) AS competitor_network_count,

    CASE
      WHEN COALESCE(n.on_google, 0) + COALESCE(n.on_meta, 0) >= 1
       AND COALESCE(n.competitor_network_count, 0) <= 2 THEN true
      ELSE false
    END AS only_google_meta

  FROM meta m
  LEFT JOIN sdl         s  ON m.app_market_bundle = s.app_bundle AND m.os = s.os
  LEFT JOIN ua_spend_90d ua ON m.app_market_bundle = ua.app_market_bundle
  LEFT JOIN tracking_pub tp ON m.app_market_bundle = tp.app_bundle
  LEFT JOIN pub_exchange  p  ON m.app_market_bundle = p.app_bundle
  LEFT JOIN fact_agg      f  ON m.app_market_bundle = f.app_market_bundle
  LEFT JOIN net_agg       n  ON m.st_app_id         = n.app_id
)

-- =============================================================================
-- FINAL OUTPUT
-- =============================================================================
SELECT

  -- List classification
  -- List 1: 90d spend check from fact_dsp_core (NULL = never had campaign = strongest signal)
  -- List 2/3: monetization_type (has_ads/has_iap) is primary; genre is fallback for Unknown
  CASE
    WHEN is_moloco_sdk_app = true
     AND COALESCE(ua_spend_usd_90d, 0) = 0
      THEN 'List1_SDK_NoSpend'

    WHEN COALESCE(ua_spend_usd_90d, 0) = 0
     AND downloads_90d >= 500000
     AND (
       -- Primary: has_ads/has_iap signals (definitive)
       monetization_type IN ('IAA', 'Hybrid-IAA')
       -- Fallback: monetization_type = Unknown (NULL fields), use genre
       OR (monetization_type = 'Unknown'
           AND (genre IN ('Casual','Puzzle','Hypercasual','Arcade','Word','Board','Card','Trivia','Tabletop')
                OR (is_gaming = false AND has_ads = true)
                OR is_iaa_moloco = true))
     )
      THEN 'List2_IAA_NoMoloco'

    WHEN COALESCE(ua_spend_usd_90d, 0) = 0
     AND downloads_90d >= 500000
     AND (
       -- Primary: has_ads/has_iap signals (definitive)
       monetization_type IN ('IAP', 'Hybrid-IAP')
       -- Fallback: monetization_type = Unknown, use genre
       OR (monetization_type = 'Unknown'
           AND genre IN ('Strategy','RPG','Action','Shooter','Sports','Racing','Simulation'))
     )
      THEN 'List3_IAP_NoMoloco'

    ELSE NULL
  END AS list_type,

  -- Prospect quality label
  CASE
    WHEN is_moloco_sdk_app = true AND COALESCE(ua_spend_usd_90d, 0) = 0
      THEN '🔴 SDK Integrated — Activate Now'
    WHEN has_other_exchange_sdk = true AND is_moloco_sdk_app = false
     AND pub_other_exchange_count > 0
      THEN '🟠 Exchange SDK (no Moloco) — SDK Pitch'
    WHEN has_other_exchange_sdk = true AND is_moloco_sdk_app = false
      THEN '🟠 Other SDK Signal — SDK Pitch'
    WHEN only_google_meta = true
      THEN '🟡 Google+Meta Only — Diversification Pitch'
    WHEN competitor_network_count >= 3 AND paid_downloads_30d > 0
      THEN '🟡 Heavy UA Spender — High Intent'
    WHEN competitor_network_count >= 1
      THEN '🟢 Active UA — Mid Intent'
    WHEN downloads_90d >= 1000000
      THEN '⚪ Large Organic — Educate First'
    ELSE '⚪ Early Stage'
  END AS prospect_label,

  -- Identity & entity resolution
  app_market_bundle,
  os,
  app_name,
  canonical_company,        -- COALESCE(tracking_publisher_name, st_parent_company)
  tracking_publisher_name,  -- GTM canonical; NULL if not in Moloco's supply history
  st_parent_company,
  company_name,
  publisher_name,
  hq_country,
  hq_region,
  china_confidence,
  website,

  -- Classification & routing
  team_routing,
  monetization_type,   -- IAA / IAP / Hybrid-IAA / Hybrid-IAP / Free / Unknown
  genre,
  subgenre,
  is_gaming,
  has_ads,
  has_iap,

  -- Moloco status
  is_moloco_sdk_app,
  is_moloco_advertiser_app,
  ua_spend_usd_90d,         -- NULL = never had campaign; 0 = campaign but no spend
  gross_spend_usd_30d,      -- from supply_demand_overlap (30d window)
  gross_spend_usd_iaa,
  sdk_media_cost_usd,
  bid_requests,
  eligibility_status,
  ineligibility_reasons,
  mmp,
  pub_rank_30d,
  advertiser_name,
  success_threshold_status,

  -- Publisher exchange SDK signals
  pub_has_moloco_sdk,
  pub_via_applovin_max,
  pub_via_admob,
  pub_via_levelplay,
  pub_via_inhouse,
  pub_on_applovin_exchange,
  pub_on_unity_exchange,
  pub_on_ironsource_exchange,
  pub_on_vungle_exchange,
  pub_on_inmobi_exchange,
  pub_other_exchange_count,
  has_other_exchange_sdk,

  -- Scale & growth
  downloads_latest_month,
  downloads_90d,
  revenue_latest_month,
  download_growth_rate,
  paid_downloads_30d,

  -- Demand-side competitor signals
  competitor_network_count,
  on_applovin,
  on_unity,
  on_ironsource,
  on_meta,
  on_tiktok,
  on_pangle,
  on_mintegral,
  on_google,
  on_moloco_network,
  only_google_meta

FROM base
WHERE
  CASE
    WHEN is_moloco_sdk_app = true
     AND COALESCE(ua_spend_usd_90d, 0) = 0 THEN true
    WHEN COALESCE(ua_spend_usd_90d, 0) = 0
     AND downloads_90d >= 500000
     AND (monetization_type IN ('IAA', 'Hybrid-IAA')
          OR (monetization_type = 'Unknown'
              AND (genre IN ('Casual','Puzzle','Hypercasual','Arcade','Word','Board','Card','Trivia','Tabletop')
                   OR (is_gaming = false AND has_ads = true) OR is_iaa_moloco = true))) THEN true
    WHEN COALESCE(ua_spend_usd_90d, 0) = 0
     AND downloads_90d >= 500000
     AND (monetization_type IN ('IAP', 'Hybrid-IAP')
          OR (monetization_type = 'Unknown'
              AND genre IN ('Strategy','RPG','Action','Shooter','Sports','Racing','Simulation'))) THEN true
    ELSE false
  END
  AND china_confidence IN ('High', 'Medium', 'Low-Review')

ORDER BY
  list_type ASC,
  competitor_network_count DESC,
  downloads_90d DESC,
  download_growth_rate DESC
;
