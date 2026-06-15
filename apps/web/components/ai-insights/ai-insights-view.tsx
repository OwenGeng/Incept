"use client";

import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  Info,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardTitle } from "@/components/ui/card";
import type { AiInsightsPayload, InsightItem, AgentStatus, ActivityItem } from "@/types/ai-insights";

// ─── Insight Feed ─────────────────────────────────────────────────────────────

const SEVERITY_STYLES = {
  warning: {
    bg: "bg-[#FFFBEB] border-[#FDE68A]",
    icon: AlertTriangle,
    iconColor: "text-warning",
    dot: "bg-[#F59E0B]",
  },
  info: {
    bg: "bg-[#EFF6FF] border-[#BFDBFE]",
    icon: Info,
    iconColor: "text-accent",
    dot: "bg-accent",
  },
  success: {
    bg: "bg-[#ECFDF5] border-[#A7F3D0]",
    icon: CheckCircle2,
    iconColor: "text-[#10B981]",
    dot: "bg-[#10B981]",
  },
  neutral: {
    bg: "bg-[#F8FAFF] border-border",
    icon: TrendingUp,
    iconColor: "text-muted-foreground",
    dot: "bg-muted-foreground",
  },
} as const;

function InsightCard({ item }: { item: InsightItem }) {
  const style = SEVERITY_STYLES[item.severity];
  const Icon = style.icon;

  return (
    <div className={`flex gap-3 rounded-[18px] border p-4 ${style.bg}`}>
      <Icon className={`mt-0.5 size-4 shrink-0 ${style.iconColor}`} />
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{item.text}</p>
        {item.detail && (
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{item.detail}</p>
        )}
      </div>
    </div>
  );
}

// ─── Agent Status ─────────────────────────────────────────────────────────────

const AGENT_STATUS_STYLES: Record<AgentStatus["status"], { chip: string; dot: string; label: string }> = {
  live:    { chip: "border-[#A7F3D0] bg-[#ECFDF5] text-[#059669]", dot: "bg-[#10B981]", label: "Live" },
  warming: { chip: "border-[#FDE68A] bg-[#FFFBEB] text-warning", dot: "bg-[#F59E0B] animate-pulse", label: "Warming" },
  idle:    { chip: "border-border bg-[#F8FAFF] text-muted-foreground",  dot: "bg-[#CBD5E1]", label: "Idle" },
};

