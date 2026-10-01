# SensorTower API Reference

Comprehensive reference covering all endpoints from `app_analysis.yml`, `custom_fields_metadata.yml`, `market_analysis.yml`, and `store_marketing.yml`.

---

## Global Config

| Item | Value |
|------|-------|
| Base URL | `https://api.sensortower.com` |
| Auth | `?auth_token=<token>` on every request |
| Rate limit | 6 requests/second |
| Monthly quota | `x-api-usage-limit` / `x-api-usage-count` response headers |

### App ID Types

| Type | Format | Example |
|------|--------|---------|
| iOS | Integer string | `"284882215"` |
| Android | Package name | `"com.facebook.katana"` |
| Unified | Hex string | `"55c530a702ac64f9c0002dff"` |

### OS Path Parameter

Endpoints using `{os}` accept: `ios`, `android`, or `unified`. The `unified` value is only valid on endpoints that explicitly support it.

---

## Part 1: App Analysis API (`app_analysis.yml`)

### 1. App Metadata

**`GET /v1/{os}/apps`**

Returns app metadata for one or more apps.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated list of app IDs |
| `os` | Yes (path) | `ios` or `android` |

**Response key fields:** `app_id`, `name`, `publisher_name`, `publisher_id`, `category`, `sub_category`, `rating`, `ratings_count`, `price`, `icon_url`, `release_date`, `version`, `description`, `supported_devices`, `languages`

---

### 2. Top In-App Purchases (iOS only)

**`GET /v1/ios/apps/top_in_app_purchases`**

Returns top in-app purchases for an iOS app.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | iOS numeric app ID |

---

### 3. Downloads & Revenue Estimates

**`GET /v1/{os}/sales_report_estimates`**

Returns estimated downloads and revenue.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated app IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated ISO country codes; omit for worldwide |
| `granularity` | No | `daily`, `weekly`, `monthly` (default: `monthly`) |
| `device_type` | No (iOS unified) | `total`, `iphone`, `ipad` |
| `use_publisher_v2026` | No (unified) | Boolean; enables company tree hierarchy |

**Response key fields:** `app_id`, `date`, `country`, `units` (downloads), `revenue`

---

### 4. Active Users (DAU / WAU / MAU)

**`GET /v1/{os}/usage/active_users`**

Returns daily, weekly, or monthly active users.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated app IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `granularity` | Yes | `daily`, `weekly`, `monthly` |
| `countries` | No | Comma-separated country codes |

**Response key fields:** `app_id`, `date`, `country`, `dau` / `wau` / `mau`

---

### 5. Category Ranking History

**`GET /v1/{os}/category/category_history`**

Returns historical category chart ranking for an app.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `country` | Yes | ISO country code |
| `chart_type` | Yes | `free`, `paid`, `grossing` |
| `category` | No | Category ID; defaults to app's primary category |
| `device_type` | No (iOS) | `total`, `iphone`, `ipad` |

**Response key fields:** `date`, `rank`, `category`, `chart_type`

---

### 6. Category Ranking Summary (Today)

**`GET /v1/{os}/category/category_ranking_summary`**

Returns today's ranking position across all categories for an app.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `country` | Yes | ISO country code |

---

### 7. Ad Intel — Creative Gallery

**`GET /v1/{os}/ad_intel/creatives`**

Returns a list of ad creatives with share-of-voice data.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated app IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `networks` | No | Comma-separated network names |
| `countries` | No | Comma-separated country codes |
| `creative_type` | No | `video`, `image`, `html` |
| `limit` | No | Max creatives to return |
| `page` | No | Pagination offset |

**Response key fields:** `creative_id`, `app_id`, `network`, `creative_type`, `first_seen`, `last_seen`, `sov_share`, `creative_url`, `publisher_count`, `country_count`

> The `count` field in the response body is the total creative count — useful as a lightweight UA-activity proxy without fetching all creatives.

---

### 8. Ad Intel — Network Analysis (SOV Time Series)

**`GET /v1/{os}/ad_intel/network_analysis`**

Returns share-of-voice time series per network. **Max 5 `app_ids` per request.**

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Max 5 |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `networks` | No | Comma-separated network names |
| `countries` | No | Comma-separated country codes |
| `granularity` | No | `daily`, `weekly`, `monthly` |

**Response key fields:** `app_id`, `date`, `network`, `sov`

---

### 9. Ad Intel — Network Analysis Rank

**`GET /v1/{os}/ad_intel/network_analysis/rank`**

Returns advertiser rank among peers on a given network. Only supports `day` and `week` granularity.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated app IDs |
| `date` | Yes | `YYYY-MM-DD` |
| `network` | Yes | Single network name |
| `granularity` | Yes | `day` or `week` only |
| `country` | No | ISO country code |

---

### 10. Downloads by Sources (Channel Breakdown)

**`GET /v1/{os}/downloads_by_sources`**

Returns download breakdown by acquisition channel. **Requires Unified app IDs. Does not include China data.**

| Param | Required | Notes |
|-------|----------|-------|
| `unified_app_ids` | Yes | Unified hex IDs only |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |
| `granularity` | No | `monthly` (default) |

**Response key fields:** `unified_app_id`, `date`, `country`, `organic`, `paid`, `search_organic`, `search_paid`, `browse`, `referral` — all as absolute counts and as fractions

---

### 11. App Update History

**`GET /v1/{os}/app_update/get_app_update_history`**

Returns a timeline of app version releases.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `os` | Yes (path) | `ios` or `android` |

**Response key fields:** `version`, `release_date`, `what's_new`, `minimum_os_version`, `file_size`

---

### 12. Version History

**`GET /v1/{os}/apps/version_history`**

Returns historical version metadata for an app.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |

**Response key fields:** `version`, `release_date`, `whats_new`

---

## Part 1 — Consumer Intelligence

### 13. Churn Analysis (Android only)

**`GET /v1/{os}/consumer_intel/churn_analysis`**

