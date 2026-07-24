"use client";

import { useMemo } from "react";
import { useSession } from "next-auth/react";
import { ImageIcon, Sparkles, Library, ArrowRight, Video, Zap } from "lucide-react";
import type { AssetSummary, CreativeThreadSummary, JobSummary } from "@incept/shared";
import type { AppView } from "./Sidebar";
import { cn } from "@/lib/utils";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function fmtRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface HomeViewProps {
  liveAssets: AssetSummary[];
  liveJobs: JobSummary[];
  liveThreads: CreativeThreadSummary[];
  onViewChange: (view: AppView) => void;
  onThreadSelect: (threadId: string) => void;
  onOpenCreateSurface: (surface: "image" | "video") => void;
}

// ─── Stat card ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: number | string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border bg-card px-5 py-4",
        accent && "border-accent/30 bg-soft-accent"
      )}
    >
      <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </p>
      <p
        className={cn(
          "mt-1.5 text-3xl font-bold tabular-nums",
          accent && "text-accent"
        )}
      >
        {value}
      </p>
      {sub && (
        <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>
      )}
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export function HomeView({
  liveAssets,
  liveJobs,
  liveThreads,
  onViewChange,
  onThreadSelect,
  onOpenCreateSurface,
}: HomeViewProps) {
  const { data: session } = useSession();
  const firstName =
    session?.user?.name?.split(" ")[0] ??
    session?.user?.email?.split("@")[0] ??
    "there";

  // ── Stats ──
  const today = new Date().toDateString();
  const todayCount = liveAssets.filter(
    (a) => new Date(a.createdAt).toDateString() === today
  ).length;
  const runningCount = liveJobs.filter(
    (j) => j.status === "running" || j.status === "queued"
  ).length;

  // ── Recent threads (filter blank ones, max 4) ──
  const recentThreads = useMemo(() => {
    const assetMap = new Map(liveAssets.map((asset) => [asset.id, asset]));
    return liveThreads
      .filter((thread) => thread.assetCount > 0 || thread.jobCount > 0)
      .map((thread) => {
        const cover = thread.coverAssetId
          ? assetMap.get(thread.coverAssetId)
          : thread.latestAssetId
          ? assetMap.get(thread.latestAssetId)
          : undefined;
        return {
          threadId: thread.id,
          title: thread.title,
          createdAt: thread.updatedAt,
          thumbnail: cover?.url ?? thread.previewUrl,
          count: thread.assetCount,
        };
      })
      .sort(
        (a, b) =>
          new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      )
      .slice(0, 4);
  }, [liveAssets, liveThreads]);

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      {/* ── Greeting ── */}
      <div>
        <h1 className="font-display text-3xl font-semibold">
          {getGreeting()}, {firstName}.
        </h1>
        <p className="mt-1 text-muted-foreground">
          What would you like to create today?
        </p>
      </div>

      {/* ── Stats ── */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Total assets" value={liveAssets.length} />
        <StatCard
          label="Created today"
          value={todayCount}
          sub={todayCount > 0 ? "new today" : "start generating"}
        />
        <StatCard
          label="Running"
          value={runningCount}
          sub={runningCount > 0 ? "jobs in progress" : "all idle"}
          accent={runningCount > 0}
        />
      </div>

      {/* ── Quick actions ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <button
          type="button"
          onClick={() => onOpenCreateSurface("image")}
          className="flex items-center gap-3 rounded-2xl border border-border bg-card px-5 py-4 text-left transition-colors hover:bg-muted/60"
        >
          <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-soft-accent text-accent">
            <Sparkles className="size-4" />
          </div>
          <div>
            <p className="text-sm font-medium">Generate Images</p>
            <p className="text-[11px] text-muted-foreground">Image &amp; endcard</p>
          </div>
        </button>

        <button
          type="button"
          onClick={() => onOpenCreateSurface("video")}
          className="flex items-center gap-3 rounded-2xl border border-border bg-card px-5 py-4 text-left transition-colors hover:bg-muted/60"
        >
          <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-soft-accent text-accent">
            <Video className="size-4" />
          </div>
          <div>
            <p className="text-sm font-medium">Generate Videos</p>
            <p className="text-[11px] text-muted-foreground">Veo scaffold</p>
          </div>
        </button>

        <button
          type="button"
          onClick={() => onViewChange("Library")}
          className="flex items-center gap-3 rounded-2xl border border-border bg-card px-5 py-4 text-left transition-colors hover:bg-muted/60"
        >
          <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground">
            <Library className="size-4" />
          </div>
          <div>
            <p className="text-sm font-medium">View Library</p>
            <p className="text-[11px] text-muted-foreground">
              {liveAssets.length} assets
            </p>
          </div>
        </button>

        <button
          type="button"
          onClick={() => {}}
          className="flex items-center gap-3 rounded-2xl border border-border bg-card px-5 py-4 text-left transition-colors hover:bg-muted/60"
        >
          <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground">
            <Zap className="size-4" />
          </div>
          <div>
            <p className="text-sm font-medium">Automate</p>
            <p className="text-[11px] text-muted-foreground">Coming soon</p>
          </div>
        </button>
      </div>

      {/* ── Recent threads ── */}
      {recentThreads.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Recent Threads</h2>
            <button
              type="button"
              onClick={() => onViewChange("Image")}
              className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              View all
              <ArrowRight className="size-3" />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            {recentThreads.map((s) => (
              <button
                key={s.threadId}
                type="button"
                onClick={() => onThreadSelect(s.threadId)}
                className="group flex flex-col gap-2 rounded-2xl border border-border bg-card p-3 text-left transition-colors hover:border-border/60 hover:bg-muted/40"
              >
                {/* Thumbnail */}
                <div className="aspect-video w-full overflow-hidden rounded-xl bg-[#07111F]">
                  {s.thumbnail ? (
                    <img
                      src={s.thumbnail}
                      alt={s.title}
                      className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center">
                      <ImageIcon className="size-5 text-white/20" />
                    </div>
                  )}
                </div>

                {/* Meta */}
                <div className="min-w-0">
                  <p className="truncate text-[12px] font-medium leading-tight">
                    {s.title}
                  </p>
                  <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                    {s.count} assets · {fmtRelative(s.createdAt)}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Empty state ── */}
      {recentThreads.length === 0 && (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border py-16 text-center">
          <div className="grid size-14 place-items-center rounded-2xl border-2 border-dashed border-border bg-muted/40">
            <Sparkles className="size-6 text-muted-foreground/40" />
          </div>
          <div>
            <p className="font-semibold">No generations yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Head over to Create to generate your first images.
            </p>
          </div>
          <button
            type="button"
            onClick={() => onViewChange("Image")}
            className="rounded-xl bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-80"
          >
            Start creating
          </button>
        </div>
      )}
    </div>
  );
}