function AgentCard({ agent }: { agent: AgentStatus }) {
  const s = AGENT_STATUS_STYLES[agent.status];
  return (
    <div className="rounded-[18px] border border-border bg-card p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Bot className="size-4 text-muted-foreground" />
          <span className="text-sm font-semibold text-foreground">{agent.name}</span>
        </div>
        <div className="flex items-center gap-2">
          {agent.badge && (
            <span className="rounded-md bg-soft-accent px-2 py-0.5 text-[10px] font-medium text-accent">
              {agent.badge}
            </span>
          )}
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-semibold ${s.chip}`}>
            <span className={`size-1.5 rounded-full ${s.dot}`} />
            {s.label}
          </span>
        </div>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{agent.detail}</p>
    </div>
  );
}

// ─── Activity Feed ────────────────────────────────────────────────────────────

const ACTION_ICONS: Record<string, typeof Clock> = {
  "Lead added":        Clock,
  "Status → Opened":   TrendingUp,
  "Status → Spending ✓": CheckCircle2,
};

function ActivityRow({ item }: { item: ActivityItem }) {
  const Icon = ACTION_ICONS[item.action] ?? Zap;
  return (
    <div className="flex items-start gap-3 py-3 border-b border-border last:border-0">
      <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-soft-accent">
        <Icon className="size-3.5 text-accent" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            {item.companyName ?? "—"}
          </span>
          <span className="text-xs text-muted-foreground">{item.action}</span>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{item.detail}</p>
      </div>
      <span className="shrink-0 text-[11px] text-muted-foreground">{item.date}</span>
    </div>
  );
}

// ─── Stats Row ────────────────────────────────────────────────────────────────

function StatChip({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-[14px] border border-border bg-card px-4 py-3 text-center">
      <div className="text-[26px] font-bold leading-none" style={{ color }}>{value}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

const SCOPE_STATS: Record<string, Array<{ label: string; color: string; key: keyof AiInsightsPayload }>> = {
  "no-sdk-no-ua": [
    { label: "Total Prospects", color: "hsl(var(--foreground))", key: "totalProspects" },
    { label: "P1 — Prime",      color: "hsl(var(--accent))",    key: "p1Count" },
    { label: "P2 — Strong",     color: "#8338ec",               key: "p2Count" },
    { label: "In Pipeline",     color: "#fb5607",               key: "leadsTotal" },
    { label: "Spending DSP",    color: "#10B981",               key: "spendingCount" },
  ],
  "sdk-no-ua": [
    { label: "Total Companies", color: "hsl(var(--foreground))", key: "totalProspects" },
    { label: "Eligible",        color: "#10B981",               key: "p1Count" },
    { label: "High Value",      color: "hsl(var(--accent))",    key: "p2Count" },
    { label: "No Manager",      color: "#fb5607",               key: "leadsTotal" },
    { label: "Spending DSP",    color: "#8338ec",               key: "spendingCount" },
  ],
  "ua-no-sdk": [
    { label: "Total Companies", color: "hsl(var(--foreground))", key: "totalProspects" },
    { label: "Active UA Buyers", color: "hsl(var(--accent))",   key: "p1Count" },
    { label: "High UA Value",   color: "#8338ec",               key: "p2Count" },
    { label: "Untapped Apps",   color: "#fb5607",               key: "leadsTotal" },
    { label: "Spending DSP",    color: "#10B981",               key: "spendingCount" },
  ],
};

// ─── Main View ────────────────────────────────────────────────────────────────

export function AiInsightsView({ data }: { data: AiInsightsPayload }) {
  const stats = SCOPE_STATS[data.scope] ?? SCOPE_STATS["no-sdk-no-ua"];
  return (
    <div className="space-y-6">
      {/* Stats overview */}
      <div className="grid grid-cols-5 gap-3">
        {stats.map((s) => (
          <StatChip key={s.label} label={s.label} value={data[s.key] as number} color={s.color} />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        {/* Left column */}
        <div className="space-y-6">
          {/* Insight Feed */}
          <Card className="p-6">
            <div className="mb-5 flex items-center gap-2">
              <CardTitle>Insight Feed</CardTitle>
              <span className="rounded-full bg-soft-accent px-2 py-0.5 text-[11px] font-semibold text-accent">
                {data.insights.length} signals
              </span>
            </div>
            <div className="space-y-3">
              {data.insights.length > 0 ? (
                data.insights.map((item, i) => <InsightCard key={i} item={item} />)
              ) : (
                <p className="text-sm text-muted-foreground">No active signals detected — all looks healthy.</p>
              )}
            </div>
          </Card>

          {/* Recent Activity */}
          <Card className="p-6">
            <CardTitle className="mb-4">Recent Lead Activity</CardTitle>
            {data.recentActivity.length > 0 ? (
              <div>
                {data.recentActivity.map((item, i) => (
                  <ActivityRow key={i} item={item} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No lead activity yet. Add leads from the Top Lists view.</p>
            )}
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Agent Operations */}
          <Card className="p-6">
            <CardTitle className="mb-5">Agent Operations</CardTitle>
            <div className="space-y-3">
              {data.agents.map((agent) => (
                <AgentCard key={agent.name} agent={agent} />
              ))}
            </div>
          </Card>

          {/* Memory / AI Summary */}
          <Card className="border-[#E0E7FF] bg-[#F5F3FF] p-6">
            <div className="mb-3 flex items-center gap-2">
              <Sparkles className="size-4 text-[#8338ec]" />
              <CardTitle>Operational Memory</CardTitle>
            </div>
            <p className="text-sm leading-7 text-[#4C4580]">{data.memorySummary}</p>
            <div className="mt-4 flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <Bot className="size-3" />
              Generated by Vertex AI · gemini-3.1-flash-lite
            </div>
          </Card>

          {/* Call Prep — top P1/P2 companies */}
          {data.callPrepCompanies.length > 0 && (
            <Card className="p-6">
              <CardTitle className="mb-4">
                {data.scope === "no-sdk-no-ua" ? "P1 + P2 Outreach Queue" : "Top Companies — Outreach Queue"}
              </CardTitle>
              <div className="space-y-2">
                {data.callPrepCompanies.slice(0, 6).map((co) => (
                  <div
                    key={co.companyName}
                    className="flex items-center justify-between gap-3 rounded-[14px] border border-border bg-card px-4 py-3"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-foreground">{co.companyName}</div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">
                        {co.hqCountry} · {co.totalApps} apps · {co.teamRouting}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {co.isSupplyVisible && (
                        <span className="rounded-full bg-[#ECFDF5] px-2 py-0.5 text-[10px] font-medium text-[#059669]">
                          Supply ✓
                        </span>
                      )}
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                          co.prospectLabel.startsWith("P1")
                            ? "bg-soft-accent text-accent"
                            : "bg-[#F3EEFB] text-[#8338ec]"
                        }`}
                      >
                        {co.prospectLabel.split(" ")[0]}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
