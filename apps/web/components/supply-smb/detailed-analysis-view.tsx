"use client";

import type { AnalysisModule, AnalysisGroup, DetailedAnalysisPayload } from "@/types/supply";
import { Card, CardTitle } from "@/components/ui/card";
import { EDonut } from "@/components/charts/EDonut";
import { EHBar } from "@/components/charts/EHBar";

const PALETTE = ["#3a86ff", "#8338ec", "#ff006e", "#fb5607", "#ffbe0b"];

const TIER_COLORS: Record<string, string> = {
  P1: "#2563eb",
  P2: "#8338ec",
  P3: "#475569",
};

// ─── Stacked Group Chart ──────────────────────────────────────────────────────
function StackedGroupChart({ groups }: { groups: AnalysisGroup[] }) {
  return (
    <div className="mt-4 space-y-4">
      {groups.map((group) => {
        const total = group.segments.reduce((s, r) => s + r.amount, 0);
        if (total === 0) return null;
        return (
          <div key={group.label}>
            {/* Tier label */}
            <div className="mb-1.5 flex items-center justify-between">
              <span
                className="text-xs font-semibold"
                style={{ color: TIER_COLORS[group.label] ?? "#475569" }}
              >
                {group.label}
              </span>
              <span className="text-xs text-muted-foreground">{total} companies</span>
            </div>
            {/* Stacked bar */}
            <div className="flex h-7 w-full overflow-hidden rounded-md">
              {group.segments.map((seg) => (
                <div
                  key={seg.label}
                  title={`${seg.label}: ${seg.value}`}
                  className="flex items-center justify-center overflow-hidden text-[10px] font-semibold text-white"
                  style={{
                    width: `${(seg.amount / total) * 100}%`,
                    backgroundColor: seg.color ?? "#94a3b8",
                  }}
                >
                  {(seg.amount / total) >= 0.12 ? seg.label : ""}
                </div>
              ))}
            </div>
            {/* Legend */}
            <div className="mt-1.5 flex gap-4">
              {group.segments.map((seg) => (
                <span key={seg.label} className="flex items-center gap-1 text-xs text-muted-foreground">
                  <span
                    className="inline-block size-2 rounded-sm"
                    style={{ backgroundColor: seg.color ?? "#94a3b8" }}
                  />
                  {seg.label}: {seg.value}
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Module Card ──────────────────────────────────────────────────────────────
function ModuleCard({ module }: { module: AnalysisModule }) {
  if (module.chartType === "stacked_group") {
    return (
      <Card className="p-6">
        <CardTitle>{module.title}</CardTitle>
        <p className="mt-2 text-sm leading-7 text-muted-foreground">{module.caption}</p>
        <StackedGroupChart groups={module.groups ?? []} />
      </Card>
    );
  }

  if (module.chartType === "pie") {
    return (
      <Card className="p-6">
        <CardTitle>{module.title}</CardTitle>
        <p className="mt-2 text-sm leading-7 text-muted-foreground">{module.caption}</p>
        <div className="mt-2">
          <EDonut rows={module.rows} height={200} />
        </div>
      </Card>
    );
  }

  const barRows = module.rows.map((r, i) => ({
    label: r.label,
    barWidth: r.amount,
    displayValue: r.value,
    color: r.color ?? PALETTE[i % PALETTE.length],
  }));

  return (
    <Card className="p-6">
      <CardTitle>{module.title}</CardTitle>
      <p className="mt-2 text-sm leading-7 text-muted-foreground">{module.caption}</p>
      <div className="mt-2">
        <EHBar rows={barRows} />
      </div>
    </Card>
  );
}

// ─── Main View ────────────────────────────────────────────────────────────────
export function DetailedAnalysisView({ data }: { data: DetailedAnalysisPayload }) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {data.modules.map((module) => (
        <ModuleCard key={module.title} module={module} />
      ))}
    </div>
  );
}