Returns churn rate for an app. Android only.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Android package name |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |
| `granularity` | No | `monthly` |

**Response key fields:** `date`, `churn_rate`, `churn_count`

---

### 14. Churn Analysis Cohorts (Android only)

**`GET /v1/{os}/consumer_intel/churn_analysis/cohorts`**

Returns peer apps used for churn benchmarking.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Android package name |
| `country` | No | ISO country code |

---

### 15. Cohort Retention (Android only)

**`GET /v1/{os}/consumer_intel/cohort_retention`**

Returns cohort-based retention curves. Android only.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Android package name |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |

---

### 16. Cohort Retention — Available Cohorts (Android only)

**`GET /v1/{os}/consumer_intel/cohort_retention/cohorts`**

Returns list of available cohort apps for retention benchmarking.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Android package name |

---

### 17. Usage Demographics

**`GET /v1/{os}/usage/demographics`**

Returns age and gender breakdown of app users.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated app IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |

**Response key fields:** `app_id`, `date`, `age_group`, `gender`, `percentage`

---

### 18. Session Metrics (Non-Unified)

**`GET /v1/apps/timeseries`**

Returns session-level engagement metrics for iOS or Android apps.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated iOS or Android app IDs |
| `metric` | Yes | `time_spent`, `session_duration`, `session_count`, `total_time_spent`, `total_session_count` |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `granularity` | No | `daily`, `weekly`, `monthly` |
| `countries` | No | Comma-separated country codes |

**Response key fields:** `app_id`, `date`, `country`, metric value

---

### 19. Session Metrics (Unified)

**`GET /v1/apps/timeseries/unified_apps`**

Same as `/v1/apps/timeseries` but accepts unified app IDs.

| Param | Required | Notes |
|-------|----------|-------|
| `unified_app_ids` | Yes | Comma-separated unified hex IDs |
| `metric` | Yes | Same options as non-unified |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `granularity` | No | `daily`, `weekly`, `monthly` |
| `countries` | No | Comma-separated country codes |

---

### 20. Engagement Insights

**`GET /v1/{os}/consumer_intel/engagement_insights`**

Returns engagement trend metrics (visits frequency, stickiness, etc.).

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `country` | No | ISO country code |

---

### 21. Engagement Insights — Available Cohorts

**`GET /v1/{os}/consumer_intel/engagement_insights/cohorts`**

Returns peer cohorts available for engagement benchmarking.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |

---

### 22. Time of Day Usage

**`GET /v1/{os}/consumer_intel/time_of_day`**

Returns usage distribution by hour of day.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `country` | No | ISO country code |

---

### 23. Time of Day — Available Cohorts

**`GET /v1/{os}/consumer_intel/time_of_day/cohorts`**

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |

---

### 24. Power User Curve

**`GET /v1/{os}/consumer_intel/power_user_curve`**

Returns distribution of days used per month (power user curve).

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `country` | No | ISO country code |

---

### 25. Power User Curve — Available Cohorts

**`GET /v1/{os}/consumer_intel/power_user_curve/cohorts`**

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |

---

### 26. Cohort Engagement

**`GET /v1/{os}/consumer_intel/cohort_engagement`**

Returns cohort-based engagement comparison across peer apps.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `country` | No | ISO country code |

---

### 27. Cohort Engagement — Available Cohorts

**`GET /v1/{os}/consumer_intel/cohort_engagement/cohorts`**

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |

---

### 28. Cross-App User Overlap

**`GET /v1/unified/app_overlap`**

Returns estimated percentage of users shared between app pairs.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Exactly 2 unified app IDs (comma-separated) |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |

---

## Part 1 — Facets / Metrics Endpoints (App Analysis)

All facets endpoints use: **`GET /v1/facets/metrics`**

The `bundle` or `metric` query param selects the data product. Multiple values are passed comma-separated.

---

### 29. Install Base & Penetration

**`GET /v1/facets/metrics?install_base`**

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `install_base` |
| `breakdown` | Yes | e.g. `date,app_id` |
| `app_ids` or `unified_app_ids` | Yes (one) | Entity filter |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `regions` | No | Comma-separated region codes |

**Available metrics:** `est_install_base`, `est_install_penetration`, `est_open_rate`, `est_usage_penetration`

**Available breakdowns:** `date`, `app_id`, `unified_app_id`, `region`

---

### 30. SDK Analysis Time Series

**`GET /v1/facets/metrics?sdk_analysis`**

Returns time-series metrics for a specific SDK across the app market.

| Param | Required | Notes |
|-------|----------|-------|
| `metric` | Yes | One or more from the list below (comma-separated) |
| `breakdown` | Yes | e.g. `date` |
| `sdk_ids` | Yes | Numeric SDK IDs (e.g. `60100000000400` for Firebase) |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `regions` | No | Comma-separated country codes |
| `categories` | No | Category IDs |

**Available metrics:**
- `sdk_apps_detected` — number of apps with SDK installed
- `sdk_installs` — new installs of SDK into apps
- `sdk_uninstalls` — removals of SDK from apps
- `sdk_apps_detected_share` — market share by app count
- `est_sdk_downloads` — estimated consumer downloads for apps using this SDK
- `est_sdk_downloads_share` — share of total downloads

---

### 31. SDK List of Apps

**`GET /v1/facets/metrics?sdk_list_of_apps`**

Returns list of apps that have a given SDK installed.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `sdk_overview_app_data` |
| `breakdown` | Yes | `app_id` or `unified_app_id` |
| `sdk_ids` | Yes | Numeric SDK IDs |
| `date` | Yes | `YYYY-MM-DD` (single date) |
| `regions` | No | Comma-separated country codes |
| `categories` | No | Category IDs |
| `limit` | No | Max results |
| `page` | No | Pagination |

**Response key fields:** `app_id`, `unified_app_id`, `sdk_detected_date`, `app_name`, `publisher_name`, `category`, `monthly_downloads`

