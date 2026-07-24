"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { TierBadge } from "@/components/supply-smb/supply-badges";
import { cn } from "@/lib/utils";
import type { ColdProspectOverview, ColdProspectAppsPayload, ColdProspectApp } from "@/lib/api";

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function pct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${Math.round(n * 100)}%`;
}

// ── Small stat card ────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  accent,
  badge,
}: {
  label: string;
  value: string | number;
  accent?: string;
  badge?: React.ReactNode;
}) {
  return (
    <Card className="relative overflow-hidden p-5">
      {accent && <div className={cn("absolute inset-x-0 top-0 h-1", accent)} />}
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 flex items-end gap-2">
        <span className="text-[38px] font-semibold leading-none text-foreground">{value}</span>
        {badge}
      </div>
    </Card>
  );
}

// ── Priority distribution bar ──────────────────────────────────────────────────

function PriorityDistBar({
  p1,
  p2,
  p3,
  total,
}: {
  p1: number;
  p2: number;
  p3: number;
  total: number;
}) {
  if (total === 0) return null;

  const segments = [
    { label: "P1", count: p1, color: "bg-[#3a86ff]", text: "text-[#2563eb]" },
    { label: "P2", count: p2, color: "bg-[#8338ec]", text: "text-[#8338ec]" },
    { label: "P3", count: p3, color: "bg-[#94a3b8]", text: "text-[#475569]" },
  ];

  return (
    <Card className="p-5">
      <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        Priority Distribution
      </div>
      {/* Bar */}
      <div className="flex h-3 w-full overflow-hidden rounded-full">
        {segments.map((s) => (
          <div
            key={s.label}
            className={cn("transition-all", s.color)}
            style={{ width: `${(s.count / total) * 100}%` }}
          />
        ))}
      </div>
      {/* Legend */}
      <div className="mt-4 flex gap-6">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-2">
            <span className={cn("text-[13px] font-semibold", s.text)}>{s.label}</span>
            <span className="text-sm text-muted-foreground">
              {s.count} ({Math.round((s.count / total) * 100)}%)
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ── Key stats row ──────────────────────────────────────────────────────────────

function KeyStatsRow({
  overview,
}: {
  overview: ColdProspectOverview;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="p-5">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Avg Paid% — P1
        </div>
        <div className="text-3xl font-semibold text-[#2563eb]">
          {pct(overview.avgPaidFracP1)}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Of P1 app installs are paid UA
        </p>
      </Card>

      <Card className="p-5">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Avg Paid% — P2
        </div>
        <div className="text-3xl font-semibold text-[#8338ec]">
          {pct(overview.avgPaidFracP2)}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Of P2 app installs are paid UA
        </p>
      </Card>

      <Card className="p-5">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Top UA Networks
        </div>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {overview.topUaNetworks.slice(0, 8).map(({ network, appCount }) => (
            <span
              key={network}
              className="inline-flex items-center gap-1 rounded-full border border-[#C7DEFF] bg-[#EFF6FF] px-2.5 py-0.5 text-[11px] font-medium text-[#2563eb]"
            >
              {network}
              <span className="ml-0.5 rounded-full bg-[#C7DEFF] px-1.5 py-px text-[10px] font-semibold text-[#1d4ed8]">
                {appCount}
              </span>
            </span>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ── App table ──────────────────────────────────────────────────────────────────

const PAGE_SIZE = 25;

function AppTable({ initialApps }: { initialApps: ColdProspectApp[] }) {
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [osFilter, setOsFilter] = useState<string>("all");
  const [search, setSearch] = useState<string>("");
  const [page, setPage] = useState(1);

  // Client-side filter over the server-fetched 50 rows
  const filtered = initialApps.filter((app) => {
    if (priorityFilter !== "all" && app.priority !== priorityFilter) return false;
    if (osFilter !== "all" && app.os !== osFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      if (
        !app.appName?.toLowerCase().includes(q) &&
        !app.companyName?.toLowerCase().includes(q)
      )
        return false;
    }
    return true;
  });

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function handleFilterChange<T>(setter: (v: T) => void, value: T) {
    setter(value);
    setPage(1);
  }

  return (
    <Card className="overflow-hidden p-0">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-4">
        <input
          type="text"
          placeholder="Search app or company…"
          value={search}
          onChange={(e) => handleFilterChange(setSearch, e.target.value)}
          className="h-8 rounded-lg border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        />

        <select
          value={priorityFilter}
          onChange={(e) => handleFilterChange(setPriorityFilter, e.target.value)}
          className="h-8 rounded-lg border border-border bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="all">All Priorities</option>
          <option value="P1">P1</option>
          <option value="P2">P2</option>
          <option value="P3">P3</option>
        </select>

        <select
          value={osFilter}
          onChange={(e) => handleFilterChange(setOsFilter, e.target.value)}
          className="h-8 rounded-lg border border-border bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="all">All OS</option>
          <option value="android">Android</option>
          <option value="ios">iOS</option>
        </select>

        <span className="ml-auto text-sm text-muted-foreground">
          {filtered.length} apps
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              <th className="px-4 py-3 text-left">Priority</th>
              <th className="px-5 py-3 text-left">App</th>
              <th className="px-5 py-3 text-left">Company</th>
              <th className="px-4 py-3 text-left">OS</th>
              <th className="px-4 py-3 text-right">Paid%</th>
              <th className="px-4 py-3 text-right">Downloads (mo)</th>
              <th className="px-5 py-3 text-left">UA Networks</th>
            </tr>
          </thead>
          <tbody>
            {paged.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-5 py-10 text-center text-muted-foreground">
                  No apps match the current filters.
                </td>
              </tr>
            ) : (
              paged.map((app) => (
                <tr
                  key={`${app.appMarketBundle}-${app.os}`}
                  className="border-b border-border transition hover:bg-muted/50"
                >
                  <td className="px-4 py-3.5">
                    <TierBadge label={app.priority} />
                  </td>
                  <td className="max-w-[200px] px-5 py-3.5 font-medium text-foreground">
                    <div className="truncate" title={app.appName ?? undefined}>
                      {app.appName ?? "—"}
                    </div>
                    <div className="truncate text-[11px] text-muted-foreground">
                      {app.appMarketBundle}
                    </div>
                  </td>
                  <td className="max-w-[160px] truncate px-5 py-3.5 text-muted-foreground">
                    {app.companyName ?? "—"}
                  </td>
                  <td className="px-4 py-3.5">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[11px] font-medium",
                        app.os === "android"
                          ? "bg-[#ECFDF5] text-[#065f46]"
                          : "bg-[#EFF6FF] text-[#1d4ed8]",
                      )}
                    >
                      {app.os === "android" ? "Android" : "iOS"}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-right font-mono text-sm">
                    {pct(app.paidFrac)}
                  </td>
                  <td className="px-4 py-3.5 text-right font-mono text-sm">
                    {fmt(app.stLastMonthDownloads)}
                  </td>
                  <td className="max-w-[200px] px-5 py-3.5">
                    {app.activeUaNetworks ? (
                      <div className="flex flex-wrap gap-1">
                        {app.activeUaNetworks
                          .split(",")
                          .map((n) => n.trim())
                          .filter(Boolean)
                          .slice(0, 3)
                          .map((net) => (
                            <span
                              key={net}
                              className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                            >
                              {net}
                            </span>
                          ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-lg border border-border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-muted"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="rounded-lg border border-border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-muted"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Main view ──────────────────────────────────────────────────────────────────

export function ColdProspectOverviewView({
  overview,
  apps,
}: {
  overview: ColdProspectOverview;
  apps: ColdProspectAppsPayload;
}) {
  const wowNewPositive = overview.wowNew > 0;
  const wowDroppedPositive = overview.wowDropped > 0;

  return (
    <div className="space-y-6 p-6">
      {/* ── Summary cards ── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Total apps card with WoW change */}
        <Card className="relative overflow-hidden p-5">
          <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,_#3a86ff_0%,_#8338ec_100%)]" />
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Total Apps
          </div>
          <div className="mt-2 text-[38px] font-semibold leading-none text-foreground">
            {overview.totalApps.toLocaleString()}
          </div>
          <div className="mt-2 flex gap-3 text-xs">
            {wowNewPositive && (
              <span className="flex items-center gap-0.5 text-[#16A34A]">
                <ArrowUp className="size-3" />
                +{overview.wowNew} new
              </span>
            )}
            {wowDroppedPositive && (
              <span className="flex items-center gap-0.5 text-[#dc2626]">
                <ArrowDown className="size-3" />
                -{overview.wowDropped} dropped
              </span>
            )}
            {!wowNewPositive && !wowDroppedPositive && (
              <span className="flex items-center gap-0.5 text-muted-foreground">
                <Minus className="size-3" />
                No change vs last week
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {overview.totalCompanies} companies · as of {overview.dataAsOf}
          </div>
        </Card>

        <StatCard
          label="P1 — Prime"
          value={overview.p1Count}
          accent="bg-[#3a86ff]"
          badge={
            <TierBadge label="P1" />
          }
        />
        <StatCard
          label="P2 — Strong"
          value={overview.p2Count}
          accent="bg-[#8338ec]"
          badge={
            <TierBadge label="P2" />
          }
        />
        <StatCard
          label="P3 — Emerging"
          value={overview.p3Count}
          accent="bg-[#94a3b8]"
          badge={
            <TierBadge label="P3" />
          }
        />
      </div>

      {/* ── Priority distribution bar ── */}
      <PriorityDistBar
        p1={overview.p1Count}
        p2={overview.p2Count}
        p3={overview.p3Count}
        total={overview.totalApps}
      />

      {/* ── Key stats ── */}
      <KeyStatsRow overview={overview} />

      {/* ── App list table ── */}
      <div>
        <div className="mb-3 text-[13px] font-semibold text-foreground">
          App List
          <span className="ml-2 text-[11px] font-normal text-muted-foreground">
            Showing up to {apps.apps.length} of {apps.total} apps (sorted P1 first, then paid% desc)
          </span>
        </div>
        <AppTable initialApps={apps.apps} />
      </div>
    </div>
  );
}
