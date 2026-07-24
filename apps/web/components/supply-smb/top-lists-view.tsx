import Link from "next/link";
import type { Route } from "next";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/card";
import { LeadModal } from "@/components/supply-smb/lead-modal";
import { Download } from "lucide-react";
import { TableToolbar } from "@/components/supply-smb/table-toolbar";
import {
  FilterContextChip,
  MonetizationChips,
  SupplyVisibleBadge,
  TierBadge,
} from "@/components/supply-smb/supply-badges";
import type { TopListsQuery } from "@/components/supply-smb/prospect-filter-bar";
export type { TopListsQuery } from "@/components/supply-smb/prospect-filter-bar";
import type { AppRow, CompanyRow, TopListsPayload } from "@/types/supply";
import { cn, formatCompactNumber, formatCurrency } from "@/lib/utils";

// ── Sort helpers ──────────────────────────────────────────────────────────────

type SortableColumn = { key: string; label: string; className?: string };

function buildHref(query: TopListsQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value) params.set(key, value);
  }
  const s = params.toString();
  return s ? `/supply-smb/no-sdk-no-ua/top-lists?${s}` : "/supply-smb/no-sdk-no-ua/top-lists";
}

function asRoute(href: string): Route {
  return href as Route;
}

function sortHref(query: TopListsQuery, table: "company" | "app", column: string): string {
  const next = { ...query };
  if (table === "company") {
    const isCurrent = query.companySortBy === column;
    next.companySortBy = column;
    next.companySortDir = isCurrent && query.companySortDir === "asc" ? "desc" : "asc";
    next.companyPage = "1";
  } else {
    const isCurrent = query.appSortBy === column;
    next.appSortBy = column;
    next.appSortDir = isCurrent && query.appSortDir === "asc" ? "desc" : "asc";
    next.appPage = "1";
  }
  return buildHref(next);
}

function pageHref(query: TopListsQuery, table: "company" | "app", page: number): string {
  const next = { ...query };
  if (table === "company") next.companyPage = String(page);
  else next.appPage = String(page);
  return buildHref(next);
}

// ── Sort indicator ─────────────────────────────────────────────────────────────

function SortIndicator({ active, direction }: { active: boolean; direction?: string }) {
  if (!active) return <ArrowUpDown className="size-3.5 text-muted-foreground" />;
  return direction === "desc"
    ? <ArrowDown className="size-3.5 text-accent" />
    : <ArrowUp className="size-3.5 text-accent" />;
}

function HeaderCell({
  table, column, query,
}: {
  table: "company" | "app";
  column: SortableColumn;
  query: TopListsQuery;
}) {
  const active    = table === "company" ? query.companySortBy === column.key : query.appSortBy === column.key;
  const direction = table === "company" ? query.companySortDir : query.appSortDir;

  return (
    <th className={cn("px-6 py-4 font-semibold", column.className)}>
      <Link
        href={asRoute(sortHref(query, table, column.key))}
        scroll={false}
        className={cn("inline-flex items-center gap-1.5 transition hover:opacity-70", active && "text-accent")}
      >
        <span>{column.label}</span>
        <SortIndicator active={active} direction={direction} />
      </Link>
    </th>
  );
}

// ── Pagination ─────────────────────────────────────────────────────────────────

