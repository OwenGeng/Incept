-- =============================================================================
-- List 3: Supply Partner — No SDK (List3_SupplyPartner_NoSDK)
-- =============================================================================
-- Definition: company is already a Moloco supply partner (is_supply_partner=true)
--             but this specific app has not integrated Moloco SDK (is_moloco_sdk_app=false)
--             and has no UA spend
-- =============================================================================
-- Comparison with other lists:
--   List 1: SDK=yes, UA=none        -> activate UA
--   List 2: SDK=yes, UA=partial     -> expand UA
--   List 3: company has Moloco relationship (other apps have SDK), this app does not -> SDK expansion
--   List 4/5/6: no prior Moloco relationship at all -> cold outreach
-- =============================================================================
-- Value: higher conversion than List 4/5/6 — company already trusts Moloco,
--        pitch is "bring this app into the SDK too"
-- Sources:
--   supply_demand_overlap  -> List 3 candidates + existing SDK app context
--   fact_dsp_core          -> exclude apps with UA spend
--   dim1_app_v3            -> ST metadata (genre, monetization_type, download signals)
--   hq_country_triage      -> GTM-verified HQ country
--   network_analysis       -> competitor UA networks (via st_app_id)
--   download_revenue_v3    -> 30d top download / revenue country
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- CTE 1: List 3 candidate apps
-- Condition: company has a supply relationship (is_supply_partner=true)
--            but this app has no SDK (is_moloco_sdk_app=false)
-- ---------------------------------------------------------------------------
candidate_apps AS (
  SELECT
    app_bundle,
    os,
    MAX(app_name)                                               AS app_name,
    MAX(publisher_name)                                         AS publisher_name,
    MAX(company_hq_country)                                     AS sdl_hq_country,
    MAX(company_hq_region)                                      AS sdl_hq_region,
    MAX(eligibility_status)                                     AS eligibility_status,
    MAX(ineligibility_reasons)                                  AS ineligibility_reasons,
    MAX(mmp)                                                    AS mmp,
    STRING_AGG(DISTINCT sdk_growth_manager, ', ')               AS sdk_growth_managers,
    STRING_AGG(DISTINCT ads_growth_manager, ', ')               AS ads_growth_managers,
    STRING_AGG(DISTINCT office, ', ')                           AS moloco_offices
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  WHERE is_supply_partner  = true
    AND is_moloco_sdk_app  = false
    AND app_bundle IS NOT NULL
  GROUP BY app_bundle, os
),

-- ---------------------------------------------------------------------------
-- CTE 2: Existing SDK app context per company (publisher_name as join key)
--         Gives sales reps context on how deep the existing relationship is
-- ---------------------------------------------------------------------------
company_sdk_context AS (
  SELECT
    publisher_name,
    COUNT(DISTINCT app_bundle)                                                         AS existing_sdk_app_count,
    SUM(sdk_media_cost_usd)                                                            AS existing_sdk_media_cost_30d,
    SUM(gross_spend_usd)                                                               AS existing_ua_spend_30d,
    STRING_AGG(DISTINCT CASE WHEN is_moloco_advertiser_app THEN app_name END, ', ')    AS existing_ua_apps,
    STRING_AGG(DISTINCT mmp, ', ')                                                     AS existing_mmps
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  WHERE is_moloco_sdk_app = true
    AND publisher_name IS NOT NULL
  GROUP BY publisher_name
),

-- ---------------------------------------------------------------------------
-- CTE 3: Apps with UA spend in past 90 days (used for exclusion)
-- ---------------------------------------------------------------------------
ua_spend AS (
  SELECT
    product.app_market_bundle AS bundle_id,
    SUM(gross_spend_usd)      AS spend_90d
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND gross_spend_usd > 0
    AND product.app_market_bundle IS NOT NULL
  GROUP BY 1
),

