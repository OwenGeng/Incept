"use client";

import { useEffect, useMemo, useRef, useState, type Dispatch, type DragEvent, type SetStateAction } from "react";
import { Check, ChevronDown, Film, FileCode2, FileText, ImageIcon, Loader2, Plus, Sparkles, VideoIcon, X } from "lucide-react";
import type { AssetSummary, CreativeThreadSummary, InceptUser, JobSummary, VideoGenerationPlan } from "@incept/shared";
import { cn } from "@/lib/utils";
import { createVideoGenerationJob, createVideoPlan, getAssetFileExtension, listAssets, listThreads, listVideoPlans, uploadAsset, type ContentScope } from "@/lib/incept-api";
import { DocsButton, FeedbackButton } from "@/components/incept/FeedbackButton";
import { StudioWorkbenchLayout } from "@/components/incept/StudioWorkbenchLayout";
import { WorkbenchShell } from "@/components/incept/WorkbenchShell";
import { WorkbenchFooterActions } from "@/components/incept/WorkbenchFooterActions";
import { Badge } from "@/components/ui/badge";

type AspectRatio = "16:9" | "9:16";
type DurationSeconds = 4 | 6 | 8 | 15 | 30 | 60;
type Variants = 1 | 2;
type ModelId = "veo-3.1-fast";
type Resolution = "720p" | "1080p";
type VideoSurfaceMode = "image_to_video" | "playable_to_video" | "competitor_style_transfer" | "video_to_playable";
type ActiveChip = "model" | "ratio" | "duration" | "resolution" | "variants" | null;

type UploadSlot = {
  assetId: string | null;
  name: string;
  previewUrl: string;
  uploading: boolean;
  mediaType: "image" | "video" | "html" | "report";
};

const MODEL_OPTIONS: Array<{ id: ModelId; label: string; sub: string }> = [
  { id: "veo-3.1-fast", label: "Veo 3.1 Fast", sub: "Faster iteration" },
];

const ASPECT_OPTIONS: AspectRatio[] = ["16:9", "9:16"];
const VEO_DURATION_OPTIONS: DurationSeconds[] = [4, 6, 8, 15, 30, 60];
const PLAYABLE_CAPTURE_DURATION_OPTIONS: DurationSeconds[] = [15, 30];
const RESOLUTION_OPTIONS: Resolution[] = ["720p", "1080p"];
const VARIANT_OPTIONS: Variants[] = [1, 2];

// Keep the work-in-progress flow available in code without exposing it to users yet.
const SHOW_VIDEO_TO_PLAYABLE = false;

function durationOptionDetails(duration: DurationSeconds): { label: string; sub?: string } {
  if (duration === 15) return { label: "15s", sub: "Beat-driven Veo sequence" };
  if (duration === 30) return { label: "30s", sub: "Multi-beat Veo sequence" };
  if (duration === 60) return { label: "60s", sub: "Long-form Veo sequence" };
  return { label: `${duration}s` };
}

function DropdownPanel({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "absolute bottom-[calc(100%+8px)] z-50 min-w-[180px] overflow-hidden rounded-2xl border border-border bg-card shadow-xl",
        className,
      )}
    >
      {children}
    </div>
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
      className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted/60"
    >
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate", selected && "font-medium")}>{label}</span>
        {sub ? <span className="mt-0.5 block text-[11px] leading-5 text-muted-foreground">{sub}</span> : null}
      </span>
      {selected ? <Check className="size-3.5 shrink-0 text-foreground" /> : null}
    </button>
  );
}

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
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {label}
      <ChevronDown className="size-3.5" />
    </button>
  );
}

function AssetPill({
  slot,
  label,
  onOpen,
  onReplace,
  onClear,
}: {
  slot: UploadSlot;
  label: string;
  onOpen: () => void;
  onReplace: () => void;
  onClear: () => void;
}) {
  return (
    <div className="group flex items-center gap-2 rounded-xl border border-accent/30 bg-soft-accent/25 px-2.5 py-2">
      <button
        type="button"
        onClick={onOpen}
        className="relative size-11 shrink-0 overflow-hidden rounded-lg border border-accent/20 bg-[#07111F]"
      >
        {slot.mediaType === "image" ? (
          <img src={slot.previewUrl} alt={slot.name} className="h-full w-full object-cover" />
        ) : slot.mediaType === "video" ? (
          <video src={slot.previewUrl} className="h-full w-full object-cover" muted playsInline preload="metadata" />
        ) : (
          <div className="grid h-full w-full place-items-center bg-[#07111F]">
            <FileCode2 className="size-5 text-white/70" />
          </div>
        )}
        {slot.uploading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-black/35">
            <Loader2 className="size-4 animate-spin text-white" />
          </div>
        ) : null}
      </button>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{label}</p>
        <p className="truncate text-sm text-foreground">{slot.name}</p>
      </div>
      <div className="flex items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
        <button
          type="button"
          onClick={onReplace}
          className="rounded-lg border border-border bg-background/80 px-2 py-1 text-[11px] font-medium text-foreground hover:bg-muted"
        >
          Replace
        </button>
        <button
          type="button"
          onClick={onClear}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

function AddAssetButton({
  title,
  hint,
  onClick,
}: {
  title: string;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-w-[170px] items-center gap-3 rounded-xl border border-dashed border-border bg-background/70 px-3 py-2.5 text-left transition-colors hover:bg-muted/50"
    >
      <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-dashed border-border bg-card">
        <Plus className="size-4 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="truncate text-xs text-muted-foreground">{hint}</p>
      </div>
    </button>
  );
}

function MediaLightbox({
  asset,
  onClose,
}: {
  asset: { url: string; name: string; mediaType: "image" | "video" | "html" | "report" };
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/75 px-4 py-8" onClick={onClose}>
      <div
        className="max-h-[90vh] max-w-5xl overflow-hidden rounded-3xl border border-white/10 bg-[#07111F]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-4 text-white">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{asset.name}</p>
            <p className="text-xs text-white/60">Preview</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-full bg-white/10 p-2">
            <X className="size-4" />
          </button>
        </div>
        <div className="bg-black p-4">
          {asset.mediaType === "video" ? (
            <video src={asset.url} controls playsInline className="max-h-[78vh] w-auto max-w-full rounded-2xl object-contain" />
          ) : asset.mediaType === "image" ? (
            <img src={asset.url} alt={asset.name} className="max-h-[78vh] w-auto max-w-full rounded-2xl object-contain" />
          ) : (
            <iframe src={asset.url} title={asset.name} className="h-[78vh] w-[min(90vw,960px)] rounded-2xl bg-white" />
          )}
        </div>
      </div>
    </div>
  );
}

function ResultCard({
  asset,
  active,
  onOpen,
}: {
  asset: AssetSummary;
  active?: boolean;
  onOpen: () => void;
}) {
  const label =
    asset.width && asset.height
      ? `${asset.width}×${asset.height} · ${getAssetFileExtension(asset).toUpperCase()}`
      : getAssetFileExtension(asset).toUpperCase();

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group overflow-hidden rounded-2xl border bg-card text-left transition-all hover:border-foreground/15 hover:shadow-[0_8px_24px_rgba(0,0,0,0.08)]",
        active ? "border-accent shadow-[0_0_0_1px_hsl(var(--accent)/0.35)]" : "border-border",
      )}
    >
      <div className="relative aspect-video overflow-hidden bg-[#07111F]">
        {asset.type === "video" ? (
          <video src={asset.url} className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]" muted playsInline preload="metadata" />
        ) : asset.type === "playable" ? (
          <iframe src={asset.url} title={asset.title} className="h-full w-full border-0 bg-white pointer-events-none" tabIndex={-1} />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-muted/20">
            <div className="flex flex-col items-center gap-2 text-muted-foreground">
              <FileText className="size-8" />
              <span className="text-[11px] font-medium uppercase tracking-[0.08em]">Report</span>
            </div>
          </div>
        )}
        <div className="absolute bottom-2 left-2 rounded-full bg-black/65 px-2.5 py-1 text-[10px] font-semibold text-white backdrop-blur-sm">
          {label}
        </div>
      </div>
      <div className="px-3 py-3">
        <p className="truncate text-sm font-medium text-foreground">{asset.title}</p>
        <p className="mt-1 truncate text-xs text-muted-foreground">{asset.model || "Video generation"}</p>
      </div>
    </button>
  );
}

