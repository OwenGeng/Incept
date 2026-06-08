# Prospect Engine — List 4 / 5 / 6: Cold Prospect Logic

## Overview

Lists 4, 5, and 6 identify **Chinese-owned app developers with zero prior Moloco relationship** who are strong overseas UA candidates. Apps are segmented by monetization model to enable model-specific sales pitches.

---

## List Definitions

| List | Name | Monetization Signal | Sales Goal |
|------|------|---------------------|------------|
| **4** | IAA Cold | `has_ads = true`, `has_iap = false` | Pitch Moloco SDK integration → display UA |
| **5** | IAP Cold | `has_ads = false`, `has_iap = true` | Direct UA campaign, ROAS-focused |
| **6** | Hybrid Cold | Both `has_ads` and `has_iap = true` | AM case-by-case: SDK + UA dual opportunity |

For gaming apps with both signals, genre is used as the tiebreaker: casual genres (Casual, Hypercasual, Puzzle, Arcade, etc.) → **Hybrid-IAA** → List 6; mid-core genres (Strategy, RPG, Shooter, etc.) → **Hybrid-IAP** → List 6.

---

## Inclusion Criteria (all must pass)

| Filter | Condition | Rationale |
|--------|-----------|-----------|
| **Scale** | Overseas monthly downloads ≥ 20,000 (latest full month) | Minimum viable app size |
| **Overseas focus** | Top download country ≠ CN / HK / TW / MO | Exclude domestic-first apps (e.g. WeChat, Xiaohongshu) |
| **HQ scope** | `final_hq_country` in CN / CHN / HK / TW / SG, or GTM-verified | Chinese developer origin (company, not app store) |
| **Monetization** | IAA, IAP, Hybrid-IAA, Hybrid-IAP, or Hybrid | Excludes free apps with no clear monetization |

---

## Exclusion Criteria (any match = excluded)

| Filter | Source | Logic |
|--------|--------|-------|
| **Bundle-level UA spend** | `fact_dsp_core` (90d) | App already running Moloco campaigns |
| **Bundle-level supply** | `supply_demand_overlap` | App is a Moloco supply partner or has SDK |
| **Company-level UA** | `fact_dsp_core` + `dim1_app_v3` (90d) | Any app from the same company has Moloco spend — catches subsidiaries and new apps from existing partners (e.g. ByteDance) |

---

## Data Sources

| Source | Usage |
|--------|-------|
| `sensortower.fact_app_basis_v3` | Monthly downloads (scale threshold + primary market check) |
| `athena.dim1_app_v3` | App metadata, monetization classification, company name |
| `athena.fact_dsp_core` | UA spend exclusion (bundle + company level) |
| `gtm.supply_demand_overlap` | Supply partner / SDK exclusion |
| `sensortower.network_analysis` | Active UA networks (competitor signal, 90d) |
| `athena.fact_dsp_publisher` | Publisher exchange SDK presence (sorted by impression volume) |
| `sensortower.download_revenue_v3` | Top download / revenue country (30d) |
| `yingzi_uploads.hq_country_triage` | GTM-validated HQ country override |

---

## Ranking (within each list)

1. `competitor_network_count DESC` — more active UA networks = stronger buying intent
2. `downloads_latest_month DESC` — app scale
3. `download_growth_rate_mom DESC` — month-over-month momentum