---

### 32. SDK Summary Metrics

**`GET /v1/sdk/summary_metrics`**

Returns metadata and performance summary for SDKs. **Max 100 `sdk_ids` per request.**

| Param | Required | Notes |
|-------|----------|-------|
| `sdk_ids` | Yes | Numeric SDK IDs; max 100 |
| `date` | No | `YYYY-MM-DD`; defaults to most recent available |

**Response key fields:** `sdk_id`, `sdk_name`, `sdk_category`, `company_name`, `website`, `sdk_apps_detected`, `est_sdk_downloads`, `sdk_apps_detected_share`, `description`

---

### 33. Metro-Level Active Users

**`GET /v1/facets/metrics?metro_active_users`**

Returns active users broken down by US metro area.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `metro_active_users` |
| `breakdown` | Yes | e.g. `date,metro` |
| `app_ids` or `unified_app_ids` | Yes (one) | Entity filter |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `granularity` | Yes | `weekly` or `monthly` |

> US metros only. Week and month granularity supported.

---

### 34. State-Level Active Users

**`GET /v1/facets/metrics?state_active_users`**

Returns active users broken down by US state.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `state_active_users` |
| `breakdown` | Yes | e.g. `date,state` |
| `app_ids` or `unified_app_ids` | Yes (one) | Entity filter |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `granularity` | Yes | `weekly` or `monthly` |

---

### 35. Retention Metrics

**`GET /v1/facets/metrics?retention`**

Returns cohort retention estimates. Calculated at monthly granularity (install day/week must fall within the specified month).

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `retention_daily`, `retention_weekly`, or `retention_monthly` |
| `breakdown` | Yes | Comma-separated; see combinations below |
| `app_ids` or `unified_app_ids` | Yes (exactly one) | Entity filter — do not combine |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `regions` | No | Comma-separated region codes; worldwide if omitted |

**Bundle → retention periods:**
| Bundle | Periods available |
|--------|-------------------|
| `retention_daily` | D1–D7, D14, D30, D60, D90, D180, D360 |
| `retention_weekly` | W1–W10, W20, W52 |
| `retention_monthly` | M1–M12 |

**Metric naming:** `est_retention_<period>` — e.g. `est_retention_d7`, `est_retention_w5`, `est_retention_m3`

**Supported breakdown combinations:**
- `date,unified_app_id,app_id`
- `date,unified_app_id`
- `date,app_id`
- `unified_app_id,app_id`
- `unified_app_id`
- `app_id`
- `date`

> Breakdown by region is not supported. Regional filter narrows scope but does not add a region dimension to results.

---

---

## Part 2: Custom Fields / Usage Intelligence API (`custom_fields_metadata.yml`)

### 1. Search Entities

**`GET /v1/{os}/search_entities`**

Searches for apps or publishers by name string.

| Param | Required | Notes |
|-------|----------|-------|
| `entity_type` | Yes | `app` or `publisher` |
| `term` | Yes | Search term |
| `os` | Yes (path) | `ios`, `android`, or `unified` |
| `limit` | No | Max results (default 10) |
| `page` | No | Pagination |

**Response key fields:** `app_id`, `name`, `publisher_name`, `icon_url`, `category`

---

### 2. Bulk App IDs by Category / Date

**`GET /v1/{os}/apps/app_ids`**

Returns up to 10,000 app IDs in a category as of a given date.

| Param | Required | Notes |
|-------|----------|-------|
| `os` | Yes (path) | `ios` or `android` |
| `category_id` | Yes | Category ID integer |
| `date` | Yes | `YYYY-MM-DD` |
| `limit` | No | Max 10,000 |
| `page` | No | Pagination |

---

### 3. Publisher Apps

**`GET /v1/{os}/publisher/publisher_apps`**

Returns up to 100 apps for a publisher.

| Param | Required | Notes |
|-------|----------|-------|
| `publisher_id` | Yes | Publisher ID |
| `os` | Yes (path) | `ios` or `android` |
| `limit` | No | Max 100 |

---

### 4. Unified Publisher + All Apps

**`GET /v1/unified/publishers/apps`**

Returns a unified publisher record plus all associated apps across iOS and Android.

| Param | Required | Notes |
|-------|----------|-------|
| `publisher_ids` | Yes | Comma-separated unified publisher IDs |
| `use_publisher_v2026` | No | Boolean; enables company tree hierarchy |

**Response key fields:** `publisher_id`, `publisher_name`, `ios_apps`, `android_apps` (each as arrays of app objects)

---

### 5. Resolve Unified App IDs

**`GET /v1/unified/apps`**

Resolves native iOS/Android app IDs to unified cross-platform IDs.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated native app IDs (iOS or Android) |

**Response key fields:** `app_id`, `unified_app_id`, `name`, `ios_app_id`, `android_app_id`

---

### 6. Resolve Unified Publisher IDs

**`GET /v1/unified/publishers`**

Resolves native publisher IDs to unified publisher IDs.

| Param | Required | Notes |
|-------|----------|-------|
| `publisher_ids` | Yes | Comma-separated native publisher IDs |

---

### 7. Custom Fields for Apps

**`GET /v1/app_tag/tags_for_apps`**

Returns all global/custom field values assigned to specified apps. **Max 100 app IDs per request.** Apps without any matching tags are omitted entirely from the response.

**Corrected params (verified against real yaml + live testing 2026-07-02/03)** — the earlier version of this doc was missing a required param and had it failing with `422 "Fields or field categories must be requested"`:

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated app IDs (iTunes numeric or Android package name); max 100 |
| `field_categories[]` | **Yes*** | Repeat the param once per category. **Must include at least one of `fields[]` or `field_categories[]` — leaving both empty/omitted returns a 422, it does NOT default to "all".** Confirmed both omitting the param and passing `field_categories[]=` (empty string) fail. |
| `fields[]` | No | Specific field names instead of/in addition to whole categories |

