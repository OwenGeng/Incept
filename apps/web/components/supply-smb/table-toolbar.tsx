"use client";

/**
 * TableToolbar — compact search + filter popover + export buttons.
 *
 * Replaces ProspectFilterBar for all three Supply SMB list pages.
 * Renders immediately (client component), no Suspense boundary needed.
 *
 * Layout:
 *   [🔍 Search…          ]  · · ·  [↓] [Sheets] [Filter ▾]
 *
 * Filter button opens a floating popover with all dimension selects.
 * Download and Sheets buttons are shown only when exportTables are provided.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronDown,
  Download,
  FileSpreadsheet,
  Loader2,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { downloadCsv } from "@/lib/csv-export";
import type { FilterField } from "@/components/supply-smb/prospect-filter-bar";

// ── Export data shape ──────────────────────────────────────────────────────────

export type ExportableTable = {
  title: string;
  headers: string[];
  rows: (string | number | boolean | null | undefined)[][];
};

// ── Props ──────────────────────────────────────────────────────────────────────

export type TableToolbarProps = {
  /** All filter field descriptors (search + selects). Search always renders inline. */
  fields: FilterField[];
  /** Current active query (from searchParams). */
  query: Record<string, string | undefined>;
  /** URL to navigate to when resetting all filters. */
  resetHref: string;
  /** Query keys to preserve across filter changes (e.g. sort state). */
  preserveKeys?: string[];
  /**
   * Tables to export. If provided, CSV download and (optionally) Sheets buttons appear.
   * Can be omitted when the toolbar is rendered outside the data Suspense boundary.
   */
  exportTables?: ExportableTable[];
  /** Filename prefix for CSV downloads (without extension). */
  exportFilename?: string;
  /**
   * Server-side CSV export URLs — one per table.
   * When provided, the CSV button fetches ALL data from these endpoints instead of
   * using the paginated `exportTables` rows. Takes precedence over `exportTables` for CSV.
   */
  csvExportHrefs?: { title: string; href: string }[];
  /**
   * Enable the "Export to Google Sheets" button.
   * Requires GOOGLE_SERVICE_ACCOUNT_EMAIL + GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY env vars
   * and the /api/export/sheets API route to be reachable.
   */
  sheetsExportEnabled?: boolean;
};

// ── URL builder ────────────────────────────────────────────────────────────────

function buildUrl(pathname: string, q: Record<string, string | undefined>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v) params.set(k, v);
  }
  const s = params.toString();
  return s ? `${pathname}?${s}` : pathname;
}

// ── Main component ─────────────────────────────────────────────────────────────

