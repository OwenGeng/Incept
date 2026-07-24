-- =============================================================================
-- Prospect Engine — List 1 (COLD_PROSPECT) & List 4 (EXPANSION)
-- =============================================================================
-- 数据来源：
--   fact_supply_with_tracking_publisher  → SDK signal + canonical publisher name + impression geo
--                                          （替代 fact_supply，更完整，包含 tracking_publisher_name）
--   fact_dsp_core                        → 90d UA spend（gross_spend_usd，非 pb_revenue_usd）
--   supply_demand_overlap                → Moloco 状态 flag + eligibility + SDK cost + MMP
--                                          （GROUP BY app_bundle 去重，跨 office MAX/STRING_AGG）
--   dim1_app_v3                          → ST metadata + monetization_type
--   sensortower.network_analysis         → 竞品 UA 网络，输出 active_ua_networks 字符串（via st_app_id）
--   sensortower.download_revenue_v3      → 30d top DL/revenue 国家（via st_app_id）
-- =============================================================================
-- List 1 (COLD_PROSPECT)：公司下所有 SDK app 均无 UA
--   moloco_offices / gms / account_age_groups 为空 → 正常，无 advertiser 关系
--   sdk_growth_managers 有值 → SDK 侧关系人（与 UA 侧无关）
-- List 4 (EXPANSION)：公司下有部分 app 有 UA，但仍有未激活 app
--   moloco_offices / gms 有值 → 反映现有 Moloco 关系
-- =============================================================================
-- 输出两个 Query（切换 final SELECT）：
--   TAB 2：公司汇总（company_level SELECT，默认）
--   TAB 3：App 明细（注释块，取消注释替换 TAB 2）
-- =============================================================================

