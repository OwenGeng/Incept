/**
 * GET /api/export/csv/dataset/[key]
 *
 * Exports ALL company or app data for a dataset list (sdk-no-ua / ua-no-sdk)
 * as a CSV file. Bypasses pagination via page_size=9999.
 *
 * Path param:
 *   key  — backend datasetKey: "list-1" | "list-2" | "list-3"
 *
 * Query params:
 *   table        "company" | "app"  (default: "company")
 *   search       filter
 *   routing      filter
 *   hqCountry    filter
 *   monetization filter
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

type Ctx = { params: Promise<{ key: string }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  // Auth check
  const session = isAuthDevSkipped() ? null : await auth();
  if (!isAuthDevSkipped() && !session?.user) {
    return new Response("Unauthorized", { status: 401 });
  }

  const { key: datasetKey } = await ctx.params;
  const sp   = req.nextUrl.searchParams;
  const table = sp.get("table") ?? "company";

  // Build backend query — page_size=9999 fetches all rows
  const params = new URLSearchParams();
  const forward: [string, string | null][] = [
    ["search",            sp.get("search")],
    ["routing",           sp.get("routing")],
    ["hq_country",        sp.get("hqCountry")],
    ["monetization",      sp.get("monetization")],
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
    res = await fetch(
      `${API_BASE}/api/v1/supply-smb/datasets/${datasetKey}/top-lists?${params}`,
      {
        cache: "no-store",
        headers: {
          "X-Internal-API-Key": INTERNAL_KEY,
          "X-User-Email":       user?.email ?? "",
          "X-User-Role":        user?.role  ?? "",
        },
      }
    );
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }

  if (!res.ok) {
    return new Response(`Backend error ${res.status}`, { status: 502 });
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = (await res.json()) as any;

  // ── Serialize to CSV ──────────────────────────────────────────────────────
  // GenericTopListsPayload has companies_table / apps_table with columns + rows
  const tablePayload = table === "app" ? data.apps_table : data.companies_table;

  if (!tablePayload) {
    return new Response("Table not found in response", { status: 500 });
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const headers: string[] = (tablePayload.columns ?? []).map((c: any) => c.label ?? c.key);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rows: (string | number | boolean | null)[][] = (tablePayload.rows ?? []).map((row: any) =>
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (tablePayload.columns ?? []).map((col: any) => {
      const v = row.cells?.[col.key];
      return v === undefined ? "" : v;
    })
  );

  const csv      = toCsvString(headers, rows);
  const title    = (tablePayload.title ?? `${datasetKey}-${table}`).toLowerCase().replace(/\s+/g, "-");
  const filename = `${title}.csv`;

  return new Response("﻿" + csv, {
    headers: {
      "Content-Type":        "text/csv;charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