export function TableToolbar({
  fields,
  query,
  resetHref,
  preserveKeys = [],
  exportTables,
  exportFilename = "export",
  csvExportHrefs,
  sheetsExportEnabled = false,
}: TableToolbarProps) {
  const router   = useRouter();
  const pathname = usePathname();

  const [filterOpen,    setFilterOpen]    = useState(false);
  const [pendingFilters, setPendingFilters] = useState<Record<string, string>>({});
  const [sheetsLoading, setSheetsLoading] = useState(false);

  const popoverRef  = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Separate search field from dimension selects
  const searchField  = fields.find((f) => f.type === "search");
  const selectFields = fields.filter((f) => f.type === "select");

  // Count active (non-default) filter values for the badge on the Filter button
  const activeCount = selectFields.reduce((n, f) => {
    const v = query[f.key];
    return n + (v && v !== "all" ? 1 : 0);
  }, 0);

  // Sync pending filter state when popover opens
  useEffect(() => {
    if (!filterOpen) return;
    const init: Record<string, string> = {};
    for (const f of selectFields) {
      init[f.key] = query[f.key] ?? "all";
    }
    setPendingFilters(init);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterOpen]);

  // Close popover on outside click
  useEffect(() => {
    if (!filterOpen) return;
    function onMouseDown(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setFilterOpen(false);
      }
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [filterOpen]);

  // ── Search (debounced, always client-side) ───────────────────────────────────

  const handleSearch = useCallback(
    (value: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        // Preserve sort keys + active select filters
        const preserved: Record<string, string | undefined> = {};
        for (const k of preserveKeys) preserved[k] = query[k];
        for (const f of selectFields) preserved[f.key] = query[f.key];
        router.push(
          buildUrl(pathname, { ...preserved, search: value || undefined }),
          { scroll: false },
        );
      }, 350);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [query, preserveKeys, pathname],
  );

  // ── Apply filter popover ─────────────────────────────────────────────────────

  const handleApply = () => {
    const preserved: Record<string, string | undefined> = {};
    for (const k of preserveKeys) preserved[k] = query[k];
    // Keep current search value
    if (searchField) preserved[searchField.key] = query[searchField.key];
    // Apply pending selects (clear "all" → undefined so it's not in the URL)
    const selects: Record<string, string | undefined> = Object.fromEntries(
      Object.entries(pendingFilters).map(([k, v]) => [k, v === "all" ? undefined : v]),
    );
    router.push(buildUrl(pathname, { ...preserved, ...selects }), { scroll: false });
    setFilterOpen(false);
  };

  const handleReset = () => {
    // Keep sort/page preserved keys, clear everything else
    const preserved: Record<string, string | undefined> = {};
    for (const k of preserveKeys) preserved[k] = query[k];
    const base = resetHref.split("?")[0];
    router.push(buildUrl(base, preserved), { scroll: false });
    setFilterOpen(false);
  };

  // ── CSV download ─────────────────────────────────────────────────────────────

  const handleCsvDownload = () => {
    // Prefer server-side export routes (full dataset, not just current page)
    if (csvExportHrefs?.length) {
      for (const { href } of csvExportHrefs) {
        const a = document.createElement("a");
        a.href = href;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
      return;
    }
    // Fallback: client-side export of current page rows
    if (!exportTables?.length) return;
    for (const t of exportTables) {
      downloadCsv(t.headers, t.rows, `${exportFilename}-${t.title}`);
    }
  };

  // ── Google Sheets export ─────────────────────────────────────────────────────

  const handleSheetsExport = async () => {
    if (!exportTables?.length) return;
    setSheetsLoading(true);
    try {
      const res = await fetch("/api/export/sheets", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ title: exportFilename, tables: exportTables }),
      });
      if (!res.ok) throw new Error(await res.text());
      const { url } = (await res.json()) as { url: string };
      window.open(url, "_blank");
    } catch (err) {
      console.error("Sheets export failed:", err);
      alert("Google Sheets export is not configured. Please ask the admin to set GOOGLE_SERVICE_ACCOUNT_EMAIL and GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY.");
    } finally {
      setSheetsLoading(false);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="relative">
      {/* ── Toolbar row ── */}
      <div className="flex items-center gap-2">

        {/* Inline search */}
        {searchField && (
          <div className="relative w-full max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              key={query[searchField.key] ?? ""}        // reset input when query changes externally
              defaultValue={query[searchField.key] ?? ""}
              placeholder={
                searchField.type === "search"
                  ? (searchField.placeholder ?? "Search…")
                  : "Search…"
              }
              onChange={(e) => handleSearch(e.target.value)}
              className="h-9 w-full rounded-xl border border-border bg-card pl-9 pr-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-accent focus:ring-2 focus:ring-soft-accent"
            />
          </div>
        )}

        <div className="flex-1" />

        {/* CSV download */}
        {(csvExportHrefs?.length || (exportTables && exportTables.length > 0)) && (
          <button
            onClick={handleCsvDownload}
            title="Download all data as CSV"
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition hover:border-accent hover:text-accent"
          >
            <Download className="size-4" />
          </button>
        )}

        {/* Google Sheets export */}
        {sheetsExportEnabled && exportTables && exportTables.length > 0 && (
          <button
            onClick={handleSheetsExport}
            disabled={sheetsLoading}
            title="Export to Google Sheets"
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition hover:border-[#1a73e8] hover:text-[#1a73e8] disabled:opacity-50"
          >
            {sheetsLoading
              ? <Loader2 className="size-4 animate-spin" />
              : <FileSpreadsheet className="size-4" />
            }
          </button>
        )}

        {/* Filter button */}
        {selectFields.length > 0 && (
          <button
            onClick={() => setFilterOpen((v) => !v)}
            className={cn(
              "inline-flex h-9 items-center gap-1.5 rounded-xl border px-3.5 text-sm font-medium transition",
              filterOpen || activeCount > 0
                ? "border-accent bg-soft-accent text-accent"
                : "border-border bg-card text-foreground hover:border-accent hover:text-accent",
            )}
          >
            <SlidersHorizontal className="size-3.5 shrink-0" />
            <span>Filter</span>
            {activeCount > 0 && (
              <span className="flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-white">
                {activeCount}
              </span>
            )}
          </button>
        )}
      </div>

      {/* ── Filter popover ── */}
      {filterOpen && selectFields.length > 0 && (
        <div
          ref={popoverRef}
          className="absolute right-0 top-11 z-50 w-[300px] overflow-hidden rounded-2xl border border-border bg-card shadow-xl"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
            <span className="text-sm font-semibold text-foreground">Filter</span>
            <button
              onClick={() => setFilterOpen(false)}
              className="rounded-lg p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>

          {/* Fields */}
          <div className="space-y-4 p-5">
            {selectFields.map((field) => {
              if (field.type !== "select") return null;
              const active =
                pendingFilters[field.key] && pendingFilters[field.key] !== "all";
              return (
                <div key={field.key}>
                  <div className="mb-1.5 flex items-center justify-between">
                    <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      {field.label}
                    </label>
                    {active && (
                      <button
                        onClick={() =>
                          setPendingFilters((p) => ({ ...p, [field.key]: "all" }))
                        }
                        className="text-[11px] font-medium text-accent transition hover:underline"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                  <div className="relative">
                    <select
                      value={pendingFilters[field.key] ?? "all"}
                      onChange={(e) =>
                        setPendingFilters((p) => ({ ...p, [field.key]: e.target.value }))
                      }
                      className="h-9 w-full appearance-none rounded-xl border border-border bg-card px-3 pr-8 text-sm text-foreground outline-none transition focus:border-accent"
                    >
                      {field.options.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-border px-5 py-3.5">
            <button
              onClick={handleReset}
              className="text-sm font-medium text-muted-foreground transition hover:text-foreground"
            >
              Reset
            </button>
            <button
              onClick={handleApply}
              className="inline-flex h-9 items-center rounded-xl bg-accent px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-accent/90"
            >
              Apply Now
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
