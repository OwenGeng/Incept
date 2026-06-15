-- =============================================================================
-- List 1: Cold Prospect — Company-level view
-- Definition: companies where ALL SDK apps have zero Moloco UA spend
--             and no app is a Moloco advertiser
-- Output: one row per company
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- CTE 1: SDK app inventory
-- ---------------------------------------------------------------------------
sdk_bundles AS (
  SELECT
    req.app_bundle                                             AS bundle_id,
    MAX(req.app_name)                                          AS app_name,
    MAX(req.app_company_name)                                  AS company_name_supply,
    MAX(req.os)                                                AS os,
    MAX(CASE WHEN req.app_is_gaming THEN 'Yes' ELSE 'No' END)  AS is_gaming_supply,
    MAX(req.app_genre)                                         AS genre_supply,
    MAX(tracking_publisher_name)                               AS tracking_publisher_name
  FROM `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND exchange LIKE 'MOLOCO_SDK%'
    AND req.app_bundle IS NOT NULL
  GROUP BY 1
),

-- ---------------------------------------------------------------------------
-- CTE 2: Apps with active UA spend in the past 90 days
-- ---------------------------------------------------------------------------
active_ua AS (
  SELECT
    product.app_market_bundle  AS bundle_id,
    SUM(gross_spend_usd)       AS gross_spend_usd_90d
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND gross_spend_usd > 0
    AND product.app_market_bundle IS NOT NULL
  GROUP BY 1
),

-- ---------------------------------------------------------------------------
-- CTE 3: supply_demand_overlap
-- ---------------------------------------------------------------------------
sdl AS (
  SELECT
    app_bundle,
    MAX(is_moloco_sdk_app)              AS is_moloco_sdk_app,
    MAX(is_moloco_advertiser_app)       AS is_moloco_advertiser_app,
    MAX(sdk_media_cost_usd)             AS sdk_media_cost_usd,
    MAX(pub_rank_30d)                   AS pub_rank_30d,
    MAX(sdk_media_cost_rank)            AS sdk_media_cost_rank,
    STRING_AGG(DISTINCT sdk_growth_manager, ', ')  AS sdl_sdk_growth_managers,
    MAX(eligibility_status)             AS eligibility_status,
    STRING_AGG(DISTINCT mmp, ', ')      AS mmp
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  GROUP BY app_bundle
),

-- ---------------------------------------------------------------------------
-- CTE 4: ST app metadata
-- ---------------------------------------------------------------------------
meta AS (
  SELECT
    app_market_bundle,
    os,
    sensortower.product.app_id       AS st_app_id,
    sensortower.product.has_ads      AS has_ads,
    sensortower.product.has_iap      AS has_iap,
    sensortower.company.name         AS company_name_st,
    sensortower.company.hq_country   AS hq_country,
    sensortower.company.parent.name  AS parent_company,
    sensortower.publisher.website    AS website,
    sensortower.class.is_gaming      AS is_gaming,
    sensortower.class.genre          AS genre,
    CASE
      WHEN sensortower.class.is_gaming = true THEN
        CASE
          WHEN sensortower.product.has_iap = false AND sensortower.product.has_ads = true  THEN 'IAA'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = true  THEN 'IAP'
          WHEN sensortower.product.has_ads = false AND sensortower.product.has_iap = false THEN 'Free'
          WHEN sensortower.product.has_ads = true  AND sensortower.product.has_iap = true
           AND sensortower.class.genre IN (
             'Casual','Hypercasual','Puzzle','Brain & Puzzle','Arcade','Arcade & Action',
             'Word','Board','Tabletop','Trivia','Match','Party','Adventure','Cards & Casino',
             'Casino','Kids','Kids & Family','Education'
           ) THEN 'Hybrid-IAA'
          WHEN sensortower.product.has_ads = true  AND sensortower.product.has_iap = true THEN 'Hybrid-IAP'
          ELSE 'Unknown'
        END
      WHEN sensortower.class.is_gaming = false THEN
        CASE
          WHEN sensortower.product.has_ads = true  THEN 'IAA'
          WHEN sensortower.product.has_iap = true  THEN 'IAP'
          ELSE                                          'Free'
        END
      ELSE 'Unknown'
    END AS monetization_type
  FROM `ads-bpd-guard-china.athena.dim1_app_v3`
),

-- ---------------------------------------------------------------------------
-- CTE 5: GTM-verified HQ country overrides
-- ---------------------------------------------------------------------------
gtm_hq AS (
  SELECT
    company_name,
    final_hq_country
  FROM `ads-bpd-guard-sandbox.yingzi_uploads.hq_country_triage`
  WHERE final_hq_country IS NOT NULL
),

-- ---------------------------------------------------------------------------
-- CTE 6: App-level join
-- ---------------------------------------------------------------------------
tagged AS (
  SELECT
    s.bundle_id,
    COALESCE(
      NULLIF(TRIM(s.tracking_publisher_name), ''),
      NULLIF(TRIM(m.parent_company), ''),
      NULLIF(TRIM(m.company_name_st), ''),
      NULLIF(TRIM(s.company_name_supply), ''),
      'Unknown'
    )                                                   AS canonical_company,
    s.tracking_publisher_name,
    COALESCE(gtm.final_hq_country, m.hq_country)        AS final_hq_country,
    m.website,
    CASE WHEN COALESCE(m.is_gaming, s.is_gaming_supply = 'Yes')
         THEN 'Gaming' ELSE 'Non-Gaming'
    END                                                 AS team_routing,
    COALESCE(m.genre, s.genre_supply)                   AS genre,
    CASE
      WHEN COALESCE(d.sdk_media_cost_usd, 0) > 1 AND m.monetization_type = 'IAP' THEN 'Hybrid-IAP'
      ELSE m.monetization_type
    END                                                 AS monetization_type,
    a.bundle_id IS NOT NULL                             AS is_buying_ua,
    COALESCE(d.is_moloco_advertiser_app, false)         AS is_moloco_advertiser_app,
    COALESCE(d.sdk_media_cost_usd,       0)             AS sdk_media_cost_usd_30d,
    d.eligibility_status,
    d.mmp,
    d.sdl_sdk_growth_managers

  FROM sdk_bundles s
  LEFT JOIN meta    m   ON s.bundle_id = m.app_market_bundle AND s.os = m.os
  LEFT JOIN gtm_hq  gtm ON m.company_name_st = gtm.company_name
  LEFT JOIN active_ua a ON s.bundle_id = a.bundle_id
  LEFT JOIN sdl     d   ON s.bundle_id = d.app_bundle
),

-- ---------------------------------------------------------------------------
-- CTE 7: Company-level rollup
-- ---------------------------------------------------------------------------
company_level AS (
  SELECT
    canonical_company                                             AS company_name,
    MAX(final_hq_country)                                        AS final_hq_country,
    MAX(team_routing)                                            AS team_routing,
    MAX(website)                                                 AS website,
    MAX(tracking_publisher_name)                                 AS tracking_publisher_name,
    STRING_AGG(DISTINCT monetization_type, ', ')                 AS monetization_types,
    COUNT(DISTINCT bundle_id)                                    AS total_sdk_apps,
    COUNT(DISTINCT CASE WHEN NOT is_buying_ua THEN bundle_id END) AS untapped_apps,
    SUM(sdk_media_cost_usd_30d)                                  AS total_sdk_media_cost_usd_30d,
    STRING_AGG(DISTINCT eligibility_status, ', ')                AS eligibility_statuses,
    STRING_AGG(DISTINCT mmp, ', ')                               AS mmps,
    MAX(sdl_sdk_growth_managers)                                 AS sdk_growth_managers
  FROM tagged
  WHERE canonical_company != 'Unknown'
    AND UPPER(final_hq_country) IN ('CHN', 'HKG', 'TWN', 'MAC', 'SGP')
  GROUP BY canonical_company
  HAVING COUNT(DISTINCT CASE WHEN is_buying_ua THEN bundle_id END) = 0
    AND MAX(CASE WHEN is_moloco_advertiser_app THEN 1 ELSE 0 END) = 0
)

-- =============================================================================
-- Final output: one row per company
-- =============================================================================
SELECT
  'List 1 New'                AS list_type,
  company_name,
  final_hq_country,
  team_routing,
  website,
  tracking_publisher_name,
  total_sdk_apps,
  untapped_apps,
  total_sdk_media_cost_usd_30d,
  monetization_types,
  eligibility_statuses,
  mmps,
  sdk_growth_managers,
  CURRENT_DATE()              AS data_as_of
FROM company_level
ORDER BY total_sdk_media_cost_usd_30d DESC;