function Pagination({
  table, page, total, pageSize, query,
}: {
  table: "company" | "app";
  page: number;
  total: number;
  pageSize: number;
  query: TopListsQuery;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const prevPage  = Math.max(1, page - 1);
  const nextPage  = Math.min(pageCount, page + 1);

  return (
    <div className="flex items-center justify-between gap-4 border-t border-border px-6 py-4 text-sm text-muted-foreground">
      <div>Page {page} of {pageCount} · {total} rows</div>
      <div className="flex items-center gap-2">
        {[
          { label: "Prev", pg: prevPage, disabled: page <= 1 },
          { label: "Next", pg: nextPage, disabled: page >= pageCount },
        ].map(({ label, pg, disabled }) => (
          <Link
            key={label}
            href={asRoute(pageHref(query, table, pg))}
            scroll={false}
            aria-disabled={disabled}
            className={cn(
              "inline-flex h-9 items-center justify-center rounded-xl border px-3 text-sm font-medium transition",
              disabled
                ? "pointer-events-none border-border text-muted-foreground"
                : "border-border bg-card text-foreground hover:bg-muted",
            )}
          >
            {label}
          </Link>
        ))}
      </div>
    </div>
  );
}

// ── Company table ──────────────────────────────────────────────────────────────

function CompanyTable({ rows, query }: { rows: CompanyRow[]; query: TopListsQuery }) {
  const columns: SortableColumn[] = [
    { key: "best_priority",                label: "Priority" },
    { key: "company_name",                 label: "Company",       className: "min-w-[200px]" },
    { key: "hq_country",                   label: "HQ" },
    { key: "website",                      label: "Website",       className: "min-w-[140px]" },
    { key: "team_routing",                 label: "Routing" },
    { key: "app_count",                    label: "Apps" },
    { key: "os_mix",                       label: "OS" },
    { key: "genres",                       label: "Genres",        className: "min-w-[180px]" },
    { key: "monetization_types",           label: "Monetization",  className: "min-w-[140px]" },
    { key: "total_downloads",              label: "DL / mo" },
    { key: "total_mau",                    label: "MAU" },
    { key: "max_paid_frac",                label: "Paid Frac" },
    { key: "any_active_ua",               label: "Active UA" },
    { key: "all_ua_networks",              label: "UA Networks",   className: "min-w-[200px]" },
    { key: "any_moloco_supply",            label: "Supply Visible" },
    { key: "moloco_media_cost_30d",        label: "Moloco Cost 30d" },
  ];
  const LIST_SOURCE = "no-sdk-no-ua";

  return (
    <div className="w-full max-w-full overflow-x-auto">
      <table className="w-max min-w-full text-left">
        <thead>
          <tr className="border-b border-border text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            {columns.map((col) => (
              <HeaderCell key={col.key} table="company" column={col} query={query} />
            ))}
            <th className="px-6 py-4" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.companyName}-${row.hqCountry}-${row.priority}`}
              className="border-b border-border text-sm transition hover:bg-muted"
            >
              <td className="px-6 py-4">
                <TierBadge label={row.companyProspectLabel} />
              </td>
              <td className="max-w-[200px] whitespace-normal break-words px-6 py-4 font-medium text-foreground">
                {row.companyName}
              </td>
              <td className="px-6 py-4 text-muted-foreground">{row.hqCountry || row.finalHqCountry}</td>
              <td className="max-w-[140px] truncate px-6 py-4 text-muted-foreground">
                {row.website ? (
                  <a href={row.website.startsWith("http") ? row.website : `https://${row.website}`}
                     target="_blank" rel="noopener noreferrer"
                     className="text-accent hover:underline">
                    {row.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
                  </a>
                ) : "—"}
              </td>
              <td className="px-6 py-4 text-muted-foreground">{row.teamRouting}</td>
              <td className="px-6 py-4 text-muted-foreground">{row.appCount || row.totalApps}</td>
              <td className="px-6 py-4 text-muted-foreground">{row.osMix || "—"}</td>
              <td className="max-w-[180px] whitespace-normal break-words px-6 py-4 text-muted-foreground">
                {row.genres || "—"}
              </td>
              <td className="px-6 py-4">
                <MonetizationChips value={row.monetizationTypes} />
              </td>
              <td className="px-6 py-4 text-muted-foreground">
                {formatCompactNumber(row.totalDownloads || row.totalDownloadsLatestMonth)}
              </td>
              <td className="px-6 py-4 text-muted-foreground">
                {row.totalMau ? formatCompactNumber(row.totalMau) : "—"}
              </td>
              <td className="px-6 py-4 text-muted-foreground">
                {row.maxPaidFrac ? `${(row.maxPaidFrac * 100).toFixed(0)}%` : "—"}
              </td>
              <td className="px-6 py-4">
                <SupplyVisibleBadge visible={row.anyActiveUa} />
              </td>
              <td className="max-w-[200px] whitespace-normal break-words px-6 py-4 text-muted-foreground">
                {row.allUaNetworks || row.allActiveNetworks || "—"}
              </td>
              <td className="px-6 py-4">
                <SupplyVisibleBadge visible={row.isMolocoSupplyVisible || row.anyMolocoSupply} />
              </td>
              <td className="px-6 py-4 font-semibold text-foreground">
                {row.molocoMediaCost30d ? formatCurrency(row.molocoMediaCost30d) : "—"}
              </td>
              <td className="px-4 py-4">
                <LeadModal
                  companyName={row.companyName}
                  teamRouting={row.teamRouting}
                  listSource={LIST_SOURCE}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Apps table ─────────────────────────────────────────────────────────────────

