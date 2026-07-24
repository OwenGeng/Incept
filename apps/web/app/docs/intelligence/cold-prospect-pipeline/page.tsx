import { BookOpen, Database, Filter, Zap, Globe, GitBranch } from "lucide-react";
import { DocsBreadcrumb } from "@/components/docs/DocsChrome";

const ENTRY_FILTERS = [
  {
    label: "HQ Country",
    value: "CHN / HKG / TWN (SensorTower company.hq_country)",
    note: "Targets Chinese-origin publishers only",
  },
  {
    label: "No Moloco SDK",
    value: "is_moloco_sdk_app = false (supply_demand_overlap, all-time)",
    note: "App has never integrated Moloco SDK",
  },
  {
    label: "No Moloco UA",
    value: "gross_spend_usd = 0 on Moloco DSP (last 90 days)",
    note: "Company has no active UA buying relationship with Moloco",
  },
  {
    label: "Min Downloads",
    value: "Monthly downloads ≥ 20,000 (last complete month, worldwide)",
    note: "Ensures meaningful app scale",
  },
  {
    label: "Top Market Exclusion",
    value: "Top download country ≠ CN and ≠ IN (last month)",
    note: "Filters out purely domestic China/India apps with no global footprint",
  },
  {
    label: "Known Company Exclusion",
    value: "Company / publisher name NOT IN existing Moloco client list",
    note: "Deduplicates against current SDK and UA customer roster",
  },
];

const ENRICHMENT_STEPS = [
  {
    step: "1",
    name: "App Overview + SDK",
    endpoint: "GET /v1/{os}/apps",
    fields: "unified_app_id, top_countries, publisher_email, publisher_country, rating, global_rating_count, release_date, last_update, monthly downloads",
    extra: "include_sdk_data=true → installed_sdks, uninstalled_sdks",
  },
  {
    step: "2",
    name: "Download Channels",
    endpoint: "GET /v1/unified/downloads_by_sources",
    fields: "paid_frac, organic_frac, paid_abs, organic_abs, paid_search_frac",
    extra: "Last complete month, worldwide",
  },
  {
    step: "3",
    name: "Monthly Active Users",
    endpoint: "GET /v1/unified/usage/active_users",
    fields: "mau_ww (worldwide MAU)",
    extra: "Last 30 days",
  },
  {
    step: "4",
    name: "UA Network SOV",
    endpoint: "GET /v1/unified/ad_intel/network_analysis",
    fields: "active_ua_networks (sorted by SOV desc), peak_sov",
    extra: "Per-app, top-3 download countries × 8 fixed networks (Admob, Applovin, Facebook, IronSource, Meta AN, Mintegral, Pangle, TikTok)",
  },
];

const TIERS = [
  {
    tier: "P1",
    label: "High Intent",
    color: "border-l-blue-500",
    badge: "bg-blue-100 text-blue-700",
    conditions: [
      "UA SDK installed (AppLovin / IronSource / UnityAds / Mintegral / Pangle / TopOn / Appodeal / BidMachine)",
      "paid_frac ≥ 50% (majority of downloads from paid UA)",
      "active_ua_networks is not null (running on competitor networks right now)",
      "P1/P2: top_countries[0] ≠ IN and ≠ PK",
    ],
  },
  {
    tier: "P2",
    label: "Medium Intent",
    color: "border-l-purple-500",
    badge: "bg-purple-100 text-purple-700",
    conditions: [
      "UA SDK installed (same list as P1)",
      "paid_frac ≥ 20%",
      "P1/P2: top_countries[0] ≠ IN and ≠ PK",
    ],
  },
  {
    tier: "P3",
    label: "Prospect",
    color: "border-l-emerald-500",
    badge: "bg-emerald-100 text-emerald-700",
    conditions: [
      "All other apps (no UA SDK, or paid_frac < 20%)",
      "Includes IN/PK top-market apps (no geographic exclusion at P3)",
      "Includes apps with no SensorTower match (no enrichment data)",
    ],
  },
];

