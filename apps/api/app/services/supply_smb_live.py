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
    # Explicit override — set INTERSIGHT_PROJECT_ROOT in Cloud Run env vars
    env_root = os.environ.get("INTERSIGHT_PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    # Auto-detect: walk up until we find a directory containing sql/
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "sql").exists():
            return candidate
    raise RuntimeError("Could not resolve InterSight project root")


PROJECT_ROOT = _project_root()
LIST_456_SQL = PROJECT_ROOT / "sql" / "list4_5_6_cold_prospects.sql"
LIST1_SQL = PROJECT_ROOT / "sql" / "list1_cold_prospect.sql"
LIST2_SQL = PROJECT_ROOT / "sql" / "list2_expansion.sql"
LIST3_SQL = PROJECT_ROOT / "sql" / "list3_supply_partner_upsdk.sql"

APP_QUERY_START = "-- =============================================================================\n-- TAB 1: COMPANY SUMMARY (default)"
APP_QUERY_COMMENT_START = "/*"
APP_QUERY_COMMENT_END = "*/"

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
            "Rows are limited to untapped bundles with sdk_media_cost_usd_30d above 10,000.",
        ],
        "company_key": "canonical_company",
        "company_columns": [
            ("company_name", "company_name", "text"),
            ("final_hq_country", "final_hq_country", "text"),
            ("team_routing", "team_routing", "text"),
            ("untapped_apps", "untapped_apps", "number"),
            ("total_sdk_apps", "total_sdk_apps", "number"),
            ("company_sdk_media_cost_usd_30d", "company_sdk_media_cost_usd_30d", "currency"),
            ("company_monetization_types", "company_monetization_types", "text"),
            ("company_eligibility_statuses", "company_eligibility_statuses", "text"),
        ],
        "app_columns": [
            ("canonical_company", "company_name", "text"),
            ("app_name", "app_name", "text"),
            ("bundle_id", "bundle_id", "text"),
            ("os", "os", "text"),
            ("genre", "genre", "text"),
            ("monetization_type", "monetization_type", "badge"),
            ("sdk_media_cost_usd_30d", "sdk_media_cost_usd_30d", "currency"),
            ("total_downloads_30d", "total_downloads_30d", "number"),
            ("top_dl_country", "top_dl_country", "text"),
            ("eligibility_status", "eligibility_status", "badge"),
        ],
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
        dataset = self._get_dataset()
        companies = dataset["companies"]
        apps = dataset["apps"]

        priority_cards = self._build_priority_cards(companies, apps)
        highlights = self._build_highlights(companies, apps)
        supporting_charts = self._build_supporting_charts(apps)

        # Try to load previous week's snapshot for comparison
        prev_snapshot: dict[str, Any] | None = None
        try:
            self._ensure_intersight()
            week_start = _current_week_start().isoformat()
            prev_snapshot = self.bigquery.read_previous_snapshot(before_date=week_start)
        except Exception:
            pass

        generated = self._generate_summary_with_gemini(
            companies, apps, highlights, priority_cards, prev_snapshot=prev_snapshot
        )

        funnel_steps = self._compute_funnel(companies, apps)

        return WeeklyBriefPayload(
            title="Supply SMB Cross-Sell",
            date_range=self._current_month_label(),
            refresh_status=f"BigQuery refresh synced {self._current_timestamp_label()}",
            summary=generated.get("summary") or self._fallback_summary(companies, apps, highlights),
            opportunity=generated.get("opportunity") or self._fallback_opportunity(companies, apps),
            big_things=generated.get("big_things") or [],
            week_changes=generated.get("week_changes") or [],
            selection_steps=self._selection_steps(),
            priorities=priority_cards,
            highlights=highlights,
            supporting_charts=supporting_charts,
            funnel_steps=funnel_steps,
        )

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
            apps = [a for a in apps if (a.get("company_name") or a.get("canonical_company") or "") in app_company_names]

        modules = [
            self._distribution_module(
                "Geography Distribution",
                "Verified HQ routing distribution across the active company pool.",
                Counter(company.get("final_hq_country") or "Unknown" for company in companies),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "Team Routing",
                "Current company mix for gaming versus non-gaming follow-up ownership.",
                Counter(company.get("team_routing") or "Unknown" for company in companies),
                CHART_PALETTE,
                chart_type="pie",
            ),
            self._distribution_module(
                "Monetization Mix",
                "App-level monetization types that shape the SDK and UA pitch path.",
                Counter((app.get("monetization_type") or "Unknown") for app in apps),
                CHART_PALETTE,
                chart_type="pie",
            ),
            self._distribution_module(
                "Genre Mix",
                "Top app genres in the current active cross-sell universe.",
                Counter((app.get("genre") or "Unknown") for app in apps),
                CHART_PALETTE,
                limit=5,
                chart_type="pie",
            ),
            self._distribution_module(
                "Download Scale",
                "Latest-month download buckets across active apps.",
                Counter(self._download_bucket(int(app.get("downloads_latest_month") or 0)) for app in apps),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "MoM Growth",
                "Month-over-month growth bands for active apps.",
                Counter(self._growth_bucket(float(app.get("download_growth_rate_mom") or 0)) for app in apps),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "Supply Visibility",
                "Priority and supply visibility split across the company queue.",
                Counter(company.get("company_prospect_label") or "Unknown" for company in companies),
                CHART_PALETTE,
            ),
            self._distribution_module(
                "Eligibility Status",
                "Moloco supply eligibility state seen on active app records.",
                Counter((app.get("sdl_eligibility_status") or "Undecided") for app in apps),
                CHART_PALETTE,
            ),
        ]

        methodology = [
            MethodologySection(
                title="Data Sources",
                items=[
                    "BigQuery prospect engine query from sql/list4_5_6_cold_prospects.sql",
                    "Sensor Tower app metadata, downloads, and network analysis tables",
                    "Moloco supply_demand_overlap and fact_dsp_publisher exchange signals",
                    "GTM HQ country triage overrides and BigQuery access configuration",
                ],
            ),
            MethodologySection(
                title="Inclusion Logic",
                items=[
                    "Latest full month downloads of at least 20,000",
                    "Primary market must be outside CN / HK / TW / MO",
                    "No Moloco SDK or Moloco UA relationship on the app or company path",
                    "Monetization must be IAA, IAP, or hybrid",
                ],
            ),
            MethodologySection(
                title="Ranking Logic",
                items=[
                    "Priority tier is inherited from the strongest company or app signal",
                    "Moloco supply visibility and media cost rank ahead of raw scale",
                    "Download momentum and active network breadth act as secondary tie-breakers",
                    "Top Lists can be filtered by priority, routing, supply visibility, and search",
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
        modules = self._build_custom_analysis_modules(rows, companies)
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
        sql = LIST_456_SQL.read_text(encoding="utf-8")
        return self.bigquery.query(sql)

    def _run_app_query(self) -> list[dict[str, Any]]:
        sql_text = LIST_456_SQL.read_text(encoding="utf-8")
        prefix, remainder = sql_text.split(APP_QUERY_START, maxsplit=1)
        comment_start = remainder.index(APP_QUERY_COMMENT_START)
        comment_end = remainder.index(APP_QUERY_COMMENT_END, comment_start)
        comment_block = remainder[comment_start + len(APP_QUERY_COMMENT_START) : comment_end]
        app_query = f"{prefix.rstrip()}\n{comment_block.strip()}"
        return self.bigquery.query(app_query)

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
                    cells={column[0]: row.get(column[0]) for column in columns},
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
        apps: list[dict[str, Any]],
        companies: list[dict[str, Any]],
    ) -> list[AnalysisModule]:
        return [
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
        ]

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
            priority = self._priority_code(company.get("company_prospect_label"))
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
            priority = self._priority_code(app.get("prospect_label"))
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
            if sort_by in {"company_prospect_label", "prospect_label"}:
                return self._priority_rank(row.get(sort_by))
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
            "P1": ("Prime", "NBS direct", "High media cost, strong scale, still growing."),
            "P2": ("Strong", "NBS + agency", "High-intent accounts ready for coordinated follow-up."),
            "P3": ("Visible", "Agency batch", "Moloco-visible or validated but lower urgency accounts."),
            "P4": ("Cold", "Monitor", "Longer-horizon prospects without strong near-term supply proof."),
        }

        cards: list[PriorityCard] = []
        for tier in ("P1", "P2", "P3", "P4"):
            company_count = sum(
                1 for company in companies if self._priority_code(company.get("company_prospect_label")) == tier
            )
            app_count = sum(1 for app in apps if self._priority_code(app.get("prospect_label")) == tier)
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
            if self._priority_code(company.get("company_prospect_label")) in {"P1", "P2"}
        ]
        focus_apps = [
            app for app in apps if self._priority_code(app.get("prospect_label")) in {"P1", "P2"}
        ]
        visible_companies = [
            company for company in companies if bool(company.get("is_moloco_supply_visible"))
        ]
        median_cost = 0
        if visible_companies:
            median_cost = round(
                statistics.median(
                    int(company.get("moloco_media_cost_usd_30d") or 0) for company in visible_companies
                )
            )
        exchange_ready_rate = 0
        if focus_apps:
            ready_count = sum(1 for app in focus_apps if bool(app.get("has_other_exchange_sdk")))
            exchange_ready_rate = round((ready_count / len(focus_apps)) * 100)

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
                label="Exchange SDK Readiness",
                value=f"{exchange_ready_rate}%",
                detail="Share of P1 + P2 apps already running on another exchange or mediation path.",
            ),
        ]

    def _build_supporting_charts(self, apps: list[dict[str, Any]]) -> list[SupportingChart]:
        genre_counts = Counter((app.get("genre") or "Unknown") for app in apps)
        scale_counts = Counter(self._download_bucket(int(app.get("downloads_latest_month") or 0)) for app in apps)

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
            1 for company in companies if self._priority_code(company.get("company_prospect_label")) in {"P1", "P2"}
        )
        growth_alerts = sum(1 for app in apps if float(app.get("download_growth_rate_mom") or 0) >= 0.2)
        ai_follow_up = sum(
            1
            for company in companies
            if (company.get("hq_country_source") or "ST_original") == "ST_original"
            or (company.get("apps_with_other_exchange_sdk") or 0) > 0
        )
        supply_on = sum(1 for company in companies if bool(company.get("is_moloco_supply_visible")))

        chips = [
            FilterChip(label="P1 + P2 Focus", value=f"{top_focus} companies", tone="blue"),
            FilterChip(label="Supply Visible", value=f"{supply_on} companies", tone="green"),
            FilterChip(label="MoM Alerts", value=f"{growth_alerts} fast-growth apps", tone="purple"),
            FilterChip(label="AI Suggested Follow-up", value=f"{ai_follow_up} accounts"),
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
            "p4_count": p_counts.get("P4", 0),
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
                if self._priority_code(c.get("company_prospect_label")) == "P1"
            ][:10],
        }

    def _generate_summary_with_gemini(
        self,
        companies: list[dict[str, Any]],
        apps: list[dict[str, Any]],
        highlights: list[HighlightCard],
        priorities: list[PriorityCard],
        prev_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            snapshot = self._build_snapshot_data(companies, apps, priorities)

            # Build delta if previous snapshot exists
            delta: dict[str, Any] = {}
            if prev_snapshot:
                delta = {
                    "companies_delta": snapshot["total_companies"] - int(prev_snapshot.get("total_companies") or 0),
                    "apps_delta": snapshot["total_apps"] - int(prev_snapshot.get("total_apps") or 0),
                    "p1_delta": snapshot["p1_count"] - int(prev_snapshot.get("p1_count") or 0),
                    "p2_delta": snapshot["p2_count"] - int(prev_snapshot.get("p2_count") or 0),
                    "prev_week": str(prev_snapshot.get("week_start_date") or ""),
                    "prev_total_companies": int(prev_snapshot.get("total_companies") or 0),
                    "prev_p1_count": int(prev_snapshot.get("p1_count") or 0),
                    "prev_genre_mix": prev_snapshot.get("genre_mix_json") or {},
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
                        "P4": snapshot["p4_count"],
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
        return {
            "company_name": company.get("company_name") or "Unknown",
            "priority": self._priority_code(company.get("company_prospect_label")),
            "company_prospect_label": company.get("company_prospect_label") or "P4 - Cold",
            "final_hq_country": company.get("final_hq_country") or company.get("sensortower_hq_country") or "Unknown",
            "team_routing": company.get("team_routing") or "Unknown",
            "monetization_types": company.get("monetization_types") or "Unknown",
            "total_apps": int(company.get("total_apps") or 0),
            "total_downloads_latest_month": int(company.get("total_downloads_latest_month") or 0),
            "is_moloco_supply_visible": bool(company.get("is_moloco_supply_visible")),
            "moloco_media_cost_30d": int(company.get("moloco_media_cost_usd_30d") or 0),
            "all_active_networks": company.get("all_active_networks") or "No Active Networks",
            "apps_with_other_exchange_sdk": int(company.get("apps_with_other_exchange_sdk") or 0),
        }

    def _to_app_row(self, app: dict[str, Any]) -> dict[str, Any]:
        return {
            "app_market_bundle": app.get("app_market_bundle") or "",
            "os": app.get("os") or "",
            "priority": self._priority_code(app.get("prospect_label")),
            "prospect_label": app.get("prospect_label") or "P4 - Cold",
            "app_name": app.get("app_name") or "Unknown",
            "company_name": app.get("company_name") or "Unknown",
            "team_routing": app.get("team_routing") or "Unknown",
            "genre": app.get("genre") or "Unknown",
            "monetization_type": app.get("monetization_type") or "Unknown",
            "downloads_latest_month": int(app.get("downloads_latest_month") or 0),
            "download_growth_rate_mom": float(app.get("download_growth_rate_mom") or 0),
            "active_ua_networks": app.get("active_ua_networks") or "No Active Networks",
            "is_moloco_supply_visible": bool(app.get("is_moloco_supply_visible")),
            "moloco_media_cost_usd_30d": int(app.get("moloco_media_cost_usd_30d") or 0),
            "top_dl_country_t1": app.get("top_dl_country_t1") or app.get("top_dl_country_T1") or "Unknown",
            "active_other_exchange_sdks": app.get("active_other_exchange_sdks") or "None",
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

    # Chinese-mainland HQ identifiers used in funnel computation
    _CHN_MAINLAND: frozenset[str] = frozenset({"CN", "CHN", "CHINA"})

    def _compute_funnel(self, companies: list[dict], apps: list[dict]) -> list[FunnelStep]:
        """
        Build 4-step selection funnel from in-memory company/app data.
        All four sets are derived without extra BQ queries.

        Step 1  All qualifying prospects  (Chinese-origin, ≥20K DL, no Moloco, non-domestic — already applied by SQL)
        Step 2  Supply visible            companies where Moloco already buys their supply
        Step 3  CHN mainland + visible   mainland China HQ + supply signal (core P1/P2 candidates)
        Step 4  P1 + P2                  top-priority active follow-up pool
        """
        total_cos = len(companies)
        total_apps_count = len(apps)

        # Step 2: supply visible (any HQ)
        visible_cos = [c for c in companies if c.get("is_moloco_supply_visible")]
        visible_names = {c.get("company_name") for c in visible_cos}
        visible_apps = [a for a in apps if (a.get("company_name") or "") in visible_names]

        # Step 3: CHN mainland HQ + supply visible
        chn_visible_cos = [
            c for c in visible_cos
            if (c.get("final_hq_country") or "").upper() in self._CHN_MAINLAND
        ]
        chn_visible_names = {c.get("company_name") for c in chn_visible_cos}
        chn_visible_apps = [a for a in apps if (a.get("company_name") or "") in chn_visible_names]

        # Step 4: P1 + P2
        p1p2_cos = [
            c for c in companies
            if (c.get("company_prospect_label") or "").startswith(("P1", "P2"))
        ]
        p1p2_names = {c.get("company_name") for c in p1p2_cos}
        p1p2_apps = [a for a in apps if (a.get("company_name") or "") in p1p2_names]

        return [
            FunnelStep(
                label="Chinese-Origin Prospects",
                description="Qualified pool: ≥20K downloads, international-first, no Moloco relationship",
                companies=total_cos,
                apps=total_apps_count,
            ),
            FunnelStep(
                label="Supply Visible",
                description="Moloco already buys their supply — strongest cross-sell signal",
                companies=len(visible_cos),
                apps=len(visible_apps),
            ),
            FunnelStep(
                label="CHN Mainland HQ",
                description="Mainland China HQ — filtered from supply-visible pool",
                companies=len(chn_visible_cos),
                apps=len(chn_visible_apps),
            ),
            FunnelStep(
                label="P1 + P2 Active Pool",
                description="Prime and strong-tier — ranked by media cost, downloads, and momentum",
                companies=len(p1p2_cos),
                apps=len(p1p2_apps),
            ),
        ]

    def _selection_steps(self) -> list[dict[str, str]]:
        return [
            {
                "title": "Step 1",
                "subtitle": "Universe",
                "detail": "Chinese-origin developers with at least 20K latest-month downloads and overseas-first traffic.",
            },
            {
                "title": "Step 2",
                "subtitle": "No Moloco relationship",
                "detail": "Exclude active SDK integrations, active advertiser spend, and known company-level Moloco relationships.",
            },
            {
                "title": "Step 3",
                "subtitle": "Supply visible",
                "detail": "Use supply_demand_overlap and publisher exchange signals to find titles Moloco already buys.",
            },
            {
                "title": "Step 4",
                "subtitle": "Priority routing",
                "detail": "Rank into P1-P4 using supply visibility, media cost, downloads, and momentum.",
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
        for tier in ("P1", "P2", "P3", "P4"):
            if tier in text:
                return tier
        return "P4"

    def _priority_rank(self, label: Any) -> int:
        mapping = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
        return mapping[self._priority_code(label)]

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
