"use client";

import { useEffect, useState } from "react";
import { getStudioUsage, type StudioUsageResponse, type UsageSummary } from "@/lib/incept-api";

function fmtCost(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

function UsageCard({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.11em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-foreground">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

function UserSummaryTable({ summaries }: { summaries: UsageSummary[] }) {
  const sorted = [...summaries].sort((a, b) => b.estimated_cost_usd - a.estimated_cost_usd);

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="border-b border-border bg-muted/30 px-5 py-3">
        <h2 className="text-sm font-semibold text-foreground">All Users</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/20 text-xs text-muted-foreground">
              <th className="px-4 py-2.5 text-left font-medium">Email</th>
              <th className="px-4 py-2.5 text-right font-medium">Image Runs</th>
              <th className="px-4 py-2.5 text-right font-medium">Video Runs</th>
              <th className="px-4 py-2.5 text-right font-medium">Assets</th>
              <th className="px-4 py-2.5 text-right font-medium">Est. Cost</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((summary) => (
              <tr key={summary.email} className="border-b border-border last:border-0 hover:bg-muted/20">
                <td className="px-4 py-3 font-medium text-foreground">{summary.email || "—"}</td>
                <td className="px-4 py-3 text-right tabular-nums">{summary.image_generation_count}</td>
                <td className="px-4 py-3 text-right tabular-nums">{summary.video_generation_count}</td>
                <td className="px-4 py-3 text-right tabular-nums">{summary.asset_count}</td>
                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{fmtCost(summary.estimated_cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function UsageView() {
  const [data, setData] = useState<StudioUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getStudioUsage()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load usage data"))
      .finally(() => setLoading(false));
  }, []);

  const mine = data?.my_summary;
  const remaining = data && mine ? Math.max(0, data.budget_usd - mine.estimated_cost_usd) : 0;

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-7">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">Usage</p>
        <h1 className="mt-0.5 text-xl font-semibold text-foreground">My Studio Usage</h1>
        <p className="mt-1 text-sm text-muted-foreground">Image and video generation estimates for your account.</p>
      </div>

      {loading ? <div className="py-20 text-center text-sm text-muted-foreground">Loading…</div> : null}
      {error ? <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div> : null}

      {data && mine ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <UsageCard label="Budget" value={fmtCost(data.budget_usd)} detail="Per-user Studio limit" />
            <UsageCard label="Used" value={fmtCost(mine.estimated_cost_usd)} detail="Estimated image + video spend" />
            <UsageCard label="Remaining" value={fmtCost(remaining)} detail="Available before the limit" />
            <UsageCard label="Generated Assets" value={mine.asset_count} detail={`${mine.generation_count} generation runs`} />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <UsageCard label="Image" value={mine.image_generation_count} detail={`${mine.image_asset_count} assets · ${fmtCost(mine.image_estimated_cost_usd)} est.`} />
            <UsageCard label="Video" value={mine.video_generation_count} detail={`${mine.video_asset_count} assets · ${fmtCost(mine.video_estimated_cost_usd)} est.`} />
          </div>

          {data.user_summaries.length > 0 ? <UserSummaryTable summaries={data.user_summaries} /> : null}
        </>
      ) : null}
    </div>
  );
}
