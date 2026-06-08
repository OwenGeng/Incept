"use client";

import { useState } from "react";
import { ChevronRight, Database, FileCode2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import type { AnalysisModule, DetailedAnalysisPayload } from "@/types/supply";
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
          <EDonut
            rows={module.rows}
            height={200}
          />
        </div>
      </Card>
    );
  }

  // bar chart
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
  const [drawerOpen, setDrawerOpen] = useState(true);

  return (
    <div className="flex gap-6">
      {/* Content */}
      <div className="min-w-0 flex-1 space-y-6">
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">
            Evidence layer for the Supply SMB opportunity. Use this page to
            validate the weekly brief with grounded distributions and
            source-aware analysis.
          </p>
          <Button
            variant="secondary"
            onClick={() => setDrawerOpen((v) => !v)}
          >
            <FileCode2 className="size-4" data-icon="inline-start" />
            Methodology
          </Button>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          {data.modules.map((module) => (
            <ModuleCard key={module.title} module={module} />
          ))}
        </div>
      </div>

      {/* Methodology sidebar */}
      {drawerOpen && (
        <aside className="sticky top-0 h-fit w-[340px] shrink-0 rounded-[24px] border border-white/80 bg-white/88 p-5 shadow-card">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Methodology
              </div>
              <div className="mt-2 text-lg font-semibold text-foreground">
                Data provenance
              </div>
            </div>
            <button
              onClick={() => setDrawerOpen(false)}
              className="rounded-2xl bg-muted p-2 text-muted-foreground transition hover:bg-[#EAEFFD]"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
          <div className="space-y-5">
            {data.methodology.map((section) => (
              <div
                key={section.title}
                className="rounded-[20px] border border-border bg-[#FCFCFE] p-4"
              >
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Database className="size-4 text-foreground" />
                  {section.title}
                </div>
                <ul className="space-y-2 text-sm leading-7 text-muted-foreground">
                  {section.items.map((item) => (
                    <li key={item} className="flex gap-2">
                      <span className="mt-[10px] size-1.5 shrink-0 rounded-full bg-accent" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </aside>
      )}
    </div>
  );
}