-- ---------------------------------------------------------------------------
-- CTE 4: ST app metadata + monetization_type
-- ---------------------------------------------------------------------------
meta AS (
  SELECT
    app_market_bundle,
    os,
    sensortower.product.app_id      AS st_app_id,
    sensortower.product.has_ads     AS has_ads,
    sensortower.product.has_iap     AS has_iap,
    sensortower.company.name        AS company_name_st,
    sensortower.company.hq_country  AS hq_country,
    sensortower.company.hq_region   AS hq_region,
    sensortower.company.parent.name AS parent_company,
    sensortower.publisher.website   AS website,
    sensortower.class.is_gaming     AS is_gaming,
    sensortower.class.genre         AS genre,
    CASE
      WHEN sensortower.class.is_gaming = true THEN
        CASE
          WHEN sensortower.product.has_iap = false AND sensortower.product.has_ads = true  THEN 'IAA'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = true  THEN 'IAP'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = false THEN 'Free'
          WHEN sensortower.product.has_ads = true  AND sensortower.product.has_iap = true
           AND sensortower.class.genre IN (
             'Casual','Hypercasual','Puzzle','Brain & Puzzle',
             'Arcade','Arcade & Action','Word','Board','Tabletop','Trivia',
             'Match','Party','Adventure','Cards & Casino','Casino',
             'Kids','Kids & Family','Education'
           ) THEN 'Hybrid-IAA'
          WHEN sensortower.product.has_ads = true  AND sensortower.product.has_iap = true THEN 'Hybrid-IAP'
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
),

-- ---------------------------------------------------------------------------
-- CTE 5: GTM-verified HQ country overrides
-- ---------------------------------------------------------------------------
gtm_hq AS (
  SELECT company_name, final_hq_country
  FROM `ads-bpd-guard-sandbox.yingzi_uploads.hq_country_triage`
  WHERE final_hq_country IS NOT NULL
),

-- ---------------------------------------------------------------------------
-- CTE 6: Competitor UA network signals (via st_app_id)
-- ---------------------------------------------------------------------------
net_signals AS (
  SELECT
    app_id,
    STRING_AGG(DISTINCT network ORDER BY network)    AS active_ua_networks,
    COUNTIF(LOWER(network) NOT LIKE '%moloco%')      AS competitor_network_count
  FROM `ads-bpd-guard-china.sensortower.network_analysis`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  GROUP BY app_id
),

