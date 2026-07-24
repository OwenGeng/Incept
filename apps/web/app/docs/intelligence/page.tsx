import Link from "next/link";
import { ArrowRight, BarChart3 } from "lucide-react";
import { DocsBreadcrumb } from "@/components/docs/DocsChrome";

const INTELLIGENCE_DOCS = [
  {
    href: "/docs/intelligence/cold-prospect-pipeline",
    title: "Cold Prospect Pipeline",
    description:
      "How the weekly BigQuery + SensorTower pipeline identifies Chinese-origin publishers with no existing Moloco relationship and scores them into P1–P3 cross-sell tiers.",
  },
];

export default function IntelligenceDocsIndexPage() {
  return (
    <div className="mx-auto max-w-4xl px-8 py-10 pb-20">
      <DocsBreadcrumb trail={[{ label: "Overview", href: "/docs" }, { label: "Intelligence" }]} />

      {/* Header */}
      <div className="mb-10 border-b border-border pb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-soft-accent">
            <BarChart3 className="size-5 text-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Intelligence — Docs</h1>
            <p className="text-sm text-muted-foreground">Supply intelligence & prospecting pipelines</p>
          </div>
        </div>
        <p className="mt-4 text-sm leading-7 text-muted-foreground max-w-2xl">
          Intelligence covers the supply-side analysis and prospecting tools — SDK/UA overlap analysis, weekly
          briefs, and the cross-sell scoring pipelines. Pick a topic below.
        </p>
      </div>

      {/* Doc list */}
      <div className="space-y-3">
        {INTELLIGENCE_DOCS.map((doc) => (
          <Link
            key={doc.href}
            href={doc.href as never}
            className="flex items-center justify-between gap-4 rounded-2xl border border-border bg-card px-5 py-4 transition-colors hover:bg-muted/40"
          >
            <div>
              <p className="font-semibold text-foreground text-sm">{doc.title}</p>
              <p className="mt-1 text-xs text-muted-foreground">{doc.description}</p>
            </div>
            <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
          </Link>
        ))}
      </div>
    </div>
  );
}
