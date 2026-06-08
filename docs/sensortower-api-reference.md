# Sensor Tower API Reference (Prospect Engine)

> **Note**: This document is based on the actual call logic in the market-prospecting-scanner skill and the Speedboat MCP source code.
> Official documentation requires login: https://app.sensortower.com/api/docs/app_analysis and https://app.sensortower.com/api/v2/docs
> Full parameter details to be filled in once auth_token is available.

---

## Base Information

| Item | Value |
|------|-----|
| Base URL | `https://api.sensortower.com` |
| Authentication | Query param: `?auth_token={YOUR_TOKEN}` or Header: `Authorization: Bearer {YOUR_TOKEN}` |
| Data format | JSON |
| OS parameter | `ios` / `android` / `unified` (unified merges both platforms) |

---

## Prospect Engine Core Endpoints

### 1. Top Publishers (Primary Data Source)

```
GET /v1/{os}/publishers/top
```

**Purpose**: Retrieves top publishers by download volume or revenue. This is the main entry point for the Prospect Engine to discover "No UA No SDK" accounts.

**Key Parameters**:

| Parameter | Type | Required | Description |
|------|------|------|------|
| `os` | string | ✅ | `ios` / `android` / `unified` |
| `category` | string | ✅ | Gaming category or non-gaming category (see appendix) |
| `country` | string | ⚠️ | **Filters by download market, not publisher HQ.** For China-focused scenarios, leave this field empty (to pull the global chart) and then filter HQ using `custom_tags["Publisher Country"]` |
| `date` | string | ✅ | Format `YYYY-MM-01`; fetches data for that month |
| `time_range` | string | ✅ | `month` / `week` |
| `limit` | int | ✅ | Maximum 50 per call; pagination required (offset 0 + offset 50) |
| `offset` | int | | Pagination offset |

**Key response fields (within `custom_tags`)**:

| Field | Purpose |
|------|------|
| `Publisher Country` | Publisher HQ country — **use this to filter Chinese developers** |
| `Most Popular Country by Downloads` | Top download market. For Chinese developers targeting overseas UA: this value must not be China to qualify as a valid prospect |
| `Most Popular Country by Revenue` | Top revenue market |
| `Game Genre` | Game major category |
| `Game Sub-genre` | Game sub-category |
| `Game Product Model` | Monetization model; values include `Casual` / `Hypercasual` (used for IAA classification) |
| `Advertised on Any Network` | `Active` / `Inactive` |
| `Advertises on Moloco Network` | `Active` = already running ads on Moloco |
| `Advertises on AppLovin Network` | Competitor signal |
| `Advertises on Unity Network` | Competitor signal |
| `Advertises on ironSource Network` | Competitor signal |
| `Advertises on Facebook Network` | Competitor signal |
| `Advertises on TikTok Network` | Competitor signal |
| `Advertises on Mintegral Network` | Competitor signal |
| `Advertises on Google UAC Network` | Competitor signal |
| `Advertises on Pangle Network` | Competitor signal |
| `Website URL` | Publisher website; used for outreach |
| `Support URL (iOS)` | Fallback website (use when Website URL is empty) |
| `Primary Category` | App category |
| `All Time Downloads (WW)` | All-time total downloads worldwide |

**Note**: The `country` parameter controls which market's chart is returned — it is unrelated to publisher HQ. Pull the global chart first, then filter HQ using `custom_tags["Publisher Country"]`.

---

### 2. Sales Report Estimates (Download and Revenue Estimates)

```
GET /v1/{os}/sales_report_estimates
```

**Purpose**: Retrieves historical download volume and revenue estimates for specific apps; used for the Scale dimension in scoring.

**Key Parameters**:

| Parameter | Type | Required | Description |
|------|------|------|------|
| `app_ids` | array | ✅ | List of ST app IDs |
| `countries` | array | ✅ | Country codes, e.g. `["US", "IN", "BR"]`; iOS uses 2-letter codes; note differences for Android bundle IDs |
| `date_granularity` | string | ✅ | `daily` / `weekly` / `monthly` |
| `start_date` | string | ✅ | `YYYY-MM-DD` |
| `end_date` | string | ✅ | `YYYY-MM-DD` |

**Notes**:
- Android bundle IDs cannot retrieve per-country data; only `Most Popular Country by Downloads` is available
- Data for the most recent 7 days is preliminary (estimates are unstable)

---

### 3. App Search & Metadata

```
GET /v1/{os}/apps
```

**Purpose**: Query app metadata by app ID or name; can include SDK data.

**Key Parameters**:

| Parameter | Type | Required | Description |
|------|------|------|------|
| `app_ids` | array | | List of ST app IDs |
| `include_sdk_data` | bool | | Returns SDK integration information when `true` |

---

### 4. Ad Network Analysis (Competitor Network Signals)

```
GET /v1/{os}/ad_intel/network_analysis
```

**Purpose**: Retrieves the app's advertising activity (Share of Voice) across ad networks; used for the Commercial Activity dimension in scoring.

**Key Parameters**:

| Parameter | Type | Required | Description |
|------|------|------|------|
| `app_ids` | array | ✅ | List of ST app IDs |
| `start_date` | string | ✅ | `YYYY-MM-DD` |
| `end_date` | string | ✅ | `YYYY-MM-DD` |
| `networks` | array | | Filter to specific networks; leave empty for all |

