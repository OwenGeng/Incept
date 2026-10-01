"use client";

import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type DragEvent,
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
import type { AssetRole, AssetSummary, CreativeThreadSummary, LinglongLabUser, JobSummary, RemediationAnalysisResult, ThemeCreatePresetSummary } from "@linglonglab/shared";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { addTextToImage, analyzeRemediationAssets, cancelJob, createImageGenerationJob, createKakaoBizboardJob, createThemeCreatePreset, createThemeCreateReport, deleteAssets, deleteThread, downloadAssetFile, downloadAssetsZip, draftThemeCreateReport, generateGifFromAsset, getAssetFileExtension, listAssets, listThemeCreatePresets, listThreads, outpaintImage, removeBackground, renameThread, uploadAsset, type ContentScope } from "@/lib/incept-api";
import {
  composeKakaoBizboard,
  KAKAO_BIZBOARD_SIZE,
  KAKAO_DEFAULT_APP_COPY,
  KAKAO_DEFAULT_MAIN_COPY,
  KAKAO_DEFAULT_TEMPLATE,
  KAKAO_GACHA_INFO,
  KAKAO_TEMPLATES,
  kakaoTemplate,
  loadKakaoFonts,
  validateKakaoBizboardInputs,
  type KakaoCompositeParams,
  type KakaoTemplateId,
} from "@/lib/kakao-compositor";
import { DocsButton, FeedbackButton } from "@/components/incept/FeedbackButton";
import { KakaoFlow } from "@/components/incept/KakaoFlow";
import { useKakaoObjectImages } from "@/components/incept/useKakaoObjectImages";
import { WorkbenchShell } from "@/components/incept/WorkbenchShell";
import { WorkbenchFooterActions } from "@/components/incept/WorkbenchFooterActions";

// Types

type CreativeMode = "image" | "endcard";
type OutputFormat = "static" | "gif";
type ProviderId = "openai" | "gemini";
type ActiveChip = "model" | "sizes" | "format" | "variants" | "presets" | null;
type CreateFlow = "resize" | "theme_create" | "kakao" | "remediation";
type DraftAssetPreview = { id: string; url: string; name: string; file?: File; role: AssetRole };
type ResizeSourceAsset = {
  id: string | null;
  url: string;
  name: string;
  file?: File;
  width?: number;
  height?: number;
};
type AssetBucketState = Partial<Record<AssetRole, DraftAssetPreview[]>>;
type ThemeCreateMode = "style_modify" | "style_transfer";

// Constants

// Size definitions

// Sizes grouped by family for the Resize task UI (endcard included as 4th group)
const RESIZE_SIZE_GROUPS = [
  { label: "Banner",           sizes: ["320x50", "728x90", "1200x222", "640x100"] },
  { label: "Landscape",        sizes: ["1200x628", "1200x600", "1920x1080"] },
  { label: "Portrait / Square",sizes: ["320x480", "300x250", "720x720"] },
  { label: "Endcard",          sizes: ["360x640", "1080x1920", "480x480", "640x360"] },
] as const;

const RESIZE_SIZE_ORDER = RESIZE_SIZE_GROUPS.flatMap((group) => group.sizes);
const RESIZE_GACHA_DISCLOSURE_SIZES = new Set(["1200x628", "1200x600"]);

const ENDCARD_SIZE_SET = new Set(["360x640", "1080x1920", "480x480", "640x360", "1920x1080"]);

const IMAGE_SIZES = [
  "1200x628", "320x480", "300x250",
  "720x720", "1200x600", "1920x1080", "360x640", "1080x1920", "480x480", "640x360",
];

// GIF supported for medium + endcard sizes
const GIF_ALLOWED_SIZES = new Set([
  "300x250",                       // medium
  "320x480",                       // portrait
  "360x640", "480x480", "640x360", // endcard
]);

const ENDCARD_SIZES = [
  { id: "360x640", label: "Portrait 9:16" },
  { id: "1080x1920", label: "Portrait 9:16 HD" },
  { id: "640x360", label: "Landscape 16:9" },
  { id: "1920x1080", label: "Landscape 16:9 HD" },
  { id: "480x480", label: "Square 1:1" },
];
const ENDCARD_SIZE_IDS = ENDCARD_SIZES.map((s) => s.id);
const DEFAULT_IMAGE_SIZES: string[] = [];
const MAX_RESIZE_SOURCE_IMAGES = 10;
const MAX_REMEDIATION_SOURCE_IMAGES = 10;

// Create flow tabs

const CREATE_FLOW_TABS: Array<{ id: CreateFlow; label: string; blurb: string }> = [
  { id: "resize",       label: "Resize",       blurb: "Adapt one image to multiple ad sizes. Background and style stay identical." },
  { id: "theme_create", label: "Theme Create", blurb: "Run one of two Gemini image workflows, then turn strong outputs into reusable style presets." },
  { id: "kakao",        label: "Kakao",        blurb: "Batch-generate Kakao Bizboard banners (960x300) from your ad creatives." },
  { id: "remediation",  label: "Remediation",  blurb: "Upload risky creatives and generate safer variants without losing the core campaign idea." },
];

const THEME_CREATE_MODES: Array<{ id: ThemeCreateMode; label: string; blurb: string }> = [
  { id: "style_modify", label: "Style Modify", blurb: "Keep the exact layout of one source image and transform its artistic style." },
  { id: "style_transfer", label: "Style Transfer", blurb: "Use Image 1 for content and Image 2 only for visual style DNA." },
];

// Keep Theme Create on Gemini-native aspect ratios. The generated image is
// exported at this exact size; arbitrary ad dimensions belong in Resize.
const THEME_CREATE_SIZES = [
  { id: "1920x1080", label: "Landscape 16:9 · 1920×1080" },
  { id: "1080x1920", label: "Portrait 9:16 · 1080×1920" },
] as const;
const THEME_CREATE_SIZE_IDS = THEME_CREATE_SIZES.map((size) => size.id);

const THEME_CREATE_WORLD_CUP_2026_PROMPT = `You are modifying [Image 1] to fit the global "2026 FIFA World Cup Tournament" premium broadcast campaign aesthetic.

Instructions:
1. Keep the exact layout, subject placement, and core structure of [Image 1] completely intact.
2. Transform the background into a magnificent, packed modern football stadium at night under dramatic, high-intensity stadium floodlights.
3. Apply a vibrant, high-contrast color scheme: dominant pitch-grass greens, deep championship golds, and atmospheric dark stadium-night blues.
4. Add dynamic, high-energy overlay elements: sharp motion-blur lighting streaks, flying stadium turf particles, and a subtle rain of golden celebration confetti in the atmosphere.
5. Enhance the main subjects from [Image 1] with dramatic rim lighting (backlighting) from the stadium lights to make them pop out. The final image must look like an official, high-stakes sports betting or championship broadcast graphic.`;

const SHOW_THEME_CREATE_PRESET_CHIP = false;

// Flat list of supported models, with provider shown as sub-text prefix
const ALL_MODELS: Array<{
  id: string;
  provider: ProviderId;
  short: string;
  sub: string;
}> = [
  { id: "gemini-3.1-flash-image", provider: "gemini", short: "Gemini 3.1 Flash", sub: "Google - Fastest" },
  { id: "gpt-image-2",            provider: "openai", short: "GPT Image 2",      sub: "OpenAI - Latest" },
];

// Props

export interface CreateImageViewProps {
  liveAssets: AssetSummary[];
  setLiveAssets: Dispatch<SetStateAction<AssetSummary[]>>;
  liveJobs: JobSummary[];
  setLiveJobs: Dispatch<SetStateAction<JobSummary[]>>;
  liveThreads: CreativeThreadSummary[];
  setLiveThreads: Dispatch<SetStateAction<CreativeThreadSummary[]>>;
  currentUser: LinglongLabUser;
  contentScope: ContentScope;
  activeWorkspaceId: string;
  activeThreadId?: string | null;
  initialResizeAssetIds?: string[];
  onThreadSelect?: (id: string | null) => void;
  onJobCreated: (job: JobSummary) => void;
}

// Helpers

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
  if (mode === "remediation") return "Remediation";
  return "Free Create";
}

