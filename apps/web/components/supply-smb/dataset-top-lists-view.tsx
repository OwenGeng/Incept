import Link from "next/link";
import type { Route } from "next";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/card";
import {
  FilterContextChip,
  MonetizationChips,
  SupplyVisibleBadge,
  TierBadge,
} from "@/components/supply-smb/supply-badges";
import { TableToolbar } from "@/components/supply-smb/table-toolbar";
import type { FilterSelectOption } from "@/components/supply-smb/prospect-filter-bar";
import type { GenericTableColumn, GenericTablePayload, GenericTopListsPayload } from "@/types/supply";
import { cn, formatCompactNumber, formatCurrency, formatPercent } from "@/lib/utils";

// ── Query type ─────────────────────────────────────────────────────────────────

type Query = {
  search?: string;
  routing?: string;
  hqCountry?: string;
  monetization?: string;
  companySortBy?: string;
  companySortDir?: string;
  appSortBy?: string;
  appSortDir?: string;
  companyPage?: string;
  appPage?: string;
};

function asRoute(href: string): Route {
  return href as Route;
}

/**
 * API response keys are snake_case, but the cells dict keys are camelCase.
 * Convert a column's snake_case key to camelCase for the cells lookup.
 */
function colKeyCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, c: string) =>
    c >= "a" && c <= "z" ? c.toUpperCase() : c,
  );
}

function buildHref(basePath: string, query: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value) params.set(key, value);
  }
  const s = params.toString();
  return s ? `${basePath}?${s}` : basePath;
}

function sortHref(basePath: string, query: Query, table: "company" | "app", column: string): string {
  const next = { ...query };
  if (table === "company") {
    const active = query.companySortBy === column;
    next.companySortBy = column;
    next.companySortDir = active && query.companySortDir === "asc" ? "desc" : "asc";
    next.companyPage = "1";
  } else {
    const active = query.appSortBy === column;
    next.appSortBy = column;
    next.appSortDir = active && query.appSortDir === "asc" ? "desc" : "asc";
    next.appPage = "1";
  }
  return buildHref(basePath, next);
}

function pageHref(basePath: string, query: Query, table: "company" | "app", page: number): string {
  const next = { ...query };
  if (table === "company") next.companyPage = String(page);
  else next.appPage = String(page);
  return buildHref(basePath, next);
}

// ── Export helper: convert a generic table payload to CSV rows ─────────────────

function payloadToExport(payload: GenericTablePayload) {
  return {
    title:   payload.title,
    headers: payload.columns.map((c) => c.label),
    rows:    payload.rows.map((row) =>
      payload.columns.map((col) => {
        const v = row.cells[colKeyCamel(col.key)];
        return v === null || v === undefined ? "" : String(v);
      }),
    ),
  };
}

// ── Smart cell renderer ────────────────────────────────────────────────────────

function renderCell(
  value: string | number | boolean | null | undefined,
  column: GenericTableColumn,
) {
  if (value === null || value === undefined || value === "") return "—";

  switch (column.format) {
    case "currency": return formatCurrency(Number(value));
    case "number":   return formatCompactNumber(Number(value));
    case "percent":  return formatPercent(Number(value));

    case "boolean":
      return <SupplyVisibleBadge visible={Boolean(value)} />;

    case "badge": {
      const str = String(value);
      if (/^P[1-4]/i.test(str)) return <TierBadge label={str} />;
      const monTypes = ["IAP", "IAA", "Hybrid"];
      if (monTypes.some((t) => str.toUpperCase().includes(t.toUpperCase()))) {
        return <MonetizationChips value={str} />;
      }
      return (
        <span className="inline-flex items-center rounded-full border border-[#BFDBFE] bg-[#EFF6FF] px-2.5 py-0.5 text-[11px] font-medium text-[#1d4ed8]">
          {str}
        </span>
      );
    }

    default: return String(value);
  }
}

// ── Sort indicator ─────────────────────────────────────────────────────────────

function HeaderCell({
  basePath, query, table, column,
}: {
  basePath: string;
  query: Query;
  table: "company" | "app";
  column: GenericTableColumn;
}) {
  const active    = table === "company" ? query.companySortBy === column.key : query.appSortBy === column.key;
  const direction = table === "company" ? query.companySortDir : query.appSortDir;

  return (
    <th className="px-6 py-4 font-semibold">
      <Link
        href={asRoute(sortHref(basePath, query, table, column.key))}
        scroll={false}
        className={cn(
          "inline-flex items-center gap-1.5 transition hover:opacity-70",
          active && "text-accent",
        )}
      >
        <span>{column.label}</span>
        {!active ? (
          <ArrowUpDown className="size-3.5 text-muted-foreground" />
        ) : direction === "desc" ? (
          <ArrowDown className="size-3.5 text-accent" />
        ) : (
          <ArrowUp className="size-3.5 text-accent" />
        )}
      </Link>
    </th>
  );
}

// ── Pagination ─────────────────────────────────────────────────────────────────

