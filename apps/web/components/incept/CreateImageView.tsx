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
  Paperclip,
  PanelRight,
  Pencil,
  RotateCcw,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import type { AssetRole, AssetSummary, CreativeThreadSummary, GenerationMode, InceptUser, JobSummary } from "@incept/shared";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { addTextToImage, cancelJob, createImageGenerationJob, deleteAssets, deleteThread, downloadAssetsZip, editImage, listAssets, listThreads, outpaintImage, removeBackground, renameThread, splitContactSheet, uploadAsset } from "@/lib/incept-api";
import { InpaintingCanvas } from "@/components/incept/InpaintingCanvas";
import { DocsButton, FeedbackButton } from "@/components/incept/FeedbackButton";

// ─── Types ────────────────────────────────────────────────────────────────────

type CreativeMode = "image" | "endcard";
type OutputFormat = "static" | "gif";
type ProviderId = "openai" | "gemini";
type ActiveChip = "model" | "sizes" | "format" | "variants" | null;
type CreateFlow = GenerationMode;
type DraftAssetPreview = { id: string; url: string; name: string; file: File; role: AssetRole };
type AssetBucketState = Partial<Record<AssetRole, DraftAssetPreview[]>>;
type ClarificationOption = { id: string; label: string; note?: string };

// ─── Constants ────────────────────────────────────────────────────────────────

// ─── Size definitions ─────────────────────────────────────────────────────────

// Sizes grouped by family for the Resize task UI (endcard included as 4th group)
const RESIZE_SIZE_GROUPS = [
  { label: "Banner",           sizes: ["320x50", "728x90", "1200x222", "640x100"] },
  { label: "Landscape",        sizes: ["1200x628", "1200x600"] },
  { label: "Portrait / Square",sizes: ["320x480", "300x250", "720x720"] },
  { label: "Endcard",          sizes: ["360x640", "480x480", "640x360"] },
] as const;

const ENDCARD_SIZE_SET = new Set(["360x640", "480x480", "640x360"]);

const IMAGE_SIZES = [
  "320x50", "1200x628", "320x480", "300x250",
  "728x90", "640x100", "720x720", "1200x600", "1200x222",
];

