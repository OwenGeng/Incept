"use client";

import { useEffect, useMemo, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  Clapperboard,
  Film,
  GitBranch,
  ImagePlus,
  Layers3,
  Loader2,
  MessageSquareText,
  Music2,
  Maximize2,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Pencil,
  RefreshCw,
  Send,
  Square,
  Sparkles,
  Upload,
  Trash2,
  Wand2,
  Workflow,
  X,
} from "lucide-react";
import type { AssetSummary, InceptUser } from "@incept/shared";
import { AppHeader } from "@/components/ui/app-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  createVideoProduction,
  cancelVideoProductionDesignSheet,
  cancelVideoProductionCopilot,
  createVideoProductionDesignSheet,
  createVideoProductionShot,
  deleteVideoProduction,
  deleteVideoProductionDesignSheet,
  deleteVideoProductionShot,
  extractVideoProductionBridgeFrame,
  generateVideoProductionDesignSheet,
  generateVideoProductionKeyframe,
  generateVideoProductionShot,
  getJob,
  listAssets,
  listVideoProductions,
  forkVideoProduction,
  lockVideoProductionScript,
  reorderVideoProductionShots,
  reframeVideoProductionScene,
  renderVideoProductionFirstCut,
  runVideoProductionCreativeDirector,
  runVideoProductionDesigner,
  runVideoProductionDirector,
  runVideoProductionEditReviewer,
  runVideoProductionScriptAgent,
  runVideoProductionCopilot,
  updateVideoProduction,
  updateVideoProductionDesignSheet,
  updateVideoProductionShot,
  uploadAsset,
  type ContentScope,
  type VideoProduction,
  type VideoProductionDesignSheet,
  type VideoProductionShot,
  type VideoProductionStage,
} from "@/lib/incept-api";

const STAGES: Array<{ id: VideoProductionStage; label: string; icon: typeof MessageSquareText }> = [
  { id: "direction", label: "Plan", icon: MessageSquareText },
  { id: "script", label: "Script", icon: Wand2 },
  { id: "design", label: "Assets", icon: ImagePlus },
  { id: "storyboard", label: "Storyboard", icon: Layers3 },
  { id: "generate", label: "Video", icon: Sparkles },
  { id: "edit", label: "Edit", icon: Film },
  { id: "deliver", label: "Deliver", icon: Check },
];

interface VideoProductionViewProps {
  liveAssets: AssetSummary[];
  setLiveAssets: Dispatch<SetStateAction<AssetSummary[]>>;
  currentUser: InceptUser;
  contentScope: ContentScope;
  activeWorkspaceId: string;
  onMobileMenuOpen: () => void;
  /** The existing stage-based workspace remains available as Video Production. */
  presentation?: "copilot" | "legacy";
}

function stageIndex(stage: VideoProductionStage): number {
  return STAGES.findIndex((item) => item.id === stage);
}

function stageLabel(stage: VideoProductionStage): string {
  return STAGES.find((item) => item.id === stage)?.label ?? "Direction";
}

function assetTypeLabel(asset: AssetSummary): string {
  if (asset.type === "video") return "Video";
  if (asset.type === "audio") return "Audio";
  if (asset.type === "playable") return "Playable";
  if (asset.type === "gif") return "GIF";
  return "Image";
}