**Valid `field_categories[]` enum (15 values — confirmed complete, does NOT include `app_iq` or `sdk_types` despite those existing as categories in `categories.json`; use `fields[]` with exact field names to get App IQ / SDK tags):**
`active_users`, `advertising`, `app_content`, `app_metadata`, `app_ratings`, `app_release_and_updates`, `custom_fields`, `demographics`, `developer_integrations`, `downloads`, `gaming`, `monetization`, `publisher_details`, `retention`, `revenue`

**Response:** `{"data": [{"app_id", "tags": [{"name", "value", "exact_value"}]}]}`. `value` is a humanized/bucketed string (e.g. `"50 - 59%"`, `"10M - 100M"`); `exact_value` is the precise raw value — use `exact_value` for any numeric filtering/sorting.

**To request everything, pass all 15 category values explicitly** (there is no shorthand "all").

---

### 8. Apps by Custom Field Value

**`GET /v1/app_tag/apps`**

Returns all apps matching a single global/custom field name+value. Paginated via `last_known_id`.

**Corrected params** (the earlier `field_name`/`field_value` names in this doc were wrong — verified against real yaml):

| Param | Required | Notes |
|-------|----------|-------|
| `name` | Yes | Exact field name (e.g. `"Contains Ads"`, `"Monetization: Ads"`) |
| `value` | Yes | Exact value to match (get valid values from `fields_values`, item 17 below) |
| `global` | Yes | `true` for ST built-in fields; `false` for your org's own custom tags |
| `app_id_type` | Yes | `itunes`, `android`, or `unified` |
| `custom_fields_filter_id` | No | Combine with a saved filter (see item 15) instead of a single name/value pair |
| `last_known_id` | No | Pagination cursor; pass the last returned ID |

**Response (non-unified):** `{"last_known_id", "app_ids": [...]}`. **Response (unified):** `{"last_known_id", "data": [{"unified_app_id", "itunes_app_ids": [...], "android_app_ids": [...]}]}`.

---

### Confirmed field coverage gaps — "does this app show ads" (verified 2026-07-03)

Two fields look like they mean "this app displays ads to users," but their real coverage is narrower than the name suggests. Verified via `/v1/app_tag/apps` (name/value scan across the whole account) **and** `/v1/app_tag/tags_for_apps` (direct inspection of specific apps, both gaming and non-gaming):

