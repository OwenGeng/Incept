"use client";

import { useEffect, useMemo, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  Clapperboard,
  Film,
  ImagePlus,
  Layers3,
  Loader2,
  MessageSquareText,
  Music2,
  Maximize2,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Send,
  Sparkles,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import type { AssetSummary, InceptUser } from "@incept/shared";
import { AppHeader } from "@/components/ui/app-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  createVideoProduction,
  generateVideoProductionSoundtrack,
  generateVideoProductionDesignSheet,
  generateVideoProductionKeyframe,
  generateVideoProductionShot,
  getJob,
  listAssets,
  listVideoProductions,
  lockVideoProductionScript,
  reorderVideoProductionShots,
  renderVideoProductionFirstCut,
  runVideoProductionCreativeDirector,
  runVideoProductionAudioProducer,
  runVideoProductionDesigner,
  runVideoProductionDirector,
  runVideoProductionScriptAgent,
  selectVideoProductionDesignSheetPanel,
  updateVideoProduction,
  updateVideoProductionShot,
  uploadAsset,
  type ContentScope,
  type VideoProduction,
  type VideoProductionDesignSheet,
  type VideoProductionShot,
  type VideoProductionStage,
} from "@/lib/incept-api";

const STAGES: Array<{ id: VideoProductionStage; label: string; icon: typeof MessageSquareText }> = [
  { id: "direction", label: "Direction", icon: MessageSquareText },
  { id: "script", label: "Script", icon: Wand2 },
  { id: "design", label: "Design", icon: ImagePlus },
  { id: "storyboard", label: "Storyboard", icon: Layers3 },
  { id: "generate", label: "Generate", icon: Sparkles },
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
}: VideoProductionViewProps) {
  const [productions, setProductions] = useState<VideoProduction[]>([]);
  const [activeProductionId, setActiveProductionId] = useState<string | null>(null);
  const [viewedStage, setViewedStage] = useState<VideoProductionStage>("direction");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [batchGenerating, setBatchGenerating] = useState(false);
  const [agentDraft, setAgentDraft] = useState("");
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [productionMenuOpen, setProductionMenuOpen] = useState(false);
  const [assetsDrawerOpen, setAssetsDrawerOpen] = useState(false);
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
    const items = await listVideoProductions(activeWorkspaceId);
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
    listVideoProductions(activeWorkspaceId)
      .then((items) => {
        if (!active) return;
        setProductions(items);
        setActiveProductionId((current) => current ?? items[0]?.production_id ?? null);
        setViewedStage(items[0]?.stage ?? "direction");
      })
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Could not load productions."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [activeWorkspaceId]);

  const createProduction = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await createVideoProduction({ workspace_id: activeWorkspaceId, title: "Untitled commercial", target_seconds: 30 });
      replaceProduction(created);
      setViewedStage("direction");
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
      replaceProduction(await updateVideoProduction(activeProduction.production_id, payload));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the production.");
    } finally {
      setSaving(false);
    }
  };

  const askProductionRole = async (stage = viewedStage) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const roleRunner = stage === "direction"
        ? runVideoProductionCreativeDirector
        : stage === "design"
          ? runVideoProductionDesigner
          : stage === "storyboard"
            ? runVideoProductionDirector
            : runVideoProductionScriptAgent;
      const next = await roleRunner(activeProduction.production_id, agentDraft);
      replaceProduction(next);
      setAgentDraft("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Production agent could not finish this pass.");
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

  const approveDirectionAndDraftScript = async () => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const approved = await updateVideoProduction(activeProduction.production_id, {
        stage: "script",
        creative_direction: { ...activeProduction.creative_direction, status: "approved" },
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
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await updateVideoProductionShot(activeProduction.production_id, selectedShot.id, payload));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save this shot.");
    } finally {
      setSaving(false);
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

  const generateDesignSheet = async (sheet: VideoProductionDesignSheet) => {
    if (!activeProduction) return;
    if (sheet.asset_pack_type === "prop" && !(sheet.asset_ids?.length)) {
      setError("This Prop Pack needs an approved product image. Add the hero product in Brand Assets, then regenerate the Design Bible.");
      return;
    }
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

  const generateMissingDesignSheets = async (sheets: VideoProductionDesignSheet[]) => {
    if (!activeProduction) return;
    const missingSheets = sheets.filter((sheet) => !(sheet.asset_pack_type === "prop" && !(sheet.asset_ids?.length))
      && !sheet.grid_asset_id
      && !(sheet.panel_asset_ids?.length)
      && !(sheet.approved_asset_ids?.length)
      && !sheet.selected_asset_id
      && sheet.status !== "generating");
    if (!missingSheets.length) return;

    setSaving(true);
    setBatchGenerating(true);
    setError(null);
    try {
      const jobs = await Promise.all(missingSheets.map((sheet) => generateVideoProductionDesignSheet(activeProduction.production_id, sheet.id)));
      await refreshProduction(activeProduction.production_id);
      jobs.forEach((job) => {
        if (job.jobId) watchProductionJob(activeProduction.production_id, job.jobId);
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start asset pack generation.");
    } finally {
      setBatchGenerating(false);
      setSaving(false);
    }
  };

  const selectDesignCandidate = async (sheet: VideoProductionDesignSheet, panel: number) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await selectVideoProductionDesignSheetPanel(activeProduction.production_id, sheet.id, panel));
      setLiveAssets(await listAssets(activeWorkspaceId, contentScope));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not select this design candidate.");
    } finally {
      setSaving(false);
    }
  };

  const generateShot = async (shot: VideoProductionShot) => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const job = await generateVideoProductionShot(activeProduction.production_id, shot.id);
      await refreshProduction(activeProduction.production_id);
      if (!job.jobId) throw new Error("Video generation did not return a job ID.");
      watchProductionJob(activeProduction.production_id, job.jobId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start Veo generation.");
    } finally {
      setSaving(false);
    }
  };

  const buildAudioPlan = async () => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      replaceProduction(await runVideoProductionAudioProducer(activeProduction.production_id, "Build the soundtrack plan from the approved script and current storyboard."));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not build the soundtrack plan.");
    } finally {
      setSaving(false);
    }
  };

  const generateSoundtrack = async () => {
    if (!activeProduction) return;
    setSaving(true);
    setError(null);
    try {
      const job = await generateVideoProductionSoundtrack(activeProduction.production_id);
      await refreshProduction(activeProduction.production_id);
      if (!job.jobId) throw new Error("Soundtrack generation did not return a job ID.");
      watchProductionJob(activeProduction.production_id, job.jobId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start soundtrack generation.");
    } finally {
      setSaving(false);
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
      }
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

  if (loading) {
    return <div className="flex flex-1 items-center justify-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>;
  }

  if (!activeProduction) {
    return (
      <main className="flex h-screen min-h-0 flex-1 flex-col overflow-hidden bg-background">
        <AppHeader title="Video Production" subtitle="Independent production workspace" docsHref="/docs/incept-video-production-workspace" onMobileMenuOpen={onMobileMenuOpen} />
        <div className="flex flex-1 items-center justify-center p-8">
          <Card className="w-full max-w-xl border-dashed p-10 text-center shadow-none">
            <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-muted"><Clapperboard className="size-7" /></div>
            <h2 className="mt-5 text-xl font-semibold">Start a video production</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">Build a commercial through a locked script, editable shot cards, approved keyframes, production, edit, and delivery.</p>
            <Button className="mt-6" onClick={createProduction} disabled={saving}><Plus /> New production</Button>
          </Card>
        </div>
      </main>
    );
  }

  const currentStageIndex = stageIndex(activeProduction.stage);
  const canLockScript = Boolean(activeProduction.script.raw_script || activeProduction.script.beats.length);
  const availableStageIndex = Math.max(
    currentStageIndex,
    canLockScript ? stageIndex("script") : stageIndex("direction"),
    activeProduction.design_bible.status !== "draft" ? stageIndex("design") : stageIndex("direction"),
    activeProduction.shots.length ? stageIndex("storyboard") : stageIndex("direction"),
  );
  return (
    <main className="flex h-screen min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <AppHeader
        title="Video Production"
        subtitle="Plan, direct, produce, and deliver commercial video"
        docsHref="/docs/incept-video-production-workspace"
        onMobileMenuOpen={onMobileMenuOpen}
        trailingActions={(
          <Button
            size="sm"
            onClick={() => setAssetsDrawerOpen((open) => !open)}
              variant={assetsDrawerOpen ? "default" : "outline"}
              className={cn(
                "hidden min-[1161px]:inline-flex",
                assetsDrawerOpen && "bg-foreground text-background hover:bg-foreground/90 hover:text-background",
              )}
          >
            {assetsDrawerOpen ? <PanelRightClose /> : <PanelRightOpen />} Assets
          </Button>
        )}
      />

      <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-background px-6 py-3 max-[900px]:px-4">
        <div className="relative min-w-0">
          <button type="button" onClick={() => setProductionMenuOpen((value) => !value)} className="flex max-w-[300px] items-center gap-2 rounded-xl border bg-card px-3.5 py-2 text-sm font-semibold hover:bg-muted">
            <Clapperboard className="size-4 text-muted-foreground" />
            <span className="truncate">{activeProduction.title}</span><ChevronDown className="size-4 text-muted-foreground" />
          </button>
          {productionMenuOpen ? (
            <div className="absolute left-0 top-[calc(100%+6px)] z-30 w-80 rounded-xl border bg-card p-1.5 shadow-xl">
              {productions.map((production) => <button key={production.production_id} type="button" onClick={() => { setActiveProductionId(production.production_id); setViewedStage(production.stage); setProductionMenuOpen(false); }} className={cn("block w-full rounded-lg px-3 py-2 text-left text-sm", production.production_id === activeProduction.production_id ? "bg-muted font-semibold" : "hover:bg-muted")}><span className="block truncate">{production.title}</span><span className="mt-0.5 block text-xs text-muted-foreground">{stageLabel(production.stage)} · {production.target_seconds}s</span></button>)}
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="hidden sm:inline-flex">{activeProduction.target_seconds}s · {activeProduction.aspect_ratio} · {activeProduction.resolution}</Badge>
          <Button size="sm" onClick={createProduction} disabled={saving}><Plus /> New production</Button>
        </div>
      </div>

      <nav className="flex shrink-0 items-center gap-0 overflow-x-auto border-b bg-background px-6 max-[900px]:px-4">
        {STAGES.map((item, index) => {
          const Icon = item.icon;
          const isCurrent = viewedStage === item.id;
          const enabled = index <= availableStageIndex;
          return <button key={item.id} type="button" disabled={!enabled} onClick={() => setViewedStage(item.id)} className={cn("relative flex shrink-0 items-center gap-2 px-4 py-3.5 text-sm font-medium transition", isCurrent ? "text-foreground" : "text-muted-foreground hover:text-foreground", !enabled && "cursor-not-allowed opacity-35")}>{saving && item.id === "script" && activeProduction.stage === "script" ? <Loader2 className="size-4 animate-spin" /> : <Icon className="size-4" />}{item.label}{isCurrent ? <span className="absolute inset-x-4 bottom-0 h-0.5 bg-foreground" /> : null}</button>;
        })}
      </nav>

      {error ? <div className="shrink-0 border-b border-destructive/20 bg-destructive/5 px-6 py-2 text-sm text-destructive">{error}</div> : null}

      <div className="flex min-h-0 flex-1 overflow-hidden max-[900px]:block max-[900px]:overflow-auto">
        <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {viewedStage === "direction" && <DirectionWorkspace production={activeProduction} saving={saving} agentDraft={agentDraft} onAgentDraftChange={setAgentDraft} onSend={() => void askProductionRole("direction")} onSave={applyUpdate} onApprove={() => void approveDirectionAndDraftScript()} />}
          {viewedStage === "script" && <ScriptWorkspace production={activeProduction} saving={saving} canLock={canLockScript} agentDraft={agentDraft} onAgentDraftChange={setAgentDraft} onSend={() => void askProductionRole("script")} onSave={applyUpdate} onLock={() => void lockScript()} />}
          {viewedStage === "design" && <DesignStage production={activeProduction} assets={liveAssets} saving={saving} batchGenerating={batchGenerating} agentDraft={agentDraft} onAgentDraftChange={setAgentDraft} onSend={() => void askProductionRole("design")} onSave={applyUpdate} onGenerateSheet={generateDesignSheet} onGenerateMissingSheets={generateMissingDesignSheets} onSelectCandidate={selectDesignCandidate} onApproveAndDirect={approveDesignAndCreateStoryboard} />}
          {viewedStage === "storyboard" && <StoryboardStage production={activeProduction} assets={liveAssets} selectedShot={selectedShot} saving={saving} agentDraft={agentDraft} onAgentDraftChange={setAgentDraft} onSend={() => void askProductionRole("storyboard")} onSave={applyUpdate} onSelectShot={setSelectedShotId} onSaveShot={saveShot} onMoveShot={moveShot} onGenerateKeyframe={generateKeyframe} onNextStage={() => { setViewedStage("generate"); void applyUpdate({ stage: "generate" }); }} />}
          {viewedStage === "generate" && <GenerateStage production={activeProduction} assets={liveAssets} saving={saving} onGenerateShot={generateShot} onStageChange={(stage) => { setViewedStage(stage); void applyUpdate({ stage }); }} />}
          {viewedStage === "edit" && <EditStage production={activeProduction} assets={liveAssets} saving={saving} onBuildAudioPlan={buildAudioPlan} onGenerateSoundtrack={generateSoundtrack} onRender={renderFirstCut} onStageChange={(stage) => { setViewedStage(stage); void applyUpdate({ stage }); }} />}
          {viewedStage === "deliver" && <DeliverStage production={activeProduction} assets={liveAssets} saving={saving} onRender={renderFirstCut} />}
        </section>

        {assetsDrawerOpen ? <aside className="flex w-80 shrink-0 flex-col overflow-hidden border-l bg-background max-[1160px]:hidden">
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
    </main>
  );
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

function DirectionWorkspace({ production, saving, agentDraft, onAgentDraftChange, onSend, onSave, onApprove }: { production: VideoProduction; saving: boolean; agentDraft: string; onAgentDraftChange: (value: string) => void; onSend: () => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; onApprove: () => void }) {
  const direction = production.creative_direction;
  const referenceFramePlan = direction.reference_frame_plan ?? [];
  const hasConversation = production.conversation.length > 0;
  const analyzeLabel = hasConversation ? "Send to Creative Strategist" : "Analyze reference";
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} hasContent={Boolean(direction.reference_summary)} thinkingLabel="Creative Strategist is thinking…" emptyIcon={MessageSquareText} emptyTitle="Start with a brief or creative reference" emptyDescription="Upload a Creative Reference on the right, then describe your product, audience, channel, and desired outcome below.">
        {direction.reference_summary ? (
          <Card className="overflow-hidden border p-0 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-muted/20 px-5 py-4">
              <div className="flex items-start gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-bold text-background">01</span>
                <div><p className="text-sm font-semibold">Creative Strategist report</p><p className="mt-1 text-xs text-muted-foreground">{displayReportText(direction.commercial_type, " · ")}</p></div>
              </div>
              <div className="flex items-center gap-3"><Badge variant="outline">{direction.status}</Badge><Button onClick={onApprove} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Check />}Generate script</Button></div>
            </div>
            <div className="p-5">
              <div className="rounded-xl border-l-4 border-foreground bg-muted/25 px-4 py-3"><p className="text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">Creative direction</p><p className="mt-2 text-sm leading-6 text-foreground">{displayReportText(direction.reference_summary)}</p></div>
              {referenceFramePlan.length ? <section className="mt-5 rounded-xl border bg-muted/10 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><p className="text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">Designer reference frames</p><p className="mt-1 text-xs leading-5 text-muted-foreground">These moments will be extracted from the Creative Reference when the Designer creates visual asset packs.</p></div>
                  <Badge variant="outline">{referenceFramePlan.length} planned</Badge>
                </div>
                <ol className="mt-4 grid gap-3 md:grid-cols-3">
                  {referenceFramePlan.map((frame, index) => <li key={`${frame.timestamp_seconds}-${index}`} className="rounded-lg border bg-background p-3">
                    <div className="flex items-center gap-2"><span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-foreground text-[10px] font-bold text-background">{String(index + 1).padStart(2, "0")}</span><span className="text-xs font-semibold tabular-nums text-muted-foreground">{formatReferenceTimecode(frame.timestamp_seconds)}</span></div>
                    <p className="mt-3 text-sm font-medium leading-5">{frame.purpose || "Reference moment"}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{frame.rationale || "Used as a controlled visual reference during design."}</p>
                  </li>)}
                </ol>
              </section> : null}
              <div className="mt-5 grid gap-4 md:grid-cols-2"><ScriptList index="02" title="Strengths to adapt" items={direction.strengths_to_adapt} /><ScriptList index="03" title="Required brand assets" items={direction.asset_request} /><ScriptList index="04" title="Story structure" items={direction.story_structure} /><ScriptList index="05" title="Originality guardrails" items={direction.originality_guardrails} /></div>
            </div>
          </Card>
        ) : null}
      </ProductionConversationMessages>
      <ProductionComposer production={production} saving={saving} value={agentDraft} onChange={onAgentDraftChange} onSend={onSend} onSave={onSave} placeholder="Describe the product and outcome, ask about the reference, or refine the direction…" ariaLabel={analyzeLabel} />
    </div>
  );
}

function ScriptWorkspace({ production, saving, canLock, agentDraft, onAgentDraftChange, onSend, onSave, onLock }: { production: VideoProduction; saving: boolean; canLock: boolean; agentDraft: string; onAgentDraftChange: (value: string) => void; onSend: () => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; onLock: () => void }) {
  const [rawScript, setRawScript] = useState(production.script.raw_script);
  const script = production.script;
  const hasDraft = Boolean(script.raw_script || script.logline || script.beats.length);

  useEffect(() => setRawScript(production.script.raw_script), [production.production_id, production.script.raw_script]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} hasContent={hasDraft} thinkingLabel="Screenwriter is drafting the script…" emptyIcon={Wand2} emptyTitle="Turn the approved direction into a script" emptyDescription="Ask the Screenwriter to draft, revise, or tighten the commercial before production design begins.">
          {hasDraft ? (
            <Card className="overflow-hidden p-0">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4"><div><p className="text-sm font-semibold">Screenwriter draft</p><p className="mt-1 text-xs text-muted-foreground">Version {script.revision} · {production.target_seconds}s</p></div><Button onClick={onLock} disabled={!canLock || saving}>{saving ? <Loader2 className="animate-spin" /> : <Check />} Lock script & open design</Button></div>
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

function DesignStage({ production, assets, saving, batchGenerating, agentDraft, onAgentDraftChange, onSend, onSave, onGenerateSheet, onGenerateMissingSheets, onSelectCandidate, onApproveAndDirect }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; batchGenerating: boolean; agentDraft: string; onAgentDraftChange: (value: string) => void; onSend: () => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; onGenerateSheet: (sheet: VideoProductionDesignSheet) => void; onGenerateMissingSheets: (sheets: VideoProductionDesignSheet[]) => void; onSelectCandidate: (sheet: VideoProductionDesignSheet, panel: number) => void; onApproveAndDirect: () => Promise<void> }) {
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
  const areSheetsReady = designSheets.length > 0
    && designSheets.every((sheet) => sheet.status === "approved" && (sheet.approved_asset_ids.length > 0 || Boolean(sheet.selected_asset_id)));
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages fullWidth saving={saving} thinkingLabel="Production Designer is building visual rules…" emptyIcon={ImagePlus} emptyTitle="Create the visual design bible" emptyDescription="Ask the Production Designer to turn the locked script and Brand Assets into controlled rules for keyframes, logo, products, and continuity.">
        {hasDesign ? (
          <Card className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
              <div><p className="text-sm font-semibold">Production Asset Packs</p><p className="mt-1 text-xs text-muted-foreground">Lock character, environment, product/UI, lighting, motion, and transition states before storyboarding.</p></div>
              <Badge variant="outline">{design.status}</Badge>
            </div>
            <DesignSheetWorkspace sheets={designSheets} assets={assets} saving={saving} batchGenerating={batchGenerating} onGenerateSheet={onGenerateSheet} onGenerateMissingSheets={onGenerateMissingSheets} onSelectCandidate={onSelectCandidate} />
            <details className="border-t px-5 py-4">
              <summary className="cursor-pointer text-sm font-medium text-muted-foreground transition hover:text-foreground">View production design bible</summary>
              <div className="mt-4 grid gap-5 md:grid-cols-2">
                <ScriptList title="Visual identity" items={design.visual_identity} />
                <ScriptList title="Character and product rules" items={design.character_and_product_rules} />
                <ScriptList title="Logo and copy rules" items={design.logo_and_copy_rules} />
                <ScriptList title="Keyframe rules" items={design.keyframe_rules} />
                <ScriptList title="Continuity rules" items={design.continuity_rules} />
                <ScriptList title="Lighting and color cards" items={design.lighting_and_color_cards} />
                <ScriptList title="Motion blueprints" items={design.motion_blueprints} />
                <ScriptList title="Transition rules" items={design.transition_rules} />
                <ScriptList title="Missing assets" items={design.missing_assets} />
                {design.keyframe_prompts.length ? <ScriptList title="Keyframe guidance" items={design.keyframe_prompts} /> : null}
              </div>
            </details>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/15 px-5 py-4">
              {!areSheetsReady ? <p className="text-xs text-muted-foreground">Approve each Pack required by this script before opening the storyboard.</p> : <span />}
              <Button onClick={() => void onApproveAndDirect()} disabled={saving || !areSheetsReady}>{saving ? <Loader2 className="animate-spin" /> : <Check />} Approve design & create storyboard</Button>
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
      <ProductionComposer production={production} saving={saving} value={agentDraft} onChange={onAgentDraftChange} onSend={onSend} onSave={onSave} placeholder="Ask the Production Designer to define visual identity, product handling, logo rules, keyframe constraints, or continuity…" ariaLabel="Send to Production Designer" />
    </div>
  );
}

function DesignSheetWorkspace({ sheets, assets, saving, batchGenerating, onGenerateSheet, onGenerateMissingSheets, onSelectCandidate }: { sheets: VideoProductionDesignSheet[]; assets: AssetSummary[]; saving: boolean; batchGenerating: boolean; onGenerateSheet: (sheet: VideoProductionDesignSheet) => void; onGenerateMissingSheets: (sheets: VideoProductionDesignSheet[]) => void; onSelectCandidate: (sheet: VideoProductionDesignSheet, panel: number) => void }) {
  const [expandedPromptIds, setExpandedPromptIds] = useState<string[]>([]);
  const [lightboxSheetId, setLightboxSheetId] = useState<string | null>(null);
  const panelLabels = ["A", "B", "C", "D"];
  const packLabel = (sheet: VideoProductionDesignSheet) => ({
    character: "Character Pack",
    environment: "Environment Pack",
    prop: "Prop Pack",
    ui: "UI Pack",
    lighting: "Lighting & Color Card",
    transition: "Transition Pair",
  }[sheet.asset_pack_type] ?? (sheet.kind === "character_consistency" ? "Character Pack" : "Environment Pack"));
  const needsPropSource = (sheet: VideoProductionDesignSheet) => sheet.asset_pack_type === "prop"
    && !(sheet.asset_ids ?? []).some((assetId) => {
      const asset = assets.find((candidate) => candidate.id === assetId);
      return asset?.type === "image" || asset?.type === "gif";
    });
  const missingSheets = sheets.filter((sheet) => !needsPropSource(sheet)
    && !sheet.grid_asset_id && !(sheet.panel_asset_ids?.length) && !(sheet.approved_asset_ids?.length) && !sheet.selected_asset_id && sheet.status !== "generating");
  const startedSheets = sheets.filter((sheet) => !needsPropSource(sheet) && (
    sheet.status === "generating"
    || sheet.status === "approved"
    || Boolean(sheet.grid_asset_id || sheet.panel_asset_ids?.length || sheet.approved_asset_ids?.length || sheet.selected_asset_id)
  )).length;
  const lightboxSheet = sheets.find((sheet) => sheet.id === lightboxSheetId);
  const lightboxAsset = lightboxSheet ? assets.find((asset) => asset.id === lightboxSheet.grid_asset_id) : undefined;

  const renderSheetGrid = (sheet: VideoProductionDesignSheet, expanded = false) => {
    const gridAsset = assets.find((asset) => asset.id === sheet.grid_asset_id);
    const legacyAssets = (sheet.panel_asset_ids ?? []).map((assetId) => assets.find((asset) => asset.id === assetId)).filter((asset): asset is AssetSummary => Boolean(asset));
    const canSelect = Boolean(gridAsset) && !saving && sheet.status !== "generating";
    if (gridAsset) {
      return <div className={cn("relative overflow-hidden bg-slate-100", expanded ? "mx-auto h-[min(76vh,900px)] max-w-[min(76vh,900px)]" : "aspect-square")}> 
        <img src={gridAsset.url} alt={`${sheet.title} controlled 2x2 consistency sheet`} className="size-full object-contain" />
        <div className="absolute inset-0 grid grid-cols-2 grid-rows-2">
          {panelLabels.map((label, panel) => <button key={label} type="button" disabled={!canSelect} onClick={() => onSelectCandidate(sheet, panel)} className={cn("relative border border-white/70 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/80 disabled:cursor-default", sheet.selected_panel === panel ? "bg-black/5 ring-2 ring-foreground ring-inset" : "hover:bg-black/5")}> 
            <span className="absolute left-2 top-2 flex size-7 items-center justify-center rounded-full bg-black/65 text-xs font-bold text-white">{label}</span>
            {sheet.approved_panel_asset_ids?.[String(panel)] ? <span className="absolute bottom-2 right-2 rounded-full bg-foreground px-2 py-1 text-[10px] font-semibold text-background">Locked</span> : sheet.selected_panel === panel ? <span className="absolute bottom-2 right-2 rounded-full bg-foreground px-2 py-1 text-[10px] font-semibold text-background">Selected</span> : null}
          </button>)}
        </div>
      </div>;
    }
    if (legacyAssets.length) {
      return <div className="grid aspect-square grid-cols-2 gap-1 bg-slate-100 p-1">{legacyAssets.slice(0, 4).map((asset, panel) => <div key={asset.id} className="relative overflow-hidden bg-slate-200"><img src={asset.url} alt={`Legacy candidate ${panelLabels[panel]}`} className="size-full object-cover" /><span className="absolute left-2 top-2 flex size-6 items-center justify-center rounded-full bg-black/65 text-[10px] font-bold text-white">{panelLabels[panel]}</span></div>)}</div>;
    }
    const needsSource = needsPropSource(sheet);
    return <div className="flex aspect-square flex-col items-center justify-center bg-[linear-gradient(135deg,#f7f9fc,#edf2f7)] p-6 text-center">{sheet.status === "generating" ? <Loader2 className="size-7 animate-spin text-slate-500" /> : <Layers3 className={cn("size-8", needsSource ? "text-amber-500" : "text-slate-400")} />}<p className="mt-3 text-sm font-semibold text-slate-800">{sheet.status === "generating" ? "Generating asset pack…" : needsSource ? "Product asset required" : "Asset pack pending"}</p><p className="mt-1 text-xs leading-5 text-slate-500">{needsSource ? "Add an approved product image in Brand Assets, then regenerate the Design Bible." : "A controlled visual sheet will appear here for review."}</p></div>;
  };

  return (
    <div className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div><p className="text-sm font-semibold">Asset pack board</p><p className="mt-1 text-xs text-muted-foreground">Each card keeps its source, visual state, instruction, and approval together.</p></div>
        <div className="flex items-center gap-2"><Badge variant="outline">{startedSheets} / {sheets.length} started</Badge><Button size="sm" onClick={() => onGenerateMissingSheets(sheets)} disabled={saving || batchGenerating || !missingSheets.length}>{batchGenerating ? <Loader2 className="animate-spin" /> : <Sparkles />}{missingSheets.length ? `Generate ${missingSheets.length} missing packs` : "All packs generated"}</Button></div>
      </div>
      <div className="mt-5 grid gap-5 md:grid-cols-2 2xl:grid-cols-3">
        {sheets.map((sheet) => {
          const sourceAssets = sheet.asset_ids.map((assetId) => assets.find((asset) => asset.id === assetId)).filter((asset): asset is AssetSummary => Boolean(asset));
          const hasOutput = Boolean(sheet.grid_asset_id || sheet.panel_asset_ids?.length);
          const needsSource = needsPropSource(sheet);
          const isPromptExpanded = expandedPromptIds.includes(sheet.id);
          const lockedCount = sheet.approved_asset_ids?.length ?? 0;
          return <Card key={sheet.id} className="group flex min-w-0 flex-col overflow-hidden p-0 shadow-sm">
            <div className="flex items-start justify-between gap-3 border-b px-4 py-3"><div className="min-w-0"><Badge variant="outline" className="text-[10px]">{packLabel(sheet)}</Badge><p className="mt-2 line-clamp-2 text-sm font-semibold">{sheet.title}</p></div><Badge className={cn("shrink-0 border-transparent", needsSource ? "bg-amber-100 text-amber-900 hover:bg-amber-100 hover:text-amber-900" : sheet.status === "approved" ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-100 hover:text-emerald-800" : sheet.status === "generating" ? "bg-blue-100 text-blue-800 hover:bg-blue-100 hover:text-blue-800" : "bg-muted text-muted-foreground hover:bg-muted hover:text-muted-foreground")}>{needsSource ? "needs product asset" : sheet.status}</Badge></div>
            <div className="relative border-b bg-slate-100">{renderSheetGrid(sheet)}{hasOutput ? <Button type="button" size="icon" variant="secondary" className="absolute right-3 top-3 rounded-full bg-background/90 shadow-md" onClick={() => setLightboxSheetId(sheet.id)} aria-label={`Expand ${sheet.title}`}><Maximize2 className="size-4" /></Button> : null}</div>
            <div className="flex flex-1 flex-col p-4">
              <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{sheet.purpose}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {sheet.scene_ids?.length ? <Badge variant="outline" className="text-[10px]">{sheet.scene_ids.length === 1 ? `Used by ${sheet.scene_ids[0]}` : `Used by ${sheet.scene_ids.length} scenes`}</Badge> : <Badge variant="outline" className="text-[10px]">Global visual rule</Badge>}
                {sheet.reason_for_new_pack ? <span className="max-w-full truncate text-[11px] leading-5 text-muted-foreground" title={sheet.reason_for_new_pack}>{sheet.reason_for_new_pack}</span> : null}
              </div>
              <div className="mt-4"><div className="flex items-center justify-between gap-2"><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">Source assets</p><span className="text-[10px] text-muted-foreground">{sourceAssets.length}</span></div><div className="mt-2 flex gap-2 overflow-x-auto pb-1">{sourceAssets.length ? sourceAssets.map((asset) => <div key={asset.id} className="w-14 shrink-0 overflow-hidden rounded-md border bg-muted/20"><div className="flex aspect-square items-center justify-center bg-muted">{asset.type === "image" || asset.type === "gif" ? <img src={asset.url} alt="" className="size-full object-cover" /> : <Film className="size-4 text-muted-foreground" />}</div><p className="truncate px-1.5 py-1 text-[9px] font-medium">{asset.title}</p></div>) : <p className={cn("text-xs", needsSource ? "font-medium text-amber-800" : "text-muted-foreground")}>{needsSource ? "Hero product image required." : "No linked source asset."}</p>}</div></div>
              <div className="mt-4 rounded-lg border bg-muted/20 p-3"><div className="flex items-center justify-between gap-2"><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">Image prompt</p><Sparkles className="size-3.5 text-muted-foreground" /></div><p className={cn("mt-2 whitespace-pre-wrap text-xs leading-5 text-foreground/80", !isPromptExpanded && "line-clamp-3")}>{sheet.prompt}</p><button type="button" className="mt-2 text-xs font-medium text-foreground underline-offset-4 hover:underline" onClick={() => setExpandedPromptIds((ids) => ids.includes(sheet.id) ? ids.filter((id) => id !== sheet.id) : [...ids, sheet.id])}>{isPromptExpanded ? "Collapse prompt" : "View full prompt"}</button></div>
              <div className="mt-4 flex items-center justify-between gap-2 border-t pt-3"><span className="text-xs text-muted-foreground">{lockedCount ? `${lockedCount} state${lockedCount === 1 ? "" : "s"} locked` : needsSource ? "Upload a hero product to continue" : "Select a panel to lock a state"}</span><Button size="sm" variant={needsSource || hasOutput ? "outline" : "default"} onClick={() => onGenerateSheet(sheet)} disabled={saving || sheet.status === "generating" || needsSource}>{sheet.status === "generating" ? <Loader2 className="animate-spin" /> : <Sparkles />}{needsSource ? "Needs product asset" : hasOutput ? "Regenerate" : "Generate"}</Button></div>
            </div>
          </Card>;
        })}
      </div>
      {lightboxSheet && lightboxAsset ? <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/85 p-6" role="dialog" aria-modal="true" aria-label="Expanded consistency sheet"><div className="relative flex max-h-full max-w-full flex-col"><div className="mb-3 flex items-center justify-between gap-4 text-sm font-medium text-white"><span>{lightboxSheet.title} - select a locked reference frame</span><Button type="button" size="icon" variant="secondary" className="rounded-full" onClick={() => setLightboxSheetId(null)} aria-label="Close sheet"><X className="size-4" /></Button></div>{renderSheetGrid(lightboxSheet, true)}</div></div> : null}
    </div>
  );
}

function StoryboardStage({ production, assets, selectedShot, saving, agentDraft, onAgentDraftChange, onSend, onSave, onSelectShot, onSaveShot, onMoveShot, onGenerateKeyframe, onNextStage }: { production: VideoProduction; assets: AssetSummary[]; selectedShot: VideoProductionShot | null; saving: boolean; agentDraft: string; onAgentDraftChange: (value: string) => void; onSend: () => void; onSave: (payload: Parameters<typeof updateVideoProduction>[1]) => Promise<void>; onSelectShot: (id: string) => void; onSaveShot: (payload: Partial<VideoProductionShot>) => Promise<void>; onMoveShot: (direction: -1 | 1) => Promise<void>; onGenerateKeyframe: (shot: VideoProductionShot) => Promise<void>; onNextStage: () => void }) {
  const shots = [...production.shots].sort((left, right) => left.order - right.order);
  const [draft, setDraft] = useState<VideoProductionShot | null>(selectedShot);
  useEffect(() => setDraft(selectedShot), [selectedShot]);

  const selectedKeyframe = selectedShot ? assets.find((asset) => asset.id === selectedShot.keyframe_asset_id) : null;
  const assetPacks = production.design_bible.asset_packs?.length
    ? production.design_bible.asset_packs
    : [...production.design_bible.character_consistency_sheets, ...production.design_bible.scene_style_sheets];
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

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} thinkingLabel="Director is refining shot cards…" emptyIcon={Layers3} emptyTitle="Create storyboard shot cards" emptyDescription="Ask the Director to convert the locked script and design bible into shot cards with keyframe intent, continuity, and Veo prompts.">
        <div className="border-t pt-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-sm font-semibold">Storyboard canvas</p>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">Each shot card carries one visual idea, one approved keyframe, one prompt, and continuity rules for adjacent shots.</p>
            </div>
            <Button onClick={onNextStage} disabled={!shots.length}><ArrowRight /> Go to production</Button>
          </div>

          {shots.length ? (
            <>
              <div className="mt-5 flex gap-3 overflow-x-auto pb-2">
                {shots.map((shot) => {
                  const cardKeyframe = assets.find((asset) => asset.id === shot.keyframe_asset_id);
                  return (
                    <button type="button" key={shot.id} onClick={() => onSelectShot(shot.id)} className={cn("w-56 shrink-0 overflow-hidden rounded-xl border text-left transition", selectedShot?.id === shot.id ? "border-foreground ring-1 ring-foreground" : "hover:border-foreground/40")}>
                      <div className="flex aspect-video items-center justify-center bg-[linear-gradient(135deg,#dfe7f2,#f7f8fa)]">
                        {cardKeyframe ? <img src={cardKeyframe.url} alt="" className="size-full object-cover" /> : <span className="rounded-md bg-background/80 px-2 py-1 text-xs font-semibold">{shot.status === "generating" ? "Generating keyframe…" : "Keyframe pending"}</span>}
                      </div>
                      <div className="p-3">
                        <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold text-muted-foreground">S{String(shot.order).padStart(2, "0")}</span><Badge variant="outline" className="text-[10px]">{shot.duration_seconds}s</Badge></div>
                        <p className="mt-2 line-clamp-2 text-sm font-semibold">{shot.title}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{shot.purpose}</p>
                      </div>
                    </button>
                  );
                })}
              </div>

              {selectedShot && draft ? (
                <Card className="mt-3 grid gap-0 overflow-hidden lg:grid-cols-[1fr_330px]">
                  <div className="p-5">
                    <div className="flex items-center justify-between gap-2">
                      <div><span className="text-xs font-semibold text-muted-foreground">S{String(draft.order).padStart(2, "0")} · {draft.start_seconds}s</span><h3 className="mt-1 text-lg font-semibold">{draft.title}</h3></div>
                      <div className="flex gap-1"><Button size="icon" variant="outline" onClick={() => void onMoveShot(-1)} aria-label="Move shot left"><ArrowLeft /></Button><Button size="icon" variant="outline" onClick={() => void onMoveShot(1)} aria-label="Move shot right"><ArrowRight /></Button></div>
                    </div>
                    <div className="mt-5 grid gap-4 sm:grid-cols-2">
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
                    <Field label="Veo prompt" value={draft.veo_prompt} multiline onChange={(value) => setDraft({ ...draft, veo_prompt: value })} />
                    <div className="mt-5 flex justify-end"><Button onClick={() => void onSaveShot(draft)} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Check />} Save shot card</Button></div>
                  </div>
                  <div className="border-t bg-muted/20 p-5 lg:border-l lg:border-t-0">
                    <p className="text-sm font-semibold">Keyframe approval</p>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">Generate a controlled keyframe from the linked assets, then explicitly approve it before video takes are allowed.</p>
                    {selectedKeyframe ? <img src={selectedKeyframe.url} alt="Selected keyframe" className="mt-4 aspect-video w-full rounded-lg border object-cover" /> : <div className="mt-5 rounded-xl border border-dashed bg-background p-4 text-sm text-muted-foreground">Link image assets in the right rail, then generate a keyframe for this shot.</div>}
                    <Button variant="secondary" className="mt-4 w-full" onClick={() => void onGenerateKeyframe(selectedShot)} disabled={saving || selectedShot.status === "generating"}><Sparkles /> {selectedShot.status === "generating" ? "Generating keyframe…" : selectedKeyframe ? "Regenerate keyframe" : "Generate keyframe"}</Button>
                    <Button className="mt-2 w-full" onClick={() => void onSaveShot({ status: "approved" })} disabled={saving || !selectedKeyframe || selectedShot.status === "approved"}><Check /> {selectedShot.status === "approved" ? "Shot approved" : "Approve keyframe"}</Button>
                  </div>
                </Card>
              ) : null}
            </>
          ) : (
            <Card className="mt-5 border-dashed p-6 text-sm leading-6 text-muted-foreground">No shot cards yet. Ask the Director to create storyboard cards after the design bible is approved.</Card>
          )}
        </div>
      </ProductionConversationMessages>
      <ProductionComposer production={production} saving={saving} value={agentDraft} onChange={onAgentDraftChange} onSend={onSend} onSave={onSave} placeholder="Ask the Director to revise shot order, split long beats, tighten continuity, or regenerate the storyboard plan…" ariaLabel="Send to Director" />
    </div>
  );
}

function GenerateStage({ production, assets, saving, onGenerateShot, onStageChange }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; onGenerateShot: (shot: VideoProductionShot) => Promise<void>; onStageChange: (stage: VideoProductionStage) => void }) {
  const approvedCount = production.shots.filter((shot) => shot.status === "approved").length;
  const readyCount = production.shots.filter((shot) => shot.status === "ready").length;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} thinkingLabel="Production queue is updating…" emptyIcon={Sparkles} emptyTitle="Shot-level generation queue" emptyDescription="Approved storyboard shots will appear here with their keyframes, prompts, and generated takes.">
        <div className="border-t pt-5">
          <Card className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
              <div><p className="text-sm font-semibold">Shot-level production queue</p><p className="mt-1 text-xs text-muted-foreground">Generate only approved shots. Every take stays linked to its prompt, keyframe, and continuity rule.</p></div>
              <div className="flex gap-2"><Badge variant="outline">{approvedCount} approved</Badge><Badge variant="outline">{readyCount} ready</Badge></div>
            </div>
            <div className="divide-y">
              {production.shots.length ? production.shots.map((shot) => {
                const video = assets.find((asset) => asset.id === shot.video_asset_ids[0]);
                const keyframe = assets.find((asset) => asset.id === shot.keyframe_asset_id);
                return (
                  <div key={shot.id} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                    <div className="flex min-w-0 items-center gap-3">
                      {video ? <video src={video.url} className="h-16 w-28 rounded-md bg-black object-cover" muted /> : keyframe ? <img src={keyframe.url} alt="" className="h-16 w-28 rounded-md object-cover" /> : <div className="flex h-16 w-28 items-center justify-center rounded-md bg-muted"><Film className="size-5 text-muted-foreground" /></div>}
                      <div className="min-w-0"><p className="truncate text-sm font-semibold">S{String(shot.order).padStart(2, "0")} · {shot.title}</p><p className="mt-1 text-xs text-muted-foreground">{shot.duration_seconds}s · {shot.status === "approved" ? "Ready for video generation" : shot.status === "generating" ? "Generating take…" : shot.status === "ready" ? "Take ready" : "Approve keyframe in Storyboard"}</p></div>
                    </div>
                    <div className="flex items-center gap-2"><Badge variant="outline">{shot.status}</Badge><Button size="sm" onClick={() => void onGenerateShot(shot)} disabled={saving || shot.status !== "approved"}>{shot.status === "generating" ? <Loader2 className="animate-spin" /> : <Sparkles />}{video ? "Regenerate" : "Generate"}</Button></div>
                  </div>
                );
              }) : <div className="px-5 py-8 text-sm text-muted-foreground">No shot cards yet. Create the storyboard before production.</div>}
            </div>
          </Card>
        </div>
      </ProductionConversationMessages>
      <ProductionActionBar><Button variant="secondary" onClick={() => onStageChange("storyboard")}>Back to storyboard</Button><Button onClick={() => onStageChange("edit")} disabled={readyCount === 0}>Open edit timeline <ArrowRight /></Button></ProductionActionBar>
    </div>
  );
}

function EditStage({ production, assets, saving, onBuildAudioPlan, onGenerateSoundtrack, onRender, onStageChange }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; onBuildAudioPlan: () => void; onGenerateSoundtrack: () => void; onRender: (includeAudio?: boolean) => void; onStageChange: (stage: VideoProductionStage) => void }) {
  const ready = production.shots.filter((shot) => shot.status === "ready").length;
  const audioPlan = production.audio_plan;
  const soundtrack = assets.find((asset) => audioPlan.music_asset_ids.includes(asset.id));
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ProductionConversationMessages saving={saving} thinkingLabel="Editor is rendering the first cut…" emptyIcon={Film} emptyTitle="Build the deterministic timeline" emptyDescription="Generated shot takes will be assembled here in storyboard order with sound, captions, transitions, CTA, and legal tracks.">
        <div className="border-t pt-5">
          <Card className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
              <div><p className="text-sm font-semibold">Deterministic timeline</p><p className="mt-1 text-xs text-muted-foreground">Arrange generated takes in storyboard order, then produce a reviewable first cut.</p></div>
              <Badge variant="outline">{ready} ready takes</Badge>
            </div>
            <div className="p-5">
              <div className="flex gap-2 overflow-x-auto">
                {production.shots.map((shot) => <div key={shot.id} className={cn("min-w-40 flex-1 rounded-lg border p-3", shot.status === "ready" ? "bg-card" : "bg-muted/30 opacity-60")}><span className="text-xs font-semibold text-muted-foreground">{shot.start_seconds}s</span><p className="mt-2 text-sm font-semibold">S{String(shot.order).padStart(2, "0")}</p><p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{shot.title}</p><Badge variant="outline" className="mt-3 text-[10px]">{shot.status}</Badge></div>)}
              </div>
              <div className="mt-5 grid gap-3 md:grid-cols-3">
                {["Sound and music track", "Captions and CTA track", "Transitions and legal copy"].map((item) => <div key={item} className="flex items-center gap-2 rounded-lg border border-dashed p-3 text-sm text-muted-foreground"><Music2 className="size-4" />{item}</div>)}
              </div>
            </div>
          </Card>
          <Card className="mt-5 overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4"><div><p className="text-sm font-semibold">Audio Producer</p><p className="mt-1 text-xs text-muted-foreground">Create an instrumental soundtrack after the script and shot timing are set.</p></div><Badge variant="outline">{audioPlan.status}</Badge></div>
            <div className="space-y-4 p-5">
              {audioPlan.music_prompt ? <><p className="text-sm leading-6 text-muted-foreground">{audioPlan.music_prompt}</p><div className="flex flex-wrap gap-2"><Badge variant="outline">{audioPlan.bpm ?? "Adaptive"} BPM</Badge><Badge variant="outline">{audioPlan.intensity}</Badge><Badge variant="outline">{audioPlan.instrumental ? "Instrumental" : "Audio plan"}</Badge></div>{audioPlan.cue_sheet.length ? <div className="grid gap-2 md:grid-cols-2">{audioPlan.cue_sheet.map((cue) => <div key={`${cue.shot_id}-${cue.start_seconds}`} className="rounded-lg border p-3 text-xs"><p className="font-semibold">{cue.start_seconds}s-{cue.end_seconds}s · {cue.purpose}</p><p className="mt-1 text-muted-foreground">{cue.music_direction}</p>{cue.sfx.length ? <p className="mt-1 text-muted-foreground">SFX: {cue.sfx.join(", ")}</p> : null}</div>)}</div> : null}</> : <p className="text-sm text-muted-foreground">Generate a soundtrack blueprint before calling Lyria.</p>}
              {soundtrack ? <audio controls className="w-full" src={soundtrack.url} /> : null}
              <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={onBuildAudioPlan} disabled={saving}>{saving && audioPlan.status === "generating" ? <Loader2 className="animate-spin" /> : <Music2 />}{audioPlan.music_prompt ? "Refine audio plan" : "Build audio plan"}</Button>{audioPlan.music_prompt ? <Button onClick={onGenerateSoundtrack} disabled={saving || audioPlan.status === "generating"}>{saving && audioPlan.status === "generating" ? <Loader2 className="animate-spin" /> : <Sparkles />}{soundtrack ? "Regenerate soundtrack" : "Generate soundtrack"}</Button> : null}</div>
            </div>
          </Card>
        </div>
      </ProductionConversationMessages>
      <ProductionActionBar><Button variant="secondary" onClick={() => onStageChange("generate")}>Back to takes</Button><Button variant="secondary" onClick={() => onRender(false)} disabled={saving || ready === 0}>{saving ? <Loader2 className="animate-spin" /> : <Film />}Render silent first cut</Button><Button onClick={() => onRender(true)} disabled={saving || ready === 0 || !soundtrack}>{saving ? <Loader2 className="animate-spin" /> : <Music2 />}Render final cut with soundtrack</Button></ProductionActionBar>
    </div>
  );
}

function DeliverStage({ production, assets, saving, onRender }: { production: VideoProduction; assets: AssetSummary[]; saving: boolean; onRender: (includeAudio?: boolean) => void }) {
  const final = assets.find((asset) => asset.id === production.final_asset_id);
  const hasSoundtrack = production.audio_plan.music_asset_ids.length > 0;
  const checks = ["Duration, aspect ratio, resolution, and first-cut continuity", "Brand logo, product, CTA, and disclaimer placement", "No black frames, duplicated shots, or continuity break", "Sound, captions, and rights review", "MP4 master and editable shot assets"];
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
      <ProductionActionBar>{!final ? <Button onClick={() => onRender(hasSoundtrack)} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : hasSoundtrack ? <Music2 /> : <Film />}{hasSoundtrack ? "Render final cut with soundtrack" : "Render first cut"}</Button> : <Button variant="secondary" disabled>Delivery package ready</Button>}</ProductionActionBar>
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
