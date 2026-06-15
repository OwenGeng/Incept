from typing import Literal, Optional

from pydantic import BaseModel


class InsightItem(BaseModel):
    type: Literal["action", "alert", "trend", "success"]
    text: str
    detail: Optional[str] = None
    severity: Literal["warning", "info", "success", "neutral"] = "info"


class AgentStatus(BaseModel):
    name: str
    status: Literal["live", "warming", "idle"]
    detail: str
    badge: Optional[str] = None


class ActivityItem(BaseModel):
    company_name: Optional[str] = None
    action: str
    detail: str
    date: str
    activated_by: Optional[str] = None


class CallPrepCompany(BaseModel):
    company_name: str
    prospect_label: str
    hq_country: str
    team_routing: str
    total_apps: int
    is_supply_visible: bool


# ── Expert analysis (Gemini structured output) ────────────────────────────────

class TrendItem(BaseModel):
    metric: str
    direction: Literal["up", "down", "stable"]
    change: str
    interpretation: str


class AnomalyItem(BaseModel):
    title: str
    detail: str
    severity: Literal["warning", "info", "critical"]


class RecommendationItem(BaseModel):
    priority: int
    action: str
    reasoning: str


class ExpertAnalysis(BaseModel):
    summary: str
    trends: list[TrendItem] = []
    anomalies: list[AnomalyItem] = []
    recommendations: list[RecommendationItem] = []
    health_score: int = 0
    health_label: str = ""
    generated_at: Optional[str] = None  # ISO timestamp
    weeks_of_history: int = 0           # how many historical snapshots were used


# ── Top-level payload ─────────────────────────────────────────────────────────

class AiInsightsPayload(BaseModel):
    scope: str = "no-sdk-no-ua"
    insights: list[InsightItem]
    agents: list[AgentStatus]
    recent_activity: list[ActivityItem]
    call_prep_companies: list[CallPrepCompany]
    memory_summary: str
    expert_analysis: Optional[ExpertAnalysis] = None
    total_prospects: int
    p1_count: int
    p2_count: int
    leads_total: int
    spending_count: int
