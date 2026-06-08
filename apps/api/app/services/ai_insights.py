from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

_MEMORY_TTL = 4 * 3600  # 4 h — same as main cache TTL

from app.models.ai_insights import (
    ActivityItem,
    AgentStatus,
    AiInsightsPayload,
    CallPrepCompany,
    InsightItem,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _starts_with(value: str | None, prefix: str) -> bool:
    return bool(value and str(value).startswith(prefix))


def _fmt_names(names: set[str], limit: int = 3) -> str:
    sorted_names = sorted(names)[:limit]
    suffix = f" +{len(names) - limit} more" if len(names) > limit else ""
    return ", ".join(sorted_names) + suffix


# ─────────────────────────────────────────────────────────────────────────────
# Main service
# ─────────────────────────────────────────────────────────────────────────────

class AiInsightsService:
    def __init__(self) -> None:
        self._memory_cache: str | None = None
        self._memory_cache_ts: float = 0.0

    def get_payload(
        self,
        companies: list[dict[str, Any]],
        leads: list[dict[str, Any]],
    ) -> AiInsightsPayload:
        insights = self._compute_insights(companies, leads)
        agents = self._compute_agent_status()
        activity = self._compute_activity(leads)
        call_prep = self._compute_call_prep(companies)
        memory = self._compute_memory(companies, leads)

        p1 = [c for c in companies if _starts_with(c.get("company_prospect_label"), "P1")]
        p2 = [c for c in companies if _starts_with(c.get("company_prospect_label"), "P2")]
        spending = [l for l in leads if l.get("status") == "spending"]

        return AiInsightsPayload(
            insights=insights,
            agents=agents,
            recent_activity=activity,
            call_prep_companies=call_prep,
            memory_summary=memory,
            total_prospects=len(companies),
            p1_count=len(p1),
            p2_count=len(p2),
            leads_total=len(leads),
            spending_count=len(spending),
        )

    # ── Insights ──────────────────────────────────────────────────────────────

    def _compute_insights(
        self,
        companies: list[dict[str, Any]],
        leads: list[dict[str, Any]],
    ) -> list[InsightItem]:
        insights: list[InsightItem] = []
        today = date.today()
        thirty_days_ago = (today - timedelta(days=30)).isoformat()

        contacted_names = {l.get("company_name", "") for l in leads}

        # 1. P1 not contacted
        p1_names = {
            c.get("company_name", "")
            for c in companies
            if _starts_with(c.get("company_prospect_label"), "P1")
        }
        uncontacted_p1 = p1_names - contacted_names
        if uncontacted_p1:
            insights.append(InsightItem(
                type="action",
                text=f"{len(uncontacted_p1)} P1 companies have not been contacted yet",
                detail=_fmt_names(uncontacted_p1),
                severity="warning",
            ))

        # 2. Stale leads — sent > 30 days
        stale = [
            l for l in leads
            if l.get("status") == "sent"
            and str(l.get("activated_date") or "") < thirty_days_ago
        ]
        if stale:
            stale_names = {l.get("company_name", "") for l in stale}
            insights.append(InsightItem(
                type="alert",
                text=f"{len(stale)} leads stuck in 'Sent' for over 30 days",
                detail=_fmt_names(stale_names),
                severity="warning",
            ))

        # 3. Supply visible ratio
        visible = [c for c in companies if c.get("is_moloco_supply_visible")]
        total = len(companies)
        if total > 0:
            pct = round(len(visible) / total * 100)
            insights.append(InsightItem(
                type="trend",
                text=f"{len(visible)} of {total} prospects ({pct}%) have Moloco-visible supply",
                detail="These are the highest-priority targets — Moloco already buys their inventory.",
                severity="info",
            ))

        # 4. P2 not contacted
        p2_names = {
            c.get("company_name", "")
            for c in companies
            if _starts_with(c.get("company_prospect_label"), "P2")
        }
        uncontacted_p2 = p2_names - contacted_names
        if uncontacted_p2:
            insights.append(InsightItem(
                type="action",
                text=f"{len(uncontacted_p2)} P2 companies are ready for outreach",
                detail="Strong-tier with confirmed supply signal.",
                severity="neutral",
            ))

        # 5. Active spenders
        spending = [l for l in leads if l.get("status") == "spending"]
        if spending:
            insights.append(InsightItem(
                type="success",
                text=f"{len(spending)} converted leads are now actively spending on DSP",
                detail="Cross-sell attribution confirmed within 90-day window.",
                severity="success",
            ))

        # 6. High-growth apps signal (from company data)
        # (company.total_apps with growth signal not directly available at company level —
        #  skip unless apps list is passed; keep this slot for future use)

        return insights

    # ── Agent Status ──────────────────────────────────────────────────────────

    def _compute_agent_status(self) -> list[AgentStatus]:
        # Import at call time to avoid circular deps
        from app.services.supply_smb_live import _cache, _cache_lock  # type: ignore[attr-defined]

        with _cache_lock:
            dataset_warm = "dataset" in _cache
            list1_warm = "custom:list-1" in _cache
            list2_warm = "custom:list-2" in _cache
            list3_warm = "custom:list-3" in _cache

        all_warm = all([dataset_warm, list1_warm, list2_warm, list3_warm])
        warm_labels = []
        if dataset_warm: warm_labels.append("No SDK+UA")
        if list1_warm:   warm_labels.append("List 1")
        if list2_warm:   warm_labels.append("List 2")
        if list3_warm:   warm_labels.append("List 3")

        return [
            AgentStatus(
                name="Weekly Supply Brief Agent",
                status="live",
                detail="Compiles P-tier movement, media-cost shifts, and AI-generated summary via Vertex AI.",
                badge="gemini-2.5-flash",
            ),
            AgentStatus(
                name="Dataset Cache Agent",
                status="live" if all_warm else "warming",
                detail=(
                    f"Datasets warm: {', '.join(warm_labels) or 'none yet — pre-warming in progress'}."
                    " Cache TTL 4 h, auto-refresh every 3 h."
                ),
                badge=f"{len(warm_labels)}/4 warm",
            ),
            AgentStatus(
                name="Lead Sync Agent",
                status="live",
                detail="Writes lead records and status updates to BigQuery intersight.lead_tracking.",
                badge=None,
            ),
        ]

    # ── Recent Activity ───────────────────────────────────────────────────────

    def _compute_activity(self, leads: list[dict[str, Any]]) -> list[ActivityItem]:
        """Derive the 8 most recent lead events from the leads list."""
        # Sort by last_updated desc
        sorted_leads = sorted(
            leads,
            key=lambda l: str(l.get("last_updated") or ""),
            reverse=True,
        )[:8]

        items: list[ActivityItem] = []
        for lead in sorted_leads:
            status = lead.get("status", "sent")
            action_map = {
                "sent": "Lead added",
                "opened": "Status → Opened",
                "spending": "Status → Spending ✓",
            }
            action = action_map.get(status, "Updated")
            last_updated = str(lead.get("last_updated") or "")
            date_str = last_updated[:10] if last_updated else ""

            items.append(ActivityItem(
                company_name=lead.get("company_name"),
                action=action,
                detail=f"{lead.get('list_source', '')} · routed to {lead.get('sent_to_team', '')}",
                date=date_str,
                activated_by=lead.get("activated_by"),
            ))

        return items

    # ── Call Prep Companies ───────────────────────────────────────────────────

    def _compute_call_prep(self, companies: list[dict[str, Any]]) -> list[CallPrepCompany]:
        """Return top 10 P1+P2 companies for the call prep selector."""
        p1p2 = [
            c for c in companies
            if _starts_with(c.get("company_prospect_label"), "P1")
            or _starts_with(c.get("company_prospect_label"), "P2")
        ]
        # Sort: P1 first, then P2; within tier by supply visible
        p1p2.sort(key=lambda c: (
            0 if _starts_with(c.get("company_prospect_label"), "P1") else 1,
            0 if c.get("is_moloco_supply_visible") else 1,
        ))
        return [
            CallPrepCompany(
                company_name=c.get("company_name", ""),
                prospect_label=c.get("company_prospect_label", ""),
                hq_country=c.get("final_hq_country", ""),
                team_routing=c.get("team_routing", ""),
                total_apps=int(c.get("total_apps") or 0),
                is_supply_visible=bool(c.get("is_moloco_supply_visible")),
            )
            for c in p1p2[:10]
        ]

    # ── Memory Summary (Gemini, cached 4 h) ──────────────────────────────────

    def _compute_memory(
        self,
        companies: list[dict[str, Any]],
        leads: list[dict[str, Any]],
    ) -> str:
        # Return cached summary if still fresh
        now = time.monotonic()
        if self._memory_cache and now - self._memory_cache_ts < _MEMORY_TTL:
            logger.debug("[ai_insights] memory cache hit")
            return self._memory_cache

        p1 = sum(1 for c in companies if _starts_with(c.get("company_prospect_label"), "P1"))
        p2 = sum(1 for c in companies if _starts_with(c.get("company_prospect_label"), "P2"))
        visible = sum(1 for c in companies if c.get("is_moloco_supply_visible"))
        contacted = len({l.get("company_name") for l in leads})
        spending = sum(1 for l in leads if l.get("status") == "spending")

        result: str | None = None
        try:
            from app.services.gemini import GeminiService
            gemini = GeminiService()
            prompt = (
                "You are an AI assistant for Moloco's New Business Sales team working on Supply SMB cross-sell. "
                "Write a concise 2-sentence operational summary (no bullet points, no headers) based on:\n"
                f"- Total prospect pool: {len(companies)} Chinese-origin publisher companies\n"
                f"- P1 (Prime): {p1} companies | P2 (Strong): {p2} companies\n"
                f"- Supply visible: {visible} companies (Moloco already buys their inventory)\n"
                f"- Contacted: {contacted} companies in lead pipeline | Active spenders: {spending}\n"
                "Focus on the business state and immediate action priority. Keep it under 40 words."
            )
            raw = gemini.generate_weekly_brief(prompt)
            if raw and len(raw.strip()) > 20:
                result = raw.strip()
        except Exception as exc:
            logger.warning(f"[ai_insights] Gemini summary failed: {exc}")

        # Fallback: rule-based summary
        if not result:
            result = (
                f"The active prospect pool contains {len(companies)} Chinese-origin publishers "
                f"with {p1} P1 and {p2} P2 priority companies — {visible} have confirmed Moloco supply overlap. "
                f"{contacted} companies are in the lead pipeline with {spending} actively spending on DSP."
            )

        # Cache the result
        self._memory_cache = result
        self._memory_cache_ts = time.monotonic()
        return result
