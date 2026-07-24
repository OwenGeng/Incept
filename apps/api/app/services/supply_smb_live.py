from __future__ import annotations

import json
import statistics
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.models.supply import (
    AnalysisModule,
    AnalysisGroup,
    AnalysisRow,
    DetailedAnalysisPayload,
    FilterChip,
    FilterControl,
    FilterOption,
    FunnelStep,
    GenericTablePayload,
    GenericTopListsPayload,
    HighlightCard,
    MethodologySection,
    PriorityCard,
    RefreshSnapshotResponse,
    SupportingChart,
    SupportingChartRow,
    TableColumn,
    TableRow,
    TopListsPayload,
    WeeklyBriefPayload,
)
from app.services.bigquery import BigQueryService
from app.services.gemini import GeminiService

# Brand palette shared across all analysis charts
CHART_PALETTE = ["#3a86ff", "#8338ec", "#ff006e", "#fb5607", "#ffbe0b"]


def _project_root() -> Path:
    import os
    # Explicit override — set INCEPT_PROJECT_ROOT in Cloud Run env vars
    env_root = os.environ.get("INCEPT_PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    # Auto-detect: walk up until we find a directory containing sql/
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "sql").exists():
            return candidate
    raise RuntimeError("Could not resolve InterSight project root")


PROJECT_ROOT = _project_root()
LIST_NO_SDK_UA_APP_SQL     = PROJECT_ROOT / "sql" / "no_sdk_no_ua_cold_app.sql"
LIST_NO_SDK_UA_COMPANY_SQL = PROJECT_ROOT / "sql" / "no_sdk_no_ua_cold_company.sql"
LIST1_SQL = PROJECT_ROOT / "sql" / "list1_cold_prospect.sql"
LIST1_COMPANY_SQL = PROJECT_ROOT / "sql" / "list1_company.sql"
LIST2_SQL = PROJECT_ROOT / "sql" / "list2_expansion.sql"
LIST3_SQL = PROJECT_ROOT / "sql" / "list3_supply_partner_upsdk.sql"


_cache_lock = threading.Lock()
_cache_ttl_seconds = 14_400  # 4 hours — keeps cache warm between periodic refreshes
_cache: dict[str, tuple[Any, float]] = {}


@dataclass
class TopListOptions:
    priority: str = "all"
    routing: str = "all"
    supply_visibility: str = "all"
    search: str = ""
    company_sort_by: str = "company_prospect_label"
    company_sort_dir: str = "asc"
    app_sort_by: str = "prospect_label"
    app_sort_dir: str = "asc"
    company_page: int = 1
    app_page: int = 1
    page_size: int = 10


@dataclass
class DatasetTopListOptions:
    search: str = ""
    routing: str = "all"
    hq_country: str = "all"
    monetization: str = "all"
    company_sort_by: str = "company_name"
    company_sort_dir: str = "asc"
    app_sort_by: str = "company_name"
    app_sort_dir: str = "asc"
    company_page: int = 1
    app_page: int = 1
    page_size: int = 10


DATASET_META: dict[str, dict[str, Any]] = {
    "list-1": {
        "sql_path": LIST1_SQL,
        "title": "List 1 Cold Prospect",
        "subtitle": "SDK integrated, no Moloco UA yet. Pure cold activation queue.",
        "methodology": [
            "App-level output from sql/list1_cold_prospect.sql.",
            "Company must already have Moloco SDK inventory but zero UA spend across all SDK apps.",
            "Companies with any is_moloco_advertiser_app=true app are excluded.",
            "Rows are limited to untapped bundles with sdk_media_cost_usd_30d above 10,000.",
        ],
        "company_key": "canonical_company",
        "company_columns": [
            ("company_name", "company_name", "text"),
            ("final_hq_country", "final_hq_country", "text"),
            ("team_routing", "team_routing", "text"),
            ("website", "website", "text"),
            ("untapped_apps", "untapped_apps", "number"),
            ("total_sdk_apps", "total_sdk_apps", "number"),
            ("company_sdk_media_cost_usd_30d", "company_sdk_media_cost_usd_30d", "currency"),
            ("company_monetization_types", "company_monetization_types", "text"),
            ("company_eligibility_statuses", "company_eligibility_statuses", "text"),
            ("company_mmps", "company_mmps", "text"),
            ("sdk_growth_managers", "sdk_growth_managers", "text"),
        ],
        "app_columns": [
            ("canonical_company", "company_name", "text"),
            ("app_name", "app_name", "text"),
            ("bundle_id", "bundle_id", "text"),
            ("os", "os", "text"),
            ("genre", "genre", "text"),
            ("monetization_type", "monetization_type", "badge"),
            ("sdk_media_cost_usd_30d", "sdk_media_cost_usd_30d", "currency"),
            ("sdk_media_cost_rank", "sdk_media_cost_rank", "number"),
            ("total_downloads_30d", "total_downloads_30d", "number"),
            ("top_sdk_impression_country", "top_sdk_impression_country", "text"),
            ("active_ua_networks", "active_ua_networks", "text"),
            ("eligibility_status", "eligibility_status", "badge"),
            ("ineligibility_reasons", "ineligibility_reasons", "text"),
            ("mmp", "mmp", "text"),
            ("sdl_sdk_growth_managers", "sdl_sdk_growth_managers", "text"),
            ("final_hq_country", "final_hq_country", "text"),
            ("team_routing", "team_routing", "text"),
            ("website", "website", "text"),
        ],
    },
    "list-1-company": {
        "sql_path": LIST1_COMPANY_SQL,
        "title": "List 1 Companies",
        "subtitle": "Company-level view of List 1 Cold Prospect. One row per company.",
        "methodology": [
            "Company-level output from sql/list1_company.sql.",
            "One row per company. All SDK apps have zero Moloco UA spend.",
            "Companies with any is_moloco_advertiser_app=true app are excluded.",
        ],
        "company_key": "company_name",
        "company_columns": [
            ("company_name", "company_name", "text"),
            ("final_hq_country", "final_hq_country", "text"),
            ("team_routing", "team_routing", "text"),
            ("website", "website", "text"),
            ("total_sdk_apps", "total_sdk_apps", "number"),
            ("untapped_apps", "untapped_apps", "number"),
            ("total_sdk_media_cost_usd_30d", "total_sdk_media_cost_usd_30d", "currency"),
            ("monetization_types", "monetization_types", "text"),
            ("eligibility_statuses", "eligibility_statuses", "text"),
            ("mmps", "mmps", "text"),
            ("sdk_growth_managers", "sdk_growth_managers", "text"),
            ("tracking_publisher_name", "tracking_publisher_name", "text"),
        ],
        "app_columns": [],
    },
    "list-2": {
        "sql_path": LIST2_SQL,
        "title": "List 2 Expansion",
        "subtitle": "SDK integrated, some Moloco UA exists. Expand from current relationship.",
        "methodology": [
            "App-level output from sql/list2_expansion.sql.",
            "Company already has at least one SDK app buying UA, while other SDK apps remain untapped.",
            "Rows are untapped bundles ordered by current SDK media cost and existing relationship depth.",
        ],
        "company_key": "canonical_company",
        "company_columns": [
            ("company_name", "company_name", "text"),
            ("final_hq_country", "final_hq_country", "text"),
            ("team_routing", "team_routing", "text"),
            ("buying_ua_apps", "buying_ua_apps", "number"),
            ("untapped_apps", "untapped_apps", "number"),
            ("company_existing_spend_usd_90d", "company_existing_spend_usd_90d", "currency"),
            ("company_moloco_offices", "company_moloco_offices", "text"),
            ("company_moloco_gms", "company_moloco_gms", "text"),
        ],
        "app_columns": [
            ("canonical_company", "company_name", "text"),
            ("app_name", "app_name", "text"),
            ("bundle_id", "bundle_id", "text"),
            ("genre", "genre", "text"),
            ("monetization_type", "monetization_type", "badge"),
            ("sdk_media_cost_usd_30d", "sdk_media_cost_usd_30d", "currency"),
            ("total_downloads_30d", "total_downloads_30d", "number"),
            ("top_dl_country", "top_dl_country", "text"),
            ("eligibility_status", "eligibility_status", "badge"),
            ("company_existing_spend_usd_90d", "company_existing_spend_usd_90d", "currency"),
        ],
    },
    "list-3": {
        "sql_path": LIST3_SQL,
        "title": "List 3 Supply Partner No SDK",
        "subtitle": "Company already trusts Moloco on other supply apps, but this app still has no SDK.",
        "methodology": [
            "App-level output from sql/list3_supply_partner_upsdk.sql.",
            "Candidate company is already a Moloco supply partner, but the specific app has no SDK and no UA spend.",
            "Rows are prioritized by existing company SDK depth, exchange reach, and app scale.",
        ],
        "company_key": "company_name",
        "company_columns": [
            ("company_name", "company_name", "text"),
            ("final_hq_country", "final_hq_country", "text"),
            ("team_routing", "team_routing", "text"),
            ("untapped_apps_count", "untapped_apps_count", "number"),
            ("existing_sdk_app_count", "existing_sdk_app_count", "number"),
            ("existing_sdk_media_cost_30d", "existing_sdk_media_cost_30d", "currency"),
            ("existing_ua_spend_30d", "existing_ua_spend_30d", "currency"),
            ("total_downloads_30d", "total_downloads_30d", "number"),
        ],
        "app_columns": [
            ("company_name", "company_name", "text"),
            ("app_bundle", "app_bundle", "text"),
            ("genre", "genre", "text"),
            ("monetization_type", "monetization_type", "badge"),
            ("existing_sdk_media_cost_30d", "existing_sdk_media_cost_30d", "currency"),
            ("total_bid_requests_90d", "total_bid_requests_90d", "number"),
            ("total_downloads_30d", "total_downloads_30d", "number"),
            ("top_dl_country", "top_dl_country", "text"),
            ("eligibility_status", "eligibility_status", "badge"),
        ],
    },
}


