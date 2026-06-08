"use client";

import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type KeyboardEvent,
  type SetStateAction,
} from "react";
import {
  AlertCircle,
  ArrowUp,
  BarChart3,
  Bot,
  Check,
  CheckSquare,
  Download,
  ImageIcon,
  Loader2,
  Menu,
  Paperclip,
  Search,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  Video,
  X,
} from "lucide-react";
import type { AssetSummary, CreativeThreadSummary, InceptUser, JobSummary, WorkspaceSummary } from "@incept/shared";
import { HomeView } from "./HomeView";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { createImageGenerationJob, deleteAssets, downloadAssetsZip, listAssets, uploadAsset } from "@/lib/incept-api";
import type { AppView } from "./Sidebar";
import { CreateImageView } from "./CreateImageView";
import { AppHeader } from "@/components/ui/app-header";

// ─── Types ────────────────────────────────────────────────────────────────────

type GenerationMode = "image" | "video" | "gif" | "analysis";

interface Attachment {
  localId: string;
  assetId?: string;
  previewUrl: string;
  name: string;
  uploading: boolean;
  file: File;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  attachments?: Omit<Attachment, "file">[];
  status?: "generating" | "done" | "error";
  progress?: number;
  assets?: AssetSummary[];
  jobId?: string;
  providerLabel?: string;
  timestamp: Date;
}

