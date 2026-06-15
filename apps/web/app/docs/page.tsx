import { BookOpen, Database, Filter, LayoutList, Users, Globe } from "lucide-react";

const LISTS = [
  {
    id: "List 1",
    name: "SDK Cold Prospect",
    scope: "SDK + No UA",
    color: "bg-blue-50 border-blue-200",
    badge: "bg-blue-100 text-blue-700",
    description:
      "Publisher app is visible in Moloco SDK supply, but the company has zero Moloco UA spend in the past 90 days. No app in the company is a Moloco advertiser.",
    filters: [
      "exchange = MOLOCO_SDK* (app appears in SDK supply inventory)",
      "is_moloco_sdk_app = true",
      "is_moloco_advertiser_app = false at company level",
      "Total Moloco UA spend (90d) = $0 across all company apps",
      "HQ country in CHN / HKG / TWN / MAC / SGP",
    ],
    pitch: "Publisher is already monetizing via Moloco SDK — zero DSP relationship yet. Clean SDK-only cross-sell.",
  },
  {
    id: "List 2",
    name: "SDK Expansion",
    scope: "SDK + No UA",
    color: "bg-purple-50 border-purple-200",
    badge: "bg-purple-100 text-purple-700",
    description:
      "Publisher app is in Moloco SDK supply AND the company has some Moloco UA spend. Existing commercial relationship makes upsell easier.",
    filters: [
      "is_moloco_sdk_app = true",
      "is_moloco_advertiser_app = false",
      "Total Moloco UA spend (90d) > $0",
      "HQ country in CHN / HKG / TWN / MAC / SGP",
    ],
    pitch: "Publisher is already a Moloco customer (some UA). Expand the relationship depth.",
  },
  {
    id: "List 3",
    name: "Supply Partner → SDK",
    scope: "UA + No SDK",
    color: "bg-emerald-50 border-emerald-200",
    badge: "bg-emerald-100 text-emerald-700",
    description:
      "Company is an active Moloco UA advertiser (buying on DSP), but the specific app has not integrated Moloco SDK for supply monetization.",
    filters: [
      "is_moloco_advertiser_app = true (runs UA on Moloco DSP)",
      "is_moloco_sdk_app = false (specific app has no SDK)",
      "HQ country in CHN / HKG / TWN / MAC / SGP",
    ],
    pitch: "Existing buyer on the DSP side — SDK pitch has a warm foundation.",
  },
  {
    id: "List 4",
    name: "IAA Cold",
    scope: "No SDK + No UA",
    color: "bg-orange-50 border-orange-200",
    badge: "bg-orange-100 text-orange-700",
    description:
      "App uses ads-based monetization (IAA). No prior Moloco relationship — not in SDK supply, not a UA advertiser. Data sourced from SensorTower only.",
    filters: [
      "has_ads = true, has_iap = false (pure IAA monetization)",
      "is_moloco_sdk_app = false",
      "is_moloco_advertiser_app = false",
      "HQ country in CHN / HKG / TWN / MAC / SGP",
    ],
    pitch: "IAA publishers are SDK-native targets — Moloco SDK adds an incremental ad network.",
  },
  {
    id: "List 5",
    name: "IAP Cold",
    scope: "No SDK + No UA",
    color: "bg-rose-50 border-rose-200",
    badge: "bg-rose-100 text-rose-700",
    description:
      "App uses in-app purchase monetization (IAP). No prior Moloco relationship. UA pitch angle: drive paid conversions via Moloco DSP.",
    filters: [
      "has_iap = true, has_ads = false (pure IAP monetization)",
      "is_moloco_sdk_app = false",
      "is_moloco_advertiser_app = false",
      "HQ country in CHN / HKG / TWN / MAC / SGP",
    ],
    pitch: "IAP publishers care about ROAS — Moloco DSP UA performance is the hook.",
  },
  {
    id: "List 6",
    name: "Hybrid Cold",
    scope: "No SDK + No UA",
    color: "bg-amber-50 border-amber-200",
    badge: "bg-amber-100 text-amber-700",
    description:
      "App uses both IAA and IAP monetization. No prior Moloco relationship. Dual revenue streams mean both SDK and UA angles apply.",
    filters: [
      "has_ads = true AND has_iap = true (hybrid monetization)",
      "is_moloco_sdk_app = false",
      "is_moloco_advertiser_app = false",
      "HQ country in CHN / HKG / TWN / MAC / SGP",
    ],
    pitch: "Hybrid publishers are high-value targets for both SDK (supply) and DSP (UA) pitches.",
  },
];