export function VideoProductionView({
  liveAssets,
  setLiveAssets,
  currentUser,
  contentScope,
  activeWorkspaceId,
  onMobileMenuOpen,
  presentation = "copilot",
}: VideoProductionViewProps) {
  const [productions, setProductions] = useState<VideoProduction[]>([]);
  const [activeProductionId, setActiveProductionId] = useState<string | null>(null);
  const [viewedStage, setViewedStage] = useState<VideoProductionStage>("direction");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // React state updates are asynchronous; this ref closes the tiny window in
  // which two Enter presses could otherwise start two Copilot turns at once.
  const copilotSendingRef = useRef(false);
  const copilotAbortRef = useRef<AbortController | null>(null);
  const [copilotThinkingMessage, setCopilotThinkingMessage] = useState<string | null>(null);
  // Frame-level requests must not freeze the entire production queue. A
  // Set-like list also lets users start independent Veo jobs for S01 and S02.
  const [busyShotIds, setBusyShotIds] = useState<string[]>([]);
  const [batchGenerating, setBatchGenerating] = useState(false);
  const [agentDraft, setAgentDraft] = useState("");
  const [copilotAttachmentIds, setCopilotAttachmentIds] = useState<string[]>([]);
  const [copilotThinkingAttachmentIds, setCopilotThinkingAttachmentIds] = useState<string[]>([]);
  // The Video workspace has two deliberate, user-facing modes. Workflow is
  // the constrained production map; Storyboard is the visual shot board.
  // Stage detail editors remain available on demand instead of occupying the
  // whole workspace by default.
  const [workspaceView, setWorkspaceView] = useState<"workflow" | "storyboard">("workflow");
  const [branchDialogOpen, setBranchDialogOpen] = useState(false);
  const [branchLabel, setBranchLabel] = useState("Variant");
  const [assetPickerOpen, setAssetPickerOpen] = useState(false);
  const [assetPickerTab, setAssetPickerTab] = useState<"library" | "local">("library");
  const [assetPickerPurpose, setAssetPickerPurpose] = useState<"project" | "message">("project");
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [pendingEndSceneShotId, setPendingEndSceneShotId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [productionMenuOpen, setProductionMenuOpen] = useState(false);
  const [assetsDrawerOpen, setAssetsDrawerOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<VideoProduction | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<VideoProduction | null>(null);
  const customerAInputRef = useRef<HTMLInputElement>(null);
  const customerBInputRef = useRef<HTMLInputElement>(null);

  const activeProduction = useMemo(
    () => productions.find((item) => item.production_id === activeProductionId) ?? null,
    [activeProductionId, productions],
  );
  const selectedShot = useMemo(
    () => activeProduction?.shots.find((shot) => shot.id === selectedShotId) ?? activeProduction?.shots[0] ?? null,
    [activeProduction, selectedShotId],
  );
  const customerAAssets = useMemo(() => {
    if (!activeProduction) return [];
    const linkedReferenceIds = new Set(activeProduction.asset_links.filter((link) => link.role === "reference").map((link) => link.asset_id));
    return liveAssets.filter((asset) => linkedReferenceIds.has(asset.id) || (!activeProduction.asset_links.length && activeProduction.reference_asset_ids.includes(asset.id)));
  }, [activeProduction, liveAssets]);
  const customerBAssets = useMemo(() => {
    if (!activeProduction) return [];
    const linkedBrandIds = new Set(activeProduction.asset_links.filter((link) => link.role !== "reference").map((link) => link.asset_id));
    return liveAssets.filter((asset) => linkedBrandIds.has(asset.id));
  }, [activeProduction, liveAssets]);

  const replaceProduction = (next: VideoProduction) => {
    setProductions((previous) => [next, ...previous.filter((item) => item.production_id !== next.production_id)]);
    setActiveProductionId(next.production_id);
    if (!selectedShotId && next.shots[0]) setSelectedShotId(next.shots[0].id);
  };

  const refreshProduction = async (productionId = activeProductionId) => {
    if (!productionId) return;
    const items = await listVideoProductions(activeWorkspaceId, contentScope);
    const next = items.find((item) => item.production_id === productionId);
    if (next) replaceProduction(next);
  };

  const watchProductionJob = (productionId: string, jobId: string) => {
    const interval = window.setInterval(() => {
      void getJob(jobId).then((job) => {
        if (!job || (job.status !== "completed" && job.status !== "failed")) return;
        window.clearInterval(interval);
        void Promise.all([refreshProduction(productionId), listAssets(activeWorkspaceId, contentScope).then(setLiveAssets)])
          .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not refresh production output."));
      });
    }, 1800);
  };

  useEffect(() => {
    let active = true;
    setLoading(true);
    listVideoProductions(activeWorkspaceId, contentScope)
      .then((items) => {
        if (!active) return;
        const requestedProductionId = window.sessionStorage.getItem("incept.openProductionId");
        const requestedProduction = requestedProductionId ? items.find((item) => item.production_id === requestedProductionId) : null;
        if (requestedProductionId) window.sessionStorage.removeItem("incept.openProductionId");
        setProductions(items);
        setActiveProductionId((current) => requestedProduction?.production_id ?? current ?? items[0]?.production_id ?? null);
        setViewedStage(presentation === "legacy" ? (requestedProduction?.stage ?? items[0]?.stage ?? "direction") : "storyboard");
      })
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Could not load productions."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [activeWorkspaceId, contentScope, presentation]);

  const createProduction = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await createVideoProduction({ workspace_id: activeWorkspaceId, title: "Untitled commercial", target_seconds: 30 });
      replaceProduction(created);
      setViewedStage(presentation === "legacy" ? "direction" : "storyboard");
      setAgentDraft("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create the production.");
    } finally {
      setSaving(false);
    }
  };

  const applyUpdate = async (payload: Parameters<typeof updateVideoProduction>[1]) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await updateVideoProduction(activeProduction.production_id, {
        ...payload,
        expected_revision: activeProduction.state_revision,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the production.");
    } finally {
      setSaving(false);
    }
  };

  const openRenameProduction = (production: VideoProduction) => {
    setRenameTarget(production);
    setRenameTitle(production.title);
    setProductionMenuOpen(false);
  };

  const renameProduction = async () => {
    if (!renameTarget) return;
    const title = renameTitle.trim();
    if (!title || title === renameTarget.title) {
      setRenameTarget(null);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await updateVideoProduction(renameTarget.production_id, { title }));
      setRenameTarget(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not rename the production.");
    } finally {
      setSaving(false);
    }
  };

  const openRemoveProduction = (production: VideoProduction) => {
    setDeleteTarget(production);
    setProductionMenuOpen(false);
  };

  const removeProduction = async () => {
    if (!deleteTarget) return;
    setSaving(true);
    setError(null);
    try {
      await deleteVideoProduction(deleteTarget.production_id);
      setProductions((previous) => {
        const remaining = previous.filter((item) => item.production_id !== deleteTarget.production_id);
        const next = remaining[0] ?? null;
        setActiveProductionId(next?.production_id ?? null);
        setViewedStage(presentation === "legacy" ? "direction" : "storyboard");
        return remaining;
      });
      setProductionMenuOpen(false);
      setDeleteTarget(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete the production.");
    } finally {
      setSaving(false);
    }
  };

  const askProductionRole = async (stage = viewedStage, instruction = agentDraft, confirmActionId?: string | null) => {
    if (!activeProduction || copilotSendingRef.current) return;
    const submittedMessage = instruction || activeProduction.pending_confirmation?.proposed_action || "Continue with the next safe production step.";
    const submittedAttachmentIds = copilotAttachmentIds;
    copilotSendingRef.current = true;
    const controller = new AbortController();
    copilotAbortRef.current = controller;
    setCopilotThinkingMessage(submittedMessage);
    setCopilotThinkingAttachmentIds(submittedAttachmentIds);
    setCopilotAttachmentIds([]);
    if (instruction.trim()) setAgentDraft("");
    setSaving(true);
    setError(null);
    try {
      const result = await runVideoProductionCopilot(activeProduction.production_id, {
        message: submittedMessage,
        asset_ids: submittedAttachmentIds,
        stage,
        confirm_action_id: confirmActionId,
      }, controller.signal);
      replaceProduction(result.production);
      if (!result.needs_confirmation) setAgentDraft("");
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      if (instruction.trim()) setAgentDraft(instruction);
      setError(reason instanceof Error ? reason.message : "Production agent could not finish this pass.");
    } finally {
      copilotSendingRef.current = false;
      copilotAbortRef.current = null;
      setCopilotThinkingMessage(null);
      setCopilotThinkingAttachmentIds([]);
      setSaving(false);
    }
  };

  const stopCopilot = () => {
    copilotAbortRef.current?.abort();
    if (activeProduction) void cancelVideoProductionCopilot(activeProduction.production_id);
    copilotAbortRef.current = null;
    copilotSendingRef.current = false;
    setCopilotThinkingMessage(null);
    setSaving(false);
  };

  const createSafeBranch = async () => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const branch = await forkVideoProduction(activeProduction.production_id, branchLabel.trim() || "Variant");
      replaceProduction(branch);
      setBranchDialogOpen(false);
      setBranchLabel("Variant");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create a safe project branch.");
    } finally {
      setSaving(false);
    }
  };

  const lockScript = async () => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const next = await lockVideoProductionScript(activeProduction.production_id);
      replaceProduction(next);
      setSelectedShotId(next.shots[0]?.id ?? null);
      setViewedStage("design");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not lock the script.");
    } finally {
      setSaving(false);
    }
  };

  const approveDirectionAndDraftScript = async (confirmedPackKeys: string[]) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const approved = await updateVideoProduction(activeProduction.production_id, {
        stage: "script",
        creative_direction: { ...activeProduction.creative_direction, status: "approved", confirmed_pack_keys: confirmedPackKeys },
      });
      replaceProduction(approved);
      setViewedStage("script");
      const drafted = await runVideoProductionScriptAgent(approved.production_id, "");
      replaceProduction(drafted);
      setAgentDraft("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not turn the approved direction into a script.");
    } finally {
      setSaving(false);
    }
  };

  const approveDesignAndCreateStoryboard = async () => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const approved = await updateVideoProduction(activeProduction.production_id, {
        design_bible: { ...activeProduction.design_bible, status: "approved" },
      });
      replaceProduction(approved);
      const next = await runVideoProductionDirector(
        approved.production_id,
        "Create the storyboard from the approved script and production design bible.",
      );
      replaceProduction(next);
      setSelectedShotId(next.shots[0]?.id ?? null);
      setViewedStage("storyboard");
      setAgentDraft("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not approve the design and create the storyboard.");
    } finally {
      setSaving(false);
    }
  };

  const saveShot = async (payload: Partial<VideoProductionShot>) => {
    if (!activeProduction || !selectedShot) return;
    return saveShotForId(selectedShot.id, payload);
  };

  const saveShotForId = async (shotId: string, payload: Partial<VideoProductionShot>) => {
    if (!activeProduction) return;
    setBusyShotIds((current) => current.includes(shotId) ? current : [...current, shotId]);
    setError(null);
    try {
      replaceProduction(await updateVideoProductionShot(activeProduction.production_id, shotId, payload));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save this shot.");
    } finally {
      setBusyShotIds((current) => current.filter((id) => id !== shotId));
    }
  };

  const generateKeyframe = async (shot: VideoProductionShot) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const job = await generateVideoProductionKeyframe(activeProduction.production_id, shot.id);
      await refreshProduction(activeProduction.production_id);
      if (!job.jobId) throw new Error("Keyframe generation did not return a job ID.");
      watchProductionJob(activeProduction.production_id, job.jobId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start keyframe generation.");
    } finally {
      setSaving(false);
    }
  };

  const generateStoryboardFrames = async (shots: VideoProductionShot[]) => {
    if (!activeProduction) return;
    const pendingShots = shots.filter((shot) => !shot.keyframe_asset_id && shot.status !== "generating");
    if (!pendingShots.length) return;
    setSaving(true);
    setError(null);
    try {
      const jobs = [];
      for (const shot of pendingShots) {
        jobs.push(await generateVideoProductionKeyframe(activeProduction.production_id, shot.id));
      }
      await refreshProduction(activeProduction.production_id);
      for (const job of jobs) {
        if (job.jobId) watchProductionJob(activeProduction.production_id, job.jobId);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start storyboard frame generation.");
    } finally {
      setSaving(false);
    }
  };

  const createStoryboardFrame = async (payload?: { title: string; purpose?: string; visual?: string; action?: string; duration_seconds?: number }) => {
    if (!activeProduction) return;
    setSaving(true); setError(null);
    try {
      const next = await createVideoProductionShot(activeProduction.production_id, payload ?? { title: `New frame ${activeProduction.shots.length + 1}`, purpose: "Describe the next story moment.", duration_seconds: 3 });
      replaceProduction(next); setSelectedShotId(next.shots.at(-1)?.id ?? null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not add a storyboard frame."); }
    finally { setSaving(false); }
  };

  const reviewVideoTakes = async () => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await runVideoProductionEditReviewer(activeProduction.production_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Edit Reviewer could not inspect the current takes.");
    } finally {
      setSaving(false);
    }
  };

  const deleteStoryboardFrame = async (shot: VideoProductionShot) => {
    if (!activeProduction) return;
    setSaving(true); setError(null);
    try {
      const next = await deleteVideoProductionShot(activeProduction.production_id, shot.id);
      replaceProduction(next); setSelectedShotId(next.shots[0]?.id ?? null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not delete this storyboard frame."); }
    finally { setSaving(false); }
  };

  const uploadDesignSourceImages = async (files: FileList | null): Promise<string[]> => {
    if (!files?.length) return [];
    setSaving(true); setError(null);
    try {
      const ids: string[] = [];
      for (const file of Array.from(files)) {
        const uploaded = await uploadAsset(file, activeWorkspaceId, "brand_element");
        if (uploaded?.id) ids.push(uploaded.id);
      }
      setLiveAssets(await listAssets(activeWorkspaceId, contentScope));
      return ids;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not upload the source image.");
      return [];
    } finally { setSaving(false); }
  };

  const generateDesignSheet = async (sheet: VideoProductionDesignSheet) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const job = await generateVideoProductionDesignSheet(activeProduction.production_id, sheet.id);
      await refreshProduction(activeProduction.production_id);
      if (!job.jobId) throw new Error("Design candidate generation did not return a job ID.");
      watchProductionJob(activeProduction.production_id, job.jobId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start design candidate generation.");
    } finally {
      setSaving(false);
    }
  };

  const cancelDesignSheet = async (sheet: VideoProductionDesignSheet) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await cancelVideoProductionDesignSheet(activeProduction.production_id, sheet.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not stop design generation.");
    } finally {
      setSaving(false);
    }
  };

  const reframeDesignScene = async (
    sheet: VideoProductionDesignSheet,
    sourceAssetId: string,
    outputAspectRatio: "project" | "16:9" | "9:16",
  ) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const job = await reframeVideoProductionScene(activeProduction.production_id, {
        source_asset_id: sourceAssetId,
        output_aspect_ratio: outputAspectRatio,
      });
      await refreshProduction(activeProduction.production_id);
      if (!job.jobId) throw new Error("Scene reframe did not return a job ID.");
      watchProductionJob(activeProduction.production_id, job.jobId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Could not reframe ${sheet.title}.`);
    } finally {
      setSaving(false);
    }
  };

  const createCustomDesignSheet = async (payload: Parameters<typeof createVideoProductionDesignSheet>[1]) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await createVideoProductionDesignSheet(activeProduction.production_id, payload));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create design pack.");
    } finally {
      setSaving(false);
    }
  };

  const updateDesignSheet = async (sheet: VideoProductionDesignSheet, payload: Parameters<typeof updateVideoProductionDesignSheet>[2]) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await updateVideoProductionDesignSheet(activeProduction.production_id, sheet.id, payload));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update design pack.");
    } finally {
      setSaving(false);
    }
  };

  const deleteDesignSheet = async (sheet: VideoProductionDesignSheet) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      await deleteVideoProductionDesignSheet(activeProduction.production_id, sheet.id);
      await refreshProduction(activeProduction.production_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete design pack.");
    } finally {
      setSaving(false);
    }
  };

  const generateDesignSheetBatch = async (
    sheets: VideoProductionDesignSheet[],
    regenerateAll: boolean,
  ) => {
    if (!activeProduction) return;
    const queuedSheets = sheets.filter((sheet) => sheet.status !== "generating" && (
      regenerateAll || (
        !sheet.grid_asset_id
        && !(sheet.panel_asset_ids?.length)
        && !(sheet.approved_asset_ids?.length)
        && !sheet.selected_asset_id
      )
    ));
    if (!queuedSheets.length) return;

    setSaving(true);
    setBatchGenerating(true);
    setError(null);
    try {
      const results = await Promise.allSettled(
        queuedSheets.map((sheet) => generateVideoProductionDesignSheet(activeProduction.production_id, sheet.id)),
      );
      await refreshProduction(activeProduction.production_id);
      const jobs = results.flatMap((result) => {
        if (result.status !== "fulfilled" || !result.value.jobId) return [];
        return [result.value];
      });
      jobs.forEach((job) => watchProductionJob(activeProduction.production_id, job.jobId!));
      const failedCount = results.length - jobs.length;
      if (!jobs.length) throw new Error("Could not start any asset pack generations.");
      if (failedCount) setError(`${failedCount} asset pack${failedCount === 1 ? "" : "s"} could not be started. Check its source requirements and try again.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start asset pack generation.");
    } finally {
      setBatchGenerating(false);
      setSaving(false);
    }
  };

  const generateMissingDesignSheets = async (sheets: VideoProductionDesignSheet[]) => generateDesignSheetBatch(sheets, false);
  const regenerateAllDesignSheets = async (sheets: VideoProductionDesignSheet[]) => generateDesignSheetBatch(sheets, true);

  const generateShot = async (shot: VideoProductionShot, veoPrompt?: string, variants?: 1 | 2) => {
    if (!activeProduction) return;
    setBusyShotIds((current) => current.includes(shot.id) ? current : [...current, shot.id]);
    setError(null);
    try {
      const prompt = veoPrompt?.trim();
      if (prompt !== undefined && prompt !== shot.veo_prompt) {
        replaceProduction(await updateVideoProductionShot(activeProduction.production_id, shot.id, { veo_prompt: prompt }));
      }
      const job = await generateVideoProductionShot(activeProduction.production_id, shot.id, variants ?? shot.generation_variants ?? 2);
      await refreshProduction(activeProduction.production_id);
      if (!job.jobId) throw new Error("Video generation did not return a job ID.");
      watchProductionJob(activeProduction.production_id, job.jobId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start Veo generation.");
    } finally {
      setBusyShotIds((current) => current.filter((id) => id !== shot.id));
    }
  };

  const extractBridgeFrame = async (shot: VideoProductionShot, timestampSeconds: number, targetShotId?: string) => {
    if (!activeProduction) return;
    setBusyShotIds((current) => current.includes(shot.id) ? current : [...current, shot.id]);
    setError(null);
    try {
      replaceProduction(await extractVideoProductionBridgeFrame(activeProduction.production_id, shot.id, {
        source_video_asset_id: shot.selected_video_asset_id ?? shot.video_asset_ids[0],
        timestamp_seconds: timestampSeconds,
        target_shot_id: targetShotId,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not extract a bridge frame.");
    } finally {
      setBusyShotIds((current) => current.filter((id) => id !== shot.id));
    }
  };

  const renderFirstCut = async (includeAudio = false) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const job = await renderVideoProductionFirstCut(activeProduction.production_id, includeAudio);
      if (!job.jobId) throw new Error("First-cut render did not return a job ID.");
      watchProductionJob(activeProduction.production_id, job.jobId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not assemble the first cut.");
    } finally {
      setSaving(false);
    }
  };

  const moveShot = async (direction: -1 | 1) => {
    if (!activeProduction || !selectedShot) return;
    const shots = [...activeProduction.shots].sort((left, right) => left.order - right.order);
    const currentIndex = shots.findIndex((shot) => shot.id === selectedShot.id);
    const nextIndex = currentIndex + direction;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= shots.length) return;
    [shots[currentIndex], shots[nextIndex]] = [shots[nextIndex], shots[currentIndex]];
    setSaving(true);
    try {
      replaceProduction(await reorderVideoProductionShots(activeProduction.production_id, shots.map((shot) => shot.id)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not reorder the storyboard.");
    } finally {
      setSaving(false);
    }
  };

  const attachAssets = async (files: FileList | null, group: "reference" | "brand") => {
    if (!files?.length || !activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const ids: string[] = [];
      for (const file of Array.from(files)) {
        const uploaded = await uploadAsset(file, activeWorkspaceId, group === "reference" ? "reference_ad" : "brand_element");
        if (uploaded?.id) ids.push(uploaded.id);
      }
      const refreshed = await listAssets(activeWorkspaceId, contentScope);
      setLiveAssets(refreshed);
      if (ids.length) {
        const existing = activeProduction.reference_asset_ids;
        const existingLinks = activeProduction.asset_links;
        const nextLinks = ids.filter((id) => !existingLinks.some((link) => link.asset_id === id)).map((asset_id) => ({ asset_id, role: group, label: group === "reference" ? "Creative reference" : "Brand asset" }));
        await applyUpdate({
          // Brand assets belong to the later Design stage. Only a Creative
          // Reference should enter the Strategist's media-analysis set.
          reference_asset_ids: group === "reference"
            ? [...existing, ...ids.filter((id) => !existing.includes(id))]
            : existing,
          asset_links: [...existingLinks, ...nextLinks],
        });
        if (assetPickerPurpose === "message") setCopilotAttachmentIds((current) => [...new Set([...current, ...ids])]);
      }
      if (assetPickerPurpose === "project") setAssetPickerOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Asset upload failed.");
    } finally {
      setSaving(false);
      const input = group === "reference" ? customerAInputRef.current : customerBInputRef.current;
      if (input) input.value = "";
    }
  };

  const removeAttachedAsset = async (assetId: string) => {
    if (!activeProduction) return;
    await applyUpdate({
      reference_asset_ids: activeProduction.reference_asset_ids.filter((id) => id !== assetId),
      asset_links: activeProduction.asset_links.filter((link) => link.asset_id !== assetId),
    });
  };

  const attachLibraryAsset = async (assetId: string) => {
    if (!activeProduction) return;
    const existing = activeProduction.asset_links;
    if (existing.some((link) => link.asset_id === assetId)) {
      if (assetPickerPurpose === "message") setCopilotAttachmentIds((current) => current.includes(assetId) ? current : [...current, assetId]);
      if (assetPickerPurpose === "project") setAssetPickerOpen(false);
      return;
    }
    await applyUpdate({ asset_links: [...existing, { asset_id: assetId, role: "brand", label: "Project asset" }] });
    if (assetPickerPurpose === "message") setCopilotAttachmentIds((current) => current.includes(assetId) ? current : [...current, assetId]);
    if (assetPickerPurpose === "project") setAssetPickerOpen(false);
  };

  if (loading) {
    return <div className="flex flex-1 items-center justify-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>;
  }

  if (!activeProduction) {
    return (
      <main className="flex h-screen min-h-0 flex-1 flex-col overflow-hidden bg-background">
        <AppHeader title="Video" subtitle="Independent video workspace" docsHref="/docs/incept-video-production-workspace" onMobileMenuOpen={onMobileMenuOpen} />
        <div className="flex flex-1 items-center justify-center p-8">
          <Card className="w-full max-w-xl border-dashed p-10 text-center shadow-none">
            <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-muted"><Clapperboard className="size-7" /></div>
            {error ? <>
              <h2 className="mt-5 text-xl font-semibold">Couldn’t load video projects</h2>
              <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-destructive">{error}</p>
              <Button className="mt-6" variant="outline" onClick={() => { setError(null); setLoading(true); void listVideoProductions(activeWorkspaceId, contentScope).then((items) => { setProductions(items); setActiveProductionId(items[0]?.production_id ?? null); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load productions.")).finally(() => setLoading(false)); }} disabled={loading}><RefreshCw className={loading ? "animate-spin" : ""} /> Retry</Button>
            </> : <>
              <h2 className="mt-5 text-xl font-semibold">Start a video project</h2>
              <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">Build a commercial through a locked script, editable shot cards, approved keyframes, production, edit, and delivery.</p>
              <Button className="mt-6" onClick={createProduction} disabled={saving}><Plus /> New production</Button>
            </>}
          </Card>
        </div>
      </main>
    );
  }

  // The original, stage-led product remains deliberately available as a
  // separate workspace. It shares the exact same production records and
  // assets with the Copilot-first Video view; only the presentation differs.
  if (presentation === "legacy") {
    const currentStageIndex = Math.max(0, stageIndex(activeProduction.stage));
    const canLockScript = Boolean(activeProduction.script.raw_script || activeProduction.script.beats.length);
    const availableStageIndex = Math.max(
      currentStageIndex,
      canLockScript ? stageIndex("script") : stageIndex("direction"),
      activeProduction.design_bible.status !== "draft" ? stageIndex("design") : stageIndex("direction"),
      activeProduction.shots.length ? stageIndex("storyboard") : stageIndex("direction"),
    );
    const goToStage = (stage: VideoProductionStage) => {
      setViewedStage(stage);
      void applyUpdate({ stage });
    };
    return (
      <main className="flex h-screen min-h-0 flex-1 flex-col overflow-hidden bg-background">
        <AppHeader
          title="Video Production"
          subtitle="Plan, script, assets, storyboard, video, edit, and delivery"
          docsHref="/docs/incept-video-production-workspace"
          onMobileMenuOpen={onMobileMenuOpen}
          trailingActions={<Button size="sm" variant={assetsDrawerOpen ? "default" : "outline"} className="hidden min-[1161px]:inline-flex" onClick={() => setAssetsDrawerOpen((open) => !open)}><PanelRightOpen /> Assets</Button>}
        />
        <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-background px-6 py-3 max-[900px]:px-4">
          <div className="relative min-w-0">
            <button type="button" onClick={() => setProductionMenuOpen((value) => !value)} className="flex max-w-[300px] items-center gap-2 rounded-xl border bg-card px-3.5 py-2 text-sm font-semibold hover:bg-muted"><Clapperboard className="size-4 text-muted-foreground" /><span className="truncate">{activeProduction.title}</span><ChevronDown className="size-4 text-muted-foreground" /></button>
            {productionMenuOpen ? <div className="absolute left-0 top-[calc(100%+6px)] z-40 w-80 rounded-xl border bg-card p-1.5 shadow-xl">{productions.map((production) => <div key={production.production_id} className={cn("group flex items-center gap-1 rounded-lg px-1 py-1", production.production_id === activeProduction.production_id ? "bg-muted" : "hover:bg-muted")}><button type="button" onClick={() => { setActiveProductionId(production.production_id); setViewedStage(production.stage); setProductionMenuOpen(false); }} className="min-w-0 flex-1 rounded-md px-2 py-1.5 text-left text-sm"><span className="block truncate font-medium">{production.title}</span><span className="mt-0.5 block text-xs text-muted-foreground">{stageLabel(production.stage)} · {production.target_seconds}s</span></button><Button variant="ghost" size="icon" className="size-7 shrink-0" aria-label={`Rename ${production.title}`} onClick={() => openRenameProduction(production)} disabled={saving}><Pencil className="size-3.5" /></Button><Button variant="ghost" size="icon" className="size-7 shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive" aria-label={`Delete ${production.title}`} onClick={() => openRemoveProduction(production)} disabled={saving}><Trash2 className="size-3.5" /></Button></div>)}</div> : null}
          </div>
          <div className="flex items-center gap-2"><Badge variant="outline" className="hidden sm:inline-flex">{activeProduction.target_seconds}s · {activeProduction.aspect_ratio} · {activeProduction.resolution}</Badge><Button size="sm" onClick={createProduction} disabled={saving}><Plus /> New production</Button></div>
        </div>
        <nav className="flex shrink-0 items-center gap-0 overflow-x-auto border-b bg-background px-6 max-[900px]:px-4" aria-label="Video production stages">
          {STAGES.map((item, index) => { const Icon = item.icon; const isCurrent = viewedStage === item.id; const enabled = index <= availableStageIndex; return <button key={item.id} type="button" disabled={!enabled} onClick={() => setViewedStage(item.id)} className={cn("relative flex shrink-0 items-center gap-2 px-4 py-3.5 text-sm font-medium transition", isCurrent ? "text-foreground" : "text-muted-foreground hover:text-foreground", !enabled && "cursor-not-allowed opacity-35")}><Icon className="size-4" />{item.label}{isCurrent ? <span className="absolute inset-x-4 bottom-0 h-0.5 bg-foreground" /> : null}</button>; })}
        </nav>
        {error ? <div className="shrink-0 border-b border-destructive/20 bg-destructive/5 px-6 py-2 text-sm text-destructive">{error}</div> : null}
        <div className="flex min-h-0 flex-1 overflow-hidden max-[900px]:block max-[900px]:overflow-auto">
          <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            {viewedStage === "direction" ? <DirectionWorkspace production={activeProduction} saving={saving} agentDraft={agentDraft} onAgentDraftChange={setAgentDraft} onSend={() => void askProductionRole("direction")} onSave={applyUpdate} onApprove={(confirmedPackKeys) => void approveDirectionAndDraftScript(confirmedPackKeys)} /> : null}
            {viewedStage === "script" ? <ScriptWorkspace production={activeProduction} saving={saving} canLock={canLockScript} agentDraft={agentDraft} onAgentDraftChange={setAgentDraft} onSend={() => void askProductionRole("script")} onComplete={() => void askProductionRole("script", "Complete and enrich the working script using the confirmed plan.")} onSave={applyUpdate} onLock={() => void lockScript()} /> : null}
            {viewedStage === "design" ? <DesignStage production={activeProduction} assets={liveAssets} saving={saving} batchGenerating={batchGenerating} agentDraft={agentDraft} onAgentDraftChange={setAgentDraft} onSend={() => void askProductionRole("design")} onSave={applyUpdate} onGenerateSheet={generateDesignSheet} onCancelSheet={cancelDesignSheet} onReframeScene={reframeDesignScene} onGenerateMissingSheets={generateMissingDesignSheets} onRegenerateAllSheets={regenerateAllDesignSheets} onCreateSheet={createCustomDesignSheet} onUpdateSheet={updateDesignSheet} onDeleteSheet={deleteDesignSheet} onUploadSourceImages={uploadDesignSourceImages} onApproveAndDirect={approveDesignAndCreateStoryboard} /> : null}
            {viewedStage === "storyboard" ? <StoryboardStage production={activeProduction} assets={liveAssets} selectedShot={selectedShot} saving={saving} agentDraft={agentDraft} onAgentDraftChange={setAgentDraft} onSend={() => void askProductionRole("storyboard")} onImproveFrame={(shot) => void generateKeyframe(shot)} onSave={applyUpdate} onSelectShot={setSelectedShotId} onSaveShot={saveShot} onSaveShotForId={saveShotForId} openEndSceneForShotId={pendingEndSceneShotId} onEndScenePickerOpened={() => setPendingEndSceneShotId(null)} onMoveShot={moveShot} onGenerateKeyframe={generateKeyframe} onGenerateAllKeyframes={generateStoryboardFrames} onCreateFrame={createStoryboardFrame} onDeleteFrame={deleteStoryboardFrame} onNextStage={() => goToStage("generate")} /> : null}
            {viewedStage === "generate" ? <GenerateStage production={activeProduction} assets={liveAssets} saving={saving} busyShotIds={busyShotIds} onGenerateShot={generateShot} onExtractBridgeFrame={extractBridgeFrame} onSaveShotForId={saveShotForId} onEditEndScene={(shotId) => { setSelectedShotId(shotId); setPendingEndSceneShotId(shotId); setViewedStage("storyboard"); }} onStageChange={goToStage} /> : null}
            {viewedStage === "edit" ? <EditStage production={activeProduction} assets={liveAssets} saving={saving} busyShotIds={busyShotIds} onRender={renderFirstCut} onSaveShotForId={saveShotForId} onReview={() => void reviewVideoTakes()} onSaveEditPlan={(edit_plan) => void applyUpdate({ edit_plan })} onStageChange={goToStage} /> : null}
            {viewedStage === "deliver" ? <DeliverStage production={activeProduction} assets={liveAssets} saving={saving} onRender={renderFirstCut} /> : null}
          </section>
          {assetsDrawerOpen ? <aside className="flex w-80 shrink-0 flex-col overflow-hidden border-l bg-background max-[1160px]:hidden"><div className="flex items-start justify-between gap-2 border-b px-4 py-3"><div><p className="text-sm font-semibold">Assets</p><p className="mt-0.5 text-xs text-muted-foreground">Creative reference and brand inputs.</p></div><Button variant="ghost" size="icon" className="size-7" onClick={() => setAssetsDrawerOpen(false)} aria-label="Close assets"><X className="size-4" /></Button></div><input ref={customerAInputRef} type="file" className="hidden" multiple accept="image/*,video/*,audio/*,.html,.htm" onChange={(event) => void attachAssets(event.target.files, "reference")} /><input ref={customerBInputRef} type="file" className="hidden" multiple accept="image/*,video/*,audio/*,.html,.htm" onChange={(event) => void attachAssets(event.target.files, "brand")} /><div className="min-h-0 flex-1 overflow-y-auto p-3"><div className="grid gap-4"><ProductionAssetGroup title="Creative Reference" description="Structure, pace, and camera language to learn from." assets={customerAAssets} saving={saving} onUpload={() => customerAInputRef.current?.click()} onDrop={(files) => void attachAssets(files, "reference")} onRemove={(assetId) => void removeAttachedAsset(assetId)} /><ProductionAssetGroup title="Brand Assets" description="Logo, product, characters, screenshots, copy, and audio." assets={customerBAssets} saving={saving} onUpload={() => customerBInputRef.current?.click()} onDrop={(files) => void attachAssets(files, "brand")} onRemove={(assetId) => void removeAttachedAsset(assetId)} /></div></div></aside> : null}
        </div>
      </main>
    );
  }

  return (
    <main className="flex h-screen min-h-0 flex-1 overflow-hidden bg-background">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <AppHeader
        title="Video"
        subtitle="Create, direct, and assemble commercial video"
        docsHref="/docs/incept-video-production-workspace"
        onMobileMenuOpen={onMobileMenuOpen}
      />

      <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-background px-6 py-3 max-[900px]:px-4">
        <div className="flex min-w-0 flex-1 items-center gap-2 overflow-visible">
          <div className="relative min-w-0">
            <button type="button" onClick={() => setProductionMenuOpen((value) => !value)} className="flex max-w-[230px] items-center gap-2 rounded-xl border bg-card px-3 py-2 text-sm font-semibold hover:bg-muted">
            <Clapperboard className="size-4 text-muted-foreground" />
            <span className="truncate">{activeProduction.title}</span><ChevronDown className="size-4 text-muted-foreground" />
            </button>
            {productionMenuOpen ? (
              <div className="absolute left-0 top-[calc(100%+6px)] z-40 w-80 rounded-xl border bg-card p-1.5 shadow-xl">
              {productions.map((production) => <div key={production.production_id} className={cn("group flex items-center gap-1 rounded-lg px-1 py-1", production.production_id === activeProduction.production_id ? "bg-muted" : "hover:bg-muted")}><button type="button" onClick={() => { setActiveProductionId(production.production_id); setViewedStage("storyboard"); setProductionMenuOpen(false); }} className="min-w-0 flex-1 rounded-md px-2 py-1.5 text-left text-sm"><span className="block truncate font-medium">{production.title}</span><span className="mt-0.5 block text-xs text-muted-foreground">{production.shots.length} frame{production.shots.length === 1 ? "" : "s"} · {production.target_seconds}s</span></button><Button variant="ghost" size="icon" className="size-7 shrink-0" aria-label={`Rename ${production.title}`} onClick={() => openRenameProduction(production)} disabled={saving}><Pencil className="size-3.5" /></Button><Button variant="ghost" size="icon" className="size-7 shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive" aria-label={`Delete ${production.title}`} onClick={() => openRemoveProduction(production)} disabled={saving}><Trash2 className="size-3.5" /></Button></div>)}
              </div>
            ) : null}
          </div>
          <div className="hidden rounded-xl border bg-muted/35 p-1 lg:flex" aria-label="Video project view">
            <Button size="sm" variant={viewedStage !== "generate" && viewedStage !== "edit" && workspaceView === "storyboard" ? "secondary" : "ghost"} onClick={() => { setWorkspaceView("storyboard"); setViewedStage("storyboard"); }}><Layers3 /> Storyboard</Button>
            <Button size="icon" variant={viewedStage !== "generate" && viewedStage !== "edit" && workspaceView === "workflow" ? "secondary" : "ghost"} className="size-8" onClick={() => { setWorkspaceView("workflow"); setViewedStage("storyboard"); }} title="Project map" aria-label="Project map"><Workflow className="size-4" /></Button>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button size="sm" variant={viewedStage === "generate" ? "secondary" : "ghost"} onClick={() => setViewedStage("generate")}><Sparkles /> <span className="hidden sm:inline">Videos</span></Button>
          <Button size="sm" variant={viewedStage === "edit" ? "secondary" : "ghost"} onClick={() => setViewedStage("edit")}><Film /> <span className="hidden sm:inline">Edit</span></Button>
          <Button size="sm" onClick={createProduction} disabled={saving}><Plus /> New</Button>
        </div>
      </div>

      {error ? <div className="shrink-0 border-b border-destructive/20 bg-destructive/5 px-6 py-2 text-sm text-destructive">{error}</div> : null}

      <div className="flex min-h-0 flex-1 overflow-hidden max-[900px]:block max-[900px]:overflow-auto">
        <ProductionKeyElementsRail
          production={activeProduction}
          assets={Array.from(new Map([...customerAAssets, ...customerBAssets].map((asset) => [asset.id, asset])).values())}
          saving={saving}
          onAdd={() => { setAssetPickerPurpose("project"); setAssetPickerOpen(true); }}
          onRemove={(assetId) => void removeAttachedAsset(assetId)}
        />
        <input ref={customerAInputRef} type="file" className="hidden" multiple accept="image/*,video/*,audio/*,.html,.htm" onChange={(event) => void attachAssets(event.target.files, "reference")} />
        <input ref={customerBInputRef} type="file" className="hidden" multiple accept="image/*,video/*,audio/*,.html,.htm" onChange={(event) => void attachAssets(event.target.files, "brand")} />
        <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[#eef4fa]">
          {viewedStage === "generate" ? <GenerateStage production={activeProduction} assets={liveAssets} saving={saving} busyShotIds={busyShotIds} onGenerateShot={generateShot} onExtractBridgeFrame={extractBridgeFrame} onSaveShotForId={saveShotForId} onEditEndScene={(shotId) => { setSelectedShotId(shotId); setPendingEndSceneShotId(shotId); setViewedStage("storyboard"); }} onStageChange={setViewedStage} /> : null}
          {viewedStage === "edit" ? <EditStage production={activeProduction} assets={liveAssets} saving={saving} busyShotIds={busyShotIds} onRender={renderFirstCut} onSaveShotForId={saveShotForId} onReview={() => void reviewVideoTakes()} onSaveEditPlan={(edit_plan) => void applyUpdate({ edit_plan })} onStageChange={setViewedStage} /> : null}
          {viewedStage !== "generate" && viewedStage !== "edit" ? (workspaceView === "workflow" ? <ProductionCanvas production={activeProduction} assets={liveAssets} onSelectStage={(stage) => setViewedStage(stage === "edit" ? "edit" : stage === "generate" ? "generate" : "storyboard")} onSelectShot={setSelectedShotId} onSaveCanvas={(canvas_state) => void applyUpdate({ canvas_state })} /> : <ProductionStoryboardBoard production={activeProduction} assets={liveAssets} selectedShotId={selectedShotId} onSelectShot={(shotId) => { setSelectedShotId(shotId); setViewedStage("storyboard"); }} />) : null}
        </section>

        {assetsDrawerOpen ? <aside className="hidden w-80 shrink-0 flex-col overflow-hidden border-l bg-background">
          <div className="flex items-start justify-between gap-2 border-b px-4 py-3"><div><p className="text-sm font-semibold">Assets</p><p className="mt-0.5 text-xs text-muted-foreground">Reference and approved brand inputs.</p></div><Button variant="ghost" size="icon" className="size-7" onClick={() => setAssetsDrawerOpen(false)} aria-label="Close production assets"><X className="size-4" /></Button></div>
          <input ref={customerAInputRef} type="file" className="hidden" multiple accept="image/*,video/*,audio/*,.html,.htm" onChange={(event) => void attachAssets(event.target.files, "reference")} />
          <input ref={customerBInputRef} type="file" className="hidden" multiple accept="image/*,video/*,audio/*,.html,.htm" onChange={(event) => void attachAssets(event.target.files, "brand")} />
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <div className="grid gap-4">
            <ProductionAssetGroup title="Creative Reference" description="Structure, pace, and camera language to learn from." assets={customerAAssets} saving={saving} onUpload={() => customerAInputRef.current?.click()} onDrop={(files) => void attachAssets(files, "reference")} onRemove={(assetId) => void removeAttachedAsset(assetId)} />
            <ProductionAssetGroup title="Brand Assets" description="Logo, product, characters, screenshots, copy, and audio." assets={customerBAssets} saving={saving} onUpload={() => customerBInputRef.current?.click()} onDrop={(files) => void attachAssets(files, "brand")} onRemove={(assetId) => void removeAttachedAsset(assetId)} />
          </div>
          </div>
        </aside> : null}
      </div>

      </section>
      <ProductionCopilotPanel production={activeProduction} assets={liveAssets} saving={saving} thinkingMessage={copilotThinkingMessage} thinkingAttachmentIds={copilotThinkingAttachmentIds} attachmentIds={copilotAttachmentIds} value={agentDraft} onChange={setAgentDraft} onSend={(confirmationId) => void askProductionRole(activeProduction.stage, agentDraft, confirmationId)} onStop={stopCopilot} onBranch={() => setBranchDialogOpen(true)} onAddAsset={() => { setAssetPickerPurpose("message"); setAssetPickerOpen(true); }} onRemoveAttachment={(assetId) => setCopilotAttachmentIds((current) => current.filter((id) => id !== assetId))} onUpdate={(payload) => void applyUpdate(payload)} />

      {assetPickerOpen ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/35 p-4" role="presentation" onMouseDown={() => !saving && setAssetPickerOpen(false)}>
        <section className="w-full max-w-2xl rounded-2xl border bg-card shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="add-project-asset-title" onMouseDown={(event) => event.stopPropagation()}>
          <div className="flex items-start justify-between border-b px-5 py-4"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Project input</p><h2 id="add-project-asset-title" className="mt-1 text-lg font-semibold">Add an image or video</h2><p className="mt-1 text-xs text-muted-foreground">Use an existing Library asset or upload a new local file.</p></div><Button variant="ghost" size="icon" className="size-8" onClick={() => setAssetPickerOpen(false)} disabled={saving}><X className="size-4" /></Button></div>
          <div className="flex gap-2 border-b px-5 py-3"><Button size="sm" variant={assetPickerTab === "library" ? "secondary" : "ghost"} onClick={() => setAssetPickerTab("library")}>Library</Button><Button size="sm" variant={assetPickerTab === "local" ? "secondary" : "ghost"} onClick={() => setAssetPickerTab("local")}>Local upload</Button></div>
          {assetPickerTab === "library" ? <div className="grid max-h-[55vh] grid-cols-2 gap-3 overflow-y-auto p-5 sm:grid-cols-3">{liveAssets.filter((asset) => assetPickerPurpose === "message" || !activeProduction.asset_links.some((link) => link.asset_id === asset.id)).map((asset) => <button key={asset.id} type="button" onClick={() => void attachLibraryAsset(asset.id)} disabled={saving} className="overflow-hidden rounded-xl border bg-background text-left transition hover:border-foreground disabled:opacity-50"><div className="aspect-square bg-muted">{asset.type === "image" || asset.type === "gif" ? <img src={asset.url} alt="" className="size-full object-cover" /> : <div className="flex size-full items-center justify-center"><Film className="size-5 text-muted-foreground" /></div>}</div><p className="truncate px-2 py-2 text-xs font-medium">{asset.title}</p></button>)}{!liveAssets.length ? <p className="col-span-full py-8 text-center text-sm text-muted-foreground">Your Library has no available assets yet.</p> : null}</div> : <div className="p-5"><button type="button" onClick={() => customerBInputRef.current?.click()} disabled={saving} className="flex min-h-44 w-full flex-col items-center justify-center rounded-xl border border-dashed bg-muted/20 text-sm text-muted-foreground transition hover:bg-muted"><Upload className="mb-3 size-6" />Choose a local image or video</button><p className="mt-3 text-xs leading-5 text-muted-foreground">The file is attached to this project{assetPickerPurpose === "message" ? " and this message" : ""}.</p></div>}
        </section>
      </div> : null}

      {renameTarget ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/35 p-4" role="presentation" onMouseDown={() => !saving && setRenameTarget(null)}>
        <form className="w-full max-w-md rounded-2xl border bg-card p-6 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="rename-production-title" onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); void renameProduction(); }}>
          <div className="flex items-start justify-between gap-4">
            <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Production</p><h2 id="rename-production-title" className="mt-1 text-lg font-semibold">Rename production</h2></div>
            <Button type="button" variant="ghost" size="icon" className="size-8" onClick={() => setRenameTarget(null)} disabled={saving} aria-label="Close rename dialog"><X className="size-4" /></Button>
          </div>
          <label className="mt-5 block text-sm font-medium">Production name<input autoFocus value={renameTitle} onChange={(event) => setRenameTitle(event.target.value)} maxLength={120} className="mt-2 h-11 w-full rounded-xl border bg-background px-3 text-sm outline-none transition focus:border-foreground focus:ring-2 focus:ring-ring" /></label>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">This only changes the production name; its script, assets, and history stay intact.</p>
          <div className="mt-6 flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setRenameTarget(null)} disabled={saving}>Cancel</Button><Button type="submit" disabled={saving || !renameTitle.trim()}>{saving ? <Loader2 className="animate-spin" /> : null}Save name</Button></div>
        </form>
      </div> : null}

      {branchDialogOpen ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/35 p-4" role="presentation" onMouseDown={() => !saving && setBranchDialogOpen(false)}>
        <form className="w-full max-w-md rounded-2xl border bg-card p-6 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="branch-production-title" onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); void createSafeBranch(); }}>
          <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Safe experiment</p><h2 id="branch-production-title" className="mt-1 text-lg font-semibold">Create a project branch</h2></div><Button type="button" variant="ghost" size="icon" className="size-8" onClick={() => setBranchDialogOpen(false)} disabled={saving} aria-label="Close branch dialog"><X className="size-4" /></Button></div>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">A branch protects this production’s script, selected Takes, and edit. Existing assets remain available, but later changes affect only the new branch.</p>
          <label className="mt-5 block text-sm font-medium">Branch name<input autoFocus value={branchLabel} onChange={(event) => setBranchLabel(event.target.value)} maxLength={80} className="mt-2 h-11 w-full rounded-xl border bg-background px-3 text-sm outline-none transition focus:border-foreground focus:ring-2 focus:ring-ring" /></label>
          <div className="mt-6 flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setBranchDialogOpen(false)} disabled={saving}>Cancel</Button><Button type="submit" disabled={saving || !branchLabel.trim()}>{saving ? <Loader2 className="animate-spin" /> : <GitBranch />}Create branch</Button></div>
        </form>
      </div> : null}

      {deleteTarget ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/35 p-4" role="presentation" onMouseDown={() => !saving && setDeleteTarget(null)}>
        <section className="w-full max-w-md rounded-2xl border bg-card p-6 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="delete-production-title" onMouseDown={(event) => event.stopPropagation()}>
          <div className="flex items-start justify-between gap-4"><div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive"><Trash2 className="size-5" /></div><Button type="button" variant="ghost" size="icon" className="-mr-1 -mt-1 size-8" onClick={() => setDeleteTarget(null)} disabled={saving} aria-label="Close delete dialog"><X className="size-4" /></Button></div>
          <div className="mt-4"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-destructive">Permanent action</p><h2 id="delete-production-title" className="mt-1 text-lg font-semibold">Delete this production?</h2><p className="mt-2 text-sm leading-6 text-muted-foreground"><span className="font-medium text-foreground">{deleteTarget.title}</span> and its production history will be removed. Your uploaded source assets will remain available.</p></div>
          <div className="mt-6 flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setDeleteTarget(null)} disabled={saving}>Keep production</Button><Button type="button" variant="destructive" onClick={() => void removeProduction()} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Trash2 />}Delete production</Button></div>
        </section>
      </div> : null}
    </main>
  );
}

function ProductionCopilotPanel({ production, assets, saving, thinkingMessage, thinkingAttachmentIds, attachmentIds, value, onChange, onSend, onStop, onBranch, onAddAsset, onRemoveAttachment, onUpdate }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; thinkingMessage: string | null; thinkingAttachmentIds: string[]; attachmentIds: string[]; value: string; onChange: (value: string) => void; onSend: (confirmationId?: string) => void; onStop: () => void; onBranch: () => void; onAddAsset: () => void; onRemoveAttachment: (assetId: string) => void; onUpdate: (payload: Parameters<typeof updateVideoProduction>[1]) => void }) {
  const [collapsed, setCollapsed] = useState(false);
  const [panelWidth, setPanelWidth] = useState(420);
  const panelWidthRef = useRef(panelWidth);
  const [activeChip, setActiveChip] = useState<"duration" | "ratio" | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  useEffect(() => {
    const saved = Number(window.localStorage.getItem("incept.video.copilot.width"));
    if (Number.isFinite(saved) && saved >= 320 && saved <= 680) {
      panelWidthRef.current = saved;
      setPanelWidth(saved);
    }
  }, []);
  const startResize = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = panelWidth;
    const onMove = (moveEvent: PointerEvent) => {
      const nextWidth = Math.min(680, Math.max(320, startWidth + startX - moveEvent.clientX));
      panelWidthRef.current = nextWidth;
      setPanelWidth(nextWidth);
    };
    const onEnd = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onEnd);
      window.localStorage.setItem("incept.video.copilot.width", String(panelWidthRef.current));
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onEnd);
  };
  // Job-completion notices belong to the cards they affect, not to a creative
  // conversation. Hide those legacy activity messages and de-duplicate the
  // remaining assistant replies so the panel stays decision-focused.
  const activityNotice = /^(all \d+ shots reviewed|s\d+ veo take is ready|the 2x2 asset sheet|the selected-take edit is ready)/i;
  const seen = new Set<string>();
  const messages = [...production.conversation].sort((left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime()).filter((message) => {
    const key = `${message.role}:${message.text.trim()}`;
    if (activityNotice.test(message.text.trim()) || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(-8);
  const pending = production.pending_confirmation;
  const attachmentAssets = attachmentIds.map((id) => assets.find((asset) => asset.id === id)).filter((asset): asset is AssetSummary => Boolean(asset));
  const thinkingAssets = thinkingAttachmentIds.map((id) => assets.find((asset) => asset.id === id)).filter((asset): asset is AssetSummary => Boolean(asset));
  const renderAttachments = (assetIds: string[], removable = false) => assetIds.length ? <div className="mb-2 flex max-w-full gap-2 overflow-x-auto pb-1">{assetIds.map((assetId) => { const asset = assets.find((item) => item.id === assetId); if (!asset) return null; return <div key={asset.id} className="group/attachment relative size-14 shrink-0 overflow-hidden rounded-lg border bg-muted"><div className="size-full">{asset.type === "image" || asset.type === "gif" ? <img src={asset.url} alt={asset.title} className="size-full object-cover" /> : <div className="flex size-full items-center justify-center"><Film className="size-4 text-muted-foreground" /></div>}</div>{removable ? <button type="button" onClick={() => onRemoveAttachment(asset.id)} className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/70 text-white opacity-0 transition group-hover/attachment:opacity-100 focus:opacity-100" aria-label={`Remove ${asset.title}`}><X className="size-3" /></button> : null}</div>; })}</div> : null;
  if (collapsed) return <aside className="flex w-12 shrink-0 flex-col items-center border-l bg-background pt-3 max-[900px]:hidden"><Button size="icon" variant="ghost" className="size-8 rounded-full" onClick={() => setCollapsed(false)} aria-label="Expand Copilot"><MessageSquareText className="size-4" /></Button></aside>;
  return <aside className="relative flex shrink-0 flex-col border-l bg-background max-[900px]:hidden" style={{ width: panelWidth }}>
    <div role="separator" aria-orientation="vertical" aria-label="Resize Copilot panel" title="Drag to resize Copilot" onPointerDown={startResize} className="absolute inset-y-0 -left-1 z-40 w-2 cursor-col-resize touch-none after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:bg-transparent after:transition-colors hover:after:bg-slate-300" />
    <div className="flex items-center justify-between border-b px-6 py-5"><div><p className="text-base font-semibold tracking-tight">Copilot</p><p className="mt-1 text-xs text-muted-foreground">Your video production partner</p></div><div className="flex items-center gap-1"><Badge variant="outline" className="rounded-full font-medium">{production.shots.length} frames</Badge><Button size="icon" variant="ghost" className="size-8 rounded-full" onClick={() => setCollapsed(true)} aria-label="Collapse Copilot"><PanelRightClose className="size-4" /></Button></div></div>
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-8">
      <div className="space-y-7">
        {messages.length ? messages.map((message, index) => message.role === "user" ? <div key={`${message.created_at}-${index}`} className="ml-auto max-w-[88%] rounded-[28px] bg-muted px-5 py-4 text-sm leading-6 text-foreground">{renderAttachments(message.asset_ids ?? [])}{message.text}</div> : <article key={`${message.created_at}-${index}`} className="max-w-full whitespace-pre-wrap text-sm leading-7 text-foreground"><p className="mb-2 text-xs font-semibold text-muted-foreground">Copilot</p>{message.text}</article>) : !thinkingMessage ? <div className="pt-10 text-center"><div className="mx-auto flex size-10 items-center justify-center rounded-full bg-muted"><Sparkles className="size-4" /></div><p className="mt-4 text-sm font-semibold">What would you like to create?</p><p className="mx-auto mt-2 max-w-[275px] text-xs leading-5 text-muted-foreground">Share a brief or add images and video. Copilot will ask before making a material assumption.</p></div> : null}
      {thinkingMessage ? <><div className="ml-auto max-w-[88%] rounded-[28px] bg-muted px-5 py-4 text-sm leading-6 text-foreground">{renderAttachments(thinkingAssets.map((asset) => asset.id))}{thinkingMessage}</div><article className="max-w-full text-sm text-muted-foreground"><p className="mb-2 text-xs font-semibold text-muted-foreground">Copilot</p><div className="inline-flex items-center gap-2 rounded-xl bg-muted/60 px-3 py-2"><Loader2 className="size-3.5 animate-spin" /> Thinking…</div></article></> : null}
      {pending ? <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950"><p className="font-semibold">Review this change</p><p className="mt-1">{pending.question}</p><p className="mt-2 text-amber-800">{pending.reason}</p><div className="mt-3 flex flex-wrap gap-2"><Button size="sm" onClick={() => onSend(pending.id)} disabled={saving}>Apply change</Button><Button size="sm" variant="secondary" onClick={onBranch} disabled={saving}>Make a copy first</Button></div></div> : null}
      </div>
    </div>
    <div className="border-t bg-background px-5 py-3"><div className="rounded-[24px] border bg-card p-1.5 shadow-sm">{renderAttachments(attachmentAssets.map((asset) => asset.id), true)}<textarea value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!saving && value.trim()) onSend(); } }} placeholder="Ask Copilot…" className="min-h-10 w-full resize-none bg-transparent px-3 py-1.5 text-sm leading-5 outline-none placeholder:text-muted-foreground" /><div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-0.5"><div className="flex items-center gap-1"><Button size="icon" variant="ghost" className="size-7 rounded-full" onClick={onAddAsset} disabled={saving} aria-label="Add local or Library asset"><Plus className="size-4" /></Button><div className="relative"><button type="button" className="inline-flex h-7 items-center gap-1 rounded-full px-2 text-[11px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground" onClick={() => setModelOpen((open) => !open)}>Gemini 3.6 Flash <ChevronDown className="size-3" /></button>{modelOpen ? <div className="absolute bottom-[calc(100%+8px)] left-0 z-30 w-44 rounded-xl border bg-card p-1 shadow-xl"><button type="button" className="w-full rounded-lg px-3 py-2 text-left text-xs font-medium hover:bg-muted" onClick={() => setModelOpen(false)}>Gemini 3.6 Flash</button></div> : null}</div><DirectionChip label="" value={`${production.target_seconds}s`} options={["15s", "30s", "60s"]} active={activeChip === "duration"} onToggle={() => setActiveChip((current) => current === "duration" ? null : "duration")} onChange={(next) => { onUpdate({ target_seconds: Number(next.replace("s", "")) as 15 | 30 | 60 }); setActiveChip(null); }} /><DirectionChip label="" value={production.aspect_ratio} options={["9:16", "16:9"]} active={activeChip === "ratio"} onToggle={() => setActiveChip((current) => current === "ratio" ? null : "ratio")} onChange={(next) => { onUpdate({ aspect_ratio: next as "9:16" | "16:9" }); setActiveChip(null); }} /></div><Button size="icon" className="size-8 rounded-full" onClick={thinkingMessage ? onStop : () => onSend()} disabled={!thinkingMessage && (saving || !value.trim())} aria-label={thinkingMessage ? "Stop Copilot" : "Send message"}>{thinkingMessage ? <Square className="size-3.5 fill-current" /> : <Send className="size-4" />}</Button></div></div></div>
  </aside>;
}

function ProductionCanvas({ production, assets, onSelectStage, onSelectShot, onSaveCanvas }: { production: VideoProduction; assets: AssetSummary[]; onSelectStage: (stage: VideoProductionStage) => void; onSelectShot: (id: string) => void; onSaveCanvas: (canvas: VideoProduction["canvas_state"]) => void }) {
  const stored = production.canvas_state?.node_positions ?? {};
  const positionFor = (id: string, fallback: { x: number; y: number }) => stored[id] ?? fallback;
  const nodes = useMemo<Node[]>(() => {
    const list: Node[] = [
      { id: "storyboard", position: positionFor("storyboard", { x: 48, y: 160 }), data: { label: <CanvasNode title="Storyboard" detail={`${production.shots.length} visual frame${production.shots.length === 1 ? "" : "s"}`} /> }, style: { width: 190, background: "transparent", border: "none", padding: 0 } },
    ];
    production.shots.slice().sort((a, b) => a.order - b.order).forEach((shot, index) => {
      const y = 54 + index * 142;
      list.push({ id: `frame:${shot.id}`, position: positionFor(`frame:${shot.id}`, { x: 330, y }), data: { label: <CanvasNode title={`F${shot.order} · ${shot.title}`} detail={shot.keyframe_asset_id ? "Scene linked" : "Scene pending"} state={shot.motion_feasibility === "blocked" ? "Needs bridge" : shot.take_outdated ? "Take outdated" : undefined} /> }, style: { width: 212, background: "transparent", border: "none", padding: 0 } });
      list.push({ id: `take:${shot.id}`, position: positionFor(`take:${shot.id}`, { x: 620, y }), data: { label: <CanvasNode title={`Video · F${shot.order}`} detail={shot.selected_video_asset_id ? "Selected" : shot.video_asset_ids.length ? `${shot.video_asset_ids.length} takes` : "Not generated"} state={shot.take_outdated ? "Review source change" : undefined} /> }, style: { width: 180, background: "transparent", border: "none", padding: 0 } });
    });
    list.push({ id: "edit", position: positionFor("edit", { x: 1090, y: 160 }), data: { label: <CanvasNode title="Edit" detail={production.final_asset_id ? "First cut ready" : "Select takes"} /> }, style: { width: 170, background: "transparent", border: "none", padding: 0 } });
    return list;
  // Canvas coordinates are persisted Project State. Domain data drives nodes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [production.production_id, production.state_revision]);
  const edges = useMemo<Edge[]>(() => {
    const list: Edge[] = [];
    const shots = production.shots.slice().sort((a, b) => a.order - b.order);
    shots.forEach((shot, index) => {
      list.push({ id: `storyboard-${shot.id}`, source: "storyboard", target: `frame:${shot.id}` });
      list.push({ id: `frame-take-${shot.id}`, source: `frame:${shot.id}`, target: `take:${shot.id}` });
      list.push({ id: `take-edit-${shot.id}`, source: `take:${shot.id}`, target: "edit" });
      if (index) list.push({ id: `sequence-${shot.id}`, source: `frame:${shots[index - 1].id}`, target: `frame:${shot.id}`, label: shot.recommended_transition_strategy || "cut", style: { strokeDasharray: "3 3" } });
    });
    return list;
  }, [production.shots]);
  return <div className="flex min-h-0 flex-1 flex-col bg-[#eef4fa] text-slate-900"><div className="flex items-center justify-between border-b border-[#dbe5ef] bg-[#f8fbff] px-6 py-4"><div><p className="text-sm font-semibold">Project map</p><p className="mt-1 text-xs text-slate-500">Storyboard frames, video takes, and edit relationships.</p></div><Button size="sm" variant="secondary" onClick={() => onSelectStage("storyboard")}>Open storyboard</Button></div><div className="min-h-0 flex-1"><ReactFlow className="bg-[#eef4fa]" nodes={nodes} edges={edges} fitView nodesDraggable onNodeClick={(_, node) => { if (node.id === "storyboard") onSelectStage("storyboard"); else if (node.id === "edit") onSelectStage("edit"); else { const shotId = node.id.split(":")[1]; if (shotId) { onSelectShot(shotId); onSelectStage(node.id.startsWith("take:") ? "generate" : "storyboard"); } } }} onNodeDragStop={(_, node) => onSaveCanvas({ ...production.canvas_state, node_positions: { ...stored, [node.id]: node.position } })} nodesConnectable={false} edgesReconnectable={false} proOptions={{ hideAttribution: true }}><Background gap={18} size={1} color="rgba(96,122,153,0.22)" bgColor="#eef4fa" /><Controls showInteractive={false} /></ReactFlow></div></div>;
}

function CanvasNode({ title, detail, state }: { title: string; detail: string; state?: string }) {
  return <div className="rounded-xl border border-[#dbe5ef] bg-white px-3 py-2 shadow-sm"><p className="truncate text-xs font-semibold text-slate-900">{title}</p><p className="mt-1 truncate text-[11px] text-slate-500">{detail}</p>{state ? <p className="mt-2 text-[10px] font-medium text-amber-700">{state}</p> : null}</div>;
}

function ProductionKeyElementsRail({ production, assets, saving, onAdd, onRemove }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; onAdd: () => void; onRemove: (assetId: string) => void }) {
  void production;
  const [collapsed, setCollapsed] = useState(false);
  return <aside className={cn("flex shrink-0 flex-col overflow-hidden border-r border-[#dbe5ef] bg-[#f8fbff] text-slate-900 transition-[width] duration-200 max-[1080px]:hidden", collapsed ? "w-12" : "w-[272px]")}>
    <div className={cn("flex items-start border-b border-[#dbe5ef] py-3", collapsed ? "justify-center px-1" : "justify-between gap-2 px-4")}><div className={cn(collapsed && "sr-only")}><p className="text-sm font-semibold">Key elements</p><p className="mt-1 text-xs leading-5 text-slate-500">A single project gallery for images and video.</p></div><Button size="icon" variant="ghost" className="size-7 shrink-0 text-slate-500 hover:bg-slate-200 hover:text-slate-900" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Expand key elements" : "Collapse key elements"}><ChevronDown className={cn("size-4 transition-transform", collapsed && "-rotate-90")} /></Button></div>
    {collapsed ? <div className="flex flex-col items-center gap-3 p-2"><ImagePlus className="size-4 text-slate-400" /><Clapperboard className="size-4 text-slate-400" /></div> : <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-3">
      <KeyElementSection title="Project assets" count={assets.length} onAdd={onAdd} saving={saving}>
        <KeyElementAssetList assets={assets} saving={saving} onRemove={onRemove} empty="Add images or video from Library or your computer" />
      </KeyElementSection>
    </div>}
  </aside>;
}

function KeyElementSection({ title, count, onAdd, saving, children }: { title: string; count: number; onAdd: () => void; saving: boolean; children: ReactNode }) {
  return <section><div className="mb-2 flex items-center justify-between gap-2"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-700">{title}</p><Button size="icon" variant="ghost" className="size-7 text-slate-500 hover:bg-slate-200 hover:text-slate-900" onClick={onAdd} disabled={saving} aria-label={`Add ${title}`}><Plus className="size-4" /></Button></div><p className="mb-2 text-[11px] text-slate-500">{count ? `${count} attached` : "Not attached yet"}</p>{children}</section>;
}

function KeyElementAssetList({ assets, saving, onRemove, empty }: { assets: AssetSummary[]; saving: boolean; onRemove: (assetId: string) => void; empty: string }) {
  if (!assets.length) return <div className="rounded-lg border border-dashed border-[#cfdbe8] p-3 text-[11px] leading-4 text-slate-500">{empty}</div>;
  return <div className="grid grid-cols-2 gap-2">{assets.map((asset) => <div key={asset.id} className="group relative overflow-hidden rounded-lg border border-[#dbe5ef] bg-white"><button type="button" onClick={() => onRemove(asset.id)} disabled={saving} className="absolute right-1 top-1 z-10 flex size-5 items-center justify-center rounded-full bg-white/95 text-slate-500 opacity-0 shadow-sm transition hover:bg-destructive hover:text-destructive-foreground group-hover:opacity-100" aria-label={`Remove ${asset.title}`}><X className="size-3" /></button><div className="aspect-square bg-slate-100">{asset.type === "image" || asset.type === "gif" ? <img src={asset.url} alt="" className="size-full object-cover" /> : <div className="flex size-full items-center justify-center"><Film className="size-4 text-slate-400" /></div>}</div><p className="truncate px-2 py-1.5 text-[10px] font-medium text-slate-700">{asset.title}</p></div>)}</div>;
}

function ProductionStoryboardBoard({ production, assets, selectedShotId, onSelectShot }: { production: VideoProduction; assets: AssetSummary[]; selectedShotId: string | null; onSelectShot: (id: string) => void }) {
  const sceneById = new Map(production.script.scenes.map((scene) => [scene.id, scene]));
  const shots = production.shots.slice().sort((left, right) => left.order - right.order);
  return <div className="min-h-0 flex-1 overflow-y-auto bg-[#eef4fa] p-5 text-slate-900 max-[900px]:p-4"><div className="mx-auto max-w-[1500px]"><div className="mb-5"><p className="text-sm font-semibold">Storyboard</p><p className="mt-1 text-xs text-slate-500">This is the visual output of the Copilot: one Scene image and one concise moment per Frame.</p></div>{shots.length ? <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{shots.map((shot) => { const frame = assets.find((asset) => asset.id === shot.keyframe_asset_id); const end = assets.find((asset) => asset.id === shot.end_keyframe_asset_id); const scene = sceneById.get(shot.scene_id); return <button key={shot.id} type="button" onClick={() => onSelectShot(shot.id)} className={cn("overflow-hidden rounded-2xl border border-[#dbe5ef] bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md", selectedShotId === shot.id && "ring-2 ring-slate-700/60")}><div className="relative aspect-[16/10] bg-slate-100">{frame?.url ? <img src={frame.url} alt="" className="size-full object-cover" /> : <div className="flex size-full items-center justify-center text-xs text-slate-500">Scene image will appear here</div>}<span className="absolute left-2 top-2 rounded-full bg-white/90 px-2 py-1 text-[10px] font-semibold text-slate-900">Frame {shot.order}</span>{end?.url ? <img src={end.url} alt="" className="absolute bottom-2 right-2 size-12 rounded-md border-2 border-white object-cover shadow" /> : null}</div><div className="p-3"><div className="flex items-start justify-between gap-2"><p className="line-clamp-2 text-sm font-semibold">{shot.title}</p><span className="shrink-0 text-[11px] text-slate-500">{shot.duration_seconds}s</span></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{scene?.action || shot.visual || shot.purpose}</p><div className="mt-3 flex items-center justify-between text-[10px] text-slate-500"><span>{frame ? "Scene selected" : "Generating scene"}</span><span>{shot.selected_video_asset_id ? "Video ready" : "Video pending"}</span></div></div></button>; })}</div> : <div className="rounded-2xl border border-dashed border-[#cfdbe8] bg-white p-12 text-center"><Layers3 className="mx-auto size-7 text-slate-400" /><p className="mt-3 text-sm font-semibold">Your storyboard will appear here</p><p className="mt-1 text-sm text-slate-500">Tell the Copilot what to make and attach a reference if you have one.</p></div>}</div></div>;
}

function ProductionStageSummary({ production, stage, detailsOpen, onOpenDetails, onCloseDetails }: { production: VideoProduction; stage: VideoProductionStage; detailsOpen: boolean; onOpenDetails: () => void; onCloseDetails: () => void }) {
  const descriptors: Record<VideoProductionStage, { title: string; detail: string }> = {
    direction: { title: "Plan", detail: production.video_setup.confirmed ? "Video setup confirmed. Refine the direction with the Copilot." : "Tell the Copilot what to make; it will ask before filling missing strategic choices." },
    script: { title: "Script", detail: `${production.script.scenes.length} structured scene${production.script.scenes.length === 1 ? "" : "s"} · revision ${production.script.revision}` },
    design: { title: "Assets", detail: `${production.design_bible.asset_packs.length} reusable visual state${production.design_bible.asset_packs.length === 1 ? "" : "s"}` },
    storyboard: { title: "Storyboard", detail: `${production.shots.length} frame${production.shots.length === 1 ? "" : "s"} in sequence` },
    generate: { title: "Video", detail: `${production.shots.filter((shot) => shot.selected_video_asset_id).length} selected take${production.shots.filter((shot) => shot.selected_video_asset_id).length === 1 ? "" : "s"}` },
    audio: { title: "Edit", detail: "Audio is assembled with the selected takes." },
    edit: { title: "Edit", detail: production.final_asset_id ? "First cut is ready for review." : "Choose takes and assemble a first cut." },
    deliver: { title: "Deliver", detail: "Review the final output and delivery checks." },
  };
  const item = descriptors[stage];
  return <div className="flex shrink-0 items-center justify-between gap-4 border-t bg-background px-5 py-3"><div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">Current focus · {item.title}</p><p className="mt-1 truncate text-xs text-muted-foreground">{item.detail}</p></div><Button size="sm" variant={detailsOpen ? "secondary" : "outline"} onClick={detailsOpen ? onCloseDetails : onOpenDetails}>{detailsOpen ? "Close details" : `Open ${item.title} details`}</Button></div>;
}

function ProductionAssetGroup({ title, description, assets, saving, onUpload, onDrop, onRemove }: { title: string; description: string; assets: AssetSummary[]; saving: boolean; onUpload: () => void; onDrop: (files: FileList) => void; onRemove: (assetId: string) => void }) {
  const [dragging, setDragging] = useState(false);
  return <section className="min-h-0"><div className="mb-2 flex items-baseline justify-between gap-2"><div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-foreground">{title}</p><p className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted-foreground">{description}</p></div><span className="shrink-0 text-[10px] text-muted-foreground">{assets.length}</span></div><div onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={(event) => { event.preventDefault(); setDragging(false); }} onDrop={(event) => { event.preventDefault(); setDragging(false); if (event.dataTransfer.files.length) onDrop(event.dataTransfer.files); }} className={cn("rounded-xl border border-dashed p-2 transition", dragging ? "border-foreground bg-muted" : "border-border")}>{assets.length ? <div className="flex gap-2 overflow-x-auto pb-1">{assets.map((asset) => <div key={asset.id} className="group relative w-[82px] shrink-0 overflow-hidden rounded-lg border bg-card"><button type="button" onClick={() => onRemove(asset.id)} disabled={saving} aria-label={`Remove ${asset.title} from this production`} className="absolute right-1 top-1 z-10 flex size-5 items-center justify-center rounded-full bg-background/90 text-muted-foreground opacity-0 shadow-sm transition hover:bg-destructive hover:text-destructive-foreground group-hover:opacity-100 focus:opacity-100 disabled:cursor-not-allowed"><X className="size-3" /></button><div className="aspect-[4/3] bg-muted">{asset.type === "image" || asset.type === "gif" ? <img src={asset.url} alt="" className="size-full object-cover" /> : <div className="flex size-full items-center justify-center">{asset.type === "audio" ? <Music2 className="size-5 text-muted-foreground" /> : <Film className="size-5 text-muted-foreground" />}</div>}</div><div className="p-1.5"><p className="truncate text-[10px] font-medium">{asset.title}</p><p className="mt-0.5 text-[10px] text-muted-foreground">{assetTypeLabel(asset)}</p></div></div>)}<button type="button" onClick={onUpload} disabled={saving} className="flex min-h-[78px] w-[82px] shrink-0 flex-col items-center justify-center rounded-lg border border-dashed text-[10px] text-muted-foreground hover:bg-muted disabled:opacity-50"><Plus className="mb-1 size-4" />Add files</button></div> : <button type="button" onClick={onUpload} disabled={saving} className="flex min-h-[92px] w-full flex-col items-center justify-center rounded-lg px-3 text-center text-xs text-muted-foreground hover:bg-muted disabled:opacity-50"><ImagePlus className="mb-2 size-5" />Drag files here or click to upload</button>}</div></section>;
}

function DirectionChip({ label, value, options, active, onToggle, onChange }: { label: string; value: string; options: string[]; active: boolean; onToggle: () => void; onChange: (value: string) => void }) {
  return <div className="relative"><button type="button" onClick={onToggle} className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition", active ? "border-foreground bg-foreground text-background" : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground")}><span className="text-foreground/55">{label}</span>{value}<ChevronDown className="size-3.5" /></button>{active ? <div className="absolute bottom-[calc(100%+8px)] left-0 z-30 min-w-36 overflow-hidden rounded-xl border bg-card p-1 shadow-xl">{options.map((option) => <button key={option} type="button" onClick={() => onChange(option)} className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs hover:bg-muted"><span>{option}</span>{option === value ? <Check className="size-3.5" /> : null}</button>)}</div> : null}</div>;
}

function ProductionConversationMessages({ saving, hasContent = true, fullWidth = true, thinkingLabel, emptyIcon: EmptyIcon, emptyTitle, emptyDescription, children }: { saving: boolean; hasContent?: boolean; fullWidth?: boolean; thinkingLabel: string; emptyIcon: typeof MessageSquareText; emptyTitle: string; emptyDescription: string; children?: ReactNode }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 max-[900px]:px-4">
      <div className={cn("space-y-5 pb-16", fullWidth ? "w-full max-w-none" : "mx-auto max-w-5xl")}>
        {!hasContent ? (
          <div className="flex min-h-[340px] flex-col items-center justify-center text-center">
            <EmptyIcon className="size-7 text-muted-foreground" />
            <p className="mt-4 text-sm font-semibold">{emptyTitle}</p>
            <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{emptyDescription}</p>
          </div>
        ) : null}
        {saving ? <AgentThinking label={thinkingLabel} /> : null}
        {children}
      </div>
    </div>
  );
}

function ProductionComposer({ production, saving, value, onChange, onSend, onSave, placeholder, ariaLabel }: { production: VideoProduction; saving: boolean; value: string; onChange: (value: string) => void; onSend: () => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; placeholder: string; ariaLabel: string }) {
  // Conversation moved to the persistent Production Copilot at the right.
  // Keep this compatibility component while individual stage cards migrate;
  // removing it avoids a second, oversized composer at the bottom.
  void production; void saving; void value; void onChange; void onSend; void onSave; void placeholder; void ariaLabel;
  return null;
  /*
  const [activeChip, setActiveChip] = useState<"duration" | "ratio" | "resolution" | null>(null);
  return (
    <div className="relative shrink-0 bg-background px-6 pb-4 pt-2 max-[900px]:px-4">
      <div className="pointer-events-none absolute inset-x-0 bottom-full h-16 bg-gradient-to-t from-background to-transparent" />
      <div className="mx-auto w-full rounded-2xl border bg-card p-3 shadow-[0_2px_20px_rgba(0,0,0,0.10)] xl:w-[70%]">
        <textarea value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); onSend(); } }} placeholder={placeholder} className="min-h-20 w-full resize-none bg-transparent px-2 py-1 text-sm leading-6 outline-none placeholder:text-muted-foreground" />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3 border-t pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <DirectionChip label="Duration" value={`${production.target_seconds}s`} options={["15s", "30s", "60s"]} active={activeChip === "duration"} onToggle={() => setActiveChip((value) => value === "duration" ? null : "duration")} onChange={(nextValue) => { void onSave({ target_seconds: Number(nextValue.replace("s", "")) as 15 | 30 | 60 }); setActiveChip(null); }} />
            <DirectionChip label="Ratio" value={production.aspect_ratio} options={["16:9", "9:16"]} active={activeChip === "ratio"} onToggle={() => setActiveChip((value) => value === "ratio" ? null : "ratio")} onChange={(nextValue) => { void onSave({ aspect_ratio: nextValue as "16:9" | "9:16" }); setActiveChip(null); }} />
            <DirectionChip label="Output" value={production.resolution} options={["720p", "1080p"]} active={activeChip === "resolution"} onToggle={() => setActiveChip((value) => value === "resolution" ? null : "resolution")} onChange={(nextValue) => { void onSave({ resolution: nextValue as "720p" | "1080p" }); setActiveChip(null); }} />
          </div>
          <Button size="icon" onClick={onSend} disabled={saving} aria-label={ariaLabel}>{saving ? <Loader2 className="animate-spin" /> : <Send />}</Button>
        </div>
      </div>
    </div>
  );
  */
}

function ProductionActionBar({ children }: { children: ReactNode }) {
  return (
    <div className="relative shrink-0 bg-background px-6 pb-4 pt-2 max-[900px]:px-4">
      <div className="pointer-events-none absolute inset-x-0 bottom-full h-16 bg-gradient-to-t from-background to-transparent" />
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-end gap-2 rounded-2xl border bg-card p-3 shadow-[0_2px_20px_rgba(0,0,0,0.10)]">
        {children}
      </div>
    </div>
  );
}

function DirectionWorkspace({ production, saving, agentDraft, onAgentDraftChange, onSend, onSave, onApprove }: { production: VideoProduction; saving: boolean; agentDraft: string; onAgentDraftChange: (value: string) => void; onSend: () => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; onApprove: (confirmedPackKeys: string[]) => void }) {
  const direction = production.creative_direction;
  const referenceAnalysis = direction.reference_analysis;
  const referenceFramePlan = direction.reference_frame_plan ?? [];
  const designHandoff = useMemo(() => {
    const usedKeys = new Set<string>();
    return (direction.design_handoff ?? []).map((item, index) => {
      const rawKey = item.pack_key?.trim();
      const baseKey = rawKey && !["none", "null", "undefined", "unknown"].includes(rawKey.toLowerCase())
        ? rawKey
        : `${item.pack_type || "asset"}_${index + 1}`;
      let packKey = baseKey;
      let suffix = 2;
      while (usedKeys.has(packKey)) {
        packKey = `${baseKey}_${suffix}`;
        suffix += 1;
      }
      usedKeys.add(packKey);
      return { ...item, pack_key: packKey };
    });
  }, [direction.design_handoff]);
  const proposedPackKeys = useMemo(() => designHandoff.map((item) => item.pack_key).filter(Boolean), [designHandoff]);
  const [confirmedPackKeys, setConfirmedPackKeys] = useState<string[]>([]);
  useEffect(() => setConfirmedPackKeys(direction.confirmed_pack_keys?.length ? direction.confirmed_pack_keys : proposedPackKeys), [direction.confirmed_pack_keys, production.production_id, proposedPackKeys]);
  const togglePack = (packKey: string) => setConfirmedPackKeys((keys) => keys.includes(packKey) ? keys.filter((key) => key !== packKey) : [...keys, packKey]);
  const hasConversation = production.conversation.length > 0;
  const analyzeLabel = hasConversation ? "Ask Production Copilot" : "Analyze reference";
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} hasContent={Boolean(direction.reference_summary)} thinkingLabel="Production Copilot is planning…" emptyIcon={MessageSquareText} emptyTitle="Start with a brief or creative reference" emptyDescription="Upload a Creative Reference on the right, then tell the Production Copilot your product, audience, channel, and desired outcome.">
        <VideoSetupCard setup={production.video_setup} saving={saving} onSave={(video_setup) => onSave({ video_setup })} />
        {direction.reference_summary ? (
          <Card className="overflow-hidden border p-0 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-muted/20 px-5 py-4">
              <div className="flex items-start gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-bold text-background">01</span>
                <div><p className="text-sm font-semibold">Production plan</p><p className="mt-1 text-xs text-muted-foreground">Reference analysis, creative direction, and visual plan · {displayReportText(direction.commercial_type, " · ")}</p></div>
              </div>
              <div className="flex items-center gap-2"><Badge variant="outline">Output: {direction.output_language || "from latest input"}</Badge><Badge variant="outline">{direction.status}</Badge><Button onClick={() => onApprove(confirmedPackKeys)} disabled={saving || !confirmedPackKeys.length}>{saving ? <Loader2 className="animate-spin" /> : <Check />}Confirm plan & generate script</Button></div>
            </div>
            <div className="p-5">
              {referenceAnalysis?.timeline?.length ? <section className="rounded-xl border bg-muted/10 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">01 · Reference video analysis</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Observed evidence only — this is what the Strategist must follow, not an adaptation yet.</p></div><Badge variant="outline">{referenceAnalysis.timeline.length} observations</Badge></div>
                {referenceAnalysis.source_summary ? <p className="mt-3 text-sm leading-6 text-foreground">{referenceAnalysis.source_summary}</p> : null}
                {referenceAnalysis.detailed_analysis ? <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{referenceAnalysis.detailed_analysis}</p> : null}
                <ol className="mt-4 grid gap-3 md:grid-cols-2">{referenceAnalysis.timeline.map((moment, index) => <li key={`${moment.start_seconds}-${index}`} className="rounded-lg border bg-background p-3"><div className="flex items-center gap-2"><span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-foreground text-[10px] font-bold text-background">{String(index + 1).padStart(2, "0")}</span><span className="text-xs font-semibold tabular-nums text-muted-foreground">{formatReferenceTimecode(moment.start_seconds)}–{formatReferenceTimecode(moment.end_seconds)}</span></div><p className="mt-2 text-sm leading-5">{moment.observed_visual}</p><p className="mt-1 text-xs leading-5 text-muted-foreground"><span className="font-medium text-foreground">Action:</span> {moment.action} <span className="font-medium text-foreground">· Camera:</span> {moment.camera}</p>{moment.on_screen_text && moment.on_screen_text !== "unknown" ? <p className="mt-1 text-xs leading-5 text-muted-foreground"><span className="font-medium text-foreground">Text:</span> {moment.on_screen_text}</p> : null}</li>)}</ol>
              </section> : null}
              <div className="mt-5 rounded-xl border-l-4 border-foreground bg-muted/25 px-4 py-3"><p className="text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">02 · Recommended video direction</p><p className="mt-2 text-sm leading-6 text-foreground">{displayReportText(direction.reference_summary)}</p>{direction.strengths_to_adapt.length ? <div className="mt-3 border-t pt-3"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Transferable strengths</p><ul className="mt-2 space-y-1 text-sm leading-6 text-muted-foreground">{direction.strengths_to_adapt.map((item, index) => <li key={`${item}-${index}`}>• {item}</li>)}</ul></div> : null}</div>
              {referenceFramePlan.length ? <section className="mt-5 rounded-xl border bg-muted/10 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><p className="text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">03 · Designer reference frames</p><p className="mt-1 text-xs leading-5 text-muted-foreground">These time-coded moments are extracted from the Creative Reference and guide original Designer assets.</p></div>
                  <Badge variant="outline">{referenceFramePlan.length} planned</Badge>
                </div>
                <ol className="mt-4 grid gap-3 md:grid-cols-3">
                  {referenceFramePlan.map((frame, index) => <li key={`${frame.timestamp_seconds}-${index}`} className="rounded-lg border bg-background p-3">
                    <div className="flex items-center gap-2"><span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-foreground text-[10px] font-bold text-background">{String(index + 1).padStart(2, "0")}</span><span className="text-xs font-semibold tabular-nums text-muted-foreground">{formatReferenceTimecode(frame.timestamp_seconds)}</span></div>
                    <p className="mt-3 text-sm font-medium leading-5">{frame.purpose || "Reference moment"}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{frame.rationale || "Used as a controlled visual reference during design."}</p>
                    <p className="mt-3 border-t pt-2 text-[11px] leading-5 text-muted-foreground"><span className="font-medium text-foreground">Source video:</span> {frame.source_asset_title || "Creative Reference"}</p>
                  </li>)}
                </ol>
              </section> : null}
              {designHandoff.length ? <section className="mt-5 rounded-xl border bg-muted/10 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">04 · Confirm Asset Plan</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Confirm the visual brief for every reusable state. The Designer will turn this brief, the locked Script, and selected source images into the final generation prompt.</p></div><Badge variant="outline">{confirmedPackKeys.length} / {designHandoff.length} selected</Badge></div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">{designHandoff.map((item) => { const checked = confirmedPackKeys.includes(item.pack_key); const sourceLabel = item.source_mode === "brand_asset" ? "brand supplied" : "AI generated"; const visualMode = String(item.visual_mode || "AI generated").replaceAll("_", " "); const continuity = Array.isArray(item.continuity_rules) ? item.continuity_rules : []; const uses = Array.isArray(item.scene_uses) ? item.scene_uses : []; const constraints = Array.isArray(item.negative_constraints) ? item.negative_constraints : []; return <label key={item.pack_key} className={cn("cursor-pointer rounded-lg border bg-background p-3 transition", checked ? "border-foreground ring-1 ring-foreground/20" : "opacity-65 hover:opacity-100")}><div className="flex items-start justify-between gap-2"><div className="flex min-w-0 gap-2"><input type="checkbox" checked={checked} onChange={() => togglePack(item.pack_key)} className="mt-0.5 size-4 accent-foreground" /><div><p className="text-sm font-semibold">{item.asset_name || item.pack_key}</p><p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{item.pack_type} · {item.required === false ? "optional" : "required"} · {item.status || "ready"}</p></div></div><div className="flex shrink-0 items-center gap-1.5"><Badge variant="outline" className="text-[10px]">{sourceLabel}</Badge></div></div><div className="mt-2 flex flex-wrap gap-1.5"><Badge variant="secondary" className="text-[10px] capitalize">{visualMode}</Badge>{item.composition_role ? <Badge variant="outline" className="text-[10px] capitalize">{String(item.composition_role).replaceAll("_", " ")}</Badge> : null}</div><p className="mt-2 text-xs leading-5 text-foreground/80">{item.visual_brief || item.purpose}</p>{continuity.length ? <p className="mt-2 text-[11px] leading-5 text-muted-foreground"><span className="font-medium text-foreground">Continuity:</span> {continuity.join(" · ")}</p> : null}{uses.length ? <p className="mt-1 text-[11px] leading-5 text-muted-foreground"><span className="font-medium text-foreground">Used for:</span> {uses.join(" · ")}</p> : null}{constraints.length ? <p className="mt-1 text-[11px] leading-5 text-muted-foreground"><span className="font-medium text-foreground">Avoid:</span> {constraints.join(" · ")}</p> : null}<p className="mt-2 border-t pt-2 text-[11px] leading-5 text-muted-foreground"><span className="font-medium text-foreground">Source:</span> {item.source_requirement}{item.source_mode === "reference_frame" ? ` · Frame ${item.reference_frame_index + 1}` : ""}</p></label>; })}</div>
              </section> : null}
              <div className="mt-5 grid gap-4 md:grid-cols-2"><ScriptList index="05" title="Video architecture" items={direction.story_structure} /><ScriptList index="06" title="Guardrails" items={[...direction.originality_guardrails, ...direction.risks]} /></div>
            </div>
          </Card>
        ) : null}
      </ProductionConversationMessages>
      <ProductionComposer production={production} saving={saving} value={agentDraft} onChange={onAgentDraftChange} onSend={onSend} onSave={onSave} placeholder="Describe the product and outcome, ask about the reference, or refine the direction…" ariaLabel={analyzeLabel} />
    </div>
  );
}

function VideoSetupCard({ setup, saving, onSave }: { setup: VideoProduction["video_setup"]; saving: boolean; onSave: (setup: VideoProduction["video_setup"]) => void }) {
  const [draft, setDraft] = useState(setup);
  useEffect(() => setDraft(setup), [setup]);
  const update = (field: keyof typeof draft, value: string) => setDraft((current) => ({ ...current, [field]: value, confirmed: false }));
  const required = [draft.target_market, draft.target_audience, draft.video_type, draft.visual_style, draft.spoken_language].every((value) => value.trim());
  return <Card className="overflow-hidden border p-0 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-[#fffaf8] px-5 py-4"><div className="flex items-start gap-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#c96552] text-xs font-bold text-white">00</span><div><p className="text-sm font-semibold">Video setup</p><p className="mt-1 text-xs leading-5 text-muted-foreground">The Production Copilot suggests these settings from your brief and reference. Review them before it creates or revises the script.</p></div></div><Badge variant="outline" className={draft.confirmed ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-[#f2d0c8] bg-[#fffaf8] text-[#c96552]"}>{draft.confirmed ? "confirmed" : "suggested · review"}</Badge></div>
    <div className="grid gap-4 p-5 md:grid-cols-2 lg:grid-cols-3">
      <SetupField label="Target market" value={draft.target_market} placeholder="e.g. South Korea" onChange={(value) => update("target_market", value)} />
      <SetupField label="Target audience" value={draft.target_audience} placeholder="e.g. women 18–30 who play casual mobile games" onChange={(value) => update("target_audience", value)} />
      <SetupField label="Video type" value={draft.video_type} placeholder="e.g. mobile game ad, live action, short drama" onChange={(value) => update("video_type", value)} />
      <SetupField label="Visual style" value={draft.visual_style} placeholder="e.g. live action + 3D game world" onChange={(value) => update("visual_style", value)} />
      <SetupField label="Spoken language" value={draft.spoken_language} placeholder="e.g. Korean" onChange={(value) => update("spoken_language", value)} />
      <SetupField label="Subtitle language" value={draft.subtitle_language} placeholder="Optional · e.g. Korean" onChange={(value) => update("subtitle_language", value)} />
      <SetupField label="Platform" value={draft.platform} placeholder="Optional · e.g. TikTok / Reels" onChange={(value) => update("platform", value)} />
      <SetupField label="Conversion goal" value={draft.conversion_goal} placeholder="Optional · e.g. app downloads" onChange={(value) => update("conversion_goal", value)} />
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/10 px-5 py-3"><p className="text-xs text-muted-foreground">Required: market, audience, video type, visual style, and spoken language. Changing any field requires reconfirmation before the next Script pass.</p><Button size="sm" onClick={() => onSave({ ...draft, confirmed: true })} disabled={saving || !required}>{saving ? <Loader2 className="animate-spin" /> : <Check />} Confirm Video setup</Button></div>
  </Card>;
}

function SetupField({ label, value, placeholder, onChange }: { label: string; value: string; placeholder: string; onChange: (value: string) => void }) {
  return <label className="block text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">{label}<input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} className="mt-2 h-10 w-full rounded-lg border bg-background px-3 text-sm font-normal normal-case tracking-normal text-foreground outline-none focus:ring-2 focus:ring-ring" /></label>;
}

function ScriptWorkspace({ production, saving, canLock, agentDraft, onAgentDraftChange, onSend, onComplete, onSave, onLock }: { production: VideoProduction; saving: boolean; canLock: boolean; agentDraft: string; onAgentDraftChange: (value: string) => void; onSend: () => void; onComplete: () => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; onLock: () => void }) {
  const [rawScript, setRawScript] = useState(production.script.raw_script);
  const script = production.script;
  const hasDraft = Boolean(script.raw_script || script.logline || script.beats.length);

  useEffect(() => setRawScript(production.script.raw_script), [production.production_id, production.script.raw_script]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} hasContent={hasDraft} thinkingLabel="Production Copilot is drafting the script…" emptyIcon={Wand2} emptyTitle="Turn the approved plan into a script" emptyDescription="Ask the Production Copilot to draft, revise, or tighten the commercial before assets are generated.">
          {hasDraft ? (
            <Card className="overflow-hidden p-0">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4"><div><p className="text-sm font-semibold">Working script</p><p className="mt-1 text-xs text-muted-foreground">Version {script.revision} · {production.target_seconds}s</p></div><div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={onComplete} disabled={saving || !production.video_setup.confirmed}>{saving ? <Loader2 className="animate-spin" /> : <RefreshCw />} Regenerate script</Button><Button onClick={onLock} disabled={!canLock || saving}>{saving ? <Loader2 className="animate-spin" /> : <Check />} Lock script & open assets</Button></div></div>
              <div className="space-y-6 p-5">
                <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Logline</p><p className="mt-2 text-lg font-medium leading-7">{script.logline || "Use the Screenwriter to create the first version."}</p></div>
                <div className="grid gap-4 md:grid-cols-2"><ScriptList index="01" title="Style bible" items={script.style_bible} /><ScriptList index="02" title="Brand rules" items={script.brand_rules} /><ScriptList index="03" title="Asset manifest" items={script.asset_manifest} /><ScriptList index="04" title="Risks to resolve" items={script.risks} /></div>
                <div className="rounded-xl border bg-muted/10 p-4"><div className="flex items-center justify-between"><div className="flex items-center gap-3"><span className="flex size-7 items-center justify-center rounded-full bg-foreground text-[11px] font-bold text-background">05</span><p className="font-semibold">Beat sheet</p></div><Badge variant="outline">{production.target_seconds}s</Badge></div><div className="mt-4 divide-y">{script.beats.map((beat, index) => <div key={`${beat.start_seconds}-${beat.title}`} className="grid gap-2 py-3 sm:grid-cols-[32px_90px_170px_1fr]"><span className="text-xs font-semibold tabular-nums text-muted-foreground">{String(index + 1).padStart(2, "0")}</span><span className="text-sm font-medium tabular-nums">{beat.start_seconds}s–{beat.end_seconds}s</span><span className="text-sm font-medium">{beat.title}</span><span className="text-sm text-muted-foreground">{beat.purpose}</span></div>)}</div></div>
                <WorkingScriptEditor value={rawScript} saving={saving} onChange={setRawScript} onSave={() => void onSave({ script: { ...script, raw_script: rawScript } })} />
              </div>
            </Card>
          ) : null}
      </ProductionConversationMessages>
      <ProductionComposer production={production} saving={saving} value={agentDraft} onChange={onAgentDraftChange} onSend={onSend} onSave={onSave} placeholder="Ask the Screenwriter to draft or revise the commercial script…" ariaLabel="Send to Screenwriter" />
    </div>
  );
}

function WorkingScriptEditor({ value, saving, onChange, onSave }: { value: string; saving: boolean; onChange: (value: string) => void; onSave: () => void }) {
  const [editing, setEditing] = useState(false);
  const sections = useMemo(() => splitWorkingScript(value), [value]);

  return (
    <section className="overflow-hidden rounded-xl border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div><p className="text-sm font-semibold">Working script</p><p className="mt-0.5 text-xs text-muted-foreground">Review by beat, then open the full draft only when you need to edit it.</p></div>
        <Button size="sm" variant="outline" onClick={() => setEditing((current) => !current)}>{editing ? "Preview scenes" : "Edit full script"}</Button>
      </div>
      {editing ? (
        <div className="p-4"><textarea value={value} onChange={(event) => onChange(event.target.value)} className="min-h-[360px] w-full resize-y rounded-lg border bg-background p-4 text-sm leading-6 outline-none focus:ring-2 focus:ring-ring" /></div>
      ) : (
        <div className="divide-y">
          {sections.map((section, index) => <details key={`${section.timecode}-${index}`} open={index === 0} className="group">
            <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 text-left hover:bg-muted/45">
              <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
              <span className="min-w-20 text-xs font-semibold tabular-nums text-muted-foreground">{section.timecode}</span>
              <span className="line-clamp-1 text-sm font-medium">{section.title}</span>
              {section.duration > 5 ? <Badge variant="outline" className="ml-auto text-[10px] text-amber-700">Split recommended</Badge> : null}
            </summary>
            <div className="border-t bg-muted/20 px-5 py-4 pl-11 text-sm leading-6 text-foreground whitespace-pre-wrap">{section.content}</div>
          </details>)}
        </div>
      )}
      <div className="flex justify-end border-t bg-muted/15 px-4 py-3"><Button variant="secondary" onClick={onSave} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Check />} Save script edits</Button></div>
    </section>
  );
}

function splitWorkingScript(value: string): Array<{ timecode: string; title: string; content: string; duration: number }> {
  const pattern = /^\d{2}:\d{2}\s*[-–—]\s*\d{2}:\d{2}/gm;
  const matches = [...value.matchAll(pattern)];
  if (!matches.length) return [{ timecode: "Draft", title: "Working script", content: value || "No working script has been drafted yet.", duration: 0 }];

  const sections: Array<{ timecode: string; title: string; content: string; duration: number }> = [];
  const intro = value.slice(0, matches[0].index).trim();
  if (intro) sections.push({ timecode: "Notes", title: "Format and production notes", content: intro, duration: 0 });
  matches.forEach((match, index) => {
    const start = match.index ?? 0;
    const end = matches[index + 1]?.index ?? value.length;
    const content = value.slice(start, end).trim();
    const lines = content.split("\n").map((line) => line.trim()).filter(Boolean);
    const title = (lines[1] ?? `Shot ${String(index + 1).padStart(2, "0")}`).replace(/^\[[^\]]+\]\s*/, "").slice(0, 92);
    sections.push({ timecode: match[0], title, content, duration: timecodeDuration(match[0]) });
  });
  return sections;
}

function timecodeDuration(value: string): number {
  const match = value.match(/^(\d{2}):(\d{2})\s*[-–—]\s*(\d{2}):(\d{2})/);
  if (!match) return 0;
  const start = Number(match[1]) * 60 + Number(match[2]);
  const end = Number(match[3]) * 60 + Number(match[4]);
  return Math.max(0, end - start);
}

function parseWorkingScriptBlocks(rawScript: string): string[] {
  const blocks: string[] = [];
  const pattern = /\[(\d{2}:\d{2}\s*[-–—]\s*\d{2}:\d{2})\]\s*([\s\S]*?)(?=\n\s*\[\d{2}:\d{2}\s*[-–—]\s*\d{2}:\d{2}\]|$)/g;
  for (const match of rawScript.matchAll(pattern)) {
    const content = match[2]?.trim();
    if (content) blocks.push(`[${match[1]}]\n${content}`);
  }
  return blocks;
}

function DesignStage({ production, assets, saving, batchGenerating, agentDraft, onAgentDraftChange, onSend, onSave, onGenerateSheet, onCancelSheet, onReframeScene, onGenerateMissingSheets, onRegenerateAllSheets, onCreateSheet, onUpdateSheet, onDeleteSheet, onUploadSourceImages, onApproveAndDirect }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; batchGenerating: boolean; agentDraft: string; onAgentDraftChange: (value: string) => void; onSend: () => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; onGenerateSheet: (sheet: VideoProductionDesignSheet) => void; onCancelSheet: (sheet: VideoProductionDesignSheet) => Promise<void>; onReframeScene: (sheet: VideoProductionDesignSheet, sourceAssetId: string, outputAspectRatio: "project" | "16:9" | "9:16") => void; onGenerateMissingSheets: (sheets: VideoProductionDesignSheet[]) => void; onRegenerateAllSheets: (sheets: VideoProductionDesignSheet[]) => void; onCreateSheet: (payload: Parameters<typeof createVideoProductionDesignSheet>[1]) => Promise<void>; onUpdateSheet: (sheet: VideoProductionDesignSheet, payload: Parameters<typeof updateVideoProductionDesignSheet>[2]) => Promise<void>; onDeleteSheet: (sheet: VideoProductionDesignSheet) => Promise<void>; onUploadSourceImages: (files: FileList | null) => Promise<string[]>; onApproveAndDirect: () => Promise<void> }) {
  const design = production.design_bible;
  const hasDesign = design.visual_identity.length > 0
    || design.keyframe_rules.length > 0
    || design.character_and_product_rules.length > 0
    || design.logo_and_copy_rules.length > 0;
  const packOrder = ["character", "environment", "prop", "ui", "lighting", "transition"];
  const designSheets = (design.asset_packs.length ? design.asset_packs : [...design.character_consistency_sheets, ...design.scene_style_sheets])
    .slice()
    .sort((left, right) => packOrder.indexOf(left.asset_pack_type) - packOrder.indexOf(right.asset_pack_type));
  // Only Packs actually required by the locked script need approval. A short
  // commercial should not be blocked by a made-up Prop/UI/Transition category.
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages fullWidth saving={saving} thinkingLabel="Production Designer is building visual rules…" emptyIcon={ImagePlus} emptyTitle="Create the visual design bible" emptyDescription="Ask the Production Designer to turn the locked script and Brand Assets into controlled rules for keyframes, logo, products, and continuity.">
        {hasDesign ? (
          <Card className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
              <div><p className="text-sm font-semibold">Designer Asset Packs</p><p className="mt-1 text-xs text-muted-foreground">Lock only the reusable digital visual states needed before storyboarding.</p></div>
              <div className="flex items-center gap-2"><Badge variant="outline">{designSheets.length} design assets</Badge><Badge variant="outline">{design.status}</Badge></div>
            </div>
            <DesignSheetWorkspace production={production} sheets={designSheets} assets={assets} saving={saving} batchGenerating={batchGenerating} onGenerateSheet={onGenerateSheet} onCancelSheet={onCancelSheet} onReframeScene={onReframeScene} onGenerateMissingSheets={onGenerateMissingSheets} onRegenerateAllSheets={onRegenerateAllSheets} onCreateSheet={onCreateSheet} onUpdateSheet={onUpdateSheet} onDeleteSheet={onDeleteSheet} onUploadSourceImages={onUploadSourceImages} />
            <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/15 px-5 py-4">
              <p className="text-xs text-muted-foreground">Your generated images are automatically available in the Scene library and Storyboard.</p>
              <Button onClick={() => void onApproveAndDirect()} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <ArrowRight />} Open storyboard</Button>
            </div>
          </Card>
        ) : (
          <Card className="border-dashed p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div><p className="text-sm font-semibold">Production design bible</p><p className="mt-1 text-sm leading-6 text-muted-foreground">After the script is locked, ask the Production Designer to inspect the Brand Assets and define the exact visual rules before storyboard keyframes are generated.</p></div>
              <Button variant="secondary" onClick={onSend} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Sparkles />} Create design bible</Button>
            </div>
          </Card>
        )}
      </ProductionConversationMessages>
      <ProductionComposer production={production} saving={saving} value={agentDraft} onChange={onAgentDraftChange} onSend={onSend} onSave={onSave} placeholder="Ask the Production Designer to revise visual rules, Pack scope, prompts, or continuity. Use Generate on a Pack to render visual states…" ariaLabel="Send to Production Designer" />
    </div>
  );
}

function DesignSheetWorkspace({ production, sheets, assets, saving, batchGenerating, onGenerateSheet, onCancelSheet, onReframeScene, onGenerateMissingSheets, onRegenerateAllSheets, onCreateSheet, onUpdateSheet, onDeleteSheet, onUploadSourceImages }: { production: VideoProduction; sheets: VideoProductionDesignSheet[]; assets: AssetSummary[]; saving: boolean; batchGenerating: boolean; onGenerateSheet: (sheet: VideoProductionDesignSheet) => void; onCancelSheet: (sheet: VideoProductionDesignSheet) => Promise<void>; onReframeScene: (sheet: VideoProductionDesignSheet, sourceAssetId: string, outputAspectRatio: "project" | "16:9" | "9:16") => void; onGenerateMissingSheets: (sheets: VideoProductionDesignSheet[]) => void; onRegenerateAllSheets: (sheets: VideoProductionDesignSheet[]) => void; onCreateSheet: (payload: Parameters<typeof createVideoProductionDesignSheet>[1]) => Promise<void>; onUpdateSheet: (sheet: VideoProductionDesignSheet, payload: Parameters<typeof updateVideoProductionDesignSheet>[2]) => Promise<void>; onDeleteSheet: (sheet: VideoProductionDesignSheet) => Promise<void>; onUploadSourceImages: (files: FileList | null) => Promise<string[]> }) {
  const [expandedPromptIds, setExpandedPromptIds] = useState<string[]>([]);
  const [lightboxSheetId, setLightboxSheetId] = useState<string | null>(null);
  const [newPackOpen, setNewPackOpen] = useState(false);
  const [workspaceMode, setWorkspaceMode] = useState<"asset" | "scene">("asset");
  const [newPack, setNewPack] = useState({ title: "", type: "environment" as VideoProductionDesignSheet["asset_pack_type"], purpose: "", prompt: "", sourceAssetIds: [] as string[], sceneIds: [] as string[], designMode: "asset" as "asset" | "scene", outputAspectRatio: "project" as "project" | "16:9" | "9:16" });
  const sourceImages = assets.filter((asset) => asset.type === "image" || asset.type === "gif");
  const panelLabels = ["A", "B", "C", "D"];
  const packLabel = (sheet: VideoProductionDesignSheet) => ({
    character: "Character Pack",
    environment: "Environment Pack",
    prop: "Prop Pack",
    ui: "UI Pack",
    lighting: "Lighting & Color Card",
    transition: "Transition Pair",
  }[sheet.asset_pack_type] ?? (sheet.kind === "character_consistency" ? "Character Pack" : "Environment Pack"));
  const visibleSheets = sheets.filter((sheet) => (sheet.design_mode ?? "asset") === workspaceMode);
  const missingSheets = visibleSheets.filter((sheet) =>
    !sheet.grid_asset_id && !(sheet.panel_asset_ids?.length) && !(sheet.approved_asset_ids?.length) && !sheet.selected_asset_id && sheet.status !== "generating");
  const startedSheets = visibleSheets.filter((sheet) => (
    sheet.status === "generating"
    || sheet.status === "approved"
    || Boolean(sheet.grid_asset_id || sheet.panel_asset_ids?.length || sheet.approved_asset_ids?.length || sheet.selected_asset_id)
  )).length;
  const assetPackCount = sheets.filter((sheet) => (sheet.design_mode ?? "asset") === "asset").length;
  const generatedAssetPackCount = sheets.filter((sheet) => (sheet.design_mode ?? "asset") === "asset" && Boolean(sheet.grid_asset_id || sheet.panel_asset_ids?.length)).length;
  const lightboxSheet = sheets.find((sheet) => sheet.id === lightboxSheetId);
  const lightboxAsset = lightboxSheet ? assets.find((asset) => asset.id === lightboxSheet.grid_asset_id) : undefined;

  const renderSheetGrid = (sheet: VideoProductionDesignSheet, expanded = false) => {
    const gridAsset = assets.find((asset) => asset.id === sheet.grid_asset_id);
    const legacyAssets = (sheet.panel_asset_ids ?? []).map((assetId) => assets.find((asset) => asset.id === assetId)).filter((asset): asset is AssetSummary => Boolean(asset));
    const isUserAuthored = Boolean(sheet.user_authored || sheet.reason_for_new_pack === "Created manually by the user.");
    const isGridOutput = !isUserAuthored || sheet.panel_asset_ids?.length === 4;
    if (gridAsset) {
      if (!isGridOutput) {
        const ratio = sheet.design_mode === "scene"
          ? (sheet.output_aspect_ratio === "16:9" ? "16 / 9" : sheet.output_aspect_ratio === "9:16" ? "9 / 16" : production.aspect_ratio === "16:9" ? "16 / 9" : "9 / 16")
          : "1 / 1";
        return <div className={cn("relative overflow-hidden bg-slate-100", expanded ? "mx-auto max-h-[76vh] max-w-[76vw]" : "w-full")} style={{ aspectRatio: ratio }}><img src={gridAsset.url} alt={`${sheet.title} custom image`} className="size-full object-contain" /></div>;
      }
      return <div className={cn("relative overflow-hidden bg-slate-100", expanded ? "mx-auto h-[min(76vh,900px)] max-w-[min(76vh,900px)]" : "aspect-square")}> 
        <img src={gridAsset.url} alt={`${sheet.title} controlled 2x2 consistency sheet`} className="size-full object-contain" />
        <div className="pointer-events-none absolute inset-0 grid grid-cols-2 grid-rows-2">
          {panelLabels.map((label) => <div key={label} className="relative border border-white/70">
            <span className="absolute left-2 top-2 flex size-7 items-center justify-center rounded-full bg-black/65 text-xs font-bold text-white">{label}</span>
          </div>)}
        </div>
      </div>;
    }
    if (legacyAssets.length) {
      return <div className="grid aspect-square grid-cols-2 gap-1 bg-slate-100 p-1">{legacyAssets.slice(0, 4).map((asset, panel) => <div key={asset.id} className="relative overflow-hidden bg-slate-200"><img src={asset.url} alt={`Legacy candidate ${panelLabels[panel]}`} className="size-full object-cover" /><span className="absolute left-2 top-2 flex size-6 items-center justify-center rounded-full bg-black/65 text-[10px] font-bold text-white">{panelLabels[panel]}</span></div>)}</div>;
    }
    const failed = sheet.status === "failed";
    return <div className="flex aspect-square flex-col items-center justify-center bg-[linear-gradient(135deg,#f7f9fc,#edf2f7)] p-6 text-center">{sheet.status === "generating" ? <Loader2 className="size-7 animate-spin text-slate-500" /> : <Layers3 className={cn("size-8", failed ? "text-destructive" : "text-slate-400")} />}<p className={cn("mt-3 text-sm font-semibold", failed ? "text-destructive" : "text-slate-800")}>{sheet.status === "generating" ? "Generating asset pack…" : failed ? "Asset pack failed" : "Asset pack pending"}</p><p className="mt-1 text-xs leading-5 text-slate-500">{failed ? (sheet.failure_reason || "The generation failed. Try again, or check the required source assets.") : "A controlled visual sheet will appear here for review."}</p></div>;
  };

  return (
    <div className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div><p className="text-sm font-semibold">{workspaceMode === "scene" ? "Scene builder" : "Asset pack board"}</p><p className="mt-1 text-xs text-muted-foreground">{workspaceMode === "scene" ? "Combine generated characters, environments, props, and UI into storyboard-ready scene images." : "Every generated image is automatically added to your library."}</p></div>
        <div className="flex flex-wrap items-center justify-end gap-2"><Badge variant="outline">{startedSheets} / {visibleSheets.length} started</Badge><Button size="sm" variant="secondary" onClick={() => { setNewPackOpen((open) => !open); setNewPack((current) => ({ ...current, designMode: workspaceMode, type: workspaceMode === "scene" ? "environment" : current.type })); }} disabled={saving}><Plus />{workspaceMode === "scene" ? "New scene" : "New custom pack"}</Button><Button size="sm" onClick={() => onGenerateMissingSheets(visibleSheets)} disabled={saving || batchGenerating || !missingSheets.length}>{batchGenerating ? <Loader2 className="animate-spin" /> : <Sparkles />}{missingSheets.length ? `Generate ${missingSheets.length} missing` : "All generated"}</Button><Button size="sm" variant="secondary" onClick={() => onRegenerateAllSheets(visibleSheets)} disabled={saving || batchGenerating || !visibleSheets.some((sheet) => sheet.status !== "generating")}><RefreshCw className={batchGenerating ? "animate-spin" : ""} />Regenerate all</Button></div>
      </div>
      <section className="mt-5 rounded-2xl border border-slate-200 bg-slate-50/70 p-4" aria-label="Design workflow steps">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 px-1"><div><p className="text-sm font-semibold">Build scenes in two steps</p><p className="mt-0.5 text-xs text-muted-foreground">First generate reusable visual ingredients. Then combine any generated images into storyboard frames.</p></div><Badge variant="outline" className="text-[10px]">Step {workspaceMode === "asset" ? "1 of 2" : "2 of 2"}</Badge></div>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-stretch">
          <button type="button" onClick={() => { setWorkspaceMode("asset"); setNewPackOpen(false); }} className={cn("rounded-xl border bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md", workspaceMode === "asset" ? "border-[#ef8a78] ring-1 ring-[#ef8a78]/25" : "border-slate-200 hover:border-[#efb1a5]")}><div className="flex items-center gap-2.5"><span className={cn("flex size-7 items-center justify-center rounded-lg text-xs font-bold", workspaceMode === "asset" ? "bg-[#fff0ec] text-[#e86750]" : "bg-slate-100 text-slate-500")}>1</span><span className="text-sm font-semibold text-slate-800">Create asset packs</span></div><p className="mt-2 text-xs leading-5 text-slate-500">Generate characters, locations, props, and UI that must stay consistent. Every result is saved to Library.</p><p className={cn("mt-2 text-[11px] font-semibold", workspaceMode === "asset" ? "text-[#dd654f]" : "text-slate-700")}>{generatedAssetPackCount} / {assetPackCount} packs generated</p></button>
          <div className="flex items-center justify-center px-1"><ArrowRight className="hidden size-5 text-[#e6a395] sm:block" /><span className="rounded-full border border-[#f2d0c8] bg-white px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-[#d87865] sm:hidden">then</span></div>
          <button type="button" onClick={() => { setWorkspaceMode("scene"); setNewPackOpen(false); }} className={cn("rounded-xl border bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md", workspaceMode === "scene" ? "border-[#ef8a78] ring-1 ring-[#ef8a78]/25" : "border-slate-200 hover:border-[#efb1a5]")}><div className="flex items-center gap-2.5"><span className={cn("flex size-7 items-center justify-center rounded-lg text-xs font-bold", workspaceMode === "scene" ? "bg-[#fff0ec] text-[#e86750]" : "bg-slate-100 text-slate-500")}>2</span><span className="text-sm font-semibold text-slate-800">Compose scene images</span></div><p className="mt-2 text-xs leading-5 text-slate-500">Choose any generated images from Library and assemble one visual for each storyboard moment.</p><p className={cn("mt-2 text-[11px] font-semibold", workspaceMode === "scene" ? "text-[#dd654f]" : "text-slate-700")}>{generatedAssetPackCount ? "Use generated images" : "Start with Step 1 assets"}</p></button>
        </div>
      </section>
      {workspaceMode === "scene" && production.script.scenes.length ? <div className="mt-4 rounded-xl border bg-muted/10 p-4"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Suggested scenes from the script</p><div className="mt-3 flex flex-wrap gap-2">{production.script.scenes.map((scene) => <button key={scene.id} type="button" onClick={() => { setNewPackOpen(true); setNewPack({ title: scene.title || "Scene composition", type: "environment", purpose: scene.purpose || scene.action, prompt: [scene.setting, scene.action, scene.dialogue_or_copy].filter(Boolean).join("\n"), sourceAssetIds: [], sceneIds: [scene.id], designMode: "scene", outputAspectRatio: "project" }); }} className="rounded-lg border bg-background px-3 py-2 text-left text-xs transition hover:border-foreground/50"><span className="block font-semibold">{scene.title || scene.id}</span><span className="mt-1 block max-w-64 truncate text-muted-foreground">{scene.action || scene.purpose}</span></button>)}</div></div> : null}
      {newPackOpen ? <Card className="mt-5 border-dashed bg-muted/10 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm font-semibold">{newPack.designMode === "scene" ? "Create a scene composition" : "Create a custom asset pack"}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{newPack.designMode === "scene" ? "Choose generated images from Library, describe the moment, then generate one storyboard-ready scene image." : "Add the exact reusable visual state you need. Write the prompt, attach source images, and generate it; every result is immediately available in Library."}</p></div><Button size="icon" variant="ghost" onClick={() => setNewPackOpen(false)} aria-label="Close custom pack form"><X /></Button></div>
        <div className="mt-4 grid gap-4 md:grid-cols-2"><Field label={newPack.designMode === "scene" ? "Scene name" : "Pack name"} value={newPack.title} onChange={(title) => setNewPack({ ...newPack, title })} /><Field label="Purpose" value={newPack.purpose} onChange={(purpose) => setNewPack({ ...newPack, purpose })} />{newPack.designMode === "scene" ? <SelectField label={`Scene ratio · project is ${production.aspect_ratio}`} value={newPack.outputAspectRatio} options={["project", "9:16", "16:9"]} onChange={(value) => setNewPack({ ...newPack, outputAspectRatio: value as "project" | "9:16" | "16:9" })} /> : null}<Field label="Generation prompt" value={newPack.prompt} multiline onChange={(prompt) => setNewPack({ ...newPack, prompt })} /></div>
        <AssetPicker label={newPack.designMode === "scene" ? "Visual ingredients from Library" : "Source images (optional)"} assets={sourceImages} value={newPack.sourceAssetIds} onChange={(sourceAssetIds) => setNewPack({ ...newPack, sourceAssetIds })} onUpload={async (files) => { const ids = await onUploadSourceImages(files); setNewPack((current) => ({ ...current, sourceAssetIds: [...new Set([...current.sourceAssetIds, ...ids])] })); }} />
        <ScenePicker scenes={production.script.scenes} value={newPack.sceneIds} onChange={(sceneIds) => setNewPack({ ...newPack, sceneIds })} />
        <div className="mt-4 flex justify-end"><Button disabled={saving || !newPack.title.trim() || !newPack.prompt.trim()} onClick={() => void onCreateSheet({ title: newPack.title, asset_pack_type: newPack.type, purpose: newPack.purpose, prompt: newPack.prompt, source_asset_ids: newPack.sourceAssetIds, scene_ids: newPack.sceneIds, design_mode: newPack.designMode, output_aspect_ratio: newPack.outputAspectRatio }).then(() => { setNewPackOpen(false); setNewPack({ title: "", type: "environment", purpose: "", prompt: "", sourceAssetIds: [], sceneIds: [], designMode: workspaceMode, outputAspectRatio: "project" }); })}><Plus />{newPack.designMode === "scene" ? "Create scene" : "Create pack"}</Button></div>
      </Card> : null}
      <div className="mt-5 grid gap-5 md:grid-cols-2 2xl:grid-cols-3">
        {visibleSheets.map((sheet) => {
          const sourceAssets = sheet.asset_ids.map((assetId) => assets.find((asset) => asset.id === assetId)).filter((asset): asset is AssetSummary => Boolean(asset));
          const hasOutput = Boolean(sheet.grid_asset_id || sheet.panel_asset_ids?.length);
          const isUserAuthored = Boolean(sheet.user_authored || sheet.reason_for_new_pack === "Created manually by the user.");
          const isGridOutput = !isUserAuthored || sheet.panel_asset_ids?.length === 4;
          const isPromptExpanded = expandedPromptIds.includes(sheet.id);
          const availableAssetIds = Array.from(new Set([...(sheet.panel_asset_ids ?? []), sheet.grid_asset_id, ...(sheet.approved_asset_ids ?? []), ...Object.values(sheet.approved_panel_asset_ids ?? {})].filter((id): id is string => Boolean(id))));
          return <Card key={sheet.id} className="group flex min-w-0 flex-col overflow-hidden p-0 shadow-sm">
            <div className="flex items-start justify-between gap-3 border-b px-4 py-3"><div className="min-w-0"><Badge variant="outline" className="text-[10px]">{sheet.design_mode === "scene" ? "Scene candidate" : packLabel(sheet)}</Badge><p className="mt-2 line-clamp-2 text-sm font-semibold">{sheet.title}</p></div><Badge variant={sheet.status === "approved" || sheet.status === "ready" ? "success" : sheet.status === "generating" ? "accent" : sheet.status === "failed" ? "destructive" : "secondary"} className="shrink-0">{sheet.status}</Badge></div>
            <div className="relative border-b bg-slate-100">{renderSheetGrid(sheet)}{hasOutput ? <Button type="button" size="icon" variant="secondary" className="absolute right-3 top-3 rounded-full bg-background/90 shadow-md" onClick={() => setLightboxSheetId(sheet.id)} aria-label={`Expand ${sheet.title}`}><Maximize2 className="size-4" /></Button> : null}</div>
            <div className="flex flex-1 flex-col p-4">
              <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{sheet.purpose}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {sheet.scene_ids?.length ? <Badge variant="outline" className="text-[10px]">{sheet.scene_ids.length === 1 ? `Used by ${sheet.scene_ids[0]}` : `Used by ${sheet.scene_ids.length} scenes`}</Badge> : <Badge variant="outline" className="text-[10px]">Global visual rule</Badge>}
                {sheet.reason_for_new_pack ? <span className="max-w-full truncate text-[11px] leading-5 text-muted-foreground" title={sheet.reason_for_new_pack}>{sheet.reason_for_new_pack}</span> : null}
              </div>
              <div className="mt-4"><div className="flex items-center justify-between gap-2"><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">Source assets</p><span className="text-[10px] text-muted-foreground">{sourceAssets.length}</span></div><div className="mt-2 flex gap-2 overflow-x-auto pb-1">{sourceAssets.length ? sourceAssets.map((asset) => <div key={asset.id} className="group/source relative w-14 shrink-0 overflow-hidden rounded-md border bg-muted/20"><div className="flex aspect-square items-center justify-center bg-muted">{asset.type === "image" || asset.type === "gif" ? <img src={asset.url} alt="" className="size-full object-cover" /> : <Film className="size-4 text-muted-foreground" />}</div><button type="button" title="Remove from this pack" aria-label={`Remove ${asset.title} from this pack`} className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/70 text-white opacity-0 transition hover:bg-destructive group-hover/source:opacity-100 focus:opacity-100" onClick={() => void onUpdateSheet(sheet, { source_asset_ids: sheet.asset_ids.filter((assetId) => assetId !== asset.id) })} disabled={saving}><X className="size-3" /></button><p className="truncate px-1.5 py-1 text-[9px] font-medium">{asset.title}</p></div>) : <p className="text-xs text-muted-foreground">{sheet.asset_pack_type === "prop" ? "A static product image will be resolved from Brand Assets when generated." : "No linked source asset."}</p>}</div></div>
              <div className="mt-4 rounded-lg border bg-muted/20 p-3"><div className="flex items-center justify-between gap-2"><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">Image prompt</p><Sparkles className="size-3.5 text-muted-foreground" /></div><p className={cn("mt-2 whitespace-pre-wrap text-xs leading-5 text-foreground/80", !isPromptExpanded && "line-clamp-3")}>{sheet.prompt}</p><button type="button" className="mt-2 text-xs font-medium text-foreground underline-offset-4 hover:underline" onClick={() => setExpandedPromptIds((ids) => ids.includes(sheet.id) ? ids.filter((id) => id !== sheet.id) : [...ids, sheet.id])}>{isPromptExpanded ? "Collapse prompt" : "View full prompt"}</button></div>
              <DesignPackEditor sheet={sheet} sourceImages={sourceImages} scenes={production.script.scenes} saving={saving} onSave={onUpdateSheet} onDelete={onDeleteSheet} onUploadSourceImages={onUploadSourceImages} />
              <div className="mt-4 border-t pt-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-muted-foreground">{hasOutput ? `${availableAssetIds.length} generated image${availableAssetIds.length === 1 ? "" : "s"} available in Library` : "Generate this pack to add its visual states to the library"}</span><div className="flex items-center gap-2">{sheet.status === "generating" ? <Button size="sm" variant="destructive" onClick={() => void onCancelSheet(sheet)} disabled={saving}><X />Stop generation</Button> : null}{sheet.design_mode === "scene" && sheet.grid_asset_id ? <><Button size="sm" variant="secondary" onClick={() => onReframeScene(sheet, sheet.grid_asset_id!, "9:16")} disabled={saving}><Wand2 />Reframe 9:16</Button><Button size="sm" variant="secondary" onClick={() => onReframeScene(sheet, sheet.grid_asset_id!, "16:9")} disabled={saving}><Wand2 />Reframe 16:9</Button></> : null}{hasOutput && isGridOutput ? <Button size="sm" variant="secondary" onClick={() => { setWorkspaceMode("scene"); setNewPackOpen(true); setNewPack({ title: `${sheet.title} scene`, type: "environment", purpose: "Compose these generated visual states into a storyboard-ready moment.", prompt: "", sourceAssetIds: availableAssetIds, sceneIds: sheet.scene_ids ?? [], designMode: "scene", outputAspectRatio: "project" }); }}> <Layers3 />Compose scene</Button> : null}<Button size="sm" variant={hasOutput ? "outline" : "default"} onClick={() => onGenerateSheet(sheet)} disabled={saving || sheet.status === "generating"}>{sheet.status === "generating" ? <Loader2 className="animate-spin" /> : <Sparkles />}{hasOutput ? "Regenerate" : "Generate"}</Button></div></div>{sheet.design_mode === "scene" && sheet.grid_asset_id ? <p className="mt-2 text-[11px] leading-5 text-muted-foreground">Reframe uses this Scene as its only Gemini reference and creates a separate candidate at the selected ratio.</p> : hasOutput && isGridOutput ? <p className="mt-2 text-[11px] leading-5 text-muted-foreground">All four panels are automatically available in Scene Builder. Choose only the images needed for this particular scene.</p> : null}</div>
            </div>
          </Card>;
        })}
      </div>
      {lightboxSheet && lightboxAsset ? <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/85 p-6" role="dialog" aria-modal="true" aria-label="Expanded consistency sheet"><div className="relative flex max-h-full max-w-full flex-col"><div className="mb-3 flex items-center justify-between gap-4 text-sm font-medium text-white"><span>{lightboxSheet.title} - generated visual states</span><Button type="button" size="icon" variant="secondary" className="rounded-full" onClick={() => setLightboxSheetId(null)} aria-label="Close sheet"><X className="size-4" /></Button></div>{renderSheetGrid(lightboxSheet, true)}</div></div> : null}
    </div>
  );
}

function AssetPicker({ label, assets, value, onChange, onUpload }: { label: string; assets: AssetSummary[]; value: string[]; onChange: (value: string[]) => void; onUpload?: (files: FileList | null) => Promise<void> }) {
  return <div className="mt-4"><div className="flex items-center justify-between gap-3"><p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">{label}</p>{onUpload ? <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-medium text-foreground hover:underline"><Upload className="size-3.5" />Upload image<input className="sr-only" type="file" accept="image/*" multiple onChange={(event) => { void onUpload(event.target.files); event.currentTarget.value = ""; }} /></label> : null}</div>{assets.length ? <div className="mt-2 grid max-h-48 grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-5">{assets.map((asset) => { const selected = value.includes(asset.id); return <button key={asset.id} type="button" onClick={() => onChange(selected ? value.filter((id) => id !== asset.id) : [...value, asset.id])} className={cn("overflow-hidden rounded-lg border text-left", selected ? "border-foreground ring-2 ring-foreground/20" : "hover:border-foreground/50")}><img src={asset.url} alt="" className="aspect-square w-full object-cover" /><span className="block truncate px-1.5 py-1 text-[10px] font-medium">{asset.title}</span></button>; })}</div> : <p className="mt-2 text-xs text-muted-foreground">Upload an image to use it as a visual source.</p>}</div>;
}

function ScenePicker({ scenes, value, onChange }: { scenes: VideoProduction["script"]["scenes"]; value: string[]; onChange: (value: string[]) => void }) {
  if (!scenes.length) return null;
  return <div className="mt-4"><p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">Used by scenes (optional)</p><div className="mt-2 flex flex-wrap gap-2">{scenes.map((scene) => { const selected = value.includes(scene.id); return <button type="button" key={scene.id} onClick={() => onChange(selected ? value.filter((id) => id !== scene.id) : [...value, scene.id])} className={cn("rounded-full border px-3 py-1.5 text-xs", selected ? "border-foreground bg-foreground text-background" : "text-muted-foreground hover:border-foreground/50")}>{scene.title || scene.id}</button>; })}</div></div>;
}

function DesignPackEditor({ sheet, sourceImages, scenes, saving, onSave, onDelete, onUploadSourceImages }: { sheet: VideoProductionDesignSheet; sourceImages: AssetSummary[]; scenes: VideoProduction["script"]["scenes"]; saving: boolean; onSave: (sheet: VideoProductionDesignSheet, payload: Parameters<typeof updateVideoProductionDesignSheet>[2]) => Promise<void>; onDelete: (sheet: VideoProductionDesignSheet) => Promise<void>; onUploadSourceImages: (files: FileList | null) => Promise<string[]> }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ title: sheet.title, type: sheet.asset_pack_type, purpose: sheet.purpose, prompt: sheet.prompt, sourceAssetIds: sheet.asset_ids, sceneIds: sheet.scene_ids, outputAspectRatio: sheet.output_aspect_ratio ?? "project" });
  const isUserAuthored = Boolean(sheet.user_authored || sheet.reason_for_new_pack === "Created manually by the user.");
  useEffect(() => setDraft({ title: sheet.title, type: sheet.asset_pack_type, purpose: sheet.purpose, prompt: sheet.prompt, sourceAssetIds: sheet.asset_ids, sceneIds: sheet.scene_ids, outputAspectRatio: sheet.output_aspect_ratio ?? "project" }), [sheet]);
  return <details className="mt-4 rounded-lg border bg-background p-3" open={open} onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}><summary className="cursor-pointer text-xs font-semibold text-muted-foreground hover:text-foreground">Customize pack</summary><div className="mt-4 grid gap-4 sm:grid-cols-2"><Field label={sheet.design_mode === "scene" ? "Scene name" : "Pack name"} value={draft.title} onChange={(title) => setDraft({ ...draft, title })} />{!isUserAuthored ? <SelectField label="Pack type" value={draft.type} options={["character", "environment", "prop", "ui", "lighting", "transition"]} onChange={(type) => setDraft({ ...draft, type: type as VideoProductionDesignSheet["asset_pack_type"] })} /> : null}{sheet.design_mode === "scene" ? <SelectField label="Scene ratio" value={draft.outputAspectRatio} options={["project", "9:16", "16:9"]} onChange={(outputAspectRatio) => setDraft({ ...draft, outputAspectRatio: outputAspectRatio as "project" | "9:16" | "16:9" })} /> : null}<Field label="Purpose" value={draft.purpose} multiline onChange={(purpose) => setDraft({ ...draft, purpose })} /><Field label="Generation prompt" value={draft.prompt} multiline onChange={(prompt) => setDraft({ ...draft, prompt })} /></div><AssetPicker label="Source images" assets={sourceImages} value={draft.sourceAssetIds} onChange={(sourceAssetIds) => setDraft({ ...draft, sourceAssetIds })} onUpload={async (files) => { const ids = await onUploadSourceImages(files); setDraft((current) => ({ ...current, sourceAssetIds: [...new Set([...current.sourceAssetIds, ...ids])] })); }} /><ScenePicker scenes={scenes} value={draft.sceneIds} onChange={(sceneIds) => setDraft({ ...draft, sceneIds })} /><div className="mt-4 flex flex-wrap justify-between gap-2"><Button size="sm" variant="destructive" onClick={() => void onDelete(sheet)} disabled={saving}><Trash2 />Delete pack</Button><Button size="sm" onClick={() => void onSave(sheet, { title: draft.title, asset_pack_type: draft.type, purpose: draft.purpose, prompt: draft.prompt, source_asset_ids: draft.sourceAssetIds, scene_ids: draft.sceneIds, output_aspect_ratio: draft.outputAspectRatio })} disabled={saving || !draft.title.trim() || !draft.prompt.trim()}><Check />Save pack</Button></div></details>;
}

function StoryboardStage({ production, assets, selectedShot, saving, agentDraft, onAgentDraftChange, onSend, onImproveFrame, onSave, onSelectShot, onSaveShot, onSaveShotForId, openEndSceneForShotId, onEndScenePickerOpened, onMoveShot, onGenerateKeyframe, onGenerateAllKeyframes, onCreateFrame, onDeleteFrame, onNextStage }: { production: VideoProduction; assets: AssetSummary[]; selectedShot: VideoProductionShot | null; saving: boolean; agentDraft: string; onAgentDraftChange: (value: string) => void; onSend: () => void; onImproveFrame: (shot: VideoProductionShot) => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; onSelectShot: (id: string) => void; onSaveShot: (payload: Partial<VideoProductionShot>) => Promise<void>; onSaveShotForId: (shotId: string, payload: Partial<VideoProductionShot>) => Promise<void>; openEndSceneForShotId: string | null; onEndScenePickerOpened: () => void; onMoveShot: (direction: -1 | 1) => Promise<void>; onGenerateKeyframe: (shot: VideoProductionShot) => Promise<void>; onGenerateAllKeyframes: (shots: VideoProductionShot[]) => Promise<void>; onCreateFrame: (payload?: { title: string; purpose?: string; visual?: string; action?: string; duration_seconds?: number }) => Promise<void>; onDeleteFrame: (shot: VideoProductionShot) => Promise<void>; onNextStage: () => void }) {
  const shots = [...production.shots].sort((left, right) => left.order - right.order);
  const [draft, setDraft] = useState<VideoProductionShot | null>(selectedShot);
  const [scenePickerShotId, setScenePickerShotId] = useState<string | null>(null);
  const [scenePickerTarget, setScenePickerTarget] = useState<"start" | "end">("start");
  const [scenePickerSource, setScenePickerSource] = useState<"scenes" | "library">("scenes");
  const [endScenePreviewAsset, setEndScenePreviewAsset] = useState<AssetSummary | null>(null);
  const [customFrameOpen, setCustomFrameOpen] = useState(false);
  const [customFrame, setCustomFrame] = useState({ title: "", purpose: "", visual: "", action: "", duration_seconds: 4 });
  useEffect(() => setDraft(selectedShot), [selectedShot]);
  useEffect(() => {
    if (!openEndSceneForShotId || !shots.some((shot) => shot.id === openEndSceneForShotId)) return;
    setScenePickerShotId(openEndSceneForShotId);
    setScenePickerTarget("end");
    setScenePickerSource("scenes");
    onEndScenePickerOpened();
  }, [openEndSceneForShotId, shots, onEndScenePickerOpened]);

  const selectedKeyframe = draft?.keyframe_asset_id ? assets.find((asset) => asset.id === draft.keyframe_asset_id) : null;
  // New productions use asset_packs, while older saved productions may still
  // keep manual Scene Builder work only in scene_style_sheets. Merge every
  // persisted location here so a valid scene never disappears from Storyboard.
  const assetPacks = Array.from(new Map([
    ...production.design_bible.asset_packs,
    ...production.design_bible.character_consistency_sheets,
    ...production.design_bible.scene_style_sheets,
  ].map((pack) => [pack.id, pack] as const)).values());
  const statesFor = (...types: string[]) => assetPacks.flatMap((pack) => {
    const inferredType = pack.asset_pack_type === "environment" && pack.kind === "character_consistency" ? "character" : pack.asset_pack_type;
    if (!types.includes(inferredType)) return [];
    const ids = Array.from(new Set([
      ...Object.values(pack.approved_panel_asset_ids ?? {}),
      ...(pack.approved_asset_ids ?? []),
      pack.selected_asset_id,
    ].filter((id): id is string => typeof id === "string" && id.length > 0)));
    return ids.map((id) => {
      const asset = assets.find((candidate) => candidate.id === id);
      return { id, label: `${pack.title} - ${asset?.title ?? id}` };
    });
  });
  const characterStates = statesFor("character");
  const environmentStates = statesFor("environment");
  const propUiStates = statesFor("prop", "ui");
  const transitionStates = statesFor("transition");
  const sceneFrameOptionEntries = assetPacks.filter((pack) => pack.design_mode === "scene").flatMap((pack) => {
    const ids = Array.from(new Set([
      pack.grid_asset_id,
      ...Object.values(pack.approved_panel_asset_ids ?? {}),
      ...(pack.approved_asset_ids ?? []),
      pack.selected_asset_id,
    ].filter((id): id is string => typeof id === "string" && id.length > 0)));
    return ids.map((id) => [id, { id, label: `Scene · ${pack.title}` }] as const);
  });
  const storyboardFrameOptionEntries = [
    ...sceneFrameOptionEntries,
    ...assetPacks.filter((pack) => pack.design_mode !== "scene").flatMap((pack) => {
      const ids = Array.from(new Set([
        ...Object.values(pack.approved_panel_asset_ids ?? {}),
        ...(pack.approved_asset_ids ?? []),
        pack.selected_asset_id,
      ].filter((id): id is string => typeof id === "string" && id.length > 0)));
      return ids.map((id) => [id, { id, label: `${pack.design_mode === "scene" ? "Scene" : "Asset"} · ${pack.title} · ${assets.find((asset) => asset.id === id)?.title ?? id}` }] as const);
    }),
    ...assets.filter((asset) => asset.type === "image" || asset.type === "gif").map((asset) => [asset.id, { id: asset.id, label: `Library · ${asset.title}` }] as const),
  ];
  // The old Map was accidentally constructed from option objects instead of
  // [id, option] entries, leaving undefined options at render time.
  const storyboardFrameOptions = Array.from(new Map<string, { id: string; label: string }>(storyboardFrameOptionEntries).values());
  const sceneLibraryAssets = storyboardFrameOptions
    .filter((option) => option.label.startsWith("Scene ·"))
    .map((option) => assets.find((asset) => asset.id === option.id))
    .filter((asset): asset is AssetSummary => Boolean(asset));
  const importableLibraryImages = assets.filter((asset) => (asset.type === "image" || asset.type === "gif") && !sceneLibraryAssets.some((scene) => scene.id === asset.id));
  const scriptSceneOptions = production.script.scenes.map((scene) => ({ id: scene.id, label: `${scene.id} · ${scene.title || scene.purpose || "Untitled script moment"}` }));
  const workingScriptBlocks = parseWorkingScriptBlocks(production.script.raw_script);
  const workingScriptForShot = (shot: VideoProductionShot) => workingScriptBlocks[shot.order - 1] ?? "";
  const renderedFrameCount = shots.filter((shot) => Boolean(shot.keyframe_asset_id)).length;
  const pendingFrameCount = shots.length - renderedFrameCount;
  const approvedFrameCount = shots.filter((shot) => shot.status === "approved").length;
  const scenePickerShot = scenePickerShotId ? shots.find((shot) => shot.id === scenePickerShotId) ?? null : null;
  const openScenePicker = (shot: VideoProductionShot, target: "start" | "end" = "start") => {
    onSelectShot(shot.id);
    setScenePickerSource("scenes");
    setScenePickerTarget(target);
    setScenePickerShotId(shot.id);
  };
  const chooseSceneImage = (asset: AssetSummary) => {
    if (!scenePickerShot) return;
    onSelectShot(scenePickerShot.id);
    if (scenePickerTarget === "end") {
      setDraft((current) => current?.id === scenePickerShot.id ? { ...current, end_keyframe_asset_id: asset.id } : current);
      void onSaveShotForId(scenePickerShot.id, { end_keyframe_asset_id: asset.id });
    } else {
      setDraft((current) => current?.id === scenePickerShot.id ? { ...current, keyframe_asset_id: asset.id, status: "approved" } : current);
      void onSaveShotForId(scenePickerShot.id, { keyframe_asset_id: asset.id, status: "approved" });
    }
    setScenePickerShotId(null);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} thinkingLabel="Director is refining shot cards…" emptyIcon={Layers3} emptyTitle="Create storyboard shot cards" emptyDescription="Ask the Director to convert the locked script and design bible into shot cards with keyframe intent, continuity, and Veo prompts.">
        <div className="border-t pt-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-sm font-semibold">Storyboard</p>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">Each frame is one unchanged Working Script moment. Select one Scene Builder image for each frame, then move to video generation.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{renderedFrameCount} / {shots.length} Scene images selected</Badge><Button variant="secondary" onClick={() => setCustomFrameOpen((open) => !open)} disabled={saving}><Plus />Add custom Frame</Button><Button variant="secondary" onClick={onSend} disabled={saving || !shots.length}>{saving ? <Loader2 className="animate-spin" /> : <Sparkles />} Generate all Director Prompts</Button><Button onClick={onNextStage} disabled={!shots.length || renderedFrameCount !== shots.length}><ArrowRight />{renderedFrameCount === shots.length ? "Go to video generate" : `Choose ${shots.length - renderedFrameCount} more Scene image${shots.length - renderedFrameCount === 1 ? "" : "s"}`}</Button></div>
          </div>

          {customFrameOpen ? <Card className="mt-5 border-dashed bg-muted/10 p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">Add a custom storyboard Frame</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Create any bridge, cutaway, or CTA Frame. It will immediately appear in Video generate after you choose its Start Scene.</p></div><Button size="icon" variant="ghost" onClick={() => setCustomFrameOpen(false)} aria-label="Close custom Frame form"><X /></Button></div><div className="mt-4 grid gap-4 md:grid-cols-2"><Field label="Frame title" value={customFrame.title} onChange={(title) => setCustomFrame({ ...customFrame, title })} /><Field label="Purpose" value={customFrame.purpose} onChange={(purpose) => setCustomFrame({ ...customFrame, purpose })} /><Field label="Visual action" value={customFrame.visual} multiline onChange={(visual) => setCustomFrame({ ...customFrame, visual })} /><Field label="Motion / camera" value={customFrame.action} multiline onChange={(action) => setCustomFrame({ ...customFrame, action })} /><label className="text-xs font-medium text-muted-foreground">Storyboard duration<select value={customFrame.duration_seconds} onChange={(event) => setCustomFrame({ ...customFrame, duration_seconds: Number(event.target.value) })} className="mt-2 h-10 w-full rounded-lg border bg-background px-2 text-sm text-foreground"><option value={3}>3 seconds</option><option value={4}>4 seconds</option><option value={6}>6 seconds</option><option value={8}>8 seconds</option></select></label></div><div className="mt-4 flex justify-end"><Button onClick={() => void onCreateFrame(customFrame).then(() => { setCustomFrameOpen(false); setCustomFrame({ title: "", purpose: "", visual: "", action: "", duration_seconds: 4 }); })} disabled={saving || !customFrame.title.trim()}><Plus />Create Frame</Button></div></Card> : null}

          {shots.length ? (
            <>
              <div className="mt-6 grid gap-x-8 gap-y-10 md:grid-cols-2 xl:grid-cols-3">
                {shots.map((shot) => {
                  const cardKeyframe = assets.find((asset) => asset.id === shot.keyframe_asset_id);
                  const cardEndFrame = assets.find((asset) => asset.id === shot.end_keyframe_asset_id);
                  const scriptExcerpt = workingScriptForShot(shot);
                  return (
                    <article key={shot.id} className={cn("group min-w-0", selectedShot?.id === shot.id && "rounded-xl outline outline-2 outline-foreground outline-offset-4")}>
                      <button type="button" onClick={() => openScenePicker(shot)} className="block w-full text-left" aria-label={`Choose a Scene image for frame ${shot.order}: ${shot.title}`}>
                        <div className="mb-2 flex items-center justify-between gap-2"><span className="text-xs font-semibold uppercase tracking-[0.12em] text-foreground">Frame {shot.order}</span><span className="text-xs tabular-nums text-muted-foreground">{formatReferenceTimecode(shot.start_seconds)} · {shot.duration_seconds}s</span></div>
                        <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-sm border bg-[linear-gradient(135deg,#e8edf5,#f8fafc)] transition group-hover:border-foreground/50">
                          {cardKeyframe ? <img src={cardKeyframe.url} alt={`Storyboard frame ${shot.order}: ${shot.title}`} className="size-full object-contain" /> : <div className="max-w-[14rem] px-5 text-center"><ImagePlus className="mx-auto size-6 text-muted-foreground" /><p className="mt-3 text-sm font-semibold text-foreground">Choose a Scene image</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Click to open your Scene library.</p></div>}
                          {cardKeyframe ? <span className="absolute right-2 top-2 rounded-full bg-background/90 px-2 py-1 text-[10px] font-medium shadow-sm">Scene selected</span> : null}
                        </div>
                      </button>
                      <button type="button" onClick={() => openScenePicker(shot)} className="mt-3 block w-full text-left"><p className="text-sm font-semibold leading-5 transition group-hover:underline">{shot.title}</p><p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted-foreground">{scriptExcerpt || shot.visual || shot.action || shot.purpose}</p></button>
                      {cardKeyframe ? <div className="mt-3 flex items-center justify-between gap-2 border-t pt-3"><div className="flex min-w-0 items-center gap-2">{cardEndFrame ? <button type="button" onClick={() => setEndScenePreviewAsset(cardEndFrame)} className="group/end relative size-8 shrink-0 overflow-hidden rounded border focus:outline-none focus:ring-2 focus:ring-foreground/30" aria-label={`Expand end Scene: ${cardEndFrame.title}`}><img src={cardEndFrame.url} alt="Selected end scene" className="size-full object-cover" /><span className="absolute inset-0 flex items-center justify-center bg-black/45 text-white opacity-0 transition group-hover/end:opacity-100 group-focus-visible/end:opacity-100"><Maximize2 className="size-3.5" /></span></button> : <span className="flex size-8 items-center justify-center rounded border border-dashed text-[10px] text-muted-foreground">End</span>}<span className="truncate text-xs text-muted-foreground">{cardEndFrame ? "End Scene selected · first/last frame" : "Single start-frame video"}</span></div><div className="flex shrink-0 items-center gap-1">{cardEndFrame ? <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => void onSaveShotForId(shot.id, { end_keyframe_asset_id: null })}><X />Remove</Button> : null}<Button size="sm" variant="secondary" className="h-7 px-2 text-xs" onClick={() => openScenePicker(shot, "end")}>{cardEndFrame ? "Change end" : "Add end Scene"}</Button><Button size="icon" variant="ghost" className="size-7 text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => void onDeleteFrame(shot)} aria-label={`Delete Frame ${shot.order}`}><Trash2 className="size-3.5" /></Button></div></div> : null}
                    </article>
                  );
                })}
              </div>

              {selectedShot && draft ? (
                <Card className="mt-12 overflow-hidden">
                  <div className="p-5">
                    <div className="flex items-center justify-between gap-2">
                      <div><span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Frame {draft.order} · starts {formatReferenceTimecode(draft.start_seconds)} · {draft.duration_seconds}s</span><h3 className="mt-1 text-lg font-semibold">{draft.title}</h3></div>
                      <div className="flex items-center gap-2"><span className="text-xs text-muted-foreground">Frame order follows the locked Working Script.</span><Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => void onDeleteFrame(draft)} disabled={saving}><Trash2 />Delete Frame</Button></div>
                    </div>
                    <div className="mt-5 grid gap-4 lg:grid-cols-2">
                      <div className="rounded-xl border border-[#f2d0c8] bg-[#fffaf8] p-4"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#c96552]">Working Script · locked</p><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{workingScriptForShot(draft) || "No matching Working Script block."}</p></div>
                      <div className="rounded-xl border bg-slate-50 p-4"><div className="flex flex-wrap items-baseline justify-between gap-2"><div><p className="text-sm font-semibold">Director Veo Prompt</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Generated from the matching Working Script. Edit and save this Frame’s production prompt.</p></div><Badge variant="outline">Frame {draft.order}</Badge></div><textarea value={draft.veo_prompt} onChange={(event) => setDraft({ ...draft, veo_prompt: event.target.value })} rows={12} className="mt-3 w-full resize-none rounded-lg border bg-background px-3 py-2 font-mono text-xs leading-5 outline-none transition focus:border-foreground focus:ring-1 focus:ring-foreground/20" /><div className="mt-3 flex flex-wrap justify-end gap-2"><Button size="sm" variant="secondary" onClick={() => onImproveFrame(draft)} disabled={saving}><Sparkles />Ask Director to improve</Button><Button size="sm" onClick={() => void onSaveShot(draft)} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Check />} Save Director Prompt</Button></div></div>
                    </div>
                    <details className="hidden mt-5 rounded-xl border bg-background p-4">
                      <summary className="cursor-pointer text-sm font-semibold text-muted-foreground transition hover:text-foreground">Edit production settings</summary>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">Optional: camera, selected library images, continuity, and the generation prompt.</p>
                    <div className="mt-4 grid gap-4 sm:grid-cols-2">
                      <Field label="Purpose" value={draft.purpose} onChange={(value) => setDraft({ ...draft, purpose: value })} />
                      <Field label="Camera" value={draft.camera} onChange={(value) => setDraft({ ...draft, camera: value })} />
                      <Field label="Visual / keyframe intent" value={draft.visual} multiline onChange={(value) => setDraft({ ...draft, visual: value })} />
                      <Field label="Action" value={draft.action} multiline onChange={(value) => setDraft({ ...draft, action: value })} />
                      <Field label="Continuity" value={draft.continuity} multiline onChange={(value) => setDraft({ ...draft, continuity: value })} />
                      <Field label="Audio cue" value={draft.audio_cue} multiline onChange={(value) => setDraft({ ...draft, audio_cue: value })} />
                    </div>
                    <div className="mt-5 rounded-xl border bg-muted/15 p-4">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <div><p className="text-sm font-semibold">Asset Pack bindings</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Bind reusable, approved states to this shot. The contact sheet itself is never sent to Veo.</p></div>
                        <Badge variant="outline">Shot-level inputs</Badge>
                      </div>
                      <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        <AssetStateSelect label="Character state" value={draft.character_state_asset_id ?? null} options={characterStates} onChange={(value) => setDraft({ ...draft, character_state_asset_id: value })} />
                        <AssetStateSelect label="Environment angle" value={draft.environment_state_asset_id ?? null} options={environmentStates} onChange={(value) => setDraft({ ...draft, environment_state_asset_id: value })} />
                        <AssetStateSelect label="Transition in anchor" value={draft.transition_in_asset_id ?? null} options={transitionStates} onChange={(value) => setDraft({ ...draft, transition_in_asset_id: value })} />
                        <AssetStateSelect label="Transition out anchor" value={draft.transition_out_asset_id ?? null} options={transitionStates} onChange={(value) => setDraft({ ...draft, transition_out_asset_id: value })} />
                      </div>
                      <div className="mt-4"><p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">Additional character states</p><div className="mt-2 flex flex-wrap gap-2">{characterStates.filter((state) => state.id !== draft.character_state_asset_id).map((state) => {
                        const additionalCharacterStates = draft.additional_character_state_asset_ids ?? [];
                        const selected = additionalCharacterStates.includes(state.id);
                        return <button key={state.id} type="button" onClick={() => setDraft({ ...draft, additional_character_state_asset_ids: selected ? additionalCharacterStates.filter((id) => id !== state.id) : [...additionalCharacterStates, state.id] })} className={cn("rounded-full border px-3 py-1.5 text-xs transition", selected ? "border-foreground bg-foreground text-background" : "border-border bg-background text-muted-foreground hover:border-foreground/40 hover:text-foreground")}>{state.label}</button>;
                      })}{characterStates.length < 2 ? <p className="text-xs text-muted-foreground">Approve another Character Pack state in Design for dialogue or reaction shots.</p> : null}</div></div>
                      <div className="mt-4"><p className="text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground">Product and UI states</p><div className="mt-2 flex flex-wrap gap-2">{propUiStates.length ? propUiStates.map((state) => {
                        const selected = draft.prop_ui_asset_ids.includes(state.id);
                        return <button key={state.id} type="button" onClick={() => setDraft({ ...draft, prop_ui_asset_ids: selected ? draft.prop_ui_asset_ids.filter((id) => id !== state.id) : [...draft.prop_ui_asset_ids, state.id] })} className={cn("rounded-full border px-3 py-1.5 text-xs transition", selected ? "border-foreground bg-foreground text-background" : "border-border bg-background text-muted-foreground hover:border-foreground/40 hover:text-foreground")}>{state.label}</button>;
                      }) : <p className="text-xs text-muted-foreground">Approve a Prop or UI Pack state in Design to bind it here.</p>}</div></div>
                      <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        <Field label="Lighting and color rule" value={draft.lighting_rule} multiline onChange={(value) => setDraft({ ...draft, lighting_rule: value })} />
                        <Field label="Motion blueprint" value={draft.motion_blueprint} multiline onChange={(value) => setDraft({ ...draft, motion_blueprint: value })} />
                      </div>
                    </div>
                    <div className="mt-5 flex justify-end"><Button onClick={() => void onSaveShot(draft)} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Check />} Save production settings</Button></div>
                    </details>
                  </div>
                  <div className="hidden border-t bg-muted/20 p-5 lg:border-l lg:border-t-0">
                    <p className="text-sm font-semibold">Storyboard frame</p>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">Choose a start image above, or render a new still from this shot’s settings. Review it here, then approve it as the visual starting state for video.</p>
                    {selectedKeyframe ? <img src={selectedKeyframe.url} alt="Selected storyboard frame" className="mt-4 aspect-video w-full rounded-lg border object-contain" /> : <div className="mt-5 rounded-xl border border-dashed bg-background p-4"><ImagePlus className="size-5 text-muted-foreground" /><p className="mt-3 text-sm font-medium">Render this storyboard frame</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{draft.visual || draft.purpose}</p></div>}
                    <Button className="mt-4 w-full" onClick={() => void onGenerateKeyframe(selectedShot)} disabled={saving || selectedShot.status === "generating"}><Sparkles /> {selectedShot.status === "generating" ? "Rendering frame…" : selectedKeyframe ? "Re-render storyboard frame" : "Render storyboard frame"}</Button>
                    <Button className="mt-2 w-full" onClick={() => void onSaveShot({ keyframe_asset_id: draft.keyframe_asset_id, end_keyframe_asset_id: draft.end_keyframe_asset_id, status: "approved" })} disabled={saving || !selectedKeyframe || selectedShot.status === "approved"}><Check /> {selectedShot.status === "approved" ? "Frame approved" : "Approve storyboard frame"}</Button>
                  </div>
                </Card>
              ) : null}
            </>
          ) : (
            <Card className="mt-5 border-dashed p-6 text-sm leading-6 text-muted-foreground">No shot cards yet. Ask the Director to create storyboard cards after the design bible is approved.</Card>
          )}
        </div>
      </ProductionConversationMessages>
      {scenePickerShot ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="dialog" aria-modal="true" aria-labelledby="scene-picker-title" onMouseDown={() => setScenePickerShotId(null)}>
        <div className="max-h-[88vh] w-full max-w-5xl overflow-hidden rounded-2xl border bg-background shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
          <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
            <div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#c96552]">Frame {scenePickerShot.order} · {scenePickerTarget === "end" ? "end frame" : "start frame"}</p><h3 id="scene-picker-title" className="mt-1 text-lg font-semibold">Choose a {scenePickerTarget === "end" ? "ending" : "starting"} Scene image</h3><p className="mt-1 text-sm text-muted-foreground">{scenePickerTarget === "end" ? "Veo will move from this Frame’s start image toward this selected ending composition." : "Select the already generated scene that matches this unchanged Working Script moment."}</p></div>
            <Button variant="ghost" size="icon" onClick={() => setScenePickerShotId(null)} aria-label="Close Scene library"><X /></Button>
          </div>
            <div className="max-h-[calc(88vh-6.5rem)] overflow-y-auto p-5">
            {workingScriptForShot(scenePickerShot) ? <div className="mb-5 rounded-xl border border-[#f2d0c8] bg-[#fffaf8] p-4"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#c96552]">Working script · unchanged</p><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{workingScriptForShot(scenePickerShot)}</p></div> : null}
            <div className="mb-4 flex items-center gap-2 border-b pb-3">
              <button type="button" onClick={() => setScenePickerSource("scenes")} className={cn("rounded-lg px-3 py-2 text-sm font-semibold transition", scenePickerSource === "scenes" ? "bg-[#fff0ec] text-[#c96552]" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>Scene Builder images <span className="ml-1 text-xs font-medium">{sceneLibraryAssets.length}</span></button>
              <button type="button" onClick={() => setScenePickerSource("library")} className={cn("rounded-lg px-3 py-2 text-sm font-semibold transition", scenePickerSource === "library" ? "bg-[#fff0ec] text-[#c96552]" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>Import from Library <span className="ml-1 text-xs font-medium">{importableLibraryImages.length}</span></button>
            </div>
            {scenePickerSource === "scenes" && sceneLibraryAssets.length ? <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">{sceneLibraryAssets.filter((asset) => scenePickerTarget !== "end" || asset.id !== scenePickerShot.keyframe_asset_id).map((asset) => { const selected = (scenePickerTarget === "end" ? scenePickerShot.end_keyframe_asset_id : scenePickerShot.keyframe_asset_id) === asset.id; return <button key={asset.id} type="button" onClick={() => chooseSceneImage(asset)} disabled={saving} className={cn("group overflow-hidden rounded-xl border bg-background text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md", selected ? "border-[#e86750] ring-2 ring-[#e86750]/25" : "hover:border-[#e86750]/70")}><img src={asset.url} alt={asset.title} className="aspect-[9/16] w-full object-cover" /><div className="flex items-center justify-between gap-2 p-3"><span className="truncate text-xs font-semibold">{asset.title}</span>{selected ? <Badge className="shrink-0 bg-[#e86750] text-white hover:bg-[#e86750]">Selected</Badge> : <span className="shrink-0 text-xs font-medium text-[#c96552]">{scenePickerTarget === "end" ? "Use as end" : "Use image"}</span>}</div></button>; })}</div> : null}
            {scenePickerSource === "library" && importableLibraryImages.length ? <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">{importableLibraryImages.map((asset) => <button key={asset.id} type="button" onClick={() => chooseSceneImage(asset)} disabled={saving} className="group overflow-hidden rounded-xl border bg-background text-left shadow-sm transition hover:-translate-y-0.5 hover:border-[#e86750]/70 hover:shadow-md"><img src={asset.url} alt={asset.title} className="aspect-[9/16] w-full object-cover" /><div className="flex items-center justify-between gap-2 p-3"><span className="truncate text-xs font-semibold">{asset.title}</span><span className="shrink-0 text-xs font-medium text-[#c96552]">Import</span></div></button>)}</div> : null}
            {scenePickerSource === "scenes" && !sceneLibraryAssets.length ? <div className="rounded-xl border border-dashed bg-muted/20 p-8 text-center"><ImagePlus className="mx-auto size-7 text-muted-foreground" /><p className="mt-3 text-sm font-semibold">No Scene Builder images found</p><p className="mt-1 text-sm text-muted-foreground">Only images created in Design → Scene builder appear here. You can also use Import from Library for an existing image.</p><Button className="mt-4" variant="secondary" onClick={() => setScenePickerSource("library")}>Import from Library</Button></div> : null}
            {scenePickerSource === "library" && !importableLibraryImages.length ? <div className="rounded-xl border border-dashed bg-muted/20 p-8 text-center"><ImagePlus className="mx-auto size-7 text-muted-foreground" /><p className="mt-3 text-sm font-semibold">No importable images in Library</p><p className="mt-1 text-sm text-muted-foreground">Upload an image in Library, or create one in Scene Builder first.</p></div> : null}
          </div>
        </div>
      </div> : null}
      <AssetPreviewLightbox asset={endScenePreviewAsset} label="End Scene preview" onClose={() => setEndScenePreviewAsset(null)} />
      <ProductionComposer production={production} saving={saving} value={agentDraft} onChange={onAgentDraftChange} onSend={onSend} onSave={onSave} placeholder="Ask the Director to revise shot order, split long beats, tighten continuity, or regenerate the storyboard plan…" ariaLabel="Send to Director" />
    </div>
  );
}

function GenerateStage({ production, assets, saving, busyShotIds, onGenerateShot, onExtractBridgeFrame, onSaveShotForId, onEditEndScene, onStageChange }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; busyShotIds: string[]; onGenerateShot: (shot: VideoProductionShot, veoPrompt?: string, variants?: 1 | 2) => Promise<void>; onExtractBridgeFrame: (shot: VideoProductionShot, timestampSeconds: number, targetShotId?: string) => Promise<void>; onSaveShotForId: (shotId: string, payload: Partial<VideoProductionShot>) => Promise<void>; onEditEndScene: (shotId: string) => void; onStageChange: (stage: VideoProductionStage) => void }) {
  const approvedCount = production.shots.filter((shot) => shot.status === "approved").length;
  const readyCount = production.shots.filter((shot) => shot.status === "ready").length;
  const [promptDrafts, setPromptDrafts] = useState<Record<string, string>>({});
  const [bridgeTimestampDrafts, setBridgeTimestampDrafts] = useState<Record<string, number>>({});
  const [endScenePreviewAsset, setEndScenePreviewAsset] = useState<AssetSummary | null>(null);
  const defaultPromptFor = (shot: VideoProductionShot) => shot.veo_prompt;
  useEffect(() => {
    setPromptDrafts((current) => Object.fromEntries(production.shots.map((shot) => [shot.id, current[shot.id] ?? defaultPromptFor(shot)])));
  }, [production.shots]);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} thinkingLabel="Video generation queue is updating…" emptyIcon={Sparkles} emptyTitle="Video generation queue" emptyDescription="Each storyboard Frame becomes one editable Veo image-to-video request.">
        <div className="border-t pt-5">
          <Card className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
              <div><p className="text-sm font-semibold">Video generate</p><p className="mt-1 text-xs text-muted-foreground">Review the scene image, duration, and Veo prompt. Edit the prompt any time, then generate or regenerate that one video.</p></div>
              <div className="flex gap-2"><Badge variant="outline">{approvedCount} approved</Badge><Badge variant="outline">{readyCount} ready</Badge></div>
            </div>
            <div className="divide-y bg-muted/5">
              {production.shots.length ? production.shots.map((shot) => {
                const shotBusy = busyShotIds.includes(shot.id);
                // The storyboard Scene is always the source of truth for this
                // row. A generated take is kept as history, but it must never
                // hide a newly selected Start or End Scene.
                const video = assets.find((asset) => asset.id === (shot.selected_video_asset_id ?? shot.video_asset_ids[0]));
                const keyframe = assets.find((asset) => asset.id === shot.keyframe_asset_id);
                const endFrame = assets.find((asset) => asset.id === shot.end_keyframe_asset_id);
                const needsIntermediate = Boolean(shot.end_keyframe_asset_id && shot.first_last_frame_status === "needs_intermediate");
                const needsDirectorReview = Boolean(shot.end_keyframe_asset_id && shot.first_last_frame_status === "not_set");
                const prompt = promptDrafts[shot.id] ?? defaultPromptFor(shot);
                const veoDuration = shot.generation_duration_seconds ?? (shot.duration_seconds <= 4 ? 4 : shot.duration_seconds <= 6 ? 6 : 8);
                const generationMode = shot.generation_mode ?? (shot.end_keyframe_asset_id ? "first_last_frame" : "image_to_video");
                const requiresFirstLastReview = generationMode === "first_last_frame";
                const bridgeTimestamp = bridgeTimestampDrafts[shot.id] ?? Math.max(0, veoDuration - 0.5);
                const nextShot = production.shots.find((candidate) => candidate.order === shot.order + 1);
                return (
                  <div key={shot.id} className="grid gap-4 px-5 py-5 lg:grid-cols-[180px_minmax(0,1fr)_auto] lg:items-start">
                    <div className="min-w-0">
                      <p className="mb-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-[#c96552]">Start Scene</p>
                      <div className="overflow-hidden rounded-lg border bg-muted">
                        {keyframe ? <img src={keyframe.url} alt={`${shot.title} start scene`} className="aspect-[9/16] w-full object-cover" /> : <div className="flex aspect-[9/16] items-center justify-center text-center"><div><Film className="mx-auto size-5 text-muted-foreground" /><p className="mt-2 px-3 text-xs text-muted-foreground">No Scene image</p></div></div>}
                      </div>
                      {endFrame ? <div className={cn("mt-2 rounded-lg border p-2", needsIntermediate ? "border-amber-300 bg-amber-50" : "bg-[#fffaf8]")}><p className={cn("text-[9px] font-semibold uppercase tracking-[0.12em]", needsIntermediate ? "text-amber-700" : "text-[#c96552]")}>{needsIntermediate ? "Bridge frame needed" : "End Scene"}</p><div className="mt-1 flex items-center gap-1.5"><ArrowRight className={cn("size-3.5 shrink-0", needsIntermediate ? "text-amber-700" : "text-[#c96552]")} /><button type="button" onClick={() => setEndScenePreviewAsset(endFrame)} className="group/end relative min-w-0 flex-1 overflow-hidden rounded border focus:outline-none focus:ring-2 focus:ring-foreground/30" aria-label={`Expand end Scene: ${endFrame.title}`}><img src={endFrame.url} alt={`${shot.title} end scene`} className="aspect-[9/16] w-full object-cover" /><span className="absolute inset-0 flex items-center justify-center bg-black/45 text-white opacity-0 transition group-hover/end:opacity-100 group-focus-visible/end:opacity-100"><Maximize2 className="size-4" /></span></button></div>{needsIntermediate ? <p className="mt-2 text-[10px] leading-4 text-amber-800">{shot.first_last_frame_note || "The selected start and end Scenes need a smaller movement step between them."}</p> : null}</div> : <p className="mt-2 text-[10px] leading-4 text-muted-foreground">No End Scene · start-frame video</p>}
                      {video ? <details className="mt-2 rounded-lg border bg-background p-2"><summary className="cursor-pointer text-[10px] font-medium text-muted-foreground">Current generated take</summary><video src={video.url} controls className="mt-2 aspect-[9/16] w-full rounded bg-black object-cover" /></details> : null}
                    </div>
                    <div className="min-w-0"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-sm font-semibold">S{String(shot.order).padStart(2, "0")} · {shot.title}</p><p className="mt-1 text-xs text-muted-foreground">{veoDuration}s Veo · {production.aspect_ratio} · {production.resolution} · {generationMode === "extend" ? "Extend Take" : generationMode === "first_last_frame" ? "First/last-frame" : "Start-frame"} · {shotBusy ? "Saving…" : shot.status === "approved" ? "Ready" : shot.status === "generating" ? "Generating video…" : shot.status === "ready" ? "Video ready" : "Choose a Scene image in Storyboard"}</p></div><div className="flex gap-1"><Badge variant="outline">{shot.status}</Badge>{shot.take_outdated ? <Badge className="border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-50">Take outdated</Badge> : null}</div></div><div className="mt-3 flex flex-wrap items-end gap-3"><label className="block"><span className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Veo duration</span><select value={veoDuration} onChange={(event) => void onSaveShotForId(shot.id, { generation_duration_seconds: Number(event.target.value) as 4 | 6 | 8 })} disabled={saving || shotBusy || shot.status === "generating"} className="mt-1 block rounded-lg border bg-background px-2.5 py-1.5 text-sm font-medium outline-none focus:border-foreground"><option value={4}>4 seconds</option><option value={6}>6 seconds</option><option value={8}>8 seconds</option></select></label><label className="block"><span className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Variants</span><select value={shot.generation_variants ?? 2} onChange={(event) => void onSaveShotForId(shot.id, { generation_variants: Number(event.target.value) as 1 | 2 })} disabled={saving || shotBusy || shot.status === "generating"} className="mt-1 block rounded-lg border bg-background px-2.5 py-1.5 text-sm font-medium outline-none focus:border-foreground"><option value={2}>2 alternatives</option><option value={1}>1 alternative</option></select></label><label className="block"><span className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Generation mode</span><select value={generationMode} onChange={(event) => void onSaveShotForId(shot.id, { generation_mode: event.target.value as "image_to_video" | "first_last_frame" | "extend", extend_source_video_asset_id: event.target.value === "extend" ? (shot.extend_source_video_asset_id ?? shot.selected_video_asset_id ?? shot.video_asset_ids[0] ?? null) : null })} disabled={saving || shotBusy || shot.status === "generating"} className="mt-1 block rounded-lg border bg-background px-2.5 py-1.5 text-sm font-medium outline-none focus:border-foreground"><option value="image_to_video">Start image</option><option value="first_last_frame" disabled={!shot.end_keyframe_asset_id}>First + last image</option><option value="extend" disabled={!shot.video_asset_ids.length}>Extend a Take</option></select></label><div className="pb-0.5"><span className="block text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">End Scene</span><Button className="mt-1" size="sm" variant="secondary" onClick={() => onEditEndScene(shot.id)} disabled={saving || shotBusy}>{shot.end_keyframe_asset_id ? "Change end Scene" : "Add end Scene"}</Button></div>{shot.estimated_audio_seconds ? <div className="pb-0.5"><span className="block text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Audio timing</span><p className="mt-1 text-xs text-muted-foreground">~{shot.estimated_audio_seconds}s dialogue / sound</p></div> : null}</div>{generationMode === "extend" ? <label className="mt-3 block"><span className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Take to extend</span><select value={shot.extend_source_video_asset_id ?? shot.selected_video_asset_id ?? ""} onChange={(event) => void onSaveShotForId(shot.id, { extend_source_video_asset_id: event.target.value || null })} className="mt-1 block max-w-md rounded-lg border bg-background px-2.5 py-1.5 text-xs outline-none focus:border-foreground">{shot.video_asset_ids.map((takeId, index) => <option key={takeId} value={takeId}>Take {index + 1}{takeId === shot.selected_video_asset_id ? " · selected" : ""}</option>)}</select></label> : null}<label className="mt-4 block"><span className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Director Veo Prompt</span><textarea value={prompt} onChange={(event) => setPromptDrafts((current) => ({ ...current, [shot.id]: event.target.value }))} rows={8} disabled={saving || shotBusy || shot.status === "generating"} className="mt-2 w-full resize-none rounded-lg border bg-background px-3 py-2 text-xs leading-5 outline-none transition focus:border-foreground focus:ring-1 focus:ring-foreground/20 disabled:opacity-60" /></label><p className="mt-2 text-[11px] leading-5 text-muted-foreground">This is the saved Director Prompt, not a copy of the Working Script. Changes are saved when you generate or regenerate.</p>{video && nextShot ? <details className="mt-3 rounded-lg border bg-amber-50/60 p-3"><summary className="cursor-pointer text-xs font-medium text-amber-900">Use a good frame from this Take to bridge into S{String(nextShot.order).padStart(2, "0")}</summary><p className="mt-1 text-[11px] leading-4 text-amber-800">Choose the last clean frame before motion decay. It becomes the next shot’s Start Scene; existing takes are preserved and marked outdated.</p><div className="mt-2 flex flex-wrap items-end gap-2"><label><span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-900">Timestamp</span><input type="number" min={0} max={Math.max(0, veoDuration - 0.01)} step={0.1} value={bridgeTimestamp} onChange={(event) => setBridgeTimestampDrafts((current) => ({ ...current, [shot.id]: Number(event.target.value) }))} className="mt-1 block w-24 rounded-md border bg-background px-2 py-1 text-xs" /></label><Button size="sm" variant="secondary" onClick={() => void onExtractBridgeFrame(shot, bridgeTimestamp, nextShot.id)} disabled={saving || shotBusy}>Extract bridge frame</Button></div></details> : null}</div>
                    <div className="flex flex-row flex-wrap gap-2 lg:w-32 lg:flex-col"><Button size="sm" onClick={() => void onGenerateShot(shot, prompt, shot.generation_variants ?? 2)} disabled={saving || shotBusy || (requiresFirstLastReview && (needsIntermediate || needsDirectorReview)) || shot.status === "generating" || (generationMode !== "extend" && !shot.keyframe_asset_id)}>{shotBusy || shot.status === "generating" ? <Loader2 className="animate-spin" /> : <Sparkles />}{requiresFirstLastReview && needsIntermediate ? "Add bridge frame" : requiresFirstLastReview && needsDirectorReview ? "Refresh Director" : video ? "Save & regenerate" : "Save & generate"}</Button>{requiresFirstLastReview && needsDirectorReview ? <p className="text-[10px] leading-4 text-muted-foreground">Refresh Director Prompts to check this first/last pair.</p> : <p className="text-[10px] leading-4 text-muted-foreground">Two alternatives are recommended for any difficult shot. Changing a Scene preserves the old Take for comparison.</p>}</div>
                  </div>
                );
              }) : <div className="px-5 py-8 text-sm text-muted-foreground">No shot cards yet. Create the storyboard before production.</div>}
            </div>
          </Card>
        </div>
      </ProductionConversationMessages>
      <AssetPreviewLightbox asset={endScenePreviewAsset} label="End Scene preview" onClose={() => setEndScenePreviewAsset(null)} />
      <ProductionActionBar><Button variant="secondary" onClick={() => onStageChange("storyboard")}>Back to storyboard</Button><Button onClick={() => onStageChange("edit")} disabled={readyCount === 0}>Choose takes & edit <ArrowRight /></Button></ProductionActionBar>
    </div>
  );
}

function AssetPreviewLightbox({ asset, label, onClose }: { asset: AssetSummary | null; label: string; onClose: () => void }) {
  if (!asset) return null;
  return <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/85 p-5 sm:p-8" role="dialog" aria-modal="true" aria-label={label} onMouseDown={onClose}>
    <div className="relative flex max-h-full max-w-full flex-col" onMouseDown={(event) => event.stopPropagation()}>
      <div className="mb-3 flex items-center justify-between gap-4 text-sm font-medium text-white"><span className="truncate">{asset.title}</span><Button type="button" size="icon" variant="secondary" className="shrink-0 rounded-full" onClick={onClose} aria-label="Close preview"><X className="size-4" /></Button></div>
      <img src={asset.url} alt={asset.title} className="max-h-[82vh] max-w-[92vw] rounded-md object-contain" />
    </div>
  </div>;
}

function VideoPreviewLightbox({ asset, onClose }: { asset: AssetSummary | null; onClose: () => void }) {
  if (!asset) return null;
  return <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/85 p-5 sm:p-8" role="dialog" aria-modal="true" aria-label="Video take preview" onMouseDown={onClose}>
    <div className="relative flex max-h-full max-w-full flex-col" onMouseDown={(event) => event.stopPropagation()}>
      <div className="mb-3 flex items-center justify-between gap-4 text-sm font-medium text-white"><span className="truncate">{asset.title}</span><Button type="button" size="icon" variant="secondary" className="shrink-0 rounded-full" onClick={onClose} aria-label="Close video preview"><X className="size-4" /></Button></div>
      <video src={asset.url} controls autoPlay className="max-h-[82vh] max-w-[92vw] rounded-md bg-black object-contain" />
    </div>
  </div>;
}

function EditStage({ production, assets, saving, busyShotIds, onRender, onSaveShotForId, onReview, onSaveEditPlan, onStageChange }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; busyShotIds: string[]; onRender: (includeAudio?: boolean) => void; onSaveShotForId: (shotId: string, payload: Partial<VideoProductionShot>) => Promise<void>; onReview: () => void; onSaveEditPlan: (editPlan: VideoProduction["edit_plan"]) => void; onStageChange: (stage: VideoProductionStage) => void }) {
  const includedShots = production.shots.filter((shot) => shot.include_in_edit !== false);
  const skippedCount = production.shots.length - includedShots.length;
  const ready = includedShots.filter((shot) => shot.status === "ready" && (shot.selected_video_asset_id || shot.video_asset_ids.length)).length;
  const allIncludedFramesReady = includedShots.length > 0 && ready === includedShots.length;
  const [previewTake, setPreviewTake] = useState<AssetSummary | null>(null);
  const timelineSnapshot = {
    version: 1,
    apply_to_render: false,
    clips: production.shots.map((shot) => ({
      shot_id: shot.id,
      frame_order: shot.order,
      take_id: shot.selected_video_asset_id ?? shot.video_asset_ids[0] ?? null,
      include: shot.include_in_edit !== false,
      trim_in_seconds: shot.trim_in_seconds ?? 0,
      trim_out_seconds: shot.trim_out_seconds ?? null,
      transition: shot.transition ?? "cut",
    })),
    overlays: production.edit_plan.overlays,
  };
  const [timelineJsonDraft, setTimelineJsonDraft] = useState("");
  const [timelineJsonError, setTimelineJsonError] = useState<string | null>(null);
  useEffect(() => {
    const value = production.edit_plan.timeline_json && Object.keys(production.edit_plan.timeline_json).length
      ? production.edit_plan.timeline_json
      : timelineSnapshot;
    setTimelineJsonDraft(JSON.stringify(value, null, 2));
  }, [production.production_id, production.edit_plan.timeline_json, production.shots]);
  const reviewByTake = new Map(production.edit_plan.take_reviews.map((review) => [review.take_id, review]));
  const imageAssets = assets.filter((asset) => asset.type === "image" || asset.type === "gif");
  const addOverlay = (kind: VideoProduction["edit_plan"]["overlays"][number]["kind"]) => {
    const overlay = { id: `overlay_${crypto.randomUUID().slice(0, 10)}`, kind, asset_id: null, text: kind === "subtitle" ? "" : "", start_seconds: 0, end_seconds: null, position: kind === "logo" ? "top_right" as const : "bottom_center" as const };
    onSaveEditPlan({ ...production.edit_plan, overlays: [...production.edit_plan.overlays, overlay] });
  };
  const updateOverlay = (id: string, patch: Partial<VideoProduction["edit_plan"]["overlays"][number]>) => onSaveEditPlan({ ...production.edit_plan, overlays: production.edit_plan.overlays.map((overlay) => overlay.id === id ? { ...overlay, ...patch } : overlay) });
  const deleteOverlay = (id: string) => onSaveEditPlan({ ...production.edit_plan, overlays: production.edit_plan.overlays.filter((overlay) => overlay.id !== id) });
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} thinkingLabel="Editor is assembling the selected takes…" emptyIcon={Film} emptyTitle="Build the video timeline" emptyDescription="Choose one generated take for each storyboard Frame, then join them in storyboard order.">
        <div className="border-t pt-5">
          <Card className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
              <div><p className="text-sm font-semibold">Selected-take timeline</p><p className="mt-1 text-xs text-muted-foreground">Preview each Take, select the strongest one, trim it, or skip any Frame that should not appear in this edit. The final cut keeps storyboard order.</p></div>
              <div className="flex flex-wrap gap-2"><Badge variant="outline">{ready} / {includedShots.length} included ready</Badge>{skippedCount ? <Badge variant="secondary">{skippedCount} skipped</Badge> : null}<Button size="sm" variant="secondary" onClick={onReview} disabled={saving || !production.shots.some((shot) => shot.video_asset_ids.length)}>{saving || production.edit_plan.review_status === "reviewing" ? <Loader2 className="animate-spin" /> : <Sparkles />}Review takes with Gemini</Button></div>
            </div>
            <div className="p-5">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {production.shots.map((shot) => {
                  const takes = shot.video_asset_ids.map((id) => assets.find((asset) => asset.id === id)).filter((asset): asset is AssetSummary => Boolean(asset));
                  const selectedId = shot.selected_video_asset_id ?? takes[0]?.id ?? null;
                  const shotBusy = busyShotIds.includes(shot.id);
                  const included = shot.include_in_edit !== false;
                  return <div key={shot.id} className={cn("rounded-xl border p-3 transition", included ? shot.status === "ready" ? "bg-card" : "bg-muted/30" : "bg-muted/20 opacity-65")}><div className="flex items-start justify-between gap-2"><div><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Frame {shot.order}</p><p className="mt-1 text-sm font-semibold">{shot.title}</p></div><div className="flex items-center gap-1.5"><Badge variant="outline" className="text-[10px]">{included ? shotBusy ? "Saving…" : `${takes.length} take${takes.length === 1 ? "" : "s"}` : "Skipped"}</Badge><Button type="button" size="sm" variant={included ? "ghost" : "secondary"} className="h-7 px-2 text-[10px]" onClick={() => void onSaveShotForId(shot.id, { include_in_edit: !included })} disabled={saving || shotBusy}>{included ? "Skip" : "Include"}</Button></div></div>{takes.length ? <div className="mt-3 grid grid-cols-2 gap-2">{takes.map((take, index) => { const review = reviewByTake.get(take.id); return <div key={take.id} className={cn("overflow-hidden rounded-lg border text-left transition", selectedId === take.id ? "border-foreground ring-1 ring-foreground/25" : "hover:border-foreground/50")}><button type="button" onClick={() => setPreviewTake(take)} className="group/take relative block w-full focus:outline-none focus:ring-2 focus:ring-foreground/30" aria-label={`Preview take ${index + 1} for ${shot.title}`}><video src={take.url} muted preload="metadata" className="aspect-[9/16] w-full bg-black object-cover" /><span className="absolute inset-0 flex items-center justify-center bg-black/45 text-white opacity-0 transition group-hover/take:opacity-100 group-focus-visible/take:opacity-100"><Maximize2 className="size-5" /></span></button>{review ? <div className="border-t bg-muted/20 px-2 py-1.5"><p className="text-[10px] font-semibold">Gemini: {review.score}/100 · {review.verdict}</p>{review.flags.length ? <p className="mt-0.5 line-clamp-2 text-[9px] text-muted-foreground">{review.flags.join(", ")}</p> : null}{review.verdict === "trim" ? <button type="button" className="mt-1 text-[9px] font-semibold underline" onClick={() => void onSaveShotForId(shot.id, { selected_video_asset_id: take.id, trim_in_seconds: review.suggested_trim_in_seconds, trim_out_seconds: review.suggested_trim_out_seconds ?? null })} disabled={saving || shotBusy || !included}>Apply suggested trim</button> : null}</div> : null}<Button type="button" size="sm" variant={selectedId === take.id ? "default" : "ghost"} onClick={() => void onSaveShotForId(shot.id, { selected_video_asset_id: take.id })} disabled={saving || shotBusy || !included} className="m-1.5 h-7 w-[calc(100%-0.75rem)] px-2 text-[10px]">{selectedId === take.id ? <><Check />Selected</> : "Select take"}</Button></div>; })}</div> : <p className="mt-3 text-xs text-muted-foreground">{included ? "Generate a video take first." : "This Frame is excluded from the current edit."}</p>}{included ? <div className="mt-3 grid grid-cols-3 gap-2 border-t pt-3"><label className="text-[10px] font-medium text-muted-foreground">Trim in<input type="number" min="0" step="0.1" value={shot.trim_in_seconds ?? 0} onChange={(event) => void onSaveShotForId(shot.id, { trim_in_seconds: Number(event.target.value) || 0 })} disabled={saving || shotBusy} className="mt-1 h-8 w-full rounded border bg-background px-2 text-xs text-foreground" /></label><label className="text-[10px] font-medium text-muted-foreground">Trim out<input type="number" min="0" step="0.1" placeholder="End" value={shot.trim_out_seconds ?? ""} onChange={(event) => void onSaveShotForId(shot.id, { trim_out_seconds: event.target.value ? Number(event.target.value) : null })} disabled={saving || shotBusy} className="mt-1 h-8 w-full rounded border bg-background px-2 text-xs text-foreground" /></label><label className="text-[10px] font-medium text-muted-foreground">Transition<select value={shot.transition || "cut"} onChange={(event) => void onSaveShotForId(shot.id, { transition: event.target.value })} disabled={saving || shotBusy} className="mt-1 h-8 w-full rounded border bg-background px-2 text-xs text-foreground"><option value="cut">Cut</option><option value="fade">Fade</option><option value="match_cut">Match cut</option></select></label></div> : null}</div>;
                })}
              </div>
            </div>
          </Card>
          <Card className="mt-5 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-semibold">Brand-safe overlays</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Add real logos, store badges, and subtitles here instead of asking Veo to draw exact text or brand marks.</p></div><div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={() => addOverlay("subtitle")}><Plus />Subtitle</Button><Button size="sm" variant="secondary" onClick={() => addOverlay("logo")}><Plus />Logo</Button><Button size="sm" variant="secondary" onClick={() => addOverlay("store_badges")}><Plus />Store badges</Button></div></div>{production.edit_plan.overlays.length ? <div className="mt-4 space-y-3">{production.edit_plan.overlays.map((overlay) => <div key={overlay.id} className="grid gap-3 rounded-lg border bg-muted/10 p-3 md:grid-cols-[120px_minmax(0,1fr)_110px_110px_auto]"><select value={overlay.kind} onChange={(event) => updateOverlay(overlay.id, { kind: event.target.value as typeof overlay.kind })} className="h-9 rounded border bg-background px-2 text-xs"><option value="subtitle">Subtitle</option><option value="logo">Logo</option><option value="store_badges">Store badges</option><option value="image">Image</option></select>{overlay.kind === "subtitle" ? <input value={overlay.text} onChange={(event) => updateOverlay(overlay.id, { text: event.target.value })} placeholder="Exact approved subtitle" className="h-9 rounded border bg-background px-2 text-xs" /> : <select value={overlay.asset_id ?? ""} onChange={(event) => updateOverlay(overlay.id, { asset_id: event.target.value || null })} className="h-9 rounded border bg-background px-2 text-xs"><option value="">Choose Library asset</option>{imageAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.title}</option>)}</select>}<input type="number" min="0" step="0.1" value={overlay.start_seconds} onChange={(event) => updateOverlay(overlay.id, { start_seconds: Number(event.target.value) || 0 })} className="h-9 rounded border bg-background px-2 text-xs" aria-label="Overlay start seconds" /><select value={overlay.position} onChange={(event) => updateOverlay(overlay.id, { position: event.target.value as typeof overlay.position })} className="h-9 rounded border bg-background px-2 text-xs"><option value="top_left">Top left</option><option value="top_right">Top right</option><option value="bottom_center">Bottom center</option><option value="center">Center</option></select><Button size="icon" variant="ghost" className="h-9 w-9 text-destructive" onClick={() => deleteOverlay(overlay.id)} aria-label="Delete overlay"><Trash2 className="size-4" /></Button></div>)}</div> : <p className="mt-4 text-xs text-muted-foreground">No deterministic overlays yet.</p>}</Card>
          <details className="mt-5 rounded-xl border bg-muted/5 p-4"><summary className="cursor-pointer text-sm font-semibold">Editable Timeline JSON</summary><p className="mt-2 text-xs leading-5 text-muted-foreground">Gemini creates a reviewable draft here. Keep <code>apply_to_render</code> false to use the visual controls above; set it to true to render this explicit JSON timeline instead.</p><textarea value={timelineJsonDraft} onChange={(event) => { setTimelineJsonDraft(event.target.value); setTimelineJsonError(null); }} rows={14} spellCheck={false} className="mt-3 w-full resize-none rounded-lg border bg-background p-3 font-mono text-[11px] leading-5 outline-none focus:border-foreground focus:ring-1 focus:ring-foreground/20" />{timelineJsonError ? <p className="mt-2 text-xs text-destructive">{timelineJsonError}</p> : null}<div className="mt-3 flex justify-end"><Button size="sm" variant="secondary" onClick={() => { try { const parsed = JSON.parse(timelineJsonDraft); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Timeline must be one JSON object."); setTimelineJsonError(null); onSaveEditPlan({ ...production.edit_plan, timeline_json: parsed as Record<string, unknown> }); } catch (error) { setTimelineJsonError(error instanceof Error ? error.message : "Timeline JSON was not saved."); } }} disabled={saving}>Save Timeline JSON</Button></div></details>
          <Card className={cn("mt-5 border-l-4 p-4", production.edit_plan.qc_status === "pass" ? "border-l-emerald-500" : production.edit_plan.qc_status === "warning" ? "border-l-amber-500" : "border-l-muted-foreground/30")}><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-semibold">Export QC</p><p className="mt-1 text-xs text-muted-foreground">Checks selected takes, missing Frames, generated-text risks, overlay references, and final duration during assembly.</p></div><Badge variant="outline">{production.edit_plan.qc_status === "not_run" ? "Runs on assemble" : production.edit_plan.qc_status}</Badge></div>{production.edit_plan.final_duration_seconds !== null ? <p className="mt-3 text-sm">Final timeline: <span className="font-semibold">{production.edit_plan.final_duration_seconds}s</span> · Project target: {production.target_seconds}s</p> : null}{production.edit_plan.qc_issues.length ? <ul className="mt-3 space-y-1 text-xs leading-5 text-amber-800 dark:text-amber-300">{production.edit_plan.qc_issues.map((issue, index) => <li key={`${issue}-${index}`}>• {issue}</li>)}</ul> : production.edit_plan.qc_status === "pass" ? <p className="mt-3 text-xs text-emerald-700 dark:text-emerald-300">No missing included Frame, selected-take warning, or overlay reference issue was found.</p> : null}</Card>
        </div>
      </ProductionConversationMessages>
      <VideoPreviewLightbox asset={previewTake} onClose={() => setPreviewTake(null)} />
      <ProductionActionBar><Button variant="secondary" onClick={() => onStageChange("generate")}>Back to video generate</Button><Button onClick={() => onRender(false)} disabled={saving || !allIncludedFramesReady}>{saving ? <Loader2 className="animate-spin" /> : <Film />}Assemble {includedShots.length} selected Frame{includedShots.length === 1 ? "" : "s"}</Button></ProductionActionBar>
    </div>
  );
}

function DeliverStage({ production, assets, saving, onRender }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; onRender: (includeAudio?: boolean) => void }) {
  const final = assets.find((asset) => asset.id === production.final_asset_id);
  const checks = ["Duration, aspect ratio, resolution, and first-cut continuity", "Brand logo, product, CTA, and disclaimer placement", "No black frames, duplicated shots, or continuity break", "Caption, transition, and rights review", "MP4 master and editable shot assets"];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} thinkingLabel="Delivery QA is updating…" emptyIcon={Check} emptyTitle="Review delivery package" emptyDescription="Render a first cut, inspect QA checks, then export the commercial package.">
        <div className="grid gap-5 border-t pt-5 lg:grid-cols-[minmax(0,1fr)_330px]">
          <Card className="overflow-hidden p-0">
            {final ? <video src={final.url} controls className="aspect-video w-full bg-black" /> : <div className="flex aspect-video w-full flex-col items-center justify-center bg-muted text-center"><Film className="size-8 text-muted-foreground" /><p className="mt-3 text-sm font-semibold">No first cut has been rendered yet.</p><p className="mt-1 text-xs text-muted-foreground">Render from Edit to start delivery review.</p></div>}
            <div className="p-4"><p className="text-sm font-semibold">{final ? "First cut ready" : "Delivery preview"}</p><p className="mt-1 text-xs text-muted-foreground">{final?.title ?? `${production.target_seconds}s · ${production.aspect_ratio} · ${production.resolution}`}</p></div>
          </Card>
          <Card className="divide-y p-0">
            {checks.map((check) => <div key={check} className="flex items-center gap-3 px-4 py-3 text-sm"><span className="flex size-5 shrink-0 items-center justify-center rounded-full border"><Check className="size-3" /></span>{check}</div>)}
          </Card>
        </div>
      </ProductionConversationMessages>
      <ProductionActionBar>{!final ? <Button onClick={() => onRender(false)} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Film />}Assemble selected takes</Button> : <Button variant="secondary" disabled>Delivery package ready</Button>}</ProductionActionBar>
    </div>
  );
}

