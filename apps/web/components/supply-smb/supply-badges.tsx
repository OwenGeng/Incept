/**
 * supply-badges.tsx
 * Shared badge / chip rendering for all three Supply SMB list pages.
 * All three lists (No-SDK/No-UA · SDK+No-UA · UA+No-SDK) import from here
 * so colours and shapes are always consistent.
 *
 * Brand palette
 *   P1 Blue   #3a86ff / soft #EFF6FF
 *   P2 Purple #8338ec / soft #F3EEFB
 *   P3 Pink   #ff006e / soft #FFF0F6
 *   P4 Gray   #475569 / soft #F1F5F9
 *
 *   IAP  Green   #2d8a64 / soft #EDFDF3
 *   IAA  Blue    #3a86ff / soft #EFF6FF
 *   Hybrid-IAP   Purple
 *   Hybrid-IAA   Amber
 *   Unknown Gray
 */

import { cn } from "@/lib/utils";

// ── Tier badge ─────────────────────────────────────────────────────────────────

/**
 * Returns Tailwind class string for a P-tier badge.
 * Accepts full label ("P1 - Prime") or just code ("P1").
 */
export function tierBadgeCls(label: string): string {
  const tier = (label ?? "").toUpperCase();
  if (tier.startsWith("P1")) return "border-[#C7DEFF] bg-[#EFF6FF] text-[#2563eb]";
  if (tier.startsWith("P2")) return "border-[#DDD6F5] bg-[#F3EEFB] text-[#8338ec]";
  if (tier.startsWith("P3")) return "border-[#FFC2DC] bg-[#FFF0F6] text-[#db0058]";
  // P4 — high-contrast charcoal on light slate, clearly readable
  return "border-[#CBD5E1] bg-[#F1F5F9] text-[#475569]";
}

export function TierBadge({ label }: { label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
        tierBadgeCls(label),
      )}
    >
      {label}
    </span>
  );
}

// ── Monetization chips ─────────────────────────────────────────────────────────

export function monetizationCls(type: string): string {
  const t = (type ?? "").trim().toUpperCase();
  if (t === "IAP")   return "border-[#A7F3D0] bg-[#ECFDF5] text-[#065f46]";
  if (t === "IAA")   return "border-[#BFDBFE] bg-[#EFF6FF] text-[#1d4ed8]";
  if (t.includes("HYBRID") && t.includes("IAP")) return "border-[#DDD6F5] bg-[#F3EEFB] text-[#8338ec]";
  if (t.includes("HYBRID") && t.includes("IAA")) return "border-[#FDE68A] bg-[#FFFBEB] text-[#92400e]";
  if (t === "HYBRID") return "border-[#DDD6F5] bg-[#F3EEFB] text-[#8338ec]";
  return "border-border bg-muted text-muted-foreground";
}

export function MonetizationChips({ value }: { value: string }) {
  const types = (value ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!types.length) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {types.map((t) => (
        <span
          key={t}
          className={cn(
            "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
            monetizationCls(t),
          )}
        >
          {t}
        </span>
      ))}
    </div>
  );
}

// ── Supply visible badge ───────────────────────────────────────────────────────

export function SupplyVisibleBadge({ visible }: { visible: boolean | string | null | undefined }) {
  const isVisible = visible === true || visible === "true" || visible === "True";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
        isVisible
          ? "border-[#A7F3D0] bg-[#ECFDF5] text-[#065f46]"
          : "border-border bg-muted text-muted-foreground",
      )}
    >
      {isVisible ? "Visible" : "Hidden"}
    </span>
  );
}

// ── Filter context chips (the summary row above tables) ────────────────────────

const toneStyle: Record<string, string> = {
  blue:   "border-[#BFDBFE] bg-[#EFF6FF]",
  purple: "border-[#DDD6F5] bg-[#F3EEFB]",
  green:  "border-[#A7F3D0] bg-[#ECFDF5]",
  pink:   "border-[#FFC2DC] bg-[#FFF0F6]",
};

export function FilterContextChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string | null;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border px-4 py-3 shadow-sm",
        tone && toneStyle[tone] ? toneStyle[tone] : "border-border bg-card",
      )}
    >
      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}
