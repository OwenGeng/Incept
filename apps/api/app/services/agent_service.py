from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

_DATASET_CONTEXT = {
    "no-sdk-no-ua": """Active dataset: NO-SDK + NO-UA (cold cross-sell targets)
- Publishers with no Moloco SDK and no Moloco UA spend — the main cold prospect pool.
- Prospect tiers: P1 (Prime), P2 (Strong), P3 (Warm), P4 (Cold) based on supply/demand signals.
- is_moloco_supply_visible: Moloco DSP already buys this publisher's inventory → urgent SDK conversion
- "Contacted" = AM added to pipeline; "Spending" = converted, actively earning on Moloco
- Key fields: company_prospect_label (tier), team_routing (NBS-CN / AM-CN), is_moloco_supply_visible, app_last_updated_time, downloads_latest_month""",

    "sdk-no-ua": """Active dataset: SDK + NO-UA (SDK integrated, no UA spend)
- Publishers with Moloco SDK integrated but zero Moloco UA (advertiser DSP) spend.
- Goal: convert SDK publishers into UA buyers.
- sdk_media_cost_usd_30d: Publisher's Moloco SDK revenue in last 30 days (key value signal)
- eligibility_status: Whether the app meets Moloco's monetization requirements
- sdl_sdk_growth_managers: Assigned SDK Growth Manager (empty = Unassigned)
- untapped_apps: Company apps without UA buying; total_sdk_apps: apps with SDK integrated
- Key fields per row: canonical_company, app_name, bundle_id, sdk_media_cost_usd_30d, eligibility_status, team_routing, total_downloads_30d""",

    "ua-no-sdk": """Active dataset: UA + NO-SDK (UA buyers without SDK)
- Active Moloco UA advertisers whose apps lack SDK integration.
- Goal: cross-sell SDK monetization to existing UA buyers.
- existing_ua_spend_30d: Their Moloco UA DSP spend in last 30 days (key commitment signal)
- existing_sdk_media_cost_30d: SDK revenue from apps that already have SDK
- existing_sdk_app_count: Apps in this company already with SDK
- untapped_apps_count: Apps in their portfolio with no SDK yet (the opportunity)
- Key fields per row: company_name, app_bundle, app_name, total_downloads_30d, active_ua_networks, team_routing""",
}


def _make_system_prompt(dataset: str) -> str:
    ctx = _DATASET_CONTEXT.get(dataset, _DATASET_CONTEXT["no-sdk-no-ua"])
    return f"""You are Linglong Analysis Assistant, a senior-level data analyst tool built into the Linglong platform.
You help users explore and analyze supply prospect data through conversation.

{ctx}

General context:
- Moloco is a programmatic DSP/SSP platform. Supply cross-sell = convincing app publishers to integrate Moloco SDK.
- Team routing: NBS-CN, AM-CN handle different segments (Gaming vs Non-Gaming, company size tiers)
- HQ countries are ISO-3 codes: CHN, HKG, TWN, MAC, SGP for the China / APAC region
- app_last_updated_time: when the app was last updated on the app store (SensorTower data)

When answering:
- Always use the provided tools to fetch data before answering — never guess numbers
- Be specific and cite actual figures from the data
- Focus on actionable insights
- Keep responses concise and business-oriented
- Use bullet points or tables when helpful""".strip()


_TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_summary",
        description=(
            "Get high-level aggregate metrics for the current dataset. "
            "Returns totals, key breakdowns (tiers, eligibility, spend), and team distribution. "
            "Use this for overview or 'how many' questions."
        ),
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="get_companies",
        description=(
            "Get a filtered list of prospect companies in the current dataset. "
            "For no-sdk-no-ua: filter by tier (P1/P2/P3/P4) and supply_visible. "
            "For all datasets: filter by team. "
            "Returns company-level aggregated data."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "tier": types.Schema(
                    type="STRING",
                    description="Filter by tier prefix: P1, P2, P3, P4. Only applies to no-sdk-no-ua dataset.",
                ),
                "team": types.Schema(
                    type="STRING",
                    description="Filter by team_routing value, e.g. 'NBS-CN'. Leave empty for all teams.",
                ),
                "supply_visible": types.Schema(
                    type="BOOLEAN",
                    description="Filter by Moloco supply visibility. Only applies to no-sdk-no-ua dataset.",
                ),
                "limit": types.Schema(
                    type="INTEGER",
                    description="Max number of companies to return. Default 100.",
                ),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="get_apps",
        description=(
            "Get a filtered list of individual apps in the current dataset. "
            "For no-sdk-no-ua: supports tier, supply_visible, and stale_months filters. "
            "For sdk-no-ua: each row is an app with SDK revenue and eligibility data. "
            "For ua-no-sdk: each row is an app with UA network data. "
            "All datasets support team and company_name filters."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "tier": types.Schema(
                    type="STRING",
                    description="Filter by tier: P1, P2, P3, P4. Only for no-sdk-no-ua dataset.",
                ),
                "team": types.Schema(
                    type="STRING",
                    description="Filter by team_routing. Leave empty for all teams.",
                ),
                "company_name": types.Schema(
                    type="STRING",
                    description="Filter apps by company name (partial match).",
                ),
                "stale_months": types.Schema(
                    type="INTEGER",
                    description=(
                        "Only return apps not updated in this many months. "
                        "Only for no-sdk-no-ua dataset."
                    ),
                ),
                "supply_visible": types.Schema(
                    type="BOOLEAN",
                    description="Filter by supply visibility. Only for no-sdk-no-ua dataset.",
                ),
                "limit": types.Schema(
                    type="INTEGER",
                    description="Max number of apps to return. Default 100.",
                ),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="get_app_update_distribution",
        description=(
            "Get distribution of apps by last-update age (app_last_updated_time). "
            "Returns counts in buckets: <3m, 3-6m, 6-12m, 1-2y, 2y+. "
            "Only meaningful for the no-sdk-no-ua dataset."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "tier": types.Schema(
                    type="STRING",
                    description="Optionally filter by tier: P1, P2, P3, P4.",
                ),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="lookup_apps_by_bundle",
        description=(
            "Look up detailed Moloco signal data for specific app bundle IDs (Android) or App Store IDs (iOS). "
            "Returns SDK supply impressions, SDK integration status, UA spend, eligibility, and company info. "
            "Use when the user mentions specific app IDs or bundle IDs, or wants to check a particular app's Moloco signals."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "bundle_ids": types.Schema(
                    type="ARRAY",
                    items=types.Schema(type="STRING"),
                    description="App bundle IDs (Android: e.g. 'com.example.app') or App Store IDs (iOS: numeric string).",
                ),
            },
            required=["bundle_ids"],
        ),
    ),
]

_TOOLS = [types.Tool(function_declarations=_TOOL_DECLARATIONS)]


# ── Data accessors ─────────────────────────────────────────────────────────────

def _get_data(dataset: str) -> dict[str, list[dict[str, Any]]]:
    from app.services.supply_smb_live import SupplySmbLiveService
    svc = SupplySmbLiveService()
    if dataset == "sdk-no-ua":
        rows = svc._get_custom_dataset_rows("list-1")
        companies = svc._build_custom_companies("list-1", rows)
        return {"rows": rows, "companies": companies}
    if dataset == "ua-no-sdk":
        rows = svc._get_custom_dataset_rows("list-3")
        companies = svc._build_custom_companies("list-3", rows)
        return {"rows": rows, "companies": companies}
    ds = svc._get_dataset()
    return {"rows": ds.get("apps", []), "companies": ds.get("companies", [])}


def _tier_matches(label: str | None, tier: str) -> bool:
    return bool(label and str(label).upper().startswith(tier.upper()))


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    from datetime import datetime
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except Exception:
        return None


# ── Tool implementations ───────────────────────────────────────────────────────