def _current_week_start() -> date:
    """Return Monday of the current week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


class SupplySmbLiveService:
    def __init__(self) -> None:
        self.bigquery = BigQueryService()
        self.gemini: GeminiService | None = None
        # Lazy: tables created on first write attempt, not at startup
        self._intersight_ready = False

    def _ensure_intersight(self) -> None:
        if not self._intersight_ready:
            try:
                self.bigquery.ensure_intersight_tables()
                self._intersight_ready = True
            except Exception:
                pass  # Non-fatal; will retry next time

    def get_weekly_brief(self) -> WeeklyBriefPayload:
        """
        Fast path — dataset is BQ-cached (see _get_dataset), no LLM call.
        summary/opportunity are filled with the deterministic fallback text so
        the page always has something to show immediately; the AI-generated
        version is fetched separately via get_weekly_brief_summary() and
        streamed in on the frontend once ready.
        """
        dataset = self._get_dataset()
        companies = dataset["companies"]
        apps = dataset["apps"]

        priority_cards = self._build_priority_cards(companies, apps)
        highlights = self._build_highlights(companies, apps)
        supporting_charts = self._build_supporting_charts(apps)
        funnel_steps = self._compute_funnel(companies, apps)

        return WeeklyBriefPayload(
            title="Supply SMB Cross-Sell",
            date_range=self._current_month_label(),
            refresh_status=f"BigQuery refresh synced {self._current_timestamp_label()}",
            summary=self._fallback_summary(companies, apps, highlights),
            opportunity=self._fallback_opportunity(companies, apps),
            big_things=[],
            week_changes=[],
            selection_steps=self._selection_steps(),
            priorities=priority_cards,
            highlights=highlights,
            supporting_charts=supporting_charts,
            funnel_steps=funnel_steps,
        )

    def get_weekly_brief_summary(self) -> dict[str, Any]:
        """
        Slow path — calls Gemini, cached for _cache_ttl_seconds (4h) so repeat
        page loads within the window skip the LLM round trip entirely.
        Cache is cleared on every refresh_snapshot() run.
        """
        cached = self._cache_get("weekly_brief_summary")
        if cached is not None:
            return cached

        dataset = self._get_dataset()
        companies = dataset["companies"]
        apps = dataset["apps"]
        priority_cards = self._build_priority_cards(companies, apps)
        highlights = self._build_highlights(companies, apps)
        snapshot_diff = self._get_snapshot_diff()

        generated = self._generate_summary_with_gemini(
            companies, apps, highlights, priority_cards, snapshot_diff=snapshot_diff
        )

        result = {
            "summary": generated.get("summary") or self._fallback_summary(companies, apps, highlights),
            "opportunity": generated.get("opportunity") or self._fallback_opportunity(companies, apps),
            "big_things": generated.get("big_things") or [],
            "week_changes": generated.get("week_changes") or [],
        }
        self._cache_set("weekly_brief_summary", result)
        return result

    def refresh_snapshot(self) -> RefreshSnapshotResponse:
        """
        Pull fresh data, write a weekly snapshot to BQ.
        Call this manually each week (or via Cloud Scheduler).
        """
        self._ensure_intersight()
        # Clear in-memory cache so we always pull fresh data
        with _cache_lock:
            _cache.clear()

        dataset = self._get_dataset()
        companies = dataset["companies"]
        apps = dataset["apps"]
        priority_cards = self._build_priority_cards(companies, apps)

        week_start = _current_week_start()
        snapshot = self._build_snapshot_data(companies, apps, priority_cards)

        written = False
        try:
            self.bigquery.write_snapshot(week_start.isoformat(), snapshot)
            written = True
        except Exception as exc:
            return RefreshSnapshotResponse(
                week_start_date=week_start.isoformat(),
                snapshot_written=False,
                message=f"Snapshot write failed: {exc}",
            )

        return RefreshSnapshotResponse(
            week_start_date=week_start.isoformat(),
            snapshot_written=written,
            message=(
                f"Snapshot written for week {week_start.isoformat()} — "
                f"{snapshot['total_companies']} companies, {snapshot['total_apps']} apps."
            ),
        )

    def get_top_lists(self, options: TopListOptions) -> TopListsPayload:
        dataset = self._get_dataset()
        filtered_companies = self._sort_rows(
            self._filter_companies(dataset["companies"], options),
            options.company_sort_by,
            options.company_sort_dir,
            table="company",
        )
        filtered_apps = self._sort_rows(
            self._filter_apps(dataset["apps"], options),
            options.app_sort_by,
            options.app_sort_dir,
            table="app",
        )

        company_total = len(filtered_companies)
        app_total = len(filtered_apps)
        companies = self._paginate_rows(filtered_companies, options.company_page, options.page_size)
        apps = self._paginate_rows(filtered_apps, options.app_page, options.page_size)

        return TopListsPayload(
            filters=self._build_filter_chips(filtered_companies, filtered_apps, options),
            companies=[self._to_company_row(company) for company in companies],
            apps=[self._to_app_row(app) for app in apps],
            company_page=options.company_page,
            company_total=company_total,
            app_page=options.app_page,
            app_total=app_total,
            page_size=options.page_size,
        )

    def get_detailed_analysis(self, routing_filter: str | None = None) -> DetailedAnalysisPayload:
        dataset = self._get_dataset()
        companies = dataset["companies"]
        apps = dataset["apps"]

        # Agency: scope distributions to their routing bucket
        if routing_filter:
            companies = [c for c in companies if (c.get("team_routing") or "") == routing_filter]
            app_company_names = {c.get("company_name") for c in companies}
            apps = [a for a in apps if (a.get("company_name") or "") in app_company_names]

        # Paid fraction buckets (from download_channels API via ST)
        def _paid_frac_bucket(frac: float) -> str:
            if frac >= 0.5:
                return "≥50% (P1 range)"
            if frac >= 0.2:
                return "20–50% (P2 range)"
            if frac >= 0.05:
                return "5–20%"
            return "<5% (organic)"

        # Parse multi-value text fields — split on ", " (pipeline delimiter), strip whitespace
        def _parse_multivalue(raw: str) -> list[str]:
            import re as _re
            parts = _re.split(r",\s*|\n", raw)
            return [p.strip() for p in parts if p.strip()]

        # UA SDK normalisation map: any name containing the key → canonical label
        _UA_SDK_NORM: list[tuple[str, str]] = [
            ("AppLovin",    "AppLovin (MAX)"),
            ("ironSource",  "ironSource / LevelPlay"),
            ("LevelPlay",   "ironSource / LevelPlay"),
            ("UnityAds",    "Unity Ads"),
            ("Mintegral",   "Mintegral"),
            ("Pangle",      "Pangle (TikTok)"),
            ("TopOn",       "TopOn"),
            ("Appodeal",    "Appodeal"),
            ("Bidmachine",  "BidMachine"),
            ("AdMob",       "AdMob"),
            ("AdColony",    "AdColony / DT Exchange"),
            ("DT Exchange", "AdColony / DT Exchange"),
            ("Vungle",      "Vungle / Liftoff"),
            ("Liftoff",     "Vungle / Liftoff"),
            ("Chartboost",  "Chartboost"),
            ("InMobi",      "InMobi"),
        ]

        def _normalise_sdk(name: str) -> str | None:
            """Return canonical UA SDK label if name matches, else None."""
            lower = name.lower()
            for keyword, label in _UA_SDK_NORM:
                if keyword.lower() in lower:
                    return label
            return None

        ua_sdk_counter: Counter[str] = Counter()
        for app in apps:
            raw = app.get("installed_sdks") or ""
            seen: set[str] = set()
            for sdk_name in _parse_multivalue(raw):
                canonical = _normalise_sdk(sdk_name)
                if canonical and canonical not in seen:
                    ua_sdk_counter[canonical] += 1
                    seen.add(canonical)

        ua_network_counter: Counter[str] = Counter()
        for app in apps:
            raw = app.get("active_ua_networks") or ""
            if raw and raw != "No Active Networks":
                for net in _parse_multivalue(raw):
                    canonical = _normalise_sdk(net) or net
                    ua_network_counter[canonical] += 1

        top_country_counter: Counter[str] = Counter()
        for app in apps:
            tc_raw = app.get("top_countries") or "[]"
            try:
                tc_list = json.loads(tc_raw) if isinstance(tc_raw, str) else (tc_raw or [])
            except Exception:
                tc_list = []
            for country in tc_list:
                if country:
                    top_country_counter[str(country).upper()] += 1

        modules = [
            self._distribution_module(
                "Priority Distribution",
                "P1/P2/P3 split across all companies. P1 = UA SDK + paid_frac ≥50% + active networks; P2 = UA SDK + paid_frac ≥20%; P3 = all others.",
                Counter(company.get("best_priority") or "P3" for company in companies),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "HQ Country Distribution",
                "Headquarters country across the full company pool, sourced from SensorTower company metadata.",
                Counter(company.get("hq_country") or "Unknown" for company in companies),
                CHART_PALETTE,
                limit=8,
            ),
            self._distribution_module(
                "Team Routing",
                "GTM routing assignment per company — determines which AE or agency handles outreach.",
                Counter(company.get("team_routing") or "Unknown" for company in companies),
                CHART_PALETTE,
                chart_type="pie",
            ),
            self._gaming_by_priority_module(companies),
            self._distribution_module(
                "Monetization Mix",
                "App-level monetization type from SensorTower (IAA / IAP / Hybrid / Free). Shapes UA pitch strategy.",
                Counter((app.get("monetization_type") or "Unknown") for app in apps),
                CHART_PALETTE,
                chart_type="pie",
            ),
            self._distribution_module(
                "Genre Mix",
                "Top app genres across the cold prospect pool. Gaming vs non-gaming determines routing and pitch angle.",
                Counter((app.get("genre") or "Unknown") for app in apps),
                CHART_PALETTE,
                limit=6,
                chart_type="pie",
            ),
            self._distribution_module(
                "Download Scale",
                "Latest-month download buckets (SensorTower st_last_month_downloads). All apps already pass the ≥20K threshold.",
                Counter(self._download_bucket(int(app.get("st_last_month_downloads") or 0)) for app in apps),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "Paid Download Fraction",
                "Share of downloads that are paid (paid_abs / total). Sourced from SensorTower download channels API. High paid_frac = active UA spender.",
                Counter(_paid_frac_bucket(float(app.get("paid_frac") or 0)) for app in apps),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "Supply Visibility",
                "Whether Moloco already buys this company's exchange inventory (any_moloco_supply). Visible = can start cross-sell immediately.",
                Counter(("Supply Visible" if company.get("any_moloco_supply") else "Not Visible") for company in companies),
                CHART_PALETTE,
                chart_type="pie",
            ),
            self._distribution_module(
                "Eligibility Status",
                "Moloco supply eligibility state from the BQ supply pipeline — indicates whether SDL has reviewed and cleared the app.",
                Counter((app.get("eligibility_status") or "Undecided") for app in apps),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "OS Distribution",
                "iOS vs Android split. Determines SensorTower API coverage and SDK integration path.",
                Counter((str(app.get("os") or "Unknown")).capitalize() for app in apps),
                CHART_PALETTE,
                chart_type="pie",
            ),
            self._distribution_module(
                "UA SDK Presence",
                "How many apps in the cold prospect pool have each UA SDK installed (from SensorTower SDK tags). AppLovin variants normalised into one label. Apps with any of these SDKs are P1/P2 candidates.",
                ua_sdk_counter,
                CHART_PALETTE,
            ),
            self._distribution_module(
                "Active UA Networks (SOV)",
                "UA networks actively running creatives on these apps right now (SensorTower network SOV data). Distinct from SDK presence — shows live spend, not just integration.",
                ua_network_counter,
                CHART_PALETTE,
                limit=12,
            ),
            self._distribution_module(
                "Top Download Countries",
                "All countries appearing in each app's top_countries list (SensorTower, all positions counted). Shows which markets these apps are actually reaching.",
                top_country_counter,
                CHART_PALETTE,
                limit=15,
            ),
        ]

        methodology = [
            MethodologySection(
                title="Data Sources",
                items=[
                    "ads-bpd-guard-sandbox.supply_smb.cold_prospect_app — one row per app, refreshed weekly by sensortower_pipeline.py",
                    "ads-bpd-guard-sandbox.supply_smb.cold_prospect_company — company rollup aggregated from cold_prospect_app",
                    "SensorTower API: app metadata, monthly downloads, download channels (paid/organic split), SDK tags, UA network SOV",
                    "Moloco BQ: supply_demand_overlap for exchange visibility, fact_dsp_publisher for media cost signals",
                ],
            ),
            MethodologySection(
                title="Inclusion Logic",
                items=[
                    "Latest full month downloads ≥ 20,000 (SensorTower st_last_month_downloads)",
                    "App has IAA, IAP, or Hybrid monetization — pure Free apps excluded",
                    "No Moloco SDK relationship on the app (is_moloco_sdk_app = false)",
                    "No Moloco UA advertiser spend on the app (is_moloco_advertiser_app = false)",
                ],
            ),
            MethodologySection(
                title="Priority Logic",
                items=[
                    "P1: has UA SDK (AppLovin/ironSource/Mintegral/Pangle etc.) + paid_frac ≥ 50% + active_ua_networks not null",
                    "P2: has UA SDK + paid_frac ≥ 20% (monetising but below P1 threshold)",
                    "P3: no UA SDK or paid_frac below threshold — broad cold pool for agency batch outreach",
                    "Company best_priority = best (lowest P-number) across all its apps",
                ],
            ),
        ]

        return DetailedAnalysisPayload(modules=modules, methodology=methodology)

    def get_dataset_top_lists(
        self,
        dataset_key: str,
        options: DatasetTopListOptions,
    ) -> GenericTopListsPayload:
        rows = self._get_custom_dataset_rows(dataset_key)
        meta = DATASET_META[dataset_key]
        filtered_apps = self._filter_custom_apps(rows, options)
        filtered_companies = self._build_custom_companies(dataset_key, filtered_apps)

        sorted_companies = self._sort_rows(filtered_companies, options.company_sort_by, options.company_sort_dir, "company")
        sorted_apps = self._sort_rows(filtered_apps, options.app_sort_by, options.app_sort_dir, "app")

        paged_companies = self._paginate_rows(sorted_companies, options.company_page, options.page_size)
        paged_apps = self._paginate_rows(sorted_apps, options.app_page, options.page_size)

        return GenericTopListsPayload(
            dataset_key=dataset_key,
            title=meta["title"],
            subtitle=meta["subtitle"],
            filters=self._build_custom_filter_chips(filtered_companies, filtered_apps, options),
            controls=self._build_custom_controls(rows),
            companies_table=self._build_generic_table(
                title="Top Companies",
                subtitle=f"Company rollup derived from {meta['sql_path'].name}.",
                rows=paged_companies,
                total=len(sorted_companies),
                page=options.company_page,
                page_size=options.page_size,
                sort_by=options.company_sort_by,
                sort_dir=options.company_sort_dir,
                columns=meta["company_columns"],
            ),
            apps_table=self._build_generic_table(
                title="Top Apps",
                subtitle=f"App detail derived from {meta['sql_path'].name}.",
                rows=paged_apps,
                total=len(sorted_apps),
                page=options.app_page,
                page_size=options.page_size,
                sort_by=options.app_sort_by,
                sort_dir=options.app_sort_dir,
                columns=meta["app_columns"],
            ),
        )

    def get_dataset_detailed_analysis(self, dataset_key: str, routing_filter: str | None = None) -> DetailedAnalysisPayload:
        rows = self._get_custom_dataset_rows(dataset_key)
        companies = self._build_custom_companies(dataset_key, rows)
        if routing_filter:
            companies = [c for c in companies if (c.get("team_routing") or "") == routing_filter]
        meta = DATASET_META[dataset_key]
        modules = self._build_custom_analysis_modules(dataset_key, rows, companies)
        methodology = [
            MethodologySection(
                title="Data Sources",
                items=[
                    f"BigQuery source query from {meta['sql_path'].name}",
                    "Sensor Tower app metadata, network analysis, and 30-day download signals",
                    "Moloco supply / demand overlap, SDK context, and GTM HQ overrides",
                ],
            ),
            MethodologySection(
                title="Dataset Logic",
                items=meta["methodology"],
            ),
            MethodologySection(
                title="Operating Use",
                items=[
                    "Use Top Companies for routing and account ownership decisions.",
                    "Use Top Apps for bundle-level action planning and follow-up sequencing.",
                    "Use these distributions to sanity-check where the queue is concentrated before outreach.",
                ],
            ),
        ]
        return DetailedAnalysisPayload(modules=modules, methodology=methodology)

    def _get_dataset(self) -> dict[str, list[dict[str, Any]]]:
        cached = self._cache_get("dataset")
        if cached is not None:
            return cached

        companies = self._run_company_query()
        apps = self._run_app_query()
        dataset = {"companies": companies, "apps": apps}
        self._cache_set("dataset", dataset)
        return dataset

    def _get_custom_dataset_rows(self, dataset_key: str) -> list[dict[str, Any]]:
        cache_key = f"custom:{dataset_key}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        rows = self.bigquery.query_file(DATASET_META[dataset_key]["sql_path"])
        self._cache_set(cache_key, rows)
        return rows

    def _run_company_query(self) -> list[dict[str, Any]]:
        return self.bigquery.query(
            "SELECT * FROM `ads-bpd-guard-sandbox.supply_smb.cold_prospect_company`"
        )

    def _run_app_query(self) -> list[dict[str, Any]]:
        return self.bigquery.query(
            "SELECT * FROM `ads-bpd-guard-sandbox.supply_smb.cold_prospect_app`"
        )

    def _get_snapshot_diff(self) -> dict[str, int]:
        """Compare latest two weeks in prospect_snapshot, return new/dropped counts."""
        try:
            sql = """
            WITH weeks AS (
              SELECT DISTINCT week_of
              FROM `ads-bpd-guard-sandbox.supply_smb.prospect_snapshot`
              ORDER BY week_of DESC LIMIT 2
            ),
            cur AS (
              SELECT app_market_bundle
              FROM `ads-bpd-guard-sandbox.supply_smb.prospect_snapshot`
              WHERE week_of = (SELECT MAX(week_of) FROM weeks)
            ),
            prev AS (
              SELECT app_market_bundle
              FROM `ads-bpd-guard-sandbox.supply_smb.prospect_snapshot`
              WHERE week_of = (SELECT MIN(week_of) FROM weeks)
            )
            SELECT
              COUNTIF(cur.app_market_bundle IS NULL)  AS dropped,
              COUNTIF(prev.app_market_bundle IS NULL) AS new_apps
            FROM cur FULL OUTER JOIN prev USING (app_market_bundle)
            """
            rows = self.bigquery.query(sql)
            if rows:
                return {
                    "new": int(rows[0].get("new_apps") or 0),
                    "dropped": int(rows[0].get("dropped") or 0),
                }
        except Exception:
            pass
        return {"new": 0, "dropped": 0}

    def _filter_custom_apps(
        self,
        rows: list[dict[str, Any]],
        options: DatasetTopListOptions,
    ) -> list[dict[str, Any]]:
        search = options.search.strip().lower()
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if options.routing != "all" and str(row.get("team_routing") or "") != options.routing:
                continue
            if options.hq_country != "all" and str(row.get("final_hq_country") or "") != options.hq_country:
                continue
            row_monetization = str(row.get("monetization_type") or "Unknown")
            if options.monetization != "all" and row_monetization != options.monetization:
                continue
            if search and search not in json.dumps(row, default=str).lower():
                continue
            filtered.append(row)
        return filtered

    def _build_custom_companies(
        self,
        dataset_key: str,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if dataset_key in {"list-1", "list-2"}:
            company_key = "canonical_company"
        else:
            company_key = "company_name"

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = str(row.get(company_key) or "Unknown")
            grouped.setdefault(key, []).append(row)

        companies: list[dict[str, Any]] = []
        for key, group in grouped.items():
            first = group[0]
            company = {
                "company_name": key,
                "final_hq_country": first.get("final_hq_country") or "Unknown",
                "team_routing": first.get("team_routing") or "Unknown",
                "total_downloads_30d": sum(int(item.get("total_downloads_30d") or 0) for item in group),
                "monetization_type": ", ".join(
                    sorted({str(item.get("monetization_type") or "Unknown") for item in group})
                ),
            }

            if dataset_key == "list-1":
                company.update(
                    {
                        "untapped_apps": max(int(item.get("untapped_apps") or 0) for item in group),
                        "total_sdk_apps": max(int(item.get("total_sdk_apps") or 0) for item in group),
                        "company_sdk_media_cost_usd_30d": max(
                            int(item.get("company_sdk_media_cost_usd_30d") or 0) for item in group
                        ),
                        "company_monetization_types": first.get("company_monetization_types") or company["monetization_type"],
                        "company_eligibility_statuses": first.get("company_eligibility_statuses") or "Unknown",
                        "company_mmps": first.get("company_mmps") or "",
                        "sdk_growth_managers": first.get("sdk_growth_managers") or "",
                        "website": first.get("website") or "",
                    }
                )
            elif dataset_key == "list-2":
                company.update(
                    {
                        "buying_ua_apps": max(int(item.get("buying_ua_apps") or 0) for item in group),
                        "untapped_apps": max(int(item.get("untapped_apps") or 0) for item in group),
                        "company_existing_spend_usd_90d": max(
                            int(item.get("company_existing_spend_usd_90d") or 0) for item in group
                        ),
                        "company_moloco_offices": first.get("company_moloco_offices") or "Unknown",
                        "company_moloco_gms": first.get("company_moloco_gms") or "Unknown",
                    }
                )
            else:
                company.update(
                    {
                        "untapped_apps_count": len(group),
                        "existing_sdk_app_count": max(int(item.get("existing_sdk_app_count") or 0) for item in group),
                        "existing_sdk_media_cost_30d": max(
                            int(item.get("existing_sdk_media_cost_30d") or 0) for item in group
                        ),
                        "existing_ua_spend_30d": max(int(item.get("existing_ua_spend_30d") or 0) for item in group),
                    }
                )
            companies.append(company)
        return companies

    def _build_custom_controls(self, rows: list[dict[str, Any]]) -> list[FilterControl]:
        def options_for(field: str) -> list[FilterOption]:
            values = sorted({str(row.get(field) or "Unknown") for row in rows if row.get(field) is not None})
            return [FilterOption(label="all", value="all")] + [FilterOption(label=value, value=value) for value in values]

        return [
            FilterControl(key="routing", label="team_routing", options=options_for("team_routing")),
            FilterControl(key="hqCountry", label="final_hq_country", options=options_for("final_hq_country")),
            FilterControl(key="monetization", label="monetization_type", options=options_for("monetization_type")),
        ]

    def _build_custom_filter_chips(
        self,
        companies: list[dict[str, Any]],
        apps: list[dict[str, Any]],
        options: DatasetTopListOptions,
    ) -> list[FilterChip]:
        chips = [
            FilterChip(label="Companies", value=str(len(companies)), tone="blue"),
            FilterChip(label="Apps", value=str(len(apps)), tone="green"),
        ]
        if options.routing != "all":
            chips.append(FilterChip(label="team_routing", value=options.routing, tone="purple"))
        if options.hq_country != "all":
            chips.append(FilterChip(label="final_hq_country", value=options.hq_country))
        if options.monetization != "all":
            chips.append(FilterChip(label="monetization_type", value=options.monetization))
        if options.search:
            chips.append(FilterChip(label="Search", value=options.search))
        return chips

    def _build_generic_table(
        self,
        *,
        title: str,
        subtitle: str,
        rows: list[dict[str, Any]],
        total: int,
        page: int,
        page_size: int,
        sort_by: str,
        sort_dir: str,
        columns: list[tuple[str, str, str]],
    ) -> GenericTablePayload:
        return GenericTablePayload(
            title=title,
            subtitle=subtitle,
            columns=[
                TableColumn(key=key, label=label, format=format_name)
                for key, label, format_name in columns
            ],
            rows=[
                TableRow(
                    key=self._row_key_from_values(row, [column[0] for column in columns], index),
                    cells={
                        column[0]: (
                            v.isoformat() if hasattr(v, "isoformat") else v
                        )
                        for column in columns
                        for v in [row.get(column[0])]
                    },
                )
                for index, row in enumerate(rows)
            ],
            page=page,
            total=total,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    def _build_custom_analysis_modules(
        self,
        dataset_key: str,
        apps: list[dict[str, Any]],
        companies: list[dict[str, Any]],
    ) -> list[AnalysisModule]:
        modules = [
            self._distribution_module(
                "Geography Distribution",
                "Verified HQ distribution across the filtered company set.",
                Counter(str(company.get("final_hq_country") or "Unknown") for company in companies),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "Team Routing",
                "Current follow-up ownership split for the active queue.",
                Counter(str(company.get("team_routing") or "Unknown") for company in companies),
                CHART_PALETTE,
                chart_type="pie",
            ),
            self._distribution_module(
                "Monetization Mix",
                "Monetization patterns shaping the pitch path.",
                Counter(str(app.get("monetization_type") or "Unknown") for app in apps),
                CHART_PALETTE,
                chart_type="pie",
            ),
            self._distribution_module(
                "Genre Mix",
                "Genre concentration for the current app queue.",
                Counter(str(app.get("genre") or "Unknown") for app in apps),
                CHART_PALETTE,
                limit=5,
                chart_type="pie",
            ),
            self._distribution_module(
                "Download Scale",
                "30-day download scale buckets across the filtered app pool.",
                Counter(self._download_bucket(int(app.get("total_downloads_30d") or 0)) for app in apps),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "Eligibility Status",
                "Eligibility pattern currently attached to the queue.",
                Counter(str(app.get("eligibility_status") or "Unknown") for app in apps),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "OS Distribution",
                "iOS vs Android split across the app queue.",
                Counter(str(app.get("os") or "Unknown").capitalize() for app in apps),
                CHART_PALETTE,
                chart_type="pie",
            ),
        ]

        if dataset_key == "list-1":
            # Top SDK impression country
            modules.append(self._distribution_module(
                "Top SDK Impression Country",
                "Countries where Moloco sees the most SDK impression volume for these apps.",
                Counter(str(app.get("top_sdk_impression_country") or "Unknown") for app in apps),
                CHART_PALETTE,
                limit=8,
            ))

            # SDK growth manager distribution (comma-separated field, split and count individually)
            mgr_counter: Counter[str] = Counter()
            for app in apps:
                raw = str(app.get("sdl_sdk_growth_managers") or "").strip()
                if not raw:
                    mgr_counter["Unassigned"] += 1
                else:
                    for mgr in (m.strip() for m in raw.split(",") if m.strip()):
                        mgr_counter[mgr] += 1
            if mgr_counter:
                modules.append(self._distribution_module(
                    "SDK Growth Manager Coverage",
                    "Number of apps each SDK Growth Manager is covering in this queue.",
                    mgr_counter,
                    CHART_PALETTE,
                ))

        return modules

    def _row_key_from_values(self, row: dict[str, Any], keys: list[str], index: int) -> str:
        values = [str(row.get(key) or "") for key in keys[:3]]
        base = "-".join(values).strip("-")
        return f"{base or 'row'}-{index}"

    def _filter_companies(
        self,
        companies: list[dict[str, Any]],
        options: TopListOptions,
    ) -> list[dict[str, Any]]:
        search = options.search.strip().lower()
        filtered: list[dict[str, Any]] = []
        for company in companies:
            priority = self._priority_code(company.get("best_priority"))
            if options.priority != "all" and priority != options.priority:
                continue
            if options.routing != "all" and (company.get("team_routing") or "") != options.routing:
                continue
            is_visible = bool(company.get("is_moloco_supply_visible"))
            if options.supply_visibility == "visible" and not is_visible:
                continue
            if options.supply_visibility == "hidden" and is_visible:
                continue
            if search and search not in json.dumps(company, default=str).lower():
                continue
            filtered.append(company)
        return filtered

    def _filter_apps(self, apps: list[dict[str, Any]], options: TopListOptions) -> list[dict[str, Any]]:
        search = options.search.strip().lower()
        filtered: list[dict[str, Any]] = []
        for app in apps:
            priority = self._priority_code(app.get("priority"))
            if options.priority != "all" and priority != options.priority:
                continue
            if options.routing != "all" and (app.get("team_routing") or "") != options.routing:
                continue
            is_visible = bool(app.get("is_moloco_supply_visible"))
            if options.supply_visibility == "visible" and not is_visible:
                continue
            if options.supply_visibility == "hidden" and is_visible:
                continue
            if search and search not in json.dumps(app, default=str).lower():
                continue
            filtered.append(app)
        return filtered

    def _sort_rows(
        self,
        rows: list[dict[str, Any]],
        sort_by: str,
        sort_dir: str,
        table: str,
    ) -> list[dict[str, Any]]:
        def normalize_value(row: dict[str, Any]) -> Any:
            if sort_by in {"best_priority", "priority", "company_prospect_label", "prospect_label"}:
                return self._priority_rank(row.get(sort_by) or row.get("best_priority") or row.get("priority"))
            value = row.get(sort_by)
            if isinstance(value, bool):
                return int(value)
            if value is None:
                return ""
            return value

        reverse = sort_dir == "desc"
        return sorted(rows, key=normalize_value, reverse=reverse)

    def _paginate_rows(
        self,
        rows: list[dict[str, Any]],
        page: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        page = max(page, 1)
        start = (page - 1) * page_size
        end = start + page_size
        return rows[start:end]

    def _build_priority_cards(
        self,
        companies: list[dict[str, Any]],
        apps: list[dict[str, Any]],
    ) -> list[PriorityCard]:
        tier_meta = {
            "P1": ("Prime / UA Ready", "NBS direct", "Has UA SDK + paid fraction ≥50% + active UA networks — highest conversion potential."),
            "P2": ("Strong Signal", "NBS + agency", "Has UA SDK + paid fraction ≥20% — clear monetization intent without full UA commitment."),
            "P3": ("Cold", "Agency batch", "No UA SDK or insufficient paid fraction — broad outreach pool for agency follow-up."),
        }

        cards: list[PriorityCard] = []
        for tier in ("P1", "P2", "P3"):
            company_count = sum(
                1 for company in companies if self._priority_code(company.get("best_priority")) == tier
            )
            app_count = sum(1 for app in apps if self._priority_code(app.get("priority")) == tier)
            label, route, note = tier_meta[tier]
            cards.append(
                PriorityCard(
                    tier=tier,  # type: ignore[arg-type]
                    label=label,
                    companies=company_count,
                    apps=app_count,
                    delta="Live",
                    note=note,
                    route=route,
                )
            )
        return cards

    def _build_highlights(
        self,
        companies: list[dict[str, Any]],
        apps: list[dict[str, Any]],
    ) -> list[HighlightCard]:
        focus_companies = [
            company
            for company in companies
            if self._priority_code(company.get("best_priority")) in {"P1", "P2"}
        ]
        visible_companies = [
            company for company in companies if bool(company.get("any_moloco_supply"))
        ]
        median_cost = 0
        if visible_companies:
            median_cost = round(
                statistics.median(
                    int(company.get("total_moloco_cost_30d") or 0) for company in visible_companies
                )
            )
        p1_count = sum(1 for c in companies if self._priority_code(c.get("best_priority")) == "P1")

        return [
            HighlightCard(
                label="Active Follow-up Companies",
                value=str(len(focus_companies)),
                detail="Current P1 + P2 company queue pulled directly from the latest BigQuery run.",
            ),
            HighlightCard(
                label="Median Moloco Media Cost",
                value=f"${median_cost:,.0f}",
                detail="Median 30-day Moloco media cost among companies with visible supply overlap.",
            ),
            HighlightCard(
                label="P1 Prime Companies",
                value=str(p1_count),
                detail="Companies with UA SDK + high paid fraction + active networks — top outreach priority.",
            ),
        ]

    def _build_supporting_charts(self, apps: list[dict[str, Any]]) -> list[SupportingChart]:
        genre_counts = Counter((app.get("genre") or "Unknown") for app in apps)
        scale_counts = Counter(self._download_bucket(int(app.get("st_last_month_downloads") or 0)) for app in apps)

        return [
            SupportingChart(
                title="App Types",
                description="The active pool is still dominated by the strongest genres in the latest live dataset.",
                rows=self._chart_rows_from_counter(genre_counts, CHART_PALETTE, limit=4),
            ),
            SupportingChart(
                title="Download Scale",
                description="Latest-month download scale distribution across currently active apps.",
                rows=self._chart_rows_from_counter(scale_counts, CHART_PALETTE),
            ),
        ]

    def _build_filter_chips(
        self,
        companies: list[dict[str, Any]],
        apps: list[dict[str, Any]],
        options: TopListOptions,
    ) -> list[FilterChip]:
        top_focus = sum(
            1 for c in companies if self._priority_code(c.get("best_priority")) in {"P1", "P2"}
        )
        supply_on = sum(1 for c in companies if bool(c.get("any_moloco_supply")))
        ua_sdk_on = sum(1 for c in companies if bool(c.get("any_active_ua")))
        p1_apps   = sum(1 for a in apps if self._priority_code(a.get("priority")) == "P1")

        chips = [
            FilterChip(label="P1 + P2 Focus",   value=f"{top_focus} companies", tone="blue"),
            FilterChip(label="Supply Visible",   value=f"{supply_on} companies", tone="green"),
            FilterChip(label="Active UA Networks", value=f"{ua_sdk_on} companies", tone="purple"),
            FilterChip(label="P1 Prime Apps",    value=f"{p1_apps} apps"),
        ]

        if options.search:
            chips.append(FilterChip(label="Search", value=options.search))
        return chips

    def _distribution_module(
        self,
        title: str,
        caption: str,
        counter: Counter[str],
        palette: list[str],
        limit: int | None = None,
        chart_type: str | None = None,
    ) -> AnalysisModule:
        rows = self._analysis_rows_from_counter(counter, palette, limit)
        return AnalysisModule(title=title, caption=caption, chart_type=chart_type, rows=rows)

    def _chart_rows_from_counter(
        self,
        counter: Counter[str],
        palette: list[str],
        limit: int | None = None,
    ) -> list[SupportingChartRow]:
        total = max(sum(counter.values()), 1)
        items = counter.most_common(limit)
        return [
            SupportingChartRow(
                label=label,
                value=round((count / total) * 100),
                display=f"{round((count / total) * 100)}%",
                color=palette[index % len(palette)],
            )
            for index, (label, count) in enumerate(items)
        ]

    def _analysis_rows_from_counter(
        self,
        counter: Counter[str],
        palette: list[str],
        limit: int | None = None,
    ) -> list[AnalysisRow]:
        total = max(sum(counter.values()), 1)
        items = counter.most_common(limit)
        return [
            AnalysisRow(
                label=label,
                value=f"{round((count / total) * 100)}%",
                amount=round((count / total) * 100),
                color=palette[index % len(palette)],
            )
            for index, (label, count) in enumerate(items)
        ]

    def _gaming_by_priority_module(self, companies: list[dict]) -> AnalysisModule:
        _GAMING_COLORS = {"Gaming": "#3a86ff", "Non-Gaming": "#ff006e", "Unknown": "#94a3b8"}
        groups: list[AnalysisGroup] = []
        for tier in ("P1", "P2", "P3"):
            tier_companies = [c for c in companies if (c.get("best_priority") or "P3") == tier]
            counter: Counter[str] = Counter(c.get("team_routing") or "Unknown" for c in tier_companies)
            total = max(sum(counter.values()), 1)
            segments = [
                AnalysisRow(
                    label=label,
                    value=f"{count} ({round(count / total * 100)}%)",
                    amount=count,
                    color=_GAMING_COLORS.get(label, "#94a3b8"),
                )
                for label, count in counter.most_common()
            ]
            groups.append(AnalysisGroup(label=tier, segments=segments))
        return AnalysisModule(
            title="Gaming Mix by Priority",
            caption="Gaming vs Non-Gaming breakdown per priority tier (P1/P2/P3), based on company team_routing.",
            chart_type="stacked_group",
            groups=groups,
        )

    def _build_snapshot_data(
        self,
        companies: list[dict[str, Any]],
        apps: list[dict[str, Any]],
        priority_cards: list[PriorityCard],
    ) -> dict[str, Any]:
        """Build aggregated snapshot data for BQ storage and Gemini context."""
        p_counts = {card.tier: card.companies for card in priority_cards}
        return {
            "total_companies": len(companies),
            "total_apps": len(apps),
            "p1_count": p_counts.get("P1", 0),
            "p2_count": p_counts.get("P2", 0),
            "p3_count": p_counts.get("P3", 0),
            "team_routing": dict(
                Counter(c.get("team_routing") or "Unknown" for c in companies).most_common(8)
            ),
            "genre_mix": dict(
                Counter(a.get("genre") or "Unknown" for a in apps).most_common(8)
            ),
            "monetization_mix": dict(
                Counter(a.get("monetization_type") or "Unknown" for a in apps)
            ),
            "top_companies": [
                c.get("company_name")
                for c in companies
                if self._priority_code(c.get("best_priority")) == "P1"
            ][:10],
        }

    def _generate_summary_with_gemini(
        self,
        companies: list[dict[str, Any]],
        apps: list[dict[str, Any]],
        highlights: list[HighlightCard],
        priorities: list[PriorityCard],
        snapshot_diff: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        try:
            snapshot = self._build_snapshot_data(companies, apps, priorities)

            # Build delta from prospect_snapshot WoW diff
            delta: dict[str, Any] = {}
            if snapshot_diff and (snapshot_diff.get("new") or snapshot_diff.get("dropped")):
                delta = {
                    "new_apps_this_week": snapshot_diff.get("new", 0),
                    "dropped_apps_this_week": snapshot_diff.get("dropped", 0),
                }

            prompt = {
                "system_context": (
                    "You are an AI assistant for Moloco China NBS (New Business Sales) team. "
                    "InterSight is an internal BI operating system. "
                    "Supply SMB Cross-Sell tracks game publisher companies with NO Moloco SDK or UA "
                    "relationship — cold outreach targets for the sales team to pitch Moloco UA advertising. "
                    "The team routes prospects to specific AEs or agency partners (e.g., Qipeng, Jiuye) "
                    "based on genre, HQ country, and priority tier."
                ),
                "task": (
                    "Generate a structured weekly brief. "
                    "Base ALL analysis STRICTLY on the numbers provided. "
                    "Do NOT invent company names, statistics, or trends not in the data."
                ),
                "strict_rules": [
                    "Return ONLY valid JSON — no markdown, no backticks, no explanation.",
                    "All numbers must come exactly from the provided data.",
                    "Tone: professional, concise, internal analyst voice.",
                    "Avoid vague words: 'significant', 'crucial', 'pivotal' — be specific and numerical.",
                    "summary: 2-3 sentences on the overall queue state this week.",
                    "opportunity: 1 sentence on why this queue matters to the sales team right now.",
                    "big_things: exactly 3 strings, each a key signal from THIS week. Reference actual numbers.",
                    "week_changes: exactly 3 strings if previous_week data is present, else empty list [].",
                    "  Each week_changes item must reference specific deltas (e.g., 'P1 +3 vs last week (15 → 18)').",
                ],
                "output_schema": {
                    "summary": "string",
                    "opportunity": "string",
                    "big_things": ["string", "string", "string"],
                    "week_changes": ["string (or empty list if no prev data)"],
                },
                "current_week": {
                    "total_companies": snapshot["total_companies"],
                    "total_apps": snapshot["total_apps"],
                    "priority_breakdown": {
                        "P1": snapshot["p1_count"],
                        "P2": snapshot["p2_count"],
                        "P3": snapshot["p3_count"],
                    },
                    "team_routing": snapshot["team_routing"],
                    "top_genres": snapshot["genre_mix"],
                    "monetization_mix": snapshot["monetization_mix"],
                    "p1_company_names": snapshot["top_companies"],
                    "highlights": [h.model_dump() for h in highlights],
                },
                "previous_week": delta if delta else None,
            }

            if self.gemini is None:
                self.gemini = GeminiService()
            response_text = self.gemini.generate_weekly_brief(json.dumps(prompt, ensure_ascii=False))

            # Strip markdown fences if model adds them
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.rsplit("```", 1)[0].strip()

            parsed = json.loads(cleaned)
            return {
                "summary": str(parsed.get("summary") or "").strip(),
                "opportunity": str(parsed.get("opportunity") or "").strip(),
                "big_things": [str(s) for s in (parsed.get("big_things") or [])],
                "week_changes": [str(s) for s in (parsed.get("week_changes") or [])],
            }
        except Exception:
            return {}

    def _to_company_row(self, company: dict[str, Any]) -> dict[str, Any]:
        priority = company.get("best_priority") or "P3"
        return {
            "company_name": company.get("company_name") or "Unknown",
            "priority": priority,
            "company_prospect_label": priority,
            "hq_country": company.get("hq_country") or "Unknown",
            "final_hq_country": company.get("hq_country") or "Unknown",  # alias for compat
            "website": company.get("website") or "",
            "team_routing": company.get("team_routing") or "Unknown",
            "app_count": int(company.get("app_count") or 0),
            "total_apps": int(company.get("app_count") or 0),
            "os_mix": company.get("os_mix") or "",
            "genres": company.get("genres") or "",
            "total_downloads": int(company.get("total_downloads") or 0),
            "total_downloads_latest_month": int(company.get("total_downloads") or 0),
            "total_mau": int(company.get("total_mau") or 0),
            "max_paid_frac": round(float(company.get("max_paid_frac") or 0), 4),
            "best_priority": priority,
            "monetization_types": company.get("monetization_types") or "Unknown",
            "any_active_ua": bool(company.get("any_active_ua")),
            "all_ua_networks": company.get("all_ua_networks") or "No Active Networks",
            "all_active_networks": company.get("all_ua_networks") or "No Active Networks",
            "is_moloco_supply_visible": bool(company.get("any_moloco_supply")),
            "any_moloco_supply": bool(company.get("any_moloco_supply")),
            "moloco_media_cost_30d": int(company.get("total_moloco_cost_30d") or 0),
        }

    def _to_app_row(self, app: dict[str, Any]) -> dict[str, Any]:
        priority = app.get("priority") or "P3"
        # Extract first country from top_countries JSON array as T1 proxy
        top_countries_raw = app.get("top_countries") or "[]"
        try:
            import json as _json
            top_countries = _json.loads(top_countries_raw) if isinstance(top_countries_raw, str) else top_countries_raw
            top_country = top_countries[0] if top_countries else "Unknown"
        except Exception:
            top_country = "Unknown"
        return {
            "app_market_bundle": app.get("app_market_bundle") or "",
            "os": app.get("os") or "",
            "priority": priority,
            "prospect_label": priority,
            "app_name": app.get("app_name") or "Unknown",
            "company_name": app.get("company_name") or "Unknown",
            "team_routing": app.get("team_routing") or "Unknown",
            "genre": app.get("genre") or "Unknown",
            "monetization_type": app.get("monetization_type") or "Unknown",
            "downloads_latest_month": int(app.get("st_last_month_downloads") or 0),
            "download_growth_rate_mom": 0.0,
            "active_ua_networks": app.get("active_ua_networks") or "No Active Networks",
            "is_moloco_supply_visible": bool(app.get("is_moloco_supply_visible")),
            "moloco_media_cost_usd_30d": int(app.get("moloco_media_cost_30d") or 0),
            "top_dl_country_t1": top_country,
            "active_other_exchange_sdks": "None",
        }

    def _fallback_summary(
        self,
        companies: list[dict[str, Any]],
        apps: list[dict[str, Any]],
        highlights: list[HighlightCard],
    ) -> str:
        visible_companies = sum(1 for company in companies if bool(company.get("is_moloco_supply_visible")))
        return (
            f"Moloco can already see supply from {visible_companies} companies in the active queue, "
            f"while the top P1 and P2 pool still centers on software, utility, and hybrid monetization. "
            f"The current dataset spans {len(companies)} companies and {len(apps)} apps, with "
            f"{highlights[1].value} as the median visible media-cost signal."
        )

    def _fallback_opportunity(self, companies: list[dict[str, Any]], apps: list[dict[str, Any]]) -> str:
        return (
            f"This queue turns {len(companies)} companies and {len(apps)} app-level prospects into a live operating list "
            "for direct NBS outreach, agency routing, and AI-assisted follow-up."
        )

    def _compute_funnel(self, companies: list[dict], apps: list[dict]) -> list[FunnelStep]:
        """
        Build 4-step selection funnel from in-memory company/app data.

        Step 1  Cold Prospect Pool  ≥20K DL, international-first, no Moloco SDK/UA — output of pipeline
        Step 2  Supply Visible      Moloco already buys their exchange inventory (any_moloco_supply)
        Step 3  UA SDK Present      Has competing UA SDK (AppLovin/ironSource/etc.) — P1+P2 pool
        Step 4  P1 Prime            paid_frac ≥50% + active UA networks — top outreach priority
        """
        total_cos = len(companies)
        total_apps_count = len(apps)

        # Step 2: supply visible (Moloco buys their exchange inventory)
        visible_cos = [c for c in companies if c.get("any_moloco_supply")]
        visible_names = {c.get("company_name") for c in visible_cos}
        visible_apps = [a for a in apps if (a.get("company_name") or "") in visible_names]

        # Step 3: UA SDK present = apps individually prioritised P1 or P2
        ua_sdk_apps = [a for a in apps if self._priority_code(a.get("priority")) in {"P1", "P2"}]
        ua_sdk_cos = {a.get("company_name") for a in ua_sdk_apps}

        # Step 4: P1 apps only — paid_frac ≥50% + active UA networks
        p1_apps = [a for a in apps if self._priority_code(a.get("priority")) == "P1"]
        p1_cos = {a.get("company_name") for a in p1_apps}

        return [
            FunnelStep(
                label="Cold Prospect Pool",
                description="≥20K monthly downloads · international-first · no Moloco SDK or UA spend · has monetization (IAA/IAP/Hybrid)",
                companies=total_cos,
                apps=total_apps_count,
            ),
            FunnelStep(
                label="Supply Visible",
                description="Moloco already buys their exchange inventory — supply relationship exists, direct cross-sell signal",
                companies=len(visible_cos),
                apps=len(visible_apps),
            ),
            FunnelStep(
                label="UA SDK Present",
                description="App has AppLovin / ironSource / Mintegral / Pangle etc. — actively monetising on competitor UA networks (paid_frac ≥20%)",
                companies=len(ua_sdk_cos),
                apps=len(ua_sdk_apps),
            ),
            FunnelStep(
                label="P1 Prime Targets",
                description="Paid downloads ≥50% + active UA networks confirmed — highest conversion probability",
                companies=len(p1_cos),
                apps=len(p1_apps),
            ),
        ]

    def _selection_steps(self) -> list[dict[str, str]]:
        return [
            {
                "title": "Step 1",
                "subtitle": "Scale + Market",
                "detail": "≥20K latest-month downloads (SensorTower). International-first — app's primary download market is not the developer's home country.",
            },
            {
                "title": "Step 2",
                "subtitle": "No Moloco Relationship",
                "detail": "Exclude apps with any Moloco SDK integration or active UA advertiser spend. Clean cold targets only.",
            },
            {
                "title": "Step 3",
                "subtitle": "Supply Signal",
                "detail": "Check supply_demand_overlap: does Moloco already buy this app's exchange inventory? Visible apps are the strongest cross-sell candidates.",
            },
            {
                "title": "Step 4",
                "subtitle": "UA Intent Scoring",
                "detail": "Score by UA SDK presence (AppLovin / ironSource / Mintegral / Pangle) and paid download fraction from SensorTower. P1 = paid_frac ≥50% + active networks. P2 = paid_frac ≥20%.",
            },
        ]

    def _download_bucket(self, downloads: int) -> str:
        if downloads < 50000:
            return "20K - 50K"
        if downloads < 100000:
            return "50K - 100K"
        if downloads < 500000:
            return "100K - 500K"
        return "500K+"

    def _growth_bucket(self, growth: float) -> str:
        if growth < 0:
            return "-10% to 0%"
        if growth < 0.1:
            return "0% to 10%"
        if growth < 0.5:
            return "10% to 50%"
        return "50%+"

    def _priority_code(self, label: Any) -> str:
        text = str(label or "")
        for tier in ("P1", "P2", "P3"):
            if tier in text:
                return tier
        return "P3"

    def _priority_rank(self, label: Any) -> int:
        mapping = {"P1": 1, "P2": 2, "P3": 3}
        return mapping.get(self._priority_code(label), 3)

    def _current_month_label(self) -> str:
        return datetime.now(UTC).strftime("%B %Y")

    def _current_timestamp_label(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def _cache_get(self, key: str) -> Any | None:
        with _cache_lock:
            value = _cache.get(key)
            if not value:
                return None
            payload, timestamp = value
            if time.monotonic() - timestamp > _cache_ttl_seconds:
                _cache.pop(key, None)
                return None
            return payload

    def _cache_set(self, key: str, payload: Any) -> None:
        with _cache_lock:
            _cache[key] = (payload, time.monotonic())

    # ── Bundle enrichment ──────────────────────────────────────────────────────

    def enrich_bundles(self, csv_bytes: bytes, bundle_id_column: str = "bundle_id") -> list[dict[str, Any]]:
        """Parse a CSV upload, look up each bundle_id in BQ, return original rows
        plus Moloco diagnosis columns appended on the right."""
        import csv
        import io

        text = csv_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return []

        # Auto-detect bundle_id column
        headers = list(rows[0].keys())
        if bundle_id_column not in headers:
            for candidate in ["bundle_id", "Bundle ID", "app_id", "package_name", "bundleId", "BundleID"]:
                if candidate in headers:
                    bundle_id_column = candidate
                    break
            else:
                raise ValueError(f"Column '{bundle_id_column}' not found. Available columns: {headers}")

        # Normalise iOS bundle_ids: "1234567890.0" → "1234567890"
        def _clean(bid: str) -> str:
            bid = bid.strip()
            if bid.endswith(".0") and bid[:-2].isdigit():
                bid = bid[:-2]
            return bid

        bundle_ids = [_clean(str(r.get(bundle_id_column, ""))) for r in rows]
        unique_ids = [b for b in dict.fromkeys(bundle_ids) if b]
        if not unique_ids:
            return [dict(r) | {"moloco_diagnosis": "⚠ NO_BUNDLE_ID"} for r in rows]

        ids_sql = ", ".join(f"'{b}'" for b in unique_ids)
        sql = f"""
        WITH
        target AS (
          SELECT bundle_id FROM UNNEST([{ids_sql}]) AS bundle_id
        ),
        sdk_check AS (
          SELECT DISTINCT req.app_bundle AS bundle_id
          FROM `ads-bpd-guard-china.gtm.fact_supply_with_tracking_publisher`
          WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
            AND exchange LIKE 'MOLOCO_SDK%'
            AND req.app_bundle IN (SELECT bundle_id FROM target)
        ),
        ua_check AS (
          SELECT
            product.app_market_bundle AS bundle_id,
            ROUND(SUM(gross_spend_usd), 0) AS ua_spend_90d
          FROM `ads-bpd-guard-china.athena.fact_dsp_core`
          WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
            AND gross_spend_usd > 0
            AND product.app_market_bundle IN (SELECT bundle_id FROM target)
          GROUP BY 1
        ),
        meta AS (
          SELECT
            app_market_bundle,
            MAX(sensortower.product.app_name)   AS st_app_name,
            MAX(sensortower.company.name)        AS st_company,
            MAX(sensortower.company.hq_country)  AS st_hq_country,
            MAX(CAST(sensortower.product.has_ads AS STRING)) AS has_ads,
            MAX(CAST(sensortower.product.has_iap AS STRING)) AS has_iap,
            MAX(CASE
              WHEN NOT sensortower.product.has_ads AND NOT sensortower.product.has_iap THEN 'Free'
              WHEN NOT sensortower.product.has_ads AND sensortower.product.has_iap     THEN 'IAP'
              WHEN sensortower.product.has_ads AND NOT sensortower.product.has_iap     THEN 'IAA'
              ELSE 'Hybrid'
            END) AS st_monetization
          FROM `ads-bpd-guard-china.athena.dim1_app_v3`
          WHERE app_market_bundle IN (SELECT bundle_id FROM target)
          GROUP BY 1
        )
        SELECT
          t.bundle_id,
          m.st_app_name,
          m.st_company,
          m.st_hq_country,
          m.st_monetization,
          sdk.bundle_id IS NOT NULL              AS has_moloco_sdk,
          COALESCE(ua.ua_spend_90d, 0)           AS moloco_ua_spend_90d,
          CASE
            WHEN sdk.bundle_id IS NOT NULL             THEN '① HAS_SDK'
            WHEN COALESCE(ua.ua_spend_90d, 0) > 0     THEN '② HAS_UA'
            WHEN m.app_market_bundle IS NULL           THEN '④ NOT_IN_ST'
            WHEN m.st_monetization = 'Free'            THEN '⑤ FREE'
            WHEN m.has_ads = 'false' AND m.has_iap = 'true' THEN '③ PURE_IAP'
            ELSE                                            '✅ PROSPECT'
          END AS moloco_diagnosis
        FROM target t
        LEFT JOIN sdk_check sdk ON t.bundle_id = sdk.bundle_id
        LEFT JOIN ua_check  ua  ON t.bundle_id = ua.bundle_id
        LEFT JOIN meta      m   ON t.bundle_id = m.app_market_bundle
        """

        enrichment_map: dict[str, dict[str, Any]] = {
            r["bundle_id"]: r for r in self.bigquery.query(sql)
        }

        result = []
        for row, bid in zip(rows, bundle_ids):
            e = enrichment_map.get(bid, {})
            merged = dict(row)
            merged["moloco_diagnosis"]    = e.get("moloco_diagnosis", "④ NOT_IN_ST")
            merged["moloco_has_sdk"]      = str(e.get("has_moloco_sdk", False)).lower()
            merged["moloco_ua_spend_90d"] = str(int(e.get("moloco_ua_spend_90d", 0)))
            merged["st_app_name"]         = e.get("st_app_name") or ""
            merged["st_company"]          = e.get("st_company") or ""
            merged["st_hq_country"]       = e.get("st_hq_country") or ""
            merged["st_monetization"]     = e.get("st_monetization") or ""
            result.append(merged)

        return result