function Pagination({
  basePath, query, table, payload,
}: {
  basePath: string;
  query: Query;
  table: "company" | "app";
  payload: GenericTablePayload;
}) {
  const pageCount = Math.max(1, Math.ceil(payload.total / payload.pageSize));
  const prevPage  = Math.max(1, payload.page - 1);
  const nextPage  = Math.min(pageCount, payload.page + 1);

  return (
    <div className="flex items-center justify-between gap-4 border-t border-border px-6 py-4 text-sm text-muted-foreground">
      <div>Page {payload.page} of {pageCount} · {payload.total} rows</div>
      <div className="flex items-center gap-2">
        {[
          { label: "Prev", pg: prevPage, disabled: payload.page <= 1 },
          { label: "Next", pg: nextPage, disabled: payload.page >= pageCount },
        ].map(({ label, pg, disabled }) => (
          <Link
            key={label}
            href={asRoute(pageHref(basePath, query, table, pg))}
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

// ── Generic data table ─────────────────────────────────────────────────────────

function DataTable({
  basePath, query, table, payload,
}: {
  basePath: string;
  query: Query;
  table: "company" | "app";
  payload: GenericTablePayload;
}) {
  return (
    <Card className="min-w-0 overflow-hidden p-0">
      <div className="px-6 pt-6 pb-4">
        <CardTitle>{payload.title}</CardTitle>
        {payload.subtitle && (
          <p className="mt-1 text-sm text-muted-foreground">{payload.subtitle}</p>
        )}
      </div>
      <div className="w-full max-w-full overflow-x-auto">
        <table className="w-max min-w-full text-left">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              {payload.columns.map((column) => (
                <HeaderCell
                  key={column.key}
                  basePath={basePath}
                  query={query}
                  table={table}
                  column={column}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {payload.rows.map((row) => (
              <tr key={row.key} className="border-b border-border text-sm transition hover:bg-muted">
                {payload.columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      "px-6 py-4 text-muted-foreground",
                      column.format === "badge" || column.format === "boolean"
                        ? "whitespace-nowrap"
                        : "max-w-[220px] whitespace-normal break-words",
                    )}
                  >
                    {renderCell(row.cells[colKeyCamel(column.key)], column)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination basePath={basePath} query={query} table={table} payload={payload} />
    </Card>
  );
}

// ── Main exported view ─────────────────────────────────────────────────────────

export function DatasetTopListsView({
  data,
  query,
  basePath,
}: {
  data: GenericTopListsPayload;
  query: Query;
  basePath: string;
}) {
  // Build filter fields from API controls
  const fields = [
    {
      type: "search" as const,
      key:  "search",
      label: "Search",
      placeholder: "company, app, genre, office…",
    },
    ...data.controls.map((control) => ({
      type: "select" as const,
      key:  control.key,
      label: control.label.replace(/_/g, " "),
      options: control.options.map((opt) => ({
        label: opt.label === "all" ? "All" : opt.label,
        value: opt.value,
      })) as FilterSelectOption[],
    })),
  ];

  // Keys to preserve across filter changes (sort state)
  const preserveKeys = [
    "companySortBy", "companySortDir",
    "appSortBy",     "appSortDir",
  ];

  // Map basePath → backend datasetKey
  // "/supply-smb/sdk-no-ua/list-1/top-lists" → "list-1"
  // "/supply-smb/sdk-no-ua/list-2/top-lists" → "list-2"
  // "/supply-smb/ua-no-sdk/top-lists"         → "list-3"
  const datasetKey = data.datasetKey; // backend already returns this

  // Build server-side CSV export URLs (downloads ALL rows, not just current page)
  const exportParams = new URLSearchParams(query as Record<string, string>);
  const csvExportHrefs = [
    {
      title: data.companiesTable.title,
      href:  `/api/export/csv/dataset/${datasetKey}?table=company&${exportParams}`,
    },
    {
      title: data.appsTable.title,
      href:  `/api/export/csv/dataset/${datasetKey}?table=app&${exportParams}`,
    },
  ];

  // Keep exportTables for Sheets export (uses current page data — acceptable for now)
  const exportTables = [
    payloadToExport(data.companiesTable),
    payloadToExport(data.appsTable),
  ];
  const exportFilename = basePath
    .replace(/^\/supply-smb\//, "")
    .replace(/\//g, "-");

  return (
    <div className="min-w-0 space-y-5">

      {/* Compact toolbar — search inline + filter popover + export buttons */}
      <TableToolbar
        fields={fields}
        query={query as Record<string, string | undefined>}
        resetHref={basePath}
        preserveKeys={preserveKeys}
        csvExportHrefs={csvExportHrefs}
        exportTables={exportTables}
        exportFilename={exportFilename}
        sheetsExportEnabled={process.env.NEXT_PUBLIC_SHEETS_EXPORT === "true"}
      />

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

      <DataTable basePath={basePath} query={query} table="company" payload={data.companiesTable} />
      <DataTable basePath={basePath} query={query} table="app"     payload={data.appsTable} />
    </div>
  );
}
