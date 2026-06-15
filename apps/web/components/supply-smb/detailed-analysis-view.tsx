"use client";

import type { AnalysisModule, DetailedAnalysisPayload } from "@/types/supply";
import { Card, CardTitle } from "@/components/ui/card";
import { EDonut } from "@/components/charts/EDonut";
import { EHBar } from "@/components/charts/EHBar";

const PALETTE = ["#3a86ff", "#8338ec", "#ff006e", "#fb5607", "#ffbe0b"];

// ─── Module Card ──────────────────────────────────────────────────────────────
function ModuleCard({ module }: { module: AnalysisModule }) {
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