WITH

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 1: SDK app 列表 + canonical publisher name
-- ─────────────────────────────────────────────────────────────────────────────
sdk_bundles AS (
  SELECT
    req.app_bundle                                            AS bundle_id,
    MAX(req.app_name)                                         AS app_name,
    MAX(req.app_company_name)                                 AS company_name_supply,
    MAX(req.os)                                               AS os,
    MAX(CASE WHEN req.app_is_gaming THEN 'Yes' ELSE 'No' END) AS is_gaming_supply,
    MAX(req.app_genre)                                        AS genre_supply,
    MAX(tracking_publisher_name)                              AS tracking_publisher_name
  FROM `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND exchange LIKE 'MOLOCO_SDK%'
    AND req.app_bundle IS NOT NULL
  GROUP BY 1
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 2: 过去 90 天有 UA spend 的 app
-- ─────────────────────────────────────────────────────────────────────────────
active_ua AS (
  SELECT
    product.app_market_bundle                               AS bundle_id,
    STRING_AGG(DISTINCT advertiser.office, ', ')            AS advertiser_offices,
    STRING_AGG(DISTINCT advertiser.account_age_group, ', ') AS account_age_groups,
    STRING_AGG(DISTINCT advertiser.gm, ', ')                AS gms,
    SUM(gross_spend_usd)                                    AS gross_spend_usd_90d
  FROM `ads-bpd-guard-china.athena.fact_dsp_core`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND gross_spend_usd > 0
    AND product.app_market_bundle IS NOT NULL
  GROUP BY 1
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 3: supply_demand_overlap
-- ─────────────────────────────────────────────────────────────────────────────
sdl AS (
  SELECT
    app_bundle,
    MAX(is_moloco_sdk_app)              AS is_moloco_sdk_app,
    MAX(is_moloco_advertiser_app)       AS is_moloco_advertiser_app,
    MAX(vertical)                       AS vertical,
    MAX(bid_requests)                  AS bid_requests,
    MAX(sdk_media_cost_usd)            AS sdk_media_cost_usd,
    MAX(pub_rank_30d)                  AS pub_rank_30d,
    MAX(sdk_media_cost_rank)           AS sdk_media_cost_rank,
    STRING_AGG(DISTINCT office, ', ')                                             AS sdl_offices,
    STRING_AGG(DISTINCT ads_growth_manager, ', ')                                 AS sdl_ads_growth_managers,
    STRING_AGG(DISTINCT ads_growth_pod, ', ')                                     AS sdl_ads_growth_pods,
    STRING_AGG(DISTINCT sdk_growth_manager, ', ')                                 AS sdl_sdk_growth_managers,
    STRING_AGG(DISTINCT CASE WHEN advertiser_name != 'Not Moloco Advertiser' 
                             THEN advertiser_name END, ', ')                      AS sdl_advertiser_names,
    MAX(mmp)                           AS mmp,
    STRING_AGG(DISTINCT mmp_event_names, ' | ')                                   AS mmp_event_names,
    MAX(eligibility_status)            AS eligibility_status,
    MAX(ineligibility_reasons)         AS ineligibility_reasons,
    MAX(eligibility_evaluation_date)   AS eligibility_evaluation_date,
  FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
  GROUP BY app_bundle
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 4: App metadata from Sensor Tower
-- ─────────────────────────────────────────────────────────────────────────────
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
             'Casual','Hypercasual','Puzzle','Brain & Puzzle','Arcade','Arcade & Action',
             'Word','Board','Tabletop','Trivia','Match','Party','Adventure','Cards & Casino','Casino','Kids','Kids & Family','Education'
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

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 5: 竞品网络信号
-- ─────────────────────────────────────────────────────────────────────────────
net_signals AS (
  SELECT
    app_id,
    STRING_AGG(DISTINCT network ORDER BY network)              AS active_ua_networks,
    MAX(CASE WHEN LOWER(network) LIKE '%applovin%' OR LOWER(network) LIKE '%max%' THEN 1 ELSE 0 END) AS on_applovin,
    MAX(CASE WHEN LOWER(network) LIKE '%unity%'      THEN 1 ELSE 0 END) AS on_unity,
    MAX(CASE WHEN LOWER(network) LIKE '%ironsource%' THEN 1 ELSE 0 END) AS on_ironsource,
    MAX(CASE WHEN LOWER(network) LIKE '%facebook%' OR LOWER(network) LIKE '%meta%' THEN 1 ELSE 0 END) AS on_meta,
    MAX(CASE WHEN LOWER(network) LIKE '%tiktok%'     THEN 1 ELSE 0 END) AS on_tiktok,
    MAX(CASE WHEN LOWER(network) LIKE '%pangle%'     THEN 1 ELSE 0 END) AS on_pangle,
    MAX(CASE WHEN LOWER(network) LIKE '%mintegral%'  THEN 1 ELSE 0 END) AS on_mintegral,
    MAX(CASE WHEN LOWER(network) LIKE '%google%' OR LOWER(network) LIKE '%uac%' THEN 1 ELSE 0 END) AS on_google,
    COUNTIF(LOWER(network) NOT LIKE '%moloco%')                AS competitor_network_count
  FROM `ads-bpd-guard-china.sensortower.network_analysis`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  GROUP BY app_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 6: ST download_revenue_v3
-- ─────────────────────────────────────────────────────────────────────────────
geo_raw AS (
  SELECT
    app_id,
    country_code,
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
    SUM(dl_30d)                                               AS total_downloads_30d,
    SUM(rev_30d)                                              AS total_revenue_30d,
    MAX(CASE WHEN dl_rank  = 1 THEN country_code END)        AS top_dl_country,
    MAX(CASE WHEN dl_rank  = 1 THEN dl_30d END)              AS top_dl_country_downloads,
    MAX(CASE WHEN rev_rank = 1 THEN country_code END)        AS top_rev_country,
    MAX(CASE WHEN rev_rank = 1 THEN rev_30d END)             AS top_rev_country_revenue
  FROM (
    SELECT *,
      ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY dl_30d  DESC) AS dl_rank,
      ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY rev_30d DESC) AS rev_rank
    FROM geo_raw
  )
  GROUP BY app_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 7: Moloco SDK impression 最多的国家
-- ─────────────────────────────────────────────────────────────────────────────
supply_imp_by_country AS (
  SELECT
    req.app_bundle   AS bundle_id,
    req.country      AS country_code,
    SUM(impressions) AS imp_30d
  FROM `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`
  WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND exchange LIKE 'MOLOCO_SDK%'
    AND req.app_bundle IS NOT NULL
  GROUP BY req.app_bundle, req.country
),
supply_top_country AS (
  SELECT
    bundle_id,
    MAX(CASE WHEN rank = 1 THEN country_code END) AS top_sdk_impression_country
  FROM (
    SELECT *,
      ROW_NUMBER() OVER (PARTITION BY bundle_id ORDER BY imp_30d DESC) AS rank
    FROM supply_imp_by_country
  )
  GROUP BY bundle_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 8: GTM 人工验证的公司 HQ 国家映射表
-- ─────────────────────────────────────────────────────────────────────────────
gtm_hq AS (
  SELECT
    company_name,
    final_hq_country,
    is_manually_corrected
  FROM `ads-bpd-guard-sandbox.yingzi_uploads.hq_country_triage`
  WHERE final_hq_country IS NOT NULL
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 9: 汇总（app 粒度）
-- ─────────────────────────────────────────────────────────────────────────────
tagged AS (
  SELECT
    s.bundle_id,
    s.app_name,
    s.os,
    COALESCE(
      NULLIF(TRIM(m.company_name_st), ''),
      NULLIF(TRIM(s.company_name_supply), ''),
      'Unknown'
    )                                                 AS canonical_company,
    s.tracking_publisher_name,
    m.parent_company,
    m.hq_country                                      AS sensortower_hq_country, 
    COALESCE(gtm.final_hq_country, m.hq_country)      AS final_hq_country,
    CASE
      WHEN gtm.final_hq_country IS NOT NULL THEN 'GTM_triage'
      ELSE 'ST_original'
    END                                               AS hq_country_source,
    COALESCE(gtm.is_manually_corrected, false)        AS is_manually_corrected, 
    m.hq_region,
    m.website,
    COALESCE(m.is_gaming, s.is_gaming_supply = 'Yes') AS is_gaming,
    CASE WHEN COALESCE(m.is_gaming, s.is_gaming_supply = 'Yes')
         THEN 'Gaming' ELSE 'Non-Gaming'
    END                                               AS team_routing,
    COALESCE(m.genre, s.genre_supply)                 AS genre,
    m.monetization_type,

    -- UA 状态
    a.bundle_id IS NOT NULL                           AS is_buying_ua,
    a.advertiser_offices,
    a.account_age_groups,
    a.gms,
    COALESCE(a.gross_spend_usd_90d, 0)                AS gross_spend_usd_90d,

    -- supply_demand_overlap
    COALESCE(d.is_moloco_sdk_app,       false)        AS is_moloco_sdk_app,       
    COALESCE(d.is_moloco_advertiser_app, false)       AS is_moloco_advertiser_app, 
    d.vertical,
    COALESCE(d.bid_requests,      0)                  AS bid_requests,
    COALESCE(d.sdk_media_cost_usd,0)                  AS sdk_media_cost_usd_30d,
    d.pub_rank_30d,
    d.sdk_media_cost_rank,
    d.sdl_offices,
    d.sdl_ads_growth_managers,
    d.sdl_ads_growth_pods,
    d.sdl_sdk_growth_managers,
    d.sdl_advertiser_names,
    d.mmp,
    d.mmp_event_names,
    d.eligibility_status,
    d.ineligibility_reasons,
    d.eligibility_evaluation_date,

    -- 竞品网络
    n.active_ua_networks,
    COALESCE(n.competitor_network_count, 0)           AS competitor_network_count,
    COALESCE(n.on_applovin,  0)                       AS on_applovin,
    COALESCE(n.on_unity,     0)                       AS on_unity,
    COALESCE(n.on_ironsource,0)                       AS on_ironsource,
    COALESCE(n.on_meta,      0)                       AS on_meta,
    COALESCE(n.on_tiktok,    0)                       AS on_tiktok,
    COALESCE(n.on_pangle,    0)                       AS on_pangle,
    COALESCE(n.on_mintegral, 0)                       AS on_mintegral,
    COALESCE(n.on_google,    0)                       AS on_google,

    -- ST 地理
    g.total_downloads_30d,
    g.total_revenue_30d,
    g.top_dl_country,
    g.top_dl_country_downloads,
    g.top_rev_country,
    g.top_rev_country_revenue,
    stc.top_sdk_impression_country

  FROM sdk_bundles s
  LEFT JOIN meta               m   ON s.bundle_id = m.app_market_bundle AND s.os = m.os
  LEFT JOIN gtm_hq             gtm ON m.company_name_st = gtm.company_name  
  LEFT JOIN active_ua          a   ON s.bundle_id = a.bundle_id
  LEFT JOIN sdl                d   ON s.bundle_id = d.app_bundle
  LEFT JOIN net_signals        n   ON m.st_app_id  = n.app_id
  LEFT JOIN geo_metrics        g   ON m.st_app_id  = g.app_id
  LEFT JOIN supply_top_country stc ON s.bundle_id  = stc.bundle_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 10: 公司层汇总
-- ─────────────────────────────────────────────────────────────────────────────
company_level AS (
  SELECT
    canonical_company,
    CASE
      WHEN COUNT(DISTINCT CASE WHEN is_buying_ua THEN bundle_id END) = 0 THEN 'List1_COLD_PROSPECT'
      ELSE 'List2_EXPANSION'
    END                                                                 AS list_type,
    MAX(sensortower_hq_country)                                         AS sensortower_hq_country,
    MAX(final_hq_country)                                               AS final_hq_country,
    MAX(hq_country_source)                                              AS hq_country_source,
    MAX(is_manually_corrected)                                          AS is_manually_corrected,
    MAX(hq_region)                                                      AS hq_region,
    MAX(team_routing)                                                   AS team_routing,
    MAX(website)                                                        AS website,
    MAX(tracking_publisher_name)                                        AS tracking_publisher_name,
    STRING_AGG(DISTINCT monetization_type, ', ')                        AS monetization_types,
    COUNT(DISTINCT bundle_id)                                           AS total_sdk_apps,
    COUNT(DISTINCT CASE WHEN is_buying_ua     THEN bundle_id END)       AS buying_ua_apps,
    COUNT(DISTINCT CASE WHEN NOT is_buying_ua THEN bundle_id END)       AS untapped_apps,
    SUM(sdk_media_cost_usd_30d)                                         AS total_sdk_media_cost_usd_30d,
    SUM(bid_requests)                                                   AS total_bid_requests,
    STRING_AGG(DISTINCT eligibility_status, ', ')                       AS eligibility_statuses,
    STRING_AGG(DISTINCT mmp, ', ')                                      AS mmps,
    MAX(sdl_sdk_growth_managers)                                        AS sdk_growth_managers,
    MAX(CASE WHEN is_buying_ua THEN advertiser_offices END)             AS moloco_offices,
    MAX(CASE WHEN is_buying_ua THEN gms END)                            AS moloco_gms,
    MAX(CASE WHEN is_buying_ua THEN account_age_groups END)             AS account_age_groups,
    SUM(CASE WHEN is_buying_ua THEN gross_spend_usd_90d ELSE 0 END)     AS existing_spend_usd_90d
  FROM tagged
  WHERE canonical_company != 'Unknown'
    -- 【🛑 核心修复：重构大盘过滤漏斗】
    AND (
      -- 规则 1：只要清洗后的国家明确落在出海白名单里，放行（包含正常的 gtm 覆盖、以及 ST 本身就准的）
      UPPER(final_hq_country) IN ('CN','CHN','CHINA','HK','HKG','TW','TWN','SG','SGP')
      
      -- 规则 2：只有当 ST 原始和 GTM 人工都是空时（双空 Unknown），允许放行 Review
      OR (
        (final_hq_country IS NULL OR TRIM(final_hq_country) = '')
        AND (sensortower_hq_country IS NULL OR TRIM(sensortower_hq_country) = '')
      )
      -- 💡 这样改之后，Codedish 因为 ST 原始值是明确的 'DEU'，不满足规则1，也不满足规则2的双空条件，会在这里直接被秒杀剔除！
    )
  GROUP BY canonical_company
)

-- =============================================================================
-- 最终 APP 明细输出
-- =============================================================================
SELECT
  cl.list_type,
  cl.team_routing,
  t.canonical_company,
  t.tracking_publisher_name,
  t.sensortower_hq_country,
  t.final_hq_country,
  t.is_manually_corrected,
  t.hq_region,
  t.bundle_id,
  t.app_name,
  t.os,
  t.is_gaming,
  t.genre,
  t.monetization_type,
  t.website,
  t.sdk_media_cost_usd_30d,
  t.sdk_media_cost_rank,
  t.bid_requests,
  t.pub_rank_30d,
  t.is_moloco_sdk_app,         
  t.is_moloco_advertiser_app,  
  t.vertical,                  
  t.eligibility_status,
  t.ineligibility_reasons,
  t.eligibility_evaluation_date,
  t.mmp,
  t.mmp_event_names,
  t.sdl_sdk_growth_managers,
  t.sdl_offices,
  t.sdl_ads_growth_managers,
  t.sdl_advertiser_names,
  t.active_ua_networks,
  t.total_downloads_30d,
  t.top_dl_country,
  t.top_dl_country_downloads,
  t.total_revenue_30d,
  t.top_rev_country,
  t.top_rev_country_revenue,
  t.top_sdk_impression_country,   
  cl.moloco_offices                                         AS company_moloco_offices,
  cl.moloco_gms                                             AS company_moloco_gms,
  cl.existing_spend_usd_90d                                 AS company_existing_spend_usd_90d,
  CURRENT_DATE()                                            AS data_as_of
FROM tagged t
-- INNER JOIN 会自动同步把被 company_level 过滤掉的非出海公司在 APP 细分层也干净切掉
INNER JOIN company_level cl ON t.canonical_company = cl.canonical_company
WHERE t.sdk_media_cost_usd_30d > 10000 
  AND t.is_buying_ua = false           
ORDER BY 
  cl.list_type ASC, 
  t.sdk_media_cost_usd_30d DESC;
-- =============================================================================
-- TAB 2: COMPANY 汇总最终输出
-- =============================================================================
-- SELECT
--   cl.list_type,
--   cl.canonical_company,
--   cl.sensortower_hq_country,  -- ST 原始 HQ 国家
--   cl.final_hq_country,        -- GTM 验证后的实际国家（优先）
--   cl.is_manually_corrected,   -- 是否经 GTM 人工核查
--   cl.hq_region,
--   cl.team_routing,
--   cl.website,
--   cl.tracking_publisher_name,
--   cl.monetization_types,
--   cl.total_sdk_apps,
--   cl.buying_ua_apps,
--   cl.untapped_apps,
--   cl.total_sdk_media_cost_usd_30d,  -- 30 天 SDK 供给 media cost（来自 supply_demand_overlap，非 90d）
--   cl.total_bid_requests,
--   cl.eligibility_statuses,
--   cl.mmps,
--   cl.sdk_growth_managers,
--   CURRENT_DATE()                                                        AS data_as_of
-- FROM company_level cl
-- ORDER BY
--   cl.list_type ASC,
--   cl.total_sdk_media_cost_usd_30d DESC; -- 优化：宏观列表下按30天SDK变现流水规模倒序排列，让头部高价值大客户直接置顶