const TIERS = [
  {
    tier: "P1",
    label: "Prime",
    color: "border-l-blue-500",
    conditions: [
      "HQ country = CHN (excludes SGP*)",
      "Moloco SDK supply visible (exchange = MOLOCO_SDK*)",
      "Media cost (30d) > $2,000",
      "Total downloads (latest month) ≥ 100,000",
      "Month-over-month download growth > +10%",
    ],
  },
  {
    tier: "P2",
    label: "Strong",
    color: "border-l-purple-500",
    conditions: [
      "HQ country = CHN (excludes SGP*)",
      "Moloco SDK supply visible",
      "Media cost (30d) > $500",
      "Total downloads (latest month) ≥ 50,000",
      "MoM download growth > −10%",
    ],
  },
  {
    tier: "P3",
    label: "Warm",
    color: "border-l-emerald-500",
    conditions: [
      "Moloco supply visible (any HQ country, SGP included*)",
      "Media cost (30d) > $0",
    ],
  },
  {
    tier: "P4",
    label: "Cold",
    color: "border-l-slate-300",
    conditions: [
      "No Moloco supply signal",
      "No SDK inventory found",
    ],
  },
];

const SOURCES = [
  {
    dataset: "gtm.supply_demand_overlap",
    project: "ads-bpd-guard-china",
    usage: "SDK visibility flag, eligibility status, media cost, SDK growth managers",
  },
  {
    dataset: "athena.fact_dsp_core",
    project: "ads-bpd-guard-china",
    usage: "UA spend signal — 90-day lookback for advertiser identification",
  },
  {
    dataset: "athena.dim1_app_v3",
    project: "ads-bpd-guard-china",
    usage: "SensorTower app & company metadata: HQ country, genre, monetization type, website",
  },
  {
    dataset: "sensortower.download_revenue_v3",
    project: "ads-bpd-guard-china",
    usage: "Monthly downloads, top download country (30d)",
  },
  {
    dataset: "sensortower.network_analysis",
    project: "ads-bpd-guard-china",
    usage: "Competitor UA networks active on the app (90d)",
  },
  {
    dataset: "gtm.fact_supply_with_tracking_publisher",
    project: "ads-bpd-guard-china",
    usage: "SDK impression signals, top SDK impression country, tracking publisher name",
  },
  {
    dataset: "yingzi_uploads.hq_country_triage",
    project: "ads-bpd-guard-sandbox",
    usage: "GTM-verified HQ country overrides — corrects SensorTower misclassifications",
  },
];

const MONO_TYPES = [
  { type: "IAA", rule: "has_ads = true, has_iap = false" },
  { type: "IAP", rule: "has_iap = true, has_ads = false" },
  { type: "Hybrid-IAA", rule: "has_ads = true AND has_iap = true, genre in casual/puzzle/arcade/etc." },
  { type: "Hybrid-IAP", rule: "has_ads = true AND has_iap = true, mid-core genre OR sdk_media_cost > $1" },
  { type: "Free", rule: "has_ads = false AND has_iap = false" },
];