**Efficiency note**: If `custom_tags` were already retrieved from Top Publishers, they already include Active/Inactive status for each network. **No need to call this endpoint separately.** Use this endpoint only when more granular SOV data (specific impression share numbers) is required.

---

### 5. Active Users / Usage

```
GET /v1/{os}/usage/active_users
```

**Purpose**: DAU / WAU / MAU; used for the Scale and Growth dimensions in scoring.

**Key Parameters**:

| Parameter | Type | Required | Description |
|------|------|------|------|
| `app_ids` | array | ✅ | List of ST app IDs |
| `date_granularity` | string | ✅ | `daily` / `weekly` / `monthly` |
| `start_date` | string | ✅ | `YYYY-MM-DD` |
| `end_date` | string | ✅ | `YYYY-MM-DD` |
| `countries` | array | | Country filter |

---

### 6. Downloads by Sources / Channel

```
GET /v1/{os}/downloads_by_sources
```

**Purpose**: Breaks down downloads by channel (organic vs paid vs paid_ads); **used to determine whether an app has paid UA activity** (Tier 2 classification aid).

**Key Parameters**:

| Parameter | Type | Required | Description |
|------|------|------|------|
| `app_ids` | array | ✅ | |
| `countries` | array | ✅ | |
| `date_granularity` | string | ✅ | `monthly` is most stable |
| `start_date` / `end_date` | string | ✅ | |

**Note**: Updated monthly; typically refreshes the previous month's data around the 9th of each month, with approximately 48 hours of lag.

---

### 7. Top Creatives (Ad Creatives)

```
GET /v1/{os}/ad_intel/creatives/top
```

**Purpose**: View competitor or target account ad creative placements; used for outreach preparation and competitive analysis. Not required for the Prospect Engine core workflow; useful as a supplemental sales outreach tool.

---

### 8. App Update / Version History

```
GET /v1/{os}/apps/{app_id}/updates
GET /v1/{os}/apps/{app_id}/versions
```

**Purpose**: Understand an app's update activity; aids in determining whether an app is still actively maintained (not a zombie app).

---

## Prospect Engine Data Flow Mapping

| Prospect Engine Module | ST Endpoint Used | Notes |
|----------------------|-------------------|------|
| Lead Intake (No UA No SDK) | `Top Publishers` | Primary data source; pull full list → filter by HQ country |
| China identification (Layer 1) | `custom_tags["Publisher Country"]` | From Top Publishers response |
| China identification (Layer 2 pattern) | `custom_tags` company name, website | Supplemental judgment |
| Commercial Activity scoring | `custom_tags["Advertises on X Network"]` | From Top Publishers; no additional calls needed |
| Scale scoring | `Sales Report Estimates` or `custom_tags["All Time Downloads"]` | Prefer custom_tags for bulk scenarios |
| Growth scoring | `Sales Report Estimates` (30/90-day comparison) | Requires additional call |
| UA channel classification (Tier 2 aid) | `Downloads by Sources` | Paid vs organic breakdown |

---

## BigQuery Mirror Refresh Frequency

ST data update cadence in BQ (relevant for batch processing):

| Table | Refresh Frequency | Notes |
|----|----------|------|
| `athena.dim1_app_v3` | Daily at 06:00 UTC | App / company metadata |
| `athena.fact_app_v3` | Daily (triggered downstream of dim1_app_v3) | Downloads/revenue; approximately 2-day lag |
| `sensortower.network_analysis` | Refreshed every Wednesday | Source data is available daily with ~2-day lag; BQ mirror is weekly granularity |

**Implication**: When designing the Prospect Engine refresh cadence, note that network_analysis updates at most once per week. dim1/fact update daily, but download/revenue data has a 2-day lag — yesterday's data is not available on the same day.

---

## Call Efficiency Recommendations

1. **A single Top Publishers call retrieves most signals** (`custom_tags` includes competitor networks, HQ country, genre, etc.); no need to call Ad Network Analysis separately.
2. **Use BQ for bulk processing**: `dim1_app_v3`, `network_analysis`, and `fact_app_v3` are BQ mirrors of ST data; use BQ for large-scale scans and use the ST API only for point lookups and validation.
3. **Android country-level data is unreliable**: `sales_report_estimates` frequently returns empty results for per-country data on Android bundle IDs; only use the `Most Popular Country` field.
4. **Data freshness**: Download/revenue estimates have approximately 48 hours of lag; monthly channel data is typically updated with the previous month's data around the 9th of each month.

---

## Appendix: Category Values Reference

### Gaming
`Games` / `Casual` / `Puzzle` / `Strategy` / `RPG` / `Action` / `Simulation` / `Sports` / `Racing` / `Card` / `Board` / `Hypercasual` / `Adventure`

### Non-Gaming
`Finance` / `Shopping` / `Social Networking` / `Entertainment` / `Travel` / `Food & Drink` / `Health & Fitness` / `Utilities` / `Education` / `Lifestyle`

---

## To Be Completed (requires auth_token to access official documentation)

- [ ] Full response schema (all fields and types)
- [ ] Rate limit specifics (requests per minute / per day)
- [ ] Functional differences between `v2` API and `v1` API (`https://app.sensortower.com/api/v2/docs`)
- [ ] Complete pagination mechanism (cursor vs offset)
- [ ] Error code list
- [ ] Full structure of SDK fields returned when `include_sdk_data=true`
