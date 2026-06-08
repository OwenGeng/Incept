import type {
  DetailedAnalysisPayload,
  TopListsPayload,
  WeeklyBriefPayload
} from "@/types/supply";

export const weeklyBriefMock: WeeklyBriefPayload = {
  title: "Supply SMB Cross-Sell",
  dateRange: "May 2026",
  refreshStatus: "BigQuery refresh synced 9 minutes ago",
  summary:
    "Moloco already buys inventory from 86 China-HQ companies in the active follow-up pool, but none of them have an official SDK relationship yet. The strongest conversion pocket remains software, utility, and health apps with hybrid monetization, where existing exchange readiness lowers onboarding friction. Gaming is still present in the pipeline, but the current media-cost threshold suppresses many viable titles into P3 instead of P2.",
  opportunity:
    "This page is the meeting brief for internal teams: quickly align on where the inventory already exists, which accounts deserve direct NBS attention, and where AI-assisted follow-up can unblock the next wave of SDK outreach.",
  selectionSteps: [
    {
      title: "Step 1",
      subtitle: "Universe",
      detail:
        "Chinese-origin developers with at least 20K latest-month downloads and overseas-first traffic."
    },
    {
      title: "Step 2",
      subtitle: "No Moloco relationship",
      detail:
        "Exclude active SDK integrations, active advertiser spend, and company-level Moloco relationships."
    },
    {
      title: "Step 3",
      subtitle: "Supply visible",
      detail:
        "Use supply_demand_overlap and publisher exchange signals to find titles Moloco already buys."
    },
    {
      title: "Step 4",
      subtitle: "Priority routing",
      detail:
        "Rank into P1-P4 using Moloco media cost, downloads, momentum, and routing logic."
    }
  ],
  priorities: [
    {
      tier: "P1",
      label: "Prime",
      companies: 10,
      apps: 15,
      delta: "+2 WoW",
      note: "High media cost, strong scale, still growing.",
      route: "NBS direct"
    },
    {
      tier: "P2",
      label: "Strong",
      companies: 76,
      apps: 109,
      delta: "+5 WoW",
      note: "Ready for coordinated NBS + agency follow-up.",
      route: "NBS + agency"
    },
    {
      tier: "P3",
      label: "Visible",
      companies: 622,
      delta: "+11 WoW",
      note: "Supply-visible but lower spend or lower scale.",
      route: "Agency batch"
    },
    {
      tier: "P4",
      label: "Cold",
      companies: 232,
      delta: "-4 WoW",
      note: "Longer-horizon pipeline without Moloco visibility.",
      route: "Monitor"
    }
  ],
  highlights: [
    {
      label: "Active Follow-up Companies",
      value: "86",
      detail: "Confirmed China-HQ companies in the P1 + P2 operating pool."
    },
    {
      label: "Median Moloco Media Cost",
      value: "$1,917",
      detail: "Monthly DSP spend Moloco already pays through open exchange."
    },
    {
      label: "Exchange SDK Readiness",
      value: "100%",
      detail: "Every P1 + P2 app already runs on familiar exchange infrastructure."
    }
  ],
  bigThings: [
    "Moloco-visible supply accounts anchor the top of the priority queue.",
    "Fast-growth gaming titles are clustering below the current P1 threshold.",
    "AI follow-up suggestions target stale notes and unverified HQ countries.",
  ],
  weekChanges: [
    "P2 pool grew by 5 companies — mostly utility and health genres.",
    "3 P3 companies upgraded to P2 on stronger media cost signals.",
  ],
  funnelSteps: [
    {
      label: "Chinese-Origin Prospects",
      description: "Apps with CHN/HKG/SGP/TWN HQ, ≥20K monthly downloads, non-mainland primary market.",
      companies: 940,
      apps: 1820,
    },
    {
      label: "Supply Visible",
      description: "Moloco already buys their inventory via open exchange.",
      companies: 534,
      apps: 1102,
    },
    {
      label: "CHN Mainland HQ",
      description: "Final HQ confirmed as China — primary outreach target.",
      companies: 432,
      apps: 891,
    },
    {
      label: "P1 + P2 Active Pool",
      description: "High-priority accounts in direct NBS or NBS + agency working queue.",
      companies: 86,
      apps: 124,
    },
  ],
  supportingCharts: [
    {
      title: "App Types",
      description: "The active pool is still dominated by utility-heavy non-gaming apps.",
      rows: [
        { label: "Software / Tools", value: 64, display: "64%", color: "#3a86ff" },
        { label: "Health & Wellness", value: 17, display: "17%", color: "#8338ec" },
        { label: "Media & Entertainment", value: 8, display: "8%", color: "#ff006e" },
        { label: "Games", value: 11, display: "11%", color: "#fb5607" }
      ]
    },
    {
      title: "Download Scale",
      description: "Enough scale to matter, but still under-served from a supply relationship standpoint.",
      rows: [
        { label: "20K - 50K", value: 22, display: "22%", color: "#ffbe0b" },
        { label: "50K - 100K", value: 29, display: "29%", color: "#3a86ff" },
        { label: "100K - 500K", value: 31, display: "31%", color: "#8338ec" },
        { label: "500K+", value: 18, display: "18%", color: "#ff006e" }
      ]
    }
  ]
};