function EmptyStage({ title, description }: { title: string; description: string }) { return <div className="mx-auto flex max-w-xl flex-col items-center py-20 text-center"><Layers3 className="size-9 text-muted-foreground" /><h2 className="mt-4 text-xl font-semibold">{title}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p></div>; }
function AgentThinking({ label }: { label: string }) { return <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /><span>{label}</span><span className="tracking-[0.22em]">...</span></div>; }

function displayReportItems(items: string[]): string[] {
  return items.flatMap((item) => {
    const candidate = item.trim();
    if (!(candidate.startsWith("[") && candidate.endsWith("]"))) return [item];

    const values = Array.from(candidate.matchAll(/(?:'([^']*)'|"([^"]*)")/g))
      .map((match) => (match[1] ?? match[2] ?? "").trim())
      .filter(Boolean);
    return values.length ? values : [item];
  });
}

function displayReportText(value: string, separator = " "): string {
  return displayReportItems([value]).join(separator);
}

function formatReferenceTimecode(value: number): string {
  const totalSeconds = Math.max(0, Math.round(Number(value) || 0));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function ScriptList({ index, title, items }: { index?: string; title: string; items: string[] }) {
  const displayItems = displayReportItems(items);
  return (
    <section className="rounded-xl border bg-card/70 p-4">
      <div className="flex items-center gap-2">
        {index ? <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold text-muted-foreground">{index}</span> : null}
        <p className="text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">{title}</p>
      </div>
      <ul className="mt-3 space-y-2">
        {displayItems.length ? displayItems.map((item, itemIndex) => <li key={`${item}-${itemIndex}`} className="grid grid-cols-[18px_1fr] gap-2 text-sm leading-5"><span className="pt-0.5 text-[10px] font-bold tabular-nums text-muted-foreground">{String(itemIndex + 1).padStart(2, "0")}</span><span>{item}</span></li>) : <li className="text-sm text-muted-foreground">Not defined yet.</li>}
      </ul>
    </section>
  );
}
function AssetStateSelect({ label, value, options, onChange }: { label: string; value: string | null; options: Array<{ id: string; label: string }>; onChange: (value: string | null) => void }) {
  return <label className="text-xs font-medium text-muted-foreground">{label}<select value={value ?? ""} onChange={(event) => onChange(event.target.value || null)} className="mt-2 h-10 w-full rounded-lg border bg-background px-2 text-sm text-foreground"><option value="">No state bound</option>{options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>;
}
function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) { return <label className="text-xs font-medium text-muted-foreground">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-2 h-10 w-full rounded-lg border bg-background px-2 text-sm text-foreground">{options.map((option) => <option key={option}>{option}</option>)}</select></label>; }
function Field({ label, value, multiline = false, onChange }: { label: string; value: string; multiline?: boolean; onChange: (value: string) => void }) { return <label className={cn("block text-xs font-semibold uppercase tracking-[0.11em] text-muted-foreground", multiline && "sm:col-span-2")}>{label}{multiline ? <textarea value={value} onChange={(event) => onChange(event.target.value)} className="mt-2 min-h-24 w-full resize-y rounded-lg border bg-background p-3 text-sm font-normal normal-case tracking-normal text-foreground outline-none focus:ring-2 focus:ring-ring" /> : <input value={value} onChange={(event) => onChange(event.target.value)} className="mt-2 h-10 w-full rounded-lg border bg-background px-3 text-sm font-normal normal-case tracking-normal text-foreground outline-none focus:ring-2 focus:ring-ring" />}</label>; }