export interface CreateVideoViewProps {
  liveAssets: AssetSummary[];
  setLiveAssets: Dispatch<SetStateAction<AssetSummary[]>>;
  liveJobs: JobSummary[];
  liveThreads: CreativeThreadSummary[];
  setLiveThreads: Dispatch<SetStateAction<CreativeThreadSummary[]>>;
  currentUser: InceptUser;
  contentScope: ContentScope;
  activeWorkspaceId: string;
  activeThreadId?: string | null;
  onThreadSelect?: (id: string | null) => void;
  onJobCreated: (job: JobSummary) => void;
}

export function CreateVideoView({
  liveAssets,
  setLiveAssets,
  liveJobs,
  liveThreads,
  setLiveThreads,
  currentUser,
  contentScope,
  activeWorkspaceId,
  activeThreadId,
  onThreadSelect,
  onJobCreated,
}: CreateVideoViewProps) {
  const [surfaceMode, setSurfaceMode] = useState<VideoSurfaceMode>("image_to_video");
  const [draft, setDraft] = useState("");
  const [model, setModel] = useState<ModelId>("veo-3.1-fast");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("16:9");
  const [durationSeconds, setDurationSeconds] = useState<DurationSeconds>(8);
  const [resolution, setResolution] = useState<Resolution>("720p");
  const [variants, setVariants] = useState<Variants>(1);
  const includeAudio = false;
  const [activeChip, setActiveChip] = useState<ActiveChip>(null);
  const [sending, setSending] = useState(false);
  const [sourceImage, setSourceImage] = useState<UploadSlot | null>(null);
  const [referenceImages, setReferenceImages] = useState<UploadSlot[]>([]);
  const [lightbox, setLightbox] = useState<{ url: string; name: string; mediaType: "image" | "video" | "html" | "report" } | null>(null);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [threadMenuOpen, setThreadMenuOpen] = useState(false);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(activeThreadId ?? null);
  const [startingNewThread, setStartingNewThread] = useState(!activeThreadId);
  const [focusedOutputId, setFocusedOutputId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [workbenchExpanded, setWorkbenchExpanded] = useState(false);
  const [workbenchMinimized, setWorkbenchMinimized] = useState(false);
  const composerView = workbenchMinimized ? "compact" : workbenchExpanded ? "expanded" : "standard";
  const [isDragUploading, setIsDragUploading] = useState(false);
  const [isReferenceDragUploading, setIsReferenceDragUploading] = useState(false);
  const [videoPlan, setVideoPlan] = useState<VideoGenerationPlan | null>(null);
  const [reviewPrompt, setReviewPrompt] = useState("");
  const [planning, setPlanning] = useState(false);
  const [pendingConversationMessage, setPendingConversationMessage] = useState<string | null>(null);
  const [activeGenerationJob, setActiveGenerationJob] = useState<JobSummary | null>(null);
  const [generationClock, setGenerationClock] = useState(() => Date.now());

  const sourceInputRef = useRef<HTMLInputElement | null>(null);
  const referencesInputRef = useRef<HTMLInputElement | null>(null);
  const threadMenuRef = useRef<HTMLDivElement | null>(null);
  const barRef = useRef<HTMLDivElement | null>(null);
  const restoredThreadRef = useRef<string | null>(null);

  const videoThreads = useMemo(
    () => liveThreads.filter((thread) => thread.generationMode === "video"),
    [liveThreads],
  );

  useEffect(() => {
    if (activeThreadId) {
      setSelectedThreadId(activeThreadId);
      setStartingNewThread(false);
      return;
    }
    if (!startingNewThread && videoThreads[0]?.id) {
      setSelectedThreadId(videoThreads[0].id);
    }
  }, [activeThreadId, startingNewThread, videoThreads]);

  useEffect(() => {
    function handleOutside(event: MouseEvent) {
      if (!threadMenuRef.current?.contains(event.target as Node)) {
        setThreadMenuOpen(false);
      }
    }
    if (threadMenuOpen) {
      document.addEventListener("mousedown", handleOutside);
      return () => document.removeEventListener("mousedown", handleOutside);
    }
  }, [threadMenuOpen]);

  useEffect(() => {
    if (!activeChip) return;
    function handleOutside(event: MouseEvent) {
      if (!barRef.current?.contains(event.target as Node)) {
        setActiveChip(null);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [activeChip]);

  useEffect(() => {
    if (surfaceMode === "playable_to_video" && !PLAYABLE_CAPTURE_DURATION_OPTIONS.includes(durationSeconds)) {
      setDurationSeconds(30);
    } else if (surfaceMode !== "playable_to_video" && !VEO_DURATION_OPTIONS.includes(durationSeconds)) {
      setDurationSeconds(8);
    }
  }, [durationSeconds, surfaceMode]);

  const currentThreadId = startingNewThread ? null : selectedThreadId ?? videoThreads[0]?.id ?? null;
  const selectedThread = currentThreadId ? videoThreads.find((thread) => thread.id === currentThreadId) ?? null : null;
  const threadTitle = startingNewThread ? "New Thread" : selectedThread?.title ?? videoThreads[0]?.title ?? "New Thread";
  const threadMessages = selectedThread?.messages ?? [];

  function slotFromAsset(asset: AssetSummary): UploadSlot {
    return {
      assetId: asset.id,
      name: asset.title,
      previewUrl: asset.url,
      uploading: false,
      mediaType:
        asset.type === "video"
          ? "video"
          : asset.type === "playable"
            ? "html"
            : asset.type === "report"
              ? "report"
              : "image",
    };
  }

  const currentThreadOutputs = useMemo(
    () =>
      liveAssets
        .filter((asset) => {
          if (asset.type !== "video" && asset.type !== "report" && asset.type !== "playable") return false;
          if (asset.type === "report" && (asset.analysis?.video_plan || asset.title.endsWith("_video_plan"))) return false;
          if (!currentThreadId) return false;
          return asset.threadId === currentThreadId;
        })
        .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()),
    [currentThreadId, liveAssets],
  );

  const pendingJobs = useMemo(
    () =>
      liveJobs.filter(
        (job) =>
          job.toolId === "veo-video" &&
          job.threadId === currentThreadId &&
          (job.status === "running" || job.status === "queued"),
      ),
    [currentThreadId, liveJobs],
  );

  const failedJobs = useMemo(
    () =>
      liveJobs.filter(
        (job) => job.toolId === "veo-video" && job.threadId === currentThreadId && job.status === "failed",
      ),
    [currentThreadId, liveJobs],
  );
  const activeLiveGenerationJob = activeGenerationJob
    ? liveJobs.find((job) => (job.jobId ?? job.id) === (activeGenerationJob.jobId ?? activeGenerationJob.id)) ?? activeGenerationJob
    : null;
  const trackedGenerationJob = activeLiveGenerationJob ?? pendingJobs[0] ?? null;
  const trackedGenerationJobId = trackedGenerationJob?.jobId ?? trackedGenerationJob?.id;
  const hasCapturedOutput = Boolean(
    trackedGenerationJobId &&
      liveAssets.some(
        (asset) => asset.jobId === trackedGenerationJobId && asset.type === "video",
      ),
  );
  const generationInProgress = Boolean(
    trackedGenerationJob &&
      !hasCapturedOutput &&
      (trackedGenerationJob.status === "queued" || trackedGenerationJob.status === "running" || trackedGenerationJob.status === "pending"),
  );

  useEffect(() => {
    if (!activeLiveGenerationJob) return;
    if (hasCapturedOutput || activeLiveGenerationJob.status === "completed" || activeLiveGenerationJob.status === "failed") {
      setActiveGenerationJob(null);
    }
  }, [activeLiveGenerationJob, hasCapturedOutput]);

  useEffect(() => {
    if (!generationInProgress || !trackedGenerationJobId) return;
    const interval = window.setInterval(() => {
      void refreshThreadTimeline();
    }, 10_000);
    return () => window.clearInterval(interval);
  }, [generationInProgress, trackedGenerationJobId]);

  useEffect(() => {
    if (!generationInProgress) return;
    const interval = window.setInterval(() => setGenerationClock(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [generationInProgress]);

  const generationElapsedSeconds = useMemo(() => {
    if (!trackedGenerationJob?.createdAt) return 0;
    const startedAt = new Date(trackedGenerationJob.createdAt).getTime();
    return Number.isFinite(startedAt) ? Math.max(0, Math.floor((generationClock - startedAt) / 1000)) : 0;
  }, [generationClock, trackedGenerationJob?.createdAt]);
  const generationElapsedLabel = generationElapsedSeconds >= 60
    ? `${Math.floor(generationElapsedSeconds / 60)}m ${generationElapsedSeconds % 60}s`
    : `${generationElapsedSeconds}s`;

  const requiresPlan = ["image_to_video", "competitor_style_transfer", "video_to_playable"].includes(surfaceMode);
  const durationOptions = surfaceMode === "playable_to_video" ? PLAYABLE_CAPTURE_DURATION_OPTIONS : VEO_DURATION_OPTIONS;
  const hasReadySource =
    Boolean(sourceImage?.assetId) &&
    !sourceImage?.uploading &&
    !referenceImages.some((item) => item.uploading);
  const canSubmitAgentMessage =
    !sending &&
    !planning &&
    hasReadySource &&
    (!requiresPlan || !videoPlan || Boolean(draft.trim()));

  useEffect(() => {
    if (currentThreadOutputs.length === 0) {
      setFocusedOutputId(null);
      return;
    }
    if (focusedOutputId && currentThreadOutputs.some((asset) => asset.id === focusedOutputId)) {
      return;
    }
    setFocusedOutputId(currentThreadOutputs[0]?.id ?? null);
  }, [currentThreadOutputs, focusedOutputId]);

  useEffect(() => {
    let active = true;
    const switchedThread = Boolean(restoredThreadRef.current && restoredThreadRef.current !== currentThreadId);
    if (switchedThread) {
      setSourceImage(null);
      setReferenceImages([]);
    }
    restoredThreadRef.current = currentThreadId;
    if (!currentThreadId) {
      setVideoPlan(null);
      return () => { active = false; };
    }
    void listVideoPlans(currentThreadId)
      .then((plans) => {
        if (!active) return;
        const matchingPlan = plans.find(
          (plan) =>
            plan.plan.mode === surfaceMode &&
            (switchedThread || !sourceImage?.assetId || plan.plan.source_asset_id === sourceImage.assetId),
        );
        setVideoPlan(matchingPlan?.plan ?? null);
        if (!matchingPlan) return;

        const sourceAsset = liveAssets.find((asset) => asset.id === matchingPlan.plan.source_asset_id);
        if (sourceAsset && (switchedThread || !sourceImage?.assetId)) {
          setSourceImage(slotFromAsset(sourceAsset));
        }
        const referenceSlots = matchingPlan.plan.reference_asset_ids
          .map((assetId) => liveAssets.find((asset) => asset.id === assetId))
          .filter((asset): asset is AssetSummary => Boolean(asset))
          .map(slotFromAsset);
        if (switchedThread) {
          setReferenceImages(referenceSlots);
        } else if (referenceSlots.length > 0) {
          setReferenceImages((current) => {
            const knownIds = new Set(current.map((slot) => slot.assetId));
            const missing = referenceSlots.filter((slot) => !knownIds.has(slot.assetId));
            return missing.length > 0 ? [...current, ...missing] : current;
          });
        }
      })
      .catch(() => {
        if (active) setVideoPlan(null);
      });
    return () => { active = false; };
  }, [currentThreadId, liveAssets, sourceImage?.assetId, surfaceMode]);

  useEffect(() => {
    if (videoPlan?.generation_prompt) {
      setReviewPrompt(videoPlan.generation_prompt);
    }
  }, [videoPlan?.generation_prompt, videoPlan?.plan_id]);

  const focusedOutput = currentThreadOutputs.find((asset) => asset.id === focusedOutputId) ?? currentThreadOutputs[0] ?? null;
  const planMessages = useMemo(() => {
    if (!videoPlan) return [];
    const rawTurns = Array.isArray(videoPlan.conversation) ? (videoPlan.conversation as unknown[]) : [];
    const normalized = rawTurns.flatMap((turn, index) => {
      if (typeof turn === "string" && turn.trim()) {
        return [{ role: "user" as const, text: turn.trim(), createdAt: `legacy-${index}` }];
      }
      if (turn && typeof turn === "object") {
        const candidate = turn as { role?: unknown; text?: unknown; created_at?: unknown; createdAt?: unknown };
        if (typeof candidate.text === "string" && candidate.text.trim()) {
          return [{
            role: candidate.role === "assistant" ? "assistant" as const : "user" as const,
            text: candidate.text.trim(),
            createdAt: typeof candidate.created_at === "string"
              ? candidate.created_at
              : typeof candidate.createdAt === "string"
                ? candidate.createdAt
                : `turn-${index}`,
          }];
        }
      }
      return [];
    });
    if (!normalized.some((turn) => turn.role === "assistant")) {
      const fallback = videoPlan.summary || videoPlan.objective;
      if (fallback?.trim()) {
        normalized.push({ role: "assistant", text: fallback.trim(), createdAt: "plan-summary" });
      }
    }
    return normalized;
  }, [videoPlan]);
  const timelineMessages = useMemo(() => {
    // Thread messages are the canonical timeline. Plans are only a migration
    // fallback for conversations created before thread-level persistence.
    if (threadMessages.length > 0) {
      return threadMessages
        .filter((message) => message.text !== "Video plan updated. Continue the conversation, or explicitly ask me to generate when you are ready.")
        .map((message) => ({
          role: message.role,
          text: message.text,
          assetIds: message.assetIds,
          createdAt: message.timestamp,
        }));
    }
    return planMessages.map((message) => ({ ...message, assetIds: [] as string[] }));
  }, [planMessages, threadMessages]);
  const visibleTimelineMessages = useMemo(() => {
    if (!pendingConversationMessage) return timelineMessages;
    const alreadySaved = timelineMessages.some(
      (message) => message.role === "user" && message.text === pendingConversationMessage,
    );
    return alreadySaved
      ? timelineMessages
      : [
          ...timelineMessages,
          {
            role: "user" as const,
            text: pendingConversationMessage,
            assetIds: [],
            createdAt: "pending",
          },
        ];
  }, [pendingConversationMessage, timelineMessages]);

  async function refreshThreadTimeline() {
    try {
      const [assets, threads] = await Promise.all([
        listAssets(activeWorkspaceId, contentScope),
        listThreads(activeWorkspaceId, contentScope),
      ]);
      setLiveAssets(assets);
      setLiveThreads(threads);
    } catch {
      // A timeline refresh should not hide a successfully saved conversation turn.
    }
  }
  const usesVeoSettings = surfaceMode === "image_to_video" || surfaceMode === "competitor_style_transfer";
  const usesCaptureSettings = surfaceMode === "playable_to_video";
  const executionModelLabel = usesCaptureSettings
    ? "Browser capture"
    : surfaceMode === "video_to_playable"
      ? "Gemini 3.5 Flash"
      : "Veo 3.1 Fast";
  const executionActionLabel = usesCaptureSettings ? "Record video" : "Generate video";
  function mediaTypeForFile(file: File): UploadSlot["mediaType"] {
    if (file.type.startsWith("video/")) return "video";
    if (file.type.startsWith("image/")) return "image";
    if (file.type === "text/html" || /\.html?$/i.test(file.name)) return "html";
    return "report";
  }

  async function handleUpload(
    file: File,
    role: "working" | "reference",
    setter: (next: UploadSlot | null) => void,
  ) {
    if (role === "working") setVideoPlan(null);
    const mediaType = mediaTypeForFile(file);
    const previewUrl = URL.createObjectURL(file);
    setter({
      assetId: null,
      name: file.name,
      previewUrl,
      uploading: true,
      mediaType,
    });
    try {
      const uploaded = await uploadAsset(file, activeWorkspaceId, role, currentThreadId ?? undefined);
      setSubmitError(null);
      setter({
        assetId: uploaded?.id ?? null,
        name: file.name,
        previewUrl,
        uploading: false,
        mediaType,
      });
      await refreshThreadTimeline();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Asset upload failed.");
      setter({
        assetId: null,
        name: file.name,
        previewUrl,
        uploading: false,
        mediaType,
      });
    }
  }

  async function handlePlan(action: "analyze" | "refine" | "confirm") {
    if (!sourceImage?.assetId || planning) return;
    setPlanning(true);
    setSubmitError(null);
    const userMessage = draft.trim() || "Analyze the attached assets and propose a video generation plan.";
    setPendingConversationMessage(userMessage);
    try {
      const response = await createVideoPlan({
        workspace_id: activeWorkspaceId,
        prompt: draft.trim(),
        created_by: currentUser.id,
        thread_id: currentThreadId ?? undefined,
        source_asset_id: sourceImage.assetId,
        reference_asset_ids: referenceImages.map((item) => item.assetId).filter(Boolean) as string[],
        video_generation_mode: surfaceMode,
        action,
        plan_id: videoPlan?.plan_id,
        aspect_ratio: aspectRatio,
        duration_seconds: durationSeconds,
        resolution,
        variants,
        include_audio: includeAudio,
      });
      setVideoPlan(response.plan);
      setReviewPrompt(response.plan.generation_prompt);
      if (response.plan.thread_id) {
        setSelectedThreadId(response.plan.thread_id);
        setStartingNewThread(false);
        onThreadSelect?.(response.plan.thread_id);
      }
      await refreshThreadTimeline();
      setPendingConversationMessage(null);
      setDraft("");
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Video planning failed.");
      setPendingConversationMessage(null);
    } finally {
      setPlanning(false);
    }
  }

  async function handleReferenceUpload(file: File) {
    const mediaType = mediaTypeForFile(file);
    const previewUrl = URL.createObjectURL(file);
    setReferenceImages((prev) => [
      ...prev,
      { assetId: null, name: file.name, previewUrl, uploading: true, mediaType },
    ]);
    try {
      const uploaded = await uploadAsset(file, activeWorkspaceId, "reference", currentThreadId ?? undefined);
      setSubmitError(null);
      setReferenceImages((prev) =>
        prev.map((item, index) =>
          index === prev.findIndex((candidate) => candidate.previewUrl === previewUrl)
            ? { assetId: uploaded?.id ?? null, name: file.name, previewUrl, uploading: false, mediaType }
            : item,
        ),
      );
      await refreshThreadTimeline();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Reference upload failed.");
      setReferenceImages((prev) =>
        prev.map((item, index) =>
          index === prev.findIndex((candidate) => candidate.previewUrl === previewUrl)
            ? { ...item, uploading: false }
            : item,
        ),
      );
    }
  }

  function sourceAssetLabel() {
    if (surfaceMode === "playable_to_video") return "HTML playable";
    if (surfaceMode === "image_to_video") return "image";
    return "video";
  }

  function acceptsSourceFile(file: File) {
    if (surfaceMode === "playable_to_video") {
      return file.type === "text/html" || /\.html?$/i.test(file.name);
    }
    if (surfaceMode === "image_to_video") return file.type.startsWith("image/");
    return file.type.startsWith("video/");
  }

  function uploadSourceFiles(files: File[]) {
    if (files.length === 0) return;
    if (surfaceMode === "image_to_video") {
      const [source, ...supportingImages] = files.filter((file) => file.type.startsWith("image/"));
      if (!source) {
        setSubmitError("Image to Video accepts image files.");
        return;
      }
      void handleUpload(source, "working", setSourceImage);
      supportingImages.forEach((file) => void handleReferenceUpload(file));
      return;
    }
    const source = files[0];
    if (!acceptsSourceFile(source)) {
      setSubmitError(`This mode accepts a ${sourceAssetLabel()} source file.`);
      return;
    }
    void handleUpload(source, "working", setSourceImage);
  }

  function handleWorkbenchDragOver(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setIsDragUploading(true);
  }

  function handleWorkbenchDragLeave(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    event.stopPropagation();
    const nextTarget = event.relatedTarget as Node | null;
    if (nextTarget && event.currentTarget.contains(nextTarget)) return;
    setIsDragUploading(false);
  }

  function handleWorkbenchDrop(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    event.stopPropagation();
    setIsDragUploading(false);

    uploadSourceFiles(Array.from(event.dataTransfer.files ?? []));
  }

  function handleReferenceDragOver(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setIsDragUploading(false);
    setIsReferenceDragUploading(true);
  }

  function handleReferenceDragLeave(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    event.stopPropagation();
    const nextTarget = event.relatedTarget as Node | null;
    if (nextTarget && event.currentTarget.contains(nextTarget)) return;
    setIsReferenceDragUploading(false);
  }

  function handleReferenceDrop(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    event.stopPropagation();
    setIsReferenceDragUploading(false);
    setIsDragUploading(false);
    const files = Array.from(event.dataTransfer.files ?? []).filter(
      (file) => file.type.startsWith("image/") || file.type.startsWith("video/"),
    );
    if (files.length === 0) {
      setSubmitError("Reference assets must be image or video files.");
      return;
    }
    files.forEach((file) => void handleReferenceUpload(file));
  }

  async function handleSend(planIdOverride?: string) {
    if (!hasReadySource || sending || (requiresPlan && !planIdOverride && !videoPlan?.plan_id)) return;
    setSending(true);
    setSubmitError(null);
    try {
      const response = await createVideoGenerationJob({
        workspace_id: activeWorkspaceId,
        prompt: draft.trim(),
        provider: "gemini",
        model,
        created_by: currentUser.id,
        thread_id: currentThreadId ?? undefined,
        source_asset_id: sourceImage?.assetId ?? undefined,
        reference_asset_ids: referenceImages.map((item) => item.assetId).filter(Boolean) as string[],
        video_generation_mode: surfaceMode,
        aspect_ratio: aspectRatio,
        duration_seconds: durationSeconds,
        resolution,
        variants,
        include_audio: includeAudio,
        plan_id: planIdOverride ?? videoPlan?.plan_id,
        enhance_with_veo_fast: false,
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
        threadId: response.thread_id ?? undefined,
        sourceAssetId: response.source_asset_id ?? undefined,
        message: response.message,
        createdAt: response.created_at,
      };
      setActiveGenerationJob(job);
      onJobCreated(job);
      if (response.thread_id) {
        setSelectedThreadId(response.thread_id);
        setStartingNewThread(false);
        onThreadSelect?.(response.thread_id);
      }
      await refreshThreadTimeline();
      setDraft("");
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Video generation failed.");
    } finally {
      setSending(false);
    }
  }

  async function handleConfirmAndGenerate() {
    if (!sourceImage?.assetId || !videoPlan || planning || sending || generationInProgress) return;
    setPlanning(true);
    setSubmitError(null);
    try {
      const response = await createVideoPlan({
        workspace_id: activeWorkspaceId,
        prompt: "",
        created_by: currentUser.id,
        thread_id: currentThreadId ?? undefined,
        source_asset_id: sourceImage.assetId,
        reference_asset_ids: referenceImages.map((item) => item.assetId).filter(Boolean) as string[],
        video_generation_mode: surfaceMode,
        action: "confirm",
        plan_id: videoPlan.plan_id,
        generation_prompt_override: reviewPrompt.trim(),
        aspect_ratio: aspectRatio,
        duration_seconds: durationSeconds,
        resolution,
        variants,
        include_audio: includeAudio,
      });
      setVideoPlan(response.plan);
      await refreshThreadTimeline();
      await handleSend(response.plan.plan_id);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Could not confirm the execution plan.");
    } finally {
      setPlanning(false);
    }
  }

  async function handlePrimaryAction() {
    if (requiresPlan) {
      await handlePlan(videoPlan ? "refine" : "analyze");
      return;
    }
    await handleSend();
  }

  return (
    <StudioWorkbenchLayout
      title="Video"
      badge={<Badge variant="secondary" className="text-xs">Beta</Badge>}
      headerActions={
        <>
          <FeedbackButton />
          <DocsButton />
        </>
      }
      rightPanelOpen={rightPanelOpen}
      onToggleRightPanel={() => setRightPanelOpen((prev) => !prev)}
      threadControls={
        <>
          <div ref={threadMenuRef} className="relative flex items-center gap-2">
            <button
              type="button"
              onClick={() => setThreadMenuOpen((open) => !open)}
              className="flex w-52 items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-left text-sm font-semibold text-foreground transition-colors hover:border-foreground/20"
            >
              <span className="min-w-0 flex-1 truncate">{threadTitle}</span>
              <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", threadMenuOpen && "rotate-180")} />
            </button>

            <button
              type="button"
              onClick={() => {
                setSelectedThreadId(null);
                setStartingNewThread(true);
                setThreadMenuOpen(false);
                onThreadSelect?.(null);
              }}
              className="flex items-center gap-1.5 rounded-xl bg-foreground px-3 py-2 text-sm font-semibold text-background transition-opacity hover:opacity-80"
            >
              <span className="text-base leading-none">+</span>
              New Thread
            </button>

            {threadMenuOpen ? (
              <div className="absolute left-0 top-[calc(100%+6px)] z-40 w-80 rounded-2xl border border-border bg-card p-2 shadow-2xl">
                <div className="px-2 py-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">Threads</p>
                </div>
                <div className="mt-1 max-h-72 space-y-1 overflow-y-auto pr-0.5 [scrollbar-width:thin]">
                  {videoThreads.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border bg-background/70 px-3 py-4 text-xs text-muted-foreground">
                      No video threads yet. Start generating to create your first thread.
                    </div>
                  ) : (
                    videoThreads.map((thread) => (
                      <button
                        key={thread.id}
                        type="button"
                        onClick={() => {
                          setSelectedThreadId(thread.id);
                          setStartingNewThread(false);
                          setThreadMenuOpen(false);
                          onThreadSelect?.(thread.id);
                        }}
                        className={cn(
                          "w-full rounded-xl border px-3 py-2.5 text-left transition-colors",
                          selectedThreadId === thread.id && !startingNewThread
                            ? "border-accent/40 bg-soft-accent/60"
                            : "border-transparent hover:border-border hover:bg-muted/40",
                        )}
                      >
                        <p className="truncate text-sm font-medium text-foreground">{thread.title}</p>
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {thread.jobCount} runs - {thread.assetCount} assets
                        </p>
                      </button>
                    ))
                  )}
                </div>
              </div>
            ) : null}
          </div>

          <span className="rounded-full border border-border bg-muted/30 px-2.5 py-1 text-[10px] font-medium text-muted-foreground">
            Thread History
          </span>
          <span className="text-xs text-muted-foreground">
            {currentThreadId
              ? `${currentThreadOutputs.length} outputs - ${Math.max(pendingJobs.length, generationInProgress ? 1 : 0)} active runs in this thread view`
              : "All new generations and edits stay inside thread history."}
          </span>
        </>
      }
      bottomBar={
        <div className="mx-auto max-w-5xl">
          <WorkbenchShell
            ref={barRef}
            expanded={workbenchExpanded}
            onToggleExpanded={() => setWorkbenchExpanded((prev) => !prev)}
            minimized={workbenchMinimized}
            onToggleMinimized={() => setWorkbenchMinimized(true)}
            viewMode={composerView}
            onViewModeChange={(mode) => {
              setWorkbenchMinimized(mode === "compact");
              setWorkbenchExpanded(mode === "expanded");
            }}
            minimizedContent={
              <>
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onFocus={() => setWorkbenchMinimized(false)}
                  placeholder="Ask for a video plan or refine the current plan..."
                  className="h-8 min-w-0 flex-1 resize-none bg-transparent px-1 py-1 text-sm leading-6 outline-none placeholder:text-muted-foreground"
                />
                <WorkbenchFooterActions
                  onUpload={() => sourceInputRef.current?.click()}
                  onPrimary={() => void handlePrimaryAction()}
                  uploadTitle="Upload source asset"
                  uploadActive={Boolean(sourceImage?.assetId)}
                  primaryDisabled={!canSubmitAgentMessage}
                  primaryLoading={sending || planning}
                  primaryLabel={undefined}
                />
              </>
            }
            className={cn(
              "focus-within:shadow-[0_2px_20px_rgba(0,0,0,0.10)]",
              isDragUploading && "border-accent bg-soft-accent/10 shadow-[0_0_0_1px_rgba(34,197,94,0.18)]",
            )}
            onDragOver={handleWorkbenchDragOver}
            onDragLeave={handleWorkbenchDragLeave}
            onDrop={handleWorkbenchDrop}
            overlay={
              isDragUploading ? (
                <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center rounded-[28px] border-2 border-dashed border-accent bg-background/75 backdrop-blur-[1px]">
                  <div className="rounded-2xl border border-accent/30 bg-card px-5 py-3 text-center shadow-lg">
                    <p className="text-sm font-semibold text-foreground">Drop {sourceAssetLabel()} to upload</p>
                    <p className="mt-1 text-xs text-muted-foreground">It will be added as this mode&apos;s source asset.</p>
                  </div>
                </div>
              ) : null
            }
            header={
              <div className="border-b border-border px-4 pt-3">
                <div className="flex flex-wrap items-center gap-5 pr-24 text-sm">
                  <button
                    type="button"
                    onClick={() => setSurfaceMode("image_to_video")}
                    className={cn(
                      "relative flex items-center gap-2 pb-3 font-medium transition-colors",
                      surfaceMode === "image_to_video" ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <ImageIcon className="size-4" />
                    Image to Video
                    {surfaceMode === "image_to_video" ? <span className="absolute bottom-0 left-0 h-0.5 w-full rounded-full bg-foreground" /> : null}
                  </button>
                  <button
                    type="button"
                    onClick={() => setSurfaceMode("competitor_style_transfer")}
                    className={cn(
                      "relative flex items-center gap-2 pb-3 font-medium transition-colors",
                      surfaceMode === "competitor_style_transfer" ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <Sparkles className="size-4" />
                    Video to Video
                    {surfaceMode === "competitor_style_transfer" ? <span className="absolute bottom-0 left-0 h-0.5 w-full rounded-full bg-foreground" /> : null}
                  </button>
                  <button
                    type="button"
                    onClick={() => setSurfaceMode("playable_to_video")}
                    className={cn(
                      "relative flex items-center gap-2 pb-3 font-medium transition-colors",
                      surfaceMode === "playable_to_video" ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <FileCode2 className="size-4" />
                    Playable to Video
                    {surfaceMode === "playable_to_video" ? <span className="absolute bottom-0 left-0 h-0.5 w-full rounded-full bg-foreground" /> : null}
                  </button>
                  {SHOW_VIDEO_TO_PLAYABLE ? (
                    <button
                      type="button"
                      onClick={() => setSurfaceMode("video_to_playable")}
                      className={cn(
                        "relative flex items-center gap-2 pb-3 font-medium transition-colors",
                        surfaceMode === "video_to_playable" ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      <VideoIcon className="size-4" />
                      Video to Playable
                      {surfaceMode === "video_to_playable" ? <span className="absolute bottom-0 left-0 h-0.5 w-full rounded-full bg-foreground" /> : null}
                    </button>
                  ) : null}
                </div>
              </div>
            }
            body={
              <div className="px-4 py-2.5">
                {!videoPlan || !requiresPlan || surfaceMode === "video_to_playable" ? (
                <div className="mb-2.5 flex flex-wrap gap-2">
                  {sourceImage ? (
                    <AssetPill
                      slot={sourceImage}
                      label="Source"
                      onOpen={() => setLightbox({ url: sourceImage.previewUrl, name: sourceImage.name, mediaType: sourceImage.mediaType })}
                      onReplace={() => sourceInputRef.current?.click()}
                      onClear={() => setSourceImage(null)}
                    />
                  ) : (
                    <AddAssetButton
                      title={
                        surfaceMode === "playable_to_video"
                          ? "Playable HTML"
                          : surfaceMode === "competitor_style_transfer"
                            ? "Source Video"
                            : surfaceMode === "video_to_playable"
                              ? "Source Video"
                              : "Source Image"
                      }
                      hint={
                        surfaceMode === "playable_to_video"
                          ? "Run and record one Moloco HTML playable."
                          : surfaceMode === "competitor_style_transfer"
                            ? "Upload one video to restyle or regenerate."
                            : surfaceMode === "video_to_playable"
                              ? "Upload one gameplay video to analyze its playable asset brief."
                              : "Upload one image to animate with Veo Fast."
                      }
                      onClick={() => sourceInputRef.current?.click()}
                    />
                  )}

                  {surfaceMode === "competitor_style_transfer" || surfaceMode === "image_to_video" || surfaceMode === "video_to_playable" ? (
                    <div
                      className={cn(
                        "flex flex-wrap gap-2 rounded-xl transition-colors",
                        isReferenceDragUploading && "bg-soft-accent/40 p-1 ring-1 ring-accent/40",
                      )}
                      onDragOver={handleReferenceDragOver}
                      onDragLeave={handleReferenceDragLeave}
                      onDrop={handleReferenceDrop}
                    >
                      {referenceImages.map((slot, index) => (
                        <AssetPill
                          key={`${slot.previewUrl}_${index}`}
                          slot={slot}
                          label={index === 0 ? "Reference" : `Reference ${index + 1}`}
                          onOpen={() => setLightbox({ url: slot.previewUrl, name: slot.name, mediaType: slot.mediaType })}
                          onReplace={() => referencesInputRef.current?.click()}
                          onClear={() => setReferenceImages((prev) => prev.filter((_, currentIndex) => currentIndex !== index))}
                        />
                      ))}
                      <AddAssetButton
                        title={surfaceMode === "video_to_playable" ? "Advertiser Asset" : surfaceMode === "image_to_video" ? "Supporting Image" : "Reference"}
                        hint={isReferenceDragUploading
                          ? "Drop image or video here to use as reference."
                          : surfaceMode === "video_to_playable"
                            ? "Upload provided art, Logo, UI, or end-card images."
                          : surfaceMode === "image_to_video"
                            ? "Optional image for the planning pass."
                            : "Drop an image or video reference here."}
                        onClick={() => referencesInputRef.current?.click()}
                      />
                    </div>
                  ) : null}
                </div>
                ) : null}

                {submitError ? (
                  <div className="mb-2.5 rounded-2xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {submitError}
                  </div>
                ) : null}

                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
                    if (event.key === "Enter" && !event.shiftKey && canSubmitAgentMessage) {
                      event.preventDefault();
                      void handlePrimaryAction();
                    }
                  }}
                  placeholder={
                    requiresPlan && !videoPlan
                      ? "Describe the outcome you want. We will analyze the source and prepare a generation plan before any model runs."
                      : surfaceMode === "video_to_playable"
                        ? "Review or refine the asset brief, then upload advertiser-provided images, logos, UI, and end-card assets."
                      : requiresPlan
                        ? "Continue the conversation, refine the direction, or say “generate” when you are ready."
                      : surfaceMode === "playable_to_video"
                      ? "Describe the gameplay tone, pacing, camera energy, or the ad feeling you want from the uploaded playable."
                      : surfaceMode === "competitor_style_transfer"
                        ? "Describe how the source video should be regenerated: preserve its core concept while changing style, pacing, or motion language."
                        : "Describe the motion, camera movement, pacing, or audio direction for the uploaded image."
                  }
                  className="min-h-[88px] w-full resize-none bg-transparent px-1 py-1 text-sm leading-6 outline-none placeholder:text-muted-foreground"
                />
              </div>
            }
            footer={
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-3 pt-2.5">
                <div className="flex flex-wrap items-center gap-2">
                {usesVeoSettings ? (
                <div className="relative">
                  <ChipButton label="Model" active={activeChip === "model"} onClick={() => setActiveChip((prev) => (prev === "model" ? null : "model"))} />
                  {activeChip === "model" ? (
                    <DropdownPanel className="left-0 w-[240px]">
                      {MODEL_OPTIONS.map((option) => (
                        <DropdownItem
                          key={option.id}
                          label={option.label}
                          sub={option.sub}
                          selected={model === option.id}
                          onClick={() => {
                            setModel(option.id);
                            setActiveChip(null);
                          }}
                        />
                      ))}
                    </DropdownPanel>
                  ) : null}
                </div>
                ) : null}

                {usesVeoSettings || usesCaptureSettings ? <div className="relative">
                  <ChipButton label={aspectRatio} active={activeChip === "ratio"} onClick={() => setActiveChip((prev) => (prev === "ratio" ? null : "ratio"))} />
                  {activeChip === "ratio" ? (
                    <DropdownPanel className="left-0 w-[160px]">
                      {ASPECT_OPTIONS.map((option) => (
                        <DropdownItem
                          key={option}
                          label={option}
                          selected={aspectRatio === option}
                          onClick={() => {
                            setAspectRatio(option);
                            setActiveChip(null);
                          }}
                        />
                      ))}
                    </DropdownPanel>
                  ) : null}
                </div> : null}

                {usesVeoSettings || usesCaptureSettings ? <div className="relative">
                  <ChipButton label={`${durationSeconds}s`} active={activeChip === "duration"} onClick={() => setActiveChip((prev) => (prev === "duration" ? null : "duration"))} />
                  {activeChip === "duration" ? (
                    <DropdownPanel className="left-0 w-[160px]">
                      {durationOptions.map((option) => (
                        <DropdownItem
                          key={option}
                          {...durationOptionDetails(option)}
                          selected={durationSeconds === option}
                          onClick={() => {
                            setDurationSeconds(option);
                            setActiveChip(null);
                          }}
                        />
                      ))}
                    </DropdownPanel>
                  ) : null}
                </div> : null}

                {usesVeoSettings || usesCaptureSettings ? <div className="relative">
                  <ChipButton label={resolution} active={activeChip === "resolution"} onClick={() => setActiveChip((prev) => (prev === "resolution" ? null : "resolution"))} />
                  {activeChip === "resolution" ? (
                    <DropdownPanel className="left-0 w-[170px]">
                      {RESOLUTION_OPTIONS.map((option) => (
                        <DropdownItem
                          key={option}
                          label={option}
                          selected={resolution === option}
                          onClick={() => {
                            setResolution(option);
                            setActiveChip(null);
                          }}
                        />
                      ))}
                    </DropdownPanel>
                  ) : null}
                </div> : null}

                {usesVeoSettings ? <div className="relative">
                  <ChipButton label={`Variants ${variants}`} active={activeChip === "variants"} onClick={() => setActiveChip((prev) => (prev === "variants" ? null : "variants"))} />
                  {activeChip === "variants" ? (
                    <DropdownPanel className="left-0 w-[160px]">
                      {VARIANT_OPTIONS.map((option) => (
                        <DropdownItem
                          key={option}
                          label={String(option)}
                          selected={variants === option}
                          onClick={() => {
                            setVariants(option);
                            setActiveChip(null);
                          }}
                        />
                      ))}
                    </DropdownPanel>
                  ) : null}
                </div> : null}

                {surfaceMode === "video_to_playable" ? (
                  <span className="rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground">
                    Analysis - Gemini 3.5 Flash
                  </span>
                ) : null}
                </div>

                <WorkbenchFooterActions
                  onUpload={() => sourceInputRef.current?.click()}
                  onPrimary={() => void handlePrimaryAction()}
                  uploadTitle="Upload source asset"
                  uploadActive={Boolean(sourceImage?.assetId)}
                  primaryDisabled={!canSubmitAgentMessage}
                  primaryLoading={sending || planning}
                  primaryLabel={undefined}
                />
              </div>
            }
          />

          <input
            ref={sourceInputRef}
            type="file"
            accept={
              surfaceMode === "playable_to_video"
                ? ".html,.htm,text/html"
                : surfaceMode === "competitor_style_transfer"
                  ? "video/*"
                  : surfaceMode === "video_to_playable"
                    ? "video/*"
                    : "image/*"
            }
            multiple={surfaceMode === "image_to_video"}
            className="hidden"
            onChange={(event) => {
              uploadSourceFiles(Array.from(event.target.files ?? []));
              event.currentTarget.value = "";
            }}
          />
          <input
            ref={referencesInputRef}
            type="file"
            accept="image/*,video/*"
            className="hidden"
            multiple
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              files.forEach((file) => void handleReferenceUpload(file));
              event.currentTarget.value = "";
            }}
          />
        </div>
      }
      rightPanel={
        <>
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

          <div className="shrink-0 border-b border-border px-4 py-3">
            <p className="text-xs text-muted-foreground">Generated videos and playable drafts in this thread.</p>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-3 [scrollbar-width:thin]">
            {currentThreadOutputs.length > 0 ? (
              <div className="grid grid-cols-2 gap-2">
                {currentThreadOutputs.map((asset) => (
                  <ResultCard
                    key={asset.id}
                    asset={asset}
                    active={asset.id === focusedOutput?.id}
                    onOpen={() => setFocusedOutputId(asset.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                <Film className="size-8 text-muted-foreground/30" />
                <div>
                  <p className="text-sm font-medium text-foreground">No generated videos yet</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    New video outputs and analysis reports for this thread will appear here.
                  </p>
                </div>
              </div>
            )}
          </div>
        </>
      }
    >
      <div className="mx-auto max-w-5xl">
        {failedJobs.length > 0 ? (
          <div className="mb-4 rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <p className="font-medium">Video task failed</p>
            <p className="mt-1 break-words text-xs leading-5">{failedJobs[0]?.message || "The video workflow did not complete."}</p>
          </div>
        ) : null}

        {visibleTimelineMessages.length > 0 || planning || sending || generationInProgress ? (
          <div className="mx-auto mb-8 max-w-3xl px-2">
            <div className="space-y-5">
              {visibleTimelineMessages.map((message, index) => (
                <div
                  key={`${message.createdAt}_${index}`}
                  className={cn(
                    "max-w-[88%] whitespace-pre-wrap text-sm leading-7 text-foreground",
                    message.role === "user"
                      ? "ml-auto rounded-[24px] rounded-br-md bg-muted px-4 py-3 leading-6"
                      : "px-1",
                  )}
                >
                  {message.text}
                  {message.role === "user" && message.assetIds.length > 0 ? (
                    <div className="mt-3 flex flex-wrap justify-end gap-2">
                      {message.assetIds
                        .map((assetId) => liveAssets.find((asset) => asset.id === assetId))
                        .filter((asset): asset is AssetSummary => Boolean(asset))
                        .map((asset) => (
                          <button
                            key={asset.id}
                            type="button"
                            onClick={() =>
                              setLightbox({
                                url: asset.url,
                                name: asset.title,
                                mediaType: asset.type === "video" ? "video" : asset.type === "playable" ? "html" : "image",
                              })
                            }
                            className="relative size-16 overflow-hidden rounded-xl border border-border/70 bg-card shadow-sm transition-transform hover:scale-[1.03]"
                            title={asset.title}
                          >
                            {asset.type === "video" ? (
                              <video src={asset.url} muted playsInline preload="metadata" className="h-full w-full object-cover" />
                            ) : asset.type === "playable" ? (
                              <div className="flex h-full w-full items-center justify-center bg-muted text-muted-foreground">
                                <FileCode2 className="size-5" />
                              </div>
                            ) : (
                              <img src={asset.url} alt={asset.title} className="h-full w-full object-cover" />
                            )}
                          </button>
                        ))}
                    </div>
                  ) : null}
                  {message.role === "assistant" && message.assetIds.length > 0 ? (
                    <div className="mt-4 grid max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
                      {message.assetIds
                        .map((assetId) => liveAssets.find((asset) => asset.id === assetId))
                        .filter((asset): asset is AssetSummary => Boolean(asset))
                        .map((asset) => (
                          <ResultCard
                            key={asset.id}
                            asset={asset}
                            active={asset.id === focusedOutput?.id}
                            onOpen={() => {
                              setFocusedOutputId(asset.id);
                              setLightbox({
                                url: asset.url,
                                name: asset.title,
                                mediaType: asset.type === "video" ? "video" : asset.type === "playable" ? "html" : "report",
                              });
                            }}
                          />
                        ))}
                    </div>
                  ) : null}
                </div>
              ))}
              {videoPlan && videoPlan.execution_intent === "generate" && requiresPlan && surfaceMode !== "video_to_playable" && !sending && !generationInProgress ? (
                <section className="max-w-2xl rounded-2xl border border-border bg-card p-4 shadow-[0_2px_14px_rgba(0,0,0,0.04)]">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-foreground">Review execution</p>
                      <p className="mt-1 text-xs text-muted-foreground">Confirm the final prompt and chip settings before the model runs.</p>
                    </div>
                    <span className="rounded-full border border-border bg-muted/40 px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                      {executionModelLabel}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="rounded-full border border-border px-2.5 py-1 text-[11px] font-medium text-muted-foreground">{aspectRatio}</span>
                    <span className="rounded-full border border-border px-2.5 py-1 text-[11px] font-medium text-muted-foreground">{durationSeconds}s</span>
                    <span className="rounded-full border border-border px-2.5 py-1 text-[11px] font-medium text-muted-foreground">{resolution}</span>
                    <span className="rounded-full border border-border px-2.5 py-1 text-[11px] font-medium text-muted-foreground">{variants} variant{variants > 1 ? "s" : ""}</span>
                    {usesVeoSettings ? <span className="rounded-full border border-border px-2.5 py-1 text-[11px] font-medium text-muted-foreground">Silent</span> : null}
                  </div>
                  {videoPlan.beats.length > 0 ? (
                    <div className="mt-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Beat plan</p>
                      <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        {videoPlan.beats.map((beat, index) => (
                          <div key={beat.id} className="rounded-xl border border-border/80 bg-muted/20 px-3 py-2.5">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-sm font-semibold text-foreground">{index + 1}. {beat.title}</p>
                              <span className="shrink-0 text-xs font-medium text-muted-foreground">{beat.duration_seconds}s</span>
                            </div>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">{beat.purpose}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <label className="mt-4 block text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground" htmlFor="veo-execution-prompt">
                    {usesVeoSettings ? "Veo prompt" : usesCaptureSettings ? "Capture brief" : "Execution prompt"}
                  </label>
                  <textarea
                    id="veo-execution-prompt"
                    value={reviewPrompt}
                    onChange={(event) => setReviewPrompt(event.target.value)}
                    className="mt-2 min-h-[120px] w-full resize-y rounded-xl border border-border bg-background px-3 py-2.5 text-sm leading-6 outline-none focus:border-foreground/30"
                  />
                  <div className="mt-3 flex justify-end">
                    <button
                      type="button"
                      onClick={() => void handleConfirmAndGenerate()}
                      disabled={!reviewPrompt.trim() || planning}
                      className="rounded-full bg-foreground px-4 py-2 text-sm font-semibold text-background transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {planning ? "Confirming…" : executionActionLabel}
                    </button>
                  </div>
                </section>
              ) : null}
              {planning ? (
                <div className="flex items-center gap-2 px-1 py-1 text-sm text-muted-foreground" aria-live="polite">
                  <span>Thinking</span>
                  <span className="flex items-center gap-1" aria-label="Thinking">
                    <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.2s]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.1s]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
                  </span>
                </div>
              ) : null}
              {sending || generationInProgress ? (
                <div className="max-w-2xl rounded-2xl border border-accent/20 bg-soft-accent/25 px-4 py-3" aria-live="polite">
                  <div className="flex items-center justify-between gap-3 text-sm font-medium text-foreground">
                    <span className="flex items-center gap-2">
                      <Loader2 className="size-4 animate-spin text-accent" />
                      {trackedGenerationJob?.message || (usesCaptureSettings ? "Preparing playable browser capture…" : "Veo is generating your video…")}
                    </span>
                    {generationInProgress ? <span className="shrink-0 text-xs font-normal text-muted-foreground">{generationElapsedLabel}</span> : null}
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-accent/10">
                    <div
                      className="h-full rounded-full bg-accent transition-[width] duration-500"
                      style={{ width: `${Math.max(5, trackedGenerationJob?.progress ?? 5)}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {generationElapsedSeconds >= 480
                      ? usesCaptureSettings
                        ? "Browser capture is taking longer than usual. The workflow will return Chrome or encoding diagnostics if it cannot complete."
                        : "Veo is still processing. This request is taking longer than usual; the workflow will report a timeout if Veo does not respond."
                      : usesCaptureSettings
                        ? "Progress reflects browser launch, automated interactions, frame capture, and MP4 encoding."
                        : "Progress reflects the completed workflow stages. Veo does not expose frame-level progress."}
                  </p>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
        <div className="h-16" />
      </div>
      {lightbox ? <MediaLightbox asset={lightbox} onClose={() => setLightbox(null)} /> : null}
    </StudioWorkbenchLayout>
  );
}
