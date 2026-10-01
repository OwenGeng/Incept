import { Paintbrush, Video, Image as ImageIcon, LayoutGrid } from "lucide-react";
import { DocsBreadcrumb } from "@/components/docs/DocsChrome";

const CREATE_IMAGE = {
  controls: [
    "Prompt (free text)",
    "Model — Gemini 3.1 Flash / GPT Image 2",
    "Size — multi-select from preset sizes (banner, landscape, portrait/square, endcard)",
    "Format — Static or GIF (GIF restricted to a fixed subset of sizes)",
    "Variants — 1 or 2 per size",
    "Flow tabs — Resize / Theme Create / Kakao / Remediation",
  ],
  flows: [
    { name: "Resize", detail: "Adapt one source image to multiple ad sizes. Max 10 source images." },
    {
      name: "Theme Create",
      detail:
        "Extract a reusable visual style. Two sub-modes: Style Modify (keep layout of Image 1, change style) and Style Transfer (Image 1 = content, Image 2 = style reference). Fields: Image 1 (required), Image 2 (required only for Style Transfer), Style Name, Style Details, Prompt. Selected outputs can be saved as a reusable preset.",
    },
    { name: "Kakao", detail: "Entry point into the Kakao Bizboard flow (see below)." },
    { name: "Remediation", detail: "Upload a flagged/risky creative and generate compliant variants. Max 10 source images." },
  ],
  validation: [
    "At least 1 size selected + non-empty prompt required to submit",
    "GIF format only enabled for a fixed set of sizes",
    "Theme Create: Image 1 always required; Image 2 required only in Style Transfer mode",
  ],
  output: [
    "Results render in a 3-column grid with thumbnail, size/format label, and action buttons",
    "\"Use as Source\" / \"Use as Reference\" feed a result back into Resize or Theme Create",
    "Assets can be multi-selected for batch download / GIF / Kakao generation",
  ],
};

const CREATE_VIDEO = {
  controls: [
    "Mode tabs — Image to Video / Video Remediation",
    "Source image or video (required)",
    "Reference images (optional, multiple)",
    "Prompt (optional but recommended)",
    "Model — Veo 3.1 Fast",
    "Aspect ratio — 16:9 or 9:16",
    "Duration — 4s / 6s / 8s",
    "Variants — 1 or 2",
    "Audio — on/off toggle",
  ],
  validation: [
    "Source required for both modes; prompt or source must be present",
    "All reference uploads must finish before submit is enabled",
    "Budget check — submit is blocked if the request would exceed the configured budget",
  ],
  output: [
    "Generated videos appear in a 2-column library panel; newest auto-focused in the main player",
    "Fullscreen lightbox preview available",
    "Library filters: mode, aspect ratio, duration, audio on/off",
  ],
};

const KAKAO = {
  purpose:
    "Produces a Kakao Bizboard ad banner (960×300px, Kakao specification effective Oct 2026) from a source image, with app icon and Korean copy composited server-side.",
  steps: [
    { step: "1. Upload & Clean", detail: "Upload up to 10 images. Each is auto-cleaned (background/element removal) with per-image pending/done/error status." },
    { step: "2. Confirm", detail: "Review cleaned results; toggle accept/reject per image. Only accepted images proceed." },
    { step: "3. Builder", detail: "Choose a template (App Promo main copy, App Promo main + sub copy, Sales/Traffic main + sub copy, or App Promo main copy with an Object image). For Object, remove the background of every source in one click or upload a transparent PNG per source. Then set the app icon, copy, optional additional info and the gacha checkbox. Preview updates on \"Apply Changes.\"" },
    { step: "4. Create", detail: "Batch-composes final PNGs and creates a Kakao job per asset; results land in the asset library." },
  ],
  validation: [
    "Main / sub copy: max 526px; main or sub copy must be at least 240px; main and sub copy cannot be identical",
    "App download copy (App Promo templates): must contain \"앱\"/\"app\"/\"App\"/\"APP\" and fit before the arrow; app icon is required",
    "No emoji or disallowed special characters (^^, :D, ☞, ☑, ♨ …)",
    "Gacha titles automatically add \"확률형 아이템 포함\" to the additional info line",
    "Output must be 300KB or smaller; max 10 source images per batch",
  ],
  composition: [
    "Transparent 960×300px canvas; Kakao draws the box and adds the AD mark, so no \"Moloco 광고입니다\" disclaimer",
    "Thumbnail 320×222px at the right with 18px rounded corners",
    "Object: transparent-background image, trimmed and scaled to 314px wide at x=603; centred vertically, or centre-cropped when taller than 300px; at least 219px wide after trimming",
    "Font: Pretendard — main copy Bold 46pt #191919, sub copy 38pt #696969, app copy 29pt #696969, additional info 22pt #949494",
    "Layout positions match the Moloco Ads Portal Bizboard generator (kakao_bizboard_v2); without additional info the copy is vertically re-centred per Kakao's official PSD",
  ],
};

const NAVIGATION = {
  points: [
    "Top-level surfaces: Create (Image/Video sub-tabs), Library, Home",
    "Create Image and Create Video are switched via the Image/Video tab in the header",
    "Assets and jobs load on mount; running jobs are polled every 2.5s until completion",
    "Each generation belongs to a thread; a thread selector allows resuming or starting a new session",
  ],
  library: [
    "Two tabs: Generated (has a job) vs Uploaded (no job)",
    "Filters: media type (image/video/GIF/report), plus video-specific filters (mode, aspect ratio, duration, audio), plus text search",
    "Grid view supports drag-to-select a rectangle of assets; List view is a table",
    "Multi-select enables batch download (zipped for >1), GIF generation, Kakao generation, and delete (with confirmation)",
  ],
};