def _tool_get_summary(dataset: str) -> dict[str, Any]:
    try:
        data = _get_data(dataset)
        companies = data["companies"]
        rows = data["rows"]
    except Exception as exc:
        return {"error": str(exc)}

    team_dist: dict[str, int] = {}
    for c in companies:
        t = c.get("team_routing") or "Unknown"
        team_dist[t] = team_dist.get(t, 0) + 1

    base = {
        "dataset": dataset,
        "total_companies": len(companies),
        "total_apps": len(rows),
        "team_distribution": dict(sorted(team_dist.items(), key=lambda x: -x[1])[:8]),
    }

    if dataset == "no-sdk-no-ua":
        base.update({
            "p1_companies": sum(1 for c in companies if _tier_matches(c.get("company_prospect_label"), "P1")),
            "p2_companies": sum(1 for c in companies if _tier_matches(c.get("company_prospect_label"), "P2")),
            "p3_companies": sum(1 for c in companies if _tier_matches(c.get("company_prospect_label"), "P3")),
            "p4_companies": sum(1 for c in companies if _tier_matches(c.get("company_prospect_label"), "P4")),
            "supply_visible_companies": sum(1 for c in companies if c.get("is_moloco_supply_visible")),
        })
    elif dataset == "sdk-no-ua":
        eligibility: dict[str, int] = {}
        for r in rows:
            e = str(r.get("eligibility_status") or "Unknown")
            eligibility[e] = eligibility.get(e, 0) + 1
        base.update({
            "eligibility_breakdown": dict(sorted(eligibility.items(), key=lambda x: -x[1])),
            "unassigned_manager_apps": sum(
                1 for r in rows if not str(r.get("sdl_sdk_growth_managers") or "").strip()
            ),
            "total_sdk_revenue_30d_usd": int(sum(
                float(r.get("sdk_media_cost_usd_30d") or 0) for r in rows
            )),
        })
    elif dataset == "ua-no-sdk":
        base.update({
            "total_untapped_apps": sum(int(c.get("untapped_apps_count") or 0) for c in companies),
            "total_existing_ua_spend_30d_usd": int(sum(
                float(c.get("existing_ua_spend_30d") or 0) for c in companies
            )),
            "total_existing_sdk_revenue_30d_usd": int(sum(
                float(c.get("existing_sdk_media_cost_30d") or 0) for c in companies
            )),
        })

    return base


