from typing import Literal, Optional

from pydantic import BaseModel


PriorityTier = Literal["P1", "P2", "P3"]


class SelectionStep(BaseModel):
    title: str
    subtitle: str
    detail: str


class PriorityCard(BaseModel):
    tier: PriorityTier
    label: str
    companies: int
    apps: int | None = None
    delta: str
    note: str
    route: str


class HighlightCard(BaseModel):
    label: str
    value: str
    detail: str


class SupportingChartRow(BaseModel):
    label: str
    value: int
    display: str
    color: str


class SupportingChart(BaseModel):
    title: str
    description: str
    rows: list[SupportingChartRow]


class FunnelStep(BaseModel):
    label: str
    description: str
    companies: int
    apps: int


class WeeklyBriefPayload(BaseModel):
    title: str
    date_range: str
    refresh_status: str
    summary: str
    opportunity: str
    big_things: list[str] = []
    week_changes: list[str] = []
    selection_steps: list[SelectionStep]
    priorities: list[PriorityCard]
    highlights: list[HighlightCard]
    supporting_charts: list[SupportingChart]
    funnel_steps: list[FunnelStep] = []


class WeeklyBriefSummaryPayload(BaseModel):
    """AI-generated portion of the weekly brief — served separately so the
    rest of the page can render without waiting on the Gemini call."""
    summary: str
    opportunity: str
    big_things: list[str] = []
    week_changes: list[str] = []


class FilterChip(BaseModel):
    label: str
    value: str
    tone: str | None = None


class CompanyRow(BaseModel):
    company_name: str
    priority: PriorityTier
    company_prospect_label: str
    hq_country: str = ""
    final_hq_country: str = ""
    website: str = ""
    team_routing: str
    app_count: int = 0
    total_apps: int = 0
    os_mix: str = ""
    genres: str = ""
    total_downloads: int = 0
    total_downloads_latest_month: int = 0
    total_mau: int = 0
    max_paid_frac: float = 0.0
    monetization_types: str
    any_active_ua: bool = False
    all_ua_networks: str = ""
    all_active_networks: str = ""
    is_moloco_supply_visible: bool = False
    any_moloco_supply: bool = False
    moloco_media_cost_30d: int = 0


class AppRow(BaseModel):
    app_market_bundle: str
    os: str
    priority: PriorityTier
    prospect_label: str
    app_name: str
    company_name: str
    team_routing: str
    genre: str
    monetization_type: str
    downloads_latest_month: int
    download_growth_rate_mom: float
    active_ua_networks: str
    is_moloco_supply_visible: bool
    moloco_media_cost_usd_30d: int
    top_dl_country_t1: str
    active_other_exchange_sdks: str


class TopListsPayload(BaseModel):
    filters: list[FilterChip]
    companies: list[CompanyRow]
    apps: list[AppRow]
    company_page: int
    company_total: int
    app_page: int
    app_total: int
    page_size: int


class AnalysisRow(BaseModel):
    label: str
    value: str
    amount: int
    color: Optional[str] = None


class AnalysisGroup(BaseModel):
    label: str
    segments: list[AnalysisRow]


class AnalysisModule(BaseModel):
    title: str
    caption: str
    chart_type: Optional[str] = None  # "bar" | "pie" | "stacked_group"
    rows: list[AnalysisRow] = []
    groups: list[AnalysisGroup] = []


class MethodologySection(BaseModel):
    title: str
    items: list[str]


class DetailedAnalysisPayload(BaseModel):
    modules: list[AnalysisModule]
    methodology: list[MethodologySection]


class TableColumn(BaseModel):
    key: str
    label: str
    format: Literal["text", "number", "currency", "percent", "boolean", "badge"] = "text"
    width: str | None = None


class TableRow(BaseModel):
    key: str
    cells: dict[str, str | int | float | bool | None]


class GenericTablePayload(BaseModel):
    title: str
    subtitle: str
    columns: list[TableColumn]
    rows: list[TableRow]
    page: int
    total: int
    page_size: int
    sort_by: str
    sort_dir: str


class FilterOption(BaseModel):
    label: str
    value: str


class FilterControl(BaseModel):
    key: str
    label: str
    options: list[FilterOption]


class GenericTopListsPayload(BaseModel):
    dataset_key: str
    title: str
    subtitle: str
    filters: list[FilterChip]
    controls: list[FilterControl]
    companies_table: GenericTablePayload
    apps_table: GenericTablePayload


# ── Lead Tracking ──────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    company_name: str
    list_source: str        # "no-sdk-no-ua" | "list-1" | "list-2" | "list-3"
    team_routing: str
    sent_to_team: str       # agency or internal team name
    notes: str = ""
    activated_by: str       # user email


class LeadStatusUpdate(BaseModel):
    status: str             # "sent" | "opened" | "spending"
    notes: str = ""


class LeadRecord(BaseModel):
    lead_id: str
    company_name: str
    list_source: str
    team_routing: str
    sent_to_team: str
    notes: str
    activated_by: str
    status: str
    activated_date: str     # ISO date string
    last_updated: str       # ISO timestamp string
    converted_date: Optional[str] = None
    total_spend_90d: Optional[float] = None
    is_attributed: bool = False


class LeadListPayload(BaseModel):
    leads: list[LeadRecord]
    total: int
    attributed_count: int
    spending_count: int


class RefreshSnapshotResponse(BaseModel):
    week_start_date: str
    snapshot_written: bool
    message: str
