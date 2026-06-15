"use client";

import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  ArrowUp,
  Check,
  CheckSquare,
  ChevronDown,
  Download,
  EyeOff,
  ImageIcon,
  Loader2,
  Maximize2,
  Plus,
  PanelRight,
  Pencil,
  RotateCcw,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import type { AssetRole, AssetSummary, CreativeThreadSummary, InceptUser, JobSummary } from "@incept/shared";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { addTextToImage, cancelJob, createImageGenerationJob, deleteAssets, deleteThread, downloadAssetFile, downloadAssetsZip, editImage, generateGifFromAsset, listAssets, listThreads, outpaintImage, removeBackground, renameThread, uploadAsset } from "@/lib/incept-api";
import { InpaintingCanvas } from "@/components/incept/InpaintingCanvas";
import { DocsButton, FeedbackButton } from "@/components/incept/FeedbackButton";
import { KakaoFlow } from "@/components/incept/KakaoFlow";

// ─── Types ────────────────────────────────────────────────────────────────────

type CreativeMode = "image" | "endcard";
type OutputFormat = "static" | "gif";
type ProviderId = "openai" | "gemini";
type ActiveChip = "model" | "sizes" | "format" | "variants" | null;
type CreateFlow = "resize" | "theme_create" | "kakao";
type DraftAssetPreview = { id: string; url: string; name: string; file: File; role: AssetRole };
type AssetBucketState = Partial<Record<AssetRole, DraftAssetPreview[]>>;
type ThemeCreateMode = "style_modify" | "style_transfer" | "asset_text_replace";

// ─── Constants ────────────────────────────────────────────────────────────────

// ─── Size definitions ─────────────────────────────────────────────────────────

// Sizes grouped by family for the Resize task UI (endcard included as 4th group)
const RESIZE_SIZE_GROUPS = [
  { label: "Banner",           sizes: ["320x50", "728x90", "1200x222", "640x100"] },
  { label: "Landscape",        sizes: ["1200x628", "1200x600"] },
  { label: "Portrait / Square",sizes: ["320x480", "300x250", "720x720"] },
  { label: "Endcard",          sizes: ["360x640", "480x480", "640x360"] },
] as const;

const RESIZE_SIZE_ORDER = RESIZE_SIZE_GROUPS.flatMap((group) => group.sizes);

const ENDCARD_SIZE_SET = new Set(["360x640", "480x480", "640x360"]);

const IMAGE_SIZES = [
  "1200x628", "320x480", "300x250",
  "720x720", "1200x600", "360x640", "480x480", "640x360",
];

// GIF supported for medium + endcard sizes
const GIF_ALLOWED_SIZES = new Set([
  "300x250",                       // medium
  "320x480",                       // portrait
  "360x640", "480x480", "640x360", // endcard
]);

const ENDCARD_SIZES = [
  { id: "360x640", label: "Portrait 9:16" },
  { id: "640x360", label: "Landscape 16:9" },
  { id: "480x480", label: "Square 1:1" },
];
const ENDCARD_SIZE_IDS = ENDCARD_SIZES.map((s) => s.id);
const DEFAULT_IMAGE_SIZES = ["1200x628", "300x250", "320x480"];

// ─── Create flow tabs ─────────────────────────────────────────────────────────

const CREATE_FLOW_TABS: Array<{ id: CreateFlow; label: string; blurb: string }> = [
  { id: "resize",       label: "Resize",       blurb: "Adapt one image to multiple ad sizes. Background and style stay identical." },
  { id: "theme_create", label: "Theme Create", blurb: "Modify a source creative using one of three Gemini image workflows." },
  { id: "kakao",        label: "Kakao",        blurb: "Batch-generate Kakao Bizboard banners (1029×258) from your ad creatives." },
];

const THEME_CREATE_MODES: Array<{ id: ThemeCreateMode; label: string; blurb: string }> = [
  { id: "style_modify", label: "Style Modify", blurb: "Keep the exact layout of one source image and transform its artistic style." },
  { id: "style_transfer", label: "Style Transfer", blurb: "Use Image 1 for content and Image 2 only for visual style DNA." },
  { id: "asset_text_replace", label: "Asset & Text Replace", blurb: "Replace a logo, replace one element, and rewrite one text string." },
];

const THEME_CREATE_POSITION_OPTIONS = [
  { value: "top-left", label: "Top Left" },
  { value: "top-right", label: "Top Right" },
  { value: "center", label: "Center" },
  { value: "bottom-left", label: "Bottom Left" },
  { value: "bottom-right", label: "Bottom Right" },
] as const;

// Flat list of supported models — provider shown as sub-text prefix
const ALL_MODELS: Array<{
  id: string;
  provider: ProviderId;
  short: string;
  sub: string;
}> = [
  { id: "gemini-3.1-flash-image", provider: "gemini", short: "Gemini 3.1 Flash", sub: "Google · Fastest" },
  { id: "gpt-image-2",            provider: "openai", short: "GPT Image 2",      sub: "OpenAI · Latest" },
];

// ─── Props ────────────────────────────────────────────────────────────────────

export interface CreateImageViewProps {
  liveAssets: AssetSummary[];
  setLiveAssets: Dispatch<SetStateAction<AssetSummary[]>>;
  liveJobs: JobSummary[];
  setLiveJobs: Dispatch<SetStateAction<JobSummary[]>>;
  liveThreads: CreativeThreadSummary[];
  setLiveThreads: Dispatch<SetStateAction<CreativeThreadSummary[]>>;
  currentUser: InceptUser;
  activeWorkspaceId: string;
  activeWorkspaceTitle?: string;
  activeThreadId?: string | null;
  onThreadSelect?: (id: string | null) => void;
  onJobCreated: (job: JobSummary) => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDateGroup(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString("en-US", { month: "long", day: "numeric" });
}

function formatThreadMode(mode: CreateFlow): string {
  if (mode === "resize") return "Resize";
  if (mode === "kakao") return "Kakao";
  if (mode === "theme_create") return "Theme Create";
  return "Free Create";
}

// ─── Dropdown panel (shared wrapper) ─────────────────────────────────────────
// Each chip wraps its button + this panel in a <div className="relative">
// The panel floats above the chip via absolute positioning.

function DropdownPanel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "absolute bottom-[calc(100%+6px)] z-50 min-w-[180px] rounded-xl border border-border bg-card py-1 shadow-xl",
        className
      )}
    >
      {children}
    </div>
  );
}

function DropdownLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-3 pb-1 pt-1.5 text-[11px] text-muted-foreground">
      {children}
    </p>
  );
}

function DropdownItem({
  label,
  sub,
  selected,
  onClick,
}: {
  label: string;
  sub?: string;
  selected?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/60"
    >
      <span className="flex-1">
        <span className={cn("block", selected && "font-medium")}>{label}</span>
        {sub && (
          <span className="block text-[11px] text-muted-foreground">{sub}</span>
        )}
      </span>
      {selected && <Check className="size-3.5 shrink-0 text-foreground" />}
    </button>
  );
}

function DropdownDivider() {
  return <div className="my-1 h-px bg-border" />;
}