def _tool_get_companies(
    dataset: str,
    tier: str = "",
    team: str = "",
    supply_visible: bool | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        data = _get_data(dataset)
        companies = data["companies"]
    except Exception as exc:
        return {"error": str(exc)}

    if team:
        companies = [c for c in companies if (c.get("team_routing") or "").lower() == team.lower()]

    if dataset == "no-sdk-no-ua":
        if tier:
            companies = [c for c in companies if _tier_matches(c.get("company_prospect_label"), tier)]
        if supply_visible is True:
            companies = [c for c in companies if c.get("is_moloco_supply_visible")]
        elif supply_visible is False:
            companies = [c for c in companies if not c.get("is_moloco_supply_visible")]

    companies = companies[:limit]

    if dataset == "no-sdk-no-ua":
        return {
            "count": len(companies),
            "companies": [
                {
                    "company_name": c.get("company_name"),
                    "tier": c.get("company_prospect_label"),
                    "team_routing": c.get("team_routing"),
                    "total_apps": c.get("total_apps"),
                    "is_supply_visible": bool(c.get("is_moloco_supply_visible")),
                    "hq_country": c.get("final_hq_country"),
                    "genre": c.get("main_genre"),
                }
                for c in companies
            ],
        }

    if dataset == "sdk-no-ua":
        return {
            "count": len(companies),
            "companies": [
                {
                    "company_name": c.get("company_name"),
                    "team_routing": c.get("team_routing"),
                    "hq_country": c.get("final_hq_country"),
                    "total_sdk_apps": int(c.get("total_sdk_apps") or 0),
                    "untapped_apps": int(c.get("untapped_apps") or 0),
                    "sdk_revenue_30d_usd": int(c.get("company_sdk_media_cost_usd_30d") or 0),
                    "sdk_growth_manager": c.get("sdk_growth_managers") or "Unassigned",
                    "total_downloads_30d": int(c.get("total_downloads_30d") or 0),
                }
                for c in companies
            ],
        }

    # ua-no-sdk
    return {
        "count": len(companies),
        "companies": [
            {
                "company_name": c.get("company_name"),
                "team_routing": c.get("team_routing"),
                "hq_country": c.get("final_hq_country"),
                "untapped_apps_count": int(c.get("untapped_apps_count") or 0),
                "existing_sdk_apps": int(c.get("existing_sdk_app_count") or 0),
                "existing_sdk_revenue_30d": int(c.get("existing_sdk_media_cost_30d") or 0),
                "existing_ua_spend_30d": int(c.get("existing_ua_spend_30d") or 0),
                "total_downloads_30d": int(c.get("total_downloads_30d") or 0),
            }
            for c in companies
        ],
    }


def _tool_get_apps(
    dataset: str,
    tier: str = "",
    team: str = "",
    company_name: str = "",
    stale_months: int | None = None,
    supply_visible: bool | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        data = _get_data(dataset)
        rows = data["rows"]
    except Exception as exc:
        return {"error": str(exc)}

    if team:
        rows = [r for r in rows if (r.get("team_routing") or "").lower() == team.lower()]

    company_field = "canonical_company" if dataset == "sdk-no-ua" else "company_name"
    if company_name:
        rows = [r for r in rows if company_name.lower() in (r.get(company_field) or "").lower()]

    if dataset == "no-sdk-no-ua":
        if tier:
            rows = [r for r in rows if _tier_matches(r.get("prospect_label"), tier)]
        if supply_visible is True:
            rows = [r for r in rows if r.get("is_moloco_supply_visible")]
        elif supply_visible is False:
            rows = [r for r in rows if not r.get("is_moloco_supply_visible")]
        if stale_months is not None:
            cutoff = date.today() - timedelta(days=stale_months * 30)
            rows = [
                r for r in rows
                if (d := _parse_date(r.get("app_last_updated_time"))) is not None and d < cutoff
            ]

    rows = rows[:limit]

    if dataset == "no-sdk-no-ua":
        return {
            "count": len(rows),
            "apps": [
                {
                    "app_name": r.get("app_name"),
                    "company_name": r.get("company_name"),
                    "tier": r.get("prospect_label"),
                    "team_routing": r.get("team_routing"),
                    "genre": r.get("genre"),
                    "os": r.get("os"),
                    "app_last_updated_time": str(r.get("app_last_updated_time") or ""),
                    "is_supply_visible": bool(r.get("is_moloco_supply_visible")),
                    "downloads_latest_month": int(r.get("downloads_latest_month") or 0),
                }
                for r in rows
            ],
        }

    if dataset == "sdk-no-ua":
        return {
            "count": len(rows),
            "apps": [
                {
                    "app_name": r.get("app_name"),
                    "bundle_id": r.get("bundle_id"),
                    "company_name": r.get("canonical_company"),
                    "team_routing": r.get("team_routing"),
                    "os": r.get("os"),
                    "genre": r.get("genre"),
                    "sdk_revenue_30d_usd": int(float(r.get("sdk_media_cost_usd_30d") or 0)),
                    "eligibility_status": r.get("eligibility_status"),
                    "growth_manager": r.get("sdl_sdk_growth_managers") or "Unassigned",
                    "total_downloads_30d": int(r.get("total_downloads_30d") or 0),
                }
                for r in rows
            ],
        }

    # ua-no-sdk
    return {
        "count": len(rows),
        "apps": [
            {
                "app_name": r.get("app_name"),
                "bundle_id": r.get("app_bundle"),
                "company_name": r.get("company_name"),
                "team_routing": r.get("team_routing"),
                "os": r.get("os"),
                "total_downloads_30d": int(r.get("total_downloads_30d") or 0),
                "active_ua_networks": r.get("active_ua_networks"),
                "competitor_network_count": int(r.get("competitor_network_count") or 0),
            }
            for r in rows
        ],
    }


def _tool_get_app_update_distribution(dataset: str, tier: str = "") -> dict[str, Any]:
    if dataset != "no-sdk-no-ua":
        return {"note": "app_last_updated_time data is only available in the no-sdk-no-ua dataset."}

    try:
        data = _get_data(dataset)
        rows = data["rows"]
    except Exception as exc:
        return {"error": str(exc)}

    if tier:
        rows = [r for r in rows if _tier_matches(r.get("prospect_label"), tier)]

    today = date.today()
    buckets = {
        "under_3_months": 0,
        "3_to_6_months": 0,
        "6_to_12_months": 0,
        "1_to_2_years": 0,
        "over_2_years": 0,
        "unknown": 0,
    }

    for r in rows:
        d = _parse_date(r.get("app_last_updated_time"))
        if d is None:
            buckets["unknown"] += 1
            continue
        months_ago = (today - d).days / 30
        if months_ago < 3:
            buckets["under_3_months"] += 1
        elif months_ago < 6:
            buckets["3_to_6_months"] += 1
        elif months_ago < 12:
            buckets["6_to_12_months"] += 1
        elif months_ago < 24:
            buckets["1_to_2_years"] += 1
        else:
            buckets["over_2_years"] += 1

    total = len(rows)
    return {
        "total_apps": total,
        "tier_filter": tier or "all",
        "distribution": buckets,
        "distribution_pct": {
            k: round(v / total * 100, 1) if total else 0
            for k, v in buckets.items()
        },
    }


def _tool_lookup_apps_by_bundle(bundle_ids: list[str]) -> dict[str, Any]:
    if not bundle_ids:
        return {"error": "bundle_ids list is empty"}
    try:
        from app.services.bigquery import BigQueryService
        bq = BigQueryService()
        results = bq.lookup_bundles(bundle_ids)
        return {
            "count": len(results),
            "note": f"Looked up {len(bundle_ids)} bundle ID(s), found {len(results)} result(s).",
            "apps": results,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _dispatch_tool(name: str, args: dict[str, Any], dataset: str) -> Any:
    if name == "get_summary":
        return _tool_get_summary(dataset)
    if name == "get_companies":
        return _tool_get_companies(
            dataset,
            **{k: v for k, v in args.items() if k in ("tier", "team", "supply_visible", "limit")},
        )
    if name == "get_apps":
        return _tool_get_apps(
            dataset,
            **{k: v for k, v in args.items() if k in ("tier", "team", "company_name", "stale_months", "supply_visible", "limit")},
        )
    if name == "get_app_update_distribution":
        return _tool_get_app_update_distribution(
            dataset,
            **{k: v for k, v in args.items() if k in ("tier",)},
        )
    if name == "lookup_apps_by_bundle":
        return _tool_lookup_apps_by_bundle(args.get("bundle_ids", []))
    return {"error": f"unknown tool: {name}"}


# ── Agent service ──────────────────────────────────────────────────────────────

class AgentService:
    def __init__(self) -> None:
        self.client = genai.Client()

    async def chat(
        self,
        message: str,
        module: str,
        history: list[dict[str, str]],
        dataset: str = "no-sdk-no-ua",
    ) -> str:
        return await asyncio.to_thread(self._chat_sync, message, module, history, dataset)

    def _chat_sync(
        self,
        message: str,
        module: str,
        history: list[dict[str, str]],
        dataset: str = "no-sdk-no-ua",
    ) -> str:
        contents: list[types.Content] = []
        for msg in history:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=msg.get("content", ""))])
            )
        contents.append(
            types.Content(role="user", parts=[types.Part(text=message)])
        )

        config = types.GenerateContentConfig(
            system_instruction=_make_system_prompt(dataset) if module == "supply" else None,
            tools=_TOOLS if module == "supply" else None,
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ) if module == "supply" else None,
            temperature=0.4,
            max_output_tokens=2048,
        )

        try:
            for _ in range(5):  # max 5 tool-call rounds
                response = self.client.models.generate_content(
                    model=settings.gemini_model,
                    contents=contents,
                    config=config,
                )

                candidate = response.candidates[0] if response.candidates else None
                if not candidate:
                    break

                fn_calls = [
                    p.function_call
                    for p in (candidate.content.parts or [])
                    if getattr(p, "function_call", None)
                ]

                if not fn_calls:
                    return response.text or "I couldn't generate a response. Please try again."

                contents.append(candidate.content)

                result_parts: list[types.Part] = []
                for fc in fn_calls:
                    tool_result = _dispatch_tool(fc.name, dict(fc.args or {}), dataset)
                    result_parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fc.name,
                                response={"result": tool_result},
                            )
                        )
                    )
                contents.append(types.Content(role="user", parts=result_parts))

            return response.text or "I couldn't generate a response. Please try again."

        except Exception as exc:
            logger.warning("AgentService.chat failed: %s", exc)
            return "Sorry, I encountered an error processing your request. Please try again."
