from app.models.supply import DetailedAnalysisPayload, TopListsPayload, WeeklyBriefPayload


weekly_brief_mock = WeeklyBriefPayload.model_validate(
    {
        "title": "Supply SMB Cross-Sell",
        "date_range": "May 2026",
        "refresh_status": "BigQuery refresh synced 9 minutes ago",
        "summary": "Moloco already buys inventory from 86 China-HQ companies in the active follow-up pool, but none of them have an official SDK relationship yet. The strongest conversion pocket remains software, utility, and health apps with hybrid monetization, where existing exchange readiness lowers onboarding friction. Gaming is still present in the pipeline, but the current media-cost threshold suppresses many viable titles into P3 instead of P2.",
        "opportunity": "This page is the meeting brief for internal teams: quickly align on where the inventory already exists, which accounts deserve direct NBS attention, and where AI-assisted follow-up can unblock the next wave of SDK outreach.",
        "big_things": [
            "86 companies (P1+P2) are supply-visible — Moloco already buys their inventory, making SDK pitch extremely low-friction.",
            "534 supply-visible companies funnel down to 86 high-priority accounts, a 16% conversion rate through the selection pipeline.",
            "Hybrid-monetization apps dominate the P1 tier, giving the team a clear exchange-readiness angle for outreach.",
        ],
        "week_changes": [],
        "selection_steps": [
            {
                "title": "Step 1",
                "subtitle": "Universe",
                "detail": "Chinese-origin developers with at least 20K latest-month downloads and overseas-first traffic.",
            },
            {
                "title": "Step 2",
                "subtitle": "No Moloco relationship",
                "detail": "Exclude active SDK integrations, active advertiser spend, and company-level Moloco relationships.",
            },
            {
                "title": "Step 3",
                "subtitle": "Supply visible",
                "detail": "Use supply_demand_overlap and publisher exchange signals to find titles Moloco already buys.",
            },
            {
                "title": "Step 4",
                "subtitle": "Priority routing",
                "detail": "Rank into P1-P3 using UA SDK presence, paid download fraction, and active UA network signals.",
            },
        ],
        "priorities": [
            {
                "tier": "P1",
                "label": "Prime",
                "companies": 10,
                "apps": 15,
                "delta": "+2 WoW",
                "note": "High media cost, strong scale, still growing.",
                "route": "NBS direct",
            },
            {
                "tier": "P2",
                "label": "Strong",
                "companies": 76,
                "apps": 109,
                "delta": "+5 WoW",
                "note": "Ready for coordinated NBS + agency follow-up.",
                "route": "NBS + agency",
            },
            {
                "tier": "P3",
                "label": "Visible",
                "companies": 622,
                "delta": "+11 WoW",
                "note": "Supply-visible but lower spend or lower scale.",
                "route": "Agency batch",
            },
            {
                "tier": "P3",
                "label": "Cold",
                "companies": 232,
                "delta": "-4 WoW",
                "note": "No UA SDK or insufficient paid fraction — broad outreach pool.",
                "route": "Agency batch",
            },
        ],
        "highlights": [
            {
                "label": "Active Follow-up Companies",
                "value": "86",
                "detail": "Confirmed China-HQ companies in the P1 + P2 operating pool.",
            },
            {
                "label": "Median Moloco Media Cost",
                "value": "$1,917",
                "detail": "Monthly DSP spend Moloco already pays through open exchange.",
            },
            {
                "label": "Exchange SDK Readiness",
                "value": "100%",
                "detail": "Every P1 + P2 app already runs on familiar exchange infrastructure.",
            },
        ],
        "supporting_charts": [
            {
                "title": "App Types",
                "description": "The active pool is still dominated by utility-heavy non-gaming apps.",
                "rows": [
                    {"label": "Software / Tools", "value": 64, "display": "64%", "color": "#3a86ff"},
                    {"label": "Health & Wellness", "value": 17, "display": "17%", "color": "#8338ec"},
                    {"label": "Media & Entertainment", "value": 8, "display": "8%", "color": "#ff006e"},
                    {"label": "Games", "value": 11, "display": "11%", "color": "#fb5607"},
                ],
            },
            {
                "title": "Download Scale",
                "description": "Enough scale to matter, but still under-served from a supply relationship standpoint.",
                "rows": [
                    {"label": "20K - 50K", "value": 22, "display": "22%", "color": "#ffbe0b"},
                    {"label": "50K - 100K", "value": 29, "display": "29%", "color": "#3a86ff"},
                    {"label": "100K - 500K", "value": 31, "display": "31%", "color": "#8338ec"},
                    {"label": "500K+", "value": 18, "display": "18%", "color": "#ff006e"},
                ],
            },
        ],
        # ── Prospect Funnel (4 selection steps from raw universe → P1+P2 pool) ──
        "funnel_steps": [
            {
                "label": "Chinese-Origin Prospects",
                "description": "Qualified pool: ≥20K downloads, international-first, no Moloco relationship",
                "companies": 940,
                "apps": 1820,
            },
            {
                "label": "Supply Visible",
                "description": "Moloco already buys their supply — strongest cross-sell signal",
                "companies": 534,
                "apps": 1102,
            },
            {
                "label": "CHN Mainland HQ",
                "description": "Mainland China HQ — filtered from supply-visible pool",
                "companies": 432,
                "apps": 891,
            },
            {
                "label": "P1 + P2 Active Pool",
                "description": "Prime and strong-tier — ranked by media cost, downloads, and momentum",
                "companies": 86,
                "apps": 124,
            },
        ],
    }
)