// GIF supported for banner + medium + endcard sizes (large landscape GIF is impractical)
const GIF_ALLOWED_SIZES = new Set([
  "320x50", "728x90", "1200x222", "640x100", // banner
  "300x250",                                   // medium
  "360x640", "480x480", "640x360",             // endcard
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
  { id: "free_create",  label: "Theme Create", blurb: "Generate new creative variants from client assets and a theme prompt." },
];

const STYLE_MATCH_ROLES: Array<{ role: AssetRole; title: string; hint: string; required?: boolean }> = [
  { role: "reference_ad", title: "Reference Ad", hint: "Upload the ad whose composition and style we should match.", required: true },
  { role: "client_character", title: "Client Character", hint: "Character or hero subject that must stay recognizable." },
  { role: "client_logo", title: "Client Logo", hint: "Brand logo. This should survive adaptation and stay legible.", required: true },
  { role: "client_product", title: "Product / Packshot", hint: "Optional product art or packshot to preserve." },
  { role: "client_background", title: "Background", hint: "Optional environment or key scene asset." },
];

const THEME_CREATE_ROLES: Array<{ role: AssetRole; title: string; hint: string; required?: boolean }> = [
  { role: "client_character", title: "Client Character", hint: "Hero character or main visual subject." },
  { role: "client_logo", title: "Client Logo", hint: "Brand logo that must remain visible and consistent.", required: true },
  { role: "client_product", title: "Product / Packshot", hint: "Optional product asset or featured object." },
  { role: "client_background", title: "Background", hint: "Optional scene starting point or environment." },
  { role: "brand_element", title: "Brand Elements", hint: "Optional CTA shell, frame, sticker, or badge." },
];

// Flat list of supported models — provider shown as sub-text prefix
const ALL_MODELS: Array<{
  id: string;
  provider: ProviderId;
  short: string;
  sub: string;
}> = [
  { id: "gemini-3.1-flash-image", provider: "gemini", short: "Gemini 3.1 Flash", sub: "Google · Fastest" },
  { id: "gemini-2.5-flash-image", provider: "gemini", short: "Gemini 2.5 Flash", sub: "Google · Balanced" },
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
  if (mode === "style_match") return "Style Match";
  if (mode === "theme_create") return "Theme Create";
  return "Free Create";
}

function getContactSheetRole(asset: AssetSummary): string | null {
  const value = asset.analysis?.contact_sheet_role;
  return typeof value === "string" ? value : null;
}

function isContactSheetPreview(asset: AssetSummary): boolean {
  return getContactSheetRole(asset) === "sheet";
}

function isContactSheetHidden(asset: AssetSummary): boolean {
  const role = getContactSheetRole(asset);
  return role === "sheet" || role === "sheet_source";
}

function isContactSheetAlreadySplit(asset: AssetSummary): boolean {
  return asset.analysis?.contact_sheet_split_status === "split_completed";
}

function getContactSheetTitle(asset: AssetSummary): string {
  const title = asset.analysis?.contact_sheet_title;
  if (typeof title === "string" && title.trim()) return title.trim();
  const family = asset.analysis?.contact_sheet_family;
  if (family === "banner") return "Banner Sheet";
  if (family === "hero") return "Hero Sheet";
  return "Contact Sheet";
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
        "absolute bottom-[calc(100%+6px)] z-50 min-w-[180px] overflow-hidden rounded-xl border border-border bg-card py-1 shadow-xl",
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

function ZoomModal({ asset, onClose }: { asset: AssetSummary; onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const fmt = asset.type === "gif" ? "GIF" : "PNG";
  const label = asset.width && asset.height
    ? `${asset.width}×${asset.height} · ${fmt}`
    : fmt;

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
        <div className="flex shrink-0 items-center justify-between px-4 py-2.5 border-b border-border">
          <span className="text-xs font-semibold text-foreground">{label}</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
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
  onSetWorking,
  onRegenerate,
  onHide,
  onZoom,
  onSplit,
  splittingAssetId,
}: {
  assets: AssetSummary[];
  title: string;
  promptText?: string;
  isGenerating?: boolean;
  onSetWorking?: (asset: AssetSummary) => void;
  onRegenerate?: () => void;
  onHide?: () => void;
  onZoom?: (asset: AssetSummary) => void;
  onSplit?: (asset: AssetSummary) => void;
  splittingAssetId?: string | null;
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
  const firstWorkingAsset =
    realAssets.find((asset) => !isContactSheetPreview(asset)) ?? realAssets[0];
  const splitTargets = realAssets.filter((asset) => isContactSheetPreview(asset));

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
          {realAssets.map((a, i) => {
            const r = a.width && a.height ? a.width / a.height : 16 / 9;
            return (
              <div key={a.id} className="group/img">
                {/* Image tile — click to zoom */}
                <div
                  className="relative cursor-zoom-in overflow-hidden border border-border bg-[#07111F]"
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
        {splitTargets.length > 0 && onSplit && splitTargets.map((target) => (
          <button
            key={target.id}
            type="button"
            title={`Split ${getContactSheetTitle(target)}`}
            onClick={() => onSplit(target)}
            disabled={splittingAssetId === target.id}
            className="rounded-lg border border-border bg-card px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className="block text-[9px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/80">
              {getContactSheetTitle(target).replace(" Sheet", "")}
            </span>
            <span className="block px-0.5 text-[10px] font-semibold">
              {splittingAssetId === target.id
                ? "..."
                : isContactSheetAlreadySplit(target)
                ? "Split Again"
                : "Split"}
            </span>
          </button>
        ))}
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
  const [themeBrief, setThemeBrief] = useState("");
  const [modelId, setModelId] = useState("gemini-3.1-flash-image");
  const [selectedSizes, setSelectedSizes] = useState<string[]>(DEFAULT_IMAGE_SIZES);
  const [format, setFormat] = useState<OutputFormat>("static");

  // ── Additional GIF output (Resize mode add-on) ──
  const [includeGif, setIncludeGif] = useState(false);

  // ── Resize source image ──
  const [resizeSourceAsset, setResizeSourceAsset] = useState<{ id: string | null; url: string; name: string; file?: File } | null>(null);
  const resizeFileRef = useRef<HTMLInputElement>(null);
  const [variants, setVariants] = useState<1 | 2 | 3>(1);
  const [activeChip, setActiveChip] = useState<ActiveChip>(null);

  // Derive provider from selected model
  const activeModel = ALL_MODELS.find((m) => m.id === modelId) ?? ALL_MODELS[0];
  const provider = activeModel.provider;

  // ── Reference images ──
  const [refPreviews, setRefPreviews] = useState<
    { id: string; url: string; name: string; file: File }[]
  >([]);
  const [styleMatchAssets, setStyleMatchAssets] = useState<AssetBucketState>({});
  const [themeCreateAssets, setThemeCreateAssets] = useState<AssetBucketState>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Generation state ──
  const [generating, setGenerating] = useState(false);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [lastPrompt, setLastPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [clarificationState, setClarificationState] = useState<{
    jobId: string;
    question: string;
    reason?: string;
    options: ClarificationOption[];
  } | null>(null);
  const [clarificationSubmitting, setClarificationSubmitting] = useState(false);
  const clarificationRetryRef = useRef<((note: string) => Promise<void>) | null>(null);

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
  const [splittingAssetId, setSplittingAssetId] = useState<string | null>(null);
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
    clarificationNote?: string,
    overrideDirection?: "left" | "right" | "top" | "bottom" | "all",
    overrideRatio?: number,
  ) {
    const id = requireAssetId();
    if (!id) return;
    const direction = overrideDirection ?? outpaintDir;
    const ratio = overrideRatio ?? outpaintRatio;
    clarificationRetryRef.current = (note) => handleOutpaint(note, direction, ratio);
    setGenerating(true); setError(null);
    try {
      const res = await outpaintImage({
        workspaceId: activeWorkspaceId, assetId: id,
        direction, ratio,
        threadId: selectedThreadId ?? undefined,
        outputSizes: selectedSizes,
        clarificationNote,
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

  async function handleRemoveBG(clarificationNote?: string) {
    const id = requireAssetId();
    if (!id) return;
    clarificationRetryRef.current = (note) => handleRemoveBG(note);
    setGenerating(true); setError(null);
    try {
      const res = await removeBackground({
        workspaceId: activeWorkspaceId,
        assetId: id,
        threadId: selectedThreadId ?? undefined,
        outputSizes: selectedSizes,
        clarificationNote,
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

  async function handleAddText(clarificationNote?: string, overrideText?: string) {
    const baseText = (overrideText ?? textInput).trim();
    if (!baseText) return;
    const id = requireAssetId();
    if (!id) return;
    clarificationRetryRef.current = (note) => handleAddText(note, baseText);
    setGenerating(true); setError(null);
    try {
      const res = await addTextToImage({
        workspaceId: activeWorkspaceId,
        assetId: id,
        text: baseText,
        position: textPosition,
        threadId: selectedThreadId ?? undefined,
        outputSizes: selectedSizes,
        clarificationNote,
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

  async function handleEditWithPrompt(
    clarificationNote?: string,
    overridePrompt?: string,
    overrideRefs?: { id: string; url: string; name: string; file: File }[],
  ) {
    const id = requireAssetId();
    const basePrompt = (overridePrompt ?? prompt).trim() || lastPrompt.trim();
    const refsToUse = overrideRefs ?? refPreviews;
    if (!id || !basePrompt || generating) return;
    clarificationRetryRef.current = (note) => handleEditWithPrompt(note, basePrompt, refsToUse);
    setGenerating(true); setError(null); setLastPrompt(basePrompt);

    // Upload any pending refPreviews to get their asset IDs
    const extraIds: string[] = [];
    for (const r of refsToUse) {
      try {
        const up = await uploadAsset(r.file, activeWorkspaceId, "upload");
        if (up) extraIds.push(up.id);
      } catch { /* skip */ }
    }

    try {
      const res = await editImage({
        workspaceId: activeWorkspaceId, assetId: id,
        extraAssetIds: extraIds,
        maskDataUrl: undefined, prompt: basePrompt, model: modelId, variants,
        theme: basePrompt.split(/\s+/).slice(0, 5).join(" "),
        threadId: selectedThreadId ?? undefined,
        outputSizes: selectedSizes,
        clarificationNote,
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
      setPrompt("");
    } catch (err) {
      setGenerating(false);
      setError(`Edit failed: ${err instanceof Error ? err.message : String(err)}`);
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
      a.workspaceId === activeWorkspaceId &&
      !isContactSheetHidden(a)
  );
  const currentProjectSessions = [...liveThreads]
    .filter((thread) => thread.workspaceId === activeWorkspaceId)
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());

  const allSelected =
    downloadableAssets.length > 0 &&
    downloadableAssets.every((a) => selectedAssetIds.has(a.id));

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
      await downloadAssetsZip(ids, downloadPrefix || "incept");
    } catch (err) {
      console.error("Download failed:", err);
    } finally {
      setDownloading(false);
    }
  }

  async function handleSplitSheet(asset: AssetSummary) {
    if (splittingAssetId) return;
    setSplittingAssetId(asset.id);
    setError(null);
    try {
      await splitContactSheet(asset.id);
      const [assets, threads] = await Promise.all([
        listAssets(activeWorkspaceId),
        listThreads(activeWorkspaceId),
      ]);
      setLiveAssets(assets);
      setLiveThreads(threads);
    } catch (err) {
      setError(`Split failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSplittingAssetId(null);
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
    if (job.status === "needs_clarification") {
      setGenerating(false);
      setCurrentJobId(null);
      setClarificationState({
        jobId: job.jobId ?? job.id,
        question: job.clarificationQuestion ?? job.message ?? "Clarification needed before continuing.",
        reason: job.clarificationReason,
        options: job.clarificationOptions ?? [],
      });
      setError(null);
      return;
    }
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

  async function handleEditSubmit(maskDataUrl: string, editPrompt: string, clarificationNote?: string) {
    if (!editTarget) return;
    clarificationRetryRef.current = (note) => handleEditSubmit(maskDataUrl, editPrompt, note);
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
        clarificationNote,
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

  // ── Reference image helpers ──
  function addRefs(files: FileList | null) {
    if (!files) return;
    const fileArray = Array.from(files);

    // First file → auto-set as working image (if none pinned yet)
    if (!workingImage && fileArray.length > 0) {
      setWorkingImageFromFile(fileArray[0]);
      fileArray.splice(0, 1);
    }

    // Remaining → extra references
    if (fileArray.length > 0) {
      const next = fileArray.map((file) => ({
        id: `ref_${Math.random().toString(36).slice(2)}`,
        url: URL.createObjectURL(file),
        name: file.name,
        file,
      }));
      setRefPreviews((prev) => [...prev, ...next]);
    }
  }

  function removeRef(id: string) {
    setRefPreviews((prev) => {
      const item = prev.find((r) => r.id === id);
      if (item) URL.revokeObjectURL(item.url);
      return prev.filter((r) => r.id !== id);
    });
  }

  function addFlowAssets(flow: Exclude<CreateFlow, "free_create">, role: AssetRole, files: FileList | null) {
    if (!files) return;
    const nextItems: DraftAssetPreview[] = Array.from(files).map((file) => ({
      id: `${role}_${Math.random().toString(36).slice(2)}`,
      url: URL.createObjectURL(file),
      name: file.name,
      file,
      role,
    }));

    const setter = flow === "style_match" ? setStyleMatchAssets : setThemeCreateAssets;
    setter((prev) => ({
      ...prev,
      [role]: [...(prev[role] ?? []), ...nextItems],
    }));
  }

  function removeFlowAsset(flow: Exclude<CreateFlow, "free_create">, role: AssetRole, id: string) {
    const setter = flow === "style_match" ? setStyleMatchAssets : setThemeCreateAssets;
    setter((prev) => {
      const bucket = prev[role] ?? [];
      const target = bucket.find((item) => item.id === id);
      if (target) URL.revokeObjectURL(target.url);
      const nextBucket = bucket.filter((item) => item.id !== id);
      const next = { ...prev };
      if (nextBucket.length > 0) {
        next[role] = nextBucket;
      } else {
        delete next[role];
      }
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
  async function handleGenerate(clarificationNote?: string) {
    if (generating) return;

    // Effective sizes (for resize the checkbox grid already has endcard included if selected)
    const sizes = selectedSizes.length ? selectedSizes : DEFAULT_IMAGE_SIZES;

    clarificationRetryRef.current = (note) => handleGenerate(note);
    setGenerating(true);
    setError(null);
    setCurrentJobId(null);
    setLastPrompt(
      createFlow === "resize"
        ? `Resize to ${sizes.join(", ")}`
        : prompt.trim() || themeBrief.trim() || createFlow.replace("_", " ")
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
          const up = await uploadAsset(resizeSourceAsset.file, activeWorkspaceId, "upload");
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
        });
      }

      // ── FREE CREATE (Theme Create) ─────────────────────────────────────────
      else if (createFlow === "free_create") {
        const basePrompt = prompt.trim() || lastPrompt.trim();
        if (!basePrompt) {
          setGenerating(false);
          setError("Add a prompt to generate.");
          return;
        }

        const referenceIds: string[] = [];
        if (workingImage?.assetId) {
          referenceIds.push(workingImage.assetId);
        }
        for (const r of refPreviews) {
          const up = await uploadAsset(r.file, activeWorkspaceId, "upload");
          if (up) referenceIds.push(up.id);
        }

        response = await createImageGenerationJob({
          workspace_id: activeWorkspaceId,
          prompt: basePrompt,
          provider,
          model: modelId,
          variants,
          aspect_ratio: "multi-size",
          created_by: currentUser.id,
          source_asset_ids: [],
          theme: basePrompt.split(/\s+/).slice(0, 5).join(" "),
          output_sizes: sizes,
          output_format: format === "gif" ? "gif" : "image",
          reference_asset_ids: referenceIds,
          preserve_layout: false,
          use_reference_style: referenceIds.length > 0,
          client_asset_ids: [],
          thread_id: selectedThreadId ?? undefined,
          generation_mode: "free_create",
          clarification_note: clarificationNote,
        });
      } else if (createFlow === "style_match") {
        if (!hasRoleAssets(styleMatchAssets, "reference_ad")) {
          setGenerating(false);
          setError("Style Match requires at least one reference ad.");
          return;
        }
        if (!hasRoleAssets(styleMatchAssets, "client_logo")) {
          setGenerating(false);
          setError("Style Match requires a client logo.");
          return;
        }
        if (!hasRoleAssets(styleMatchAssets, "client_character") && !hasRoleAssets(styleMatchAssets, "client_product")) {
          setGenerating(false);
          setError("Style Match needs at least one client character or product asset.");
          return;
        }

        const uploaded = await uploadRoleBuckets(styleMatchAssets);
        const referenceIds = flattenUploaded(uploaded, ["reference_ad"]);
        const sourceIds = flattenUploaded(uploaded, ["client_logo", "client_product", "client_background", "brand_element"]);
        const clientIds = flattenUploaded(uploaded, ["client_character"]);
        const stylePrompt = [
          "Create a new ad set that matches the uploaded reference ad's composition, layout rhythm, and visual style.",
          "Use the uploaded client assets as the hero content.",
          "Keep the brand logo visible and legible in every requested size.",
          prompt.trim() ? `Additional direction: ${prompt.trim()}` : "",
        ].filter(Boolean).join(" ");

        response = await createImageGenerationJob({
          workspace_id: activeWorkspaceId,
          prompt: stylePrompt,
          provider,
          model: modelId,
          variants,
          aspect_ratio: "multi-size",
          created_by: currentUser.id,
          source_asset_ids: sourceIds,
          theme: "Style Match",
          output_sizes: sizes,
          output_format: format === "gif" ? "gif" : "image",
          reference_asset_ids: referenceIds,
          preserve_layout: false,
          use_reference_style: true,
          client_asset_ids: clientIds,
          thread_id: selectedThreadId ?? undefined,
          generation_mode: "style_match",
          clarification_note: clarificationNote,
        });
      } else {
        if (!themeBrief.trim()) {
          setGenerating(false);
          setError("Theme Create requires a theme brief.");
          return;
        }
        if (!hasRoleAssets(themeCreateAssets, "client_logo")) {
          setGenerating(false);
          setError("Theme Create requires a client logo.");
          return;
        }
        if (!hasRoleAssets(themeCreateAssets, "client_character") && !hasRoleAssets(themeCreateAssets, "client_product")) {
          setGenerating(false);
          setError("Theme Create needs at least one client character or product asset.");
          return;
        }

        const uploaded = await uploadRoleBuckets(themeCreateAssets);
        const sourceIds = flattenUploaded(uploaded, ["client_logo", "client_product", "client_background", "brand_element"]);
        const clientIds = flattenUploaded(uploaded, ["client_character"]);
        const themePrompt = [
          `Create a themed ad set for: ${themeBrief.trim()}.`,
          "Use the uploaded client assets as the fixed brand inputs.",
          "Keep the logo visible, preserve character identity, and adapt cleanly across all requested sizes.",
          prompt.trim() ? `Additional direction: ${prompt.trim()}` : "",
        ].filter(Boolean).join(" ");

        response = await createImageGenerationJob({
          workspace_id: activeWorkspaceId,
          prompt: themePrompt,
          provider,
          model: modelId,
          variants,
          aspect_ratio: "multi-size",
          created_by: currentUser.id,
          source_asset_ids: sourceIds,
          theme: themeBrief.trim(),
          output_sizes: sizes,
          output_format: format === "gif" ? "gif" : "image",
          reference_asset_ids: [],
          preserve_layout: false,
          use_reference_style: false,
          client_asset_ids: clientIds,
          thread_id: selectedThreadId ?? undefined,
          generation_mode: "theme_create",
          clarification_note: clarificationNote,
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
      const msg = err instanceof Error ? err.message : String(err);
      // "Failed to fetch" = server not running; HTTP errors = something else
      if (msg.toLowerCase().includes("fetch") || msg.toLowerCase().includes("network")) {
        setError("Cannot reach the API server. Run: cd services/api && uv run uvicorn app.main:app --reload --port 8000");
      } else if (msg.includes("400")) {
        setError(`Bad request (400) — check variants ≤ 3 and sizes ≤ 6. Detail: ${msg}`);
      } else if (msg.includes("401") || msg.includes("403")) {
        setError(`Auth error (${msg}). Check AUTH_MODE=dev and INCEPT_ADMIN_EMAILS in services/api/.env`);
      } else if (msg.includes("422")) {
        setError(`Validation error (422) — the API rejected the request body. Detail: ${msg}`);
      } else {
        setError(`Generation failed: ${msg}`);
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
      const previewAssets = assets.filter((asset) => isContactSheetPreview(asset));
      const displayAssets = previewAssets.length > 0 ? previewAssets : assets.filter((asset) => getContactSheetRole(asset) !== "sheet_source");
      return {
        id: jobId,
        threadId: assets[0]?.threadId ?? "",
        createdAt: assets[0]?.createdAt ?? new Date().toISOString(),
        assets: displayAssets.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()),
        title: liveJobMap.get(jobId)?.title ?? assets[0]?.theme ?? "Generation",
        promptText:
          (typeof assets[0]?.analysis?.source_prompt === "string" && assets[0]?.analysis?.source_prompt.trim())
            ? assets[0]?.analysis?.source_prompt.trim()
            : undefined,
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

  const styleMatchReady =
    hasRoleAssets(styleMatchAssets, "reference_ad") &&
    hasRoleAssets(styleMatchAssets, "client_logo") &&
    (hasRoleAssets(styleMatchAssets, "client_character") || hasRoleAssets(styleMatchAssets, "client_product"));

  const themeCreateReady =
    themeBrief.trim().length > 0 &&
    hasRoleAssets(themeCreateAssets, "client_logo") &&
    (hasRoleAssets(themeCreateAssets, "client_character") || hasRoleAssets(themeCreateAssets, "client_product"));

  const resizeReady = createFlow === "resize" && !!resizeSourceAsset && selectedSizes.length > 0;

  const canGenerate =
    !generating &&
    (
      createFlow === "resize"
        ? resizeReady
        : createFlow === "free_create"
        ? prompt.trim().length > 0
        : createFlow === "style_match"
        ? styleMatchReady
        : themeCreateReady
    );
  const activeRunningJob =
    (currentJobId ? liveJobs.find((j) => (j.jobId ?? j.id) === currentJobId) : null) ??
    liveJobs.find((j) => j.status === "running" || j.status === "pending") ??
    null;
  const isTaskRunning = generating || activeRunningJob?.status === "running" || activeRunningJob?.status === "pending";
  const taskProgress = activeRunningJob?.progress ?? (currentJobId ? 15 : 5);
  const taskMessage = activeRunningJob?.message ?? "";
  const taskStatusLabel = !currentJobId && !activeRunningJob
    ? "Starting"
    : taskProgress < 30
    ? "Planning"
    : taskProgress < 70
    ? "Generating sheet"
    : taskProgress < 95
    ? "Preparing previews"
    : "Finalizing sheets";

  async function handleClarificationChoice(option: ClarificationOption) {
    if (!clarificationRetryRef.current) {
      setClarificationState(null);
      return;
    }
    setClarificationSubmitting(true);
    setClarificationState(null);
    setError(null);
    try {
      await clarificationRetryRef.current(option.note ?? option.label);
    } catch (err) {
      setGenerating(false);
      setError(`Clarification retry failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setClarificationSubmitting(false);
    }
  }

  function dismissClarification() {
    setClarificationState(null);
    setCurrentJobId(null);
    setGenerating(false);
  }


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
                onSetWorking={setWorkingImageFromAsset}
                onRegenerate={() => setPrompt(jobEntry.promptText || jobEntry.title)}
                onHide={() => setHiddenJobIds((prev) => new Set([...prev, jobEntry.id]))}
                onZoom={setZoomedAsset}
                onSplit={(asset) => void handleSplitSheet(asset)}
                splittingAssetId={splittingAssetId}
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
      <div className="relative shrink-0 bg-background px-6 pb-6 pt-3">
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
                    {taskMessage || `${taskStatusLabel} image assets`}
                  </p>
                  <p className="truncate text-[11px] text-accent/70">
                    {lastPrompt || "Your generation is running"}
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
            className="rounded-2xl border border-border bg-card shadow-[0_2px_16px_rgba(0,0,0,0.06)] transition-shadow focus-within:shadow-[0_2px_20px_rgba(0,0,0,0.10)]"
          >

            {/* Task type tabs: Resize | Theme Create */}
            <div className="flex items-center gap-1 px-4 pt-3 pb-2 border-b border-border">
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
              {/* GIF addon — only shown in Resize mode */}
              {createFlow === "resize" && (
                <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                  <input
                    type="checkbox"
                    checked={includeGif}
                    onChange={(e) => setIncludeGif(e.target.checked)}
                    className="size-3.5 rounded accent-accent"
                  />
                  + GIF
                  <span className="text-[9px] text-muted-foreground/60">(banner + endcard)</span>
                </label>
              )}
            </div>

            {/* ── Resize: source image + size checkboxes ── */}
            {createFlow === "resize" && (
              <div className="border-t border-border px-4 py-3 space-y-3">
                {/* Source image upload */}
                <div>
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Source Image
                  </p>
                  {resizeSourceAsset ? (
                    <div className="flex items-center gap-3 rounded-xl border border-accent/40 bg-soft-accent/40 px-3 py-2">
                      <div className="size-10 shrink-0 overflow-hidden rounded-lg border border-accent/20">
                        <img src={resizeSourceAsset.url} alt="" className="h-full w-full object-cover" />
                      </div>
                      <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{resizeSourceAsset.name}</span>
                      <button type="button" onClick={() => setResizeSourceAsset(null)} className="text-muted-foreground hover:text-foreground">
                        <X className="size-4" />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => resizeFileRef.current?.click()}
                      className="flex w-full items-center gap-2 rounded-xl border border-dashed border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground transition-colors hover:border-accent/60 hover:text-foreground"
                    >
                      <ImageIcon className="size-4 shrink-0" />
                      Upload source image to resize
                    </button>
                  )}
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
                </div>

                {/* Size checkboxes grouped by family */}
                <div>
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Target Sizes
                  </p>
                  <div className="space-y-2">
                    {RESIZE_SIZE_GROUPS.map((group) => (
                      <div key={group.label}>
                        <p className="mb-1 text-[10px] font-semibold text-muted-foreground/70">{group.label}</p>
                        <div className="flex flex-wrap gap-1.5">
                          {group.sizes.map((sz) => {
                            const checked = selectedSizes.includes(sz);
                            return (
                              <label
                                key={sz}
                                className={cn(
                                  "flex cursor-pointer items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-all",
                                  checked
                                    ? "border-accent/50 bg-soft-accent text-accent"
                                    : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"
                                )}
                              >
                                <input
                                  type="checkbox"
                                  className="sr-only"
                                  checked={checked}
                                  onChange={(e) =>
                                    setSelectedSizes((prev) =>
                                      e.target.checked ? [...prev, sz] : prev.filter((s) => s !== sz)
                                    )
                                  }
                                />
                                {sz}
                                {includeGif && GIF_ALLOWED_SIZES.has(sz) && (
                                  <span className="ml-0.5 rounded bg-accent/20 px-0.5 text-[8px] font-bold text-accent">+GIF</span>
                                )}
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Endcard hint when any endcard size is selected */}
                {selectedSizes.some((s) => ENDCARD_SIZE_SET.has(s)) && (
                  <div className="rounded-xl border border-border bg-muted/20 px-3 py-2">
                    <p className="text-[10px] text-muted-foreground">
                      Endcard layout: Logo top · App Store + Google Play middle · CTA bottom
                    </p>
                  </div>
                )}
              </div>
            )}

            {createFlow === "style_match" && (
              <div className="grid gap-3 border-t border-border px-4 py-3 md:grid-cols-2">
                {STYLE_MATCH_ROLES.map((bucket) => (
                  <AssetBucketUploader
                    key={bucket.role}
                    title={bucket.title}
                    hint={bucket.hint}
                    role={bucket.role}
                    required={bucket.required}
                    files={styleMatchAssets[bucket.role] ?? []}
                    onAdd={(role, files) => addFlowAssets("style_match", role, files)}
                    onRemove={(role, id) => removeFlowAsset("style_match", role, id)}
                  />
                ))}
              </div>
            )}

            {createFlow === "theme_create" && (
              <div className="border-t border-border px-4 py-3">
                <div className="mb-3 rounded-xl border border-border bg-background/60 p-3">
                  <p className="text-sm font-medium text-foreground">Theme Brief</p>
                  <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                    Describe the campaign theme we should build around, for example `World Cup 2026`, `Summer Sale`, or `Anniversary Event`.
                  </p>
                  <input
                    value={themeBrief}
                    onChange={(e) => setThemeBrief(e.target.value)}
                    placeholder="World Cup 2026"
                    className="mt-3 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-accent/60"
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {THEME_CREATE_ROLES.map((bucket) => (
                    <AssetBucketUploader
                      key={bucket.role}
                      title={bucket.title}
                      hint={bucket.hint}
                      role={bucket.role}
                      required={bucket.required}
                      files={themeCreateAssets[bucket.role] ?? []}
                      onAdd={(role, files) => addFlowAssets("theme_create", role, files)}
                      onRemove={(role, id) => removeFlowAsset("theme_create", role, id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* ── Working image pinned bar ── */}
            {createFlow === "free_create" && workingImage && (
              <div className="mx-4 mb-2 overflow-hidden rounded-xl border border-accent/30 bg-soft-accent/50">
                {/* Main row */}
                <div className="flex items-center gap-2.5 px-3 py-2">
                  {/* Thumbnail */}
                  <div className="size-9 shrink-0 overflow-hidden rounded-lg border border-accent/20">
                    <img src={workingImage.url} alt="" className="h-full w-full object-cover" />
                  </div>
                  {/* Label */}
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-semibold text-accent">Working image</p>
                    <p className="truncate text-[10px] text-accent/70">
                      {workingImage.label}
                      {!workingImage.assetId && " · uploading…"}
                    </p>
                  </div>
                  {/* Clear */}
                  <button
                    type="button"
                    onClick={() => { setWorkingImage(null); setActiveOp(null); }}
                    className="shrink-0 rounded-md p-1 text-accent/60 hover:bg-accent/15 hover:text-accent"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>

                {/* Outpaint panel */}
                {false && activeOp === "outpaint" && (
                  <div className="border-t border-accent/20 px-3 py-2">
                    <p className="mb-1.5 text-[10px] font-medium text-accent/70">Expand direction</p>
                    <div className="flex items-center gap-2">
                      <div className="flex gap-1">
                        {(["↑ Top","← Left","All","Right →","↓ Bot"] as const).map((lbl, i) => {
                          const dirs = ["top","left","all","right","bottom"] as const;
                          const d = dirs[i];
                          return (
                            <button key={d} type="button" onClick={() => setOutpaintDir(d)}
                              className={cn("rounded-md px-2 py-1 text-[10px] font-medium transition-colors",
                                outpaintDir === d ? "bg-accent text-white" : "border border-accent/30 text-accent hover:bg-accent/10"
                              )}>
                              {lbl}
                            </button>
                          );
                        })}
                      </div>
                      <input type="range" min="10" max="70" value={Math.round(outpaintRatio * 100)}
                        onChange={(e) => setOutpaintRatio(Number(e.target.value) / 100)}
                        className="flex-1 accent-accent" />
                      <span className="text-[10px] text-accent/70">{Math.round(outpaintRatio * 100)}%</span>
                      <button type="button" onClick={() => void handleOutpaint()}
                        disabled={!workingImage?.assetId || generating}
                        className="rounded-lg bg-accent px-3 py-1.5 text-[11px] font-semibold text-white hover:opacity-80 disabled:opacity-40">
                        Expand
                      </button>
                    </div>
                  </div>
                )}

                {/* Add text panel */}
                {false && activeOp === "text" && (
                  <div className="border-t border-accent/20 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <input value={textInput} onChange={(e) => setTextInput(e.target.value)}
                        placeholder="Text to overlay…"
                        className="min-w-0 flex-1 rounded-lg border border-accent/30 bg-white/60 px-3 py-1.5 text-sm outline-none focus:border-accent/60" />
                      <select value={textPosition} onChange={(e) => setTextPosition(e.target.value as "top"|"center"|"bottom")}
                        className="rounded-lg border border-accent/30 bg-white/60 px-2 py-1.5 text-xs outline-none">
                        <option value="top">Top</option>
                        <option value="center">Center</option>
                        <option value="bottom">Bottom</option>
                      </select>
                      <button type="button" onClick={() => void handleAddText()}
                        disabled={!textInput.trim() || !workingImage?.assetId || generating}
                        className="rounded-lg bg-accent px-3 py-1.5 text-[11px] font-semibold text-white hover:opacity-80 disabled:opacity-40">
                        Apply
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Reference image thumbnails — compact chips shown above textarea */}
            {createFlow === "free_create" && refPreviews.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-4 pb-1 pt-0">
                {refPreviews.map((r) => (
                  <div
                    key={r.id}
                    className="group relative size-10 shrink-0 overflow-hidden rounded-lg border border-border"
                  >
                    <img src={r.url} alt={r.name} className="h-full w-full object-cover" />
                    <button
                      type="button"
                      onClick={() => removeRef(r.id)}
                      className="absolute inset-0 hidden items-center justify-center rounded-lg bg-black/60 group-hover:flex"
                    >
                      <X className="size-3 text-white" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="sr-only"
              onChange={(e) => { addRefs(e.target.files); e.target.value = ""; }}
            />

            {/* Textarea */}
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && canGenerate) {
                  e.preventDefault();
                  handleGenerate();
                }
              }}
              placeholder={
                createFlow === "free_create" && workingImage
                  ? "Describe what to change in the working image…"
                  : createFlow === "style_match"
                  ? "Optional direction for matching the reference ad…"
                  : createFlow === "theme_create"
                  ? "Optional art direction, copy notes, or campaign constraints…"
                  : mode === "image"
                  ? "Describe the image you want to generate…"
                  : "Describe your endcard creative…"
              }
              rows={3}
              className="w-full resize-none bg-transparent px-4 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground"
            />

            {/* ── Chip row ── */}
            <div className="flex items-center gap-1.5 px-4 pb-3 pt-1">

              {/* Model chip */}
              <div className="relative">
                <ChipButton
                  label="Model"
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

              {/* Sizes / Format / Variants chips — hidden in Resize mode (handled by checkbox grid) */}
              {/* Sizes chip */}
              <div className={cn("relative", createFlow === "resize" && "hidden")}>
                <ChipButton
                  label="Size"
                  active={activeChip === "sizes"}
                  onClick={() => toggleChip("sizes")}
                />
                {activeChip === "sizes" && (
                  <DropdownPanel className="left-0 w-52">
                    <DropdownLabel>
                      Sizes — {selectedSizes.length} selected
                    </DropdownLabel>
                    {(mode === "endcard" ? ENDCARD_SIZES.map(s => ({ id: s.id, display: `${s.id} · ${s.label}` })) : IMAGE_SIZES.map(s => ({ id: s, display: s }))).map(({ id, display }) => (
                      <DropdownItem
                        key={id}
                        label={display}
                        selected={selectedSizes.includes(id)}
                        onClick={() =>
                          setSelectedSizes((cur) =>
                            cur.includes(id)
                              ? cur.filter((x) => x !== id)
                              : [...cur, id]
                          )
                        }
                      />
                    ))}
                  </DropdownPanel>
                )}
              </div>

              {/* Format chip */}
              <div className={cn("relative", createFlow === "resize" && "hidden")}>
                <ChipButton
                  label="Format"
                  active={activeChip === "format"}
                  onClick={() => toggleChip("format")}
                />
                {activeChip === "format" && (
                  <DropdownPanel className="left-0 w-44">
                    <DropdownLabel>Format</DropdownLabel>
                    <DropdownItem
                      label="Static"
                      sub="PNG · ready to serve"
                      selected={format === "static"}
                      onClick={() => { setFormat("static"); setActiveChip(null); }}
                    />
                    <DropdownItem
                      label="GIF"
                      sub="Animated loop"
                      selected={format === "gif"}
                      onClick={() => { setFormat("gif"); setActiveChip(null); }}
                    />
                  </DropdownPanel>
                )}
              </div>

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
                    {([1, 2, 3] as const).map((n) => (
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
                {/* Attachment icon — opens file picker */}
                <button
                  type="button"
                  title={createFlow === "free_create" ? "Attach reference images" : "Reference upload is above"}
                  onClick={() => {
                    if (createFlow === "free_create") fileInputRef.current?.click();
                  }}
                  disabled={createFlow !== "free_create"}
                  className={cn(
                    "relative flex size-8 items-center justify-center rounded-full transition-colors",
                    createFlow !== "free_create"
                      ? "cursor-not-allowed text-muted-foreground/40"
                      : refPreviews.length > 0
                      ? "bg-soft-accent text-accent"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <Paperclip className="size-4" />
                  {createFlow === "free_create" && refPreviews.length > 0 && (
                    <span className="absolute -right-0.5 -top-0.5 flex size-3.5 items-center justify-center rounded-full bg-accent text-[8px] font-bold text-white">
                      {refPreviews.length}
                    </span>
                  )}
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

            </div>
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
                        onClick={() => toggleAsset(asset.id)}
                        className={cn(
                          "absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full border-2 transition-all",
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
              {downloading ? "Preparing…" : selectedAssetIds.size === 0 ? "Select to download" : `Download ${selectedAssetIds.size}`}
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
      <ZoomModal asset={zoomedAsset} onClose={() => setZoomedAsset(null)} />
    )}

    {/* ── Inpainting canvas modal ── */}
    {clarificationState && (
      <div className="fixed inset-0 z-[72] flex items-center justify-center bg-black/65 p-6">
        <div className="w-full max-w-xl rounded-3xl border border-border bg-card p-6 shadow-2xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">
                Clarification Needed
              </p>
              <h3 className="mt-2 text-xl font-semibold text-foreground">
                Choose what to preserve first
              </h3>
            </div>
            <button
              type="button"
              onClick={dismissClarification}
              className="rounded-full border border-border p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            {clarificationState.question}
          </p>
          {clarificationState.options.length > 0 ? (
            <div className="mt-5 space-y-3">
              {clarificationState.options.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => void handleClarificationChoice(option)}
                  disabled={clarificationSubmitting}
                  className="w-full rounded-2xl border border-border bg-background px-4 py-3 text-left transition-colors hover:border-foreground/20 hover:bg-muted/40 disabled:opacity-60"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold text-foreground">{option.label}</span>
                    {clarificationSubmitting && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
                  </div>
                  {option.note && (
                    <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{option.note}</p>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <div className="mt-5 rounded-2xl border border-dashed border-border bg-background/70 px-4 py-4 text-sm text-muted-foreground">
              This request needs a more specific instruction before we continue.
            </div>
          )}
          <div className="mt-6 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={dismissClarification}
              className="rounded-xl border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    )}

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