const SOURCES = [
  {
    dataset: "athena.dim1_app_v3",
    project: "ads-bpd-guard-china",
    usage: "App metadata: HQ country, genre, monetization flags (has_ads, has_iap), company name, publisher",
  },
  {
    dataset: "gtm.supply_demand_overlap",
    project: "ads-bpd-guard-china",
    usage: "Moloco SDK flag (is_moloco_sdk_app), advertiser flag (is_moloco_advertiser_app)",
  },
  {
    dataset: "athena.fact_dsp_core",
    project: "ads-bpd-guard-china",
    usage: "Moloco UA spend signal — 90-day lookback to detect existing advertiser relationship",
  },
  {
    dataset: "sensortower.fact_app_basis_v3",
    project: "ads-bpd-guard-china",
    usage: "Monthly download estimates — entry threshold (≥ 20K) and top download country filter",
  },
  {
    dataset: "SensorTower API (live)",
    project: "api.sensortower.com",
    usage: "App overview, SDK intelligence, download channels, MAU, competitor UA network SOV — fetched fresh each pipeline run",
  },
  {
    dataset: "supply_smb.cold_prospect_app",
    project: "ads-bpd-guard-sandbox",
    usage: "Pipeline output — one row per app, WRITE_TRUNCATE each run",
  },
  {
    dataset: "supply_smb.cold_prospect_company",
    project: "ads-bpd-guard-sandbox",
    usage: "Company-level rollup — aggregated from cold_prospect_app (best priority, total downloads, installed SDKs)",
  },
  {
    dataset: "supply_smb.prospect_snapshot",
    project: "ads-bpd-guard-sandbox",
    usage: "Weekly append — tracks which apps appear each week for WoW comparison",
  },
];

const MONO_TYPES = [
  { type: "IAA", rule: "has_ads = true, has_iap = false" },
  { type: "IAP", rule: "has_iap = true, has_ads = false (capped at P2 — no ad inventory to monetize)" },
  { type: "Hybrid", rule: "has_ads = true AND has_iap = true" },
  { type: "Free", rule: "has_ads = false AND has_iap = false — excluded from the pipeline entirely" },
];

