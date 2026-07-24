import { Suspense } from "react";
import { ArrowRight, CalendarDays, CheckCircle2, RefreshCw } from "lucide-react";
import { Card } from "@/components/ui/card";
import { ProspectFunnel } from "@/components/supply-smb/prospect-funnel";
import { RunPipelineButton } from "@/components/supply-smb/run-pipeline-button";
import { RefreshDataButton } from "@/components/supply-smb/refresh-data-button";
import {
  WeeklyBriefSummaryLeft,
  WeeklyBriefSummaryLeftSkeleton,
  WeeklyBriefSummaryRight,
  WeeklyBriefSummaryRightSkeleton,
} from "@/components/supply-smb/weekly-brief-summary-section";
import type { WeeklyBriefPayload, WeeklyBriefSummaryPayload } from "@/types/supply";
import { cn } from "@/lib/utils";

// Consistent with supply-badges.tsx tier colour palette
const tierStyles = {
  P1: { chip: "bg-[#EFF6FF] text-[#2563eb]",  line: "bg-[#3a86ff]" },
  P2: { chip: "bg-[#F3EEFB] text-[#8338ec]",  line: "bg-[#8338ec]" },
  P3: { chip: "bg-[#FFF0F6] text-[#db0058]",  line: "bg-[#ff006e]" },
} as const;

export function WeeklyBriefView({
  data,
  summaryPromise,
}: {
  data: WeeklyBriefPayload;
  summaryPromise: Promise<WeeklyBriefSummaryPayload>;
}) {
  return (
    <div className="space-y-6">
      {/* ── Hero brief card ── */}
      <Card className="overflow-hidden border-border p-0 shadow-sm">
        {/* Top accent bar */}
        <div className="h-1 w-full bg-[linear-gradient(90deg,_#3a86ff_0%,_#8338ec_100%)]" />

        <div className="p-7">
          {/* Header row */}
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent">
                  Weekly Brief
                </span>
              </div>
              <h2 className="mt-1.5 text-[26px] font-bold leading-tight text-foreground">
                {data.title}
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <RefreshDataButton />
              <RunPipelineButton />
              <div className="flex items-center gap-2 rounded-full bg-soft-accent px-4 py-1.5 text-sm font-medium text-accent">
                <CalendarDays className="size-3.5" />
                {data.dateRange}
              </div>
            </div>
          </div>

          {/* Body: 2-col grid */}
          <div className="grid gap-5 lg:grid-cols-[1.7fr_1fr]">

            {/* Left: summary + opportunity — streams in separately, doesn't block the page */}
            <div className="space-y-4">
              <Suspense fallback={<WeeklyBriefSummaryLeftSkeleton />}>
                <WeeklyBriefSummaryLeft summaryPromise={summaryPromise} />
              </Suspense>
            </div>

            {/* Right: insight boxes */}
            <div className="space-y-3">
              <Suspense fallback={<WeeklyBriefSummaryRightSkeleton />}>
                <WeeklyBriefSummaryRight summaryPromise={summaryPromise} />
              </Suspense>

              {/* Refresh status */}
              <div className="flex items-start gap-3 rounded-2xl bg-muted px-5 py-4">
                <RefreshCw className="mt-0.5 size-3.5 shrink-0 text-accent" />
                <div>
                  <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    Refresh Status
                  </div>
                  <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                    <CheckCircle2 className="size-3.5 text-[#16A34A]" />
                    {data.refreshStatus}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-4">
        {data.selectionSteps.map((step, index) => (
          <Card key={step.subtitle} className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                {step.title}
              </span>
              {index < data.selectionSteps.length - 1 ? (
                <ArrowRight className="size-4 text-muted-foreground" />
              ) : null}
            </div>
            <div className="mb-2 text-lg font-semibold text-foreground">{step.subtitle}</div>
            <p className="text-sm leading-7 text-muted-foreground">{step.detail}</p>
          </Card>
        ))}
      </div>

      {data.funnelSteps && data.funnelSteps.length > 0 && (
        <ProspectFunnel steps={data.funnelSteps} />
      )}

      <div className="grid gap-4 xl:grid-cols-4">
        {data.priorities.map((card) => {
          const style = tierStyles[card.tier as keyof typeof tierStyles] ?? tierStyles.P3;
          return (
            <Card key={card.tier} className="relative overflow-hidden p-5">
              <div className={cn("absolute inset-x-0 top-0 h-1.5", style.line)} />
              <div className="mb-4 flex items-center justify-between">
                <span className={cn("rounded-full px-3 py-1 text-[11px] font-semibold", style.chip)}>
                  {card.tier} {card.label}
                </span>
                <span className="text-xs font-medium text-muted-foreground">{card.delta}</span>
              </div>
              <div className="text-[42px] font-semibold leading-none text-foreground">
                {card.companies}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                {card.apps ? `${card.apps} apps` : "companies"}
              </div>
              <p className="mt-4 text-sm leading-7 text-muted-foreground">{card.note}</p>
            </Card>
          );
        })}
      </div>

    </div>
  );
}