async function getImageDimensionsFromFile(file: File): Promise<{ width: number; height: number } | null> {
  const objectUrl = URL.createObjectURL(file);
  try {
    const dimensions = await new Promise<{ width: number; height: number } | null>((resolve) => {
      const image = new Image();
      image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
      image.onerror = () => resolve(null);
      image.src = objectUrl;
    });
    return dimensions;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function buildSizeLabel(width?: number, height?: number): string | null {
  if (!width || !height) return null;
  return `${width}x${height}`;
}

// Dropdown panel shared wrapper
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

function buildThemeCreatePresetName(mode: ThemeCreateMode, styleName: string, promptValue: string) {
  const normalizedStyleName = styleName.trim();
  if (normalizedStyleName) return normalizedStyleName;
  const normalizedPrompt = promptValue.trim();
  if (!normalizedPrompt) {
    return mode === "style_modify" ? "Style Modify Preset" : "Style Transfer Preset";
  }
  return normalizedPrompt.split("\n")[0]?.trim().slice(0, 80) || (mode === "style_modify" ? "Style Modify Preset" : "Style Transfer Preset");
}

function buildThemeCreatePresetSummary(mode: ThemeCreateMode, styleDetails: string, promptValue: string) {
  const normalizedStyleDetails = styleDetails.trim();
  if (normalizedStyleDetails) return normalizedStyleDetails;
  const normalizedPrompt = promptValue.replace(/\s+/g, " ").trim();
  if (!normalizedPrompt) {
    return mode === "style_modify"
      ? "Reusable style-modification preset captured from a successful Theme Create run."
      : "Reusable style-transfer preset captured from a successful Theme Create run.";
  }
  return normalizedPrompt.slice(0, 180);
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
  onPreview,
  required,
  onDropFiles,
}: {
  title: string;
  hint: string;
  file: DraftAssetPreview | null;
  onPick: (file: File | null) => void;
  onClear: () => void;
  onPreview?: (file: DraftAssetPreview) => void;
  required?: boolean;
  onDropFiles?: (files: FileList | File[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  return (
    <div
      className={cn(
        "rounded-xl border bg-background/60 p-3 transition-colors",
        isDragOver ? "border-accent bg-soft-accent/10" : "border-border"
      )}
      onDragOver={(event) => {
        if (!onDropFiles || !Array.from(event.dataTransfer.types).includes("Files")) return;
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = "copy";
        setIsDragOver(true);
      }}
      onDragLeave={(event) => {
        if (!onDropFiles) return;
        event.preventDefault();
        event.stopPropagation();
        const related = event.relatedTarget as Node | null;
        if (related && event.currentTarget.contains(related)) return;
        setIsDragOver(false);
      }}
      onDrop={(event) => {
        if (!onDropFiles) return;
        event.preventDefault();
        event.stopPropagation();
        setIsDragOver(false);
        onDropFiles(event.dataTransfer.files);
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-foreground">{title}</p>
            {required && <Badge variant="secondary" className="text-[10px]">Required</Badge>}
          </div>
          {hint ? <p className="mt-1 text-[11px] leading-5 text-muted-foreground">{hint}</p> : null}
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
          <button
            type="button"
            onClick={() => onPreview?.(file)}
            className="size-12 shrink-0 overflow-hidden rounded-lg border border-border bg-[#07111F] transition-transform hover:scale-[1.02]"
            title="Preview image"
          >
            <img src={file.url} alt={file.name} className="h-full w-full object-cover" />
          </button>
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

function ThemeDraftPreviewModal({
  file,
  onClose,
}: {
  file: DraftAssetPreview;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[75] flex items-center justify-center bg-black/85 p-4"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[92vh] max-w-[92vw] flex-col overflow-hidden rounded-2xl bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <p className="truncate text-xs font-semibold text-foreground">{file.name}</p>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-[#07111F]">
          <img
            src={file.url}
            alt={file.name}
            className="block max-h-[80vh] max-w-[90vw] object-contain"
          />
        </div>
      </div>
    </div>
  );
}

// Chip button

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

// Image zoom modal

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

  const fmt = getAssetFileExtension(asset).toUpperCase();
  const label = asset.width && asset.height
    ? `${asset.width}x${asset.height} - ${fmt}`
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
          {asset.type === "video" ? (
            <video
              src={asset.url}
              controls
              playsInline
              className="block max-h-[80vh] max-w-[90vw] object-contain"
            />
          ) : (
            <img
              src={asset.url}
              alt={asset.title}
              className="block max-h-[80vh] max-w-[90vw] object-contain"
            />
          )}
        </div>
      </div>
    </div>
  );
}

// Generation card: 3-column image grid, prompt, and action buttons

type KakaoBuilderAsset = {
  id: string;
  url: string;
  title?: string;
  type: "image" | "video" | "audio" | "gif" | "report" | "playable";
  threadId?: string | null;
};

export function KakaoBatchModal({
  assets,
  submitting,
  template,
  appIconUrl,
  appCopy,
  mainCopy,
  subCopy,
  additionalInfo,
  gacha,
  previewUrl,
  validationErrors,
  mainCopyWidthPx,
  onClose,
  onSubmit,
  onTemplateChange,
  onAppIconChange,
  setGacha,
  onAppCopyChange,
  onMainCopyChange,
  onSubCopyChange,
  onAdditionalInfoChange,
  onApplyChanges,
  previewBusy,
  previewAssetIndex,
  onPreviewAssetChange,
  objectUrl,
  objectBusy,
  objectError,
  onRemoveBackgrounds,
  onUploadObject,
}: {
  assets: KakaoBuilderAsset[];
  submitting: boolean;
  template: KakaoTemplateId;
  appIconUrl: string | null;
  appCopy: string;
  mainCopy: string;
  subCopy: string;
  additionalInfo: string;
  gacha: boolean;
  previewUrl: string | null;
  validationErrors: string[];
  mainCopyWidthPx: number;
  onClose: () => void;
  onSubmit: () => void;
  onTemplateChange: (value: KakaoTemplateId) => void;
  onAppIconChange: (file: File | null) => void;
  setGacha: Dispatch<SetStateAction<boolean>>;
  onAppCopyChange: (value: string) => void;
  onMainCopyChange: (value: string) => void;
  onSubCopyChange: (value: string) => void;
  onAdditionalInfoChange: (value: string) => void;
  onApplyChanges: () => void;
  previewBusy: boolean;
  previewAssetIndex: number;
  onPreviewAssetChange: (assetIndex: number) => void;
  /** Object image used for the previewed source (Object template only). */
  objectUrl: string | null;
  objectBusy: boolean;
  objectError: string | null;
  onRemoveBackgrounds: () => void;
  onUploadObject: (file: File) => void;
}) {
  const firstAsset = assets[0] ?? null;
  const currentPreviewAsset = assets[previewAssetIndex] ?? firstAsset ?? null;
  const [showGuideline, setShowGuideline] = useState(true);
  const [showGrid, setShowGrid] = useState(false);
  const templateSpec = kakaoTemplate(template);
  const inputsReady = !!firstAsset && (!templateSpec.appCopy || !!appIconUrl);
  const canCreate = !submitting && !objectBusy && validationErrors.length === 0 && inputsReady;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-black/80 p-4 md:items-center"
      aria-modal="true"
      role="dialog"
    >
      <div
        className="my-4 grid h-[calc(100vh-2rem)] max-h-[900px] w-full max-w-6xl gap-0 overflow-hidden rounded-3xl border border-border bg-white shadow-2xl lg:grid-cols-[minmax(0,1fr)_305px]"
      >
        <div className="flex min-h-0 flex-col bg-muted/25">
          <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
            <div>
              <p className="text-sm font-semibold text-foreground">Kakao Bizboard Batch</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {assets.length === 1 ? "1 cleaned image selected" : `${assets.length} cleaned images selected`}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <X className="size-4" />
            </button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
            <div className="flex flex-wrap items-center gap-6">
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={showGuideline}
                  onChange={(e) => setShowGuideline(e.target.checked)}
                  className="size-4 rounded border-border bg-transparent"
                />
                Guidelines
              </label>
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={showGrid}
                  onChange={(e) => setShowGrid(e.target.checked)}
                  className="size-4 rounded border-border bg-transparent"
                />
                Grid background
              </label>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-foreground">Selected Sources</p>
                <p className="text-xs text-muted-foreground">{assets.length} / 10 selected</p>
              </div>
              <p className="text-xs text-muted-foreground">
                One template and copy setting will be applied across all selected cleaned images.
                Click a thumbnail to preview that source in the Bizboard frame.
              </p>
              <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:thin]">
                {assets.map((asset, index) => {
                  const selected = currentPreviewAsset === asset;
                  return (
                    <button
                      key={asset.id}
                      type="button"
                      onClick={() => onPreviewAssetChange(index)}
                      className={cn(
                        "group relative w-28 shrink-0 overflow-hidden rounded-2xl border-2 bg-white text-left transition-all",
                        selected
                          ? "border-accent shadow-[0_0_0_1px_hsl(var(--accent)/0.18)]"
                          : "border-border hover:border-foreground/20"
                      )}
                    >
                      <div className="aspect-[4/3] bg-white">
                        {asset.type === "video" ? (
                          <video
                            src={asset.url}
                            className="h-full w-full object-cover"
                            muted
                            playsInline
                            preload="metadata"
                          />
                        ) : (
                          <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" />
                        )}
                      </div>
                      <div className="border-t border-border bg-card px-2 py-2">
                        <p className="truncate text-[11px] font-medium text-foreground">
                          {asset.title || `Source ${index + 1}`}
                        </p>
                        <p className="mt-0.5 text-[10px] text-muted-foreground">
                          {selected ? "Previewing" : `Source ${index + 1}`}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {showGuideline && (
              <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-xs text-sky-900">
                Kakao 960x300 spec: copy must stay between the red and blue guides (max 526px); the thumbnail sits at the right (320x222). Kakao adds the AD mark automatically, so no disclaimer is needed.
              </div>
            )}

            <div className="flex justify-center">
              <div className="relative w-full max-w-[760px] overflow-hidden bg-white">
                {showGrid && (
                  <div
                    aria-hidden
                    className="absolute inset-0 opacity-30"
                    style={{
                      backgroundSize: "10px, 30px, 10px 10px, 30px 30px",
                      backgroundImage:
                        "linear-gradient(90deg, #00111111 1px, transparent 1px), linear-gradient(90deg, #00111111 1px, transparent 1px), linear-gradient(#00111111 1px, transparent 1px), linear-gradient(#00111111 1px, transparent 1px)",
                    }}
                  />
                )}
                {previewBusy ? (
                  <div className="grid aspect-[960/300] place-items-center border border-dashed border-border bg-background">
                    <Loader2 className="size-5 animate-spin text-muted-foreground" />
                  </div>
                ) : previewUrl ? (
                  <img src={previewUrl} alt="Kakao Bizboard preview" className="relative block w-full bg-[#f3f3f3]" />
                ) : currentPreviewAsset ? (
                  <div className="grid aspect-[960/300] place-items-center border border-dashed border-border bg-background text-sm text-muted-foreground">
                    Apply changes to generate the Kakao preview.
                  </div>
                ) : (
                  <div className="grid aspect-[960/300] place-items-center border border-dashed border-border bg-background text-sm text-muted-foreground">
                    Select cleaned assets first.
                  </div>
                )}
                {showGuideline && (
                  // Copy area x=43..569 of 960 (Kakao 960x300 layout).
                  <div className="pointer-events-none absolute inset-0">
                    <div className="ml-[4.48%] h-full w-[54.79%] border-l border-dashed border-red-500 border-r border-dashed border-blue-500" />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="flex min-h-0 flex-col border-l border-border bg-white">
          <div className="border-b border-border px-5 py-4">
            <p className="text-sm font-semibold text-foreground">Image Settings</p>
          </div>

          <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto p-4 pr-3">
            <label className="grid gap-2">
              <span className="text-xs font-medium text-muted-foreground">Template</span>
              <select
                value={template}
                onChange={(e) => onTemplateChange(e.target.value as KakaoTemplateId)}
                className="rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-foreground/20"
              >
                {KAKAO_TEMPLATES.map((option) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
            </label>

            {templateSpec.object && (
              <div className="grid gap-2">
                <span className="text-xs font-medium text-muted-foreground">Object Image</span>
                <div
                  className="grid aspect-[314/300] place-items-center overflow-hidden rounded-md border border-border"
                  style={{ backgroundImage: "repeating-conic-gradient(#eee 0% 25%, #fff 0% 50%)", backgroundSize: "16px 16px" }}
                >
                  {objectUrl ? (
                    <img src={objectUrl} alt="Object image" className="max-h-full max-w-full object-contain" />
                  ) : (
                    <ImageIcon className="size-5 text-muted-foreground/50" />
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={onRemoveBackgrounds}
                    disabled={objectBusy || !firstAsset}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {objectBusy && <Loader2 className="size-3.5 animate-spin" />}
                    {objectBusy ? "Removing…" : `Remove background (${assets.length})`}
                  </button>
                  <label className="cursor-pointer rounded-md border border-border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted">
                    Upload transparent PNG
                    <input
                      type="file"
                      accept="image/png"
                      className="sr-only"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) onUploadObject(file);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
                <span className="text-[11px] text-muted-foreground">
                  Background-free object, no text. Scaled to 314px wide; taller than 300px is cropped top and bottom. Upload applies to the source being previewed.
                </span>
                {objectError && <span className="text-[11px] text-red-600">{objectError}</span>}
              </div>
            )}

            {templateSpec.appCopy && <div className="grid gap-4">
              <label className="grid gap-2">
                <span className="text-xs font-medium text-muted-foreground">App Icon</span>
                <div className="flex items-center gap-3 rounded-md border border-border bg-background px-2 py-2">
                  <div className="grid size-[54px] shrink-0 place-items-center overflow-hidden border border-border bg-white">
                    {appIconUrl ? (
                      <img src={appIconUrl} alt="App icon" className="h-full w-full object-contain" />
                    ) : (
                      <ImageIcon className="size-5 text-muted-foreground/50" />
                    )}
                  </div>
                  <label className="cursor-pointer rounded-md border border-border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted">
                    Upload Icon
                    <input
                      type="file"
                      accept="image/*"
                      className="sr-only"
                      onChange={(e) => onAppIconChange(e.target.files?.[0] ?? null)}
                    />
                  </label>
                </div>
              </label>
            </div>}

            <div className="grid gap-2">
              <span className="text-xs font-medium text-muted-foreground">Current Preview Source</span>
              {currentPreviewAsset ? (
                <div className="overflow-hidden border border-border bg-white">
                  <div className="aspect-[4/3]">
                    {currentPreviewAsset.type === "video" ? (
                      <video
                        src={currentPreviewAsset.url}
                        className="h-full w-full object-cover"
                        muted
                        playsInline
                        preload="metadata"
                      />
                    ) : (
                      <img
                        src={currentPreviewAsset.url}
                        alt={currentPreviewAsset.title}
                        className="h-full w-full object-contain bg-white"
                      />
                    )}
                  </div>
                  <div className="px-2 py-2">
                    <p className="truncate text-[11px] font-medium text-foreground">{currentPreviewAsset.title}</p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">This source is currently shown in the preview.</p>
                  </div>
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">
                  No selected source.
                </div>
              )}
            </div>

            {templateSpec.appCopy && (
              <label className="grid gap-2">
                <span className="text-xs font-medium text-muted-foreground">App Download Copy</span>
                <input
                  value={appCopy}
                  onChange={(e) => onAppCopyChange(e.target.value)}
                  placeholder={KAKAO_DEFAULT_APP_COPY}
                  className="rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-foreground/20"
                />
                <span className="text-[11px] text-muted-foreground">Must include &quot;앱&quot; or &quot;App&quot;.</span>
              </label>
            )}

            <label className="grid gap-2">
              <span className="text-xs font-medium text-muted-foreground">Main Copy</span>
              <input
                value={mainCopy}
                onChange={(e) => onMainCopyChange(e.target.value)}
                placeholder={KAKAO_DEFAULT_MAIN_COPY}
                className="rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-foreground/20"
              />
              <span className="text-[11px] text-muted-foreground">Width: {Math.round(mainCopyWidthPx)}px (240–526px)</span>
            </label>

            {templateSpec.subCopy && (
              <label className="grid gap-2">
                <span className="text-xs font-medium text-muted-foreground">Sub Copy</span>
                <input
                  value={subCopy}
                  onChange={(e) => onSubCopyChange(e.target.value)}
                  className="rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-foreground/20"
                />
                <span className="text-[11px] text-muted-foreground">Must differ from the main copy.</span>
              </label>
            )}

            <label className="grid gap-2">
              <span className="text-xs font-medium text-muted-foreground">Additional Info (optional)</span>
              <input
                value={additionalInfo}
                onChange={(e) => onAdditionalInfoChange(e.target.value)}
                placeholder="Legal notice, review approval, image source…"
                className="rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-foreground/20"
              />
            </label>

            <label className="flex items-center gap-3 text-sm text-foreground">
              <input
                type="checkbox"
                checked={gacha}
                onChange={(e) => setGacha(e.target.checked)}
                className="size-4 rounded border-border bg-transparent"
              />
              Includes gacha contents (adds &quot;{KAKAO_GACHA_INFO}&quot;)
            </label>

            {validationErrors.length > 0 && (
              <div className="rounded-2xl border border-amber-300 bg-amber-50 p-3">
                <p className="text-xs font-medium text-amber-900">Please fix these first</p>
                <div className="mt-2 space-y-1">
                  {validationErrors.map((message) => (
                    <p key={message} className="text-xs text-amber-800">
                      {message}
                    </p>
                  ))}
                </div>
              </div>
            )}

            <div className="w-[156px]">
              <button
                type="button"
                onClick={onApplyChanges}
                disabled={previewBusy || !inputsReady}
                className={cn(
                  "w-full rounded-xl px-4 py-2 text-sm font-semibold transition-all",
                  previewBusy || !inputsReady
                    ? "cursor-not-allowed bg-muted text-muted-foreground"
                    : "border border-border bg-background text-foreground hover:bg-muted"
                )}
              >
                {previewBusy ? "Applying..." : "Apply Changes"}
              </button>
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-end gap-3 border-t border-border px-4 py-4">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-xl border border-border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onSubmit}
              disabled={!canCreate}
              className={cn(
                "flex items-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-xs font-semibold transition-all",
                canCreate
                  ? "bg-accent text-white hover:opacity-85"
                  : "cursor-not-allowed bg-muted text-muted-foreground"
              )}
            >
              {submitting ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              {submitting ? "Creating..." : `Create ${assets.length} Kakao Assets`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function GenerationCard({
  assets,
  title,
  promptText,
  isGenerating,
  selectedAssetIds,
  onToggleSelect,
  onUseAsSource,
  onUseAsReference,
  onUseForResize,
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
  onUseAsSource?: (asset: AssetSummary) => void;
  onUseAsReference?: (asset: AssetSummary) => void;
  onUseForResize?: (asset: AssetSummary) => void;
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
  function fmtLabel(a: AssetSummary) {
    const size = a.width && a.height ? `${a.width}x${a.height}` : "";
    const fmt  = getAssetFileExtension(a).toUpperCase();
    return size ? `${size} - ${fmt}` : fmt;
  }

  return (
    <div className="group col-span-3 flex gap-2">
      {/* Images in 3-column grid */}
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

                {/* Image tile: click to zoom */}
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
                  {a.type === "video" ? (
                    <video
                      src={a.url}
                      className="h-full w-full object-cover transition-transform group-hover/img:scale-[1.02]"
                      muted
                      playsInline
                      preload="metadata"
                    />
                  ) : (
                    <img src={a.url} alt={a.title} className="h-full w-full object-cover transition-transform group-hover/img:scale-[1.02]" />
                  )}

                  {canRegenerateAsset && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onRegenerateAsset?.(a); }}
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

                  {(onUseAsSource || onUseAsReference || onUseForResize) && (
                    <div className="absolute bottom-2 left-2 right-2 z-10 hidden max-w-[calc(100%-16px)] grid-cols-2 gap-1 group-hover/img:grid">
                      {onUseAsSource && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUseAsSource(a);
                          }}
                          className="rounded-lg border border-white/20 bg-black/60 px-2 py-1 text-[10px] font-semibold text-white backdrop-blur-sm hover:bg-black/75"
                          style={{ gridColumn: onUseAsReference ? "span 1 / span 1" : "1 / -1" }}
                        >
                          Use as Source
                        </button>
                      )}
                      {onUseAsReference && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUseAsReference(a);
                          }}
                          className="rounded-lg border border-white/20 bg-black/60 px-2 py-1 text-[10px] font-semibold text-white backdrop-blur-sm hover:bg-black/75"
                          style={{ gridColumn: onUseAsSource ? "span 1 / span 1" : "1 / -1" }}
                        >
                          Use as Reference
                        </button>
                      )}
                      {onUseForResize && a.type === "image" && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUseForResize(a);
                          }}
                          className="rounded-lg border border-white/20 bg-black/60 px-2 py-1 text-[10px] font-semibold text-white backdrop-blur-sm hover:bg-black/75"
                          style={{ gridColumn: "1 / -1" }}
                        >
                          Resize
                        </button>
                      )}
                    </div>
                  )}
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

      {/* Action buttons in the right column, shown on hover */}
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

function RemediationReviewCard({
  asset,
  analysis,
  onRemediate,
  onHide,
  onZoom,
}: {
  asset: AssetSummary;
  analysis: RemediationAnalysisResult;
  onRemediate: () => void;
  onHide?: () => void;
  onZoom?: (asset: AssetSummary) => void;
}) {
  const riskTone =
    analysis.overall_risk === "high" || analysis.overall_risk === "extreme"
      ? "border-red-200 bg-red-50 text-red-700"
      : analysis.overall_risk === "medium" || analysis.overall_risk === "serious"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : "border-emerald-200 bg-emerald-50 text-emerald-700";

  return (
    <div className="group col-span-3 flex gap-3">
      <div className="min-w-0 flex-1 rounded-2xl border border-border bg-card p-4">
        <div className="flex gap-4">
          <button
            type="button"
            onClick={() => onZoom?.(asset)}
            className="h-28 w-40 shrink-0 overflow-hidden rounded-xl border border-border bg-[#07111F]"
          >
            <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" />
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-blue-700">
                Scan Result
              </span>
              <span className={cn("rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em]", riskTone)}>
                {analysis.overall_risk} risk
              </span>
            </div>
            <p className="mt-3 text-sm font-semibold text-foreground">{asset.title}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{analysis.summary}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {analysis.violations.length > 0 ? (
                analysis.violations.map((violation, index) => (
                  <span
                    key={`${asset.id}_${violation.category}_${index}`}
                    className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-medium text-foreground"
                  >
                    {violation.category.replace(/_/g, " ")}
                  </span>
                ))
              ) : (
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">
                  No violations
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-center gap-1.5 pt-1 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          title="Remediate"
          onClick={onRemediate}
          className="rounded-lg border border-accent/30 bg-soft-accent/40 p-2 text-accent transition-colors hover:bg-soft-accent"
        >
          <Sparkles className="size-4" />
        </button>
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

// Main component

export function CreateImageView({
  liveAssets,
  setLiveAssets,
  liveJobs,
  setLiveJobs,
  liveThreads,
  setLiveThreads,
  currentUser,
  contentScope,
  activeWorkspaceId,
  activeThreadId,
  initialResizeAssetIds = [],
  onThreadSelect,
  onJobCreated,
}: CreateImageViewProps) {
  // Form state
  const [mode, setMode] = useState<CreativeMode>("image");
  const [createFlow, setCreateFlow] = useState<CreateFlow>("resize");
  const [prompt, setPrompt] = useState("");
  const [modelId, setModelId] = useState("gemini-3.1-flash-image");
  const [selectedSizes, setSelectedSizes] = useState<string[]>(DEFAULT_IMAGE_SIZES);
  const [format, setFormat] = useState<OutputFormat>("static");

  // Additional GIF output for Resize mode
  const [includeGif, setIncludeGif] = useState(false);
  const [includeResizeGachaDisclosure, setIncludeResizeGachaDisclosure] = useState(false);

  // Resize source images
  const [resizeSourceAssets, setResizeSourceAssets] = useState<ResizeSourceAsset[]>([]);
  const resizeFileRef = useRef<HTMLInputElement>(null);
  const appliedInitialResizeSignature = useRef("");
  const [resizeLibraryPickerOpen, setResizeLibraryPickerOpen] = useState(false);
  const [remediationSourceAssets, setRemediationSourceAssets] = useState<ResizeSourceAsset[]>([]);
  const [remediationAnalyses, setRemediationAnalyses] = useState<Record<string, RemediationAnalysisResult>>({});
  const [remediationScanning, setRemediationScanning] = useState(false);
  const [showDevPromptOverride, setShowDevPromptOverride] = useState(false);
  const [resizePromptOverrides, setResizePromptOverrides] = useState<Record<string, string>>({});
  const [resizeNegativePromptOverride, setResizeNegativePromptOverride] = useState("");
  const [variants, setVariants] = useState<1 | 2>(1);
  const [activeChip, setActiveChip] = useState<ActiveChip>(null);
  const [isDragUploading, setIsDragUploading] = useState(false);

  // Derive provider from selected model
  const activeModel = ALL_MODELS.find((m) => m.id === modelId) ?? ALL_MODELS[0];
  const provider = activeModel.provider;

  // Theme Create
  const [themeCreateMode, setThemeCreateMode] = useState<ThemeCreateMode>("style_modify");
  const [themeCreateAssets, setThemeCreateAssets] = useState<AssetBucketState>({});
  const [themeCreateStyleName, setThemeCreateStyleName] = useState("");
  const [themeCreateStyleDetails, setThemeCreateStyleDetails] = useState("");
  const [themeCreatePresets, setThemeCreatePresets] = useState<ThemeCreatePresetSummary[]>([]);
  const [themeCreatePresetLoading, setThemeCreatePresetLoading] = useState(false);
  const [, setThemeCreatePresetPreviewId] = useState<string | null>(null);
  const [themeCreatePreviewFile, setThemeCreatePreviewFile] = useState<DraftAssetPreview | null>(null);
  const [themeCreatePresetName, setThemeCreatePresetName] = useState("");
  const [themeCreatePresetDescription, setThemeCreatePresetDescription] = useState("");
  const [themeCreatePresetSaving, setThemeCreatePresetSaving] = useState(false);
  const [, setThemeCreatePresetFeedback] = useState<string | null>(null);
  const [themeCreateDrafting, setThemeCreateDrafting] = useState(false);

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [uploadingSource, setUploadingSource] = useState(false);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [lastPrompt, setLastPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [psdInfo, setPsdInfo] = useState<string | null>(null);
  // Session

  // Working image ("current working object", drives edit vs generate)
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [selectedAssetIds, setSelectedAssetIds] = useState<Set<string>>(new Set());
  const [downloading, setDownloading] = useState(false);
  const [assetPanelSelectMode, setAssetPanelSelectMode] = useState(false);
  const [hiddenJobIds, setHiddenJobIds] = useState<Set<string>>(new Set());
  const [zoomedAsset, setZoomedAsset] = useState<AssetSummary | null>(null);
  const [kakaoBatchOpen, setKakaoBatchOpen] = useState(false);
  const [kakaoBatchAssets, setKakaoBatchAssets] = useState<KakaoBuilderAsset[]>([]);
  const [kakaoBatchSubmitting, setKakaoBatchSubmitting] = useState(false);
  const [kakaoBatchAppIconUrl, setKakaoBatchAppIconUrl] = useState<string | null>(null);
  const [kakaoBatchMainCopy, setKakaoBatchMainCopy] = useState(KAKAO_DEFAULT_MAIN_COPY);
  const [kakaoBatchTemplate, setKakaoBatchTemplate] = useState<KakaoTemplateId>(KAKAO_DEFAULT_TEMPLATE);
  const [kakaoBatchAppDownloadCopy, setKakaoBatchAppDownloadCopy] = useState(KAKAO_DEFAULT_APP_COPY);
  const [kakaoBatchSubCopy, setKakaoBatchSubCopy] = useState("");
  const [kakaoBatchAdditionalInfo, setKakaoBatchAdditionalInfo] = useState("");
  const [kakaoBatchGacha, setKakaoBatchGacha] = useState(false);
  const [kakaoBatchPreviewUrl, setKakaoBatchPreviewUrl] = useState<string | null>(null);
  const [kakaoBatchValidationErrors, setKakaoBatchValidationErrors] = useState<string[]>([]);
  const [kakaoBatchMainCopyWidthPx, setKakaoBatchMainCopyWidthPx] = useState(0);
  const [kakaoBatchPreviewBusy, setKakaoBatchPreviewBusy] = useState(false);
  const [kakaoBatchPreviewAssetIndex, setKakaoBatchPreviewAssetIndex] = useState(0);
  const [renamingThreadId, setRenamingThreadId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const lastSelectionSignatureRef = useRef("");

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

  function appendResizeSourceFiles(files: FileList | File[] | null) {
    if (!files) return;
    const incoming = Array.from(files).slice(0, MAX_RESIZE_SOURCE_IMAGES);
    const hasPsd = incoming.some((f) => f.name.toLowerCase().endsWith(".psd"));
    if (hasPsd) setPsdInfo("PSD detected, converting to PNG on upload…");
    setResizeSourceAssets((prev) => {
      const remaining = Math.max(0, MAX_RESIZE_SOURCE_IMAGES - prev.length);
      const additions = incoming.slice(0, remaining).map((file) => ({
        id: null,
        url: URL.createObjectURL(file),
        name: file.name,
        file,
      }));
      return [...prev, ...additions];
    });
  }

  async function appendRemediationSourceFiles(files: FileList | File[] | null) {
    if (!files) return;
    const incoming = Array.from(files).slice(0, MAX_REMEDIATION_SOURCE_IMAGES);
    const additionsWithDimensions = await Promise.all(
      incoming.map(async (file) => {
        const dimensions = await getImageDimensionsFromFile(file);
        return {
          id: null,
          url: URL.createObjectURL(file),
          name: file.name,
          file,
          width: dimensions?.width,
          height: dimensions?.height,
        };
      })
    );
    setRemediationAnalyses({});
    setRemediationSourceAssets((prev) => {
      const remaining = Math.max(0, MAX_REMEDIATION_SOURCE_IMAGES - prev.length);
      const additions = additionsWithDimensions.slice(0, remaining);
      return [...prev, ...additions];
    });
  }

  function appendThemeCreateFiles(
    files: FileList | File[] | null,
    targetRole?: "upload" | "reference_ad"
  ) {
    setIsDragUploading(false);
    if (!files) return;
    const incoming = Array.from(files).filter((file) => file.type.startsWith("image/"));
    if (incoming.length === 0) return;

    if (targetRole) {
      const targetFile = incoming[0] ?? null;
      if (targetFile) {
        setSingleThemeAsset(targetRole, targetFile);
      }
      return;
    }

    const nextUpload = incoming[0] ?? null;
    const nextReference = incoming[1] ?? null;

    if (nextUpload) {
      setSingleThemeAsset("upload", nextUpload);
    }
    if (nextReference) {
      setSingleThemeAsset("reference_ad", nextReference);
    }
  }

  function handleCreateFlowDrop(files: FileList | File[] | null) {
    if (!files) return;
    const imageFiles = Array.from(files).filter((file) => file.type.startsWith("image/"));
    if (imageFiles.length === 0) return;

    if (createFlow === "resize") {
      appendResizeSourceFiles(imageFiles);
      return;
    }
    if (createFlow === "remediation") {
      void appendRemediationSourceFiles(imageFiles);
      return;
    }
    if (createFlow === "theme_create") {
      appendThemeCreateFiles(imageFiles);
      return;
    }
  }

  function handleWorkbenchDragOver(event: DragEvent<HTMLDivElement>) {
    if (createFlow === "kakao") return;
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setIsDragUploading(true);
  }

  function handleWorkbenchDragLeave(event: DragEvent<HTMLDivElement>) {
    if (createFlow === "kakao") return;
    event.preventDefault();
    event.stopPropagation();
    const related = event.relatedTarget as Node | null;
    if (related && event.currentTarget.contains(related)) return;
    setIsDragUploading(false);
  }

  function handleWorkbenchDrop(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    event.stopPropagation();
    setIsDragUploading(false);
    handleCreateFlowDrop(event.dataTransfer.files);
  }

  function removeResizeSourceAsset(index: number) {
    setResizeSourceAssets((prev) => prev.filter((_, assetIndex) => assetIndex !== index));
  }

  function removeRemediationSourceAsset(index: number) {
    setRemediationSourceAssets((prev) => {
      const next = prev.filter((_, assetIndex) => assetIndex !== index);
      const nextKeys = new Set(next.map((asset, nextIndex) => asset.id ?? `${asset.name}_${nextIndex}`));
      setRemediationAnalyses((current) =>
        Object.fromEntries(Object.entries(current).filter(([key]) => nextKeys.has(key)))
      );
      return next;
    });
  }

  function remediationAssetKey(asset: ResizeSourceAsset, index: number) {
    return asset.id ?? `${asset.name}_${index}`;
  }

  function remediationOutputSize(asset: ResizeSourceAsset) {
    return buildSizeLabel(asset.width, asset.height);
  }

  function remediationRiskTone(risk?: string) {
    switch ((risk ?? "").toLowerCase()) {
      case "high":
      case "severe":
      case "extreme":
        return "border-red-200 bg-red-50 text-red-700";
      case "medium":
      case "serious":
        return "border-amber-200 bg-amber-50 text-amber-700";
      case "low":
        return "border-sky-200 bg-sky-50 text-sky-700";
      default:
        return "border-border bg-muted text-muted-foreground";
    }
  }

  function openDraftPreviewFromSourceAsset(asset: ResizeSourceAsset, index: number) {
    setThemeCreatePreviewFile({
      id: asset.id ?? `source_${index}`,
      url: asset.url,
      name: asset.name,
      file: asset.file,
      role: "upload",
    });
  }

  function setResizeSourceFromExistingAsset(asset: AssetSummary) {
    setResizeSourceAssets((prev) => {
      prev.forEach((item) => {
        if (item.url.startsWith("blob:")) {
          URL.revokeObjectURL(item.url);
        }
      });
      return [{
        id: asset.id,
        url: asset.url,
        name:
          asset.title ||
          `${asset.width ?? ""}x${asset.height ?? ""}`.replace(/^x|x$/g, "") ||
          "Resize source",
      }];
    });
    setCreateFlow("resize");
  }

  function addResizeSourceFromLibrary(asset: AssetSummary) {
    if (asset.type !== "image" || !asset.url || asset.url.includes("placeholder")) return;
    setResizeSourceAssets((prev) => {
      if (prev.some((item) => item.id === asset.id) || prev.length >= MAX_RESIZE_SOURCE_IMAGES) return prev;
      return [...prev, {
        id: asset.id,
        url: asset.url,
        name: asset.title || "Resize source",
        width: asset.width,
        height: asset.height,
      }];
    });
    setResizeLibraryPickerOpen(false);
    setCreateFlow("resize");
  }

  useEffect(() => {
    const ids = initialResizeAssetIds.filter(Boolean).slice(0, MAX_RESIZE_SOURCE_IMAGES);
    const signature = ids.join("|");
    if (!signature || appliedInitialResizeSignature.current === signature) return;
    const selectedAssets = ids
      .map((id) => liveAssets.find((asset) => asset.id === id))
      .filter((asset): asset is AssetSummary => Boolean(asset && asset.type === "image" && asset.url && !asset.url.includes("placeholder")));
    if (!selectedAssets.length) return;
    appliedInitialResizeSignature.current = signature;
    setResizeSourceAssets(selectedAssets.map((asset) => ({
      id: asset.id,
      url: asset.url,
      name: asset.title || "Resize source",
      width: asset.width,
      height: asset.height,
    })));
    setCreateFlow("resize");
  }, [initialResizeAssetIds, liveAssets]);

  function buildThemeCreatePresetTemplate(): string {
    if (themeCreateMode === "style_modify") {
      return prompt.trim();
    }
    return [
      prompt.trim(),
      themeCreateStyleName.trim(),
      themeCreateStyleDetails.trim(),
    ]
      .filter(Boolean)
      .join("\n\n");
  }

  function applyThemeCreatePreset(preset: {
    promptTemplate: string;
    styleName?: string;
    styleDetails?: string;
    name: string;
    description: string;
  }) {
    setPrompt(preset.promptTemplate);
    setThemeCreateStyleName(preset.styleName ?? preset.name);
    setThemeCreateStyleDetails(preset.styleDetails ?? preset.description);
    setThemeCreatePresetName(preset.name);
    setThemeCreatePresetDescription(preset.description);
    setThemeCreatePresetPreviewId(null);
    setActiveChip(null);
  }

  function kakaoBatchParams(asset: { id: string; url: string }): KakaoCompositeParams {
    return {
      template: kakaoBatchTemplate,
      thumbnailUrl: kakaoTemplate(kakaoBatchTemplate).object ? kakaoObjects.objectUrlFor(asset) : asset.url,
      appIconUrl: kakaoBatchAppIconUrl,
      appCopy: kakaoBatchAppDownloadCopy,
      mainCopy: kakaoBatchMainCopy,
      subCopy: kakaoBatchSubCopy,
      additionalInfo: kakaoBatchAdditionalInfo,
      gacha: kakaoBatchGacha,
    };
  }

  useEffect(() => {
    if (createFlow !== "theme_create") return;
    let cancelled = false;
    setThemeCreatePresetLoading(true);
    listThemeCreatePresets({ workspaceId: activeWorkspaceId, mode: themeCreateMode })
      .then((presets) => {
        if (!cancelled) {
          setThemeCreatePresets(presets);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setThemeCreatePresets([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setThemeCreatePresetLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspaceId, createFlow, themeCreateMode]);

  useEffect(() => {
    const hasReference = Boolean(themeCreateAssets.reference_ad?.[0]);
    setThemeCreateMode(hasReference ? "style_transfer" : "style_modify");
  }, [themeCreateAssets.reference_ad]);

  async function rebuildKakaoBatchPreview() {
    if (!kakaoBatchOpen || kakaoBatchAssets.length === 0) return;
    const previewAsset =
      kakaoBatchAssets[kakaoBatchPreviewAssetIndex] ??
      kakaoBatchAssets[0] ??
      null;
    if (!previewAsset) {
      setKakaoBatchValidationErrors(["Select at least one cleaned image."]);
      setKakaoBatchMainCopyWidthPx(0);
      setKakaoBatchPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return;
    }

    setKakaoBatchPreviewBusy(true);
    try {
      await loadKakaoFonts();
      const validation = await validateKakaoBizboardInputs(kakaoBatchParams(previewAsset));
      setKakaoBatchValidationErrors(validation.errors);
      setKakaoBatchMainCopyWidthPx(validation.mainCopyWidthPx);

      if (validation.errors.length > 0) {
        setKakaoBatchPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return null;
        });
        return;
      }

      const blob = await composeKakaoBizboard(kakaoBatchParams(previewAsset));
      const nextPreviewUrl = URL.createObjectURL(blob);
      setKakaoBatchPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return nextPreviewUrl;
      });
    } catch (err) {
      setKakaoBatchValidationErrors([
        err instanceof Error ? err.message : "Kakao preview generation failed.",
      ]);
      setKakaoBatchPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    } finally {
      setKakaoBatchPreviewBusy(false);
    }
  }

  useEffect(() => {
    if (!kakaoBatchOpen || kakaoBatchAssets.length === 0) return;
    rebuildKakaoBatchPreview();
    // intentionally only when the modal opens or selected assets change;
    // follow company flow and apply field edits through an explicit button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kakaoBatchOpen, kakaoBatchAssets, kakaoBatchPreviewAssetIndex]);

  function handleKakaoBatchIconChange(file: File | null) {
    setKakaoBatchAppIconUrl((prev) => {
      if (prev?.startsWith("blob:")) {
        URL.revokeObjectURL(prev);
      }
      return file ? URL.createObjectURL(file) : null;
    });
  }

  // Upload a file and auto-set it as the working image
  async function setWorkingImageFromFile(file: File) {
    const blobUrl = URL.createObjectURL(file);
    setWorkingImage({ assetId: null, url: blobUrl, label: file.name });
    try {
      const uploaded = await uploadAsset(file, activeWorkspaceId, "working", currentThreadIdForWrites);
      if (uploaded) {
        setWorkingImage((prev) =>
          prev ? { ...prev, assetId: uploaded.id } : null
        );
      }
    } catch {
      /* keep blob URL, submit will handle upload */
    }
  }

  // Operation handlers that require workingImage.assetId
  function requireAssetId(): string | null {
    const id = workingImage?.assetId ?? null;
    if (!id) setError("Image is still uploading - please wait a moment.");
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
        threadId: currentThreadIdForWrites,
        outputSizes: selectedSizes,
      });
      const job = { id: res.job_id, jobId: res.job_id, title: res.title, toolId: res.tool_id, status: res.status, progress: res.progress, eta: "Running...", lineageKey: res.lineage_key, threadId: res.thread_id ?? currentThreadIdForWrites };
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
        threadId: currentThreadIdForWrites,
        outputSizes: selectedSizes,
      });
      const job = { id: res.job_id, jobId: res.job_id, title: res.title, toolId: res.tool_id, status: res.status, progress: res.progress, eta: "Running...", lineageKey: res.lineage_key, threadId: res.thread_id ?? currentThreadIdForWrites };
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
        threadId: currentThreadIdForWrites,
        outputSizes: selectedSizes,
      });
      const job = { id: res.job_id, jobId: res.job_id, title: res.title, toolId: res.tool_id, status: res.status, progress: res.progress, eta: "Running...", lineageKey: res.lineage_key, threadId: res.thread_id ?? currentThreadIdForWrites };
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

  // Right assets panel
  // Only real assets that belong to the current thread container
  const downloadableAssets = liveAssets.filter(
    (a) =>
      a.jobId &&
      a.url &&
      !a.url.includes("placeholder") &&
      a.workspaceId === activeWorkspaceId
  );
  const currentThreads = [...liveThreads]
    .filter(
      (thread) =>
        thread.workspaceId === activeWorkspaceId &&
        thread.generationMode !== "video"
    )
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  const currentThreadsWithHistory = currentThreads.filter(
    (thread) => (thread.jobCount ?? 0) > 0 || (thread.assetCount ?? 0) > 0
  );
  const currentThreadIdForWrites = startingNewSession
    ? undefined
    : selectedThreadId ?? currentThreads[0]?.id ?? undefined;
  const kakaoObjects = useKakaoObjectImages(activeWorkspaceId, currentThreadIdForWrites);

  const allSelected =
    downloadableAssets.length > 0 &&
    downloadableAssets.every((a) => selectedAssetIds.has(a.id));
  const selectedAssets = downloadableAssets.filter((asset) => selectedAssetIds.has(asset.id));
  const selectedGifEligibleAssets = selectedAssets.filter((asset) => asset.type !== "gif");
  const selectedKakaoEligibleAssets = selectedAssets.filter((asset) => asset.type !== "gif");
  const selectedKakaoPreviewAsset = selectedKakaoEligibleAssets[0] ?? null;

  useEffect(() => {
    const nextSignature = selectedAssets
      .map((asset) => asset.id)
      .join("|");
    if (lastSelectionSignatureRef.current === nextSignature) return;
    lastSelectionSignatureRef.current = nextSignature;
  }, [selectedAssets]);

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
        await downloadAssetsZip(ids);
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
          threadId: asset.threadId ?? currentThreadIdForWrites,
        });
        lastResponse = response;
        const job: JobSummary = {
          id: response.job_id,
          jobId: response.job_id,
          title: response.title,
          toolId: response.tool_id,
          status: response.status,
          progress: response.progress,
          eta: response.status === "completed" ? "Completed" : "Running...",
          lineageKey: response.lineage_key,
          threadId: response.thread_id ?? asset.threadId ?? currentThreadIdForWrites,
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

  function handleOpenKakaoBatch(assetsOverride?: KakaoBuilderAsset[]) {
    const nextAssets = assetsOverride?.length
      ? assetsOverride
      : selectedKakaoEligibleAssets.map((asset) => ({
          id: asset.id,
          url: asset.url,
          title: asset.title,
          type: asset.type,
          threadId: asset.threadId ?? null,
        }));
    if (nextAssets.length === 0) return;
    setKakaoBatchAssets(nextAssets);
    setKakaoBatchPreviewAssetIndex(0);
    setKakaoBatchAppDownloadCopy((prev) => prev.trim() || KAKAO_DEFAULT_APP_COPY);
    setKakaoBatchMainCopy((prev) => prev.trim() || KAKAO_DEFAULT_MAIN_COPY);
    setKakaoBatchOpen(true);
  }

  async function handleGenerateKakaoSelected() {
    if (kakaoBatchAssets.length === 0) return;
    setKakaoBatchSubmitting(true);
    setGenerating(true);
    setError(null);

    let nextThreadId = currentThreadIdForWrites;
    const queuedJobs: JobSummary[] = [];
    const template = kakaoTemplate(kakaoBatchTemplate);

    try {
      for (const asset of kakaoBatchAssets) {
        const blob = await composeKakaoBizboard(kakaoBatchParams(asset));
        const safeName = (asset.title || "kakao_asset")
          .replace(/\.[^.]+$/, "")
          .replace(/[^a-zA-Z0-9_-]+/g, "_");
        const file = new File([blob], `${safeName}_kakao_bizboard_${KAKAO_BIZBOARD_SIZE}.png`, {
          type: "image/png",
        });
        const uploaded = await uploadAsset(file, activeWorkspaceId, "upload", nextThreadId ?? currentThreadIdForWrites);
        if (!uploaded) {
          throw new Error(`Bizboard upload failed for ${asset.title}`);
        }

        const response = await createKakaoBizboardJob({
          workspaceId: activeWorkspaceId,
          cleanedAssetId: asset.id,
          composedAssetId: uploaded.id,
          template: kakaoBatchTemplate,
          mainCopy: kakaoBatchMainCopy,
          subCopy: template.subCopy ? kakaoBatchSubCopy : "",
          appDownloadCopy: template.appCopy ? kakaoBatchAppDownloadCopy : "",
          additionalInfo: kakaoBatchAdditionalInfo,
          gacha: kakaoBatchGacha,
          threadId: nextThreadId ?? currentThreadIdForWrites,
        });

        queuedJobs.push({
          id: response.job_id,
          jobId: response.job_id,
          title: response.title,
          toolId: response.tool_id,
          status: response.status,
          progress: response.progress,
          eta: response.status === "completed" ? "Completed" : "Running...",
          lineageKey: response.lineage_key,
          threadId: response.thread_id ?? nextThreadId ?? currentThreadIdForWrites,
        });
        nextThreadId = response.thread_id ?? nextThreadId ?? currentThreadIdForWrites;
      }

      if (queuedJobs.length === 0) {
        throw new Error("No Kakao Bizboard jobs were created.");
      }

      if (nextThreadId) {
        setSelectedThreadId(nextThreadId);
        setStartingNewSession(false);
        onThreadSelect?.(nextThreadId);
      }

      setLastPrompt("Kakao Bizboard");
      setCurrentJobId(queuedJobs[queuedJobs.length - 1]?.jobId ?? null);
      setLiveJobs((prev) => [...queuedJobs.reverse(), ...prev]);
      queuedJobs.forEach((job) => onJobCreated(job));
      setKakaoBatchOpen(false);
      setKakaoBatchAssets([]);
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setKakaoBatchSubmitting(false);
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
        threadId: threadId ?? currentThreadIdForWrites,
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
        threadId: response.thread_id ?? (threadId ?? currentThreadIdForWrites) ?? undefined,
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
    const sourceAsset = resizeSourceAssets[0];
    if (!sourceAsset) return;
    let sourceId = sourceAsset.id;
    if (!sourceId && sourceAsset.file) {
      setUploadingSource(true);
      try {
        const uploaded = await uploadAsset(sourceAsset.file, activeWorkspaceId, "upload", currentThreadIdForWrites);
        if (uploaded) {
          sourceId = uploaded.id;
          setResizeSourceAssets((prev) =>
            prev.map((item, index) => (index === 0 ? { ...item, id: uploaded.id } : item))
          );
        }
      } finally {
        setUploadingSource(false);
      }
    }
    if (!sourceId) {
      setError("Upload a source image first.");
      return;
    }
    await triggerGifJob(sourceId, currentThreadIdForWrites);
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
        thread_id: entry.threadId || currentThreadIdForWrites,
        generation_mode: "resize",
        include_gif: false,
        resize_include_gacha_disclosure: Boolean(
          outputSizes.some((size) => RESIZE_GACHA_DISCLOSURE_SIZES.has(size)) && entry.assets.some(
            (asset) => asset.analysis?.resize_include_gacha_disclosure === true
          )
        ),
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
        eta: response.status === "completed" ? "Completed" : "Running...",
        lineageKey: response.lineage_key,
        threadId: response.thread_id ?? (entry.threadId || currentThreadIdForWrites) ?? undefined,
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
        thread_id: asset.threadId || currentThreadIdForWrites,
        generation_mode: "resize",
        include_gif: false,
        resize_include_gacha_disclosure: Boolean(
          RESIZE_GACHA_DISCLOSURE_SIZES.has(targetSize) && asset.analysis?.resize_include_gacha_disclosure === true
        ),
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
        eta: response.status === "completed" ? "Completed" : "Running...",
        lineageKey: response.lineage_key,
        threadId: response.thread_id ?? (asset.threadId || currentThreadIdForWrites) ?? undefined,
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
        listAssets(activeWorkspaceId, contentScope),
        listThreads(activeWorkspaceId, contentScope),
      ]);
      setLiveAssets(assets);
      setLiveThreads(threads);
      setSelectedAssetIds(new Set());
    } catch (err) {
      console.error("Delete failed:", err);
    }
  }

  // Session selection, which can be driven externally from the global sidebar
  useEffect(() => {
    if (activeThreadId && currentThreads.some((thread) => thread.id === activeThreadId)) {
      setSelectedThreadId(activeThreadId);
      setStartingNewSession(false);
      return;
    }
    if (!startingNewSession) {
      setSelectedThreadId(currentThreadsWithHistory[0]?.id ?? currentThreads[0]?.id ?? null);
    }
  }, [activeThreadId, activeWorkspaceId, currentThreads, currentThreadsWithHistory, startingNewSession]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAssets(activeWorkspaceId, contentScope), listThreads(activeWorkspaceId, contentScope)])
      .then(([assets, threads]) => {
        if (cancelled) return;
        setLiveAssets(assets);
        setLiveThreads(threads);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [activeWorkspaceId, contentScope, setLiveAssets, setLiveThreads]);

  useEffect(() => {
    setSelectedAssetIds(new Set());
  }, [selectedThreadId, activeWorkspaceId]);

  useEffect(() => {
    setStartingNewSession(false);
  }, [activeWorkspaceId]);

  // Ref for click-outside detection
  const barRef = useRef<HTMLDivElement>(null);

  // Reset sizes on mode change
  useEffect(() => {
    setSelectedSizes(mode === "endcard" ? ENDCARD_SIZE_IDS : DEFAULT_IMAGE_SIZES);
  }, [mode]);

  useEffect(() => {
    if (!selectedSizes.some((size) => RESIZE_GACHA_DISCLOSURE_SIZES.has(size))) {
      setIncludeResizeGachaDisclosure(false);
    }
  }, [selectedSizes]);

  // Watch liveJobs for completion
  useEffect(() => {
    if (!currentJobId || !generating) return;
    const job = liveJobs.find((j) => (j.jobId ?? j.id) === currentJobId);
    if (!job) return;
    if (job.status === "completed") {
      Promise.all([listAssets(activeWorkspaceId, contentScope), listThreads(activeWorkspaceId, contentScope)])
        .then(([a, threads]) => {
          setLiveAssets(a);
          setLiveThreads(threads);
        })
        .catch(() => {});
      if (job.threadId) {
        setSelectedThreadId(job.threadId);
        setStartingNewSession(false);
        onThreadSelect?.(job.threadId);
      }
      if (createFlow === "theme_create") {
        const nextPresetName = buildThemeCreatePresetName(themeCreateMode, themeCreateStyleName, prompt);
        const nextPresetSummary = buildThemeCreatePresetSummary(themeCreateMode, themeCreateStyleDetails, prompt);
        setThemeCreatePresetName((prev) => prev.trim() || nextPresetName);
        setThemeCreatePresetDescription((prev) => prev.trim() || nextPresetSummary);
        setThemeCreatePresetFeedback(
          "Theme Create output is ready. Review the result, then draft a style report or save it directly as a preset asset."
        );
      }
      setGenerating(false);
      setCurrentJobId(null);
    }
    if (job.status === "failed") {
      setGenerating(false);
      setCurrentJobId(null);
      setError(job.message ?? "Generation failed. Check your API credentials and try again.");
    }
  }, [
    liveJobs,
    currentJobId,
    generating,
    activeWorkspaceId,
    contentScope,
    setLiveAssets,
    setLiveThreads,
    createFlow,
    themeCreateMode,
    themeCreateStyleName,
    themeCreateStyleDetails,
    prompt,
    onThreadSelect,
  ]);

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

  // Theme Create always produces one Gemini-native canvas. Resize is the
  // separate workflow for non-native ad dimensions such as 1200×628.
  useEffect(() => {
    if (createFlow === "theme_create") {
      setSelectedSizes((current) =>
        THEME_CREATE_SIZE_IDS.includes(current[0] as (typeof THEME_CREATE_SIZE_IDS)[number])
          ? [current[0]]
          : ["1920x1080"]
      );
    }
  }, [createFlow]);

  useEffect(() => {
    if (createFlow === "remediation") {
      setVariants(2);
    }
  }, [createFlow]);

  useEffect(() => {
    if (createFlow === "resize" || createFlow === "kakao" || createFlow === "remediation") {
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

  function setSingleThemeAsset(role: AssetRole, file: File | null) {
    setThemeCreateAssets((prev) => {
      const existing = prev[role] ?? [];
      existing.forEach((item) => {
        if (item.url.startsWith("blob:")) {
          URL.revokeObjectURL(item.url);
        }
      });
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

  function setThemeAssetFromExistingAsset(role: AssetRole, asset: AssetSummary) {
    setThemeCreateAssets((prev) => {
      const existing = prev[role] ?? [];
      existing.forEach((item) => {
        if (item.url.startsWith("blob:")) {
          URL.revokeObjectURL(item.url);
        }
      });
      return {
        ...prev,
        [role]: [{
          id: asset.id,
          url: asset.url,
          name: asset.title || `${asset.width ?? ""}x${asset.height ?? ""}`.replace(/^x|x$/g, "") || "Theme asset",
          role,
        }],
      };
    });
    setThemeCreatePreviewFile(null);
    setCreateFlow("theme_create");
  }

  function hasRoleAssets(bucket: AssetBucketState, role: AssetRole) {
    return (bucket[role] ?? []).length > 0;
  }

  async function uploadRoleBuckets(bucket: AssetBucketState) {
    const uploaded: Partial<Record<AssetRole, string[]>> = {};
    for (const role of Object.keys(bucket) as AssetRole[]) {
      const drafts = bucket[role] ?? [];
      for (const draft of drafts) {
        if (draft.id && !draft.file) {
          uploaded[role] = [...(uploaded[role] ?? []), draft.id];
          continue;
        }
        if (!draft.file) continue;
        const asset = await uploadAsset(draft.file, activeWorkspaceId, role, currentThreadIdForWrites);
        if (!asset) continue;
        uploaded[role] = [...(uploaded[role] ?? []), asset.id];
      }
    }
    return uploaded;
  }

  function flattenUploaded(uploaded: Partial<Record<AssetRole, string[]>>, roles: AssetRole[]) {
    return roles.flatMap((role) => uploaded[role] ?? []);
  }

  async function handleSaveThemeCreatePreset() {
    if (themeCreatePresetSaving) return;
    const template = buildThemeCreatePresetTemplate();
    const name = themeCreatePresetName.trim();
    if (!name) {
      setThemeCreatePresetFeedback("Preset name is required.");
      return;
    }
    if (!template) {
      setThemeCreatePresetFeedback("Add prompt content before saving a preset.");
      return;
    }

    setThemeCreatePresetSaving(true);
    setThemeCreatePresetFeedback(null);
    try {
      const sourceAssetId = themeCreateAssets.upload?.[0]?.id ?? undefined;
      const referenceAssetIds = [
        themeCreateAssets.reference_ad?.[0]?.id,
      ].filter((value): value is string => Boolean(value));
      const baseTags = [
        "theme-create",
        themeCreateMode.replaceAll("_", "-"),
      ];
      const report = await createThemeCreateReport({
        workspace_id: activeWorkspaceId,
        title: name,
        summary: themeCreatePresetDescription.trim() || `Reusable ${themeCreateMode.replaceAll("_", " ")} preset captured by GM.`,
        theme_create_mode: themeCreateMode,
        prompt_template: template,
        source_asset_id: sourceAssetId,
        reference_asset_ids: referenceAssetIds,
        source_job_id: latestThemeCreateEntry?.id,
        recommended_preset_name: name,
        visual_dna: themeCreateStyleDetails.trim() ? [themeCreateStyleDetails.trim()] : [],
        composition_rules: themeCreateMode === "style_modify" ? ["Preserve original layout and subject placement."] : [],
        do_not_copy: themeCreateMode === "style_transfer" ? ["Do not copy physical subjects or text from the inspiration image."] : [],
        tags: baseTags,
        taxonomy: {
          workflow: [themeCreateMode],
        },
      });
      const preset = await createThemeCreatePreset({
        workspace_id: activeWorkspaceId,
        name,
        description: themeCreatePresetDescription.trim() || report.summary,
        theme_create_mode: themeCreateMode,
        visibility: "team",
        prompt_template: template,
        style_name: themeCreateMode === "style_modify" ? name : themeCreateStyleName.trim() || name,
        style_details: themeCreateStyleDetails.trim() || undefined,
        tags: report.tags,
        taxonomy: report.taxonomy,
        source_report_id: report.id,
        source_job_id: latestThemeCreateEntry?.id,
        source_asset_id: sourceAssetId,
      });
      setThemeCreatePresets((prev) => [preset, ...prev.filter((item) => item.id !== preset.id)]);
      setThemeCreatePresetFeedback(`Saved preset "${preset.name}".`);
      setThemeCreatePresetName("");
      setThemeCreatePresetDescription("");
    } catch (err) {
      setThemeCreatePresetFeedback(err instanceof Error ? err.message : "Failed to save preset.");
    } finally {
      setThemeCreatePresetSaving(false);
    }
  }

  async function handleDraftThemeCreateReport() {
    if (themeCreateDrafting) return;
    const template = buildThemeCreatePresetTemplate();
    if (!template) {
      setThemeCreatePresetFeedback("Add prompt content before drafting a report.");
      return;
    }

    const nextAssets = { ...themeCreateAssets };
    setThemeCreateDrafting(true);
    setThemeCreatePresetFeedback(null);
    try {
      for (const role of ["upload", "reference_ad"] as AssetRole[]) {
        const drafts = nextAssets[role] ?? [];
        for (let index = 0; index < drafts.length; index++) {
          const draft = drafts[index];
          if (draft && !draft.id && draft.file) {
            const uploaded = await uploadAsset(draft.file, activeWorkspaceId, role, currentThreadIdForWrites);
            if (uploaded) {
              drafts[index] = { ...draft, id: uploaded.id, url: uploaded.url };
            }
          }
        }
        if (drafts.length > 0) {
          nextAssets[role] = drafts;
        }
      }
      setThemeCreateAssets(nextAssets);

      const sourceAssetId = nextAssets.upload?.[0]?.id;
      if (!sourceAssetId) {
        throw new Error("Theme Create draft needs a source image.");
      }
      const referenceAssetIds = [
        nextAssets.reference_ad?.[0]?.id,
      ].filter((value): value is string => Boolean(value));

      const draft = await draftThemeCreateReport({
        workspace_id: activeWorkspaceId,
        theme_create_mode: themeCreateMode,
        prompt_template: template,
        source_asset_id: sourceAssetId,
        reference_asset_ids: referenceAssetIds,
        style_name: themeCreateStyleName.trim() || themeCreatePresetName.trim() || undefined,
        style_details: themeCreateStyleDetails.trim() || undefined,
      });

      setThemeCreatePresetName(draft.recommended_preset_name ?? draft.title);
      setThemeCreatePresetDescription(draft.summary);
      if (!themeCreateStyleName.trim()) {
        setThemeCreateStyleName(draft.recommended_preset_name ?? draft.title);
      }
      if (!themeCreateStyleDetails.trim() && draft.visual_dna.length > 0) {
        setThemeCreateStyleDetails(draft.visual_dna.join(", "));
      }
      setThemeCreatePresetFeedback("Style report drafted. Review the preset asset name and summary, then save it into the reusable library.");
    } catch (err) {
      setThemeCreatePresetFeedback(err instanceof Error ? err.message : "Failed to draft report.");
    } finally {
      setThemeCreateDrafting(false);
    }
  }

  async function ensureUploadedRemediationSources() {
    const nextSources: ResizeSourceAsset[] = [...remediationSourceAssets];
    setUploadingSource(true);
    try {
      for (let index = 0; index < nextSources.length; index++) {
        let sourceId = nextSources[index]?.id ?? null;
        const sourceFile = nextSources[index]?.file;
        if (!sourceId && sourceFile) {
          const uploaded = await uploadAsset(sourceFile, activeWorkspaceId, "upload", currentThreadIdForWrites);
          if (uploaded) {
            sourceId = uploaded.id;
            nextSources[index] = {
              ...nextSources[index],
              id: uploaded.id,
              url: uploaded.url,
              width: uploaded.width,
              height: uploaded.height,
            };
          }
        }
        if (!sourceId) {
          throw new Error(`Upload failed for ${nextSources[index]?.name ?? `image ${index + 1}`}`);
        }
      }
      setRemediationSourceAssets(nextSources);
      return nextSources;
    } finally {
      setUploadingSource(false);
    }
  }

  async function handleAnalyzeRemediation() {
    if (remediationScanning || generating) return;
    if (remediationSourceAssets.length === 0) {
      setError("Upload at least one source image to analyze.");
      return;
    }

    setRemediationScanning(true);
    setError(null);
    try {
      const uploadedSources = await ensureUploadedRemediationSources();
      const sourceIds = uploadedSources.map((asset) => asset.id).filter((value): value is string => Boolean(value));
      const response = await analyzeRemediationAssets({
        workspace_id: activeWorkspaceId,
        source_asset_ids: sourceIds,
        prompt: prompt.trim(),
        created_by: currentUser.id,
      });

      const nextAnalyses = Object.fromEntries(
        response.results.map((result) => [result.asset_id, result])
      );
      setRemediationAnalyses(nextAnalyses);
      const [assets, threads] = await Promise.all([
        listAssets(activeWorkspaceId, contentScope),
        listThreads(activeWorkspaceId, contentScope),
      ]);
      setLiveAssets(assets);
      setLiveThreads(threads);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to analyze remediation assets.");
    } finally {
      setRemediationScanning(false);
    }
  }

  async function handleBulkRemediate(
    targets: Array<{ asset: AssetSummary | ResizeSourceAsset; analysis: RemediationAnalysisResult }>
  ) {
    if (targets.length === 0) {
      setGenerating(false);
      setError("No scanned remediation items are ready to fix.");
      return;
    }

    setGenerating(true);
    setError(null);
    setCurrentJobId(null);
    setLastPrompt("Image Remediation");
    try {
      let nextThreadId = currentThreadIdForWrites;
      const queuedJobs: JobSummary[] = [];

      for (const target of targets) {
        const assetId = target.asset.id ?? null;
        if (!assetId) {
          const assetLabel = "name" in target.asset ? target.asset.name : target.asset.title;
          throw new Error(`Missing source asset ID for ${assetLabel ?? "remediation source"}`);
        }
        const outputSize = buildSizeLabel(target.asset.width, target.asset.height);
        const response = await createImageGenerationJob({
          workspace_id: activeWorkspaceId,
          prompt: prompt.trim() || "Remediate policy violations while preserving valid layout and branding.",
          provider: "gemini",
          model: "gemini-3.1-flash-image",
          variants,
          aspect_ratio: "multi-size",
          created_by: currentUser.id,
          source_asset_ids: [assetId],
          reference_asset_ids: [],
          client_asset_ids: [],
          output_sizes: outputSize ? [outputSize] : [],
          output_format: "image",
          generation_mode: "remediation",
          remediation_analysis: [target.analysis],
          thread_id: nextThreadId ?? undefined,
          source_asset_id: assetId,
          theme: "Image Remediation",
        });

        queuedJobs.push({
          id: response.job_id,
          jobId: response.job_id,
          title: response.title,
          toolId: response.tool_id,
          status: response.status,
          progress: response.progress,
          eta: response.status === "completed" ? "Completed" : "Running...",
          lineageKey: response.lineage_key,
          threadId: response.thread_id ?? nextThreadId,
        });
        nextThreadId = response.thread_id ?? nextThreadId;
      }

      if (queuedJobs.length === 0) {
        throw new Error("No remediation jobs were created.");
      }
      if (nextThreadId) {
        setSelectedThreadId(nextThreadId);
        setStartingNewSession(false);
        onThreadSelect?.(nextThreadId);
      }
      setLiveJobs((prev) => [...queuedJobs.reverse(), ...prev]);
      queuedJobs.forEach((job) => onJobCreated(job));
      setCurrentJobId(queuedJobs[queuedJobs.length - 1]?.jobId ?? null);
    } catch (err) {
      setGenerating(false);
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    }
  }

  async function handleRemediateFromHistory(asset: AssetSummary, analysis: RemediationAnalysisResult) {
    setCreateFlow("remediation");
    setRemediationSourceAssets([
      {
        id: asset.id,
        url: asset.url,
        name: asset.title,
        width: asset.width ?? undefined,
        height: asset.height ?? undefined,
      },
    ]);
    setRemediationAnalyses({ [asset.id]: analysis });
    setPrompt("");
    await handleBulkRemediate([{ asset, analysis }]);
  }

  // Generate / edit router
  async function handleGenerate() {
    if (generating) return;

    // Effective sizes (for resize the checkbox grid already has endcard included if selected)
    const sizes = selectedSizes.length ? selectedSizes : DEFAULT_IMAGE_SIZES;

    setGenerating(true);
    setError(null);
    setPsdInfo(null);
    setCurrentJobId(null);
    setLastPrompt(
      createFlow === "resize"
        ? `Resize to ${sizes.join(", ")}`
        : createFlow === "theme_create"
        ? `Theme Create - ${THEME_CREATE_MODES.find((item) => item.id === themeCreateMode)?.label ?? "Theme Create"}`
        : createFlow === "remediation"
        ? `Image Remediation - ${prompt.trim() || "Safer policy-aligned variant"}`
        : prompt.trim() || createFlow.replace("_", " ")
    );

    try {
      let response: Awaited<ReturnType<typeof createImageGenerationJob>>;

      // Resize task
      if (createFlow === "resize") {
        if (resizeSourceAssets.length === 0) {
          setGenerating(false);
          setError("Upload at least one source image to resize.");
          return;
        }
        let nextThreadId = currentThreadIdForWrites;
        const queuedJobs: JobSummary[] = [];
        const nextSources = [...resizeSourceAssets];
        setUploadingSource(true);
        try {
          for (let index = 0; index < nextSources.length; index++) {
            let sourceId = nextSources[index]?.id ?? null;
            const sourceFile = nextSources[index]?.file;
            if (!sourceId && sourceFile) {
              const uploaded = await uploadAsset(sourceFile, activeWorkspaceId, "upload", currentThreadIdForWrites);
              if (uploaded) {
                sourceId = uploaded.id;
                nextSources[index] = { ...nextSources[index], id: uploaded.id };
              }
            }
            if (!sourceId) {
              throw new Error(`Upload failed for ${nextSources[index]?.name ?? `image ${index + 1}`}`);
            }
            response = await createImageGenerationJob({
              workspace_id: activeWorkspaceId,
              prompt: `Resize the source image to the requested ad sizes. ${prompt.trim() ? `Additional note: ${prompt.trim()}` : ""}`.trim(),
              provider,
              model: modelId,
              variants: 1,
              aspect_ratio: "multi-size",
              created_by: currentUser.id,
              source_asset_ids: [sourceId],
              reference_asset_ids: [sourceId],
              theme: `Resize ${sizes.join(" ")}`,
              output_sizes: sizes,
              output_format: "image",
              preserve_layout: true,
              use_reference_style: true,
              client_asset_ids: [],
              thread_id: nextThreadId,
              generation_mode: "resize",
              include_gif: includeGif,
              resize_include_gacha_disclosure:
                selectedSizes.some((size) => RESIZE_GACHA_DISCLOSURE_SIZES.has(size)) && includeResizeGachaDisclosure,
              resize_prompt_overrides: Object.fromEntries(
                sizes
                  .map((size) => [size, resizePromptOverrides[size]?.trim() ?? ""])
                  .filter(([, value]) => value.length > 0)
              ),
              resize_negative_prompt_override: resizeNegativePromptOverride.trim() || undefined,
            });
            queuedJobs.push({
              id: response.job_id,
              jobId: response.job_id,
              title: response.title,
              toolId: response.tool_id,
              status: response.status,
              progress: response.progress,
              eta: response.status === "completed" ? "Completed" : "Running...",
              lineageKey: response.lineage_key,
              threadId: response.thread_id ?? nextThreadId,
            });
            nextThreadId = response.thread_id ?? nextThreadId;
          }
        } finally {
          setUploadingSource(false);
        }
        setResizeSourceAssets(nextSources);
        if (queuedJobs.length === 0) {
          throw new Error("No resize jobs were created.");
        }
        if (nextThreadId) {
          setSelectedThreadId(nextThreadId);
          setStartingNewSession(false);
          onThreadSelect?.(nextThreadId);
        }
        setLiveJobs((prev) => [...queuedJobs.reverse(), ...prev]);
        queuedJobs.forEach((job) => onJobCreated(job));
        setCurrentJobId(queuedJobs[queuedJobs.length - 1]?.jobId ?? null);
        return;
      }

      if (createFlow === "remediation") {
        if (remediationSourceAssets.length === 0) {
          setGenerating(false);
          setError("Upload at least one source image to remediate.");
          return;
        }
        const nextSources = await ensureUploadedRemediationSources();
        const analyzedTargets = nextSources
          .map((asset, index) => {
            const assetId = asset.id;
            if (!assetId) return null;
            const analysis = remediationAnalyses[assetId] ?? remediationAnalyses[remediationAssetKey(asset, index)];
            if (!analysis || analysis.violations.length === 0) return null;
            return { asset, analysis };
          })
          .filter((item): item is { asset: ResizeSourceAsset; analysis: RemediationAnalysisResult } => Boolean(item));

        const allScanned =
          nextSources.length > 0 &&
          nextSources.every((asset, index) => {
            const assetId = asset.id;
            return Boolean(assetId && (remediationAnalyses[assetId] ?? remediationAnalyses[remediationAssetKey(asset, index)]));
          });

        if (!allScanned) {
          setGenerating(false);
          await handleAnalyzeRemediation();
          return;
        }

        if (analyzedTargets.length === 0) {
          setGenerating(false);
          setError("Scan completed, but no policy violations were found to remediate.");
          return;
        }

        await handleBulkRemediate(analyzedTargets);
        return;
      }

      else {
        const uploaded = await uploadRoleBuckets(themeCreateAssets);
        const sourceIds = flattenUploaded(uploaded, ["upload"]);
        const referenceIds = flattenUploaded(uploaded, ["reference_ad"]);

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

        const modeLabel = THEME_CREATE_MODES.find((item) => item.id === themeCreateMode)?.label ?? "Theme Create";
        response = await createImageGenerationJob({
          workspace_id: activeWorkspaceId,
          prompt: prompt.trim() || `Theme Create - ${modeLabel}`,
          provider,
          model: modelId,
          variants,
          aspect_ratio: "multi-size",
          created_by: currentUser.id,
          source_asset_ids: [sourceIds[0]],
          theme: modeLabel,
          output_sizes: sizes,
          output_format: "image",
          reference_asset_ids: referenceIds,
          preserve_layout: false,
          use_reference_style: false,
          client_asset_ids: [],
        thread_id: currentThreadIdForWrites,
          generation_mode: "theme_create",
          theme_create_mode: themeCreateMode,
          theme_create_style_name: themeCreateStyleName.trim() || (themeCreateMode === "style_modify" ? prompt.trim() : undefined),
          theme_create_style_details: themeCreateStyleDetails.trim() || undefined,
        });
      }

      const job: JobSummary = {
        id: response.job_id,
        jobId: response.job_id,
        title: response.title,
        toolId: response.tool_id,
        status: response.status,
        progress: response.progress,
        eta: response.status === "completed" ? "Completed" : "Running...",
        lineageKey: response.lineage_key,
        threadId: response.thread_id ?? currentThreadIdForWrites,
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
          listAssets(activeWorkspaceId, contentScope),
          listThreads(activeWorkspaceId, contentScope),
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

  // History data
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
          const isThemeCreate = Boolean(assets[0]?.analysis?.theme_create_mode);
          const requestPrompt = assets[0]?.analysis?.request_prompt;
          if (typeof requestPrompt === "string" && requestPrompt.trim()) {
            return requestPrompt.trim();
          }
          if (!isThemeCreate) {
            const actualThemeCreatePrompt = assets[0]?.analysis?.actual_theme_create_prompt;
            if (typeof actualThemeCreatePrompt === "string" && actualThemeCreatePrompt.trim()) {
              return actualThemeCreatePrompt.trim();
            }
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
  for (const asset of liveAssets) {
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
  const threadMap = new Map(currentThreads.map((thread) => [thread.id, thread]));
  const threadDateGroups: Array<{ date: string; threads: CreativeThreadSummary[] }> = [];

  // Chip labels
  const selectedThread = selectedThreadId ? threadMap.get(selectedThreadId) ?? null : null;
  const selectedThreadAssets = selectedThreadId ? threadAssetMap.get(selectedThreadId) ?? [] : [];
  const selectedThreadJobs = selectedThreadId ? threadJobsMap.get(selectedThreadId) ?? [] : [];
  const threadTitle = startingNewSession
    ? "New Thread"
    : selectedThread?.title ?? currentThreads[0]?.title ?? "New Thread";
  // When starting a new thread: show empty canvas
  // When a thread is selected: show only that thread's jobs
  // Otherwise (no thread, not new): show all thread jobs
  const visibleJobEntries = startingNewSession
    ? []
    : selectedThreadId
    ? jobEntries.filter((e) => e.threadId === selectedThreadId)
    : jobEntries;
  const remediationReviewEntries = (startingNewSession
    ? []
    : (selectedThreadId ? liveAssets.filter((asset) => asset.threadId === selectedThreadId) : liveAssets)
        .filter((asset) => !asset.jobId && asset.analysis?.remediation_analysis && asset.type === "image")
        .map((asset) => ({
          id: `scan_${asset.id}`,
          asset,
          analysis: asset.analysis?.remediation_analysis as RemediationAnalysisResult,
          createdAt: asset.createdAt,
        }))
        .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
  );
  const assetBackedJobIds = new Set(jobEntries.map((entry) => entry.id));
  const pendingVisibleJobEntries = (startingNewSession
    ? []
    : liveJobs.filter((job) => {
        const jobKey = job.jobId ?? job.id;
        if (assetBackedJobIds.has(jobKey)) return false;
        if (!(job.status === "running" || job.status === "queued" || job.status === "pending")) return false;
        if (selectedThreadId) return job.threadId === selectedThreadId;
        return true;
      }).map((job) => ({
        id: job.jobId ?? job.id,
        threadId: job.threadId ?? "",
        createdAt: new Date().toISOString(),
        assets: [] as AssetSummary[],
        title: job.title || lastPrompt || "Generating...",
        promptText: job.message,
        isGenerating: true,
      }))
  );
  const renderJobEntries = [...pendingVisibleJobEntries, ...visibleJobEntries];
  const latestThemeCreateEntry = visibleJobEntries.find((entry) =>
    entry.assets.some(
      (asset) =>
        typeof asset.analysis?.theme_create_mode === "string" &&
        (asset.analysis.theme_create_mode === "style_modify" || asset.analysis.theme_create_mode === "style_transfer")
    )
  );

  const sizesLabel =
    selectedSizes.length === 0 ? "Sizes"
    : selectedSizes.length === 1 ? selectedSizes[0]
    : `${selectedSizes[0]} +${selectedSizes.length - 1}`;

  const themeCreateReady =
    hasRoleAssets(themeCreateAssets, "upload") &&
    (
      themeCreateMode === "style_modify"
        ? prompt.trim().length > 0
        : hasRoleAssets(themeCreateAssets, "reference_ad")
    );

  const resizeReady = createFlow === "resize" && resizeSourceAssets.length > 0 && selectedSizes.length > 0;
  const remediationAnalyzedCount = remediationSourceAssets.filter((asset, index) =>
    Boolean(remediationAnalyses[remediationAssetKey(asset, index)])
  ).length;
  const orderedSelectedResizeSizes = RESIZE_SIZE_ORDER.filter((size) => selectedSizes.includes(size));
  const hasAnyResizeOverride =
    orderedSelectedResizeSizes.some((size) => (resizePromptOverrides[size] ?? "").trim().length > 0) ||
    resizeNegativePromptOverride.trim().length > 0;
  const showImageWorkbenchSection = createFlow === "theme_create" || createFlow === "kakao" || createFlow === "resize" || createFlow === "remediation";
  const isKakaoFlow = createFlow === "kakao";
  const remediationFlaggedCount = remediationSourceAssets.filter((asset, index) => {
    const key = remediationAssetKey(asset, index);
    const analysis = remediationAnalyses[asset.id ?? key];
    return Boolean(analysis && analysis.violations.length > 0);
  }).length;
  const remediationAllScanned =
    remediationSourceAssets.length > 0 &&
    remediationAnalyzedCount === remediationSourceAssets.length;
  const remediationPrimaryActionLabel =
    remediationAllScanned && remediationFlaggedCount > 0
      ? `Remediate${remediationFlaggedCount > 1 ? ` ${remediationFlaggedCount}` : ""}`
      : "Scan";

  const canGenerate =
    !generating &&
    !remediationScanning &&
    (
      createFlow === "resize"
        ? resizeReady
        : createFlow === "theme_create"
        ? themeCreateReady
        : createFlow === "remediation"
        ? remediationSourceAssets.length > 0 && (!remediationAllScanned || remediationFlaggedCount > 0)
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
    ? "Generating..."
    : taskProgress < 95
    ? "Preparing"
    : "Finalizing";


  return (
    <>
    <div className="flex flex-1 min-w-0 h-screen overflow-hidden bg-background">

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">

      {/* Header */}
      <div className="shrink-0 border-b px-8 pb-0 pt-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <ImageIcon className="size-5" />
            <h1 className="font-display text-2xl font-semibold">Image</h1>
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
          {/* Thread switcher */}
        <div ref={sessionMenuRef} className="relative flex items-center gap-2">
            {/* Dropdown button */}
            <button
              type="button"
              onClick={() => setSessionMenuOpen((open) => !open)}
              className="flex w-52 items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-left text-sm font-semibold text-foreground transition-colors hover:border-foreground/20"
            >
              <span className="min-w-0 flex-1 truncate">{threadTitle}</span>
              <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", sessionMenuOpen && "rotate-180")} />
            </button>

            {/* New Thread: solid black button, always visible */}
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
              New Thread
            </button>

            {sessionMenuOpen && (
              <div className="absolute left-0 top-[calc(100%+6px)] z-40 w-80 rounded-2xl border border-border bg-card p-2 shadow-2xl">
                <div className="px-2 py-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
                    Threads
                  </p>
                </div>
                <div className="mt-1 max-h-72 space-y-1 overflow-y-auto pr-0.5 [scrollbar-width:thin]">
                  {currentThreads.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border bg-background/70 px-3 py-4 text-xs text-muted-foreground">
                      No threads yet. Start generating to create your first thread.
                    </div>
                  ) : (
                    currentThreads.map((thread) => (
                      <div key={thread.id} className="group relative">
                        {renamingThreadId === thread.id ? (
                          /* Inline rename input */
                          <form
                            onSubmit={async (e) => {
                              e.preventDefault();
                              await renameThread(thread.id, renameValue);
                              const updated = await listThreads(activeWorkspaceId, contentScope);
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
                              {thread.jobCount} runs - {thread.assetCount} assets
                            </p>
                          </button>
                        )}

                        {/* Rename and delete actions shown on hover */}
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
                              title="Delete thread"
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!confirm(`Delete "${thread.title}"? This cannot be undone.`)) return;
                                await deleteThread(thread.id);
                                const updated = await listThreads(activeWorkspaceId, contentScope);
                                setLiveThreads(updated);
                                if (selectedThreadId === thread.id) {
                                  const nextThread = updated.find((item) => item.id !== thread.id) ?? null;
                                  if (nextThread) {
                                    setSelectedThreadId(nextThread.id);
                                    setStartingNewSession(false);
                                    onThreadSelect?.(nextThread.id);
                                  } else {
                                    setSelectedThreadId(null);
                                    setStartingNewSession(true);
                                    onThreadSelect?.(null);
                                  }
                                }
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
            Thread History
          </Badge>
          <span className="hidden text-xs text-muted-foreground">
            {selectedThread
              ? `${selectedThreadAssets.length} assets - ${selectedThreadJobs.length} runs`
              : startingNewSession
              ? "Start a fresh thread."
              : currentThreads.length === 0
              ? "No threads yet."
              : "Select a thread to continue editing."}
          </span>
          <span className="text-xs text-muted-foreground">
            {downloadableAssets.length > 0
              ? `${downloadableAssets.length} assets - ${visibleJobEntries.length} runs in this thread view`
              : "All new generations and edits stay inside thread history."}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto max-w-4xl">
          {/* Generation stream, each card spans full width with an internal 3-column grid */}
          <div className="grid grid-cols-3 gap-6">
          {remediationReviewEntries
            .filter((entry) => !hiddenJobIds.has(entry.id))
            .map((entry) => (
              <RemediationReviewCard
                key={entry.id}
                asset={entry.asset}
                analysis={entry.analysis}
                onRemediate={() => void handleRemediateFromHistory(entry.asset, entry.analysis)}
                onHide={() => setHiddenJobIds((prev) => new Set([...prev, entry.id]))}
                onZoom={setZoomedAsset}
              />
            ))}
          {renderJobEntries
            .filter((e) => !hiddenJobIds.has(e.id))
            .map((jobEntry) => {
              if ("isGenerating" in jobEntry && jobEntry.isGenerating) {
                return (
                  <GenerationCard
                    key={jobEntry.id}
                    assets={[]}
                    title={jobEntry.title}
                    promptText={jobEntry.promptText}
                    isGenerating
                  />
                );
              }
              const isThemeCreateEntry = jobEntry.assets.some(
                (asset) =>
                  typeof asset.analysis?.theme_create_mode === "string" &&
                  (asset.analysis.theme_create_mode === "style_modify" || asset.analysis.theme_create_mode === "style_transfer")
              );
              return (
                <GenerationCard
                  key={jobEntry.id}
                  assets={jobEntry.assets}
                  title={jobEntry.title}
                  promptText={jobEntry.promptText}
                  selectedAssetIds={selectedAssetIds}
                  onToggleSelect={toggleAsset}
                  onUseAsSource={
                    isThemeCreateEntry
                      ? (asset) => setThemeAssetFromExistingAsset("upload", asset)
                      : undefined
                  }
                  onUseAsReference={
                    isThemeCreateEntry
                      ? (asset) => setThemeAssetFromExistingAsset("reference_ad", asset)
                      : undefined
                  }
                  onUseForResize={
                    (asset) => setResizeSourceFromExistingAsset(asset)
                  }
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
              );
            })}
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

          {/* Empty state shown when the grid is empty */}
          {!isTaskRunning &&
            remediationReviewEntries.filter((entry) => !hiddenJobIds.has(entry.id)).length === 0 &&
            renderJobEntries.filter((e) => !hiddenJobIds.has(e.id)).length === 0 && (
            <div className="flex min-h-[240px] flex-col items-center justify-center gap-4 rounded-3xl border border-dashed border-border bg-muted/20 text-center">
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

      {/* Bottom input bar floating over history */}
      <div className="relative min-h-0 shrink-0 overflow-visible bg-background px-6 pb-4 pt-2" style={{ maxHeight: "calc(100svh - 120px)" }}>
        {/* Gradient fade so history content dissolves into the bar */}
        <div className="pointer-events-none absolute inset-x-0 bottom-full h-16 bg-gradient-to-t from-background to-transparent" />
        <div className="mx-auto max-w-5xl">

          {/* PSD info banner */}
          {psdInfo && (
            <div className="mb-2 flex items-start gap-2 rounded-xl border border-accent/30 bg-soft-accent px-3 py-2.5">
              <p className="flex-1 text-xs text-accent">{psdInfo}</p>
              <button type="button" onClick={() => setPsdInfo(null)} className="shrink-0">
                <X className="size-3.5 text-accent" />
              </button>
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div className="mb-2 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5">
              <p className="flex-1 text-xs text-destructive">{error}</p>
              <button type="button" onClick={() => setError(null)} className="shrink-0">
                <X className="size-3.5 text-destructive" />
              </button>
            </div>
          )}

          {/* Input card */}
          {isTaskRunning && (
            <div className="mb-2 overflow-hidden rounded-xl border border-accent/25 bg-soft-accent/50 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <Loader2 className="size-3.5 animate-spin text-accent" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-accent">
                    {taskMessage || `${taskStatusLabel}...`}
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

          <WorkbenchShell
            ref={barRef}
            autoHeight
            showExpandControl={false}
            className={cn(
              "focus-within:shadow-[0_2px_20px_rgba(0,0,0,0.10)]",
              isDragUploading && "border-accent bg-soft-accent/10 shadow-[0_0_0_1px_rgba(34,197,94,0.18)]"
            )}
            onDragOver={handleWorkbenchDragOver}
            onDragLeave={handleWorkbenchDragLeave}
            onDrop={handleWorkbenchDrop}
            overlay={isDragUploading && createFlow !== "kakao" ? (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-[28px] border-2 border-dashed border-accent bg-background/70 backdrop-blur-[1px]">
                <div className="rounded-full border border-accent/30 bg-card px-4 py-2 text-sm font-medium text-accent">
                  Drop images to upload
                </div>
              </div>
            ) : null}
          >
            {/* Task type tabs: Resize | Theme Create */}
            <div className="shrink-0 border-b border-border px-4 pt-3">
              {CREATE_FLOW_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setCreateFlow(tab.id)}
                  className={cn(
                    "relative px-3.5 pb-3 text-sm font-medium transition-colors",
                    createFlow === tab.id
                      ? "font-semibold text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {tab.label}
                  {createFlow === tab.id ? (
                    <span className="absolute bottom-0 left-0 h-0.5 w-full rounded-full bg-foreground" />
                  ) : null}
                </button>
              ))}
            </div>

            {/* Scrollable form sections to keep textarea and chips visible */}
            <div
              className={cn(
                "overflow-y-auto [scrollbar-width:thin]",
                isKakaoFlow
                  ? "max-h-[calc(100svh-280px)] flex-none"
                  : showImageWorkbenchSection
                  ? "max-h-[calc(100svh-280px)] flex-none"
                  : "h-0 min-h-0 flex-none overflow-hidden"
              )}
            >

            {createFlow === "theme_create" && (
              <div className="space-y-3 border-t border-border px-4 py-3">
                <div className="grid gap-2 md:grid-cols-2">
                  <ThemeAssetInput
                    title="Source Image"
                    hint=""
                    required
                    file={themeCreateAssets.upload?.[0] ?? null}
                    onPreview={setThemeCreatePreviewFile}
                    onPick={(file) => setSingleThemeAsset("upload", file)}
                    onClear={() => setSingleThemeAsset("upload", null)}
                    onDropFiles={(files) => appendThemeCreateFiles(files, "upload")}
                  />

                  <ThemeAssetInput
                    title="Reference Image"
                    hint=""
                    file={themeCreateAssets.reference_ad?.[0] ?? null}
                    onPreview={setThemeCreatePreviewFile}
                    onPick={(file) => setSingleThemeAsset("reference_ad", file)}
                    onClear={() => setSingleThemeAsset("reference_ad", null)}
                    onDropFiles={(files) => appendThemeCreateFiles(files, "reference_ad")}
                  />
                </div>
              </div>
            )}

            {/* Resize source image thumbnail chip */}
            {createFlow === "resize" && resizeSourceAssets.length > 0 && (
              <div className="border-t border-border px-4 py-3">
                <div className="flex flex-wrap gap-1.5">
                {resizeSourceAssets.map((asset, index) => (
                  <div key={`${asset.name}-${index}`} className="group relative flex items-center gap-2 rounded-lg border border-accent/40 bg-soft-accent/30 px-2 py-1">
                    <button
                      type="button"
                      onClick={() => openDraftPreviewFromSourceAsset(asset, index)}
                      className="size-7 shrink-0 overflow-hidden rounded-md border border-accent/20 transition-transform hover:scale-[1.03]"
                      title="Preview image"
                    >
                      <img src={asset.url} alt="" className="h-full w-full object-cover" />
                    </button>
                    <span className="max-w-[120px] truncate text-xs text-foreground">{asset.name}</span>
                    <button type="button" onClick={() => removeResizeSourceAsset(index)} className="text-muted-foreground hover:text-foreground">
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => void handleGenerateGifFromResizeSource()}
                  disabled={generating || uploadingSource || resizeSourceAssets.length !== 1}
                  className={cn(
                    "rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
                    generating || uploadingSource || resizeSourceAssets.length !== 1
                      ? "cursor-not-allowed border-border bg-muted text-muted-foreground"
                      : "border-border bg-background/80 text-foreground hover:border-foreground/20 hover:bg-muted"
                  )}
                >
                  Generate GIF
                </button>
                </div>
              </div>
            )}

            {createFlow === "resize" && resizeSourceAssets.length === 0 && (
              <div className="border-t border-border px-4 py-3">
                <div className="flex min-h-[72px] items-center rounded-xl border border-dashed border-border bg-background/50 px-3 text-sm text-muted-foreground">
                  Tap + below to add a source image from your computer or Library, then choose target sizes.
                </div>
              </div>
            )}

            {createFlow === "remediation" && remediationSourceAssets.length > 0 && (
              <div className="border-t border-border px-4 py-3">
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-foreground">Source Images</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {remediationAnalyzedCount > 0
                          ? remediationAllScanned
                            ? remediationFlaggedCount > 0
                              ? `${remediationAnalyzedCount}/${remediationSourceAssets.length} scanned. ${remediationFlaggedCount} image${remediationFlaggedCount > 1 ? "s are" : " is"} ready. Use the Remediate button below to fix them in one batch.`
                              : `${remediationAnalyzedCount}/${remediationSourceAssets.length} scanned. No policy violations were found.`
                            : `${remediationAnalyzedCount}/${remediationSourceAssets.length} scanned. Click Scan again after uploading more images.`
                          : "Upload one or more creatives, then click Scan to detect policy violations."}
                      </p>
                    </div>
                    <span className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                      {remediationSourceAssets.length}/{MAX_REMEDIATION_SOURCE_IMAGES}
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {remediationSourceAssets.map((asset, index) => {
                      const key = remediationAssetKey(asset, index);
                      const analysis = remediationAnalyses[key];
                      const sourceSize = remediationOutputSize(asset);

                      return (
                        <div
                          key={`analysis_${asset.name}_${index}`}
                          className="group relative flex items-center gap-2 rounded-lg border border-border bg-background px-2 py-1.5"
                        >
                          <button
                            type="button"
                            onClick={() => openDraftPreviewFromSourceAsset(asset, index)}
                            className="size-9 shrink-0 overflow-hidden rounded-md border border-border transition-transform hover:scale-[1.03]"
                            title="Preview image"
                          >
                            <img src={asset.url} alt={asset.name} className="h-full w-full object-cover" />
                          </button>
                          <div className="min-w-0">
                            <p className="max-w-[140px] truncate text-xs font-medium text-foreground">{asset.name}</p>
                            <div className="mt-0.5 flex items-center gap-1.5">
                              {sourceSize ? (
                                <span className="text-[10px] text-muted-foreground">{sourceSize}</span>
                              ) : null}
                              <span
                                className={cn(
                                  "rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
                                  analysis
                                    ? remediationRiskTone(analysis.overall_risk)
                                    : "border-border bg-muted text-muted-foreground"
                                )}
                              >
                                {analysis ? `${analysis.overall_risk} risk` : "Pending"}
                              </span>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeRemediationSourceAsset(index)}
                            className="text-muted-foreground transition-colors hover:text-foreground"
                          >
                            <X className="size-3.5" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {createFlow === "remediation" && remediationSourceAssets.length === 0 && (
              <div className="border-t border-border px-4 py-3">
                <div className="flex min-h-[72px] items-center rounded-xl border border-dashed border-border bg-background/50 px-3 text-sm text-muted-foreground">
                  Tap + below to upload creatives. We will scan each image first, then generate a compliant version in the same original size.
                </div>
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
              multiple
              className="sr-only"
              onChange={(e) => {
                if (createFlow === "resize") {
                  appendResizeSourceFiles(e.target.files);
                } else if (createFlow === "remediation") {
                  void appendRemediationSourceFiles(e.target.files);
                }
                e.target.value = "";
              }}
            />
            {/* Kakao Bizboard batch flow */}
            {createFlow === "kakao" && (
              <div className="h-full">
                <KakaoFlow
                  activeWorkspaceId={activeWorkspaceId}
                  currentThreadId={currentThreadIdForWrites ?? null}
                  onThreadResolved={(threadId) => {
                    setSelectedThreadId(threadId);
                    setStartingNewSession(false);
                    onThreadSelect?.(threadId);
                  }}
                  onAssetsCreated={() => {
                    Promise.all([listAssets(activeWorkspaceId, contentScope), listThreads(activeWorkspaceId, contentScope)])
                      .then(([a, t]) => {
                        setLiveAssets(a);
                        setLiveThreads(t);
                      })
                      .catch(() => {});
                  }}
                  onOpenBuilder={(assets) => {
                    handleOpenKakaoBatch(assets);
                  }}
                />
              </div>
            )}

            </div>{/* end scrollable form sections */}

            {createFlow !== "kakao" && <textarea
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.nativeEvent.isComposing || e.keyCode === 229) {
                  return;
                }
                if (e.key === "Enter" && !e.shiftKey && canGenerate) {
                  e.preventDefault();
                  handleGenerate();
                }
              }}
              placeholder={
                createFlow === "resize"
                  ? resizeSourceAssets.length > 0
                    ? "Optional note on the resize (e.g. focus on the logo)..."
                    : "Tap + to upload a source image, then send to resize..."
                  : createFlow === "theme_create"
                  ? themeCreateMode === "style_modify"
                    ? "Write the full style-modification prompt here. Example: the 2026 World Cup broadcast treatment."
                    : themeCreateMode === "style_transfer"
                    ? "Optional extra direction. Leave blank to use the standard zero-loss style transfer prompt."
                    : "Theme Create prompt..."
                  : createFlow === "remediation"
                  ? remediationSourceAssets.length > 0
                    ? "Optional note for the remediation pass. Each image will keep its original uploaded size."
                    : "Tap + to upload creatives. We will scan violations first, then remediate each image at its original size."
                  : mode === "image"
                  ? "Describe the image you want to generate..."
                  : "Describe your endcard creative..."
              }
              rows={2}
              className="h-[72px] w-full resize-none bg-transparent px-4 py-2 text-sm leading-6 outline-none placeholder:text-muted-foreground"
            />}

            {/* Chip row, hidden for Kakao */}
            {createFlow !== "kakao" &&
            <div className="flex items-center gap-1.5 px-4 pb-3 pt-2">

              {/* Model chip */}
              {createFlow === "theme_create" ? (
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
              ) : (
                <div className="flex items-center rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  Model - Gemini 3.1 Flash
                </div>
              )}

              {/* Size chip: multi-select for Resize, one Gemini-native output for Theme Create, original-size output for Remediation */}
              {createFlow === "resize" ? (
                <div className="relative">
                  <ChipButton
                    label={`Size - ${selectedSizes.length || "0"}`}
                    active={activeChip === "sizes"}
                    onClick={() => toggleChip("sizes")}
                  />
                  {activeChip === "sizes" && (
                    <DropdownPanel className="left-0 w-52">
                      <p className="px-3 pb-1 pt-1.5 text-[11px] text-muted-foreground">
                        Target Sizes - {selectedSizes.length} selected
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
              ) : createFlow === "theme_create" ? (
                <div className="relative">
                  <ChipButton
                    label={`Size - ${selectedSizes[0] === "1080x1920" ? "9:16" : "16:9"}`}
                    active={activeChip === "sizes"}
                    onClick={() => toggleChip("sizes")}
                  />
                  {activeChip === "sizes" && (
                    <DropdownPanel className="left-0 w-64">
                      <DropdownLabel>Gemini-native output</DropdownLabel>
                      {THEME_CREATE_SIZES.map((size) => (
                        <DropdownItem
                          key={size.id}
                          label={size.label}
                          selected={selectedSizes[0] === size.id}
                          onClick={() => {
                            setSelectedSizes([size.id]);
                            setActiveChip(null);
                          }}
                        />
                      ))}
                    </DropdownPanel>
                  )}
                </div>
              ) : createFlow === "remediation" ? (
                <div className="flex items-center rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  Output - Original size
                </div>
              ) : (
                <div className="flex items-center rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  1200x628
                </div>
              )}

              {createFlow === "resize" && selectedSizes.some((size) => RESIZE_GACHA_DISCLOSURE_SIZES.has(size)) && (
                <button
                  type="button"
                  onClick={() => setIncludeResizeGachaDisclosure((value) => !value)}
                  className={cn(
                    "flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium transition-all",
                    includeResizeGachaDisclosure
                      ? "border-accent/50 bg-soft-accent text-accent"
                      : "border-border text-muted-foreground hover:text-foreground"
                  )}
                >
                  Gacha content
                </button>
              )}

              {/* GIF toggle for Resize only */}
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

              {SHOW_THEME_CREATE_PRESET_CHIP && createFlow === "theme_create" && (
                <div className="relative">
                  <ChipButton
                    label="Preset Library"
                    active={activeChip === "presets"}
                    onClick={() => toggleChip("presets")}
                  />
                  {activeChip === "presets" && (
                    <DropdownPanel className="left-0 w-[560px] max-w-[calc(100vw-48px)] overflow-hidden p-0">
                      <div className="border-b border-border px-4 py-3">
                        <p className="text-sm font-semibold text-foreground">Preset Library</p>
                        <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                          Browse saved GM presets and load one directly into the prompt box.
                        </p>
                      </div>

                      <div className="max-h-[360px] overflow-y-auto [scrollbar-width:thin]">
                        <div className="border-b border-border px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-foreground">2026 World Cup Edition</p>
                              <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                                Packed stadium lights, championship greens and golds, sports-broadcast energy.
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() =>
                                applyThemeCreatePreset({
                                  promptTemplate: THEME_CREATE_WORLD_CUP_2026_PROMPT,
                                  styleName: "2026 World Cup Edition",
                                  styleDetails: "Packed stadium lights, championship greens and golds, sports-broadcast energy.",
                                  name: "2026 World Cup Edition",
                                  description: "Packed stadium lights, championship greens and golds, sports-broadcast energy.",
                                })
                              }
                              className="shrink-0 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
                            >
                              Use Preset
                            </button>
                          </div>
                        </div>

                        {themeCreatePresetLoading ? (
                          <div className="px-4 py-6 text-sm text-muted-foreground">Loading presets...</div>
                        ) : themeCreatePresets.length === 0 ? (
                          <div className="px-4 py-6 text-sm text-muted-foreground">
                            No saved preset assets yet. Save a strong Theme Create result and it will appear here.
                          </div>
                        ) : (
                          <div className="divide-y divide-border">
                            {themeCreatePresets.map((preset) => (
                              <div key={preset.id} className="px-4 py-3">
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                      <p className="text-sm font-medium text-foreground">{preset.name}</p>
                                      {preset.isOfficial && (
                                        <Badge variant="secondary" className="text-[10px]">
                                          Official
                                        </Badge>
                                      )}
                                    </div>
                                    <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                                      {preset.description}
                                    </p>
                                    <p className="mt-1 text-[10px] uppercase tracking-[0.08em] text-muted-foreground/70">
                                      {preset.themeCreateMode === "style_modify" ? "Style Modify" : "Style Transfer"}
                                    </p>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => applyThemeCreatePreset(preset)}
                                    className="shrink-0 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
                                  >
                                    Use Preset
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </DropdownPanel>
                  )}
                </div>
              )}

              {/* Cancel button visible only while generating */}
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

              <div className={cn(!isTaskRunning && "ml-auto")}>
                <WorkbenchFooterActions
                  uploadTitle={
                    createFlow === "resize"
                      ? `Upload source images (${resizeSourceAssets.length}/${MAX_RESIZE_SOURCE_IMAGES})`
                      : createFlow === "remediation"
                        ? `Upload source images (${remediationSourceAssets.length}/${MAX_REMEDIATION_SOURCE_IMAGES})`
                        : undefined
                  }
                  onUpload={() => {
                    if (createFlow === "resize" && resizeSourceAssets.length < MAX_RESIZE_SOURCE_IMAGES) {
                      resizeFileRef.current?.click();
                    } else if (createFlow === "remediation" && remediationSourceAssets.length < MAX_REMEDIATION_SOURCE_IMAGES) {
                      resizeFileRef.current?.click();
                    }
                  }}
                  onChooseFromLibrary={
                    createFlow === "resize" && resizeSourceAssets.length < MAX_RESIZE_SOURCE_IMAGES
                      ? () => setResizeLibraryPickerOpen(true)
                      : undefined
                  }
                  uploadDisabled={
                    (createFlow !== "resize" && createFlow !== "remediation") ||
                    (createFlow === "resize" && resizeSourceAssets.length >= MAX_RESIZE_SOURCE_IMAGES) ||
                    (createFlow === "remediation" && remediationSourceAssets.length >= MAX_REMEDIATION_SOURCE_IMAGES)
                  }
                  uploadActive={
                    (createFlow === "resize" && resizeSourceAssets.length > 0) ||
                    (createFlow === "remediation" && remediationSourceAssets.length > 0)
                  }
                  onPrimary={() => void handleGenerate()}
                  primaryDisabled={!canGenerate}
                  primaryLoading={generating || remediationScanning}
                  primaryLabel={createFlow === "remediation" ? remediationPrimaryActionLabel : undefined}
                />
              </div>

            </div>}

          </WorkbenchShell>
        </div>
      </div>

      </div>{/* end main column */}

      {/* Right assets panel */}
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

          {/* Select row */}
          {downloadableAssets.length > 0 && (
            <div className="shrink-0 border-b border-border px-4 py-2">
              <div className="flex items-center justify-between gap-3">
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
                <button
                  type="button"
                  onClick={() => {
                    if (assetPanelSelectMode) {
                      setAssetPanelSelectMode(false);
                      setSelectedAssetIds(new Set());
                      return;
                    }
                    setAssetPanelSelectMode(true);
                  }}
                  className={cn(
                    "rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors",
                    assetPanelSelectMode
                      ? "border-foreground bg-foreground text-background"
                      : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  {assetPanelSelectMode ? "Unselect" : "Select"}
                </button>
              </div>
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
                  const formatLabel = getAssetFileExtension(asset).toUpperCase();
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
                        onClick={() => {
                          if (assetPanelSelectMode) {
                            toggleAsset(asset.id);
                            return;
                          }
                          setPreviewState({ assets: downloadableAssets, index: downloadableAssets.findIndex((item) => item.id === asset.id) });
                        }}
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
                            ? `${asset.width}x${asset.height} - ${formatLabel}`
                            : formatLabel}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="shrink-0 space-y-2 border-t border-border p-3">
            {(selectedKakaoEligibleAssets.length > 0 || selectedGifEligibleAssets.length > 0) && (
              <div className="grid grid-cols-2 gap-2">
                {selectedKakaoEligibleAssets.length > 0 && (
                  <button
                    type="button"
                    onClick={() => handleOpenKakaoBatch()}
                    disabled={generating}
                    className={cn(
                      "flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium transition-all",
                      generating
                        ? "cursor-not-allowed border-border bg-muted text-muted-foreground"
                        : "border-border bg-background text-foreground hover:bg-muted"
                    )}
                  >
                    {generating ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                    {selectedKakaoEligibleAssets.length === 1
                      ? "Create Kakao"
                      : `Create Kakao (${selectedKakaoEligibleAssets.length})`}
                  </button>
                )}
                {selectedGifEligibleAssets.length > 0 && (
                  <button
                    type="button"
                    onClick={handleGenerateGifSelected}
                    disabled={generating}
                    className={cn(
                      "flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium transition-all",
                      generating
                        ? "cursor-not-allowed border-border bg-muted text-muted-foreground"
                        : "border-border bg-background text-foreground hover:bg-muted",
                      selectedKakaoEligibleAssets.length === 0 && "col-span-2"
                    )}
                  >
                    {generating ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                    {selectedGifEligibleAssets.length === 1
                      ? "Generate GIF"
                      : `Generate GIF (${selectedGifEligibleAssets.length})`}
                  </button>
                )}
              </div>
            )}
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
              {downloading
                ? "Preparing..."
                : selectedAssetIds.size === 0
                ? "Select to download"
                : selectedAssetIds.size === 1
                ? "Download"
                : `Download ${selectedAssetIds.size}`}
            </button>
            <button
              type="button"
              onClick={handleDeleteSelected}
              disabled={selectedAssetIds.size === 0}
              className={cn(
                "flex w-full items-center justify-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium transition-all",
                selectedAssetIds.size > 0
                  ? "border-destructive/30 bg-background text-destructive hover:bg-destructive/10"
                  : "cursor-not-allowed border-border bg-background text-muted-foreground"
              )}
            >
              <Trash2 className="size-4" />
              {selectedAssetIds.size === 0 ? "Select to delete" : `Delete ${selectedAssetIds.size}`}
            </button>
          </div>
        </aside>
      )}

    </div>

    {/* Image zoom modal */}
    {kakaoBatchOpen && (
      <KakaoBatchModal
        assets={kakaoBatchAssets}
        submitting={kakaoBatchSubmitting}
        template={kakaoBatchTemplate}
        appIconUrl={kakaoBatchAppIconUrl}
        appCopy={kakaoBatchAppDownloadCopy}
        mainCopy={kakaoBatchMainCopy}
        subCopy={kakaoBatchSubCopy}
        additionalInfo={kakaoBatchAdditionalInfo}
        gacha={kakaoBatchGacha}
        previewUrl={kakaoBatchPreviewUrl}
        validationErrors={kakaoBatchValidationErrors}
        mainCopyWidthPx={kakaoBatchMainCopyWidthPx}
        onClose={() => {
          if (!kakaoBatchSubmitting) {
            setKakaoBatchOpen(false);
            setKakaoBatchAssets([]);
            kakaoObjects.reset();
          }
        }}
        onSubmit={handleGenerateKakaoSelected}
        onTemplateChange={setKakaoBatchTemplate}
        onAppIconChange={handleKakaoBatchIconChange}
        setGacha={setKakaoBatchGacha}
        onAppCopyChange={setKakaoBatchAppDownloadCopy}
        onMainCopyChange={setKakaoBatchMainCopy}
        onSubCopyChange={setKakaoBatchSubCopy}
        onAdditionalInfoChange={setKakaoBatchAdditionalInfo}
        onApplyChanges={rebuildKakaoBatchPreview}
        previewBusy={kakaoBatchPreviewBusy}
        previewAssetIndex={kakaoBatchPreviewAssetIndex}
        onPreviewAssetChange={setKakaoBatchPreviewAssetIndex}
        objectUrl={(() => {
          const asset = kakaoBatchAssets[kakaoBatchPreviewAssetIndex] ?? kakaoBatchAssets[0];
          return asset ? kakaoObjects.objectUrlFor(asset) : null;
        })()}
        objectBusy={kakaoObjects.removing}
        objectError={kakaoObjects.error}
        onRemoveBackgrounds={() => void kakaoObjects.removeBackgrounds(kakaoBatchAssets)}
        onUploadObject={(file) => {
          const asset = kakaoBatchAssets[kakaoBatchPreviewAssetIndex] ?? kakaoBatchAssets[0];
          if (asset) kakaoObjects.uploadObject(asset.id, file);
        }}
      />
    )}

    {resizeLibraryPickerOpen && (
      <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="resize-library-title" onMouseDown={() => setResizeLibraryPickerOpen(false)}>
        <div className="flex max-h-[86vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
          <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
            <div><p className="text-xs font-semibold uppercase tracking-[0.13em] text-accent">Resize source</p><h2 id="resize-library-title" className="mt-1 text-lg font-semibold">Choose an image from Library</h2><p className="mt-1 text-sm text-muted-foreground">Choose an existing image to add as a Resize source. You can add up to {MAX_RESIZE_SOURCE_IMAGES} images.</p></div>
            <button type="button" onClick={() => setResizeLibraryPickerOpen(false)} className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close Library picker"><X className="size-4" /></button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            {liveAssets.filter((asset) => asset.type === "image" && asset.url && !asset.url.includes("placeholder")).length ? (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {liveAssets.filter((asset) => asset.type === "image" && asset.url && !asset.url.includes("placeholder")).map((asset) => {
                  const alreadyAdded = resizeSourceAssets.some((item) => item.id === asset.id);
                  return <button key={asset.id} type="button" onClick={() => addResizeSourceFromLibrary(asset)} disabled={alreadyAdded || resizeSourceAssets.length >= MAX_RESIZE_SOURCE_IMAGES} className={cn("overflow-hidden rounded-xl border bg-card text-left transition", alreadyAdded ? "cursor-not-allowed opacity-55" : "hover:-translate-y-0.5 hover:border-accent/70 hover:shadow-md")}><img src={asset.url} alt={asset.title} className="aspect-square w-full object-cover" /><div className="flex items-center justify-between gap-2 p-3"><span className="min-w-0 truncate text-xs font-semibold">{asset.title}</span><span className="shrink-0 text-[10px] font-medium text-accent">{alreadyAdded ? "Added" : "Use image"}</span></div></button>;
                })}
              </div>
            ) : <div className="rounded-xl border border-dashed bg-muted/20 px-6 py-16 text-center"><ImageIcon className="mx-auto size-7 text-muted-foreground" /><p className="mt-3 text-sm font-semibold">No images in Library yet</p><p className="mt-1 text-sm text-muted-foreground">Upload an image from your computer first, then return here to reuse it.</p></div>}
          </div>
        </div>
      </div>
    )}

    {zoomedAsset && (
      <ZoomModal
        asset={zoomedAsset}
        onClose={() => setZoomedAsset(null)}
        onRegenerate={handleRegenerateAsset}
      />
    )}

    {themeCreatePreviewFile && (
      <ThemeDraftPreviewModal
        file={themeCreatePreviewFile}
        onClose={() => setThemeCreatePreviewFile(null)}
      />
    )}

    {/* Inpainting canvas modal */}
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

    </>
  );
}