export default function ColdProspectPipelineDocsPage() {
  return (
    <div className="mx-auto max-w-4xl px-8 py-10 pb-20">
      <DocsBreadcrumb
        trail={[
          { label: "Overview", href: "/docs" },
          { label: "Intelligence", href: "/docs/intelligence" },
          { label: "Cold Prospect Pipeline" },
        ]}
      />

      {/* Header */}
      <div className="mb-10 border-b border-border pb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-soft-accent">
            <BookOpen className="size-5 text-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Cold Prospect Pipeline — Docs</h1>
            <p className="text-sm text-muted-foreground">Methodology & Data Reference · Updated 2026-07</p>
          </div>
        </div>
        <p className="mt-4 text-sm leading-7 text-muted-foreground max-w-2xl">
          The Cold Prospect Pipeline identifies Chinese-origin app publishers with no existing Moloco relationship
          as UA cross-sell targets. It runs a BigQuery selection, enriches each app via the SensorTower API,
          and scores them into P1/P2/P3 tiers. Output is written to BigQuery weekly.
        </p>
      </div>

      {/* Entry Filters */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Filter className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Entry Filters (BQ Selection)</h2>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          All conditions must be satisfied for an app to enter the pipeline. Source: BigQuery cold prospect SQL.
        </p>
        <div className="space-y-3">
          {ENTRY_FILTERS.map((f) => (
            <div key={f.label} className="rounded-2xl border border-border bg-card px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-2 mb-1">
                <span className="font-semibold text-foreground text-sm">{f.label}</span>
              </div>
              <code className="text-xs font-mono text-foreground/80">{f.value}</code>
              <p className="mt-1 text-xs text-muted-foreground">{f.note}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ST Enrichment */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Zap className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">SensorTower API Enrichment</h2>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          After BQ selection, each app is enriched via SensorTower API in 4 sequential steps. Rate-limited to 5 RPS.
        </p>
        <div className="space-y-3">
          {ENRICHMENT_STEPS.map((s) => (
            <div key={s.step} className="rounded-2xl border border-border bg-card px-5 py-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="flex size-5 items-center justify-center rounded-full bg-muted text-xs font-bold text-muted-foreground">{s.step}</span>
                <span className="font-semibold text-foreground text-sm">{s.name}</span>
                <code className="ml-auto text-xs font-mono text-muted-foreground">{s.endpoint}</code>
              </div>
              <p className="text-xs text-foreground/70 mb-1"><span className="font-medium">Fields:</span> {s.fields}</p>
              <p className="text-xs text-muted-foreground">{s.extra}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Priority Tiers */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <GitBranch className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Priority Tiers (P1 – P3)</h2>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          Priority is assigned per-app based on ST enrichment signals. Evaluated after ST API calls complete.
        </p>
        <div className="space-y-3">
          {TIERS.map((t) => (
            <div key={t.tier} className={`rounded-2xl border border-border bg-card px-5 py-4 border-l-4 ${t.color}`}>
              <div className="flex items-center gap-2 mb-2">
                <span className={`rounded-lg px-2 py-0.5 text-xs font-semibold ${t.badge}`}>{t.tier}</span>
                <span className="text-sm text-muted-foreground">— {t.label}</span>
              </div>
              <ul className="space-y-1">
                {t.conditions.map((c) => (
                  <li key={c} className="flex items-start gap-2 text-sm text-muted-foreground">
                    <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <span className="font-semibold">IN/PK exclusion:</span> P1 and P2 apps whose #1 download country is India (IN) or Pakistan (PK)
          are excluded — these markets have very low monetization value for UA campaigns. P3 apps are kept regardless.
        </div>
      </section>

      {/* Monetization Types */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Filter className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Monetization Types</h2>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          Derived from SensorTower <code className="font-mono text-xs">has_ads</code> and{" "}
          <code className="font-mono text-xs">has_iap</code> flags in BQ metadata.
        </p>
        <div className="overflow-hidden rounded-2xl border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-3 text-left font-semibold text-foreground">Type</th>
                <th className="px-4 py-3 text-left font-semibold text-foreground">Rule</th>
              </tr>
            </thead>
            <tbody>
              {MONO_TYPES.map((m, i) => (
                <tr key={m.type} className={i < MONO_TYPES.length - 1 ? "border-b border-border" : ""}>
                  <td className="px-4 py-3 font-medium text-foreground">{m.type}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{m.rule}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Team Routing */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Globe className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Team Routing</h2>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-border bg-card p-5">
            <p className="font-semibold text-foreground mb-1">Gaming</p>
            <p className="text-sm text-muted-foreground">
              <code className="font-mono text-xs">is_gaming = true</code> (SensorTower genre classification).
              Routed to Gaming NBS / AM team.
            </p>
          </div>
          <div className="rounded-2xl border border-border bg-card p-5">
            <p className="font-semibold text-foreground mb-1">Non-Gaming</p>
            <p className="text-sm text-muted-foreground">
              <code className="font-mono text-xs">is_gaming = false</code> (SensorTower genre classification).
              Routed to Non-Gaming NBS / AM team.
            </p>
          </div>
        </div>
      </section>

      {/* Data Sources */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Database className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Data Sources</h2>
        </div>
        <div className="overflow-hidden rounded-2xl border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-3 text-left font-semibold text-foreground">Dataset</th>
                <th className="px-4 py-3 text-left font-semibold text-foreground">Usage</th>
              </tr>
            </thead>
            <tbody>
              {SOURCES.map((s, i) => (
                <tr key={s.dataset} className={i < SOURCES.length - 1 ? "border-b border-border" : ""}>
                  <td className="px-4 py-3 align-top">
                    <code className="font-mono text-xs text-foreground">{s.dataset}</code>
                    <div className="text-[11px] text-muted-foreground mt-0.5">{s.project}</div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground align-top text-xs">{s.usage}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
