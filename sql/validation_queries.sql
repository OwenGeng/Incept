-- =============================================================================
-- Prospect Engine V1 — Validation Queries
-- Run these after prospect_list_v1.sql to sanity-check the data
-- =============================================================================

-- V1: Row count by list type
-- Expected: List1 << List2 ≈ List3 (List1 should be tens to low hundreds for CHN)
SELECT
  list_type,
  COUNT(*)                                            AS total_apps,
  COUNT(DISTINCT parent_company_name)                 AS unique_parent_companies,
  COUNT(DISTINCT company_name)                        AS unique_companies,
  COUNTIF(team_routing = 'Gaming')                    AS gaming_count,
  COUNTIF(team_routing = 'Non-Gaming')                AS non_gaming_count,
  COUNTIF(china_confidence = 'High')                  AS china_high,
  COUNTIF(china_confidence = 'Medium')                AS china_medium,
  COUNTIF(china_confidence = 'Low-Review')            AS china_low_review
FROM (
  -- paste or reference the full query output here
  SELECT * FROM `<your_project>.prospect_engine.prospect_list_v1`
)
WHERE list_type IS NOT NULL
GROUP BY list_type
ORDER BY list_type;

-- ---------------------------------------------------------------------------
-- V2: List 1 top 20 — manual eyeball check
-- These should be recognizable apps that actually have Moloco SDK
-- ---------------------------------------------------------------------------
SELECT
  app_market_bundle, os, app_name, company_name, parent_company_name,
  hq_country, genre, downloads_90d, competitor_network_count,
  sdk_media_cost_usd, eligibility_status, prospect_label
FROM `<your_project>.prospect_engine.prospect_list_v1`
WHERE list_type = 'List1_SDK_NoSpend'
ORDER BY downloads_90d DESC
LIMIT 20;

-- ---------------------------------------------------------------------------
-- V3: Cross-list overlap check
-- An app should appear in exactly ONE list. If count > 1, classification logic has a bug.
-- ---------------------------------------------------------------------------
SELECT
  app_market_bundle,
  os,
  STRING_AGG(list_type ORDER BY list_type) AS lists_assigned,
  COUNT(DISTINCT list_type)                AS n_lists
FROM `<your_project>.prospect_engine.prospect_list_v1`
WHERE list_type IS NOT NULL
GROUP BY app_market_bundle, os
HAVING COUNT(DISTINCT list_type) > 1
ORDER BY n_lists DESC
LIMIT 20;
-- Expected result: 0 rows. If rows appear, review the list classification CASE logic.

-- ---------------------------------------------------------------------------
-- V4: Download threshold sensitivity
-- Check how many apps pass/fail at different thresholds before fixing the cutoff
-- ---------------------------------------------------------------------------
SELECT
  threshold,
  COUNTIF(downloads_90d >= threshold AND genre IN (
    'Casual','Puzzle','Hypercasual','Arcade','Word','Board','Card','Trivia',
    'Strategy','RPG','Action','Shooter','Sports','Racing','Simulation'
  ) AND gross_spend_usd = 0) AS apps_above_threshold
FROM UNNEST([100000, 250000, 500000, 1000000, 2000000, 5000000]) AS threshold
CROSS JOIN (
  SELECT downloads_90d, genre, gross_spend_usd
  FROM `<your_project>.prospect_engine.prospect_list_v1`
)
GROUP BY threshold
ORDER BY threshold;

-- ---------------------------------------------------------------------------
-- V5: Genre distribution — are IAA / IAP genres classified as expected?
-- ---------------------------------------------------------------------------
SELECT
  list_type,
  genre,
  COUNT(*)           AS app_count,
  SUM(downloads_90d) AS total_downloads_90d
FROM `<your_project>.prospect_engine.prospect_list_v1`
WHERE list_type IN ('List2_IAA_NoMoloco', 'List3_IAP_NoMoloco')
GROUP BY list_type, genre
ORDER BY list_type, total_downloads_90d DESC;

-- ---------------------------------------------------------------------------
-- V6: "Has other exchange SDK" sub-list (high value sub-set of List 2)
-- These are apps visible in Moloco's supply stream but without Moloco SDK
-- ---------------------------------------------------------------------------
SELECT
  app_market_bundle, os, app_name, company_name, genre,
  downloads_90d, competitor_network_count, bid_requests,
  is_sdk_any, is_moloco_sdk_app, eligibility_status
FROM `<your_project>.prospect_engine.prospect_list_v1`
WHERE list_type = 'List2_IAA_NoMoloco'
  AND has_other_exchange_sdk = true
ORDER BY downloads_90d DESC
LIMIT 30;

-- ---------------------------------------------------------------------------
-- V7: China confidence distribution — how many need manual review?
-- ---------------------------------------------------------------------------
SELECT
  china_confidence,
  COUNT(*)                       AS app_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM `<your_project>.prospect_engine.prospect_list_v1`
WHERE list_type IS NOT NULL
GROUP BY china_confidence
ORDER BY app_count DESC;

-- ---------------------------------------------------------------------------
-- V8: MMP distribution (for context on attribution setup)
-- Useful for sales to know what MMP the prospect is using
-- ---------------------------------------------------------------------------
SELECT
  list_type,
  COALESCE(mmp, '(none / unknown)') AS mmp,
  COUNT(*)                          AS app_count
FROM `<your_project>.prospect_engine.prospect_list_v1`
WHERE list_type IS NOT NULL
GROUP BY list_type, mmp
ORDER BY list_type, app_count DESC;

-- ---------------------------------------------------------------------------
-- V9: supply_demand_overlap raw check
-- Confirm List 1 filter logic against source table directly
-- Expected: rows where is_moloco_sdk_app=true and gross_spend_usd=0
-- ---------------------------------------------------------------------------
SELECT
  app_bundle, os, app_name, is_moloco_sdk_app, is_moloco_advertiser_app,
  gross_spend_usd, sdk_media_cost_usd, bid_requests, eligibility_status
FROM `ads-bpd-guard-china.gtm.supply_demand_overlap`
WHERE is_moloco_sdk_app = true
  AND gross_spend_usd = 0
ORDER BY sdk_media_cost_usd DESC
LIMIT 30;
-- Cross-check: these bundles should all appear in List1_SDK_NoSpend output
