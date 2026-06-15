from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Business context injected into every expert analysis ──────────────────────
_SUPPLY_SYSTEM_PROMPT = """
You are an expert business analyst for Moloco's NBS (New Business Sales) China GTM team.
You specialize in Supply-side cross-sell intelligence for the Chinese mobile app market.

Key business context:
- Goal: identify Chinese mobile app publishers who should adopt Moloco DSP supply-side SDK
- Prospect tiers:
    P1 (Prime)  — SDK not installed, strong UA spend signal, Moloco supply already visible → highest priority
    P2 (Strong) — SDK not installed, confirmed supply signal → strong outreach target
    P3 (Warm)   — partial signal, SDK not installed → nurture pipeline
    P4 (Cold)   — low signal or early-stage → monitor
- "Supply visible" means Moloco's DSP already buys this publisher's inventory → urgent conversion opportunity
- "Contacted" means AM has added the company to the lead pipeline
- "Spending" means the lead converted and is actively spending on Moloco DSP → cross-sell success
- Team routing: NBS China teams (NBS-CN, AM-CN, etc.) handle different publisher segments
- Data refreshes weekly via BigQuery ETL pipelines

Your job: analyze weekly snapshots + historical trends to surface actionable insights,
spot anomalies, and recommend concrete next steps. Be concise, specific, and business-oriented.
Never mention technical infrastructure. Respond ONLY with valid JSON matching the schema provided.
""".strip()


class GeminiService:
    def __init__(self) -> None:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.google_cloud_project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.google_cloud_location)
        os.environ.setdefault(
            "GOOGLE_GENAI_USE_ENTERPRISE",
            "True" if settings.google_genai_use_enterprise else "False",
        )
        self.client = genai.Client()

    def generate_weekly_brief(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        return response.text or ""

    def generate_expert_analysis(
        self,
        current: dict[str, Any],
        history: list[dict[str, Any]],
        leads_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a structured expert analysis using current + historical snapshots.
        Returns a dict matching ExpertAnalysis schema. Falls back to {} on failure.
        """
        history_lines = self._format_history(history)
        current_lines = self._format_snapshot(current, label="This week")

        prompt = f"""
Analyze the following Supply SMB weekly data and return a structured expert analysis.

=== HISTORICAL CONTEXT (oldest → newest) ===
{history_lines if history_lines else "No historical data yet — this is the first snapshot."}

=== CURRENT WEEK ===
{current_lines}

=== LEAD PIPELINE ===
- Total leads in pipeline: {leads_summary.get('total_leads', 0)}
- Actively spending: {leads_summary.get('spending', 0)}
- Sent (awaiting response): {leads_summary.get('sent', 0)}
- Opened / in discussion: {leads_summary.get('opened', 0)}
- Stale leads (sent >30 days): {leads_summary.get('stale', 0)}

=== OUTPUT SCHEMA ===
Return ONLY a JSON object with exactly this structure:
{{
  "summary": "<2–3 sentence executive overview of the current state and most important development this week>",
  "trends": [
    {{
      "metric": "<metric name>",
      "direction": "<up|down|stable>",
      "change": "<e.g. +3 (+15%) or -2 (-10%)>",
      "interpretation": "<1 sentence business meaning>"
    }}
  ],
  "anomalies": [
    {{
      "title": "<short title>",
      "detail": "<1–2 sentence explanation>",
      "severity": "<warning|info|critical>"
    }}
  ],
  "recommendations": [
    {{
      "priority": <1|2|3>,
      "action": "<concrete next step>",
      "reasoning": "<why this matters now based on data>"
    }}
  ],
  "health_score": <integer 0–100 representing overall pipeline health>,
  "health_label": "<Excellent|Good|Needs Attention|Critical>"
}}

Rules:
- Include 2–4 trend items (skip metrics with no meaningful change if history is short)
- Include 0–3 anomaly items (only flag genuine anomalies, not normal fluctuations)
- Include 2–3 recommendation items, ordered by priority
- If this is the first snapshot (no history), set trends to [] and focus summary on current state
- Be specific: use actual numbers from the data, not vague statements
"""

        response_schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "trends": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metric": {"type": "string"},
                            "direction": {"type": "string"},
                            "change": {"type": "string"},
                            "interpretation": {"type": "string"},
                        },
                    },
                },
                "anomalies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "detail": {"type": "string"},
                            "severity": {"type": "string"},
                        },
                    },
                },
                "recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "priority": {"type": "integer"},
                            "action": {"type": "string"},
                            "reasoning": {"type": "string"},
                        },
                    },
                },
                "health_score": {"type": "integer"},
                "health_label": {"type": "string"},
            },
            "required": ["summary", "trends", "anomalies", "recommendations", "health_score", "health_label"],
        }

        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_SUPPLY_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=0.3,
                ),
            )
            raw = response.text or ""
            return json.loads(raw)
        except Exception as exc:
            logger.warning("generate_expert_analysis failed: %s", exc)
            return {}

    # ── Formatting helpers ────────────────────────────────────────────────────

    def _format_snapshot(self, snap: dict[str, Any], label: str = "") -> str:
        week = snap.get("week_start_date", "unknown")
        prefix = f"[{label} — {week}]" if label else f"[{week}]"
        visible = snap.get("supply_visible_count", "n/a")
        contacted = snap.get("contacted_count", "n/a")
        return (
            f"{prefix}\n"
            f"  Total companies: {snap.get('total_companies', 'n/a')}\n"
            f"  P1: {snap.get('p1_count', 'n/a')} | P2: {snap.get('p2_count', 'n/a')} | "
            f"P3: {snap.get('p3_count', 'n/a')} | P4: {snap.get('p4_count', 'n/a')}\n"
            f"  Supply visible: {visible} | Contacted: {contacted}\n"
            f"  Top team: {self._top_key(snap.get('team_routing_json', {}))}"
        )

    def _format_history(self, history: list[dict[str, Any]]) -> str:
        if not history:
            return ""
        return "\n".join(self._format_snapshot(s) for s in history)

    def _top_key(self, d: dict) -> str:
        if not d:
            return "n/a"
        return max(d, key=lambda k: d[k], default="n/a")

