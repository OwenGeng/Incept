# Supply SMB Cross-Sell Project

## 1. Background & Problem Statement

Moloco's current publisher SDK pipeline is heavily weighted toward large, established accounts. A significant opportunity exists in the **mid-to-long-tail SMB segment**: Chinese-origin developers whose apps have meaningful overseas download scale but have not yet integrated Moloco's publisher SDK.

These developers represent untapped **supply inventory** — their ad impressions are either not being monetized at full potential, or are being monetized exclusively through Google AdMob and Meta Audience Network without exploring additional demand sources.

The Supply SMB Cross-Sell Project is a systematic workflow to **discover, qualify, assign, onboard, and track growth** for this SMB segment, bridging the gap between supply (publisher SDK) and demand (UA campaigns).

---

## 2. Target Universe

### Who We're Looking For

Chinese-owned app developers (HQ in CN / HK / TW / SG) who meet **all** of the following:

| Criterion | Definition |
|-----------|-----------|
| **No Moloco SDK** | `is_moloco_sdk_app = false` at app level AND no SDK relationship at company level |
| **No Moloco UA** | No advertiser spend in last 90 days (both app and company level) |
| **Overseas-first** | Primary download market is NOT China/HK/TW/MO — focused on overseas UA |
| **Scale** | ≥ 20,000 monthly downloads in latest full month |
| **Monetization** | Has advertising or IAP signals (not free apps with no revenue model) |

### Priority Tiers (SMB Cross-Sell Labels)

| Label | Signal | Rationale |
|-------|--------|-----------|
| **P1 — Supply Visible** | Moloco DSP already buys this app's inventory via open exchange | Lowest friction: proven IAA inventory, SDK pitch is "we already work together" |
| **P2 — Other Exchange SDK** | App has integrated other SSP/exchange SDKs (AppLovin, Unity, InMobi, etc.) | Proven SDK integration willingness; just needs Moloco added |
| **P3 — Multi-Network UA** | Actively buying UA on 3+ competitor networks | Strong commercial intent and budget; open to diversification |
| **P4 — Limited UA** | Buying UA on 1–2 non-G/M networks | Some UA sophistication; exploratory pitch |
| **P5 — Large Organic** | ≥ 400K monthly downloads, no paid UA | Scale is there; needs education on paid UA value |
| **P6 — G+M Conservative** | Only on Google/Meta | Conservative UA buyer — lower priority, harder to convert to new SDK |
| **P7 — Early Stage** | Small scale, no UA signal | Long-term pipeline; lower immediate priority |

### Monetization Segmentation

- **List 4 (IAA)**: `has_ads=true, has_iap=false` — pure ad-monetized apps; SDK is the primary product
- **List 5 (IAP)**: `has_ads=false, has_iap=true` — pure IAP; UA campaign without SDK requirement
- **List 6 (Hybrid)**: both `has_ads` and `has_iap` — dual opportunity; AM judgment required

**Focus order: IAA → Hybrid → IAP**. IAA and Hybrid apps directly generate publisher revenue upon SDK integration.

---

## 3. Workflow

```
DISCOVER → QUALIFY → ASSIGN → ONBOARD → TRACK GROWTH
```

### Stage 1 — Discover
- Automated weekly scan across 6 lists (List 1–6 in Prospect Engine)
- Source: Sensor Tower app metadata + Moloco internal supply/demand data
- Output: ranked prospect list by company, with priority label and key signals

### Stage 2 — Qualify
- NBS reviews P1–P3 priority accounts
- Check: is this company already covered by an existing Moloco account team?
- Check: is `final_hq_country` verified (GTM triage)? If `hq_country_source = ST_original`, flag for AI review
- Output: qualified account pool with assigned routing

### Stage 3 — Assign
- **Agency route**: mid-tail accounts (P3–P5) with clear SDK signal → assigned to agency partners
- **Direct NBS route**: top-priority accounts (P1–P2) or strategic accounts → NBS direct outreach
- Assignment tracked in prospect tracking sheet with `assigned_owner` and `recommended_route`

### Stage 4 — Onboard
- SDK integration assistance (for IAA/Hybrid accounts)
- UA campaign setup (for IAP accounts)
- First spend milestone: Day 30 target

