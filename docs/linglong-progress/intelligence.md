# Linglong Lab · Intelligence — Progress Tracker

> Weekly-update file. Add new dated entries to the **Progress Log** (newest on top, don't delete history). Update the **Feature Status** table in place when something ships or changes state. Sources this file is grounded in: `apps/web/app/docs/intelligence/**` (in-app docs), `apps/web/app/(supply)/**` (route surface), `apps/api/app/routers/supply_smb.py`, `apps/api/app/services/supply_smb_live.py`, `apps/api/app/incept/save_cold_prospect_table.py`, `apps/prospect-tracker/**`, `docs/supply-smb-crosssell-project.md`, `docs/prospect-engine-queries.md`, `docs/bq-tables-reference.md`.

## What it is

Intelligence is Linglong Lab's supply-side analysis and cross-sell prospecting module: SDK/UA overlap analysis between Moloco and competitor networks, AI-assisted querying over that data, and pipelines that turn raw BigQuery/SensorTower signal into a prioritized, human-workable prospect list for China GTM / NBS sales.

## Architecture

- **Frontend:** Next.js (`apps/web`), routes under `apps/web/app/(supply)/` and `apps/web/app/ctv/`.
- **Backend:** FastAPI (`apps/api`), `apps/api/app/routers/supply_smb.py` (prefix `/api/v1/supply-smb`), business logic in `apps/api/app/services/supply_smb_live.py`.
- **Cold Prospect Pipeline (standalone script):** `apps/api/app/incept/save_cold_prospect_table.py` — BigQuery + SensorTower API + Gemini enrichment, run monthly, writes to `ads-bpd-guard-sandbox.supply_smb.*`.
- **Prospect Tracker / "Signal Desk" (standalone Google Apps Script tool):** `apps/prospect-tracker/` (`Code.gs` + `index.html`) — a separate Web App (not part of the Next.js app) that sits on top of the pipeline's output Google Sheet, for sales to annotate and track outreach without touching raw BigQuery/Sheets.
- **Data sources:** `ads-bpd-guard-china.athena.*` (app metadata, DSP spend), `ads-bpd-guard-china.gtm.supply_demand_overlap` (Moloco SDK/advertiser flags), `ads-bpd-guard-china.sensortower.*` (download estimates), live SensorTower API, `ads-bpd-guard-sandbox.supply_smb.*` (pipeline output tables).

## Feature Status

| Feature | Status | Notes |
|---|---|---|
| SDK/UA overlap top-lists (3-way matrix) | Live | `sdk-no-ua`, `ua-no-sdk`, `no-sdk-no-ua` — each with a top-lists view; company- and app-level rows (`CompanyRow`, `AppRow`), pagination, filter chips. |
| Detailed analysis views | Live | Per-segment detail pages for each of the 3 overlap combinations, plus a scoped variant. |
| Weekly Brief | Live | AI-generated summary (`WeeklyBriefSummaryPayload`, served separately so the rest of the page doesn't block on the Gemini call) + funnel steps + priority cards + supporting charts. Currently only wired for `no-sdk-no-ua`. |
| Ask AI | Live | Natural-language query interface over supply datasets (`apps/web/app/(supply)/ask-ai/[dataset]`). |
| AI Insights | Live | AI-generated insights, global and per-scope (`[scope]`). |
| Bundle Compare | Live | Upload an external CSV (广大大 / SensorTower export), backend enriches each bundle against Moloco BQ and appends diagnosis columns (`moloco_diagnosis`, `moloco_has_sdk`, `moloco_ua_spend_90d`, `st_*`). |
| Leads tracking | Live | `LeadRecord` model tracks list source, team routing, activation, conversion (`converted_date`, `total_spend_90d`, `is_attributed`) — attribution of cold-prospect leads back to real Moloco spend. |
| Xiaomi dashboard | Live | Dedicated account-specific Intelligence page. |
| Cold Prospect Pipeline | Live (monthly run) | BQ selection (China/HK/TW HQ, no existing Moloco SDK/UA relationship, ≥20K monthly downloads, top market ≠ CN/IN) → SensorTower enrichment (overview+SDK, download channels, MAU, UA network SOV) → P1/P2/P3 scoring → writes `cold_prospect_app` / `cold_prospect_company` / `prospect_snapshot`. Full methodology documented in-app at `/docs/intelligence/cold-prospect-pipeline`. |
| Chinese entity / company background enrichment | Live | Gemini (`gemini-3.5-flash`) + Google Search grounding, cache-first via `chinese_entity_cache`, runs as part of the monthly pipeline. |
| Moloco historical advertiser match | Live | 24-month lookback against `fact_dsp_core` — flags prospects who were previously a Moloco DSP advertiser (`moloco_advertiser_title/gm/nbs`, `moloco_platform_id`, `moloco_last_active`). |
| Prospect Tracker / Signal Desk (Apps Script tool) | Live | Standalone web app over the pipeline's Google Sheet: annotation form (Status/Stage/Sales-GM/Gatherone/Agency Note), BQ sync of new companies, weekly Launch Status check (spend detection via `fact_dsp_core`), Agency List export. |
| Weekly Launch Status check | Live | `checkLaunchStatus()` in `Code.gs` — checks last-7-day `fact_dsp_core` spend per bundle, marks `Launched` / `Not Onboard`; installed as a weekly (Monday 06:00) Apps Script time trigger. |
| Agency List export | **Paused** | Google Sheet's `Agency List` tab was manually redesigned with new columns (Onboarding Bonus, GatherOne销售, 是否有增加Bundle, 备注拓展情况) that don't match what `generateAgencyList()` writes. Export function is disabled (returns an error instead of running) to avoid wiping manual data, pending an agreed column layout / inclusion rule. |
| Supply team Top-2000 BD target exclusion/flagging | SQL written, not yet merged | Cross-references the supply team's `sdk_bd_target_setting_26q3_0624` publisher-level ranking: excludes cold-prospect candidates that supply already assigned a BD rep to (top 2000 + owned), flags the unassigned-but-top-2000 ones via `is_supply_top2000` / `supply_top2000_rank`. Migration deliberately deferred by request. |
| Admin — user management | Live | `apps/api/app/routers/admin.py`, role-based (`Role.admin`), backed by `BQAccessService` / `Incept.users` BQ table. |

## Key Files

### Frontend (Next.js Intelligence surface)
- `apps/web/app/(supply)/supply-smb/**` (top-lists, detailed-analysis, weekly-brief per segment)
- `apps/web/app/(supply)/ask-ai/[dataset]/page.tsx`
- `apps/web/app/(supply)/ai-insights/[scope]/page.tsx`
- `apps/web/components/supply-smb/bundle-compare-view.tsx`
- `apps/web/components/supply-smb/weekly-brief-view.tsx`
- `apps/web/app/actions/leads.ts`
- `apps/web/app/docs/intelligence/**` — in-app methodology docs

### Backend
- `apps/api/app/routers/supply_smb.py`
- `apps/api/app/services/supply_smb_live.py`
- `apps/api/app/models/supply.py`
- `apps/api/app/incept/save_cold_prospect_table.py` — the Cold Prospect Pipeline script

### Prospect Tracker (standalone Apps Script, not part of the Next.js app)
- `apps/prospect-tracker/Code.gs`
- `apps/prospect-tracker/index.html`

## Known Caveats / Open Questions

- Agency List export is disabled pending clarification of which companies it should include (previously Gatherone=Yes only; the manually-redesigned tab appears to include a broader set) and how to preserve manually-entered columns.
- Top-2000 BD exclusion SQL exists but hasn't been merged into `save_cold_prospect_table.py` — deferred by request, not blocked technically.
- Publisher-name matching against the supply team's BD target list is exact-string (`LOWER(TRIM(...))`), no fuzzy fallback — match rate not yet validated.
- Weekly Brief is only wired for the `no-sdk-no-ua` segment; not confirmed whether the other two segments need one too.

## Progress Log

_(newest first — add new entries above the previous one, don't rewrite history)_

### 2026-07-24
- Fixed a column-mapping bug in the Prospect Tracker (`Code.gs`) caused by a manually-inserted "Gatherone Sales" column in the Google Sheet shifting every subsequent column by one — every save would have silently written to the wrong column if left unfixed.
- Fixed the Stage Type dropdown in the annotation UI, which only offered `New/Growth/KA` while the real sheet data uses `Growth - consumer` / `Growth - gaming` — previously this would silently overwrite those values with "New" on save.
- Renamed "Follow-up Note" → "Agency Note" throughout the tool to match the sheet's actual header, and surfaced the new "Gatherone Sales" field (read-only) in the Info panel.
- Added weekly Launch Status check: queries `fact_dsp_core` for last-7-day spend per bundle, marks each prospect row `Launched`/`Not Onboard`, with a one-time-install weekly Apps Script trigger (`installWeeklyLaunchCheckTrigger`).
- Disabled `generateAgencyList()` (returns an error instead of executing) after discovering the live `Agency List` sheet tab had been manually redesigned with extra columns the export logic doesn't know how to preserve — avoids an accidental data wipe on next click.
- Reworked the Prospect Tracker's visual theme to a `#00a8e8`-based blue color family (replacing a near-black navy) across the header, stat cards, and the company detail/edit panel.
- Designed (but did not merge) SQL to cross-reference the supply team's Top-2000 BD target list against the Cold Prospect Pipeline's selection query, to exclude companies supply already owns and flag the rest.
- Set up the "Linglong Team Progress" Google Drive space for this project (`Project LinglongLab - Owen`) as a separate cross-team progress-sharing mechanism (distinct from this local `docs/` tracker).