export default function StudioDocsPage() {
  return (
    <div className="mx-auto max-w-4xl px-8 py-10 pb-20">
      <DocsBreadcrumb trail={[{ label: "Overview", href: "/docs" }, { label: "Studio" }]} />

      {/* Header */}
      <div className="mb-6 border-b border-border pb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-soft-accent">
            <Paintbrush className="size-5 text-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Studio — Docs</h1>
            <p className="text-sm text-muted-foreground">Draft outline · pending review — content generated from source code, not yet verified against actual usage</p>
          </div>
        </div>
        <p className="mt-4 text-sm leading-7 text-muted-foreground max-w-2xl">
          Studio is the creative-generation workspace: Create Image, Create Video, and the Kakao Bizboard compositor.
          This page is a structural outline — headings and bullet points only — pending your edits before it becomes
          the real operations doc.
        </p>
      </div>

      <div className="mb-10 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <span className="font-semibold">Draft:</span> every bullet below was extracted directly from the current
        frontend code (CreateImageView, CreateVideoView, KakaoFlow, Workspace). Nothing here is invented, but it
        hasn&apos;t been checked against actual day-to-day usage — flag anything wrong, missing, or mis-prioritized.
      </div>

      {/* Create Image */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <ImageIcon className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Create Image</h2>
        </div>

        <h3 className="text-sm font-semibold text-foreground mb-2">Controls</h3>
        <ul className="mb-5 space-y-1.5">
          {CREATE_IMAGE.controls.map((c) => (
            <li key={c} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {c}
            </li>
          ))}
        </ul>

        <h3 className="text-sm font-semibold text-foreground mb-2">Flow tabs</h3>
        <div className="mb-5 space-y-3">
          {CREATE_IMAGE.flows.map((f) => (
            <div key={f.name} className="rounded-2xl border border-border bg-card px-5 py-4">
              <p className="font-semibold text-foreground text-sm mb-1">{f.name}</p>
              <p className="text-xs text-muted-foreground">{f.detail}</p>
            </div>
          ))}
        </div>

        <h3 className="text-sm font-semibold text-foreground mb-2">Validation</h3>
        <ul className="mb-5 space-y-1.5">
          {CREATE_IMAGE.validation.map((v) => (
            <li key={v} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {v}
            </li>
          ))}
        </ul>

        <h3 className="text-sm font-semibold text-foreground mb-2">Output handling</h3>
        <ul className="space-y-1.5">
          {CREATE_IMAGE.output.map((o) => (
            <li key={o} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {o}
            </li>
          ))}
        </ul>
      </section>

      {/* Create Video */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <Video className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Create Video</h2>
        </div>

        <h3 className="text-sm font-semibold text-foreground mb-2">Controls</h3>
        <ul className="mb-5 space-y-1.5">
          {CREATE_VIDEO.controls.map((c) => (
            <li key={c} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {c}
            </li>
          ))}
        </ul>

        <h3 className="text-sm font-semibold text-foreground mb-2">Validation</h3>
        <ul className="mb-5 space-y-1.5">
          {CREATE_VIDEO.validation.map((v) => (
            <li key={v} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {v}
            </li>
          ))}
        </ul>

        <h3 className="text-sm font-semibold text-foreground mb-2">Output handling</h3>
        <ul className="space-y-1.5">
          {CREATE_VIDEO.output.map((o) => (
            <li key={o} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {o}
            </li>
          ))}
        </ul>
      </section>

      {/* Kakao Bizboard */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <LayoutGrid className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Kakao Bizboard Flow</h2>
        </div>
        <p className="mb-5 text-sm text-muted-foreground">{KAKAO.purpose}</p>

        <h3 className="text-sm font-semibold text-foreground mb-2">Steps</h3>
        <div className="mb-5 space-y-3">
          {KAKAO.steps.map((s) => (
            <div key={s.step} className="rounded-2xl border border-border bg-card px-5 py-4">
              <p className="font-semibold text-foreground text-sm mb-1">{s.step}</p>
              <p className="text-xs text-muted-foreground">{s.detail}</p>
            </div>
          ))}
        </div>

        <h3 className="text-sm font-semibold text-foreground mb-2">Validation rules</h3>
        <ul className="mb-5 space-y-1.5">
          {KAKAO.validation.map((v) => (
            <li key={v} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {v}
            </li>
          ))}
        </ul>

        <h3 className="text-sm font-semibold text-foreground mb-2">Composition details</h3>
        <ul className="space-y-1.5">
          {KAKAO.composition.map((c) => (
            <li key={c} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {c}
            </li>
          ))}
        </ul>
      </section>

      {/* Navigation & Library */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6">
          <LayoutGrid className="size-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Workspace Navigation & Asset Library</h2>
        </div>

        <h3 className="text-sm font-semibold text-foreground mb-2">Navigation</h3>
        <ul className="mb-5 space-y-1.5">
          {NAVIGATION.points.map((p) => (
            <li key={p} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {p}
            </li>
          ))}
        </ul>

        <h3 className="text-sm font-semibold text-foreground mb-2">Library</h3>
        <ul className="space-y-1.5">
          {NAVIGATION.library.map((l) => (
            <li key={l} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
              {l}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