top_lists_mock = TopListsPayload.model_validate(
    {
        "filters": [
            {"label": "P1 + P2 Focus", "value": "86 companies", "tone": "blue"},
            {"label": "Supply Visible", "value": "On", "tone": "green"},
            {"label": "MoM Alerts", "value": "24 fast-growth apps", "tone": "purple"},
            {"label": "AI Suggested Follow-up", "value": "17 accounts"},
        ],
        "companies": [
            {
                "company_name": "Guangzhou Hongshi Information Technology",
                "priority": "P2",
                "company_prospect_label": "P2 - Strong",
                "final_hq_country": "CHN",
                "team_routing": "Non-Gaming",
                "monetization_types": "Hybrid, IAP",
                "total_apps": 2,
                "total_downloads_latest_month": 612000,
                "is_moloco_supply_visible": True,
                "moloco_media_cost_30d": 97224,
                "all_active_networks": "Google ADX, Vungle, InMobi",
                "apps_with_other_exchange_sdk": 2,
            },
            {
                "company_name": "QR Code Scanner.",
                "priority": "P1",
                "company_prospect_label": "P1 - Prime",
                "final_hq_country": "CHN",
                "team_routing": "Non-Gaming",
                "monetization_types": "Hybrid, IAA",
                "total_apps": 9,
                "total_downloads_latest_month": 704000,
                "is_moloco_supply_visible": True,
                "moloco_media_cost_30d": 89127,
                "all_active_networks": "ADX, AppLovin, Meta",
                "apps_with_other_exchange_sdk": 5,
            },
            {
                "company_name": "Abishkking",
                "priority": "P2",
                "company_prospect_label": "P2 - Strong",
                "final_hq_country": "CHN",
                "team_routing": "Non-Gaming",
                "monetization_types": "Hybrid, IAP",
                "total_apps": 7,
                "total_downloads_latest_month": 488000,
                "is_moloco_supply_visible": True,
                "moloco_media_cost_30d": 83921,
                "all_active_networks": "Google, Meta, TikTok",
                "apps_with_other_exchange_sdk": 3,
            },
            {
                "company_name": "Lark Player",
                "priority": "P2",
                "company_prospect_label": "P2 - Strong",
                "final_hq_country": "SGP",
                "team_routing": "Non-Gaming",
                "monetization_types": "Hybrid",
                "total_apps": 1,
                "total_downloads_latest_month": 851000,
                "is_moloco_supply_visible": True,
                "moloco_media_cost_30d": 77128,
                "all_active_networks": "ADX, Unity, InMobi",
                "apps_with_other_exchange_sdk": 1,
            },
        ],
        "apps": [
            {
                "app_market_bundle": "com.hongshi.v380pro",
                "os": "android",
                "priority": "P2",
                "prospect_label": "P2 - Strong",
                "app_name": "V380 Pro",
                "company_name": "Guangzhou Hongshi Information Technology",
                "team_routing": "Non-Gaming",
                "genre": "Home & Garden Services",
                "monetization_type": "Hybrid",
                "downloads_latest_month": 358000,
                "download_growth_rate_mom": 0.17,
                "active_ua_networks": "Google ADX, Vungle, InMobi",
                "is_moloco_supply_visible": True,
                "moloco_media_cost_usd_30d": 97224,
                "top_dl_country_t1": "ID",
                "active_other_exchange_sdks": "AppLovin, Unity",
            },
            {
                "app_market_bundle": "com.qrscanner.pdfreader",
                "os": "android",
                "priority": "P1",
                "prospect_label": "P1 - Prime",
                "app_name": "PDF Reader - PDF Viewer",
                "company_name": "QR Code Scanner.",
                "team_routing": "Non-Gaming",
                "genre": "Software",
                "monetization_type": "IAA",
                "downloads_latest_month": 416000,
                "download_growth_rate_mom": 0.28,
                "active_ua_networks": "ADX, AppLovin, Meta",
                "is_moloco_supply_visible": True,
                "moloco_media_cost_usd_30d": 89127,
                "top_dl_country_t1": "BR",
                "active_other_exchange_sdks": "AppLovin MAX",
            },
            {
                "app_market_bundle": "com.abishkking.periodtracker",
                "os": "android",
                "priority": "P2",
                "prospect_label": "P2 - Strong",
                "app_name": "Period Tracker Calendar",
                "company_name": "Abishkking",
                "team_routing": "Non-Gaming",
                "genre": "Health & Wellness",
                "monetization_type": "Hybrid-IAP",
                "downloads_latest_month": 224000,
                "download_growth_rate_mom": 0.12,
                "active_ua_networks": "Google, Meta, TikTok",
                "is_moloco_supply_visible": True,
                "moloco_media_cost_usd_30d": 83921,
                "top_dl_country_t1": "US",
                "active_other_exchange_sdks": "InMobi",
            },
        ],
        "company_page": 1,
        "company_total": 940,
        "app_page": 1,
        "app_total": 1820,
        "page_size": 10,
    }
)