### Stage 5 — Track Growth
- Revenue tracked at two windows:
  - **D0–D90**: Initial ramp (SDK fill rate, eCPM, first UA spend)
  - **D90–D180**: Growth rate from baseline (revenue growth %, UA scale-up)
- Ownership transferred to Gaming Growth or Non-Gaming Growth team at D30+

---

## 4. Team Responsibilities & Value

### NBS (Owen's team — project owner)
**Responsibilities**: Prospect discovery, qualification, assignment coordination, pipeline oversight

**Value gained**:
- Replaces manual, static prospect lists with a dynamic, data-driven pipeline
- Pre-qualified leads arrive with priority scores, exchange signals, and company HQ verified
- Reduces time-to-first-pitch by eliminating research overhead

### Agency Sales Partners
**Responsibilities**: Outreach and onboarding for P3–P5 assigned accounts

**Value gained**:
- Ready-to-use account lists with full context (download scale, exchange SDKs, active networks)
- Priority scoring tells them where to focus; no guesswork on account selection
- Clear success metric: SDK live within 30 days → commissionable event

### Gaming Growth Team
**Responsibilities**: Post-onboard SDK revenue monitoring and growth strategy for gaming accounts

**Value gained**:
- Pre-screened gaming accounts with IAA/Hybrid monetization already confirmed
- Revenue growth data at D0–90 and D90–180 provides clear attribution
- Early signal on which Casual/Hypercasual sub-genres respond best to Moloco SDK

### Non-Gaming Growth Team
**Responsibilities**: Same as Gaming Growth for non-gaming IAA/Hybrid accounts

**Value gained**:
- Non-gaming SMB supply is an underdeveloped vertical; this project surfaces it systematically
- Ad-supported utility, social, and entertainment apps with proven scale
- Subscription hybrid apps provide both SDK revenue and UA opportunity

---

## 5. Revenue Tracking Framework

For each onboarded account, track:

| Metric | Window | Definition |
|--------|--------|-----------|
| `sdk_revenue_d90` | D0–D90 | Cumulative SDK publisher revenue in first 90 days |
| `sdk_revenue_d90_d180` | D90–D180 | SDK revenue in the second 90-day window |
| `sdk_revenue_growth_rate` | D90 vs D90–D180 | Period-over-period growth rate |
| `ua_spend_d90` | D0–D90 | UA advertiser spend (for IAP/Hybrid accounts) |
| `ua_spend_d90_d180` | D90–D180 | UA spend growth |
| `days_to_first_revenue` | — | Days from SDK integration to first non-zero publisher revenue |

Growth rate formula: `(D90–D180 revenue − D0–D90 revenue) / D0–D90 revenue`

---

## 6. Project Value & Strategic Rationale

### For Supply: Expanding the SMB Inventory Base
Each SMB SDK integration adds new ad inventory to Moloco's exchange. Unlike large accounts that are already contested, SMB accounts are often underserved — integrating them builds supply density in niche genres, regions, and verticals that improve demand-side fill rates for all advertisers.

### For Demand: Better Targeting Signal
More diverse publisher inventory means advertisers can reach users in contexts that large publishers don't cover (e.g., casual games from emerging SEA/LATAM publishers, niche non-gaming apps). This increases campaign efficiency and reduces advertiser CPIs.

### For the Company: Revenue Multiplier
A typical SMB SDK account may generate modest individual revenue, but at scale (hundreds of onboarded accounts), the aggregate supply revenue is significant — and each account also creates an inbound demand opportunity as the publisher may eventually want to run their own UA campaigns.

### For Agency Partners: Pipeline Quality
Agencies struggle to identify high-quality SMB leads that are both technically ready (have ad SDK infrastructure) and commercially motivated (already spending on UA). The Supply SMB Cross-Sell list provides exactly this: pre-qualified, ranked, with context to customize the pitch.

---

## 7. Success Metrics

| Metric | Target |
|--------|--------|
| Qualified prospects identified per cycle | 100+ companies (P1–P3) |
| SDK integrations in 90 days | 20+ new SDK accounts |
| First-revenue accounts (D0–D90) | ≥ 70% of integrated accounts |
| D90–D180 revenue growth rate | ≥ 30% average |
| Pipeline coverage (assigned owner) | 100% of P1–P2 accounts |
| Agency-onboarded accounts | ≥ 50% of P3–P5 assignments |