interface WorkspaceProps {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
  liveAssets: AssetSummary[];
  setLiveAssets: Dispatch<SetStateAction<AssetSummary[]>>;
  liveJobs: JobSummary[];
  setLiveJobs: Dispatch<SetStateAction<JobSummary[]>>;
  liveThreads: CreativeThreadSummary[];
  setLiveThreads: Dispatch<SetStateAction<CreativeThreadSummary[]>>;
  currentUser: InceptUser;
  activeWorkspaceId: string;
  activeThreadId: string | null;
  onThreadSelect: (id: string | null) => void;
  workspaces: WorkspaceSummary[];
  onJobCreated: (job: JobSummary) => void;
  onMobileMenuOpen: () => void;
  onThreadSelectFromHome: (workspaceId: string, threadId: string) => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

// ─── Constants ────────────────────────────────────────────────────────────────

const ALL_SIZES = ["300x250", "320x480", "1200x628", "728x90", "1200x600", "320x50"];
const DEFAULT_SIZES = ["300x250", "320x480", "1200x628"];

const MODES: { id: GenerationMode; label: string; icon: React.FC<{ className?: string }>; disabled?: boolean }[] = [
  { id: "image",    label: "Image Gen",  icon: ({ className }) => <ImageIcon className={className} /> },
  { id: "video",    label: "Video Gen",  icon: ({ className }) => <Video className={className} />, disabled: true },
  { id: "gif",      label: "GIF",        icon: ({ className }) => <Sparkles className={className} />, disabled: true },
  { id: "analysis", label: "Analysis",   icon: ({ className }) => <BarChart3 className={className} />, disabled: true },
];

const QUICK_PROMPTS = [
  {
    icon: <ImageIcon className="size-5" />,
    title: "Batch concepts",
    detail: "2 master concepts across all required ad sizes",
    prompt: "Generate 2 premium lifestyle concepts for a skincare campaign. Export into all selected ad sizes with performance-ready copy space.",
  },
  {
    icon: <Sparkles className="size-5" />,
    title: "Style transfer",
    detail: "Apply a reference image's style to new creatives",
    prompt: "Use the attached reference image as style inspiration. Generate fresh ad creatives that match the visual language and mood.",
  },
  {
    icon: <BarChart3 className="size-5" />,
    title: "Performance set",
    detail: "Creatives optimized for CTR and clarity",
    prompt: "Create performance-optimized ad creatives with clear visual hierarchy, bold headline space, and a strong CTA area.",
  },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function MiniAssetTile({ asset }: { asset: AssetSummary }) {
  const hasReal = Boolean(asset.url && !asset.url.includes("placeholder"));
  return (
    <div className="relative aspect-square overflow-hidden border border-border bg-muted">
      {hasReal ? (
        <img alt={asset.title} className="h-full w-full object-cover" src={asset.url} />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-[#07111F] to-[#171A20]">
          <ImageIcon className="size-4 text-white/20" />
        </div>
      )}
      {asset.width && asset.height && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-1.5 pb-1 pt-4">
          <span className="text-[9px] leading-none text-white/80">{asset.width}×{asset.height}</span>
        </div>
      )}
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end gap-3">
        <div className="max-w-[78%]">
          {message.attachments && message.attachments.length > 0 && (
            <div className="mb-2 flex flex-wrap justify-end gap-2">
              {message.attachments.map((att) => (
                <div key={att.localId} className="relative h-20 w-20 overflow-hidden rounded-xl border border-border shadow-sm">
                  <img alt={att.name} className="h-full w-full object-cover" src={att.previewUrl} />
                </div>
              ))}
            </div>
          )}
          {message.text && (
            <div className="rounded-2xl rounded-tr-sm border border-accent/20 bg-accent/10 px-4 py-3 text-sm leading-6">
              {message.text}
            </div>
          )}
          <p className="mt-1 text-right text-[10px] text-muted-foreground">
            {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <Avatar className="mt-0.5 size-8 shrink-0 bg-foreground text-background">
        <AvatarFallback className="text-xs font-bold">LL</AvatarFallback>
      </Avatar>
      <div className="min-w-0 max-w-[85%]">
        {message.status === "generating" && (
          <div className="rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-4">
            <div className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
              <span className="size-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              Generating with {message.providerLabel}…
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-accent transition-all duration-700"
                style={{ width: `${Math.max(message.progress ?? 0, 5)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{message.progress ?? 0}%</p>
          </div>
        )}
        {message.status === "error" && (
          <div className="flex items-start gap-2 rounded-2xl rounded-tl-sm border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            Generation failed. Check API key / ADC credentials and try again.
          </div>
        )}
        {message.status === "done" && message.assets && (
          <div>
            <div className={cn(
              "grid gap-2",
              message.assets.length === 1 ? "grid-cols-1 max-w-[180px]"
              : message.assets.length === 2 ? "grid-cols-2 max-w-[260px]"
              : "grid-cols-3 max-w-[340px]"
            )}>
              {message.assets.slice(0, 6).map((a) => <MiniAssetTile key={a.id} asset={a} />)}
            </div>
            {message.assets.length > 6 && (
              <p className="mt-1.5 text-xs text-muted-foreground">+{message.assets.length - 6} more in Results →</p>
            )}
            <p className="mt-2 text-[11px] text-muted-foreground">
              {message.assets.length} assets · {message.providerLabel} ·{" "}
              {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </p>
          </div>
        )}
        {!message.status && message.text && (
          <div className="rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3 text-sm leading-6 text-muted-foreground">
            {message.text}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Chat Input Box (reused in both welcome + active states) ──────────────────

function ChatInputBox({
  draft, setDraft,
  attachments, onAttach, onRemoveAttachment,
  mode, setMode,
  selectedSizes, setSelectedSizes,
  provider, setProvider,
  variants, setVariants,
  sending,
  onSend,
  compact = false,
}: {
  draft: string; setDraft: (v: string) => void;
  attachments: Attachment[]; onAttach: (files: FileList | null) => void; onRemoveAttachment: (id: string) => void;
  mode: GenerationMode; setMode: (m: GenerationMode) => void;
  selectedSizes: string[]; setSelectedSizes: (fn: (prev: string[]) => string[]) => void;
  provider: "openai" | "gemini"; setProvider: (p: "openai" | "gemini") => void;
  variants: number; setVariants: (v: number) => void;
  sending: boolean;
  onSend: () => void;
  compact?: boolean;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [showOptions, setShowOptions] = useState(false);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !sending) { e.preventDefault(); onSend(); }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setDraft(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  const canSend = (draft.trim().length > 0 || attachments.length > 0) && !sending;

  return (
    <div className="w-full">
      {/* Attachment thumbnails */}
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {attachments.map((att) => (
            <div key={att.localId} className="group relative h-14 w-14 overflow-hidden rounded-xl border border-border">
              <img alt={att.name} className="h-full w-full object-cover" src={att.previewUrl} />
              {att.uploading && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                  <span className="size-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                </div>
              )}
              <button
                className="absolute right-0.5 top-0.5 hidden rounded-full bg-black/70 p-0.5 text-white group-hover:flex"
                onClick={() => onRemoveAttachment(att.localId)}
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Main input card */}
      <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-shadow focus-within:border-accent focus-within:shadow-[0_0_0_3px_rgba(53,111,236,0.08)]">
        {/* Textarea */}
        <textarea
          ref={textareaRef}
          className={cn(
            "w-full resize-none bg-transparent px-4 pt-4 pb-2 text-sm leading-6 outline-none placeholder:text-muted-foreground",
            compact ? "min-h-[60px]" : "min-h-[80px]"
          )}
          disabled={sending}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={
            attachments.length > 0
              ? "Describe how to use this reference image…"
              : mode === "image"
              ? "Describe the creative you want to generate…"
              : mode === "gif"
              ? "Describe the GIF animation you want…"
              : "Ask anything…"
          }
          rows={compact ? 2 : 3}
          value={draft}
        />

        {/* Mode chips + actions row */}
        <div className="flex flex-wrap items-center gap-2 border-t border-border/60 px-3 py-2.5">
          {MODES.map((m) => {
            const active = mode === m.id && !m.disabled;
            return (
              <button
                key={m.id}
                disabled={m.disabled}
                onClick={() => !m.disabled && setMode(m.id)}
                title={m.disabled ? "Coming soon" : undefined}
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  active
                    ? "border-accent bg-soft-accent text-accent"
                    : m.disabled
                    ? "cursor-not-allowed border-border text-muted-foreground/40"
                    : "border-border text-muted-foreground hover:border-accent hover:text-foreground"
                )}
              >
                <m.icon className="size-3" />
                {m.label}
                {m.disabled && <span className="ml-0.5 text-[9px] opacity-60">soon</span>}
              </button>
            );
          })}

          <div className="ml-auto flex items-center gap-2">
            {/* Attach file */}
            <input
              accept="image/*"
              className="sr-only"
              multiple
              onChange={(e) => onAttach(e.target.files)}
              ref={fileInputRef}
              type="file"
            />
            <button
              className="flex size-8 items-center justify-center rounded-full border border-dashed border-border text-muted-foreground transition-colors hover:border-accent hover:text-accent"
              onClick={() => fileInputRef.current?.click()}
              title="Attach reference image"
            >
              <Paperclip className="size-3.5" />
            </button>

            {/* Send */}
            <Button
              className="size-8 rounded-xl"
              disabled={!canSend}
              onClick={onSend}
              size="icon"
            >
              {sending
                ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                : <ArrowUp className="size-4" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Sizes + Options row */}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Sizes</span>
        {ALL_SIZES.map((size) => {
          const active = selectedSizes.includes(size);
          return (
            <button
              key={size}
              onClick={() =>
                setSelectedSizes((cur) =>
                  cur.includes(size) ? cur.filter((s) => s !== size) : [...cur, size]
                )
              }
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-[10px] font-semibold transition-colors",
                active
                  ? "border-accent bg-soft-accent text-accent"
                  : "border-border text-muted-foreground hover:border-accent/60"
              )}
            >
              {size}
            </button>
          );
        })}

        <button
          onClick={() => setShowOptions((v) => !v)}
          className={cn(
            "ml-auto flex items-center gap-1 text-[10px] font-medium transition-colors",
            showOptions ? "text-accent" : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Settings2 className="size-3" />
          Options
        </button>
      </div>

      {/* Options panel */}
      {showOptions && (
        <div className="mt-2 flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card px-4 py-3">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Provider
            <select
              className="rounded-lg border border-border bg-background px-2 py-1 text-xs text-foreground outline-none focus:border-accent"
              onChange={(e) => setProvider(e.target.value as "openai" | "gemini")}
              value={provider}
            >
              <option value="openai">OpenAI DALL·E 3</option>
              <option value="gemini">Vertex AI Imagen</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Variants per size
            <div className="flex rounded-lg border border-border overflow-hidden">
              {[1, 2].map((n) => (
                <button
                  key={n}
                  onClick={() => setVariants(n)}
                  className={cn(
                    "px-3 py-1 text-xs font-medium transition-colors",
                    variants === n ? "bg-accent text-white" : "bg-background text-muted-foreground hover:bg-muted"
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
          </label>
          <p className="text-[10px] text-muted-foreground">
            {provider === "gemini"
              ? "Vertex AI uses Application Default Credentials (gcloud auth application-default login)"
              : "OpenAI uses OPENAI_API_KEY from your .env"}
          </p>
        </div>
      )}

      <p className="mt-2 text-center text-[10px] text-muted-foreground">
        <kbd className="rounded border bg-muted px-1 text-[9px]">Enter</kbd> to send ·{" "}
        <kbd className="rounded border bg-muted px-1 text-[9px]">Shift+Enter</kbd> for new line
      </p>
    </div>
  );
}

// ─── Other views ──────────────────────────────────────────────────────────────

function ComingSoon({ activeView }: { activeView: AppView }) {
  const details =
    activeView === "Analyze"
      ? ["Looker Agent", "Performance Lab", "BigQuery creative lineage analysis"]
      : activeView === "Automate"
      ? ["Workflow automation", "Creative optimization loops", "Scheduled jobs"]
      : [];
  return (
    <Card className="min-h-[520px]">
      <CardContent className="flex min-h-[520px] flex-col items-center justify-center gap-5 p-10 text-center">
        <div className="grid size-14 place-items-center rounded-xl bg-soft-accent text-accent">
          {activeView === "Analyze" ? <BarChart3 className="size-7" /> : <Bot className="size-7" />}
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">{activeView}</p>
          <h2 className="mt-2 font-display text-3xl font-semibold">Coming soon</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
            This capability will come online after the image generation workspace is stable.
          </p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          {details.map((d) => <Badge key={d} variant="secondary">{d}</Badge>)}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Library helpers ──────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function getContactSheetRole(asset: AssetSummary): string | null {
  const value = asset.analysis?.contact_sheet_role;
  return typeof value === "string" ? value : null;
}

function LibraryView({
  activeView,
  liveAssets,
  setLiveAssets,
}: {
  activeView: AppView;
  liveAssets: AssetSummary[];
  setLiveAssets: Dispatch<SetStateAction<AssetSummary[]>>;
}) {
  const [tab, setTab] = useState<"generated" | "assets">("generated");
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  // ── Multi-select ──
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [downloadPrefix, setDownloadPrefix] = useState("incept");
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting] = useState(false);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll(assets: AssetSummary[]) {
    const allIds = assets.map((a) => a.id);
    const allSelected = allIds.every((id) => selected.has(id));
    if (allSelected) {
      setSelected((prev) => {
        const next = new Set(prev);
        allIds.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      setSelected((prev) => new Set([...prev, ...allIds]));
    }
  }

  async function handleDownload() {
    const ids = Array.from(selected);
    if (!ids.length) return;
    setDownloading(true);
    try { await downloadAssetsZip(ids, downloadPrefix || "incept"); }
    catch (e) { console.error(e); }
    finally { setDownloading(false); }
  }

  async function handleDelete() {
    const ids = Array.from(selected);
    if (!ids.length) return;
    if (!confirm(`Delete ${ids.length} asset(s)? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await deleteAssets(ids);
      setLiveAssets((prev) => prev.filter((a) => !ids.includes(a.id)));
      setSelected(new Set());
    } catch (e) { console.error(e); }
    finally { setDeleting(false); }
  }

  if (activeView === "Settings") {
    return (
      <Card>
        <CardContent className="grid min-h-[520px] gap-5 p-7">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">Settings</p>
            <h2 className="mt-3 font-display text-4xl font-semibold">Provider configuration</h2>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {["API Keys", "Model Defaults", "Team & Permissions", "Billing"].map((name) => (
              <Card key={name}><CardHeader><CardTitle className="text-base">{name}</CardTitle></CardHeader></Card>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const generatedAssets = liveAssets.filter(
    (a) => a.provider !== "upload" && a.jobId && !["sheet", "sheet_source"].includes(getContactSheetRole(a) ?? "")
  );
  const uploadedAssets = liveAssets.filter((a) => a.provider === "upload");
  const q = search.trim().toLowerCase();
  const filteredGenerated = q
    ? generatedAssets.filter((a) =>
        [a.title, a.theme, a.model, a.provider]
          .filter(Boolean).some((v) => String(v).toLowerCase().includes(q))
      )
    : generatedAssets;
  const filteredUploads = q
    ? uploadedAssets.filter((a) => a.title.toLowerCase().includes(q))
    : uploadedAssets;

  return (
    <div>
      {/* Search bar — above tabs, filters both tabs */}
      <div className="mb-5 flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-2 text-sm text-muted-foreground focus-within:border-accent">
        <Search className="size-4 shrink-0" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search library…"
          className="min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-muted-foreground"
        />
        {search && (
          <button onClick={() => setSearch("")}>
            <X className="size-4" />
          </button>
        )}
      </div>

      {/* Tabs + action buttons */}
      <div className="mb-6 flex items-center gap-6 border-b border-border">
        <div className="flex gap-6">
          {(["generated", "assets"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "relative pb-3 text-sm font-medium capitalize transition-colors",
                tab === t
                  ? "text-foreground after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:rounded-full after:bg-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {t === "generated" ? "Generated" : "Assets"}
              <span className="ml-2 text-[10px] text-muted-foreground">
                {t === "generated" ? generatedAssets.length : uploadedAssets.length}
              </span>
            </button>
          ))}
        </div>
        {tab === "assets" && (
          <div className="ml-auto flex items-center gap-2 pb-3">
            <button className="flex items-center gap-1.5 rounded-xl border border-border px-3 py-1.5 text-sm font-medium hover:bg-muted">
              New folder
            </button>
            <button className="flex items-center gap-1.5 rounded-xl bg-foreground px-3 py-1.5 text-sm font-medium text-background hover:opacity-80">
              <span>↑</span> Upload
            </button>
          </div>
        )}
      </div>

      {/* ── Selection toolbar (shown when any item selected) ── */}
      {selected.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 shadow-sm">
          <span className="text-sm font-medium">{selected.size} selected</span>
          <div className="flex items-center gap-1 rounded-lg border border-border bg-background px-2">
            <span className="text-[11px] text-muted-foreground">Prefix:</span>
            <input
              value={downloadPrefix}
              onChange={(e) => setDownloadPrefix(e.target.value.replace(/[^a-zA-Z0-9_-]/g, ""))}
              placeholder="incept"
              className="w-24 bg-transparent px-1 py-1 text-xs outline-none"
            />
          </div>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background hover:opacity-80 disabled:opacity-50"
          >
            {downloading ? <Loader2 className="size-3 animate-spin" /> : <Download className="size-3" />}
            Download
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center gap-1.5 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/20 disabled:opacity-50"
          >
            {deleting ? <Loader2 className="size-3 animate-spin" /> : <Trash2 className="size-3" />}
            Delete
          </button>
          <button
            onClick={() => setSelected(new Set())}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground"
          >
            Clear selection
          </button>
        </div>
      )}

      {/* ── Generated tab ── */}
      {tab === "generated" && (
        filteredGenerated.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
            <div className="grid size-14 place-items-center rounded-2xl border-2 border-dashed border-border bg-muted/40">
              <ImageIcon className="size-6 text-muted-foreground/40" />
            </div>
            <p className="font-medium">No generated images yet</p>
            <p className="text-sm text-muted-foreground">Go to Create to generate your first batch</p>
          </div>
        ) : (
          <>
            {/* Select-all row */}
            <div className="mb-2 flex items-center gap-2">
              <button
                onClick={() => toggleAll(filteredGenerated)}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                {filteredGenerated.every((a) => selected.has(a.id))
                  ? <CheckSquare className="size-4 text-accent" />
                  : <Square className="size-4" />}
                Select all
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {filteredGenerated.map((asset) => {
                const hasReal = Boolean(asset.url && !asset.url.includes("placeholder"));
                const isSel = selected.has(asset.id);
                return (
                  <div key={asset.id} className="group flex flex-col gap-1.5">
                    <div
                      className={cn(
                        "relative aspect-square cursor-pointer overflow-hidden border-2 bg-[#07111F] transition-all",
                        isSel ? "border-accent shadow-[0_0_0_1px_hsl(var(--accent)/0.3)]" : "border-transparent hover:border-border"
                      )}
                      onClick={() => toggleSelect(asset.id)}
                    >
                      {hasReal ? (
                        <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <ImageIcon className="size-6 text-white/20" />
                        </div>
                      )}
                      {/* Checkbox */}
                      <div className={cn(
                        "absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full border-2 transition-all",
                        isSel
                          ? "border-accent bg-accent text-white"
                          : "border-white/50 bg-black/30 opacity-0 group-hover:opacity-100"
                      )}>
                        {isSel && <Check className="size-3" />}
                      </div>
                      {/* Size + format label — always visible */}
                      <div className="absolute bottom-1.5 left-1.5 rounded-md bg-black/75 px-1.5 py-0.5 backdrop-blur-sm">
                        <span className="text-[8px] font-semibold text-white">
                          {asset.width && asset.height
                            ? `${asset.width}×${asset.height} · ${asset.type === "gif" ? "GIF" : "PNG"}`
                            : asset.type === "gif" ? "GIF" : "PNG"}
                        </span>
                      </div>
                    </div>
                    <p className="truncate text-[11px] font-medium">{asset.title}</p>
                    <p className="text-[10px] text-muted-foreground">{asset.model}</p>
                  </div>
                );
              })}
            </div>
          </>
        )
      )}

      {/* ── Assets tab ── */}
      {tab === "assets" && (
        <div>
          {/* View toggle */}
          <div className="mb-4 flex items-center justify-end gap-3">
            <div className="flex overflow-hidden rounded-xl border border-border">
              {(["list", "grid"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setViewMode(m)}
                  className={cn(
                    "flex size-9 items-center justify-center transition-colors",
                    viewMode === m ? "bg-foreground text-background" : "bg-background text-muted-foreground hover:bg-muted"
                  )}
                >
                  {m === "list" ? (
                    <svg className="size-4" viewBox="0 0 16 16" fill="none">
                      <rect x="2" y="3" width="12" height="1.5" rx="0.75" fill="currentColor"/>
                      <rect x="2" y="7.25" width="12" height="1.5" rx="0.75" fill="currentColor"/>
                      <rect x="2" y="11.5" width="12" height="1.5" rx="0.75" fill="currentColor"/>
                    </svg>
                  ) : (
                    <svg className="size-4" viewBox="0 0 16 16" fill="none">
                      <rect x="2" y="2" width="5.5" height="5.5" rx="1" fill="currentColor"/>
                      <rect x="8.5" y="2" width="5.5" height="5.5" rx="1" fill="currentColor"/>
                      <rect x="2" y="8.5" width="5.5" height="5.5" rx="1" fill="currentColor"/>
                      <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1" fill="currentColor"/>
                    </svg>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Filter chips */}
          <div className="mb-5">
            <button className="flex items-center gap-1 rounded-full border border-border px-3 py-1 text-xs font-medium text-muted-foreground hover:bg-muted">
              + Owner
            </button>
          </div>

          {filteredUploads.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
              <div className="grid size-14 place-items-center rounded-2xl border-2 border-dashed border-border bg-muted/40">
                <ImageIcon className="size-6 text-muted-foreground/40" />
              </div>
              <p className="font-medium">No uploaded assets</p>
              <p className="text-sm text-muted-foreground">
                Upload reference images to use them in generation
              </p>
            </div>
          ) : viewMode === "list" ? (
            /* List view */
            <div>
              <div className="mb-1 grid grid-cols-[32px_minmax(0,1fr)_160px_100px_80px] gap-4 px-4 py-2 text-xs font-semibold text-muted-foreground">
                <button onClick={() => toggleAll(filteredUploads)} className="flex items-center justify-center">
                  {filteredUploads.every((a) => selected.has(a.id))
                    ? <CheckSquare className="size-3.5 text-accent" />
                    : <Square className="size-3.5" />}
                </button>
                <span>Name</span>
                <span>Added</span>
                <span>Type</span>
                <span></span>
              </div>
              <div className="divide-y divide-border rounded-xl border border-border">
                {filteredUploads.map((asset) => {
                  const hasReal = Boolean(asset.url && !asset.url.includes("placeholder"));
                  const isSel = selected.has(asset.id);
                  return (
                    <div
                      key={asset.id}
                      className={cn(
                        "grid grid-cols-[32px_minmax(0,1fr)_160px_100px_80px] items-center gap-4 px-4 py-3 transition-colors hover:bg-muted/30",
                        isSel && "bg-soft-accent/40"
                      )}
                    >
                      <button onClick={() => toggleSelect(asset.id)} className="flex items-center justify-center">
                        <div className={cn(
                          "flex size-4 items-center justify-center rounded border",
                          isSel ? "border-accent bg-accent text-white" : "border-border"
                        )}>
                          {isSel && <Check className="size-2.5" />}
                        </div>
                      </button>
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="size-9 shrink-0 overflow-hidden border border-border bg-muted">
                          {hasReal ? (
                            <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center">
                              <ImageIcon className="size-4 text-muted-foreground" />
                            </div>
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{asset.title}</p>
                          <p className="text-[11px] text-muted-foreground">
                            {asset.width && asset.height ? `${asset.width}×${asset.height} · ` : ""}
                            {asset.type === "gif" ? "GIF" : "PNG"}
                          </p>
                        </div>
                      </div>
                      <span className="text-sm text-muted-foreground">{fmtDate(asset.createdAt)}</span>
                      <span className="text-sm text-muted-foreground capitalize">{asset.type}</span>
                      <button
                        onClick={async () => {
                          if (!confirm("Delete this asset?")) return;
                          await deleteAssets([asset.id]);
                          setLiveAssets((prev) => prev.filter((a) => a.id !== asset.id));
                          setSelected((prev) => { const n = new Set(prev); n.delete(asset.id); return n; });
                        }}
                        className="flex items-center justify-center rounded-lg p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            /* Grid view */
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {filteredUploads.map((asset) => {
                const hasReal = Boolean(asset.url && !asset.url.includes("placeholder"));
                const isSel = selected.has(asset.id);
                return (
                  <div key={asset.id} className="group flex flex-col gap-1.5">
                    <div
                      className={cn(
                        "relative aspect-square cursor-pointer overflow-hidden border-2 bg-muted transition-all",
                        isSel ? "border-accent" : "border-transparent hover:border-border"
                      )}
                      onClick={() => toggleSelect(asset.id)}
                    >
                      {hasReal ? (
                        <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <ImageIcon className="size-6 text-muted-foreground/40" />
                        </div>
                      )}
                      <div className={cn(
                        "absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full border-2 transition-all",
                        isSel
                          ? "border-accent bg-accent text-white"
                          : "border-white/50 bg-black/30 opacity-0 group-hover:opacity-100"
                      )}>
                        {isSel && <Check className="size-3" />}
                      </div>
                      {/* Size + format label */}
                      <div className="absolute bottom-1.5 left-1.5 rounded-md bg-black/75 px-1.5 py-0.5 backdrop-blur-sm">
                        <span className="text-[8px] font-semibold text-white">
                          {asset.width && asset.height
                            ? `${asset.width}×${asset.height} · ${asset.type === "gif" ? "GIF" : "PNG"}`
                            : asset.type === "gif" ? "GIF" : "PNG"}
                        </span>
                      </div>
                    </div>
                    <p className="truncate text-[11px] font-medium">{asset.title}</p>
                    <p className="text-[10px] text-muted-foreground">{fmtDate(asset.createdAt)}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function HomeOverview({ onViewChange, assetCount, jobCount }: {
  onViewChange: (v: AppView) => void; assetCount: number; jobCount: number;
}) {
  return (
    <div className="grid gap-5">
      <Card>
        <CardContent className="grid gap-6 p-7 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">Home</p>
            <h2 className="mt-3 font-display text-4xl font-semibold leading-tight">
              Create a workspace for each real campaign or client request.
            </h2>
          </div>
          <Button className="self-end" onClick={() => onViewChange("Workspace")}>Open Workspace</Button>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="grid gap-4 p-7 md:grid-cols-3">
          <div><p className="text-sm text-muted-foreground">Connected assets</p><p className="mt-2 text-4xl font-bold">{assetCount}</p></div>
          <div><p className="text-sm text-muted-foreground">Backend jobs</p><p className="mt-2 text-4xl font-bold">{jobCount}</p></div>
          <div><p className="text-sm text-muted-foreground">Mode</p><p className="mt-2 text-lg font-semibold">API-driven</p></div>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Main Workspace ───────────────────────────────────────────────────────────

export function Workspace({
  activeView, onViewChange,
  liveAssets, setLiveAssets,
  liveJobs, setLiveJobs,
  liveThreads, setLiveThreads,
  currentUser, activeWorkspaceId, activeThreadId, onThreadSelect,
  workspaces, onJobCreated, onMobileMenuOpen, onThreadSelectFromHome,
}: WorkspaceProps) {
  const isChat = activeView === "Workspace";
  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId);
  const greeting = getGreeting();

  // ── Chat state ──
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [sending, setSending] = useState(false);

  // ── Settings state ──
  const [mode, setMode] = useState<GenerationMode>("image");
  const [provider, setProvider] = useState<"openai" | "gemini">("gemini");
  const [selectedSizes, setSelectedSizes] = useState<string[]>(DEFAULT_SIZES);
  const [variants, setVariants] = useState(2);

  // ── Results panel ──
  const [resultsOpen, setResultsOpen] = useState(true);
  const [resultSearch, setResultSearch] = useState("");
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const jobToMsg = useRef<Map<string, string>>(new Map());

  const hasConversation = messages.length > 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Update generating messages when AppShell polling fires
  useEffect(() => {
    setMessages((prev) => {
      let changed = false;
      const next = prev.map((msg) => {
        if (msg.status !== "generating" || !msg.jobId) return msg;
        const job = liveJobs.find((j) => (j.jobId ?? j.id) === msg.jobId);
        if (!job) return msg;
        if (job.status === "completed") {
          const jobAssets = liveAssets.filter((a) => a.jobId === msg.jobId);
          changed = true;
          return { ...msg, status: "done" as const, progress: 100, assets: jobAssets };
        }
        if (job.status === "failed") { changed = true; return { ...msg, status: "error" as const }; }
        if (job.progress !== msg.progress) { changed = true; return { ...msg, progress: job.progress }; }
        return msg;
      });
      return changed ? next : prev;
    });
  }, [liveJobs, liveAssets]);

  // ── Attach files ──
  function handleAttach(files: FileList | null) {
    if (!files) return;
    const newAtts: Attachment[] = Array.from(files).map((file) => ({
      localId: `att_${Math.random().toString(36).slice(2)}`,
      previewUrl: URL.createObjectURL(file),
      name: file.name,
      uploading: false,
      file,
    }));
    setAttachments((prev) => [...prev, ...newAtts]);
  }

  function removeAttachment(localId: string) {
    setAttachments((prev) => {
      const att = prev.find((a) => a.localId === localId);
      if (att) URL.revokeObjectURL(att.previewUrl);
      return prev.filter((a) => a.localId !== localId);
    });
  }

  // ── Quick-prompt click ──
  function handleQuickPrompt(prompt: string) {
    setDraft(prompt);
  }

  // ── Send ──
  async function handleSend() {
    const text = draft.trim();
    if (!text && attachments.length === 0) return;
    if (sending) return;
    setSending(true);

    const userMsgId = `msg_${Date.now()}`;
    const aiMsgId = `msg_${Date.now()}_ai`;
    const now = new Date();
    const providerLabel = provider === "openai" ? "OpenAI DALL·E 3" : "Vertex AI Imagen";

    const userMsg: ChatMessage = {
      id: userMsgId, role: "user", text,
      attachments: attachments.map(({ localId, previewUrl, name, uploading }) => ({ localId, previewUrl, name, uploading })),
      timestamp: now,
    };
    const aiMsg: ChatMessage = {
      id: aiMsgId, role: "assistant", status: "generating",
      text: "", progress: 0, providerLabel, timestamp: now,
    };
    setMessages((prev) => [...prev, userMsg, aiMsg]);
    setDraft("");

    try {
      // Upload reference images
      const referenceIds: string[] = [];
      for (const att of attachments) {
        try {
          const result = await uploadAsset(att.file, activeWorkspaceId, "reference");
          if (result) referenceIds.push(result.id);
        } catch { /* skip failed uploads */ }
      }
      setAttachments([]);

      const outputFormat = mode === "gif" ? "gif" : "image";
      const sizes = selectedSizes.length ? selectedSizes : DEFAULT_SIZES;

      const response = await createImageGenerationJob({
        workspace_id: activeWorkspaceId,
        prompt: text,
        provider,
        model: provider === "openai" ? "gpt-image-2" : "imagen-4.0-generate-001",
        variants,
        aspect_ratio: "multi-size",
        created_by: currentUser.id,
        source_asset_ids: [],
        theme: text.split(/\s+/).slice(0, 3).join(" "),
        output_sizes: sizes,
        output_format: outputFormat,
        reference_asset_ids: referenceIds,
        preserve_layout: false,
        use_reference_style: referenceIds.length > 0,
        client_asset_ids: [],
      });

      const job: JobSummary = {
        id: response.job_id, jobId: response.job_id,
        title: response.title, toolId: response.tool_id,
        status: response.status, progress: response.progress,
        eta: response.status === "completed" ? "Completed" : "Running…",
        lineageKey: response.lineage_key,
      };
      setLiveJobs((prev) => [job, ...prev]);
      onJobCreated(job);
      jobToMsg.current.set(response.job_id, aiMsgId);

      if (response.status === "completed") {
        const newAssets = await listAssets(activeWorkspaceId);
        setLiveAssets(newAssets);
        const jobAssets = newAssets.filter((a) => a.jobId === response.job_id);
        setMessages((prev) =>
          prev.map((m) => m.id === aiMsgId
            ? { ...m, status: "done", progress: 100, assets: jobAssets, jobId: response.job_id }
            : m)
        );
      } else {
        setMessages((prev) =>
          prev.map((m) => m.id === aiMsgId ? { ...m, jobId: response.job_id, progress: 5 } : m)
        );
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) => m.id === aiMsgId ? { ...m, status: "error" } : m)
      );
    } finally {
      setSending(false);
    }
  }

  const filteredAssets = liveAssets.filter((a) => {
    const q = resultSearch.trim().toLowerCase();
    if (!q) return true;
    return [a.title, a.type, a.theme, a.provider, a.model]
      .filter(Boolean).some((v) => String(v).toLowerCase().includes(q));
  });
  const hasRunningJob = liveJobs.some((j) => j.status === "running" || j.status === "queued");

  const sharedInputProps = {
    draft, setDraft,
    attachments, onAttach: handleAttach, onRemoveAttachment: removeAttachment,
    mode, setMode,
    selectedSizes, setSelectedSizes,
    provider, setProvider,
    variants, setVariants,
    sending, onSend: handleSend,
  };

  // ── Create Image view — full-screen, bypasses the chat layout ──
  if (activeView === "Create") {
    return (
      <CreateImageView
        liveAssets={liveAssets}
        setLiveAssets={setLiveAssets}
        liveJobs={liveJobs}
        setLiveJobs={setLiveJobs}
        liveThreads={liveThreads}
        setLiveThreads={setLiveThreads}
        currentUser={currentUser}
        activeWorkspaceId={activeWorkspaceId}
        activeWorkspaceTitle={activeWorkspace?.title}
        activeThreadId={activeThreadId}
        onThreadSelect={onThreadSelect}
        onJobCreated={onJobCreated}
      />
    );
  }

  return (
    <main className="flex-1 min-w-0 grid min-h-screen grid-cols-1">
      {/* ── Left panel ── */}
      <section className="flex min-h-screen min-w-0 flex-col border-r bg-background">
        {/* Header — only in active chat or non-chat views */}
        {(!isChat || hasConversation) && (
          <AppHeader
            variant="header"
            title={isChat && activeWorkspace ? activeWorkspace.title : activeView}
            onMobileMenuOpen={onMobileMenuOpen}
          />
        )}

        {/* Non-chat views */}
        {!isChat && (
          <div className="flex-1 overflow-auto px-7 py-6 max-[860px]:px-4">
            {activeView === "Home" && (
              <HomeView
                liveAssets={liveAssets}
                liveJobs={liveJobs}
                liveThreads={liveThreads}
                workspaces={workspaces}
                onViewChange={onViewChange}
                onThreadSelect={onThreadSelectFromHome}
              />
            )}
            {(activeView === "Analyze" || activeView === "Automate") && <ComingSoon activeView={activeView} />}
            {(activeView === "Library" || activeView === "Settings") && <LibraryView activeView={activeView} liveAssets={liveAssets} setLiveAssets={setLiveAssets} />}
          </div>
        )}

        {/* ── Chat: Welcome screen (no messages yet) ── */}
        {isChat && !hasConversation && (
          <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
            {/* Mobile menu button */}
            <button
              className="absolute left-4 top-4 hidden max-[980px]:flex items-center justify-center size-9 rounded-xl border bg-card"
              onClick={onMobileMenuOpen}
            >
              <Menu className="size-4" />
            </button>

            {/* Orb */}
            <div className="relative mb-8">
              <div className="size-20 rounded-full bg-accent/20 blur-2xl absolute inset-0 scale-150" />
              <div className="relative size-20 rounded-full bg-gradient-to-br from-accent/40 via-accent/20 to-transparent border border-accent/20 shadow-[0_0_40px_rgba(53,111,236,0.2)]" />
            </div>

            {/* Greeting */}
            <p className="text-xl font-semibold text-accent">
              {greeting}, {currentUser.name.split(" ")[0]}.
            </p>
            <h2 className="mt-1 mb-10 font-display text-3xl font-bold text-foreground text-center">
              What would you like to create?
            </h2>

            {/* Input box */}
            <div className="w-full max-w-2xl">
              <ChatInputBox {...sharedInputProps} compact={false} />
            </div>

            {/* Quick-start cards */}
            <div className="mt-10 grid w-full max-w-2xl grid-cols-3 gap-3 max-[600px]:grid-cols-1">
              {QUICK_PROMPTS.map((q) => (
                <button
                  key={q.title}
                  onClick={() => handleQuickPrompt(q.prompt)}
                  className="group rounded-2xl border border-border bg-card p-4 text-left transition-colors hover:border-accent/50 hover:bg-soft-accent"
                >
                  <div className="mb-3 text-muted-foreground group-hover:text-accent transition-colors">
                    {q.icon}
                  </div>
                  <p className="text-sm font-semibold">{q.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground leading-5">{q.detail}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Chat: Active conversation ── */}
        {isChat && hasConversation && (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-6 py-6 max-[860px]:px-4">
              <div className="mx-auto max-w-3xl space-y-6">
                {messages.map((msg) => <ChatBubble key={msg.id} message={msg} />)}
                <div ref={bottomRef} />
              </div>
            </div>

            {/* Input docked at bottom */}
            <div className="shrink-0 border-t bg-background px-6 pb-5 pt-4 max-[860px]:px-4">
              <div className="mx-auto max-w-3xl">
                <ChatInputBox {...sharedInputProps} compact />
              </div>
            </div>
          </>
        )}
      </section>

      {/* Results panel hidden — assets surfaced in Create > History */}
    </main>
  );
}
