"use client";

import { useState, useTransition } from "react";
import { CheckCircle2, Clock, DollarSign, RefreshCw, Sparkles, TrendingUp } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { updateLeadStatusAction } from "@/app/actions/leads";
import type { LeadListPayload, LeadRecord } from "@/types/supply";
import { formatCurrency } from "@/lib/utils";

const STATUS_META = {
  sent: {
    label: "Sent",
    icon: Clock,
    chip: "border-[#FEF3C7] bg-[#FFFBEB] text-warning",
    dot: "bg-[#F59E0B]",
  },
  opened: {
    label: "Opened",
    icon: TrendingUp,
    chip: "border-[#DBEAFE] bg-[#EFF6FF] text-accent",
    dot: "bg-accent",
  },
  spending: {
    label: "Spending",
    icon: DollarSign,
    chip: "border-[#DCFCE7] bg-[#EDFDF3] text-[#16A34A]",
    dot: "bg-[#22C55E]",
  },
} as const;

const LIST_LABEL: Record<string, string> = {
  "no-sdk-no-ua": "No SDK + No UA",
  "list-1": "SDK No UA – List 1",
  "list-2": "SDK No UA – List 2",
  "list-3": "UA No SDK",
};

function StatusBadge({ status }: { status: LeadRecord["status"] }) {
  const meta = STATUS_META[status] ?? STATUS_META.sent;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${meta.chip}`}>
      <span className={`size-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}

function AttributionBadge({ isAttributed, totalSpend }: { isAttributed: boolean; totalSpend?: number }) {
  if (!isAttributed) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[#DCFCE7] bg-[#EDFDF3] px-2.5 py-0.5 text-[11px] font-semibold text-[#16A34A]">
      <CheckCircle2 className="size-3" />
      Converted {totalSpend ? `· ${formatCurrency(totalSpend)}` : ""}
    </span>
  );
}

function LeadRow({ lead }: { lead: LeadRecord }) {
  const [status, setStatus] = useState(lead.status);
  const [isPending, startTransition] = useTransition();

  const NEXT_STATUS: Record<string, "opened" | "spending"> = {
    sent: "opened",
    opened: "spending",
  };

  function advance() {
    const next = NEXT_STATUS[status];
    if (!next) return;
    startTransition(async () => {
      await updateLeadStatusAction(lead.leadId, next);
      setStatus(next);
    });
  }

  return (
    <tr className="border-b border-border text-sm transition hover:bg-muted">
      <td className="max-w-[200px] px-6 py-4 font-medium text-foreground whitespace-normal break-words">
        {lead.companyName}
      </td>
      <td className="px-6 py-4 text-muted-foreground">{LIST_LABEL[lead.listSource] ?? lead.listSource}</td>
      <td className="px-6 py-4 text-muted-foreground">{lead.teamRouting}</td>
      <td className="px-6 py-4 text-muted-foreground">{lead.sentToTeam}</td>
      <td className="px-6 py-4">
        <StatusBadge status={status} />
      </td>
      <td className="px-6 py-4">
        {lead.isAttributed ? (
          <AttributionBadge isAttributed={lead.isAttributed} totalSpend={lead.totalSpend90d ?? undefined} />
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-6 py-4 text-muted-foreground">{lead.activatedBy}</td>
      <td className="px-6 py-4 text-muted-foreground">{lead.activatedDate}</td>
      <td className="max-w-[200px] px-6 py-4 text-muted-foreground whitespace-normal break-words text-xs">
        {lead.notes || "—"}
      </td>
      <td className="px-4 py-4">
        {NEXT_STATUS[status] && (
          <button
            onClick={advance}
            disabled={isPending}
            className="rounded-lg border border-border bg-card px-2.5 py-1 text-[11px] font-semibold text-muted-foreground transition hover:bg-muted disabled:opacity-50"
          >
            {isPending ? "…" : `→ ${STATUS_META[NEXT_STATUS[status]!].label}`}
          </button>
        )}
        {status === "spending" && (
          <span className="text-xs text-[#22C55E] font-semibold">Active ✓</span>
        )}
      </td>
    </tr>
  );
}

export function LeadsView({ data }: { data: LeadListPayload }) {
  const [showAttribution, setShowAttribution] = useState(false);
  const [isPending, startTransition] = useTransition();

  const sentCount = data.leads.filter((l) => l.status === "sent").length;
  const openedCount = data.leads.filter((l) => l.status === "opened").length;

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Total Leads</div>
          <div className="mt-3 text-[42px] font-semibold leading-none text-foreground">{data.total}</div>
          <div className="mt-1 text-sm text-muted-foreground">across all lists</div>
        </Card>
        <Card className="p-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Sent / In Progress</div>
          <div className="mt-3 text-[42px] font-semibold leading-none text-[#fb5607]">{sentCount}</div>
          <div className="mt-1 text-sm text-muted-foreground">{openedCount} opened</div>
        </Card>
        <Card className="p-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Spending</div>
          <div className="mt-3 text-[42px] font-semibold leading-none text-[#22C55E]">{data.spendingCount}</div>
          <div className="mt-1 text-sm text-muted-foreground">active on DSP</div>
        </Card>
        <Card className="p-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Attributed Converts</div>
          <div className="mt-3 text-[42px] font-semibold leading-none text-foreground">{data.attributedCount}</div>
          <div className="mt-1 text-sm text-muted-foreground">within 90-day window</div>
        </Card>
      </div>

      {/* Attribution check prompt */}
      <Card className="border-[#E0E7FF] bg-[#F5F3FF] p-5">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <Sparkles className="mt-0.5 size-4 text-[#8338ec]" />
            <div>
              <div className="text-sm font-semibold text-foreground">Attribution Check</div>
              <div className="mt-0.5 text-sm text-muted-foreground">
                Join active leads against <code className="rounded bg-[#EDE9FE] px-1 text-xs">fact_dsp_core</code> to
                identify companies that opened an account within 90 days of being contacted.
              </div>
            </div>
          </div>
          <a
            href="/supply-smb/leads?attribution=true"
            className="shrink-0 inline-flex items-center gap-1.5 rounded-xl bg-[#8338ec] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#6D28D9]"
          >
            <RefreshCw className="size-3.5" />
            Run Check
          </a>
        </div>
      </Card>

      {/* Leads table */}
      <Card className="min-w-0 overflow-hidden p-0">
        <div className="px-6 pt-5 pb-4 border-b border-border">
          <CardTitle>Lead Pipeline</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            All companies marked as contacted. Advance status as the deal progresses.
          </p>
        </div>
        {data.leads.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm text-muted-foreground">
            No leads yet. Mark companies as contacted from the Top Lists tables.
          </div>
        ) : (
          <div className="w-full overflow-x-auto">
            <table className="w-max min-w-full text-left">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                  {["Company", "List", "Routing", "Sent To", "Status", "Attribution", "By", "Date", "Notes", ""].map(
                    (h) => (
                      <th key={h} className="px-6 py-4 font-semibold">{h}</th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {data.leads.map((lead) => (
                  <LeadRow key={lead.leadId} lead={lead} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
