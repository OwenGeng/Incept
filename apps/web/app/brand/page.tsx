export default function BrandPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-14 py-10">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="border-b border-border pb-8">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Linglong Design System
        </p>
        <h1 className="text-[36px] font-bold tracking-tight text-foreground">Brand & UI Guidelines</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Internal reference for Scout and Studio — the two products of the Linglong platform.
          Update when tokens or components change.
        </p>
      </div>

      {/* ── 1. Colors ────────────────────────────────────────────────────────── */}
      <section className="space-y-8">
        <h2 className="text-[22px] font-semibold tracking-tight">1. Colors</h2>

        {/* Brand palette */}
        <div>
          <h3 className="mb-4 text-base font-semibold">Brand Palette</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {[
              { name: "Accent Blue",  hex: "#356fec", label: "--accent" },
              { name: "Brand Blue",   hex: "#3a86ff", label: "charts · P1" },
              { name: "Purple",       hex: "#8338ec", label: "P2 · charts" },
              { name: "Rose / Pink",  hex: "#ff006e", label: "P3 · charts" },
              { name: "Orange",       hex: "#fb5607", label: "charts" },
              { name: "Amber",        hex: "#ffbe0b", label: "charts" },
              { name: "AI Accent",    hex: "#2bacff", label: "--ai-accent" },
            ].map(({ name, hex, label }) => (
              <div key={hex} className="space-y-2">
                <div
                  className="h-14 w-full rounded-xl border border-border/30"
                  style={{ background: hex }}
                />
                <div>
                  <div className="text-[12px] font-semibold text-foreground">{name}</div>
                  <div className="font-mono text-[11px] text-muted-foreground">{hex}</div>
                  <div className="text-[11px] text-muted-foreground">{label}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Semantic tokens */}
        <div>
          <h3 className="mb-4 text-base font-semibold">Semantic Tokens</h3>
          <div className="overflow-hidden rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted">
                  <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Swatch</th>
                  <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Name</th>
                  <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Hex</th>
                  <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Token</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { name: "Background",       hex: "#ffffff", token: "--background" },
                  { name: "Secondary/Sidebar", hex: "#fafbfc", token: "--secondary" },
                  { name: "Muted",            hex: "#f6f8fb", token: "--muted" },
                  { name: "Soft Accent",      hex: "#f2f6ff", token: "--soft-accent (active bg)" },
                  { name: "Foreground",       hex: "#101318", token: "--foreground" },
                  { name: "Muted Foreground", hex: "#5f6673", token: "--muted-foreground" },
                  { name: "Border",           hex: "#e6e8ec", token: "--border" },
                  { name: "Border Soft",      hex: "#f0f2f5", token: "--border-soft" },
                  { name: "Success",          hex: "#2d8a64", token: "--success" },
                  { name: "Destructive",      hex: "#d04444", token: "--destructive" },
                  { name: "Warning",          hex: "#d89216", token: "--warning" },
                ].map(({ name, hex, token }, i) => (
                  <tr key={hex} className={i % 2 === 0 ? "bg-background" : "bg-muted/40"}>
                    <td className="px-4 py-2.5">
                      <div
                        className="h-5 w-8 rounded border border-border/50"
                        style={{ background: hex }}
                      />
                    </td>
                    <td className="px-4 py-2.5 font-medium text-foreground">{name}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-muted-foreground">{hex}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-muted-foreground">{token}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[12px] text-muted-foreground">
            <span className="font-semibold text-foreground">Rule:</span> always use semantic tokens in component code. Hardcode hex only in{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-[11px]">supply-badges.tsx</code> for fixed-palette items.
          </p>
        </div>
      </section>

      {/* ── 2. Typography ────────────────────────────────────────────────────── */}
      <section className="space-y-6">
        <h2 className="text-[22px] font-semibold tracking-tight">2. Typography</h2>
        <div className="space-y-4">
          {[
            { role: "Display / Hero",     cls: "text-[42px] font-bold tracking-tight",                  sample: "Supply SMB Cross-Sell" },
            { role: "Page Title",         cls: "text-[28px] font-semibold tracking-tight",               sample: "Top Companies" },
            { role: "Product Name",       cls: "text-2xl font-semibold tracking-tight",                  sample: "Scout" },
            { role: "Card Title",         cls: "text-xl font-bold",                                      sample: "Prospect Funnel" },
            { role: "Section Header",     cls: "text-base font-semibold",                                sample: "Priority Tier Breakdown" },
            { role: "Body / Table",       cls: "text-sm font-medium",                                    sample: "App bundle · media cost · installs" },
            { role: "Label / Caps",       cls: "text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground", sample: "WEEKLY BRIEF" },
            { role: "Caption / Meta",     cls: "text-[11px] text-muted-foreground",                     sample: "Page 1 of 94 · 940 rows" },
          ].map(({ role, cls, sample }) => (
            <div key={role} className="flex items-baseline gap-6 border-b border-border/60 pb-4 last:border-0">
              <div className="w-36 shrink-0 text-[11px] text-muted-foreground">{role}</div>
              <div className={cls}>{sample}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 3. Components ────────────────────────────────────────────────────── */}
      <section className="space-y-8">
        <h2 className="text-[22px] font-semibold tracking-tight">3. Components</h2>

        {/* Buttons */}
        <div>
          <h3 className="mb-4 text-base font-semibold">Buttons</h3>
          <div className="flex flex-wrap gap-3">
            <button className="inline-flex h-10 items-center rounded-xl bg-foreground px-5 text-sm font-medium text-background transition hover:opacity-90">Default</button>
            <button className="inline-flex h-10 items-center rounded-xl bg-[#356fec] px-5 text-sm font-medium text-white shadow-sm transition hover:opacity-90">Accent</button>
            <button className="inline-flex h-10 items-center rounded-xl border border-border bg-card px-5 text-sm font-medium text-foreground transition hover:bg-muted">Secondary</button>
            <button className="inline-flex h-10 items-center rounded-xl px-5 text-sm font-medium text-muted-foreground transition hover:bg-muted">Ghost</button>
            <button className="inline-flex h-10 items-center rounded-xl border border-border px-5 text-sm font-medium text-foreground transition hover:bg-muted">Outline</button>
            <button className="inline-flex h-10 items-center rounded-xl bg-[#d04444] px-5 text-sm font-medium text-white transition hover:opacity-90">Destructive</button>
          </div>
          <p className="mt-3 text-[12px] text-muted-foreground">
            Sizes: <code className="rounded bg-muted px-1 py-0.5 text-[11px]">default h-10</code>{" · "}
            <code className="rounded bg-muted px-1 py-0.5 text-[11px]">sm h-8 text-xs</code>{" · "}
            <code className="rounded bg-muted px-1 py-0.5 text-[11px]">lg h-11</code>{" · "}
            <code className="rounded bg-muted px-1 py-0.5 text-[11px]">icon h-9 w-9</code>
          </p>
        </div>

        {/* Badges */}
        <div>
          <h3 className="mb-4 text-base font-semibold">Badges</h3>
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center rounded-full border border-transparent bg-foreground px-2.5 py-0.5 text-[11px] font-semibold text-background">Default</span>
            <span className="inline-flex items-center rounded-full border border-[#C7DEFF] bg-[#f2f6ff] px-2.5 py-0.5 text-[11px] font-semibold text-[#356fec]">Accent</span>
            <span className="inline-flex items-center rounded-full border border-border bg-muted px-2.5 py-0.5 text-[11px] font-semibold text-muted-foreground">Secondary</span>
            <span className="inline-flex items-center rounded-full border border-[#A7F3D0] bg-[#ECFDF5] px-2.5 py-0.5 text-[11px] font-semibold text-[#065f46]">Success</span>
            <span className="inline-flex items-center rounded-full border border-[#FDE68A] bg-[#FFFBEB] px-2.5 py-0.5 text-[11px] font-semibold text-[#92400e]">Warning</span>
            <span className="inline-flex items-center rounded-full border border-[#FECACA] bg-[#FFF1F1] px-2.5 py-0.5 text-[11px] font-semibold text-[#d04444]">Destructive</span>
          </div>
        </div>

        {/* Cards */}
        <div>
          <h3 className="mb-4 text-base font-semibold">Cards</h3>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <div className="mb-1 text-xl font-bold">Card Title</div>
              <div className="text-sm text-muted-foreground">Standard card — <code className="text-[11px]">rounded-2xl p-6 shadow-sm</code></div>
            </div>
            <div className="rounded-2xl border border-border bg-card p-7 shadow-sm">
              <div className="mb-1 text-xl font-bold">Data Card</div>
              <div className="text-sm text-muted-foreground">Wider padding — <code className="text-[11px]">p-7</code></div>
            </div>
            <div className="rounded-2xl border border-[#C7DEFF] bg-[#f2f6ff] p-6 shadow-sm">
              <div className="mb-1 text-xl font-bold text-[#356fec]">Accent Card</div>
              <div className="text-sm text-muted-foreground">Soft accent background variant</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── 4. Priority Tiers & Chips ────────────────────────────────────────── */}
      <section className="space-y-8">
        <h2 className="text-[22px] font-semibold tracking-tight">4. Priority Tiers & Data Chips</h2>

        {/* Tier badges */}
        <div>
          <h3 className="mb-4 text-base font-semibold">Prospect Tier Badges (P1–P4)</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { tier: "P1 Prime",   bg: "#EFF6FF", text: "#2563eb", bar: "#3a86ff", desc: "Direct NBS outreach — highest media cost + scale" },
              { tier: "P2 Strong",  bg: "#F3EEFB", text: "#8338ec", bar: "#8338ec", desc: "NBS + agency coordination queue" },
              { tier: "P3 Visible", bg: "#FFF0F6", text: "#db0058", bar: "#ff006e", desc: "Agency batch — Moloco-visible but lower spend" },
              { tier: "P4 Cold",    bg: "#F1F5F9", text: "#475569", bar: "#94a3b8", desc: "Monitor — longer-horizon pipeline" },
            ].map(({ tier, bg, text, bar, desc }) => (
              <div key={tier} className="rounded-xl border border-border bg-card p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span
                    className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
                    style={{ background: bg, color: text, borderColor: text + "33" }}
                  >
                    {tier}
                  </span>
                </div>
                <div className="mb-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div className="h-full w-3/4 rounded-full" style={{ background: bar }} />
                </div>
                <p className="text-[12px] text-muted-foreground">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Monetization chips */}
        <div>
          <h3 className="mb-4 text-base font-semibold">Monetization Chips</h3>
          <div className="flex flex-wrap gap-2">
            {[
              { label: "IAP",       bg: "#ECFDF5", text: "#065f46", border: "#A7F3D0" },
              { label: "IAA",       bg: "#EFF6FF", text: "#1d4ed8", border: "#BFDBFE" },
              { label: "Hybrid-IAP",bg: "#F3EEFB", text: "#8338ec", border: "#DDD6F5" },
              { label: "Hybrid-IAA",bg: "#FFFBEB", text: "#92400e", border: "#FDE68A" },
              { label: "Hybrid",    bg: "#F3EEFB", text: "#8338ec", border: "#DDD6F5" },
            ].map(({ label, bg, text, border }) => (
              <span
                key={label}
                className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
                style={{ background: bg, color: text, borderColor: border }}
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── 5. Design Principles ─────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-[22px] font-semibold tracking-tight">5. Design Principles</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {[
            { icon: "◎", title: "Token-first, hex-last",       body: "Use semantic tokens everywhere. Only the badge/chart palette in supply-badges.tsx uses raw hex — making global theme changes a one-file edit." },
            { icon: "⊞", title: "One shared component, two products", body: "AppSidebar, AppHeader, TableToolbar, and supply-badges are shared across Scout and Studio. Each product wraps shared components — never duplicates." },
            { icon: "⬡", title: "Readable contrast everywhere", body: "P4 uses #475569 on #F1F5F9 (not muted-foreground). Every badge meets AA contrast. Avoid light-on-light." },
            { icon: "⟳", title: "Streaming over blocking",      body: "Pages never block on data. Shell + topbar render instantly; Suspense boundaries handle async data. Users see structure immediately, data fills in." },
            { icon: "▣", title: "Component over inline styles",  body: "Color values that appear in more than one place must live in a component or utility. Duplicated inline styles are a maintenance debt." },
          ].map(({ icon, title, body }) => (
            <div key={title} className="rounded-xl border border-border bg-card p-5">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-lg text-muted-foreground">{icon}</span>
                <span className="font-semibold text-foreground">{title}</span>
              </div>
              <p className="text-sm text-muted-foreground">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 6. Key Files ─────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-[22px] font-semibold tracking-tight">6. Key Files Reference</h2>
        <div className="overflow-hidden rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted">
                <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Path</th>
                <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">What it defines</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["app/globals.css",                               "All CSS custom properties (--accent, --background, etc.)"],
                ["components/ui/app-sidebar.tsx",                 "Shared sidebar component (Scout + Studio)"],
                ["components/ui/app-header.tsx",                  "Shared page/section header"],
                ["components/layout/sidebar.tsx",                 "Scout sidebar — nav items, active state, signOut"],
                ["components/incept/Sidebar.tsx",                 "Studio sidebar — state-based nav, useSession"],
                ["components/supply-smb/supply-badges.tsx",       "All tier/mono/supply badge colors + components"],
                ["components/supply-smb/table-toolbar.tsx",       "Compact filter toolbar with CSV/Sheets export"],
                ["lib/csv-export.ts",                             "downloadCsv() — browser-side Blob download"],
                ["app/api/export/sheets/route.ts",                "Google Sheets export API route"],
                ["app/brand/page.tsx",                            "This page — live brand reference at /brand"],
              ].map(([path, desc], i) => (
                <tr key={path} className={i % 2 === 0 ? "bg-background" : "bg-muted/40"}>
                  <td className="px-4 py-2.5 font-mono text-[12px] text-muted-foreground">{path}</td>
                  <td className="px-4 py-2.5 text-sm text-foreground">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Footer */}
      <div className="border-t border-border pt-6 text-[12px] text-muted-foreground">
        Last updated: 2026-06-08 · Source of truth:{" "}
        <code className="rounded bg-muted px-1 py-0.5 text-[11px]">docs/brand-guidelines.md</code>
      </div>

    </div>
  );
}