detailed_analysis_mock = DetailedAnalysisPayload.model_validate(
    {
        "modules": [
            {
                "title": "Geography Distribution",
                "caption": "Most of the pool is Mainland China or Singapore-registered Chinese-origin entities.",
                "rows": [
                    {"label": "CHN", "value": "57%", "amount": 57},
                    {"label": "SGP", "value": "41%", "amount": 41},
                    {"label": "HKG", "value": "<1%", "amount": 2},
                ],
            },
            {
                "title": "Team Routing",
                "caption": "Non-gaming still owns most of the working set.",
                "chart_type": "pie",
                "rows": [
                    {"label": "Non-Gaming", "value": "72%", "amount": 72},
                    {"label": "Gaming", "value": "28%", "amount": 28},
                ],
            },
            {
                "title": "Monetization Mix",
                "caption": "Hybrid and IAA-heavy apps are the core SDK pitch surface.",
                "chart_type": "pie",
                "rows": [
                    {"label": "Hybrid", "value": "32%", "amount": 32},
                    {"label": "IAA", "value": "24%", "amount": 24},
                    {"label": "IAP", "value": "24%", "amount": 24},
                    {"label": "Hybrid-IAP", "value": "13%", "amount": 13},
                ],
            },
            {
                "title": "Genre Mix",
                "caption": "Software and utility clusters dominate the current opportunity.",
                "chart_type": "pie",
                "rows": [
                    {"label": "Software", "value": "64%", "amount": 64},
                    {"label": "Health", "value": "17%", "amount": 17},
                    {"label": "Media", "value": "8%", "amount": 8},
                    {"label": "Puzzle / Sim", "value": "11%", "amount": 11},
                ],
            },
            {
                "title": "Download Scale",
                "caption": "The pool skews mid-market rather than mega-scale.",
                "rows": [
                    {"label": "20K - 50K", "value": "22%", "amount": 22},
                    {"label": "50K - 100K", "value": "29%", "amount": 29},
                    {"label": "100K - 500K", "value": "31%", "amount": 31},
                    {"label": "500K+", "value": "18%", "amount": 18},
                ],
            },
            {
                "title": "MoM Growth",
                "caption": "A large segment is still growing fast enough to justify immediate contact.",
                "rows": [
                    {"label": "-10% to 0%", "value": "31%", "amount": 31},
                    {"label": "0% to 10%", "value": "21%", "amount": 21},
                    {"label": "10% to 50%", "value": "28%", "amount": 28},
                    {"label": "50%+", "value": "20%", "amount": 20},
                ],
            },
            {
                "title": "Supply Visibility",
                "caption": "Almost the entire active pool already has open-exchange confirmation.",
                "rows": [
                    {"label": "P1 + P2", "value": "119 apps", "amount": 90},
                    {"label": "P3 visible", "value": "622 companies", "amount": 72},
                    {"label": "P3 cold", "value": "232 companies", "amount": 28},
                ],
            },
            {
                "title": "Eligibility Status",
                "caption": "The pipeline is mostly open rather than blocked by eligibility.",
                "rows": [
                    {"label": "Undecided", "value": "98%", "amount": 98},
                    {"label": "Enrolled", "value": "1%", "amount": 1},
                    {"label": "Ineligible", "value": "1%", "amount": 1},
                ],
            },
        ],
        "methodology": [
            {
                "title": "Data Sources",
                "items": [
                    "dim1_app_v3 for app, company, genre, and monetization metadata",
                    "fact_app_basis_v3 for latest-month downloads and primary market filtering",
                    "supply_demand_overlap for Moloco supply visibility and media cost",
                    "fact_dsp_core for UA spend exclusion logic",
                    "fact_dsp_publisher for publisher exchange SDK signals",
                    "download_revenue_v3 for top download and revenue countries",
                    "hq_country_triage for GTM-validated HQ country overrides",
                ],
            },
            {
                "title": "Inclusion Logic",
                "items": [
                    "Latest full month downloads must be at least 20,000",
                    "Primary market cannot be CN, HK, TW, or MO",
                    "HQ must resolve to CHN, HKG, TWN, or SGP unless manually corrected",
                    "App must carry IAA, IAP, or hybrid monetization signals",
                ],
            },
            {
                "title": "Exclusions & Ranking",
                "items": [
                    "Remove apps with Moloco SDK already installed",
                    "Remove company and bundle level Moloco UA relationships in the last 90 days",
                    "Use Moloco media cost, downloads, growth, and supply visibility for priority ranking",
                    "Allow gaming-specific threshold tuning without rewriting the full methodology",
                ],
            },
        ],
    }
)