| Field | Category | Real coverage |
|-------|----------|----------------|
| `Contains Ads` | `advertising` | **Effectively unpopulated for iOS, for both games and non-games.** `app_id_type=itunes` returns `[]` for both `value=true` AND `value=false` (i.e. not "mostly false" — literally no iOS records at all). Scanning 96,525 `unified` records tagged `Contains Ads=true` found **zero** with a non-empty `itunes_app_ids`. Direct tag lookups on 5 known iOS apps (2 ad-supported non-games + 3 apps spanning game/entertainment/utilities) never returned this field. Works fine for Android (`app_id_type=android` returns tens of thousands of real results, e.g. Indeed, LinkedIn, UPS in the Android Business category). |
| `Monetization: Ads` | `gaming` | **Games only.** Confirmed populated (`True`) for an iOS game; confirmed **absent entirely** (not `false` — the key doesn't appear) on two non-game iOS apps (Entertainment and Utilities categories) in the same batch request. |
| `Advertises on <Network>` family (AdMob, Facebook, TikTok, etc.) | `advertising` | **Not the same concept** — this measures whether the app itself *buys* UA ads on that network, not whether it *displays* ads to monetize. Both non-gaming test apps had many of these set to `Active` while having no `Contains Ads`/`Monetization: Ads` tag at all. Don't substitute this for an ads-monetization flag. |

**Net conclusion: there is currently no reliable "does this app show ads" signal for iOS non-gaming apps** via ST's custom-fields system. For that segment, keep using internal BQ `m.sensortower.product.has_ads` as the existing pipeline already does. For iOS games, use `Monetization: Ads`. For Android (any category), use `Contains Ads`.

---

### 9. List All Custom Fields

**`GET /v1/custom_field/custom_field_list`**

Returns metadata for all custom fields defined in the account.

No additional params required beyond `auth_token`.

**Response key fields:** `field_name`, `field_type`, `description`, `value_count`

---

### 10. Add Tag to App

**`POST /v1/app_tag/add_tag_for_app`**

Assigns a custom field value to an app.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `field_name` | Yes | Custom field name |
| `field_value` | Yes | Value to assign |

---

### 11. Edit Tag Value for App

**`POST /v1/app_tag/edit_tag`**

Updates the value of a custom field for a specific app.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `field_name` | Yes | Custom field name |
| `field_value` | Yes | New value |

---

### 12. Remove Tag from App

**`POST /v1/app_tag/remove_tag_for_app`**

Removes a custom field value from one or more apps.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | One or more app IDs (array or comma-separated) |
| `field_name` | Yes | Custom field name |

---

### 13. Bulk Rename Tag Values

**`POST /v1/custom_field/change_all_values_matching`**

Renames all occurrences of a custom field value across all apps.

| Param | Required | Notes |
|-------|----------|-------|
| `field_name` | Yes | Custom field name |
| `old_value` | Yes | Current value to replace |
| `new_value` | Yes | New value |

---

### 14. Delete Custom Field (DESTRUCTIVE)

**`POST /v1/custom_field/remove_custom_field`**

Permanently deletes a custom field and all its values across all apps.

| Param | Required | Notes |
|-------|----------|-------|
| `field_name` | Yes | Custom field to delete |

> **Warning:** This is irreversible. All tag assignments for this field are deleted.

---

### 15. Create Reusable Filter

**`POST /v1/custom_fields_filter`**

Creates a saved filter combining one or more global/custom field criteria. Returns a `custom_fields_filter_id` reusable as a query param on several other endpoints (see below). **Verified against the actual swagger spec + live testing on 2026-07-02** — this is NOT a `{field_name, operator, values}` shape (there is no operator concept).

Request body (`application/json`):
```json
{
  "custom_fields": [
    {
      "name": "Monetization: Ads",
      "global": true,
      "values": ["True"],
      "exclude": false
    }
  ]
}
```

| Field (per item in `custom_fields[]`) | Required | Notes |
|------|----------|-------|
| `name` | Yes | Exact field name string (from `categories.json` or `fields_values`) |
| `global` | Yes | `true` for ST built-in fields (e.g. "Publisher Country"); `false` for your org's own custom tags |
| `values` | Yes | Array of strings to match. Multiple values = OR. Multiple `custom_fields` entries = AND. |
| `exclude` | No | `false` (default) = include only these values (≈ IN). `true` = exclude these values (≈ NOT IN) |

**Response:** `{"custom_fields_filter_id": "<id>"}`

**Confirmed usable via `custom_fields_filter_id` query param on:**
- `GET /v1/app_tag/apps`
- `GET /v1/{os}/sales_report_estimates_comparison_attributes`
- `GET /v1/{os}/usage/active_users` (top-apps variant)
- `GET /v1/{os}/top_and_trending/...` (advertiser/publisher ranking)
- If `os=unified`, also requires `custom_tags_mode` param.

---

### 16. Get Filter by ID

**`GET /v1/custom_fields_filter/{id}`**

Returns the definition of a saved filter.

| Param | Required | Notes |
|-------|----------|-------|
| `id` | Yes (path) | Filter ID from creation |

---

### 17. List All Field Names and Values

**`GET /v1/custom_fields_filter/fields_values`**

Returns the exact possible `values` for one field (or all fields if `term` omitted). **Always call this before building a filter** — value strings must match exactly (e.g. countries are full names like `"China"`, `"Hong Kong"`, `"Macau"`, `"Taiwan"` — NOT ISO codes).

| Param | Required | Notes |
|-------|----------|-------|
| `term` | No | Field name to look up (e.g. `"Publisher Country"`) |

**Response:** `{"custom_fields": [{"name", "global", "values": [...]}]}`

---

### 18. List All Field Categories (undocumented in swagger, but live and useful)

**`GET https://app.sensortower.com/api/custom_field/categories.json`**

Not in `custom_fields_metadata.yml`'s path list, but a real, working endpoint (auth via `auth_token` query param, hosted on `app.sensortower.com` not `api.sensortower.com`). Returns every filterable field name grouped by category — this is the fastest way to discover what's filterable without guessing.

**Top-level categories (verified 2026-07-02):** `active_users`, `advertising`, `app_content`, `app_iq`, `app_metadata`, `app_ratings`, `app_release_and_updates`, `demographics`, `developer_integrations`, `downloads`, `gaming`, `monetization`, `publisher_details`, `retention`, `revenue`, `sdk_types`

**Fields relevant to prospect/cross-sell filtering:**

| Field | Category | Values | Notes |
|-------|----------|--------|-------|
| `Contains Ads` | `advertising` | `true` / `false` | **Android-only coverage** — confirmed empty for all tested iOS categories/apps. Works via `app_id_type=android` on `/v1/app_tag/apps`. |
| `Monetization: Ads` | `gaming` | `"True"` / `"False"` (capitalized) | Cross-platform but **games only**. This is the field that's actually populated for iOS games — use this instead of `Contains Ads` for iOS gaming apps. |
| `Publisher Country` | `publisher_details` | Full country names, e.g. `"China"`, `"Hong Kong"`, `"Macau"`, `"Taiwan"`, `"India"`, `"US"` | Not ISO codes. |
| `Most Popular Country by Downloads` | `downloads` | Full country names | Use `exclude: true` to filter OUT a country (e.g. China/India). |
| `Store Category` | `app_metadata` | App-store category names, e.g. `"Games"`, `"Social Networking"`, `"Business"`, `"Utilities"`, `"Photo & Video"`, etc. (both iOS- and Android-style names mixed) | Use this to filter by category **inside** the custom-fields-filter system, as an alternative/complement to the numeric `category` param on ranking endpoints. Set `exclude: true` with `values: ["Games"]` to scope to non-gaming apps in one shot. |
| `Primary Category` | `app_metadata` | (listed in `categories.json` but `fields_values` returned empty — **not usable as a filter value list**, confirmed 2026-07-02) | Do not use; use `Store Category` instead. |

**No confirmed "contains ads" signal exists for iOS non-gaming apps** via this API (tested empty across categories 6000/6002/6007/6018). For iOS non-gaming ads detection, fall back to internal BQ `m.sensortower.product` (`has_ads`) as already used in the pipeline, rather than this custom-fields system.

---

---

## Part 3: Market Analysis / Ad Intelligence API (`market_analysis.yml`)

### 1. Top Charts

**`GET /v1/{os}/ranking`**

Returns the app store top chart for a given category, chart type, and country.

| Param | Required | Notes |
|-------|----------|-------|
| `category` | Yes | Category ID |
| `chart_type` | Yes | `free`, `paid`, `grossing` |
| `country` | Yes | ISO country code |
| `date` | No | `YYYY-MM-DD`; defaults to most recent |
| `device_type` | No (iOS) | `total`, `iphone`, `ipad` |
| `limit` | No | Number of results (max 200) |
| `os` | Yes (path) | `ios` or `android` |

**Response key fields:** `rank`, `app_id`, `name`, `publisher_name`, `icon_url`, `units` (downloads estimate)

---

### 2. Top Apps by Downloads / Revenue

**`GET /v1/{os}/sales_report_estimates_comparison_attributes`**

Returns ranked list of top apps by downloads or revenue, with support for absolute, delta, and transformed-delta ranking modes.

| Param | Required | Notes |
|-------|----------|-------|
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `country` | Yes | ISO country code |
| `measure` | Yes | `units` (downloads) or `revenue` |
| `comparison_attribute` | Yes | `absolute`, `delta`, `transformed_delta` |
| `category` | No | Category ID |
| `device_type` | No (iOS) | `total`, `iphone`, `ipad` |
| `limit` | No | Max results |
| `entities` | No (unified) | Comma-separated unified app IDs to include |

**Response key fields:** `app_id`, `name`, `publisher_name`, `measure_value`, `comparison_value`, `rank`

---

### 3. Top Apps by Active Users

**`GET /v1/{os}/top_and_trending/active_users`**

Returns top apps ranked by DAU, WAU, or MAU.

| Param | Required | Notes |
|-------|----------|-------|
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `country` | Yes | ISO country code |
| `granularity` | Yes | `daily`, `weekly`, `monthly` |
| `category` | No | Category ID |
| `limit` | No | Max results |

**Response key fields:** `app_id`, `name`, `publisher_name`, `active_users`, `rank`

---

### 4. Top Publishers

**`GET /v1/{os}/top_and_trending/publishers`**

Returns top publishers ranked by downloads or revenue.

| Param | Required | Notes |
|-------|----------|-------|
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `country` | Yes | ISO country code |
| `measure` | Yes | `units` or `revenue` |
| `category` | No | Category ID |
| `limit` | No | Max results |

**Response key fields:** `publisher_id`, `publisher_name`, `measure_value`, `rank`, `app_count`

---

### 5. Store Summary (DEPRECATED)

**`GET /v1/{os}/store_summary`**

Returns category-level download/revenue summary. **Deprecated — use facets endpoints instead.**

---

### 6. Games Breakdown (DEPRECATED)

**`GET /v1/{os}/games_breakdown`**

Returns game sub-category breakdown. **Deprecated — use facets endpoints instead.**

---

### 7. Top Advertisers / Publishers (Ad Intel)

**`GET /v1/{os}/ad_intel/top_apps`**

Returns top advertising apps or top publishers by impression share.

| Param | Required | Notes |
|-------|----------|-------|
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `role` | Yes | `advertisers` or `publishers` |
| `networks` | No | Comma-separated network names (includes `Apple Search Ads`) |
| `countries` | No | Comma-separated country codes |
| `category` | No | Category ID |
| `limit` | No | Max results |
| `creative_type` | No | `video`, `image`, `html` |

**Response key fields:** `app_id`, `name`, `publisher_name`, `sov_share`, `rank`, `network_count`, `creative_count`

---

### 8. Advertiser / Publisher Rank (Ad Intel Search)

**`GET /v1/{os}/ad_intel/top_apps/search`**

Returns the rank of a specific app among all advertisers or publishers.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `role` | Yes | `advertisers` or `publishers` |
| `networks` | No | Comma-separated network names |
| `countries` | No | Comma-separated country codes |

**Response key fields:** `app_id`, `rank`, `sov_share`, `total_advertisers`

---

### 9. Top Creatives (Ad Intel)

**`GET /v1/{os}/ad_intel/creatives/top`**

Returns the top-performing creatives for a given category, network, and time period.

| Param | Required | Notes |
|-------|----------|-------|
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `network` | Yes | Single network name |
| `category` | No | Category ID |
| `countries` | No | Comma-separated country codes |
| `creative_type` | No | `video`, `image`, `html` |
| `limit` | No | Max results |

**Response key fields:** `creative_id`, `app_id`, `app_name`, `network`, `creative_type`, `sov_share`, `creative_url`, `first_seen`, `last_seen`

---

## Part 3 — Facets / Metrics Endpoints (Market Analysis)

### 10. Market Size: Downloads & Revenue

**`GET /v1/facets/metrics?market_size_downloads_and_revenue`**

Returns market-level download and revenue estimates.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `mobile_store_estimates` |
| `breakdown` | Yes | e.g. `date`, `date,region`, `date,os` |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `regions` | No | Comma-separated region codes |
| `categories` | No | Category IDs |
| `os` | No | `ios`, `android`, or omit for both |

**Available metrics:** `est_mobile_downloads`, `est_mobile_revenue`, `est_mobile_rpd` (revenue per download)

---

### 11. Market Size: Usage

**`GET /v1/facets/metrics?market_size_usage`**

Returns market-level session and time-spent estimates.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `mobile_usage_estimates` |
| `breakdown` | Yes | e.g. `date`, `date,region` |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `regions` | No | Comma-separated region codes |
| `categories` | No | Category IDs |

**Available metrics:** `est_mobile_time_spent` (avg minutes/user/day), `est_mobile_total_time_spent` (aggregate)

---

### 12. Market Size: Impression Share

**`GET /v1/facets/metrics?market_size_impression_share`**

Returns market-level ad impression share by network.

| Param | Required | Notes |
|-------|----------|-------|
| `metric` | Yes | `est_mobile_impression_share` |
| `breakdown` | Yes | e.g. `date,network` |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `network` | No | Filter to specific network(s); adds `network` as available breakdown dimension |
| `regions` | No | Comma-separated region codes |

---

---

## Part 4: Store Intelligence API (`store_marketing.yml`)

### 1. Featured Today Stories (iOS only)

**`GET /v1/ios/featured/today/stories`**

Returns App Store "Today" editorial stories featuring apps.

| Param | Required | Notes |
|-------|----------|-------|
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |
| `limit` | No | Max results |

**Response key fields:** `story_id`, `title`, `featured_apps` (array of app_ids), `countries`, `date`

---

### 2. Featured Apps / Games

**`GET /v1/ios/featured/apps`**

Returns apps featured in a specific App Store category placement.

| Param | Required | Notes |
|-------|----------|-------|
| `category` | Yes | Category ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |

**Response key fields:** `app_id`, `name`, `position`, `placement_type`, `date`, `country`

---

### 3. Featured Creatives

**`GET /v1/{os}/featured/creatives`**

Returns creative assets used in featured placements, with position and download data.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated app IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |

**Response key fields:** `app_id`, `date`, `country`, `position`, `placement_type`, `creative_url`, `est_downloads`

---

### 4. Featured Impacts

**`GET /v1/{os}/featured/impacts`**

Returns the download lift associated with each featured placement.

| Param | Required | Notes |
|-------|----------|-------|
| `app_ids` | Yes | Comma-separated app IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |

**Response key fields:** `app_id`, `date`, `country`, `placement_type`, `featured_days`, `est_download_lift`, `est_download_lift_pct`

---

## Part 4 — Facets / Metrics Endpoints (Store Intelligence)

### 5. ASO Keyword Research

**`GET /v1/facets/metrics?aso_keyword_research`**

Returns detailed keyword intelligence for a single keyword in a single region.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `aso_keyword_research` |
| `keyword` | Yes | Single keyword string |
| `region` | Yes | Single ISO country code |
| `os` | Yes | `ios` or `android` |
| `app_ids` | No | App IDs to include rank data for |

**Response key fields:** `keyword`, `traffic_score`, `difficulty_score`, `opportunity_score`, `total_apps`, `top_apps` (array)

---

### 6. ASO Keyword Time Series

**`GET /v1/facets/metrics?aso_timeseries`**

Returns time-series ASO metrics for up to 100 keywords.

| Param | Required | Notes |
|-------|----------|-------|
| `metric` | Yes | One or more from list below |
| `breakdown` | Yes | e.g. `date,keyword` |
| `app_ids` | Yes | App IDs to track |
| `keywords` | Yes | Up to 100 keywords (comma-separated) |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `region` | Yes | Single ISO country code |

**Available metrics:**
- `keyword_rank` — app's rank for the keyword
- `keyword_traffic` — traffic score
- `est_keyword_downloads` — estimated downloads attributed to this keyword
- `keyword_opportunity_score` — opportunity index
- `keyword_app_count` — total apps competing for keyword

---

### 7. ASO Rank Overview

**`GET /v1/facets/metrics?aso_rank_overview`**

Returns a distribution of an app's keyword ranks across rank buckets.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `aso_rank_overview` |
| `breakdown` | Yes | e.g. `date` |
| `app_ids` | Yes | App IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `region` | Yes | Single ISO country code |

**Rank buckets in response:** rank 1, 2–3, 4–5, 6–10, 11–20, 21+

---

### 8. ASO Top Keywords for App

**`GET /v1/facets/metrics?aso_top_keywords`**

Returns the top-ranked keywords for an app. **Max 200 keywords returned.**

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `aso_top_keywords` |
| `breakdown` | Yes | `keyword` or `keyword,date` |
| `app_ids` | Yes | App IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `region` | Yes | Single ISO country code |
| `order_by` | No | Field to sort by (e.g. `est_keyword_downloads`) |
| `limit` | No | Max keywords; capped at 200 |

---

### 9. Get Reviews

**`GET /v1/{os}/review/get_reviews`**

Returns raw app store reviews with rich filtering. **Max 200 reviews per request.**

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |
| `countries` | No | Comma-separated country codes |
| `languages` | No | Comma-separated language codes |
| `rating_filters` | No | Array of star ratings (1–5) |
| `search_terms` | No | Keywords to filter review text |
| `tags` | No | Custom review tags |
| `versions` | No | App versions to filter |
| `sentiments` | No | `happy`, `mixed`, `neutral`, `unhappy` |
| `username` | No | Filter by reviewer username |
| `limit` | No | Max 200 |
| `page` | No | Pagination |

**Response key fields:** `review_id`, `author`, `title`, `body`, `rating`, `date`, `country`, `version`, `sentiment`, `tags`

---

### 10. App History Summary (DEPRECATED)

**`GET /v1/{os}/review/app_history_summary`**

Deprecated. Use the `reviews_by_rating` facets endpoint instead.

---

### 11. Get Ratings (DEPRECATED)

**`GET /v1/{os}/review/get_ratings`**

Deprecated. Use the `ratings` facets endpoint instead.

---

### 12. Ratings Metrics

**`GET /v1/facets/metrics?ratings`**

Returns star rating counts and averages. **Supports up to 1,000 `app_ids` per request.**

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `ratings_incremental` or `ratings_cumulative` |
| `breakdown` | Yes | See supported combinations below |
| `app_ids` | Yes | Up to 1,000 app IDs |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |

**Bundle meanings:**
- `ratings_incremental` — new ratings in the period
- `ratings_cumulative` — all-time ratings as of end_date

**Supported breakdown combinations:** `app_id`, `app_id,date`, `region`, `region,date`, `app_version`

**Response key fields:** `app_id`, `date`, `region`, `rating_avg`, `rating_count`, `star_1` through `star_5`

---

### 13. Reviews by Rating

**`GET /v1/facets/metrics?reviews_by_rating`**

Returns review volume broken down by star rating. Single app per request.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `reviews_by_rating` |
| `breakdown` | Yes | See supported combinations below |
| `app_ids` | Yes | Single app ID only |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |

**Supported breakdown combinations:** `date,review_rating`, `region,review_rating`, `language,review_rating`, `app_version,review_rating`

**Response key fields:** `date`, `region`, `language`, `app_version`, `review_rating`, `review_count`

---

### 14. Reviews by Sentiment

**`GET /v1/facets/metrics?reviews_by_sentiment`**

Returns review volume broken down by sentiment classification.

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `reviews_by_sentiment` |
| `breakdown` | Yes | e.g. `date,sentiment` |
| `app_ids` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |

**Sentiment values:** `happy`, `mixed`, `neutral`, `unhappy`

---

### 15. Reviews by Tag

**`GET /v1/facets/metrics?reviews_by_tag`**

Returns review volume broken down by review tag (topic classification).

| Param | Required | Notes |
|-------|----------|-------|
| `bundle` | Yes | `reviews_by_tag` |
| `breakdown` | Yes | e.g. `date,tag` |
| `app_ids` | Yes | Single app ID |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |

---

### 16. Apple Search Ads — Apps for Keyword (iOS only)

**`GET /v1/ios/search_ads/apps`**

Returns apps that are running Apple Search Ads for a given keyword.

| Param | Required | Notes |
|-------|----------|-------|
| `keyword` | Yes | Keyword string |
| `country` | Yes | ISO country code |
| `date` | No | `YYYY-MM-DD`; defaults to most recent |

**Response key fields:** `app_id`, `name`, `publisher_name`, `position`, `impression_share`

---

### 17. Apple Search Ads — Keywords for App (iOS only)

**`GET /v1/ios/search_ads/terms`**

Returns Apple Search Ads keywords an app is bidding on.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | iOS numeric app ID |
| `country` | Yes | ISO country code |
| `start_date` | No | `YYYY-MM-DD` |
| `end_date` | No | `YYYY-MM-DD` |
| `limit` | No | Max results |

**Response key fields:** `keyword`, `impression_share`, `avg_position`, `first_seen`, `last_seen`

---

### 18. Apple Search Ads — SOV History (iOS only)

**`GET /v1/ios/search_ads/history`**

Returns share-of-voice time series for an app on Apple Search Ads.

| Param | Required | Notes |
|-------|----------|-------|
| `app_id` | Yes | iOS numeric app ID |
| `country` | Yes | ISO country code |
| `start_date` | Yes | `YYYY-MM-DD` |
| `end_date` | Yes | `YYYY-MM-DD` |

**Response key fields:** `date`, `impression_share`, `keyword_count`, `avg_position`

---

### 19. User Apps (DEPRECATED)

**`GET /v1/ios/ajax/user_apps`**

Deprecated internal endpoint. Do not use.

---

---

## Error Responses

| HTTP Status | Meaning |
|-------------|---------|
| `400` | Bad request — missing or invalid parameters |
| `401` | Unauthorized — invalid or missing `auth_token` |
| `403` | Forbidden — feature not included in subscription |
| `404` | Not found — app ID does not exist |
| `429` | Rate limit exceeded — back off and retry |
| `500` | Server error |

---

## Rate Limiting

- **Per-second limit:** 6 requests/second across the account
- **Monthly quota:** Tracked via `x-api-usage-count` and `x-api-usage-limit` response headers
- **Best practice:** Throttle to 5 req/s in production pipelines; implement exponential backoff on 429s

---

## Network Reference

Full list of ad networks tracked across Ad Intel endpoints:

```
Adcolony, Admob, Applovin, Apple Search Ads, BidMachine, Chartboost,
Digital Turbine, Facebook, InMobi, Instagram, Line, Meta Audience Network,
Mintegral, Moloco, Mopub, Pangle, Pinterest, Smaato, Snapchat,
Supersonic, Tapjoy, TikTok, Twitter, Unity, Verve, Vungle, Youtube
```

Note: `Apple Search Ads` appears in `top_apps` / `top_apps_search` but not in `creatives` or `network_analysis`.

---

## BQ Pipeline Architecture (LinglongLab)

Proposed pipeline for loading ST data into BQ for prospect scoring:

```
Cloud Scheduler (daily/weekly trigger)
    → Cloud Run job (Python)
        → SensorTower API (batched, throttled at 5 req/s)
        → BigQuery write (append or MERGE)
            ads-bpd-guard-china.sensortower_incept.*
```

### Recommended tables to build

| BQ Table | ST Endpoint | Refresh | Key columns |
|----------|-------------|---------|-------------|
| `st_creatives_count` | `/ad_intel/creatives` (read `count`) | Weekly | `app_id`, `period_start`, `creative_count` |
| `st_network_sov` | `/ad_intel/network_analysis` | Weekly | `app_id`, `network`, `month`, `sov` |
| `st_download_channels` | `/downloads_by_sources` | Monthly | `unified_app_id`, `month`, `paid_frac`, `organic_frac`, `paid_abs` |
| `st_app_metadata` | `/v1/{os}/apps` | Weekly | `app_id`, `publisher_name`, `category`, `rating`, `version` |
| `st_downloads_monthly` | `/sales_report_estimates` | Monthly | `app_id`, `month`, `country`, `downloads`, `revenue` |
| `st_sdk_tags` | `/app_tag/tags_for_apps` | Weekly | `app_id`, `field_name`, `field_value` |
| `st_active_users_mau` | `/usage/active_users` | Monthly | `app_id`, `month`, `country`, `mau` |
| `st_unified_id_map` | `/v1/unified/apps` | On-demand | `android_id`, `ios_id`, `unified_id` |

### Critical: Unified ID mapping

The `/downloads_by_sources` endpoint requires **Unified app IDs**. Build `st_unified_id_map` first, then JOIN on it for any channel-related queries.

### Prospect scoring query pattern

```sql
SELECT
    a.app_id,
    a.publisher_name,
    COALESCE(c.creative_count, 0)        AS creative_count,     -- UA activity proxy
    COALESCE(n.active_network_count, 0)  AS active_networks,    -- UA breadth
    COALESCE(d.paid_frac, 0)             AS paid_download_frac, -- paid UA signal
    COALESCE(s.sdk_count, 0)             AS sdk_count,          -- mediation openness
    a.monthly_downloads
FROM st_app_metadata a
LEFT JOIN st_creatives_count c USING (app_id)
LEFT JOIN (
    SELECT app_id, COUNT(DISTINCT network) AS active_network_count
    FROM st_network_sov
    WHERE sov > 0 AND month >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH), MONTH)
    GROUP BY 1
) n USING (app_id)
LEFT JOIN st_download_channels d ON d.unified_app_id = a.unified_app_id
    AND d.month = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
LEFT JOIN (
    SELECT app_id, COUNT(*) AS sdk_count
    FROM st_sdk_tags
    WHERE field_name LIKE 'has_sdk_%' AND field_value = 'true'
    GROUP BY 1
) s USING (app_id)
```
