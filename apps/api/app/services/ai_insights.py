from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, timedelta
from typing import Any

from app.models.ai_insights import (
    ActivityItem,
    AgentStatus,
    AiInsightsPayload,
    AnomalyItem,
    CallPrepCompany,
    ExpertAnalysis,
    InsightItem,
    RecommendationItem,
    TrendItem,
)

logger = logging.getLogger(__name__)

_MEMORY_TTL = 4 * 3600       # 4 h — expert analysis cache
_SNAPSHOT_TTL = 24 * 3600    # 24 h — don't re-snapshot more than once per day
_HISTORY_WEEKS = 8           # how many past weeks to feed Gemini


def _starts_with(value: str | None, prefix: str) -> bool:
    return bool(value and str(value).startswith(prefix))


def _fmt_names(names: set[str], limit: int = 3) -> str:
    sorted_names = sorted(names)[:limit]
    suffix = f" +{len(names) - limit} more" if len(names) > limit else ""
    return ", ".join(sorted_names) + suffix


def _current_week_start() -> str:
    """Return ISO date string for the most recent Monday."""
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


class AiInsightsService:
    def __init__(self) -> None:
        self._analysis_cache: ExpertAnalysis | None = None
        self._analysis_cache_ts: float = 0.0
        self._analysis_lock = threading.Lock()
        self._snapshot_written_ts: float = 0.0

    def get_payload(
        self,
        companies: list[dict[str, Any]],
        leads: list[dict[str, Any]],
    ) -> AiInsightsPayload:
        insights = self._compute_insights(companies, leads)
        agents = self._compute_agent_status()
        activity = self._compute_activity(leads)
        call_prep = self._compute_call_prep(companies)
        expert = self._compute_expert_analysis(companies, leads)

        p1 = [c for c in companies if _starts_with(c.get("company_prospect_label"), "P1")]
        p2 = [c for c in companies if _starts_with(c.get("company_prospect_label"), "P2")]
        spending = [l for l in leads if l.get("status") == "spending"]

        return AiInsightsPayload(
            insights=insights,
            agents=agents,
            recent_activity=activity,
            call_prep_companies=call_prep,
            memory_summary=expert.summary if expert else "",
            expert_analysis=expert,
            total_prospects=len(companies),
            p1_count=len(p1),
            p2_count=len(p2),
            leads_total=len(leads),
            spending_count=len(spending),
        )

    # ── Expert analysis (Gemini + historical memory) ──────────────────────────

    def _compute_expert_analysis(
        self,
        companies: list[dict[str, Any]],
        leads: list[dict[str, Any]],
    ) -> ExpertAnalysis | None:
        now = time.monotonic()
        with self._analysis_lock:
            if self._analysis_cache and now - self._analysis_cache_ts < _MEMORY_TTL:
                logger.debug("[ai_insights] expert analysis cache hit")
                return self._analysis_cache

        try:
            from app.services.bigquery import BigQueryService
            from app.services.gemini import GeminiService

            bq = BigQueryService()
            gemini = GeminiService()

            # 1. Build current snapshot dict
            current = self._build_snapshot_dict(companies, leads)

            # 2. Auto-save snapshot if we haven't done so today
            self._maybe_write_snapshot(bq, current)

            # 3. Load historical snapshots (up to _HISTORY_WEEKS, excluding current week)
            week_start = _current_week_start()
            history = bq.read_historical_snapshots(
                n_weeks=_HISTORY_WEEKS, before_date=week_start
            )

            # 4. Build leads summary for the prompt
            leads_summary = self._build_leads_summary(leads)

            # 5. Call Gemini expert analysis
            raw = gemini.generate_expert_analysis(current, history, leads_summary)
            if not raw:
                return self._fallback_analysis(current, history)

            analysis = ExpertAnalysis(
                summary=raw.get("summary", ""),
                trends=[TrendItem(**t) for t in raw.get("trends", [])],
                anomalies=[AnomalyItem(**a) for a in raw.get("anomalies", [])],
                recommendations=[RecommendationItem(**r) for r in raw.get("recommendations", [])],
                health_score=raw.get("health_score", 0),
                health_label=raw.get("health_label", ""),
                generated_at=date.today().isoformat(),
                weeks_of_history=len(history),
            )

            with self._analysis_lock:
                self._analysis_cache = analysis
                self._analysis_cache_ts = time.monotonic()
            return analysis

        except Exception as exc:
            logger.warning("[ai_insights] expert analysis failed: %s", exc)
            return None

    def _maybe_write_snapshot(
        self, bq: Any, current: dict[str, Any]
    ) -> None:
        """Write a weekly snapshot to BQ at most once per day."""
        now = time.monotonic()
        if now - self._snapshot_written_ts < _SNAPSHOT_TTL:
            return
        week_start = _current_week_start()
        try:
            if not bq.snapshot_exists_for_week(week_start):
                bq.ensure_intersight_tables()
                bq.write_snapshot(week_start, current)
                logger.info("[ai_insights] wrote weekly snapshot for %s", week_start)
            self._snapshot_written_ts = time.monotonic()
        except Exception as exc:
            logger.warning("[ai_insights] snapshot write failed: %s", exc)

    def _build_snapshot_dict(
        self,
        companies: list[dict[str, Any]],
        leads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        p1 = [c for c in companies if _starts_with(c.get("company_prospect_label"), "P1")]
        p2 = [c for c in companies if _starts_with(c.get("company_prospect_label"), "P2")]
        p3 = [c for c in companies if _starts_with(c.get("company_prospect_label"), "P3")]
        p4 = [c for c in companies if _starts_with(c.get("company_prospect_label"), "P4")]
        visible = [c for c in companies if c.get("is_moloco_supply_visible")]
        contacted_names = {l.get("company_name", "") for l in leads}

        # Team routing distribution
        team_routing: dict[str, int] = {}
        for c in companies:
            team = c.get("team_routing") or "Unknown"
            team_routing[team] = team_routing.get(team, 0) + 1

        # Genre mix
        genre_mix: dict[str, int] = {}
        for c in companies:
            for app in (c.get("apps") or []):
                genre = app.get("genre") or "Unknown"
                genre_mix[genre] = genre_mix.get(genre, 0) + 1

        # Monetization mix
        monetization_mix: dict[str, int] = {}
        for c in companies:
            m = c.get("monetization_type") or "Unknown"
            monetization_mix[m] = monetization_mix.get(m, 0) + 1

        # Top companies (P1 supply visible first)
        top = sorted(
            [c for c in companies if _starts_with(c.get("company_prospect_label"), "P1")],
            key=lambda c: (0 if c.get("is_moloco_supply_visible") else 1),
        )[:10]
        top_companies = [
            {
                "name": c.get("company_name", ""),
                "label": c.get("company_prospect_label", ""),
                "supply_visible": bool(c.get("is_moloco_supply_visible")),
                "contacted": c.get("company_name", "") in contacted_names,
            }
            for c in top
        ]

        return {
            "week_start_date": _current_week_start(),
            "total_companies": len(companies),
            "total_apps": sum(int(c.get("total_apps") or 0) for c in companies),
            "p1_count": len(p1),
            "p2_count": len(p2),
            "p3_count": len(p3),
            "p4_count": len(p4),
            "supply_visible_count": len(visible),
            "contacted_count": len(contacted_names),
            "team_routing": team_routing,
            "team_routing_json": team_routing,
            "genre_mix": genre_mix,
            "genre_mix_json": genre_mix,
            "monetization_mix": monetization_mix,
            "monetization_mix_json": monetization_mix,
            "top_companies": top_companies,
            "top_companies_json": top_companies,
        }

    def _build_leads_summary(self, leads: list[dict[str, Any]]) -> dict[str, Any]:
        today = date.today()
        thirty_days_ago = (today - timedelta(days=30)).isoformat()
        stale = sum(
            1 for l in leads
            if l.get("status") == "sent"
            and str(l.get("activated_date") or "") < thirty_days_ago
        )
        return {
            "total_leads": len(leads),
            "spending": sum(1 for l in leads if l.get("status") == "spending"),
            "sent": sum(1 for l in leads if l.get("status") == "sent"),
            "opened": sum(1 for l in leads if l.get("status") == "opened"),
            "stale": stale,
        }

    def _fallback_analysis(
        self, current: dict[str, Any], history: list[dict[str, Any]]
    ) -> ExpertAnalysis:
        """Rule-based fallback when Gemini is unavailable."""
        p1 = current.get("p1_count", 0)
        p2 = current.get("p2_count", 0)
        visible = current.get("supply_visible_count", 0)
        total = current.get("total_companies", 0)
        summary = (
            f"Active prospect pool: {total} publishers, {p1} P1 and {p2} P2 priority companies. "
            f"{visible} have confirmed Moloco supply overlap — highest-priority conversion targets."
        )
        return ExpertAnalysis(
            summary=summary,
            trends=[],
            anomalies=[],
            recommendations=[
                RecommendationItem(
                    priority=1,
                    action=f"Prioritize outreach to {p1} P1 companies with supply overlap",
                    reasoning="These are highest-probability cross-sell targets.",
                )
            ] if p1 > 0 else [],
            health_score=0,
            health_label="",
            generated_at=date.today().isoformat(),
            weeks_of_history=len(history),
        )

    # ── Rule-based insights (fast, no Gemini) ─────────────────────────────────

    def _compute_insights(
        self,
        companies: list[dict[str, Any]],
        leads: list[dict[str, Any]],
    ) -> list[InsightItem]:
        insights: list[InsightItem] = []
        today = date.today()
        thirty_days_ago = (today - timedelta(days=30)).isoformat()
        contacted_names = {l.get("company_name", "") for l in leads}

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

        spending = [l for l in leads if l.get("status") == "spending"]
        if spending:
            insights.append(InsightItem(
                type="success",
                text=f"{len(spending)} converted leads are now actively spending on DSP",
                detail="Cross-sell attribution confirmed within 90-day window.",
                severity="success",
            ))

        return insights

    # ── Agent status ──────────────────────────────────────────────────────────

    def _compute_agent_status(self) -> list[AgentStatus]:
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

        history_note = (
            f"Using {_HISTORY_WEEKS}-week memory for trend analysis."
            if self._analysis_cache and self._analysis_cache.weeks_of_history > 0
            else "Building history — trend analysis improves each week."
        )

        return [
            AgentStatus(
                name="Supply Expert Agent",
                status="live" if self._analysis_cache else "warming",
                detail=f"Analyzes weekly data with {self._analysis_cache.weeks_of_history if self._analysis_cache else 0} weeks of historical memory. {history_note}",
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
                detail="Writes lead records and status updates to BigQuery supply_smb.lead_tracking.",
                badge=None,
            ),
        ]

    # ── Recent activity ───────────────────────────────────────────────────────

    def _compute_activity(self, leads: list[dict[str, Any]]) -> list[ActivityItem]:
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

    # ── Call prep ─────────────────────────────────────────────────────────────

    def _compute_call_prep(self, companies: list[dict[str, Any]]) -> list[CallPrepCompany]:
        p1p2 = [
            c for c in companies
            if _starts_with(c.get("company_prospect_label"), "P1")
            or _starts_with(c.get("company_prospect_label"), "P2")
        ]
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

    # ── SDK + No UA scope (list-1) ─────────────────────────────────────────────

    def get_sdk_no_ua_payload(
        self,
        companies: list[dict[str, Any]],
        rows: list[dict[str, Any]],
    ) -> AiInsightsPayload:
        total = len(companies)
        eligible = sum(
            1 for c in companies
            if "Eligible" in str(c.get("company_eligibility_statuses") or "")
        )
        high_value = sum(
            1 for c in companies
            if int(c.get("company_sdk_media_cost_usd_30d") or 0) >= 1000
        )
        no_manager = sum(
            1 for c in companies
            if not str(c.get("sdk_growth_managers") or "").strip()
        )

        insights: list[InsightItem] = []
        if no_manager:
            insights.append(InsightItem(
                type="alert",
                text=f"{no_manager} companies have no SDK Growth Manager assigned",
                detail="Review and assign managers to improve conversion rates.",
                severity="warning",
            ))
        if eligible:
            insights.append(InsightItem(
                type="action",
                text=f"{eligible} companies are eligibility-cleared for SDK activation",
                detail="These are the highest-priority outreach targets in this list.",
                severity="info",
            ))
        if high_value:
            insights.append(InsightItem(
                type="trend",
                text=f"{high_value} companies have SDK media cost > $1,000/month",
                detail="Strong monetization signal — existing SDK revenue motivates deeper engagement.",
                severity="info",
            ))
        team_dist: dict[str, int] = {}
        for c in companies:
            t = c.get("team_routing") or "Unknown"
            team_dist[t] = team_dist.get(t, 0) + 1
        if team_dist:
            top_team = max(team_dist, key=lambda k: team_dist[k])
            insights.append(InsightItem(
                type="trend",
                text=f"Team routing: {', '.join(f'{k} {v}' for k, v in sorted(team_dist.items(), key=lambda x: -x[1]))}",
                detail=f"{top_team} accounts for the largest share of this prospect pool.",
                severity="neutral",
            ))

        top_companies = sorted(
            companies,
            key=lambda c: int(c.get("company_sdk_media_cost_usd_30d") or 0),
            reverse=True,
        )[:10]
        call_prep = [
            CallPrepCompany(
                company_name=c.get("company_name", ""),
                prospect_label=f"${int(c.get('company_sdk_media_cost_usd_30d') or 0):,}/mo SDK",
                hq_country=c.get("final_hq_country", ""),
                team_routing=c.get("team_routing", ""),
                total_apps=int(c.get("total_sdk_apps") or 0),
                is_supply_visible=True,
            )
            for c in top_companies
        ]

        agents = self._compute_agent_status()
        summary = (
            f"SDK + No UA pool: {total} companies, {eligible} eligibility-cleared, "
            f"{high_value} generating > $1K/mo in SDK revenue. "
            f"{no_manager} companies have no assigned growth manager."
        )

        return AiInsightsPayload(
            scope="sdk-no-ua",
            insights=insights,
            agents=agents,
            recent_activity=[],
            call_prep_companies=call_prep,
            memory_summary=summary,
            total_prospects=total,
            p1_count=eligible,
            p2_count=high_value,
            leads_total=no_manager,
            spending_count=0,
        )

    # ── UA + No SDK scope (list-3) ─────────────────────────────────────────────

    def get_ua_no_sdk_payload(
        self,
        companies: list[dict[str, Any]],
        rows: list[dict[str, Any]],
    ) -> AiInsightsPayload:
        total = len(companies)
        with_ua = sum(
            1 for c in companies
            if int(c.get("existing_ua_spend_30d") or 0) > 0
        )
        high_ua = sum(
            1 for c in companies
            if int(c.get("existing_ua_spend_30d") or 0) >= 5000
        )
        total_untapped = sum(
            int(c.get("untapped_apps_count") or 0) for c in companies
        )

        insights: list[InsightItem] = []
        if with_ua:
            insights.append(InsightItem(
                type="trend",
                text=f"{with_ua} companies have active Moloco UA spend",
                detail="Existing DSP relationship makes SDK pitch warm — buyer knows Moloco already.",
                severity="info",
            ))
        if high_ua:
            insights.append(InsightItem(
                type="action",
                text=f"{high_ua} companies have UA spend > $5,000/month",
                detail="High-value UA buyers are the strongest SDK cross-sell targets.",
                severity="warning",
            ))
        if total_untapped:
            insights.append(InsightItem(
                type="trend",
                text=f"{total_untapped} individual apps across all companies are SDK-untapped",
                detail="Each untapped app is a direct SDK integration opportunity.",
                severity="neutral",
            ))
        team_dist: dict[str, int] = {}
        for c in companies:
            t = c.get("team_routing") or "Unknown"
            team_dist[t] = team_dist.get(t, 0) + 1
        if team_dist:
            insights.append(InsightItem(
                type="trend",
                text=f"Team routing: {', '.join(f'{k} {v}' for k, v in sorted(team_dist.items(), key=lambda x: -x[1]))}",
                detail="Distribution of UA buyers by team responsibility.",
                severity="neutral",
            ))

        top_companies = sorted(
            companies,
            key=lambda c: (
                int(c.get("existing_ua_spend_30d") or 0)
                + int(c.get("existing_sdk_media_cost_30d") or 0)
            ),
            reverse=True,
        )[:10]
        call_prep = [
            CallPrepCompany(
                company_name=c.get("company_name", ""),
                prospect_label=f"${int(c.get('existing_ua_spend_30d') or 0):,}/mo UA",
                hq_country=c.get("final_hq_country", ""),
                team_routing=c.get("team_routing", ""),
                total_apps=int(c.get("untapped_apps_count") or 0),
                is_supply_visible=False,
            )
            for c in top_companies
        ]

        agents = self._compute_agent_status()
        summary = (
            f"UA + No SDK pool: {total} companies with UA spend but no SDK integration. "
            f"{with_ua} currently active on Moloco DSP. "
            f"{total_untapped} individual apps across the pool are SDK-untapped."
        )

        return AiInsightsPayload(
            scope="ua-no-sdk",
            insights=insights,
            agents=agents,
            recent_activity=[],
            call_prep_companies=call_prep,
            memory_summary=summary,
            total_prospects=total,
            p1_count=with_ua,
            p2_count=high_ua,
            leads_total=total_untapped,
            spending_count=0,
        )