export default function DocsPage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-10 pb-20">
      {/* Header */}
      <div className="mb-10 border-b border-border pb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-soft-accent">
            <BookOpen className="size-5 text-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Linglong Docs</h1>
            <p className="text-sm text-muted-foreground">Supply SMB Cross-Sell — Methodology & Data Reference</p>
          </div>
        </div>
        <p className="mt-4 text-sm leading-7 text-muted-foreground max-w-2xl">
          Linglong identifies Chinese-origin app publishers as SDK and UA cross-sell targets for Moloco China GTM.
          Data is pulled from BigQuery every 4 hours and cached. The 6 lists segment prospects by their existing
          Moloco relationship and monetization type.
        </p>
      </div>

      {/* The 6 Lists */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <LayoutList className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">The 6 Lists</h2>
        </div>
        <div className="space-y-4">
          {LISTS.map((list) => (
            <div key={list.id} className={`rounded-2xl border p-5 ${list.color}`}>
              <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <span className={`rounded-lg px-2 py-0.5 text-xs font-semibold ${list.badge}`}>
                    {list.id}
                  </span>
                  <span className="font-semibold text-foreground">{list.name}</span>
                </div>
                <span className="rounded-full border border-border bg-white/80 px-2.5 py-0.5 text-xs text-muted-foreground">
                  {list.scope}
                </span>
              </div>
              <p className="text-sm text-foreground/80 mb-3">{list.description}</p>
              <div className="mb-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
                  Filter Conditions
                </p>
                <ul className="space-y-1">
                  {list.filters.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-foreground/70">
                      <span className="mt-2 size-1 shrink-0 rounded-full bg-current opacity-40" />
                      <code className="font-mono text-xs leading-6">{f}</code>
                    </li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-muted-foreground italic">{list.pitch}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Priority Tiers */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Filter className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Priority Tiers (P1 – P4)</h2>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          Applied to Lists 1 and 2 (SDK-visible prospects). Tiers rank companies by signal strength and conversion likelihood.
        </p>
        <div className="space-y-3">
          {TIERS.map((t) => (
            <div
              key={t.tier}
              className={`rounded-2xl border border-border bg-card px-5 py-4 border-l-4 ${t.color}`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="font-bold text-foreground">{t.tier}</span>
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
          <span className="font-semibold">* SGP exception:</span> Singapore-registered companies are forced into
          P3/P4 regardless of media cost. Many Chinese companies register offshore Singapore entities —
          SensorTower often misclassifies them as Singapore HQ, inflating their CHN priority score.
        </div>
      </section>

      {/* Team Routing */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Users className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Team Routing</h2>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-border bg-card p-5">
            <p className="font-semibold text-foreground mb-1">Gaming</p>
            <p className="text-sm text-muted-foreground">
              <code className="font-mono text-xs">is_gaming = true</code> in SensorTower classification.
              Routed to the Gaming NBS / AM team.
            </p>
          </div>
          <div className="rounded-2xl border border-border bg-card p-5">
            <p className="font-semibold text-foreground mb-1">Non-Gaming</p>
            <p className="text-sm text-muted-foreground">
              <code className="font-mono text-xs">is_gaming = false</code> in SensorTower classification.
              Routed to the Non-Gaming NBS / AM team.
            </p>
          </div>
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
          <code className="font-mono text-xs">has_iap</code> flags, with an override rule when
          SDK media cost exceeds $1.
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
        <p className="mt-2 text-xs text-muted-foreground">
          Override: if <code className="font-mono">sdk_media_cost_usd (30d) &gt; $1</code> and base type is IAP → reclassified as Hybrid-IAP.
        </p>
      </section>

      {/* Geographic Filter */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Globe className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Geographic Filter</h2>
        </div>
        <div className="rounded-2xl border border-border bg-card p-5">
          <p className="text-sm text-muted-foreground mb-3">
            All lists filter to HQ countries with Chinese-origin publishers:
          </p>
          <div className="flex flex-wrap gap-2">
            {[
              { code: "CHN", name: "China" },
              { code: "HKG", name: "Hong Kong" },
              { code: "TWN", name: "Taiwan" },
              { code: "MAC", name: "Macau" },
              { code: "SGP", name: "Singapore*" },
            ].map((c) => (
              <span
                key={c.code}
                className="rounded-xl border border-border bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground"
              >
                {c.code} <span className="text-muted-foreground font-normal">· {c.name}</span>
              </span>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            * SGP included for coverage, but downranked to P3/P4 due to offshore entity classification risk.
          </p>
        </div>
      </section>

      {/* Data Sources */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Database className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Data Sources</h2>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          All data is queried from BigQuery. Lookback windows: 30 days for supply/download signals, 90 days for UA spend and SDK inventory checks.
        </p>
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
                  <td className="px-4 py-3 text-muted-foreground align-top">{s.usage}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
