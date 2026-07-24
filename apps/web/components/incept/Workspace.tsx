"use client";

import {
  useEffect,
  useMemo,
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
  Maximize2,
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
import type { AssetSummary, CreativeThreadSummary, InceptUser, JobSummary } from "@incept/shared";
import { HomeView } from "./HomeView";
import { CreateWorkbenchView } from "./CreateWorkbenchView";
import { VideoProductionView } from "./VideoProductionView";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { createImageGenerationJob, createKakaoBizboardJob, deleteAssets, downloadAssetFile, downloadAssetsZip, generateGifFromAsset, getAssetFileExtension, listAssets, uploadAsset, type ContentScope } from "@/lib/incept-api";
import {
  buildKakaoDisclosure,
  composeKakaoBizboard,
  KAKAO_DEFAULT_DISCLOSURE,
  KAKAO_DEFAULT_MAIN_COPY,
  KAKAO_DEFAULT_SUBTITLE,
  loadSpoqaFonts,
  validateKakaoBizboardInputs,
} from "@/lib/kakao-compositor";
import type { AppView } from "./Sidebar";
import { KakaoBatchModal } from "./CreateImageView";
import { UsageView } from "./UsageView";
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
  contentScope: ContentScope;
  activeWorkspaceId: string;
  activeThreadId: string | null;
  onThreadSelect: (id: string | null) => void;
  onJobCreated: (job: JobSummary) => void;
  onMobileMenuOpen: () => void;
  onThreadSelectFromHome: (threadId: string) => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function ZoomModal({
  asset,
  onClose,
}: {
  asset: AssetSummary;
  onClose: () => void;
}) {
  const label =
    asset.width && asset.height
      ? `${asset.width}x${asset.height} · ${getAssetFileExtension(asset).toUpperCase()}`
      : getAssetFileExtension(asset).toUpperCase();

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 p-6" onClick={onClose}>
      <div
        className="relative flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-[#07111F] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 z-10 rounded-full bg-black/50 p-2 text-white hover:bg-black/70"
        >
          <X className="size-4" />
        </button>
        <div className="flex min-h-0 flex-1 items-center justify-center bg-black/30 p-6">
          {asset.type === "video" ? (
            <video
              src={asset.url}
              controls
              playsInline
              className="max-h-[72vh] max-w-full rounded-2xl object-contain"
            />
          ) : (
            <img src={asset.url} alt={asset.title} className="max-h-[72vh] max-w-full rounded-2xl object-contain" />
          )}
        </div>
        <div className="flex items-center gap-3 border-t border-white/10 bg-card px-5 py-4">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-foreground">{asset.title}</p>
            <p className="mt-1 text-xs text-muted-foreground">{label}</p>
          </div>
        </div>
      </div>
    </div>
  );
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
        asset.type === "video" ? (
          <video
            src={asset.url}
            className="h-full w-full object-cover"
            muted
            playsInline
            preload="metadata"
          />
        ) : (
          <img alt={asset.title} className="h-full w-full object-cover" src={asset.url} />
        )
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
  const details = activeView === "Analyze"
    ? ["Looker Agent", "Performance Lab", "BigQuery creative lineage analysis"]
    : [];
  return (
    <Card className="min-h-[520px]">
      <CardContent className="flex min-h-[520px] flex-col items-center justify-center gap-5 p-10 text-center">
        <div className="grid size-14 place-items-center rounded-xl bg-soft-accent text-accent">
          <BarChart3 className="size-7" />
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

function LibraryView({
  activeView,
  liveAssets,
  setLiveAssets,
  setLiveJobs,
  onJobCreated,
  activeWorkspaceId,
  contentScope,
  activeThreadId,
}: {
  activeView: AppView;
  liveAssets: AssetSummary[];
  setLiveAssets: Dispatch<SetStateAction<AssetSummary[]>>;
  setLiveJobs: Dispatch<SetStateAction<JobSummary[]>>;
  onJobCreated: (job: JobSummary) => void;
  activeWorkspaceId: string;
  contentScope: ContentScope;
  activeThreadId: string | null;
}) {
  const [tab, setTab] = useState<"generated" | "assets">("generated");
  const [mediaFilter, setMediaFilter] = useState<"all" | "image" | "video" | "gif" | "report" | "playable">("all");
  const [videoModeFilter, setVideoModeFilter] = useState<string>("all");
  const [videoAspectFilter, setVideoAspectFilter] = useState<string>("all");
  const [videoDurationFilter, setVideoDurationFilter] = useState<string>("all");
  const [videoAudioFilter, setVideoAudioFilter] = useState<"all" | "audio_on" | "audio_off">("all");
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  const [selectMode, setSelectMode] = useState(false);

  // ── Multi-select ──
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [downloading, setDownloading] = useState(false);
  const [gifGenerating, setGifGenerating] = useState(false);
  const [kakaoBatchOpen, setKakaoBatchOpen] = useState(false);
  const [kakaoBatchSubmitting, setKakaoBatchSubmitting] = useState(false);
  const [kakaoBatchAppIconUrl, setKakaoBatchAppIconUrl] = useState<string | null>(null);
  const [kakaoBatchMainCopy, setKakaoBatchMainCopy] = useState(KAKAO_DEFAULT_MAIN_COPY);
  const [kakaoBatchAppDownloadCopy, setKakaoBatchAppDownloadCopy] = useState(KAKAO_DEFAULT_SUBTITLE);
  const [kakaoBatchDspName, setKakaoBatchDspName] = useState(KAKAO_DEFAULT_DISCLOSURE);
  const [kakaoBatchGacha, setKakaoBatchGacha] = useState(false);
  const [kakaoBatchPreviewUrl, setKakaoBatchPreviewUrl] = useState<string | null>(null);
  const [kakaoBatchPreviewAssetIndex, setKakaoBatchPreviewAssetIndex] = useState(0);
  const [kakaoBatchValidationErrors, setKakaoBatchValidationErrors] = useState<string[]>([]);
  const [kakaoBatchMainCopyWidthPx, setKakaoBatchMainCopyWidthPx] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const [zoomedAsset, setZoomedAsset] = useState<AssetSummary | null>(null);
  const [uploadingAssets, setUploadingAssets] = useState(false);
  const assetUploadInputRef = useRef<HTMLInputElement | null>(null);
  const lastSelectionSignatureRef = useRef("");
  const dragSelectContainerRef = useRef<HTMLDivElement | null>(null);
  const dragSelectOriginRef = useRef<{ x: number; y: number } | null>(null);
  const dragSelectPointerIdRef = useRef<number | null>(null);
  const dragSelectMovedRef = useRef(false);
  const suppressSelectClickRef = useRef(false);
  const suppressSelectClickTimerRef = useRef<number | null>(null);
  const [dragSelectRect, setDragSelectRect] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

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

  useEffect(() => {
    setSelected(new Set());
    setSelectMode(false);
    setVideoModeFilter("all");
    setVideoAspectFilter("all");
    setVideoDurationFilter("all");
    setVideoAudioFilter("all");
  }, [tab, mediaFilter]);

  async function handleDownload() {
    const ids = Array.from(selected);
    if (!ids.length) return;
    setDownloading(true);
    try {
      if (ids.length === 1) {
        const asset = liveAssets.find((item) => item.id === ids[0]);
        if (!asset) throw new Error("Selected asset not found.");
        await downloadAssetFile(asset);
      } else {
        await downloadAssetsZip(ids);
      }
    }
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

  async function handleGenerateGif() {
    const selectedAssets = liveAssets.filter((asset) => selected.has(asset.id) && asset.type !== "gif");
    if (!selectedAssets.length) return;
    setGifGenerating(true);
    try {
      for (const asset of selectedAssets) {
        const response = await generateGifFromAsset({
          workspaceId: activeWorkspaceId,
          assetId: asset.id,
          threadId: asset.threadId ?? undefined,
        });
        const job: JobSummary = {
          id: response.job_id,
          jobId: response.job_id,
          title: response.title,
          toolId: response.tool_id,
          status: response.status,
          progress: response.progress,
          eta: response.status === "completed" ? "Completed" : "Running…",
          lineageKey: response.lineage_key,
        };
        setLiveJobs((prev) => [job, ...prev]);
        onJobCreated(job);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setGifGenerating(false);
    }
  }

  function handleOpenAssetUpload() {
    assetUploadInputRef.current?.click();
  }

  async function handleAssetUploadChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;

    setUploadingAssets(true);
    try {
      const uploadedIds: string[] = [];

      for (const file of files) {
        const uploaded = await uploadAsset(file, activeWorkspaceId, "upload", activeThreadId ?? undefined);
        if (!uploaded) {
          throw new Error(`Upload failed for ${file.name}`);
        }
        uploadedIds.push(uploaded.id);
      }

      const refreshedAssets = await listAssets(activeWorkspaceId, contentScope);
      const uploadedBatch = refreshedAssets.filter((asset) => uploadedIds.includes(asset.id));
      setLiveAssets((prev) => {
        const remaining = prev.filter((asset) => !uploadedIds.includes(asset.id));
        return [...uploadedBatch.reverse(), ...remaining];
      });
    } catch (error) {
      console.error(error);
      window.alert(error instanceof Error ? error.message : "Asset upload failed.");
    } finally {
      setUploadingAssets(false);
    }
  }

  const selectedAssets = liveAssets.filter((asset) => selected.has(asset.id));
  const selectedKakaoEligibleAssets = useMemo(
    () => liveAssets.filter(
      (asset) => selected.has(asset.id) && asset.type !== "gif" && asset.url && !asset.url.includes("placeholder")
    ),
    // liveAssets and selected are both stable refs that only change on real data updates
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [liveAssets, selected],
  );

  useEffect(() => {
    const nextSignature = selectedAssets
      .map((asset) => asset.id)
      .sort()
      .join("|");
    if (lastSelectionSignatureRef.current === nextSignature) return;
    lastSelectionSignatureRef.current = nextSignature;
  }, [selectedAssets]);

  useEffect(() => {
    setKakaoBatchDspName(buildKakaoDisclosure(kakaoBatchGacha));
  }, [kakaoBatchGacha]);

  useEffect(() => {
    if (!kakaoBatchOpen) return;

    loadSpoqaFonts().catch(() => {});

    const previewAsset =
      selectedKakaoEligibleAssets[kakaoBatchPreviewAssetIndex] ?? selectedKakaoEligibleAssets[0];
    if (!previewAsset) {
      setKakaoBatchValidationErrors(["Select at least one image asset."]);
      setKakaoBatchMainCopyWidthPx(0);
      setKakaoBatchPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return;
    }

    let cancelled = false;
    let nextPreviewUrl: string | null = null;

    async function buildPreview() {
      const validation = await validateKakaoBizboardInputs({
        thumbnailUrl: previewAsset.url,
        appIconUrl: kakaoBatchAppIconUrl,
        subtitle: kakaoBatchAppDownloadCopy,
        mainCopy: kakaoBatchMainCopy,
        gacha: kakaoBatchGacha,
      });
      if (cancelled) return;

      setKakaoBatchValidationErrors(validation.errors);
      setKakaoBatchMainCopyWidthPx(validation.mainCopyWidthPx);

      if (validation.errors.length > 0) {
        setKakaoBatchPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return null;
        });
        return;
      }

      const blob = await composeKakaoBizboard({
        thumbnailUrl: previewAsset.url,
        appIconUrl: kakaoBatchAppIconUrl,
        subtitle: kakaoBatchAppDownloadCopy,
        mainCopy: kakaoBatchMainCopy,
        gacha: kakaoBatchGacha,
      });
      if (cancelled) return;

      nextPreviewUrl = URL.createObjectURL(blob);
      setKakaoBatchPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return nextPreviewUrl;
      });
    }

    buildPreview().catch((err) => {
      if (cancelled) return;
      setKakaoBatchValidationErrors([
        err instanceof Error ? err.message : "Kakao preview generation failed.",
      ]);
      setKakaoBatchPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    });

    return () => {
      cancelled = true;
      if (nextPreviewUrl) URL.revokeObjectURL(nextPreviewUrl);
    };
  }, [
    kakaoBatchOpen,
    kakaoBatchAppIconUrl,
    kakaoBatchMainCopy,
    kakaoBatchAppDownloadCopy,
    kakaoBatchDspName,
    kakaoBatchGacha,
    kakaoBatchPreviewAssetIndex,
    selectedKakaoEligibleAssets,
  ]);

  function handleOpenKakaoBatch() {
    if (selectedKakaoEligibleAssets.length === 0) return;
    setKakaoBatchAppDownloadCopy((prev) => prev.trim() || KAKAO_DEFAULT_SUBTITLE);
    setKakaoBatchMainCopy((prev) => prev.trim() || KAKAO_DEFAULT_MAIN_COPY);
    setKakaoBatchPreviewAssetIndex(0);
    setKakaoBatchOpen(true);
  }

  function handleKakaoBatchIconChange(file: File | null) {
    setKakaoBatchAppIconUrl((prev) => {
      if (prev?.startsWith("blob:")) {
        URL.revokeObjectURL(prev);
      }
      return file ? URL.createObjectURL(file) : null;
    });
  }

  async function handleGenerateKakaoSelected() {
    if (selectedKakaoEligibleAssets.length === 0) return;
    setKakaoBatchSubmitting(true);
    try {
      const queuedJobs: JobSummary[] = [];

      for (const asset of selectedKakaoEligibleAssets) {
        const blob = await composeKakaoBizboard({
          thumbnailUrl: asset.url,
          appIconUrl: kakaoBatchAppIconUrl,
          subtitle: kakaoBatchAppDownloadCopy,
          mainCopy: kakaoBatchMainCopy,
          gacha: kakaoBatchGacha,
        });
        const safeName = (asset.title || "kakao_asset")
          .replace(/\.[^.]+$/, "")
          .replace(/[^a-zA-Z0-9_-]+/g, "_");
        const file = new File([blob], `${safeName}_kakao_bizboard_1029x258.png`, {
          type: "image/png",
        });
        const uploaded = await uploadAsset(file, activeWorkspaceId, "upload", activeThreadId ?? undefined);
        if (!uploaded) {
          throw new Error(`Bizboard upload failed for ${asset.title}`);
        }

        const response = await createKakaoBizboardJob({
          workspaceId: activeWorkspaceId,
          cleanedAssetId: asset.id,
          composedAssetId: uploaded.id,
          mainCopy: kakaoBatchMainCopy,
          appDownloadCopy: kakaoBatchAppDownloadCopy,
          dspName: kakaoBatchDspName,
          gacha: kakaoBatchGacha,
          threadId: activeThreadId ?? undefined,
        });

        const job: JobSummary = {
          id: response.job_id,
          jobId: response.job_id,
          title: response.title,
          toolId: response.tool_id,
          status: response.status,
          progress: response.progress,
          eta: response.status === "completed" ? "Completed" : "Running...",
          lineageKey: response.lineage_key,
        };
        queuedJobs.push(job);
      }

      if (queuedJobs.length === 0) {
        throw new Error("No Kakao Bizboard jobs were created.");
      }

      setLiveJobs((prev) => [...queuedJobs.reverse(), ...prev]);
      queuedJobs.forEach((job) => onJobCreated(job));
      setKakaoBatchOpen(false);
    } catch (e) {
      console.error(e);
    } finally {
      setKakaoBatchSubmitting(false);
    }
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

  function readVideoMeta(asset: AssetSummary): {
    mode: string | null;
    aspectRatio: string | null;
    durationSeconds: string | null;
    includeAudio: boolean | null;
  } {
    const video = (asset.analysis?.video ?? null) as Record<string, unknown> | null;
    return {
      mode: typeof video?.mode === "string" ? video.mode : null,
      aspectRatio: typeof video?.aspect_ratio === "string" ? video.aspect_ratio : null,
      durationSeconds:
        typeof video?.duration_seconds === "number" || typeof video?.duration_seconds === "string"
          ? String(video.duration_seconds)
          : null,
      includeAudio: typeof video?.include_audio === "boolean" ? video.include_audio : null,
    };
  }

  function matchesMediaFilter(asset: AssetSummary) {
    if (mediaFilter === "all") return true;
    return asset.type === mediaFilter;
  }

  function matchesVideoFilters(asset: AssetSummary) {
    if (mediaFilter !== "video") return true;
    if (asset.type !== "video") return false;
    const meta = readVideoMeta(asset);
    if (videoModeFilter !== "all" && meta.mode !== videoModeFilter) return false;
    if (videoAspectFilter !== "all" && meta.aspectRatio !== videoAspectFilter) return false;
    if (videoDurationFilter !== "all" && meta.durationSeconds !== videoDurationFilter) return false;
    if (videoAudioFilter === "audio_on" && meta.includeAudio !== true) return false;
    if (videoAudioFilter === "audio_off" && meta.includeAudio !== false) return false;
    return true;
  }

  const generatedAssets = liveAssets.filter((a) => Boolean(a.jobId));
  const uploadedAssets = liveAssets.filter((a) => !a.jobId);
  const filteredGeneratedBase = generatedAssets.filter((asset) => matchesMediaFilter(asset) && matchesVideoFilters(asset));
  const filteredUploadsBase = uploadedAssets.filter((asset) => matchesMediaFilter(asset) && matchesVideoFilters(asset));
  const q = search.trim().toLowerCase();
  const filteredGenerated = q
    ? filteredGeneratedBase.filter((a) =>
        [a.title, a.theme, a.model, a.provider, a.type]
          .filter(Boolean).some((v) => String(v).toLowerCase().includes(q))
      )
    : filteredGeneratedBase;
  const filteredUploads = q
    ? filteredUploadsBase.filter((a) =>
        [a.title, a.model, a.provider, a.type]
          .filter(Boolean).some((v) => String(v).toLowerCase().includes(q))
      )
    : filteredUploadsBase;
  const dragSelectableAssets = useMemo(
    () => (tab === "generated" ? filteredGenerated : filteredUploads),
    [filteredGenerated, filteredUploads, tab]
  );
  const activeTabAssets = tab === "generated" ? generatedAssets : uploadedAssets;
  const mediaFilterCounts = {
    all: activeTabAssets.length,
    image: activeTabAssets.filter((asset) => asset.type === "image").length,
    video: activeTabAssets.filter((asset) => asset.type === "video").length,
    gif: activeTabAssets.filter((asset) => asset.type === "gif").length,
    report: activeTabAssets.filter((asset) => asset.type === "report").length,
    playable: activeTabAssets.filter((asset) => asset.type === "playable").length,
  };
  const activeVideoAssets = activeTabAssets.filter((asset) => asset.type === "video");
  const videoModeOptions = Array.from(
    new Set(activeVideoAssets.map((asset) => readVideoMeta(asset).mode).filter(Boolean) as string[])
  );
  const videoAspectOptions = Array.from(
    new Set(activeVideoAssets.map((asset) => readVideoMeta(asset).aspectRatio).filter(Boolean) as string[])
  );
  const videoDurationOptions = Array.from(
    new Set(activeVideoAssets.map((asset) => readVideoMeta(asset).durationSeconds).filter(Boolean) as string[])
  ).sort((left, right) => Number(left) - Number(right));

  useEffect(() => {
    return () => {
      if (suppressSelectClickTimerRef.current !== null) {
        window.clearTimeout(suppressSelectClickTimerRef.current);
      }
    };
  }, []);

  function clearSuppressSelectClick() {
    if (suppressSelectClickTimerRef.current !== null) {
      window.clearTimeout(suppressSelectClickTimerRef.current);
    }
    suppressSelectClickTimerRef.current = window.setTimeout(() => {
      suppressSelectClickRef.current = false;
      suppressSelectClickTimerRef.current = null;
    }, 0);
  }

  function isInteractiveSelectionTarget(target: EventTarget | null) {
    if (!(target instanceof HTMLElement)) return false;
    return Boolean(target.closest("button, input, textarea, select, a, label, video"));
  }

  function getSelectionHits(nextRect: { left: number; top: number; width: number; height: number }) {
    const container = dragSelectContainerRef.current;
    if (!container) return [];
    const selectionRight = nextRect.left + nextRect.width;
    const selectionBottom = nextRect.top + nextRect.height;
    return Array.from(container.querySelectorAll<HTMLElement>("[data-library-asset-id]"))
      .filter((element) => {
        const id = element.dataset.libraryAssetId;
        if (!id) return false;
        const elementRect = element.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        const left = elementRect.left - containerRect.left;
        const top = elementRect.top - containerRect.top;
        const right = left + elementRect.width;
        const bottom = top + elementRect.height;
        return !(
          right < nextRect.left ||
          left > selectionRight ||
          bottom < nextRect.top ||
          top > selectionBottom
        );
      })
      .map((element) => element.dataset.libraryAssetId!)
      .filter(Boolean);
  }

  function handleDragSelectPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!selectMode || isInteractiveSelectionTarget(event.target)) return;
    const container = dragSelectContainerRef.current;
    if (!container) return;
    const bounds = container.getBoundingClientRect();
    dragSelectOriginRef.current = {
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    };
    dragSelectPointerIdRef.current = event.pointerId;
    dragSelectMovedRef.current = false;
    setDragSelectRect(null);
    container.setPointerCapture(event.pointerId);
  }

  function handleDragSelectPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const container = dragSelectContainerRef.current;
    const origin = dragSelectOriginRef.current;
    if (!selectMode || !container || !origin || dragSelectPointerIdRef.current !== event.pointerId) return;
    const bounds = container.getBoundingClientRect();
    const currentX = Math.max(0, Math.min(event.clientX - bounds.left, bounds.width));
    const currentY = Math.max(0, Math.min(event.clientY - bounds.top, bounds.height));
    const left = Math.min(origin.x, currentX);
    const top = Math.min(origin.y, currentY);
    const width = Math.abs(currentX - origin.x);
    const height = Math.abs(currentY - origin.y);
    if (width < 4 && height < 4) return;
    dragSelectMovedRef.current = true;
    const nextRect = { left, top, width, height };
    setDragSelectRect(nextRect);
    const hits = getSelectionHits(nextRect);
    setSelected(new Set(hits));
  }

  function handleDragSelectPointerEnd(event: React.PointerEvent<HTMLDivElement>) {
    const container = dragSelectContainerRef.current;
    if (container && dragSelectPointerIdRef.current === event.pointerId) {
      try {
        container.releasePointerCapture(event.pointerId);
      } catch {}
    }
    const interactiveTarget = isInteractiveSelectionTarget(event.target);
    const assetTarget = event.target instanceof HTMLElement
      ? event.target.closest<HTMLElement>("[data-library-asset-id]")
      : null;
    dragSelectOriginRef.current = null;
    dragSelectPointerIdRef.current = null;
    setDragSelectRect(null);
    if (!dragSelectMovedRef.current && selectMode && !interactiveTarget && assetTarget?.dataset.libraryAssetId) {
      toggleSelect(assetTarget.dataset.libraryAssetId);
    } else if (dragSelectMovedRef.current) {
      suppressSelectClickRef.current = true;
      clearSuppressSelectClick();
    }
    dragSelectMovedRef.current = false;
  }

  function handleLibraryTileClick(asset: AssetSummary, hasReal: boolean) {
    if (selectMode) {
      if (suppressSelectClickRef.current) return;
      toggleSelect(asset.id);
      return;
    }
    if (!hasReal) return;
    setZoomedAsset(asset);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="-mx-2 mb-4 border-b border-border bg-background px-2 pb-4 pt-1">
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

        <div className="mb-5 flex items-center gap-6 border-b border-border">
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
              <button
                type="button"
                onClick={handleOpenAssetUpload}
                disabled={uploadingAssets}
                className="flex items-center gap-1.5 rounded-xl bg-foreground px-3 py-1.5 text-sm font-medium text-background hover:opacity-80 disabled:opacity-50"
              >
                {uploadingAssets ? <Loader2 className="size-4 animate-spin" /> : <span>↑</span>}
                Upload
              </button>
              <input
                ref={assetUploadInputRef}
                type="file"
                multiple
                accept="image/*,video/*,.psd,.ai,.pdf"
                className="hidden"
                onChange={handleAssetUploadChange}
              />
            </div>
          )}
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          {([
            { id: "all", label: "All" },
            { id: "image", label: "Images" },
            { id: "video", label: "Videos" },
            { id: "gif", label: "GIFs" },
            { id: "playable", label: "Playables" },
            { id: "report", label: "Reports" },
          ] as const).map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setMediaFilter(option.id)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                mediaFilter === option.id
                  ? "border-foreground bg-foreground text-background"
                  : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {option.label}
              <span className="ml-1.5 text-[10px] opacity-75">
                {mediaFilterCounts[option.id]}
              </span>
            </button>
          ))}
        </div>

        {mediaFilter === "video" ? (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {[{ id: "all", label: "All modes" }, ...videoModeOptions.map((value) => ({ id: value, label: value.replaceAll("_", " ") }))].map((option) => (
              <button
                key={`video-mode-${option.id}`}
                type="button"
                onClick={() => setVideoModeFilter(option.id)}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                  videoModeFilter === option.id
                    ? "border-foreground bg-foreground text-background"
                    : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {option.label}
              </button>
            ))}

            {[{ id: "all", label: "All ratios" }, ...videoAspectOptions.map((value) => ({ id: value, label: value }))].map((option) => (
              <button
                key={`video-aspect-${option.id}`}
                type="button"
                onClick={() => setVideoAspectFilter(option.id)}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                  videoAspectFilter === option.id
                    ? "border-foreground bg-foreground text-background"
                    : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {option.label}
              </button>
            ))}

            {[{ id: "all", label: "All durations" }, ...videoDurationOptions.map((value) => ({ id: value, label: `${value}s` }))].map((option) => (
              <button
                key={`video-duration-${option.id}`}
                type="button"
                onClick={() => setVideoDurationFilter(option.id)}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                  videoDurationFilter === option.id
                    ? "border-foreground bg-foreground text-background"
                    : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {option.label}
              </button>
            ))}

            {[
              { id: "all", label: "All audio" },
              { id: "audio_on", label: "Audio on" },
              { id: "audio_off", label: "Silent" },
            ].map((option) => (
              <button
                key={`video-audio-${option.id}`}
                type="button"
                onClick={() => setVideoAudioFilter(option.id as "all" | "audio_on" | "audio_off")}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                  videoAudioFilter === option.id
                    ? "border-foreground bg-foreground text-background"
                    : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : null}

        {selected.size > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 shadow-sm">
            <span className="text-sm font-medium">{selected.size} selected</span>
            <button
              onClick={handleDownload}
              disabled={downloading}
              className="flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background hover:opacity-80 disabled:opacity-50"
            >
              {downloading ? <Loader2 className="size-3 animate-spin" /> : <Download className="size-3" />}
              {selected.size === 1
                ? `Download ${getAssetFileExtension(
                    liveAssets.find((asset) => selected.has(asset.id)) ?? {
                      url: "",
                      title: "",
                      type: "image",
                    }
                  ).toUpperCase()}`
                : "Download"}
            </button>
            <button
              onClick={handleGenerateGif}
              disabled={gifGenerating || Array.from(selected).length === 0}
              className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50"
            >
              {gifGenerating ? <Loader2 className="size-3 animate-spin" /> : <Sparkles className="size-3" />}
              Generate GIF
            </button>
            <button
              onClick={handleOpenKakaoBatch}
              disabled={kakaoBatchSubmitting || selectedKakaoEligibleAssets.length === 0}
              className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50"
            >
              {kakaoBatchSubmitting ? <Loader2 className="size-3 animate-spin" /> : <Sparkles className="size-3" />}
              {selectedKakaoEligibleAssets.length <= 1 ? "Generate Kakao" : `Generate Kakao (${selectedKakaoEligibleAssets.length})`}
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

        {tab === "generated" && filteredGenerated.length > 0 && (
          <div className="flex items-center justify-between gap-3">
            <button
              onClick={() => toggleAll(filteredGenerated)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              {filteredGenerated.every((a) => selected.has(a.id))
                ? <CheckSquare className="size-4 text-accent" />
                : <Square className="size-4" />}
              Select all
            </button>
            <button
              type="button"
              onClick={() => {
                if (selectMode) {
                  setSelectMode(false);
                  setSelected(new Set());
                  return;
                }
                setSelectMode(true);
              }}
              className={cn(
                "rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors",
                selectMode
                  ? "border-foreground bg-foreground text-background"
                  : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {selectMode ? "Unselect" : "Select"}
            </button>
          </div>
        )}

        {tab === "assets" && filteredUploads.length > 0 && (
          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={() => {
                if (selectMode) {
                  setSelectMode(false);
                  setSelected(new Set());
                  return;
                }
                setSelectMode(true);
              }}
              className={cn(
                "rounded-xl border px-3 py-1.5 text-sm font-medium transition-colors",
                selectMode
                  ? "border-foreground bg-foreground text-background"
                  : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {selectMode ? "Unselect" : "Select"}
            </button>
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
        )}
      </div>

      {zoomedAsset && (
        <ZoomModal asset={zoomedAsset} onClose={() => setZoomedAsset(null)} />
      )}

      {kakaoBatchOpen && (
        <KakaoBatchModal
          assets={selectedKakaoEligibleAssets}
          submitting={kakaoBatchSubmitting}
          appIconUrl={kakaoBatchAppIconUrl}
          mainCopy={kakaoBatchMainCopy}
          appDownloadCopy={kakaoBatchAppDownloadCopy}
          gacha={kakaoBatchGacha}
          previewUrl={kakaoBatchPreviewUrl}
          validationErrors={kakaoBatchValidationErrors}
          mainCopyWidthPx={kakaoBatchMainCopyWidthPx}
          onClose={() => setKakaoBatchOpen(false)}
          onSubmit={handleGenerateKakaoSelected}
          onAppIconChange={handleKakaoBatchIconChange}
          setGacha={setKakaoBatchGacha}
          onSubtitleChange={setKakaoBatchAppDownloadCopy}
          onMainCopyChange={setKakaoBatchMainCopy}
          onApplyChanges={() => {}}
          previewBusy={false}
          previewAssetIndex={kakaoBatchPreviewAssetIndex}
          onPreviewAssetChange={setKakaoBatchPreviewAssetIndex}
        />
      )}

      <div
        className="min-h-0 flex-1 overflow-y-auto pr-1"
      >
      <div
        ref={dragSelectContainerRef}
        className="relative"
        onPointerDown={handleDragSelectPointerDown}
        onPointerMove={handleDragSelectPointerMove}
        onPointerUp={handleDragSelectPointerEnd}
        onPointerCancel={handleDragSelectPointerEnd}
      >
        {dragSelectRect && selectMode && (
          <div
            className="pointer-events-none absolute z-20 rounded-md border border-accent bg-accent/10"
            style={{
              left: dragSelectRect.left,
              top: dragSelectRect.top,
              width: dragSelectRect.width,
              height: dragSelectRect.height,
            }}
          />
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
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {filteredGenerated.map((asset) => {
                const hasReal = Boolean(asset.url && !asset.url.includes("placeholder"));
                const isSel = selected.has(asset.id);
                return (
                  <div
                    key={asset.id}
                    data-library-asset-id={asset.id}
                    className={cn("group flex cursor-pointer flex-col gap-1.5", selectMode && "select-none")}
                    onClick={() => handleLibraryTileClick(asset, hasReal)}
                  >
                    <div
                      className={cn(
                        "relative aspect-square overflow-hidden border-2 bg-[#07111F] transition-all",
                        isSel ? "border-accent shadow-[0_0_0_1px_hsl(var(--accent)/0.3)]" : "border-transparent hover:border-border"
                      )}
                    >
                      {hasReal ? (
                        asset.type === "video" ? (
                          <video
                            src={asset.url}
                            className="h-full w-full object-cover"
                            muted
                            playsInline
                            preload="metadata"
                            draggable={false}
                          />
                        ) : (
                          <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" draggable={false} />
                        )
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <ImageIcon className="size-6 text-white/20" />
                        </div>
                      )}
                      {/* Checkbox */}
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleSelect(asset.id);
                        }}
                        className={cn(
                          "absolute right-1.5 top-1.5 z-20 flex size-5 items-center justify-center rounded-full border-2 transition-all",
                          isSel
                            ? "border-accent bg-accent text-white"
                            : "border-white/50 bg-black/30 opacity-0 group-hover:opacity-100"
                        )}
                      >
                        {isSel && <Check className="size-3" />}
                      </button>
                      {hasReal && !selectMode && (
                        <div className="pointer-events-none absolute inset-0 hidden items-center justify-center bg-black/20 group-hover:flex">
                          <div className="rounded-full bg-black/60 p-1.5 backdrop-blur-sm">
                            <Maximize2 className="size-4 text-white" />
                          </div>
                        </div>
                      )}
                      {/* Size + format label — always visible */}
                      <div className="absolute bottom-1.5 left-1.5 rounded-md bg-black/75 px-1.5 py-0.5 backdrop-blur-sm">
                        <span className="text-[8px] font-semibold text-white">
                          {asset.width && asset.height
                            ? `${asset.width}×${asset.height} · ${getAssetFileExtension(asset).toUpperCase()}`
                            : getAssetFileExtension(asset).toUpperCase()}
                        </span>
                      </div>
                    </div>
                    <p className="truncate text-[11px] font-medium">{asset.title}</p>
                    <p className="text-[10px] text-muted-foreground">{asset.model}</p>
                  </div>
                );
              })}
          </div>
        )
      )}

      {/* ── Assets tab ── */}
      {tab === "assets" && (
        <div>
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
                      data-library-asset-id={asset.id}
                      className={cn(
                        "grid cursor-pointer grid-cols-[32px_minmax(0,1fr)_160px_100px_80px] items-center gap-4 px-4 py-3 transition-colors hover:bg-muted/30",
                        isSel && "bg-soft-accent/40"
                      )}
                      onClick={(event) => {
                        if (isInteractiveSelectionTarget(event.target)) return;
                        handleLibraryTileClick(asset, hasReal);
                      }}
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
                        <button
                          type="button"
                          onClick={() => handleLibraryTileClick(asset, hasReal)}
                          className="size-9 shrink-0 overflow-hidden border border-border bg-muted"
                        >
                          {hasReal ? (
                            asset.type === "video" ? (
                              <video
                                src={asset.url}
                                className="h-full w-full object-cover"
                                muted
                                playsInline
                                preload="metadata"
                                draggable={false}
                              />
                            ) : (
                              <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" draggable={false} />
                            )
                          ) : (
                            <div className="flex h-full w-full items-center justify-center">
                              <ImageIcon className="size-4 text-muted-foreground" />
                            </div>
                          )}
                        </button>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{asset.title}</p>
                          <p className="text-[11px] text-muted-foreground">
                            {asset.width && asset.height ? `${asset.width}×${asset.height} · ` : ""}
                            {getAssetFileExtension(asset).toUpperCase()}
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
                  <div
                    key={asset.id}
                    data-library-asset-id={asset.id}
                    className={cn("group flex cursor-pointer flex-col gap-1.5", selectMode && "select-none")}
                    onClick={() => handleLibraryTileClick(asset, hasReal)}
                  >
                    <div
                      className={cn(
                        "relative aspect-square overflow-hidden border-2 bg-muted transition-all",
                        isSel ? "border-accent" : "border-transparent hover:border-border"
                      )}
                    >
                      {hasReal ? (
                        asset.type === "video" ? (
                          <video
                            src={asset.url}
                            className="h-full w-full object-cover"
                            muted
                            playsInline
                            preload="metadata"
                            draggable={false}
                          />
                        ) : (
                          <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" draggable={false} />
                        )
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <ImageIcon className="size-6 text-muted-foreground/40" />
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleSelect(asset.id);
                        }}
                        className={cn(
                          "absolute right-1.5 top-1.5 z-20 flex size-5 items-center justify-center rounded-full border-2 transition-all",
                          isSel
                            ? "border-accent bg-accent text-white"
                            : "border-white/50 bg-black/30 opacity-0 group-hover:opacity-100"
                        )}
                      >
                        {isSel && <Check className="size-3" />}
                      </button>
                      {hasReal && !selectMode && (
                        <div className="pointer-events-none absolute inset-0 hidden items-center justify-center bg-black/20 group-hover:flex">
                          <div className="rounded-full bg-black/60 p-1.5 backdrop-blur-sm">
                            <Maximize2 className="size-4 text-white" />
                          </div>
                        </div>
                      )}
                      {/* Size + format label */}
                      <div className="absolute bottom-1.5 left-1.5 rounded-md bg-black/75 px-1.5 py-0.5 backdrop-blur-sm">
                        <span className="text-[8px] font-semibold text-white">
                          {asset.width && asset.height
                            ? `${asset.width}×${asset.height} · ${getAssetFileExtension(asset).toUpperCase()}`
                            : getAssetFileExtension(asset).toUpperCase()}
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
      </div>
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
  currentUser, contentScope, activeWorkspaceId, activeThreadId, onThreadSelect,
  onJobCreated, onMobileMenuOpen, onThreadSelectFromHome,
}: WorkspaceProps) {
  const isChat = activeView === "Workspace";
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
          const result = await uploadAsset(att.file, activeWorkspaceId, "reference", activeThreadId ?? undefined);
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
        const newAssets = await listAssets(activeWorkspaceId, contentScope);
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

  if (activeView === "Image" || activeView === "Video") {
    return (
      <CreateWorkbenchView
        surface={activeView === "Video" ? "video" : "image"}
        liveAssets={liveAssets}
        setLiveAssets={setLiveAssets}
        liveJobs={liveJobs}
        setLiveJobs={setLiveJobs}
        liveThreads={liveThreads}
        setLiveThreads={setLiveThreads}
        currentUser={currentUser}
        contentScope={contentScope}
        activeWorkspaceId={activeWorkspaceId}
        activeThreadId={activeThreadId}
        onThreadSelect={onThreadSelect}
        onJobCreated={onJobCreated}
      />
    );
  }

  if (activeView === "VideoProduction") {
    return (
      <VideoProductionView
        liveAssets={liveAssets}
        setLiveAssets={setLiveAssets}
        currentUser={currentUser}
        contentScope={contentScope}
        activeWorkspaceId={activeWorkspaceId}
        onMobileMenuOpen={onMobileMenuOpen}
      />
    );
  }

  return (
    <main className="flex h-screen min-h-0 flex-1 min-w-0 grid-cols-1 overflow-hidden">
      {/* ── Left panel ── */}
      <section className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-r bg-background">
        {/* Header — only in active chat or non-chat views */}
        {(!isChat || hasConversation) && (
          <AppHeader
            variant="header"
            title={isChat ? "Thread" : activeView}
            onMobileMenuOpen={onMobileMenuOpen}
            docsHref="/docs/studio"
          />
        )}

        {/* Non-chat views */}
        {!isChat && (
          <div
            className={cn(
              "flex-1 min-h-0 px-7 py-6 max-[860px]:px-4",
              activeView === "Library" || activeView === "Settings"
                ? "flex flex-col overflow-hidden"
                : "overflow-auto"
            )}
          >
            {activeView === "Home" && (
              <HomeView
                liveAssets={liveAssets}
                liveJobs={liveJobs}
                liveThreads={liveThreads}
                onViewChange={onViewChange}
                onThreadSelect={onThreadSelectFromHome}
                onOpenCreateSurface={(surface) => onViewChange(surface === "video" ? "Video" : "Image")}
              />
            )}
            {activeView === "Analyze" && <ComingSoon activeView={activeView} />}
            {activeView === "Usage" && <UsageView />}
            {(activeView === "Library" || activeView === "Settings") && (
              <LibraryView
                activeView={activeView}
                liveAssets={liveAssets}
                setLiveAssets={setLiveAssets}
                setLiveJobs={setLiveJobs}
                onJobCreated={onJobCreated}
                activeWorkspaceId={activeWorkspaceId}
                contentScope={contentScope}
                activeThreadId={activeThreadId}
              />
            )}
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
