/**
 * GET /api/export/csv/top-lists
 *
 * Exports ALL (no-sdk-no-ua) company or app data as a CSV file.
 * Bypasses pagination by passing page_size=9999 to the backend.
 *
 * Query params:
 *   table            "company" | "app"  (default: "company")
 *   priority         filter
 *   routing          filter
 *   supplyVisibility filter
 *   search           filter
 *   companySortBy / companySortDir
 *   appSortBy / appSortDir
 */

import { NextRequest } from "next/server";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import { toCsvString } from "@/lib/csv-export";

const API_BASE = (
  process.env.API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const INTERNAL_KEY = process.env.INCEPT_INTERNAL_API_KEY ?? "";

// ── Column definitions ────────────────────────────────────────────────────────

const COMPANY_HEADERS = [
  "Label", "Company", "HQ", "Routing", "Monetization",
  "Apps", "DL / mo", "Supply Visible", "Media Cost 30d", "Other Exch. SDK",
];

const APP_HEADERS = [
  "Label", "App", "Bundle", "OS", "Company", "Routing", "Genre",
  "Monetization", "DL / mo", "MoM %", "UA Networks",
  "Supply Visible", "Media Cost 30d", "Top DL Country",
];

// ── Route handler ─────────────────────────────────────────────────────────────

export async function GET(req: NextRequest) {
  // Auth check
  const session = isAuthDevSkipped() ? null : await auth();
  if (!isAuthDevSkipped() && !session?.user) {
    return new Response("Unauthorized", { status: 401 });
  }

  const sp = req.nextUrl.searchParams;
  const table = sp.get("table") ?? "company";

  // Build backend query — page_size=9999 fetches all rows
  const params = new URLSearchParams();
  const forward: [string, string | null][] = [
    ["priority",          sp.get("priority")],
    ["routing",           sp.get("routing")],
    ["supply_visibility", sp.get("supplyVisibility")],
    ["search",            sp.get("search")],
    ["company_sort_by",   sp.get("companySortBy")],
    ["company_sort_dir",  sp.get("companySortDir")],
    ["app_sort_by",       sp.get("appSortBy")],
    ["app_sort_dir",      sp.get("appSortDir")],
    ["company_page",      "1"],
    ["app_page",          "1"],
    ["page_size",         "9999"],
  ];
  for (const [k, v] of forward) {
    if (v) params.set(k, v);
  }

  const user = session?.user as { email?: string; role?: string } | null;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1/supply-smb/top-lists?${params}`, {
      cache: "no-store",
      headers: {
        "X-Internal-API-Key": INTERNAL_KEY,
        "X-User-Email":       user?.email ?? "",
        "X-User-Role":        user?.role  ?? "",
      },
    });
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }

  if (!res.ok) {
    return new Response(`Backend error ${res.status}`, { status: 502 });
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = (await res.json()) as any;

  // ── Serialize to CSV ──────────────────────────────────────────────────────
  let csv: string;
  let filename: string;

  if (table === "app") {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rows = (data.apps ?? []).map((r: any) => [
      r.prospect_label,
      r.app_name,
      r.app_market_bundle,
      r.os,
      r.company_name,
      r.team_routing,
      r.genre,
      r.monetization_type,
      r.downloads_latest_month,
      r.download_growth_rate_mom,
      r.active_ua_networks,
      r.is_moloco_supply_visible ? "Visible" : "Hidden",
      r.moloco_media_cost_usd_30d,
      r.top_dl_country_t1,
    ]);
    csv      = toCsvString(APP_HEADERS, rows);
    filename = "no-sdk-no-ua-apps.csv";
  } else {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rows = (data.companies ?? []).map((r: any) => [
      r.company_prospect_label,
      r.company_name,
      r.final_hq_country,
      r.team_routing,
      r.monetization_types,
      r.total_apps,
      r.total_downloads_latest_month,
      r.is_moloco_supply_visible ? "Visible" : "Hidden",
      r.moloco_media_cost_usd_30d,
      r.apps_with_other_exchange_sdk,
    ]);
    csv      = toCsvString(COMPANY_HEADERS, rows);
    filename = "no-sdk-no-ua-companies.csv";
  }

  return new Response("﻿" + csv, {
    headers: {
      "Content-Type":        "text/csv;charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