export const topListsMock: TopListsPayload = {
  filters: [
    { label: "P1 + P2 Focus", value: "86 companies", tone: "blue" },
    { label: "Supply Visible", value: "On", tone: "green" },
    { label: "MoM Alerts", value: "24 fast-growth apps", tone: "purple" },
    { label: "AI Suggested Follow-up", value: "17 accounts" }
  ],
  companies: [
    {
      companyName: "Guangzhou Hongshi Information Technology",
      priority: "P2",
      companyProspectLabel: "P2 - Strong",
      finalHqCountry: "CHN",
      teamRouting: "Non-Gaming",
      monetizationTypes: "Hybrid, IAP",
      totalApps: 2,
      totalDownloadsLatestMonth: 612000,
      isMolocoSupplyVisible: true,
      molocoMediaCost30d: 97224,
      allActiveNetworks: "Google ADX, Vungle, InMobi",
      appsWithOtherExchangeSdk: 2
    },
    {
      companyName: "QR Code Scanner.",
      priority: "P1",
      companyProspectLabel: "P1 - Prime",
      finalHqCountry: "CHN",
      teamRouting: "Non-Gaming",
      monetizationTypes: "Hybrid, IAA",
      totalApps: 9,
      totalDownloadsLatestMonth: 704000,
      isMolocoSupplyVisible: true,
      molocoMediaCost30d: 89127,
      allActiveNetworks: "ADX, AppLovin, Meta",
      appsWithOtherExchangeSdk: 5
    },
    {
      companyName: "Abishkking",
      priority: "P2",
      companyProspectLabel: "P2 - Strong",
      finalHqCountry: "CHN",
      teamRouting: "Non-Gaming",
      monetizationTypes: "Hybrid, IAP",
      totalApps: 7,
      totalDownloadsLatestMonth: 488000,
      isMolocoSupplyVisible: true,
      molocoMediaCost30d: 83921,
      allActiveNetworks: "Google, Meta, TikTok",
      appsWithOtherExchangeSdk: 3
    },
    {
      companyName: "Lark Player",
      priority: "P2",
      companyProspectLabel: "P2 - Strong",
      finalHqCountry: "SGP",
      teamRouting: "Non-Gaming",
      monetizationTypes: "Hybrid",
      totalApps: 1,
      totalDownloadsLatestMonth: 851000,
      isMolocoSupplyVisible: true,
      molocoMediaCost30d: 77128,
      allActiveNetworks: "ADX, Unity, InMobi",
      appsWithOtherExchangeSdk: 1
    },
    {
      companyName: "INTSIG Information (CamScanner)",
      priority: "P1",
      companyProspectLabel: "P1 - Prime",
      finalHqCountry: "CHN",
      teamRouting: "Non-Gaming",
      monetizationTypes: "Hybrid",
      totalApps: 1,
      totalDownloadsLatestMonth: 391000,
      isMolocoSupplyVisible: true,
      molocoMediaCost30d: 30264,
      allActiveNetworks: "ADX, AppLovin",
      appsWithOtherExchangeSdk: 1
    },
    {
      companyName: "Play2Ever Games",
      priority: "P2",
      companyProspectLabel: "P2 - Strong",
      finalHqCountry: "CHN",
      teamRouting: "Gaming",
      monetizationTypes: "IAP",
      totalApps: 1,
      totalDownloadsLatestMonth: 222000,
      isMolocoSupplyVisible: true,
      molocoMediaCost30d: 24901,
      allActiveNetworks: "Unity, AppLovin MAX",
      appsWithOtherExchangeSdk: 1
    }
  ],
  apps: [
    {
      appMarketBundle: "com.hongshi.v380pro",
      os: "android",
      priority: "P2",
      prospectLabel: "P2 - Strong",
      appName: "V380 Pro",
      companyName: "Guangzhou Hongshi Information Technology",
      teamRouting: "Non-Gaming",
      genre: "Home & Garden Services",
      monetizationType: "Hybrid",
      downloadsLatestMonth: 358000,
      downloadGrowthRateMom: 0.17,
      activeUaNetworks: "Google ADX, Vungle, InMobi",
      isMolocoSupplyVisible: true,
      molocoMediaCostUsd30d: 97224,
      topDlCountryT1: "ID",
      activeOtherExchangeSdks: "AppLovin, Unity"
    },
    {
      appMarketBundle: "com.qrscanner.pdfreader",
      os: "android",
      priority: "P1",
      prospectLabel: "P1 - Prime",
      appName: "PDF Reader - PDF Viewer",
      companyName: "QR Code Scanner.",
      teamRouting: "Non-Gaming",
      genre: "Software",
      monetizationType: "IAA",
      downloadsLatestMonth: 416000,
      downloadGrowthRateMom: 0.28,
      activeUaNetworks: "ADX, AppLovin, Meta",
      isMolocoSupplyVisible: true,
      molocoMediaCostUsd30d: 89127,
      topDlCountryT1: "BR",
      activeOtherExchangeSdks: "AppLovin MAX"
    },
    {
      appMarketBundle: "com.abishkking.periodtracker",
      os: "android",
      priority: "P2",
      prospectLabel: "P2 - Strong",
      appName: "Period Tracker Calendar",
      companyName: "Abishkking",
      teamRouting: "Non-Gaming",
      genre: "Health & Wellness",
      monetizationType: "Hybrid-IAP",
      downloadsLatestMonth: 224000,
      downloadGrowthRateMom: 0.12,
      activeUaNetworks: "Google, Meta, TikTok",
      isMolocoSupplyVisible: true,
      molocoMediaCostUsd30d: 83921,
      topDlCountryT1: "US",
      activeOtherExchangeSdks: "InMobi"
    },
    {
      appMarketBundle: "com.larkplayer.music",
      os: "android",
      priority: "P2",
      prospectLabel: "P2 - Strong",
      appName: "Lark Player: Music & MP3",
      companyName: "Lark Player",
      teamRouting: "Non-Gaming",
      genre: "Software",
      monetizationType: "Hybrid",
      downloadsLatestMonth: 851000,
      downloadGrowthRateMom: -0.03,
      activeUaNetworks: "ADX, Unity, InMobi",
      isMolocoSupplyVisible: true,
      molocoMediaCostUsd30d: 77128,
      topDlCountryT1: "IN",
      activeOtherExchangeSdks: "Unity Ads"
    },
    {
      appMarketBundle: "com.intsig.camscanner",
      os: "android",
      priority: "P1",
      prospectLabel: "P1 - Prime",
      appName: "CamScanner",
      companyName: "INTSIG Information (CamScanner)",
      teamRouting: "Non-Gaming",
      genre: "Software",
      monetizationType: "Hybrid",
      downloadsLatestMonth: 391000,
      downloadGrowthRateMom: 0.11,
      activeUaNetworks: "ADX, AppLovin",
      isMolocoSupplyVisible: true,
      molocoMediaCostUsd30d: 30264,
      topDlCountryT1: "MX",
      activeOtherExchangeSdks: "AdMob"
    },
    {
      appMarketBundle: "com.play2ever.colorblockrun",
      os: "android",
      priority: "P2",
      prospectLabel: "P2 - Strong",
      appName: "Color Block Run - Puzzle",
      companyName: "Play2Ever Games",
      teamRouting: "Gaming",
      genre: "Puzzle",
      monetizationType: "Hybrid-IAA",
      downloadsLatestMonth: 222000,
      downloadGrowthRateMom: 0.42,
      activeUaNetworks: "Unity, AppLovin MAX",
      isMolocoSupplyVisible: true,
      molocoMediaCostUsd30d: 24901,
      topDlCountryT1: "US",
      activeOtherExchangeSdks: "AppLovin MAX"
    }
  ],
  companyPage: 1,
  companyTotal: 6,
  appPage: 1,
  appTotal: 6,
  pageSize: 10
};