function AssetBucketUploader({
  title,
  hint,
  role,
  files,
  required = false,
  onAdd,
  onRemove,
}: {
  title: string;
  hint: string;
  role: AssetRole;
  files: DraftAssetPreview[];
  required?: boolean;
  onAdd: (role: AssetRole, files: FileList | null) => void;
  onRemove: (role: AssetRole, id: string) => void;
}) {
  const inputId = `asset-${role}-${title.replace(/\s+/g, "-").toLowerCase()}`;

  return (
    <div className="rounded-xl border border-border bg-background/60 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-foreground">{title}</p>
            {required && <Badge variant="secondary" className="text-[10px]">Required</Badge>}
          </div>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">{hint}</p>
        </div>
        <label
          htmlFor={inputId}
          className="shrink-0 cursor-pointer rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-foreground/25 hover:text-foreground"
        >
          Add
        </label>
        <input
          id={inputId}
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          onChange={(e) => {
            onAdd(role, e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {files.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {files.map((item) => (
            <div
              key={item.id}
              className="group relative size-12 overflow-hidden rounded-lg border border-border bg-[#07111F]"
            >
              <img src={item.url} alt={item.name} className="h-full w-full object-cover" />
              <button
                type="button"
                onClick={() => onRemove(role, item.id)}
                className="absolute inset-0 hidden items-center justify-center bg-black/60 group-hover:flex"
              >
                <X className="size-3 text-white" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-[11px] text-muted-foreground">No assets added yet.</p>
      )}
    </div>
  );
}

function ThemeAssetInput({
  title,
  hint,
  file,
  onPick,
  onClear,
  required,
}: {
  title: string;
  hint: string;
  file: DraftAssetPreview | null;
  onPick: (file: File | null) => void;
  onClear: () => void;
  required?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="rounded-xl border border-border bg-background/60 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-foreground">{title}</p>
            {required && <Badge variant="secondary" className="text-[10px]">Required</Badge>}
          </div>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">{hint}</p>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="shrink-0 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-foreground/25 hover:text-foreground"
        >
          {file ? "Replace" : "Upload"}
        </button>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="sr-only"
        onChange={(e) => {
          onPick(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />

      {file ? (
        <div className="mt-3 flex items-center gap-3 rounded-lg border border-border bg-card/80 p-2">
          <div className="size-12 shrink-0 overflow-hidden rounded-lg border border-border bg-[#07111F]">
            <img src={file.url} alt={file.name} className="h-full w-full object-cover" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-foreground">{file.name}</p>
          </div>
          <button
            type="button"
            onClick={onClear}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ) : (
        <p className="mt-3 text-[11px] text-muted-foreground">No file chosen.</p>
      )}
    </div>
  );
}

// ─── Chip button ──────────────────────────────────────────────────────────────

function ChipButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium transition-all",
        active
          ? "border-foreground/30 bg-muted text-foreground"
          : "border-border bg-transparent text-muted-foreground hover:border-foreground/30 hover:text-foreground"
      )}
    >
      {label}
      <ChevronDown className="size-3 opacity-50" />
    </button>
  );
}

// ─── Image zoom modal ────────────────────────────────────────────────────────

function ZoomModal({
  asset,
  onClose,
  onRegenerate,
}: {
  asset: AssetSummary;
  onClose: () => void;
  onRegenerate?: (asset: AssetSummary) => void;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const fmt = asset.type === "gif" ? "GIF" : "PNG";
  const label = asset.width && asset.height
    ? `${asset.width}×${asset.height} · ${fmt}`
    : fmt;
  const canRegenerate = Boolean(onRegenerate && (asset.parentAssetId || asset.rootAssetId) && asset.width && asset.height);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[92vh] max-w-[92vw] flex-col overflow-hidden rounded-2xl bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold text-foreground">{label}</p>
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{asset.title}</p>
          </div>
          <div className="flex items-center gap-2">
            {canRegenerate && (
              <button
                type="button"
                onClick={() => onRegenerate?.(asset)}
                className="rounded-lg border border-border px-2.5 py-1.5 text-[11px] font-semibold text-foreground hover:bg-muted"
              >
                Regenerate This Size
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>
        {/* Image */}
        <div className="min-h-0 flex-1 overflow-auto">
          <img
            src={asset.url}
            alt={asset.title}
            className="block max-h-[80vh] max-w-[90vw] object-contain"
          />
        </div>
      </div>
    </div>
  );
}

// ─── Generation card — 3-column image grid + prompt + action buttons ──────────

function GenerationCard({
  assets,
  title,
  promptText,
  isGenerating,
  selectedAssetIds,
  onToggleSelect,
  onSetWorking,
  onRegenerate,
  onRegenerateAsset,
  onHide,
  onZoom,
}: {
  assets: AssetSummary[];
  title: string;
  promptText?: string;
  isGenerating?: boolean;
  selectedAssetIds?: Set<string>;
  onToggleSelect?: (assetId: string) => void;
  onSetWorking?: (asset: AssetSummary) => void;
  onRegenerate?: () => void;
  onRegenerateAsset?: (asset: AssetSummary) => void;
  onHide?: () => void;
  onZoom?: (asset: AssetSummary) => void;
}) {
  if (isGenerating) {
    return (
      <div className="col-span-3 flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-accent/40 bg-soft-accent/20">
        <div className="relative size-9">
          <div className="absolute inset-0 animate-ping rounded-full bg-accent/20" />
          <div className="relative grid size-9 place-items-center rounded-full bg-soft-accent text-accent">
            <Sparkles className="size-4" />
          </div>
        </div>
        <p className="max-w-xs text-center text-sm text-muted-foreground line-clamp-2">{title}</p>
      </div>
    );
  }

  const realAssets = assets.filter((a) => a.url && !a.url.includes("placeholder"));
  if (realAssets.length === 0) return null;
  const firstWorkingAsset = realAssets[0];
  function fmtLabel(a: AssetSummary) {
    const size = a.width && a.height ? `${a.width}×${a.height}` : "";
    const fmt  = a.type === "gif" ? "GIF" : "PNG";
    return size ? `${size} · ${fmt}` : fmt;
  }

  return (
    <div className="group col-span-3 flex gap-2">
      {/* ── Images in 3-column grid ── */}
      <div className="min-w-0 flex-1">
        <div className="grid grid-cols-3 gap-3">
          {realAssets.map((a) => {
            const r = a.width && a.height ? a.width / a.height : 16 / 9;
            const canRegenerateAsset = Boolean(onRegenerateAsset && (a.parentAssetId || a.rootAssetId) && a.width && a.height);
            const selected = selectedAssetIds?.has(a.id) ?? false;
            return (
              <div key={a.id} className="group/img relative">
                {onToggleSelect && (
                  <button
                    type="button"
                    onClick={() => onToggleSelect(a.id)}
                    className={cn(
                      "absolute right-2 top-2 z-30 flex size-5 items-center justify-center rounded-full border-2 transition-all",
                      selected
                        ? "border-accent bg-accent text-white"
                        : "border-white/70 bg-black/35 text-white hover:border-white"
                    )}
                    title={selected ? "Deselect" : "Select"}
                  >
                    {selected ? <Check className="size-3" /> : <span className="size-2 rounded-full bg-white/90" />}
                  </button>
                )}

                {/* Image tile — click to zoom */}
                <div
                  className={cn(
                    "relative cursor-zoom-in overflow-hidden border bg-[#07111F]",
                    selected
                      ? "border-accent shadow-[0_0_0_1px_hsl(var(--accent)/0.35)]"
                      : "border-border"
                  )}
                  style={{ aspectRatio: Math.min(Math.max(r, 0.3), 4) }}
                  onClick={() => onZoom?.(a)}
                >
                  <img src={a.url} alt={a.title} className="h-full w-full object-cover transition-transform group-hover/img:scale-[1.02]" />

                  {/* Use as working image — first image only */}
                  {a.id === firstWorkingAsset.id && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onSetWorking?.(a); }}
                      className="absolute left-2 top-2 hidden rounded-lg bg-accent/90 px-2 py-1 text-[10px] font-semibold text-white backdrop-blur-sm hover:bg-accent group-hover:flex"
                    >
                      Use
                    </button>
                  )}

                  {canRegenerateAsset && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onRegenerateAsset(a); }}
                      className="absolute right-9 top-2 z-10 hidden rounded-lg border border-white/20 bg-black/60 p-1.5 text-white backdrop-blur-sm hover:bg-black/75 group-hover/img:flex"
                      title={`Regenerate ${fmtLabel(a)}`}
                    >
                      <RotateCcw className="size-3.5" />
                    </button>
                  )}

                  {/* Zoom hint on hover */}
                  <div className="absolute inset-0 hidden items-center justify-center bg-black/20 group-hover/img:flex">
                    <div className="rounded-full bg-black/60 p-1.5 backdrop-blur-sm">
                      <Maximize2 className="size-4 text-white" />
                    </div>
                  </div>
                </div>

                {/* Size + format label */}
                <p className="mt-1 text-[10px] font-semibold text-foreground/80">
                  {fmtLabel(a)}
                </p>
              </div>
            );
          })}
        </div>

        {/* Prompt / history text */}
        <div className="mt-2 space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/80">
            {title}
          </p>
          <p className="text-xs leading-5 text-muted-foreground line-clamp-3">
            {promptText?.trim() || title}
          </p>
        </div>
      </div>

      {/* ── Action buttons (right column, appear on hover) ── */}
      <div className="flex shrink-0 flex-col items-center gap-1.5 pt-1 opacity-0 transition-opacity group-hover:opacity-100">
        {onRegenerate && (
          <button
            type="button"
            title="Regenerate"
            onClick={onRegenerate}
            className="rounded-lg border border-border bg-card p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <RotateCcw className="size-4" />
          </button>
        )}
        {onHide && (
          <button
            type="button"
            title="Hide"
            onClick={onHide}
            className="rounded-lg border border-border bg-card p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <EyeOff className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function CreateImageView({
  liveAssets,
  setLiveAssets,
  liveJobs,
  setLiveJobs,
  liveThreads,
  setLiveThreads,
  currentUser,
  activeWorkspaceId,
  activeWorkspaceTitle,
  activeThreadId,
  onThreadSelect,
  onJobCreated,
}: CreateImageViewProps) {
  // ── Form state ──
  const [mode, setMode] = useState<CreativeMode>("image");
  const [createFlow, setCreateFlow] = useState<CreateFlow>("resize");
  const [prompt, setPrompt] = useState("");
  const [modelId, setModelId] = useState("gemini-3.1-flash-image");
  const [selectedSizes, setSelectedSizes] = useState<string[]>(DEFAULT_IMAGE_SIZES);
  const [format, setFormat] = useState<OutputFormat>("static");

  // ── Additional GIF output (Resize mode add-on) ──
  const [includeGif, setIncludeGif] = useState(false);

  // ── Resize source image ──
  const [resizeSourceAsset, setResizeSourceAsset] = useState<{ id: string | null; url: string; name: string; file?: File } | null>(null);
  const resizeFileRef = useRef<HTMLInputElement>(null);
  const [showDevPromptOverride, setShowDevPromptOverride] = useState(false);
  const [resizePromptOverrides, setResizePromptOverrides] = useState<Record<string, string>>({});
  const [resizeNegativePromptOverride, setResizeNegativePromptOverride] = useState("");
  const [variants, setVariants] = useState<1 | 2>(1);
  const [activeChip, setActiveChip] = useState<ActiveChip>(null);

  // Derive provider from selected model
  const activeModel = ALL_MODELS.find((m) => m.id === modelId) ?? ALL_MODELS[0];
  const provider = activeModel.provider;

  // ── Theme Create ──
  const [themeCreateMode, setThemeCreateMode] = useState<ThemeCreateMode>("style_modify");
  const [themeCreateAssets, setThemeCreateAssets] = useState<AssetBucketState>({});
  const [themeCreateStyleName, setThemeCreateStyleName] = useState("");
  const [themeCreateStyleDetails, setThemeCreateStyleDetails] = useState("");
  const [themeCreateLogoPosition, setThemeCreateLogoPosition] = useState("top-left");
  const [themeCreateElementPosition, setThemeCreateElementPosition] = useState("top-right");
  const [themeCreateOldText, setThemeCreateOldText] = useState("");
  const [themeCreateNewText, setThemeCreateNewText] = useState("");
  const [themeCreateFontStyle, setThemeCreateFontStyle] = useState("");

  // ── Generation state ──
  const [generating, setGenerating] = useState(false);
  const [uploadingSource, setUploadingSource] = useState(false);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [lastPrompt, setLastPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  // ── Session ──

  // ── Working image ("current working object", drives edit vs generate) ──
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [selectedAssetIds, setSelectedAssetIds] = useState<Set<string>>(new Set());
  const [downloadPrefix, setDownloadPrefix] = useState("incept");
  const [downloading, setDownloading] = useState(false);
  const [hiddenJobIds, setHiddenJobIds] = useState<Set<string>>(new Set());
  const [zoomedAsset, setZoomedAsset] = useState<AssetSummary | null>(null);
  const [renamingThreadId, setRenamingThreadId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(activeThreadId ?? null);
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const [startingNewSession, setStartingNewSession] = useState(false);
  const [previewState, setPreviewState] = useState<{ assets: AssetSummary[]; index: number } | null>(null);
  const sessionMenuRef = useRef<HTMLDivElement>(null);
  const [workingImage, setWorkingImage] = useState<{
    assetId: string | null; // null while uploading
    url: string;
    label: string;
    width?: number;
    height?: number;
  } | null>(null);

  // Active operation panel inside the pinned bar
  const [activeOp, setActiveOp] = useState<"outpaint" | "text" | null>(null);
  const [outpaintDir, setOutpaintDir] = useState<"left" | "right" | "top" | "bottom" | "all">("all");
  const [outpaintRatio, setOutpaintRatio] = useState(0.3);
  const [textInput, setTextInput] = useState("");
  const [textPosition, setTextPosition] = useState<"top" | "center" | "bottom">("bottom");

  // Upload a file and auto-set it as the working image
  async function setWorkingImageFromFile(file: File) {
    const blobUrl = URL.createObjectURL(file);
    setWorkingImage({ assetId: null, url: blobUrl, label: file.name });
    try {
      const uploaded = await uploadAsset(file, activeWorkspaceId, "working");
      if (uploaded) {
        setWorkingImage((prev) =>
          prev ? { ...prev, assetId: uploaded.id } : null
        );
      }
    } catch {
      /* keep blob URL, submit will handle upload */
    }
  }

  function setWorkingImageFromAsset(asset: AssetSummary) {
    setWorkingImage({
      assetId: asset.id,
      url: asset.url,
      label: asset.theme ?? asset.title ?? "Generated",
      width: asset.width,
      height: asset.height,
    });
    if (asset.threadId) {
      setSelectedThreadId(asset.threadId);
      onThreadSelect?.(asset.threadId);
    }
    setActiveOp(null);
  }

  // ── Operation handlers (require workingImage.assetId) ──
  function requireAssetId(): string | null {
    const id = workingImage?.assetId ?? null;
    if (!id) setError("Image is still uploading — please wait a moment.");
    return id;
  }

  async function handleOutpaint(
    overrideDirection?: "left" | "right" | "top" | "bottom" | "all",
    overrideRatio?: number,
  ) {
    const id = requireAssetId();
    if (!id) return;
    const direction = overrideDirection ?? outpaintDir;
    const ratio = overrideRatio ?? outpaintRatio;
    setGenerating(true); setError(null);
    try {
      const res = await outpaintImage({
        workspaceId: activeWorkspaceId, assetId: id,
        direction, ratio,
        threadId: selectedThreadId ?? undefined,
        outputSizes: selectedSizes,
      });
      const job = { id: res.job_id, jobId: res.job_id, title: res.title, toolId: res.tool_id, status: res.status, progress: res.progress, eta: "Running…", lineageKey: res.lineage_key };
      setCurrentJobId(res.job_id);
      if (res.thread_id) {
        setSelectedThreadId(res.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(res.thread_id);
      }
      setLiveJobs((p) => [job, ...p]);
      onJobCreated(job);
      setActiveOp(null);
    } catch (err) {
      setGenerating(false);
      setError(`Outpaint failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  async function handleRemoveBG() {
    const id = requireAssetId();
    if (!id) return;
    setGenerating(true); setError(null);
    try {
      const res = await removeBackground({
        workspaceId: activeWorkspaceId,
        assetId: id,
        threadId: selectedThreadId ?? undefined,
        outputSizes: selectedSizes,
      });
      const job = { id: res.job_id, jobId: res.job_id, title: res.title, toolId: res.tool_id, status: res.status, progress: res.progress, eta: "Running…", lineageKey: res.lineage_key };
      setCurrentJobId(res.job_id);
      if (res.thread_id) {
        setSelectedThreadId(res.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(res.thread_id);
      }
      setLiveJobs((p) => [job, ...p]);
      onJobCreated(job);
    } catch (err) {
      setGenerating(false);
      setError(`Remove BG failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  async function handleAddText(overrideText?: string) {
    const baseText = (overrideText ?? textInput).trim();
    if (!baseText) return;
    const id = requireAssetId();
    if (!id) return;
    setGenerating(true); setError(null);
    try {
      const res = await addTextToImage({
        workspaceId: activeWorkspaceId,
        assetId: id,
        text: baseText,
        position: textPosition,
        threadId: selectedThreadId ?? undefined,
        outputSizes: selectedSizes,
      });
      const job = { id: res.job_id, jobId: res.job_id, title: res.title, toolId: res.tool_id, status: res.status, progress: res.progress, eta: "Running…", lineageKey: res.lineage_key };
      setCurrentJobId(res.job_id);
      if (res.thread_id) {
        setSelectedThreadId(res.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(res.thread_id);
      }
      setLiveJobs((p) => [job, ...p]);
      onJobCreated(job);
      setTextInput(""); setActiveOp(null);
    } catch (err) {
      setGenerating(false);
      setError(`Add text failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  // ── Inpainting canvas ──
  const [editTarget, setEditTarget] = useState<{
    assetId: string;
    url: string;
    width: number;
    height: number;
    theme?: string;
  } | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);

  // ── Right assets panel ──
  // Only real assets that belong to the current workspace (project)
  const downloadableAssets = liveAssets.filter(
    (a) =>
      a.jobId &&
      a.url &&
      !a.url.includes("placeholder") &&
      a.workspaceId === activeWorkspaceId
  );
  const currentProjectSessions = [...liveThreads]
    .filter((thread) => thread.workspaceId === activeWorkspaceId)
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());

  const allSelected =
    downloadableAssets.length > 0 &&
    downloadableAssets.every((a) => selectedAssetIds.has(a.id));
  const selectedAssets = downloadableAssets.filter((asset) => selectedAssetIds.has(asset.id));
  const selectedGifEligibleAssets = selectedAssets.filter((asset) => asset.type !== "gif");

  function toggleAsset(id: string) {
    setSelectedAssetIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (allSelected) {
      setSelectedAssetIds(new Set());
    } else {
      setSelectedAssetIds(new Set(downloadableAssets.map((a) => a.id)));
    }
  }

  async function handleDownload() {
    const ids = Array.from(selectedAssetIds);
    if (ids.length === 0) return;
    setDownloading(true);
    try {
      if (ids.length === 1) {
        const asset = downloadableAssets.find((item) => item.id === ids[0]);
        if (!asset) throw new Error("Selected asset not found.");
        await downloadAssetFile(asset);
      } else {
        await downloadAssetsZip(ids, downloadPrefix || "incept");
      }
    } catch (err) {
      console.error("Download failed:", err);
    } finally {
      setDownloading(false);
    }
  }

  async function handleGenerateGifSelected() {
    if (selectedGifEligibleAssets.length === 0) return;
    setGenerating(true);
    setError(null);
    let lastResponse: Awaited<ReturnType<typeof generateGifFromAsset>> | null = null;
    try {
      for (const asset of selectedGifEligibleAssets) {
        const response = await generateGifFromAsset({
          workspaceId: activeWorkspaceId,
          assetId: asset.id,
          threadId: asset.threadId ?? selectedThreadId ?? undefined,
        });
        lastResponse = response;
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
      if (lastResponse?.thread_id) {
        setSelectedThreadId(lastResponse.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(lastResponse.thread_id);
      }
      if (lastResponse) {
        setCurrentJobId(lastResponse.job_id);
        setLastPrompt("Generate GIF");
      } else {
        setGenerating(false);
      }
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function triggerGifJob(assetId: string, threadId?: string | null) {
    setGenerating(true);
    setError(null);
    setCurrentJobId(null);
    setLastPrompt("Generate GIF");
    try {
      const response = await generateGifFromAsset({
        workspaceId: activeWorkspaceId,
        assetId,
        threadId: threadId ?? selectedThreadId ?? undefined,
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
      setCurrentJobId(response.job_id);
      if (response.thread_id) {
        setSelectedThreadId(response.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(response.thread_id);
      }
      setLiveJobs((prev) => [job, ...prev]);
      onJobCreated(job);
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleGenerateGifFromResizeSource() {
    if (!resizeSourceAsset) return;
    let sourceId = resizeSourceAsset.id;
    if (!sourceId && resizeSourceAsset.file) {
      setUploadingSource(true);
      try {
        const uploaded = await uploadAsset(resizeSourceAsset.file, activeWorkspaceId, "upload");
        if (uploaded) {
          sourceId = uploaded.id;
          setResizeSourceAsset((prev) => (prev ? { ...prev, id: uploaded.id } : null));
        }
      } finally {
        setUploadingSource(false);
      }
    }
    if (!sourceId) {
      setError("Upload a source image first.");
      return;
    }
    await triggerGifJob(sourceId, selectedThreadId);
  }

  async function handleRegenerate(entry: (typeof jobEntries)[number]) {
    const resizeAssets = entry.assets.filter((asset) => asset.parentAssetId || asset.rootAssetId);
    const sourceAssetId = resizeAssets[0]?.parentAssetId ?? resizeAssets[0]?.rootAssetId;
    const outputSizes = Array.from(
      new Set(
        resizeAssets
          .map((asset) =>
            typeof asset.analysis?.resize_requested_size === "string" && asset.analysis.resize_requested_size.trim()
              ? asset.analysis.resize_requested_size.trim()
              : asset.width && asset.height
                ? `${asset.width}x${asset.height}`
                : ""
          )
          .filter((size) => size.length > 0)
      )
    );
    if (!sourceAssetId || outputSizes.length === 0) {
      setError("This run cannot be regenerated because the resize source is missing.");
      return;
    }

    setGenerating(true);
    setError(null);
    setCurrentJobId(null);
    setLastPrompt(`Resize to ${outputSizes.join(", ")}`);

    try {
      const response = await createImageGenerationJob({
        workspace_id: activeWorkspaceId,
        prompt:
          entry.promptText?.trim() ||
          `Resize the source image to the requested ad sizes.`,
        provider,
        model: modelId,
        variants: 1,
        aspect_ratio: "multi-size",
        created_by: currentUser.id,
        source_asset_ids: [sourceAssetId],
        reference_asset_ids: [sourceAssetId],
        theme: `Resize ${outputSizes.join(" ")}`,
        output_sizes: outputSizes,
        output_format: "image",
        preserve_layout: true,
        use_reference_style: true,
        client_asset_ids: [],
        thread_id: entry.threadId || selectedThreadId || undefined,
        generation_mode: "resize",
        include_gif: false,
        resize_prompt_overrides: Object.fromEntries(
          outputSizes
            .map((size) => [size, resizePromptOverrides[size]?.trim() ?? ""])
            .filter(([, value]) => value.length > 0)
        ),
        resize_negative_prompt_override: resizeNegativePromptOverride.trim() || undefined,
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
      setCurrentJobId(response.job_id);
      if (response.thread_id) {
        setSelectedThreadId(response.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(response.thread_id);
      }
      setLiveJobs((prev) => [job, ...prev]);
      onJobCreated(job);
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleRegenerateAsset(asset: AssetSummary) {
    const sourceAssetId = asset.parentAssetId ?? asset.rootAssetId;
    const targetSize =
      typeof asset.analysis?.resize_requested_size === "string" && asset.analysis.resize_requested_size.trim()
        ? asset.analysis.resize_requested_size.trim()
        : asset.width && asset.height
          ? `${asset.width}x${asset.height}`
          : "";
    if (!sourceAssetId || !targetSize) {
      setError("This image cannot be regenerated because its resize source or size is missing.");
      return;
    }

    setGenerating(true);
    setError(null);
    setCurrentJobId(null);
    setLastPrompt(`Resize to ${targetSize}`);
    setZoomedAsset(null);
    setPreviewState(null);

    try {
      const sourcePrompt =
        typeof asset.analysis?.source_prompt === "string" && asset.analysis.source_prompt.trim()
          ? asset.analysis.source_prompt.trim()
          : "Resize the source image to the requested ad size.";
      const response = await createImageGenerationJob({
        workspace_id: activeWorkspaceId,
        prompt: sourcePrompt,
        provider,
        model: modelId,
        variants: 1,
        aspect_ratio: "multi-size",
        created_by: currentUser.id,
        source_asset_ids: [sourceAssetId],
        reference_asset_ids: [sourceAssetId],
        theme: `Resize ${targetSize}`,
        output_sizes: [targetSize],
        output_format: "image",
        preserve_layout: true,
        use_reference_style: true,
        client_asset_ids: [],
        thread_id: asset.threadId || selectedThreadId || undefined,
        generation_mode: "resize",
        include_gif: false,
        resize_prompt_overrides: resizePromptOverrides[targetSize]?.trim()
          ? { [targetSize]: resizePromptOverrides[targetSize].trim() }
          : undefined,
        resize_negative_prompt_override: resizeNegativePromptOverride.trim() || undefined,
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
      setCurrentJobId(response.job_id);
      if (response.thread_id) {
        setSelectedThreadId(response.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(response.thread_id);
      }
      setLiveJobs((prev) => [job, ...prev]);
      onJobCreated(job);
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDeleteSelected() {
    const ids = Array.from(selectedAssetIds);
    if (!ids.length) return;
    if (!confirm(`Delete ${ids.length} asset(s)?`)) return;
    try {
      await deleteAssets(ids);
      const [assets, threads] = await Promise.all([
        listAssets(activeWorkspaceId),
        listThreads(activeWorkspaceId),
      ]);
      setLiveAssets(assets);
      setLiveThreads(threads);
      setSelectedAssetIds(new Set());
    } catch (err) {
      console.error("Delete failed:", err);
    }
  }

  // ── Session selection (can be driven externally from the global sidebar) ──
  useEffect(() => {
    if (activeThreadId) {
      setSelectedThreadId(activeThreadId);
      setStartingNewSession(false);
      return;
    }
    if (!startingNewSession) {
      setSelectedThreadId(currentProjectSessions[0]?.id ?? null);
    }
  }, [activeThreadId, activeWorkspaceId, liveThreads, startingNewSession]);

  useEffect(() => {
    setSelectedAssetIds(new Set());
  }, [selectedThreadId, activeWorkspaceId]);

  useEffect(() => {
    setStartingNewSession(false);
  }, [activeWorkspaceId]);

  // ── Ref for click-outside detection ──
  const barRef = useRef<HTMLDivElement>(null);

  // Reset sizes on mode change
  useEffect(() => {
    setSelectedSizes(mode === "endcard" ? ENDCARD_SIZE_IDS : DEFAULT_IMAGE_SIZES);
  }, [mode]);

  // Watch liveJobs for completion
  useEffect(() => {
    if (!currentJobId || !generating) return;
    const job = liveJobs.find((j) => (j.jobId ?? j.id) === currentJobId);
    if (!job) return;
    if (job.status === "completed") {
      Promise.all([listAssets(activeWorkspaceId), listThreads(activeWorkspaceId)])
        .then(([a, threads]) => {
          setLiveAssets(a);
          setLiveThreads(threads);
        })
        .catch(() => {});
      setGenerating(false);
      setCurrentJobId(null);
    }
    if (job.status === "failed") {
      setGenerating(false);
      setCurrentJobId(null);
      setError(job.message ?? "Generation failed. Check your API credentials and try again.");
    }
  }, [liveJobs, currentJobId, generating, activeWorkspaceId, setLiveAssets, setLiveThreads]);

  // Close chip panel on outside click
  useEffect(() => {
    if (!activeChip) return;
    function handler(e: MouseEvent) {
      if (barRef.current && !barRef.current.contains(e.target as Node)) {
        setActiveChip(null);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [activeChip]);

  // Theme Create always generates at 1200x628
  useEffect(() => {
    if (createFlow === "theme_create") {
      setSelectedSizes(["1200x628"]);
    }
  }, [createFlow]);

  useEffect(() => {
    if (createFlow === "resize" || createFlow === "kakao") {
      setModelId("gemini-3.1-flash-image");
      setActiveChip((prev) => (prev === "model" ? null : prev));
    }
  }, [createFlow]);

  useEffect(() => {
    if (!sessionMenuOpen) return;
    function handler(e: MouseEvent) {
      if (sessionMenuRef.current && !sessionMenuRef.current.contains(e.target as Node)) {
        setSessionMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [sessionMenuOpen]);

  function toggleChip(chip: ActiveChip) {
    setActiveChip((prev) => (prev === chip ? null : chip));
  }

  async function handleCancel() {
    const fallbackRunningJob = liveJobs.find((j) => j.status === "running" || j.status === "pending");
    const cancelId = currentJobId ?? fallbackRunningJob?.jobId ?? fallbackRunningJob?.id;
    if (!cancelId) return;
    await cancelJob(cancelId).catch(() => {});
    setGenerating(false);
    setCurrentJobId(null);
    setError("Generation cancelled.");
  }

  async function handleEditSubmit(maskDataUrl: string, editPrompt: string) {
    if (!editTarget) return;
    setEditSubmitting(true);
    try {
      const response = await editImage({
        workspaceId: activeWorkspaceId,
        assetId: editTarget.assetId,
        maskDataUrl,
        prompt: editPrompt,
        theme: editTarget.theme,
        threadId: selectedThreadId ?? undefined,
        outputSizes: selectedSizes,
      });
      const job = {
        id: response.job_id,
        jobId: response.job_id,
        title: response.title,
        toolId: response.tool_id,
        status: response.status,
        progress: response.progress,
        eta: "Running…",
        lineageKey: response.lineage_key,
      };
      if (response.thread_id) {
        setSelectedThreadId(response.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(response.thread_id);
      }
      setLiveJobs((prev) => [job, ...prev]);
      onJobCreated(job);
      setEditTarget(null);
    } catch (err) {
      setError(`Edit failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setEditSubmitting(false);
    }
  }

  function setSingleThemeAsset(role: AssetRole, file: File | null) {
    setThemeCreateAssets((prev) => {
      const existing = prev[role] ?? [];
      existing.forEach((item) => URL.revokeObjectURL(item.url));
      const next = { ...prev };
      if (!file) {
        delete next[role];
        return next;
      }
      next[role] = [{
        id: `${role}_${Math.random().toString(36).slice(2)}`,
        url: URL.createObjectURL(file),
        name: file.name,
        file,
        role,
      }];
      return next;
    });
  }

  function hasRoleAssets(bucket: AssetBucketState, role: AssetRole) {
    return (bucket[role] ?? []).length > 0;
  }

  async function uploadRoleBuckets(bucket: AssetBucketState) {
    const uploaded: Partial<Record<AssetRole, string[]>> = {};
    for (const role of Object.keys(bucket) as AssetRole[]) {
      const drafts = bucket[role] ?? [];
      for (const draft of drafts) {
        const asset = await uploadAsset(draft.file, activeWorkspaceId, role);
        if (!asset) continue;
        uploaded[role] = [...(uploaded[role] ?? []), asset.id];
      }
    }
    return uploaded;
  }

  function flattenUploaded(uploaded: Partial<Record<AssetRole, string[]>>, roles: AssetRole[]) {
    return roles.flatMap((role) => uploaded[role] ?? []);
  }

  // ── Generate / Edit router ──
  async function handleGenerate() {
    if (generating) return;

    // Effective sizes (for resize the checkbox grid already has endcard included if selected)
    const sizes = selectedSizes.length ? selectedSizes : DEFAULT_IMAGE_SIZES;

    setGenerating(true);
    setError(null);
    setCurrentJobId(null);
    setLastPrompt(
      createFlow === "resize"
        ? `Resize to ${sizes.join(", ")}`
        : createFlow === "theme_create"
        ? `Theme Create · ${THEME_CREATE_MODES.find((item) => item.id === themeCreateMode)?.label ?? "Theme Create"}`
        : prompt.trim() || createFlow.replace("_", " ")
    );

    try {
      let response: Awaited<ReturnType<typeof createImageGenerationJob>>;

      // ── RESIZE TASK ────────────────────────────────────────────────────────
      if (createFlow === "resize") {
        if (!resizeSourceAsset) {
          setGenerating(false);
          setError("Upload a source image to resize.");
          return;
        }
        // Upload source if not yet uploaded
        let sourceId = resizeSourceAsset.id;
        if (!sourceId && resizeSourceAsset.file) {
          setUploadingSource(true);
          const up = await uploadAsset(resizeSourceAsset.file, activeWorkspaceId, "upload");
          setUploadingSource(false);
          if (up) {
            sourceId = up.id;
            setResizeSourceAsset((prev) => prev ? { ...prev, id: up.id } : null);
          }
        }
        response = await createImageGenerationJob({
          workspace_id: activeWorkspaceId,
          prompt: `Resize the source image to the requested ad sizes. ${prompt.trim() ? `Additional note: ${prompt.trim()}` : ""}`.trim(),
          provider,
          model: modelId,
          variants: 1,
          aspect_ratio: "multi-size",
          created_by: currentUser.id,
          source_asset_ids: sourceId ? [sourceId] : [],
          reference_asset_ids: sourceId ? [sourceId] : [],
          theme: `Resize ${sizes.join(" ")}`,
          output_sizes: sizes,
          output_format: "image",
          preserve_layout: true,
          use_reference_style: true,
          client_asset_ids: [],
          thread_id: selectedThreadId ?? undefined,
          generation_mode: "resize",
          include_gif: includeGif,
          resize_prompt_overrides: Object.fromEntries(
            sizes
              .map((size) => [size, resizePromptOverrides[size]?.trim() ?? ""])
              .filter(([, value]) => value.length > 0)
          ),
          resize_negative_prompt_override: resizeNegativePromptOverride.trim() || undefined,
        });
      }

      else {
        const uploaded = await uploadRoleBuckets(themeCreateAssets);
        const sourceIds = flattenUploaded(uploaded, ["upload"]);
        const referenceIds = flattenUploaded(uploaded, ["reference_ad", "client_logo", "brand_element"]);

        if (!sourceIds.length) {
          setGenerating(false);
          setError("Theme Create requires a source image.");
          return;
        }

        if (themeCreateMode === "style_modify") {
          if (!prompt.trim()) {
            setGenerating(false);
            setError("Style Modify requires a prompt.");
            return;
          }
        }

        if (themeCreateMode === "style_transfer" && !referenceIds[0]) {
          setGenerating(false);
          setError("Style Transfer requires a style reference image.");
          return;
        }

        if (themeCreateMode === "asset_text_replace") {
          if (referenceIds.length < 2) {
            setGenerating(false);
            setError("Asset & Text Replace requires both a new logo image and a new element image.");
            return;
          }
          if (!themeCreateOldText.trim() || !themeCreateNewText.trim() || !themeCreateFontStyle.trim()) {
            setGenerating(false);
            setError("Asset & Text Replace requires old text, new text, and font style.");
            return;
          }
        }

        const modeLabel = THEME_CREATE_MODES.find((item) => item.id === themeCreateMode)?.label ?? "Theme Create";
        response = await createImageGenerationJob({
          workspace_id: activeWorkspaceId,
          prompt: `Theme Create · ${modeLabel}`,
          provider,
          model: modelId,
          variants,
          aspect_ratio: "multi-size",
          created_by: currentUser.id,
          source_asset_ids: [sourceIds[0]],
          theme: modeLabel,
          output_sizes: ["1200x628"],
          output_format: "image",
          reference_asset_ids: referenceIds,
          preserve_layout: false,
          use_reference_style: false,
          client_asset_ids: [],
          thread_id: selectedThreadId ?? undefined,
          generation_mode: "theme_create",
          theme_create_mode: themeCreateMode,
          theme_create_style_name: themeCreateMode === "style_modify" ? prompt.trim() : themeCreateStyleName.trim() || undefined,
          theme_create_style_details: themeCreateMode === "style_modify" ? prompt.trim() : themeCreateStyleDetails.trim() || undefined,
          theme_create_logo_position: themeCreateLogoPosition,
          theme_create_element_position: themeCreateElementPosition,
          theme_create_old_text: themeCreateOldText.trim() || undefined,
          theme_create_new_text: themeCreateNewText.trim() || undefined,
          theme_create_font_style: themeCreateFontStyle.trim() || undefined,
        });
      }

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
      setCurrentJobId(response.job_id);
      if (response.thread_id) {
        setSelectedThreadId(response.thread_id);
        setStartingNewSession(false);
        onThreadSelect?.(response.thread_id);
      }
      setLiveJobs((prev) => [job, ...prev]);
      onJobCreated(job);
      setPrompt("");

      if (response.status === "completed") {
        const [newAssets, newThreads] = await Promise.all([
          listAssets(activeWorkspaceId),
          listThreads(activeWorkspaceId),
        ]);
        setLiveAssets(newAssets);
        setLiveThreads(newThreads);
        setGenerating(false);
        setCurrentJobId(null);
      }
    } catch (err) {
      setGenerating(false);
      setUploadingSource(false);
      const msg = err instanceof Error ? err.message : String(err);
      // "Failed to fetch" = server not running; HTTP errors = something else
      if (msg.toLowerCase().includes("failed to fetch") || msg.toLowerCase().includes("networkerror")) {
        setError("Cannot reach the API. Check your connection or contact support.");
      } else {
        setError(msg);
      }
    }
  }

  // ── History data ──
  const generatedAssets = liveAssets.filter((a) => a.jobId);
  const liveJobMap = new Map(liveJobs.map((job) => [job.jobId ?? job.id, job]));
  const jobEntries = Array.from(
    generatedAssets.reduce((map, asset) => {
      const key = asset.jobId!;
      const current = map.get(key) ?? [];
      current.push(asset);
      map.set(key, current);
      return map;
    }, new Map<string, AssetSummary[]>())
  )
    .map(([jobId, assets]) => {
      return {
        id: jobId,
        threadId: assets[0]?.threadId ?? "",
        createdAt: assets[0]?.createdAt ?? new Date().toISOString(),
        assets: assets.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()),
        title: liveJobMap.get(jobId)?.title ?? assets[0]?.theme ?? "Generation",
        promptText: (() => {
          const requestPrompt = assets[0]?.analysis?.request_prompt;
          if (typeof requestPrompt === "string" && requestPrompt.trim()) {
            return requestPrompt.trim();
          }
          const sourcePrompt = assets[0]?.analysis?.source_prompt;
          if (typeof sourcePrompt === "string" && sourcePrompt.trim()) {
            return sourcePrompt.trim();
          }
          return undefined;
        })(),
      };
    })
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  const threadJobsMap = new Map<string, typeof jobEntries>();
  for (const entry of jobEntries) {
    if (!entry.threadId) continue;
    const current = threadJobsMap.get(entry.threadId) ?? [];
    current.push(entry);
    threadJobsMap.set(entry.threadId, current);
  }
  const threadAssetMap = new Map<string, AssetSummary[]>();
  for (const asset of generatedAssets) {
    if (!asset.threadId) continue;
    const current = threadAssetMap.get(asset.threadId) ?? [];
    current.push(asset);
    threadAssetMap.set(asset.threadId, current);
  }
  for (const [threadId, assets] of threadAssetMap.entries()) {
    threadAssetMap.set(
      threadId,
      assets.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    );
  }
  const threadMap = new Map(currentProjectSessions.map((thread) => [thread.id, thread]));
  const sortedThreads = currentProjectSessions;
  const threadDateGroups: Array<{ date: string; threads: CreativeThreadSummary[] }> = [];

  // ── Chip labels ──
  const selectedThread = selectedThreadId ? threadMap.get(selectedThreadId) ?? null : null;
  const selectedThreadAssets = selectedThreadId ? threadAssetMap.get(selectedThreadId) ?? [] : [];
  const selectedThreadJobs = selectedThreadId ? threadJobsMap.get(selectedThreadId) ?? [] : [];
  const sessionTitle = startingNewSession
    ? "New Session"
    : selectedThread?.title ?? currentProjectSessions[0]?.title ?? "New Session";
  // When starting a new project: show empty canvas
  // When a thread is selected: show only that thread's jobs
  // Otherwise (no thread, not new): show all workspace jobs
  const projectJobEntries = startingNewSession
    ? []
    : selectedThreadId
    ? jobEntries.filter((e) => e.threadId === selectedThreadId)
    : jobEntries;

  const sizesLabel =
    selectedSizes.length === 0 ? "Sizes"
    : selectedSizes.length === 1 ? selectedSizes[0]
    : `${selectedSizes[0]} +${selectedSizes.length - 1}`;

  const themeCreateReady =
    hasRoleAssets(themeCreateAssets, "upload") &&
    (
      themeCreateMode === "style_modify"
        ? prompt.trim().length > 0
        : themeCreateMode === "style_transfer"
        ? hasRoleAssets(themeCreateAssets, "reference_ad")
        : hasRoleAssets(themeCreateAssets, "client_logo") &&
          hasRoleAssets(themeCreateAssets, "brand_element") &&
          themeCreateOldText.trim().length > 0 &&
          themeCreateNewText.trim().length > 0 &&
          themeCreateFontStyle.trim().length > 0
    );

  const resizeReady = createFlow === "resize" && !!resizeSourceAsset && selectedSizes.length > 0;
  const orderedSelectedResizeSizes = RESIZE_SIZE_ORDER.filter((size) => selectedSizes.includes(size));
  const hasAnyResizeOverride =
    orderedSelectedResizeSizes.some((size) => (resizePromptOverrides[size] ?? "").trim().length > 0) ||
    resizeNegativePromptOverride.trim().length > 0;

  const canGenerate =
    !generating &&
    (
      createFlow === "resize"
        ? resizeReady
        : createFlow === "theme_create"
        ? themeCreateReady
        : false
    );
  const activeRunningJob =
    (currentJobId ? liveJobs.find((j) => (j.jobId ?? j.id) === currentJobId) : null) ??
    liveJobs.find((j) => j.status === "running" || j.status === "pending") ??
    null;
  const isTaskRunning = generating || activeRunningJob?.status === "running" || activeRunningJob?.status === "pending";
  const taskProgress = activeRunningJob?.progress ?? (currentJobId ? 15 : 5);
  const taskMessage = activeRunningJob?.message ?? "";
  const taskStatusLabel = uploadingSource
    ? "Uploading source image"
    : !currentJobId && !activeRunningJob
    ? "Starting"
    : taskProgress < 30
    ? "Planning"
    : taskProgress < 70
    ? "Generating"
    : taskProgress < 95
    ? "Preparing"
    : "Finalizing";

  // ─────────────────────────────────────────────────────────────────────────────
  return (
    <>
    <div className="flex flex-1 min-w-0 h-screen overflow-hidden bg-background">

      {/* ── Main column ── */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">

      {/* ── Header ── */}
      <div className="shrink-0 border-b px-8 pb-0 pt-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h1 className="font-display text-2xl font-semibold">Image &amp; Video</h1>
            <Badge variant="secondary" className="text-xs">Beta</Badge>
          </div>
          <div className="flex items-center gap-2 pb-1">
            <FeedbackButton />
            <DocsButton />
            {/* Assets panel toggle */}
            <button
              type="button"
              onClick={() => setRightPanelOpen((v) => !v)}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
                rightPanelOpen
                  ? "bg-foreground text-background hover:opacity-80"
                  : "bg-muted text-foreground hover:bg-muted/80"
              )}
            >
              <PanelRight className="size-3.5" />
              Assets
            </button>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3 pb-4">
          {/* ── Project switcher ── */}
        <div ref={sessionMenuRef} className="relative flex items-center gap-2">
            {/* Dropdown button */}
            <button
              type="button"
              onClick={() => setSessionMenuOpen((open) => !open)}
              className="flex w-52 items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-left text-sm font-semibold text-foreground transition-colors hover:border-foreground/20"
            >
              <span className="min-w-0 flex-1 truncate">{sessionTitle}</span>
              <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", sessionMenuOpen && "rotate-180")} />
            </button>

            {/* New Project — solid black button, always visible */}
            <button
              type="button"
              onClick={() => {
                setSelectedThreadId(null);
                setStartingNewSession(true);
                setSessionMenuOpen(false);
                setWorkingImage(null);
                setActiveOp(null);
                setPrompt("");
                setHiddenJobIds(new Set());
                onThreadSelect?.(null);
              }}
              className="flex items-center gap-1.5 rounded-xl bg-foreground px-3 py-2 text-sm font-semibold text-background transition-opacity hover:opacity-80"
            >
              <span className="text-base leading-none">+</span>
              New Project
            </button>

            {sessionMenuOpen && (
              <div className="absolute left-0 top-[calc(100%+6px)] z-40 w-80 rounded-2xl border border-border bg-card p-2 shadow-2xl">
                <div className="px-2 py-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
                    Projects
                  </p>
                </div>
                <div className="mt-1 max-h-72 space-y-1 overflow-y-auto pr-0.5 [scrollbar-width:thin]">
                  {currentProjectSessions.filter(t => t.assetCount > 0).length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border bg-background/70 px-3 py-4 text-xs text-muted-foreground">
                      No projects yet. Start generating to create your first project.
                    </div>
                  ) : (
                    currentProjectSessions.filter(t => t.assetCount > 0).map((thread) => (
                      <div key={thread.id} className="group relative">
                        {renamingThreadId === thread.id ? (
                          /* Inline rename input */
                          <form
                            onSubmit={async (e) => {
                              e.preventDefault();
                              await renameThread(thread.id, renameValue);
                              const updated = await listThreads(activeWorkspaceId);
                              setLiveThreads(updated);
                              setRenamingThreadId(null);
                            }}
                            className="flex gap-1 rounded-xl border border-accent/40 bg-soft-accent/40 px-3 py-2"
                          >
                            <input
                              autoFocus
                              value={renameValue}
                              onChange={(e) => setRenameValue(e.target.value)}
                              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                              onKeyDown={(e) => e.key === "Escape" && setRenamingThreadId(null)}
                            />
                            <button type="submit" className="text-[10px] font-semibold text-accent">Save</button>
                          </form>
                        ) : (
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedThreadId(thread.id);
                              setStartingNewSession(false);
                              setSessionMenuOpen(false);
                              onThreadSelect?.(thread.id);
                            }}
                            className={cn(
                              "w-full rounded-xl border px-3 py-2.5 text-left transition-colors",
                              selectedThreadId === thread.id && !startingNewSession
                                ? "border-accent/40 bg-soft-accent/60"
                                : "border-transparent hover:border-border hover:bg-muted/40"
                            )}
                          >
                            <p className="truncate pr-10 text-sm font-medium text-foreground">{thread.title}</p>
                            <p className="mt-1 text-[11px] text-muted-foreground">
                              {thread.jobCount} runs · {thread.assetCount} assets
                            </p>
                          </button>
                        )}

                        {/* Rename + Delete — appear on hover */}
                        {renamingThreadId !== thread.id && (
                          <div className="absolute right-2 top-2 hidden items-center gap-1 group-hover:flex">
                            <button
                              type="button"
                              title="Rename"
                              onClick={(e) => {
                                e.stopPropagation();
                                setRenamingThreadId(thread.id);
                                setRenameValue(thread.title);
                              }}
                              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                            >
                              <Pencil className="size-3" />
                            </button>
                            <button
                              type="button"
                              title="Delete project"
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!confirm(`Delete "${thread.title}"? This cannot be undone.`)) return;
                                await deleteThread(thread.id);
                                if (selectedThreadId === thread.id) {
                                  setSelectedThreadId(null);
                                  setStartingNewSession(true);
                                  onThreadSelect?.(null);
                                }
                                const updated = await listThreads(activeWorkspaceId);
                                setLiveThreads(updated);
                              }}
                              className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                            >
                              <Trash2 className="size-3" />
                            </button>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
          <Badge variant="secondary" className="text-[10px]">
            Continuous History
          </Badge>
          <span className="hidden text-xs text-muted-foreground">
            {selectedThread
              ? `${selectedThreadAssets.length} assets · ${selectedThreadJobs.length} runs`
              : startingNewSession
              ? "Start a fresh session inside this project."
              : currentProjectSessions.length === 0
              ? "No sessions yet in this project."
              : "Select a session to continue editing."}
          </span>
          <span className="text-xs text-muted-foreground">
            {downloadableAssets.length > 0
              ? `${downloadableAssets.length} assets · ${projectJobEntries.length} runs in this project`
              : "All new generations and edits stay inside this project until you switch projects."}
          </span>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto max-w-4xl">
          {/* Generating placeholder — occupies one grid cell */}
          {isTaskRunning && (
            <GenerationCard assets={[]} title={lastPrompt || "Generating…"} isGenerating />
          )}

          {/* Generation stream — each card spans full width with internal 3-col grid */}
          <div className="grid grid-cols-3 gap-6">
          {projectJobEntries
            .filter((e) => !hiddenJobIds.has(e.id))
            .map((jobEntry) => (
              <GenerationCard
                key={jobEntry.id}
                assets={jobEntry.assets}
                title={jobEntry.title}
                promptText={jobEntry.promptText}
                selectedAssetIds={selectedAssetIds}
                onToggleSelect={toggleAsset}
                onSetWorking={setWorkingImageFromAsset}
                onRegenerate={
                  jobEntry.assets.some((asset) => asset.parentAssetId || asset.rootAssetId)
                    ? () => handleRegenerate(jobEntry)
                    : undefined
                }
                onRegenerateAsset={
                  jobEntry.assets.some((asset) => asset.parentAssetId || asset.rootAssetId)
                    ? handleRegenerateAsset
                    : undefined
                }
                onHide={() => setHiddenJobIds((prev) => new Set([...prev, jobEntry.id]))}
                onZoom={setZoomedAsset}
              />
            ))}
          </div>

          {hiddenJobIds.size > 0 && (
            <div className="mt-4 flex items-center justify-center">
              <button
                type="button"
                onClick={() => setHiddenJobIds(new Set())}
                className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                Show hidden runs ({hiddenJobIds.size})
              </button>
            </div>
          )}

          {/* Empty state — shown when grid is empty */}
          {!isTaskRunning && projectJobEntries.filter((e) => !hiddenJobIds.has(e.id)).length === 0 && (
            <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 rounded-3xl border border-dashed border-border bg-muted/20 text-center">
              <div className="grid size-16 place-items-center rounded-2xl border-2 border-dashed border-border bg-muted/40">
                <ImageIcon className="size-7 text-muted-foreground/40" />
              </div>
              <div>
                <p className="font-semibold">No generations yet</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Describe what you want to create below
                </p>
              </div>
            </div>
          )}
        </div>

      </div>

      {/* ── Bottom input bar — floats over history ── */}
      <div className="relative min-h-0 shrink-0 overflow-visible bg-background px-6 pb-6 pt-3" style={{ maxHeight: "calc(100svh - 120px)" }}>
        {/* Gradient fade so history content dissolves into the bar */}
        <div className="pointer-events-none absolute inset-x-0 bottom-full h-16 bg-gradient-to-t from-background to-transparent" />
        <div className="mx-auto max-w-2xl">

          {/* Error banner */}
          {error && (
            <div className="mb-2 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5">
              <p className="flex-1 text-xs text-destructive">{error}</p>
              <button type="button" onClick={() => setError(null)} className="shrink-0">
                <X className="size-3.5 text-destructive" />
              </button>
            </div>
          )}

          {/* ── Input card ── */}
          {isTaskRunning && (
            <div className="mb-2 overflow-hidden rounded-xl border border-accent/25 bg-soft-accent/50 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <Loader2 className="size-3.5 animate-spin text-accent" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-accent">
                    {taskMessage || `${taskStatusLabel}…`}
                  </p>
                  <p className="truncate text-[11px] text-accent/70">
                    {uploadingSource ? "Sending image to server" : (lastPrompt || "Your generation is running")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="rounded-full border border-accent/30 px-2.5 py-1 text-[11px] font-semibold text-accent hover:bg-accent/10"
                >
                  Cancel
                </button>
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-accent/10">
                <div
                  className="h-full rounded-full bg-accent transition-all"
                  style={{ width: `${Math.max(8, Math.min(100, taskProgress))}%` }}
                />
              </div>
            </div>
          )}

          <div
            ref={barRef}
            className="rounded-2xl border border-border bg-card shadow-[0_2px_16px_rgba(0,0,0,0.06)] transition-shadow focus-within:shadow-[0_2px_20px_rgba(0,0,0,0.10)] flex flex-col"
            style={{ maxHeight: "calc(100svh - 220px)" }}
          >

            {/* Task type tabs: Resize | Theme Create */}
            <div className="shrink-0 flex items-center gap-1 px-4 pt-3 pb-2 border-b border-border">
              {CREATE_FLOW_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setCreateFlow(tab.id)}
                  className={cn(
                    "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all",
                    createFlow === tab.id
                      ? "bg-foreground text-background shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Scrollable form sections — keeps textarea+chips always visible */}
            <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-width:thin]">

            {createFlow === "theme_create" && (
              <div className="space-y-4 border-t border-border px-4 py-3">
                <div className="flex flex-wrap gap-2">
                  {THEME_CREATE_MODES.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setThemeCreateMode(item.id)}
                      className={cn(
                        "rounded-xl border px-3 py-2 text-left transition-colors",
                        themeCreateMode === item.id
                          ? "border-foreground bg-foreground text-background"
                          : "border-border bg-background/60 text-foreground hover:border-foreground/20"
                      )}
                    >
                      <p className="text-sm font-medium">{item.label}</p>
                      <p className={cn("mt-1 text-[11px] leading-5", themeCreateMode === item.id ? "text-background/80" : "text-muted-foreground")}>
                        {item.blurb}
                      </p>
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap gap-2">
                  <ThemeAssetInput
                    title="Source Image"
                    hint="Image 1"
                    required
                    file={themeCreateAssets.upload?.[0] ?? null}
                    onPick={(file) => setSingleThemeAsset("upload", file)}
                    onClear={() => setSingleThemeAsset("upload", null)}
                  />

                  {themeCreateMode === "style_transfer" && (
                    <ThemeAssetInput
                      title="Reference Image"
                      hint="Image 2"
                      required
                      file={themeCreateAssets.reference_ad?.[0] ?? null}
                      onPick={(file) => setSingleThemeAsset("reference_ad", file)}
                      onClear={() => setSingleThemeAsset("reference_ad", null)}
                    />
                  )}

                  {themeCreateMode === "asset_text_replace" && (
                    <>
                      <ThemeAssetInput
                        title="Reference Image A"
                        hint="Image 2 · New Logo"
                        required
                        file={themeCreateAssets.client_logo?.[0] ?? null}
                        onPick={(file) => setSingleThemeAsset("client_logo", file)}
                        onClear={() => setSingleThemeAsset("client_logo", null)}
                      />
                      <ThemeAssetInput
                        title="Reference Image B"
                        hint="Image 3 · New Button / Element"
                        required
                        file={themeCreateAssets.brand_element?.[0] ?? null}
                        onPick={(file) => setSingleThemeAsset("brand_element", file)}
                        onClear={() => setSingleThemeAsset("brand_element", null)}
                      />
                    </>
                  )}
                </div>

                {themeCreateMode === "asset_text_replace" && (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-1">
                      <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        Logo Position
                      </label>
                      <select
                        value={themeCreateLogoPosition}
                        onChange={(e) => setThemeCreateLogoPosition(e.target.value)}
                        className="w-full rounded-xl border border-border bg-card px-3 py-2 text-sm outline-none focus:border-accent/40"
                      >
                        {THEME_CREATE_POSITION_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        Element Position
                      </label>
                      <select
                        value={themeCreateElementPosition}
                        onChange={(e) => setThemeCreateElementPosition(e.target.value)}
                        className="w-full rounded-xl border border-border bg-card px-3 py-2 text-sm outline-none focus:border-accent/40"
                      >
                        {THEME_CREATE_POSITION_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        Old Text
                      </label>
                      <input
                        value={themeCreateOldText}
                        onChange={(e) => setThemeCreateOldText(e.target.value)}
                        placeholder="Text currently shown in Image 1"
                        className="w-full rounded-xl border border-border bg-card px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:border-accent/40"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        New Text
                      </label>
                      <input
                        value={themeCreateNewText}
                        onChange={(e) => setThemeCreateNewText(e.target.value)}
                        placeholder="Exact replacement text"
                        className="w-full rounded-xl border border-border bg-card px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:border-accent/40"
                      />
                    </div>
                    <div className="space-y-1 md:col-span-2">
                      <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        Font Style
                      </label>
                      <input
                        value={themeCreateFontStyle}
                        onChange={(e) => setThemeCreateFontStyle(e.target.value)}
                        placeholder="bold sans-serif, elegant serif, condensed display..."
                        className="w-full rounded-xl border border-border bg-card px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:border-accent/40"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Resize source image thumbnail chip */}
            {createFlow === "resize" && resizeSourceAsset && (
              <div className="flex flex-wrap gap-1.5 px-4 pb-1 pt-0">
                <div className="group relative flex items-center gap-2 rounded-lg border border-accent/40 bg-soft-accent/30 px-2 py-1">
                  <div className="size-7 shrink-0 overflow-hidden rounded-md border border-accent/20">
                    <img src={resizeSourceAsset.url} alt="" className="h-full w-full object-cover" />
                  </div>
                  <span className="max-w-[120px] truncate text-xs text-foreground">{resizeSourceAsset.name}</span>
                  <button type="button" onClick={() => setResizeSourceAsset(null)} className="text-muted-foreground hover:text-foreground">
                    <X className="size-3" />
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => void handleGenerateGifFromResizeSource()}
                  disabled={generating || uploadingSource}
                  className={cn(
                    "rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
                    generating || uploadingSource
                      ? "cursor-not-allowed border-border bg-muted text-muted-foreground"
                      : "border-border bg-background/80 text-foreground hover:border-foreground/20 hover:bg-muted"
                  )}
                >
                  Generate GIF
                </button>
              </div>
            )}

            {false && createFlow === "resize" && (
              <div className="border-t border-border px-4 py-3">
                <button
                  type="button"
                  onClick={() => setShowDevPromptOverride((prev) => !prev)}
                  className="flex w-full items-center justify-between rounded-xl border border-border bg-background/60 px-3 py-2 text-left transition-colors hover:border-foreground/20"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">Dev Prompt Override</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Override resize prompts per size for local testing without editing backend templates.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {hasAnyResizeOverride && (
                      <Badge variant="secondary" className="text-[10px]">Override Active</Badge>
                    )}
                    <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", showDevPromptOverride && "rotate-180")} />
                  </div>
                </button>

                {showDevPromptOverride && (
                  <div className="mt-3 space-y-3 rounded-2xl border border-border bg-background/40 p-3">
                    <div className="space-y-1">
                      <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        Negative Prompt Override
                      </label>
                      <textarea
                        value={resizeNegativePromptOverride}
                        onChange={(e) => setResizeNegativePromptOverride(e.target.value)}
                        rows={3}
                        placeholder="Optional. Leave blank to use the default negative prompt."
                        className="w-full resize-y rounded-xl border border-border bg-card px-3 py-2 text-xs leading-5 outline-none placeholder:text-muted-foreground focus:border-accent/40"
                      />
                    </div>

                    <div className="space-y-3">
                      {orderedSelectedResizeSizes.map((size) => (
                        <div key={size} className="space-y-1">
                          <div className="flex items-center justify-between gap-3">
                            <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                              {size} Prompt Override
                            </label>
                            {(resizePromptOverrides[size] ?? "").trim() && (
                              <button
                                type="button"
                                onClick={() =>
                                  setResizePromptOverrides((prev) => {
                                    const next = { ...prev };
                                    delete next[size];
                                    return next;
                                  })
                                }
                                className="text-[11px] text-muted-foreground hover:text-foreground"
                              >
                                Clear
                              </button>
                            )}
                          </div>
                          <textarea
                            value={resizePromptOverrides[size] ?? ""}
                            onChange={(e) =>
                              setResizePromptOverrides((prev) => ({
                                ...prev,
                                [size]: e.target.value,
                              }))
                            }
                            rows={8}
                            placeholder={`Optional override for ${size}. Leave blank to use the backend default prompt.`}
                            className="w-full resize-y rounded-xl border border-border bg-card px-3 py-2 text-xs leading-5 outline-none placeholder:text-muted-foreground focus:border-accent/40"
                          />
                        </div>
                      ))}
                    </div>

                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setResizePromptOverrides({});
                          setResizeNegativePromptOverride("");
                        }}
                        className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
                      >
                        Clear All Overrides
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Hidden file inputs */}
            <input
              ref={resizeFileRef}
              type="file"
              accept="image/*"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const url = URL.createObjectURL(file);
                setResizeSourceAsset({ id: null, url, name: file.name, file });
                e.target.value = "";
              }}
            />
            {/* Kakao Bizboard batch flow */}
            {createFlow === "kakao" && (
              <div className="flex-1">
                <KakaoFlow
                  activeWorkspaceId={activeWorkspaceId}
                  onAssetsCreated={() => {
                    Promise.all([listAssets(activeWorkspaceId), listThreads(activeWorkspaceId)])
                      .then(([a, t]) => {
                        setLiveAssets(a);
                        setLiveThreads(t);
                        const latestThread = [...t].sort(
                          (left, right) =>
                            new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime()
                        )[0];
                        if (latestThread?.id) {
                          setSelectedThreadId(latestThread.id);
                          setStartingNewSession(false);
                          onThreadSelect?.(latestThread.id);
                        }
                      })
                      .catch(() => {});
                  }}
                />
              </div>
            )}

            </div>{/* end scrollable form sections */}

            {/* Textarea — hidden only for Kakao */}
            {createFlow !== "kakao" && <textarea
              value={prompt}
              onChange={(e) => {
                const value = e.target.value;
                setPrompt(value);
                if (createFlow === "theme_create" && themeCreateMode === "style_modify") {
                  setThemeCreateStyleName(value);
                  setThemeCreateStyleDetails(value);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && canGenerate) {
                  e.preventDefault();
                  handleGenerate();
                }
              }}
              placeholder={
                createFlow === "resize"
                  ? resizeSourceAsset
                    ? "Optional note on the resize (e.g. focus on the logo)…"
                    : "Tap + to upload a source image, then send to resize…"
                  : createFlow === "theme_create"
                  ? themeCreateMode === "style_modify"
                    ? "Describe the new artistic style and visual treatment you want..."
                    : themeCreateMode === "style_transfer"
                    ? "Optional direction for how Image 1 should inherit the style of Image 2..."
                    : "Optional instruction for the replacement task..."
                  : mode === "image"
                  ? "Describe the image you want to generate…"
                  : "Describe your endcard creative…"
              }
              rows={3}
              className="w-full resize-none bg-transparent px-4 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground"
            />}

            {/* ── Chip row (hidden for Kakao) ── */}
            {createFlow !== "kakao" &&
            <div className="flex items-center gap-1.5 px-4 pb-3 pt-1">

              {/* Model chip */}
              {createFlow === "theme_create" ? (
                <div className="relative">
                  <ChipButton
                    label={`Model · ${activeModel.short}`}
                    active={activeChip === "model"}
                    onClick={() => toggleChip("model")}
                  />
                  {activeChip === "model" && (
                    <DropdownPanel className="left-0 w-64">
                      <DropdownLabel>Model</DropdownLabel>
                      {ALL_MODELS.map((m) => (
                        <DropdownItem
                          key={m.id}
                          label={m.short}
                          sub={m.sub}
                          selected={modelId === m.id}
                          onClick={() => { setModelId(m.id); setActiveChip(null); }}
                        />
                      ))}
                    </DropdownPanel>
                  )}
                </div>
              ) : (
                <div className="flex items-center rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  Model · Gemini 3.1 Flash
                </div>
              )}

              {/* Size chip — multi-select for Resize, fixed 1200x628 for Theme Create */}
              {createFlow === "resize" ? (
                <div className="relative">
                  <ChipButton
                    label={`Size · ${selectedSizes.length || "0"}`}
                    active={activeChip === "sizes"}
                    onClick={() => toggleChip("sizes")}
                  />
                  {activeChip === "sizes" && (
                    <DropdownPanel className="left-0 w-52">
                      <p className="px-3 pb-1 pt-1.5 text-[11px] text-muted-foreground">
                        Target Sizes — {selectedSizes.length} selected
                      </p>
                      <div className="max-h-72 overflow-y-auto [scrollbar-width:thin]">
                        {RESIZE_SIZE_GROUPS.map((group) => (
                          <div key={group.label}>
                            <div className="px-3 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/60">
                              {group.label}
                            </div>
                            {group.sizes.map((sz) => (
                              <DropdownItem
                                key={sz}
                                label={sz}
                                selected={selectedSizes.includes(sz)}
                                onClick={() =>
                                  setSelectedSizes((cur) =>
                                    cur.includes(sz) ? cur.filter((x) => x !== sz) : [...cur, sz]
                                  )
                                }
                              />
                            ))}
                          </div>
                        ))}
                      </div>
                    </DropdownPanel>
                  )}
                </div>
              ) : (
                <div className="flex items-center rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  1200×628
                </div>
              )}

              {/* GIF toggle — Resize only */}
              {createFlow === "resize" && (
                <button
                  type="button"
                  onClick={() => setIncludeGif((v) => !v)}
                  className={cn(
                    "flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium transition-all",
                    includeGif
                      ? "border-accent/50 bg-soft-accent text-accent"
                      : "border-border text-muted-foreground hover:text-foreground"
                  )}
                >
                  + GIF
                </button>
              )}

              {/* Variants chip */}
              <div className={cn("relative", createFlow === "resize" && "hidden")}>
                <ChipButton
                  label="Variants"
                  active={activeChip === "variants"}
                  onClick={() => toggleChip("variants")}
                />
                {activeChip === "variants" && (
                  <DropdownPanel className="right-0 w-40">
                    <DropdownLabel>Variants</DropdownLabel>
                    {([1, 2] as const).map((n) => (
                      <DropdownItem
                        key={n}
                        label={String(n)}
                        selected={variants === n}
                        onClick={() => { setVariants(n); setActiveChip(null); }}
                      />
                    ))}
                  </DropdownPanel>
                )}
              </div>

              {/* Cancel button — visible only while generating */}
              {isTaskRunning && (
                <button
                  type="button"
                  onClick={handleCancel}
                  className="ml-auto flex items-center gap-1.5 rounded-full border border-destructive/40 bg-destructive/10 px-3 py-1.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20"
                >
                  <X className="size-3" />
                  Cancel
                </button>
              )}

              {/* Attach + Send (right-aligned group) */}
              <div className={cn("flex items-center gap-1.5", !isTaskRunning && "ml-auto")}>
                {/* Upload button — source image for Resize */}
                <button
                  type="button"
                  title={createFlow === "resize" ? "Upload source image" : undefined}
                  onClick={() => {
                    if (createFlow === "resize") resizeFileRef.current?.click();
                  }}
                  disabled={createFlow !== "resize"}
                  className={cn(
                    "relative flex size-8 items-center justify-center rounded-full transition-colors",
                    createFlow !== "resize"
                      ? "cursor-not-allowed text-muted-foreground/40"
                      : createFlow === "resize" && resizeSourceAsset
                      ? "bg-soft-accent text-accent"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <Plus className="size-4" />
                </button>

                {/* Send button */}
                <button
                  type="button"
                  onClick={() => void handleGenerate()}
                  disabled={!canGenerate}
                  className={cn(
                    "flex size-9 items-center justify-center rounded-full transition-all",
                    canGenerate
                      ? "bg-foreground text-background shadow-md hover:opacity-80"
                      : "cursor-not-allowed bg-muted text-muted-foreground"
                  )}
                >
                  {generating ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <ArrowUp className="size-4" />
                  )}
                </button>
              </div>

            </div>}

          </div>
        </div>
      </div>

      </div>{/* end main column */}

      {/* ── Right assets panel ── */}
      {rightPanelOpen && (
        <aside className="flex w-80 shrink-0 flex-col overflow-hidden border-l border-border bg-card">
          {/* Panel header */}
          <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
            <span className="text-sm font-semibold">Assets</span>
            <button
              type="button"
              onClick={() => setRightPanelOpen(false)}
              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>

          {/* Prefix input */}
          <div className="shrink-0 border-b border-border px-4 py-3">
            <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              File prefix
            </label>
            <div className="flex items-center">
              <input
                type="text"
                value={downloadPrefix}
                onChange={(e) => setDownloadPrefix(e.target.value.replace(/[^a-zA-Z0-9_-]/g, ""))}
                placeholder="incept"
                className="min-w-0 flex-1 rounded-l-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-accent/60"
              />
              <span className="rounded-r-lg border border-l-0 border-border bg-muted px-2.5 py-1.5 text-[10px] text-muted-foreground whitespace-nowrap">
                _1200x628.png
              </span>
            </div>
            <p className="mt-1.5 text-[10px] text-muted-foreground">
              e.g. <span className="font-mono">{downloadPrefix || "incept"}_300x250.png</span>
            </p>
          </div>

          {/* Select all row */}
          {downloadableAssets.length > 0 && (
            <div className="shrink-0 border-b border-border px-4 py-2">
              <button
                type="button"
                onClick={toggleAll}
                className="flex items-center gap-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                {allSelected
                  ? <CheckSquare className="size-4 text-accent" />
                  : <Square className="size-4" />}
                {allSelected
                  ? "Deselect all"
                  : `Select all (${downloadableAssets.length})`}
              </button>
            </div>
          )}

          {/* Asset grid */}
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {downloadableAssets.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                <ImageIcon className="size-8 text-muted-foreground/30" />
                <p className="text-xs text-muted-foreground">No generated images yet</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {downloadableAssets.map((asset) => {
                  const selected = selectedAssetIds.has(asset.id);
                  const ratio =
                    asset.width && asset.height ? asset.width / asset.height : 1;
                  return (
                    <div
                      key={asset.id}
                      className={cn(
                        "group relative overflow-hidden border-2 transition-all",
                        selected
                          ? "border-accent shadow-[0_0_0_1px_hsl(var(--accent)/0.3)]"
                          : "border-transparent hover:border-border"
                      )}
                    >
                      {/* Thumbnail */}
                      <button
                        type="button"
                        onClick={() => setPreviewState({ assets: downloadableAssets, index: downloadableAssets.findIndex((item) => item.id === asset.id) })}
                        className="w-full overflow-hidden bg-[#07111F]"
                        style={{ aspectRatio: Math.min(Math.max(ratio, 0.4), 3) }}
                      >
                        <img
                          src={asset.url}
                          alt={asset.title}
                          className="h-full w-full object-cover"
                        />
                      </button>

                      {/* Checkbox */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleAsset(asset.id);
                        }}
                        className={cn(
                          "absolute right-1.5 top-1.5 z-10 flex size-5 items-center justify-center rounded-full border-2 transition-all",
                          selected
                            ? "border-accent bg-accent text-white"
                            : "border-white/60 bg-black/30 group-hover:border-white"
                        )}
                      >
                        {selected && <Check className="size-3" />}
                      </button>

                      {/* Size + format label */}
                      <div className="absolute bottom-1.5 left-1.5 rounded-md bg-black/75 px-1.5 py-0.5 backdrop-blur-sm">
                        <span className="text-[8px] font-semibold text-white">
                          {asset.width && asset.height
                            ? `${asset.width}×${asset.height} · ${asset.type === "gif" ? "GIF" : "PNG"}`
                            : asset.type === "gif" ? "GIF" : "PNG"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Download + Delete */}
          <div className="shrink-0 space-y-2 border-t border-border p-3">
            <button
              type="button"
              onClick={handleGenerateGifSelected}
              disabled={selectedGifEligibleAssets.length === 0 || generating}
              className={cn(
                "flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all",
                selectedGifEligibleAssets.length > 0 && !generating
                  ? "border border-border bg-background text-foreground hover:bg-muted"
                  : "cursor-not-allowed bg-muted text-muted-foreground"
              )}
            >
              {generating ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              {selectedGifEligibleAssets.length === 0
                ? "Select PNG assets"
                : selectedGifEligibleAssets.length === 1
                ? "Generate GIF"
                : `Generate GIF (${selectedGifEligibleAssets.length})`}
            </button>
            <button
              type="button"
              onClick={handleDownload}
              disabled={selectedAssetIds.size === 0 || downloading}
              className={cn(
                "flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-all",
                selectedAssetIds.size > 0 && !downloading
                  ? "bg-foreground text-background hover:opacity-80"
                  : "cursor-not-allowed bg-muted text-muted-foreground"
              )}
            >
              {downloading ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
              {downloading ? "Preparing…" : selectedAssetIds.size === 0 ? "Select to download" : selectedAssetIds.size === 1 ? "Download PNG" : `Download ${selectedAssetIds.size}`}
            </button>
            <button
              type="button"
              onClick={handleDeleteSelected}
              disabled={selectedAssetIds.size === 0}
              className={cn(
                "flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all",
                selectedAssetIds.size > 0
                  ? "border border-destructive/40 bg-destructive/10 text-destructive hover:bg-destructive/20"
                  : "cursor-not-allowed text-muted-foreground"
              )}
            >
              <Trash2 className="size-4" />
              {selectedAssetIds.size === 0 ? "Select to delete" : `Delete ${selectedAssetIds.size}`}
            </button>
          </div>
        </aside>
      )}

    </div>

    {/* ── Image zoom modal ── */}
    {zoomedAsset && (
      <ZoomModal
        asset={zoomedAsset}
        onClose={() => setZoomedAsset(null)}
        onRegenerate={handleRegenerateAsset}
      />
    )}

    {/* ── Inpainting canvas modal ── */}
    {previewState && previewState.assets[previewState.index] && (
      <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 p-6">
        <div className="relative flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-[#07111F] shadow-2xl">
          <button
            type="button"
            onClick={() => setPreviewState(null)}
            className="absolute right-4 top-4 z-10 rounded-full bg-black/50 p-2 text-white hover:bg-black/70"
          >
            <X className="size-4" />
          </button>
          <div className="flex min-h-0 flex-1 items-center justify-center bg-black/30 p-6">
            <img
              src={previewState.assets[previewState.index].url}
              alt={previewState.assets[previewState.index].title}
              className="max-h-[72vh] max-w-full rounded-2xl object-contain"
            />
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-white/10 bg-card px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-foreground">
                {previewState.assets[previewState.index].title}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {previewState.assets[previewState.index].width && previewState.assets[previewState.index].height
                  ? `${previewState.assets[previewState.index].width}x${previewState.assets[previewState.index].height}`
                  : previewState.assets[previewState.index].model}
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setWorkingImageFromAsset(previewState.assets[previewState.index]);
                setPreviewState(null);
              }}
              className="rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white hover:opacity-85"
            >
              Use as Working Image
            </button>
            <button
              type="button"
              onClick={() => {
                const asset = previewState.assets[previewState.index];
                setEditTarget({
                  assetId: asset.id,
                  url: asset.url,
                  width: asset.width ?? 1024,
                  height: asset.height ?? 1024,
                  theme: asset.theme,
                });
                setPreviewState(null);
              }}
              className="rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted"
            >
              Mask Edit
            </button>
            {previewState.assets[previewState.index].type !== "gif" && (
              <button
                type="button"
                onClick={() => {
                  const asset = previewState.assets[previewState.index];
                  void triggerGifJob(asset.id, asset.threadId);
                  setPreviewState(null);
                }}
                className="rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted"
              >
                Generate GIF
              </button>
            )}
            {((previewState.assets[previewState.index].parentAssetId || previewState.assets[previewState.index].rootAssetId) &&
              previewState.assets[previewState.index].width &&
              previewState.assets[previewState.index].height) && (
              <button
                type="button"
                onClick={() => handleRegenerateAsset(previewState.assets[previewState.index])}
                className="rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted"
              >
                Regenerate This Size
              </button>
            )}
            {previewState.assets.length > 1 && (
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  onClick={() =>
                    setPreviewState((prev) =>
                      prev
                        ? {
                            ...prev,
                            index: prev.index === 0 ? prev.assets.length - 1 : prev.index - 1,
                          }
                        : prev
                    )
                  }
                  className="rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted"
                >
                  Prev
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setPreviewState((prev) =>
                      prev
                        ? {
                            ...prev,
                            index: (prev.index + 1) % prev.assets.length,
                          }
                        : prev
                    )
                  }
                  className="rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    )}

    {editTarget && (
      <InpaintingCanvas
        imageUrl={editTarget.url}
        assetId={editTarget.assetId}
        naturalWidth={editTarget.width}
        naturalHeight={editTarget.height}
        onClose={() => setEditTarget(null)}
        onSubmit={handleEditSubmit}
        submitting={editSubmitting}
      />
    )}
    </>
  );
}
