import { GitCompareArrows, TrendingUp } from "lucide-react";
import type { WeeklyBriefSummaryPayload } from "@/types/supply";

// ── Left column: summary + opportunity (streams in once Gemini resolves) ──────

export async function WeeklyBriefSummaryLeft({
  summaryPromise,
}: {
  summaryPromise: Promise<WeeklyBriefSummaryPayload>;
}) {
  const data = await summaryPromise;
  return (
    <>
      <p className="text-[15px] leading-8 text-muted-foreground">{data.summary}</p>

      <div className="rounded-2xl border-l-4 border-accent bg-[#F0F5FF] px-5 py-4">
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
          Opportunity
        </div>
        <p className="text-sm leading-7 text-[#344163]">{data.opportunity}</p>
      </div>
    </>
  );
}

export function WeeklyBriefSummaryLeftSkeleton() {
  return (
    <>
      <div className="space-y-2.5">
        <div className="h-3.5 w-full animate-pulse rounded bg-muted" />
        <div className="h-3.5 w-full animate-pulse rounded bg-muted" />
        <div className="h-3.5 w-2/3 animate-pulse rounded bg-muted" />
      </div>
      <div className="rounded-2xl border-l-4 border-accent/30 bg-[#F0F5FF] px-5 py-4">
        <div className="mb-2 h-3 w-24 animate-pulse rounded bg-accent/20" />
        <div className="h-3.5 w-full animate-pulse rounded bg-muted" />
      </div>
    </>
  );
}

// ── Right column: big things + week-over-week (streams in once Gemini resolves) ──

export async function WeeklyBriefSummaryRight({
  summaryPromise,
}: {
  summaryPromise: Promise<WeeklyBriefSummaryPayload>;
}) {
  const data = await summaryPromise;
  return (
    <>
      <div className="rounded-2xl bg-muted px-5 py-4">
        <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <TrendingUp className="size-3.5 text-accent" />
          Big things this week
        </div>
        <div className="space-y-2.5 text-sm leading-7 text-muted-foreground">
          {data.bigThings && data.bigThings.length > 0 ? (
            data.bigThings.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-accent" />
                <span>{item}</span>
              </div>
            ))
          ) : (
            <>
              {[
                "Moloco-visible supply accounts anchor the top of the priority queue.",
                "Fast-growth gaming titles are clustering below the current P1 threshold.",
                "AI follow-up suggestions target stale notes and unverified HQ countries.",
              ].map((text, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-accent" />
                  <span>{text}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {data.weekChanges && data.weekChanges.length > 0 && (
        <div className="rounded-2xl bg-muted px-5 py-4">
          <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-foreground">
            <GitCompareArrows className="size-3.5 text-[#8338ec]" />
            vs. last week
          </div>
          <div className="space-y-2.5 text-sm leading-7 text-muted-foreground">
            {data.weekChanges.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-[#8338ec]" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export function WeeklyBriefSummaryRightSkeleton() {
  return (
    <div className="rounded-2xl bg-muted px-5 py-4">
      <div className="mb-3 h-3 w-40 animate-pulse rounded bg-foreground/10" />
      <div className="space-y-2.5">
        <div className="h-3.5 w-full animate-pulse rounded bg-background/60" />
        <div className="h-3.5 w-full animate-pulse rounded bg-background/60" />
        <div className="h-3.5 w-2/3 animate-pulse rounded bg-background/60" />
      </div>
    </div>
  );
}