function AppsTable({ rows, query }: { rows: AppRow[]; query: TopListsQuery }) {
  const columns: SortableColumn[] = [
    { key: "priority",                       label: "Priority" },
    { key: "app_name",                       label: "App",            className: "min-w-[220px]" },
    { key: "company_name",                   label: "Company",        className: "min-w-[180px]" },
    { key: "team_routing",                   label: "Routing" },
    { key: "genre",                          label: "Genre" },
    { key: "monetization_type",              label: "Monetization" },
    { key: "downloads_latest_month",         label: "DL / mo" },
    { key: "active_ua_networks",             label: "UA Networks",    className: "min-w-[180px]" },
    { key: "is_moloco_supply_visible",       label: "Supply Visible" },
    { key: "moloco_media_cost_usd_30d",      label: "Media Cost 30d" },
    { key: "top_dl_country_t1",              label: "Top DL Country" },
  ];

  return (
    <div className="w-full max-w-full overflow-x-auto">
      <table className="w-max min-w-full text-left">
        <thead>
          <tr className="border-b border-border text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            {columns.map((col) => (
              <HeaderCell key={col.key} table="app" column={col} query={query} />
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.appMarketBundle}-${row.os}-${row.prospectLabel}`}
              className="border-b border-border text-sm transition hover:bg-muted"
            >
              <td className="px-6 py-4">
                <TierBadge label={row.prospectLabel} />
              </td>
              <td className="max-w-[220px] whitespace-normal break-words px-6 py-4 font-medium text-foreground">
                {row.appName}
              </td>
              <td className="max-w-[220px] whitespace-normal break-words px-6 py-4 text-muted-foreground">
                {row.companyName}
              </td>
              <td className="px-6 py-4 text-muted-foreground">{row.teamRouting}</td>
              <td className="px-6 py-4 text-muted-foreground">{row.genre}</td>
              <td className="px-6 py-4">
                <MonetizationChips value={row.monetizationType} />
              </td>
              <td className="px-6 py-4 text-muted-foreground">
                {formatCompactNumber(row.downloadsLatestMonth)}
              </td>
              <td className="max-w-[180px] whitespace-normal break-words px-6 py-4 text-muted-foreground">
                {row.activeUaNetworks || "—"}
              </td>
              <td className="px-6 py-4">
                <SupplyVisibleBadge visible={row.isMolocoSupplyVisible} />
              </td>
              <td className="px-6 py-4 font-semibold text-foreground">
                {formatCurrency(row.molocoMediaCostUsd30d)}
              </td>
              <td className="px-6 py-4 text-muted-foreground">{row.topDlCountryT1}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Tables + context chips — used inside Suspense ──────────────────────────────

function buildExportUrl(table: "company" | "app", query: TopListsQuery): string {
  const params = new URLSearchParams({ table });
  const map: [string, string | undefined][] = [
    ["priority",         query.priority],
    ["routing",          query.routing],
    ["supplyVisibility", query.supplyVisibility],
    ["search",           query.search],
    ["companySortBy",    query.companySortBy],
    ["companySortDir",   query.companySortDir],
    ["appSortBy",        query.appSortBy],
    ["appSortDir",       query.appSortDir],
  ];
  for (const [k, v] of map) {
    if (v) params.set(k, v);
  }
  return `/api/export/csv/top-lists?${params}`;
}

export function TopListsTablesContent({ data, query }: { data: TopListsPayload; query: TopListsQuery }) {

  return (
    <div className="space-y-5">

      {/* Active context chips */}
      {data.filters.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {data.filters.map((filter) => (
            <FilterContextChip
              key={`${filter.label}-${filter.value}`}
              label={filter.label}
              value={filter.value}
              tone={filter.tone}
            />
          ))}
        </div>
      )}

      {/* Top Companies table */}
      <Card className="overflow-hidden p-0">
        <div className="flex items-start justify-between px-6 pt-6 pb-4">
          <div>
            <CardTitle>Top Companies</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Company-level rollup · {data.companyTotal} total
            </p>
          </div>
          <a
            href={buildExportUrl("company", query)}
            title={`Download all ${data.companyTotal} companies as CSV`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition hover:border-accent hover:text-accent"
          >
            <Download className="size-3.5" />
          </a>
        </div>
        <CompanyTable rows={data.companies} query={query} />
        <Pagination
          table="company"
          page={data.companyPage}
          total={data.companyTotal}
          pageSize={data.pageSize}
          query={query}
        />
      </Card>

      {/* Top Apps table */}
      <Card className="overflow-hidden p-0">
        <div className="flex items-start justify-between px-6 pt-6 pb-4">
          <div>
            <CardTitle>Top Apps</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              App-level output · {data.appTotal} total
            </p>
          </div>
          <a
            href={buildExportUrl("app", query)}
            title={`Download all ${data.appTotal} apps as CSV`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition hover:border-accent hover:text-accent"
          >
            <Download className="size-3.5" />
          </a>
        </div>
        <AppsTable rows={data.apps} query={query} />
        <Pagination
          table="app"
          page={data.appPage}
          total={data.appTotal}
          pageSize={data.pageSize}
          query={query}
        />
      </Card>
    </div>
  );
}

// ── Filter fields config ───────────────────────────────────────────────────────

const NO_SDK_NO_UA_FIELDS = [
  {
    type: "search" as const,
    key: "search",
    label: "Search",
    placeholder: "company, app, genre…",
  },
  {
    type: "select" as const,
    key: "priority",
    label: "Priority",
    options: [
      { label: "All",        value: "all" },
      { label: "P1 Prime",   value: "P1" },
      { label: "P2 Strong",  value: "P2" },
      { label: "P3 Cold",    value: "P3" },
    ],
  },
  {
    type: "select" as const,
    key: "routing",
    label: "Team Routing",
    options: [
      { label: "All",         value: "all" },
      { label: "Non-Gaming",  value: "Non-Gaming" },
      { label: "Gaming",      value: "Gaming" },
    ],
  },
  {
    type: "select" as const,
    key: "supplyVisibility",
    label: "Supply Visible",
    options: [
      { label: "All",     value: "all" },
      { label: "Visible", value: "visible" },
      { label: "Hidden",  value: "hidden" },
    ],
  },
];

const PRESERVE_KEYS = ["companySortBy", "companySortDir", "appSortBy", "appSortDir"];

// ── Full view: toolbar (outside Suspense) + tables (inside Suspense) ───────────
// NOTE: In the page file, TableToolbar is rendered OUTSIDE Suspense for instant
// display, and TopListsTablesContent is rendered INSIDE Suspense for streaming.
// TopListsView is the combined version used when both are loaded together.

export function TopListsView({ data, query }: { data: TopListsPayload; query: TopListsQuery }) {
  return (
    <div className="space-y-5">
      <TableToolbar
        fields={NO_SDK_NO_UA_FIELDS}
        query={query as Record<string, string | undefined>}
        resetHref="/supply-smb/no-sdk-no-ua/top-lists"
        preserveKeys={PRESERVE_KEYS}
        // No exportTables here — TopListsTablesContent adds per-table buttons
        sheetsExportEnabled={process.env.NEXT_PUBLIC_SHEETS_EXPORT === "true"}
      />
      <TopListsTablesContent data={data} query={query} />
    </div>
  );
}