-- ---------------------------------------------------------------------------
-- CTE 7: Open-exchange bid request breakdown by exchange
-- These apps have no Moloco SDK but Moloco DSP can reach them via open exchange.
-- Exchange examples: ADX_RTB, INMOBI, APPODEAL, APPLOVIN, etc.
-- ---------------------------------------------------------------------------
bid_exchange_raw AS (
  SELECT
    req.app_bundle             AS bundle_id,
    exchange,
    SUM(bid_requests)          AS exchange_bid_requests
  FROM `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND req.app_bundle IS NOT NULL
    AND bid_requests > 0
  GROUP BY req.app_bundle, exchange
),
bid_exchange_breakdown AS (
  SELECT
    bundle_id,
    SUM(exchange_bid_requests)                           AS total_bid_requests_90d,
    STRING_AGG(exchange, ', ' ORDER BY exchange_bid_requests DESC) AS bid_exchanges_by_volume
  FROM bid_exchange_raw
  GROUP BY bundle_id
),

-- ---------------------------------------------------------------------------
-- CTE 8: ST download / revenue by country (30d top download / revenue country)
-- ---------------------------------------------------------------------------
geo_raw AS (
  SELECT
    app_id, country_code,
    SUM(download) AS dl_30d,
    SUM(revenue)  AS rev_30d
  FROM `ads-bpd-guard-china.sensortower.download_revenue_v3`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND app_id IS NOT NULL
  GROUP BY app_id, country_code
),
geo_metrics AS (
  SELECT
    app_id,
    MAX(CASE WHEN dl_rank  = 1 THEN country_code END)  AS top_dl_country,
    MAX(CASE WHEN dl_rank  = 1 THEN dl_30d END)         AS top_dl_country_downloads,
    MAX(CASE WHEN rev_rank = 1 THEN country_code END)  AS top_rev_country,
    SUM(dl_30d)                                         AS total_downloads_30d
  FROM (
    SELECT *,
      ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY dl_30d  DESC) AS dl_rank,
      ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY rev_30d DESC) AS rev_rank
    FROM geo_raw
  )
  GROUP BY app_id
)

-- =============================================================================
-- Final output: app-level detail
-- =============================================================================
SELECT
  'List3_SupplyPartner_NoSDK'                                          AS list_type,
  c.app_bundle,
  c.os,
  COALESCE(m.company_name_st, c.publisher_name)                       AS company_name,
  c.publisher_name                                                     AS sdl_publisher_name,
  COALESCE(m.is_gaming, false)                                         AS is_gaming,
  CASE WHEN COALESCE(m.is_gaming, false)
       THEN 'Gaming' ELSE 'Non-Gaming' END                            AS team_routing,
  m.genre,
  m.monetization_type,
  m.website,
  m.hq_country                                                        AS sensortower_hq_country,
  COALESCE(gtm.final_hq_country, m.hq_country)                        AS final_hq_country,
  CASE WHEN gtm.final_hq_country IS NOT NULL
       THEN 'GTM_triage' ELSE 'ST_original' END                       AS hq_country_source,
  ctx.existing_sdk_app_count,
  ctx.existing_sdk_media_cost_30d,
  ctx.existing_ua_spend_30d,
  ctx.existing_ua_apps,
  ctx.existing_mmps,
  b.total_bid_requests_90d,
  b.bid_exchanges_by_volume,
  c.eligibility_status,
  c.ineligibility_reasons,
  c.mmp,
  c.sdk_growth_managers,
  c.ads_growth_managers,
  c.moloco_offices,
  COALESCE(n.active_ua_networks, 'No Active Networks')                AS active_ua_networks,
  COALESCE(n.competitor_network_count, 0)                             AS competitor_network_count,
  g.top_dl_country,
  g.top_dl_country_downloads,
  g.top_rev_country,
  g.total_downloads_30d,
  CURRENT_DATE()                                                       AS data_as_of

FROM candidate_apps c
LEFT JOIN ua_spend              ua  ON c.app_bundle = ua.bundle_id
LEFT JOIN meta                  m   ON c.app_bundle = m.app_market_bundle AND c.os = m.os
LEFT JOIN gtm_hq                gtm ON m.company_name_st = gtm.company_name
LEFT JOIN company_sdk_context   ctx ON c.publisher_name = ctx.publisher_name
LEFT JOIN net_signals            n   ON m.st_app_id = n.app_id
LEFT JOIN geo_metrics            g   ON m.st_app_id = g.app_id
LEFT JOIN bid_exchange_breakdown b   ON c.app_bundle = b.bundle_id

WHERE COALESCE(ua.spend_90d, 0) = 0
  AND UPPER(COALESCE(gtm.final_hq_country, m.hq_country, c.sdl_hq_country))
      IN ('CHN', 'HKG', 'TWN', 'MAC', 'SGP')

ORDER BY
  ctx.existing_sdk_media_cost_30d DESC,
  COALESCE(b.total_bid_requests_90d, 0) DESC,
  COALESCE(n.competitor_network_count, 0) DESC,
  g.total_downloads_30d DESC;

-- =============================================================================
-- Company-level rollup (uncomment to replace the SELECT above)
-- =============================================================================
/*
SELECT
  'List3_SupplyPartner_NoSDK'                                   AS list_type,
  COALESCE(m.company_name_st, c.publisher_name)                 AS company_name,
  MAX(COALESCE(gtm.final_hq_country, m.hq_country))             AS final_hq_country,
  MAX(CASE WHEN COALESCE(m.is_gaming, false)
      THEN 'Gaming' ELSE 'Non-Gaming' END)                      AS team_routing,
  COUNT(DISTINCT c.app_bundle)                                   AS untapped_apps_count,
  MAX(ctx.existing_sdk_app_count)                                AS existing_sdk_apps,
  MAX(ctx.existing_sdk_media_cost_30d)                           AS existing_sdk_media_cost_30d,
  MAX(ctx.existing_ua_spend_30d)                                 AS existing_ua_spend_30d,
  MAX(ctx.existing_ua_apps)                                      AS existing_ua_apps,
  MAX(ctx.existing_mmps)                                         AS existing_mmps,
  STRING_AGG(DISTINCT m.monetization_type, ', ')                 AS monetization_types,
  SUM(g.total_downloads_30d)                                     AS total_downloads_30d,
  CURRENT_DATE()                                                 AS data_as_of
FROM candidate_apps c
LEFT JOIN ua_spend            ua  ON c.app_bundle = ua.bundle_id
LEFT JOIN meta                m   ON c.app_bundle = m.app_market_bundle AND c.os = m.os
LEFT JOIN gtm_hq              gtm ON m.company_name_st = gtm.company_name
LEFT JOIN company_sdk_context ctx ON c.publisher_name = ctx.publisher_name
LEFT JOIN geo_metrics          g   ON m.st_app_id = g.app_id
WHERE COALESCE(ua.spend_90d, 0) = 0
  AND UPPER(COALESCE(gtm.final_hq_country, m.hq_country, c.sdl_hq_country))
      IN ('CHN', 'HKG', 'TWN', 'MAC', 'SGP')
GROUP BY COALESCE(m.company_name_st, c.publisher_name)
ORDER BY existing_sdk_media_cost_30d DESC, total_downloads_30d DESC;
*/
