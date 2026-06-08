import { Suspense } from "react";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { Topbar } from "@/components/layout/topbar";
import { AiInsightsView } from "@/components/ai-insights/ai-insights-view";
import { getAiInsights } from "@/lib/api";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";

// ── Data layer (runs inside Suspense) ─────────────────────────────────────────

async function AiInsightsContent() {
  const session = await auth();
  const data = await getAiInsights(session?.user ?? undefined);
  return <AiInsightsView data={data} />;
}

// ── Skeleton — matches AiInsightsView layout ──────────────────────────────────

function AiInsightsSkeleton() {
  return (
    <div className="space-y-6">
      {/* Stat chips row */}
      <div className="flex flex-wrap gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-14 w-44 animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>

      {/* Two-column body */}
      <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
        {/* Left column */}
        <div className="space-y-5">
          <div className="h-64 animate-pulse rounded-2xl bg-muted" />
          <div className="h-48 animate-pulse rounded-2xl bg-muted" />
        </div>
        {/* Right column */}
        <div className="space-y-5">
          <div className="h-40 animate-pulse rounded-2xl bg-muted" />
          <div className="h-40 animate-pulse rounded-2xl bg-muted" />
          <div className="h-40 animate-pulse rounded-2xl bg-muted" />
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function AiInsightsPage() {
  const session = await auth();

  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }

  return (
    <AppShell>
      {/*
        Topbar renders immediately — no data dependency.
        AiInsightsContent streams behind Suspense.
      */}
      <Topbar
        title="AI Insights"
        subtitle="Live intelligence from the prospect pool — rule-based signals and Vertex AI synthesis."
      />
      <Suspense fallback={<AiInsightsSkeleton />}>
        <AiInsightsContent />
      </Suspense>
    </AppShell>
  );
}
