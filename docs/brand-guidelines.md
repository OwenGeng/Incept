# Incept Brand & UI Guidelines

> Internal design system reference for Scout and Studio — the two products of the Incept platform.
> Living doc: update when tokens or components change.

---

## Table of Contents

1. [Colors](#1-colors)
2. [Typography](#2-typography)
3. [Components](#3-components)
4. [Priority Tiers & Data Chips](#4-priority-tiers--data-chips)
5. [Key Patterns](#5-key-patterns)
6. [Design Principles](#6-design-principles)
7. [Key Files Reference](#7-key-files-reference)

---

## 1. Colors

### Brand Palette

| Name | Hex | Token / Usage |
|---|---|---|
| Accent Blue | `#356fec` | `--accent` — primary actions, active states, links |
| Brand Blue | `#3a86ff` | `brand.blue` — charts, P1 tier bar |
| Purple | `#8338ec` | `brand.purple` — P2 tier, charts |
| Rose / Pink | `#ff006e` | `brand.pink` — P3 tier, charts |
| Orange | `#fb5607` | `brand.orange` — charts |
| Amber | `#ffbe0b` | `brand.amber` — charts (use dark text `#101318`) |
| AI Accent | `#2bacff` | `--ai-accent` — AI feature highlights |

### Semantic Tokens

| Name | Hex | Token |
|---|---|---|
| Background | `#ffffff` | `--background` |
| Secondary / Sidebar | `#fafbfc` | `--secondary` |
| Muted | `#f6f8fb` | `--muted` |
| Soft Accent | `#f2f6ff` | `--soft-accent` — active item bg |
| Foreground | `#101318` | `--foreground` |
| Muted Foreground | `#5f6673` | `--muted-foreground` |
| Border | `#e6e8ec` | `--border` |
| Border Soft | `#f0f2f5` | `--border-soft` |

### Status Colors

| Name | Hex | Token |
|---|---|---|
| Success | `#2d8a64` | `--success` |
| Destructive | `#d04444` | `--destructive` |
| Warning | `#d89216` | `--warning` |

### Token Usage Rule

- Always use **semantic tokens** (`bg-accent`, `text-muted-foreground`, etc.) in component code.
- Hardcode raw hex values **only** for fixed-palette items like tier badges and chart bars.
- Keep all badge hex values in `components/supply-smb/supply-badges.tsx` — single source of truth.

---

## 2. Typography

### Type Scale

| Role | Classes | Example |
|---|---|---|
| Display / Hero | `text-[42px] font-bold tracking-tight` | "Supply SMB Cross-Sell" |
| Page Title | `text-[28px] font-semibold tracking-tight` | "Top Companies" |
| Product Name (sidebar) | `text-2xl font-semibold tracking-tight` | "Scout" |
| Card Title | `text-xl font-bold` | "Prospect Funnel" |
| Section Header | `text-base font-semibold` | "Priority Tier Breakdown" |
| Body / Table | `text-sm font-medium` | row content |
| Label / Caps | `text-[11px] font-semibold uppercase tracking-[0.18em]` | "WEEKLY BRIEF" |
| Caption / Meta | `text-[11px]` | "Page 1 of 94 · 940 rows" |

### Rules

- Font family: `system-ui → -apple-system → Segoe UI → sans-serif`. No external font downloads.
- All-caps labels: `text-[11px] font-semibold uppercase tracking-[0.16–0.22em] text-muted-foreground`
- Numbers in tables: `font-semibold text-foreground` for currency/key metrics; `text-muted-foreground` for counts.
- Positive growth rate: `text-success` — Negative: `text-destructive`

---

## 3. Components

### Buttons

```
Default      bg-foreground text-background             h-10 rounded-xl px-5
Accent       bg-accent text-white shadow-accent/25     h-10 rounded-xl px-5
Secondary    border border-border bg-card              h-10 rounded-xl px-5
Ghost        text-muted-foreground hover:bg-muted      h-10 rounded-xl px-5
Outline      border border-border text-foreground      h-10 rounded-xl px-5
Destructive  bg-destructive text-white                 h-10 rounded-xl px-5
```

Sizes: `default (h-10)` · `sm (h-8 text-xs)` · `lg (h-11)` · `icon (h-9 w-9)`

### Badges

```
Default      bg-foreground text-background border-transparent
Accent       bg-soft-accent text-accent border-[#C7DEFF]
Secondary    bg-muted text-muted-foreground border-border
Success      bg-[#ECFDF5] text-[#065f46] border-[#A7F3D0]
Warning      bg-[#FFFBEB] text-[#92400e] border-[#FDE68A]
Destructive  bg-[#FFF1F1] text-destructive border-[#FECACA]
```

Shape: `rounded-full border px-2.5 py-0.5 text-[11px] font-semibold`

### Cards

- Background: `bg-card` (= white)
- Border: `border border-border`
- Radius: `rounded-2xl` (= 0.875rem)
- Shadow: `shadow-sm` (light elevation)
- Padding: `p-6` standard, `p-7` for data cards

### Filter Toolbar (`TableToolbar`)

Compact single-row toolbar pattern used in all Scout data pages:

```
[Search input (350ms debounce)] [Filter button w/ badge count] [CSV] [Sheets]
```

- Search: inline, 350px wide, real-time `router.push`
- Filter popover: 300px floating panel with per-field Clear + Reset/Apply buttons
- Active filter count shown as badge on Filter button
- CSV: browser-side Blob download with BOM for Excel
- Sheets: POST to `/api/export/sheets`, opens returned URL
- File: `components/supply-smb/table-toolbar.tsx`

### Data Table

```
Header:   bg-muted text-[11px] uppercase tracking-[0.16em] text-muted-foreground
Row:      hover:bg-muted border-b border-border
Sort:     ChevronUp/Down icons from lucide-react
Outer:    overflow-hidden rounded-xl border border-border
```

### AppSidebar

```
Background:    bg-secondary (#fafbfc)
Width:         220px expanded / 64px collapsed
Active item:   bg-soft-accent (#f2f6ff) + font-semibold + icon text-accent
Toggle button: absolute -right-3.5 top-[68px] z-20, rounded-full
```

Shared component: `components/ui/app-sidebar.tsx`
Props: `productName`, `logo`, `storageKey`, `items`, `isActive`, `user`, `onSignOut`

---

## 4. Priority Tiers & Data Chips

### Prospect Tier Badges (P1–P4)

| Tier | bg | text | bar | Description |
|---|---|---|---|---|
| P1 Prime | `#EFF6FF` | `#2563eb` | `#3a86ff` | Direct NBS outreach — highest media cost + scale |
| P2 Strong | `#F3EEFB` | `#8338ec` | `#8338ec` | NBS + agency coordination queue |
| P3 Visible | `#FFF0F6` | `#db0058` | `#ff006e` | Agency batch — Moloco-visible but lower spend |
| P4 Cold | `#F1F5F9` | `#475569` | `#94a3b8` | Monitor — longer-horizon pipeline |

Badge shape: `rounded-full border px-2.5 py-0.5 text-[11px] font-semibold`
Source: `TierBadge` component + `tierBadgeCls()` in `components/supply-smb/supply-badges.tsx`

### Monetization Chips

| Label | bg | text | border | Usage |
|---|---|---|---|---|
| IAP | `#ECFDF5` | `#065f46` | `#A7F3D0` | In-app purchase — green (revenue signal) |
| IAA | `#EFF6FF` | `#1d4ed8` | `#BFDBFE` | In-app ads — blue (exchange opportunity) |
| Hybrid-IAP | `#F3EEFB` | `#8338ec` | `#DDD6F5` | Mixed: primary IAP — purple |
| Hybrid-IAA | `#FFFBEB` | `#92400e` | `#FDE68A` | Mixed: primary IAA — amber |
| Hybrid | `#F3EEFB` | `#8338ec` | `#DDD6F5` | Generic hybrid — purple |

Source: `MonetizationChips` component in `components/supply-smb/supply-badges.tsx`

### Supply Visible Badge

```
Visible:  bg-[#ECFDF5] text-[#065f46] border-[#A7F3D0]  rounded-full
Hidden:   bg-muted text-muted-foreground border-border     rounded-full
```

Component: `<SupplyVisibleBadge visible={boolean} />` from `supply-badges.tsx`

---

## 5. Key Patterns

### Page Header (AppHeader)

Two variants shared via `components/ui/app-header.tsx`:

**`variant="page"` — Scout style** (embedded in scrollable content)
```
mb-8 border-b pb-5
Title: text-[28px] font-semibold tracking-tight
Subtitle: text-sm text-muted-foreground
Tab rows: scope / dataset / page tabs below title
Right: Feedback + Docs buttons
```

**`variant="header"` — Studio style** (sticky bar at top of section)
```
flex items-center border-b px-7 py-4 shrink-0
Title: text-2xl font-semibold tracking-tight
Right: mobile menu button (hidden >980px) + Feedback + Docs
```

### Context Chips

Summary chips above data tables showing filter state:

```
blue:    border-[#BFDBFE] bg-[#EFF6FF]   — company/scope counts
green:   border-[#A7F3D0] bg-[#ECFDF5]   — supply visibility
purple:  border-[#DDD6F5] bg-[#F3EEFB]   — alerts / signals
default: border-border   bg-card          — general
```

Shape: `rounded-2xl px-4 py-3`
Component: `FilterContextChip` from `supply-badges.tsx`

### Suspense Streaming Pattern

All data-heavy pages use Suspense for instant shell render:

```tsx
// Page shell renders immediately
export default function Page() {
  return (
    <AppShell>
      <Topbar title="..." />
      <Suspense fallback={<Skeleton />}>
        <AsyncContent />   {/* data fetch inside */}
      </Suspense>
    </AppShell>
  );
}
```

Used in: `app/ai-insights/page.tsx`, `app/settings/users/page.tsx`, `app/supply-smb/**/top-lists/page.tsx`

---

## 6. Design Principles

### ◎ Token-first, hex-last
Use semantic tokens everywhere. Only the badge/chart palette in `supply-badges.tsx` uses raw hex — making global theme changes a one-file edit.

### ⊞ One shared component, two products
`AppSidebar`, `AppHeader`, `TableToolbar`, and `supply-badges` are shared across Scout and Studio. Each product wraps shared components — never duplicates.

### ⬡ Readable contrast everywhere
P4 uses `#475569` on `#F1F5F9` (not muted-foreground). Every badge meets AA contrast. Avoid light-on-light.

### ⟳ Streaming over blocking
Pages never block on data. Shell + topbar render instantly; Suspense boundaries handle async data. Users see structure immediately, data fills in.

### ▣ Component over inline styles
Color values that appear in more than one place must live in a component or utility. Duplicated inline styles are a maintenance debt.

---

## 7. Key Files Reference

| Path | What it defines |
|---|---|
| `app/globals.css` | All CSS custom properties (`--accent`, `--background`, etc.) |
| `components/ui/app-sidebar.tsx` | Shared sidebar component (Scout + Studio) |
| `components/ui/app-header.tsx` | Shared page/section header |
| `components/layout/sidebar.tsx` | Scout sidebar — nav items, active state, signOut |
| `components/incept/Sidebar.tsx` | Studio sidebar — state-based nav, useSession |
| `components/supply-smb/supply-badges.tsx` | All tier/mono/supply badge colors + components |
| `components/supply-smb/table-toolbar.tsx` | Compact filter toolbar with CSV/Sheets export |
| `lib/csv-export.ts` | `downloadCsv()` — browser-side Blob download |
| `app/api/export/sheets/route.ts` | Google Sheets export API route |
| `app/brand/page.tsx` | Live interactive brand page at `/brand` |

---

*Last updated: 2026-06-08*