export const detailedAnalysisMock: DetailedAnalysisPayload = {
  modules: [
    {
      title: "Geography Distribution",
      caption: "Most of the pool is Mainland China or Singapore-registered Chinese-origin entities.",
      rows: [
        { label: "CHN", value: "57%", amount: 57 },
        { label: "SGP", value: "41%", amount: 41 },
        { label: "HKG", value: "<1%", amount: 2 }
      ]
    },
    {
      title: "Team Routing",
      caption: "Non-gaming still owns most of the working set.",
      chartType: "pie",
      rows: [
        { label: "Non-Gaming", value: "72%", amount: 72 },
        { label: "Gaming", value: "28%", amount: 28 }
      ]
    },
    {
      title: "Monetization Mix",
      caption: "Hybrid and IAA-heavy apps are the core SDK pitch surface.",
      chartType: "pie",
      rows: [
        { label: "Hybrid", value: "32%", amount: 32 },
        { label: "IAA", value: "24%", amount: 24 },
        { label: "IAP", value: "24%", amount: 24 },
        { label: "Hybrid-IAP", value: "13%", amount: 13 }
      ]
    },
    {
      title: "Genre Mix",
      caption: "Software and utility clusters dominate the current opportunity.",
      chartType: "pie",
      rows: [
        { label: "Software", value: "64%", amount: 64 },
        { label: "Health", value: "17%", amount: 17 },
        { label: "Media", value: "8%", amount: 8 },
        { label: "Puzzle / Sim", value: "11%", amount: 11 }
      ]
    },
    {
      title: "Download Scale",
      caption: "The pool skews mid-market rather than mega-scale.",
      rows: [
        { label: "20K - 50K", value: "22%", amount: 22 },
        { label: "50K - 100K", value: "29%", amount: 29 },
        { label: "100K - 500K", value: "31%", amount: 31 },
        { label: "500K+", value: "18%", amount: 18 }
      ]
    },
    {
      title: "MoM Growth",
      caption: "A large segment is still growing fast enough to justify immediate contact.",
      rows: [
        { label: "-10% to 0%", value: "31%", amount: 31 },
        { label: "0% to 10%", value: "21%", amount: 21 },
        { label: "10% to 50%", value: "28%", amount: 28 },
        { label: "50%+", value: "20%", amount: 20 }
      ]
    },
    {
      title: "Supply Visibility",
      caption: "Almost the entire active pool already has open-exchange confirmation.",
      rows: [
        { label: "P1 + P2", value: "119 apps", amount: 90 },
        { label: "P3 visible", value: "622 companies", amount: 72 },
        { label: "P4 cold", value: "232 companies", amount: 28 }
      ]
    },
    {
      title: "Eligibility Status",
      caption: "The pipeline is mostly open rather than blocked by eligibility.",
      rows: [
        { label: "Undecided", value: "98%", amount: 98 },
        { label: "Enrolled", value: "1%", amount: 1 },
        { label: "Ineligible", value: "1%", amount: 1 }
      ]
    }
  ],
  methodology: [
    {
      title: "Data Sources",
      items: [
        "dim1_app_v3 for app, company, genre, and monetization metadata",
        "fact_app_basis_v3 for latest-month downloads and primary market filtering",
        "supply_demand_overlap for Moloco supply visibility and media cost",
        "fact_dsp_core for UA spend exclusion logic",
        "fact_dsp_publisher for publisher exchange SDK signals",
        "download_revenue_v3 for top download and revenue countries",
        "hq_country_triage for GTM-validated HQ country overrides"
      ]
    },
    {
      title: "Inclusion Logic",
      items: [
        "Latest full month downloads must be at least 20,000",
        "Primary market cannot be CN, HK, TW, or MO",
        "HQ must resolve to CHN, HKG, TWN, or SGP unless manually corrected",
        "App must carry IAA, IAP, or hybrid monetization signals"
      ]
    },
    {
      title: "Exclusions & Ranking",
      items: [
        "Remove apps with Moloco SDK already installed",
        "Remove company and bundle level Moloco UA relationships in the last 90 days",
        "Use Moloco media cost, downloads, growth, and supply visibility for priority ranking",
        "Allow gaming-specific threshold tuning without rewriting the full methodology"
      ]
    }
  ]
};
