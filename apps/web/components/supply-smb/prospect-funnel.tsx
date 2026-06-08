"use client";

import { useId } from "react";
import { Card, CardTitle } from "@/components/ui/card";
import type { FunnelStep } from "@/types/supply";

// ─── Constants ────────────────────────────────────────────────────────────────
const CHART_H = 160;   // SVG viewport height (also CSS height in px)
const VIEW_W  = 800;   // SVG logical width (stretches to container via preserveAspectRatio="none")
const GAP     = 10;    // gap between steps (SVG units)

// Colors for each step: purple → indigo → brand blue → sky blue
const STEP_COLORS = [
  { light: "#D8B4FE", dark: "#8338ec", text: "#8338ec" },  // purple
  { light: "#A5B4FC", dark: "#4F46E5", text: "#4F46E5" },  // indigo
  { light: "#93C5FD", dark: "#3a86ff", text: "#3a86ff" },  // brand blue
  { light: "#BAE6FD", dark: "#0EA5E9", text: "#0EA5E9" },  // sky
] as const;

function fmt(n: number) {
  return n.toLocaleString();
}

// ─── Main Component ───────────────────────────────────────────────────────────
export function ProspectFunnel({ steps }: { steps: FunnelStep[] }) {
  const uid = useId().replace(/:/g, "");

  if (!steps || steps.length === 0) return null;

  const n = steps.length;
  const maxCos = steps[0].companies;

  // Step width in SVG units
  const stepW = (VIEW_W - GAP * (n - 1)) / n;

  // Height (in SVG units = px) for right edge of each step
  // Minimum height 12px so the last bar is still visible
  const rightHeights = steps.map((s) =>
    Math.max(12, Math.round((s.companies / maxCos) * CHART_H))
  );

  // Build SVG path for each step
  // Each step is a curved trapezoid:
  //   top-left  → bezier → top-right
  //   top-right → straight → bottom-right
  //   bottom-right → straight → bottom-left → Z
  function buildPath(i: number): string {
    const x     = i * (stepW + GAP);
    const leftH = i === 0 ? CHART_H : rightHeights[i - 1];
    const rightH= rightHeights[i];
    const lt    = CHART_H - leftH;   // y of top-left corner
    const rt    = CHART_H - rightH;  // y of top-right corner
    // S-curve bezier: horizontal tangent on both sides
    const mx    = x + stepW / 2;
    return [
      `M ${x} ${lt}`,
      `C ${mx} ${lt}, ${mx} ${rt}, ${x + stepW} ${rt}`,
      `L ${x + stepW} ${CHART_H}`,
      `L ${x} ${CHART_H}`,
      `Z`,
    ].join(" ");
  }

  const lastStep = steps[steps.length - 1];
  const convRate = maxCos > 0 ? Math.round((lastStep.companies / maxCos) * 100) : 0;

  return (
    <Card className="p-6">
      {/* Header */}
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        Selection Pipeline
      </div>
      <div className="mb-5 flex items-end justify-between gap-4">
        <CardTitle>Prospect Funnel</CardTitle>
        <div className="shrink-0 rounded-xl border border-border bg-soft-accent px-3.5 py-2 text-right">
          <span className="text-[22px] font-bold leading-none text-accent">{convRate}%</span>
          <div className="mt-0.5 text-[10px] text-muted-foreground">Pipeline conversion</div>
        </div>
      </div>

      {/* SVG Wave Chart */}
      <svg
        width="100%"
        height={CHART_H}
        viewBox={`0 0 ${VIEW_W} ${CHART_H}`}
        preserveAspectRatio="none"
        aria-hidden="true"
        className="block"
      >
        <defs>
          {STEP_COLORS.map((c, i) => (
            <linearGradient key={i} id={`${uid}_g${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={c.light} stopOpacity="0.92" />
              <stop offset="100%" stopColor={c.dark} stopOpacity="1" />
            </linearGradient>
          ))}
        </defs>

        {steps.map((_, i) => (
          <path
            key={i}
            d={buildPath(i)}
            fill={`url(#${uid}_g${i % STEP_COLORS.length})`}
          />
        ))}
      </svg>

      {/* Label row — HTML grid so text is crisp and wraps properly */}
      <div
        className="mt-3"
        style={{ display: "grid", gridTemplateColumns: `repeat(${n}, 1fr)`, gap: `${GAP}px` }}
      >
        {steps.map((step, i) => {
          const color = STEP_COLORS[i % STEP_COLORS.length];
          const prevCos = i > 0 ? steps[i - 1].companies : null;
          const drop    = prevCos !== null ? prevCos - step.companies : null;
          const dropPct = drop !== null && prevCos! > 0
            ? Math.round((drop / prevCos!) * 100)
            : null;

          return (
            <div key={step.label} className="min-w-0">
              {/* Count */}
              <div
                className="text-[26px] font-bold leading-none"
                style={{ color: color.text }}
              >
                {fmt(step.companies)}
              </div>
              {/* Label */}
              <div className="mt-1.5 text-[12px] font-semibold leading-tight text-foreground">
                {step.label}
              </div>
              {/* Apps + drop */}
              <div className="mt-1 text-[11px] text-muted-foreground">
                {fmt(step.apps)} apps
              </div>
              {drop !== null && (
                <div className="mt-1 text-[10px] text-muted-foreground">
                  −{fmt(drop)}{dropPct !== null ? ` (${dropPct}%)` : ""}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
