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
    badge: Optional[str] = None   # e.g. "Last run: Mon 06:12"


class ActivityItem(BaseModel):
    company_name: Optional[str] = None
    action: str
    detail: str
    date: str          # ISO date string
    activated_by: Optional[str] = None


class CallPrepCompany(BaseModel):
    company_name: str
    prospect_label: str
    hq_country: str
    team_routing: str
    total_apps: int
    is_supply_visible: bool


class AiInsightsPayload(BaseModel):
    insights: list[InsightItem]
    agents: list[AgentStatus]
    recent_activity: list[ActivityItem]
    call_prep_companies: list[CallPrepCompany]
    memory_summary: str
    total_prospects: int
    p1_count: int
    p2_count: int
    leads_total: int
    spending_count: int
