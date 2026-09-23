"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Bot, Check, ChevronLeft, ChevronRight, Clapperboard, Film, ImagePlus, Layers3, Loader2, MessageSquare, Play, Send, Sparkles, Wand2 } from "lucide-react";
import type { AssetSummary, JobSummary } from "@incept/shared";
import { approveVideoProductionStoryboard, cancelJob, createVideoProductionDesignSheet, createVideoProductionShot, deleteVideoProductionShot, generateVideoProductionDesignSheet, generateVideoProductionKeyframe, generateVideoProductionShot, generateVideoProductionSoundtrack, getJob, getVideoProduction, getVideoProductionCapabilities, listAssets, listVideoProductionEvents, lockVideoProductionScript, openVideoProductionEventStream, renderVideoProductionFirstCut, reorderVideoProductionShots, restoreVideoProductionScriptRevision, runVideoProductionAudioProducer, runVideoProductionCopilot, runVideoProductionEditReviewer, runVideoProductionScriptAgent, selectVideoProductionDesignSheetPanel, updateVideoProduction, updateVideoProductionShot, type VideoProduction, type VideoProductionDesignSheet, type VideoProductionEditOverlay, type VideoProductionEvent, type VideoProductionProviderCapabilities, type VideoProductionProviderSelection, type VideoProductionShot } from "@/lib/incept-api";

const WORKSPACE_ID = "wsp_q2";
const phases = ["Preparation", "Script", "Production", "Completed"];
type Tab = "storyboard" | "versions" | "review";
type WorkspaceView = "script" | "storyboard" | "assets";

function operatorPhase(project: VideoProduction) {
  if (project.final_asset_id) return 3;
  if (project.shots.some((shot) => shot.video_asset_ids.length) || ["generate", "audio", "edit", "deliver"].includes(project.stage)) return 2;
  if (project.script.status === "locked" || project.shots.length || ["script", "design", "storyboard"].includes(project.stage)) return 1;
  return 0;
}

function shotState(shot: VideoProductionShot) {
  if (shot.status === "generating") return "Generating";
  if (shot.status === "failed") return "Needs attention";
  if (shot.selected_video_asset_id) return "Selected";
  if (shot.video_asset_ids.length) return "Takes ready";
  if (shot.keyframe_asset_id) return "Ready for motion";
  return "Needs keyframe";
}

function MediaPreview({ asset, className }: { asset?: AssetSummary; className: string }) {
  if (!asset) return null;
  return asset.type === "video" ? <video className={className} controls preload="metadata" src={asset.url} /> : <img className={className} src={asset.url} alt={asset.title} />;
}

function ProjectModelSelect({ label, operation, options, value, onChange, required = false }: { label: string; operation: keyof VideoProductionProviderSelection; options: VideoProductionProviderCapabilities["text"]; value: VideoProductionProviderSelection["text"]; onChange: (operation: keyof VideoProductionProviderSelection, value: string) => void; required?: boolean }) {
  const selected = value.provider && value.model ? `${value.provider}::${value.model}` : "";
  return <label className="rounded-lg border border-[#e6e8ec] bg-white p-3 text-[11px] font-semibold text-[#171a20]">{label}{required ? <span className="ml-1 text-[#b42318]">*</span> : null}<select value={selected} disabled={!options.length} onChange={(event) => onChange(operation, event.target.value)} className="mt-2 h-8 w-full rounded-md border border-[#e6e8ec] bg-white px-2 text-[11px] font-normal outline-none disabled:bg-[#f6f8fb]"><option value="" disabled>{options.length ? "Select configured model" : "Not configured"}</option>{options.map((option) => <option key={`${option.provider}:${option.model}`} value={`${option.provider}::${option.model}`}>{option.label} · {option.model}</option>)}</select></label>;
}

function defaultProviderSelection(capabilities: VideoProductionProviderCapabilities): VideoProductionProviderSelection {
  const first = (options: VideoProductionProviderCapabilities["text"]) => options[0]
    ? { provider: options[0].provider, model: options[0].model }
    : { provider: "", model: "" };
  return { text: first(capabilities.text), image: first(capabilities.image), video: first(capabilities.video), audio: first(capabilities.audio) };
}

export function VideoProductionWorkspace({ productionId }: { productionId: string }) {
  const [project, setProject] = useState<VideoProduction | null>(null);
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("storyboard");
  const [scriptDraft, setScriptDraft] = useState("");
  const [savingScript, setSavingScript] = useState(false);
  const [savingStoryboard, setSavingStoryboard] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [audioBusy, setAudioBusy] = useState(false);
  const [overlayDraft, setOverlayDraft] = useState({ kind: "subtitle" as VideoProductionEditOverlay["kind"], text: "", start: "0", end: "", position: "bottom_center" as VideoProductionEditOverlay["position"] });
  const [savingOverlay, setSavingOverlay] = useState(false);
  const [designBusyId, setDesignBusyId] = useState<string | null>(null);
  const [newPack, setNewPack] = useState({ title: "", type: "environment" as VideoProductionDesignSheet["asset_pack_type"], purpose: "" });
  const [editDraft, setEditDraft] = useState({ include: true, trimIn: "0", trimOut: "" });
  const [shotDraft, setShotDraft] = useState({ title: "", purpose: "", visual: "", action: "", duration: "5" });
  const [tab, setTab] = useState<Tab>("storyboard");
  const [message, setMessage] = useState("");
  const [thinking, setThinking] = useState(false);
  const [busyShotId, setBusyShotId] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobStates, setJobStates] = useState<Record<string, JobSummary | null>>({});
  const [editingModels, setEditingModels] = useState(false);
  const [modelCapabilities, setModelCapabilities] = useState<VideoProductionProviderCapabilities | null>(null);
  const [modelDraft, setModelDraft] = useState<VideoProductionProviderSelection | null>(null);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelSaving, setModelSaving] = useState(false);
  const [activityEvents, setActivityEvents] = useState<VideoProductionEvent[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [activityReload, setActivityReload] = useState(0);

  async function refresh() {
    const [nextProject, nextAssets] = await Promise.all([getVideoProduction(productionId), listAssets(WORKSPACE_ID)]);
    setProject(nextProject); setAssets(nextAssets);
    setSelectedShotId((current) => current && nextProject.shots.some((shot) => shot.id === current) ? current : nextProject.shots[0]?.id ?? null);
  }

  async function openModelSettings() {
    if (!project) return;
    setModelLoading(true); setError(null);
    try {
      const capabilities = await getVideoProductionCapabilities();
      setModelCapabilities(capabilities);
      setModelDraft(project.video_setup.provider_selection ?? defaultProviderSelection(capabilities));
      setEditingModels(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load configured project models."); }
    finally { setModelLoading(false); }
  }

  function chooseModel(operation: keyof VideoProductionProviderSelection, encoded: string) {
    const [provider, model] = encoded.split("::");
    setModelDraft((current) => current ? { ...current, [operation]: { provider, model } } : current);
  }

  async function saveModelSettings() {
    if (!project || !modelDraft || modelSaving) return;
    setModelSaving(true); setError(null);
    try {
      const nextProject = await updateVideoProduction(project.production_id, {
        video_setup: { ...project.video_setup, provider_selection: modelDraft },
        expected_revision: project.state_revision,
      });
      setProject(nextProject); setEditingModels(false);
      setNotice("Project model selections saved. Future operations use these server-validated choices.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save project model selections."); }
    finally { setModelSaving(false); }
  }

  useEffect(() => { void refresh().catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load this production.")); }, [productionId]);
  useEffect(() => { setScriptDraft(project?.script.raw_script ?? ""); }, [project?.production_id, project?.script.raw_script]);
  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    setActivityLoading(true); setActivityError(null);
    void listVideoProductionEvents(project.production_id).then((events) => {
      if (!cancelled) setActivityEvents(events);
    }).catch((cause) => {
      if (!cancelled) setActivityError(cause instanceof Error ? cause.message : "Could not load project activity.");
    }).finally(() => { if (!cancelled) setActivityLoading(false); });
    return () => { cancelled = true; };
  }, [project?.production_id, project?.state_revision, activityReload]);
  useEffect(() => {
    if (!project) return;
    const stream = openVideoProductionEventStream(project.production_id);
    const refreshFromStream = () => {
      setActivityReload((value) => value + 1);
      void refresh().catch((cause) => setError(cause instanceof Error ? cause.message : "Could not refresh this production."));
    };
    stream.addEventListener("snapshot", refreshFromStream);
    stream.addEventListener("activity", refreshFromStream);
    stream.addEventListener("access_revoked", () => setError("Your access to this production changed. Refresh the library."));
    return () => stream.close();
  }, [project?.production_id]);

  const assetById = useMemo(() => new Map(assets.map((asset) => [asset.id, asset])), [assets]);
  const selectedShot = project?.shots.find((shot) => shot.id === selectedShotId) ?? project?.shots[0] ?? null;
  const selectedIndex = project?.shots.findIndex((shot) => shot.id === selectedShot?.id) ?? -1;
  const selectedTake = selectedShot ? assetById.get(selectedShot.selected_video_asset_id ?? "") : undefined;
  const selectedFrame = selectedTake ?? (selectedShot ? assetById.get(selectedShot.keyframe_asset_id ?? "") : undefined);
  const includedCount = project?.shots.filter((shot) => shot.include_in_edit !== false).length ?? 0;
  const selectedCount = project?.shots.filter((shot) => shot.include_in_edit !== false && shot.selected_video_asset_id).length ?? 0;
  const activePhase = project ? operatorPhase(project) : 0;
  const storyboardApproved = Boolean(project?.storyboard_approved_at);
  const trackedJobIds = useMemo(() => project ? Array.from(new Set([
    project.render_job_id,
    project.audio_plan.job_id,
    ...project.shots.flatMap((shot) => [shot.keyframe_job_id, shot.video_job_id]),
  ].filter((jobId): jobId is string => Boolean(jobId)))) : [], [project]);
  const selectedOperationIds = selectedShot ? [selectedShot.keyframe_job_id, selectedShot.video_job_id].filter((jobId): jobId is string => Boolean(jobId)) : [];
  const projectOperationIds = [project?.audio_plan.job_id, project?.render_job_id].filter((jobId): jobId is string => Boolean(jobId));
  useEffect(() => {
    if (!selectedShot) return;
    setShotDraft({ title: selectedShot.title, purpose: selectedShot.purpose, visual: selectedShot.visual, action: selectedShot.action, duration: String(selectedShot.duration_seconds) });
    setEditDraft({ include: selectedShot.include_in_edit !== false, trimIn: String(selectedShot.trim_in_seconds ?? 0), trimOut: selectedShot.trim_out_seconds == null ? "" : String(selectedShot.trim_out_seconds) });
  }, [selectedShot?.id]);

  useEffect(() => {
    if (!trackedJobIds.length) return;
    let cancelled = false;
    async function poll() {
      const records = await Promise.all(trackedJobIds.map(async (jobId) => [jobId, await getJob(jobId)] as const));
      if (!cancelled) setJobStates(Object.fromEntries(records));
    }
    void poll();
    const timer = window.setInterval(() => void poll(), 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [trackedJobIds.join(",")]);

  async function copilot(prompt: string) {
    if (!project || thinking || !prompt.trim()) return;
    setThinking(true); setError(null);
    try {
      const result = await runVideoProductionCopilot(project.production_id, { message: prompt, asset_ids: project.reference_asset_ids });
      setProject(result.production);
      setNotice(result.needs_confirmation ? "A decision is ready for your confirmation." : "Production plan updated.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Copilot could not complete that action."); }
    finally { setThinking(false); }
  }

  async function createMedia(kind: "keyframe" | "take") {
    if (!project || !selectedShot) return;
    setBusyShotId(selectedShot.id); setError(null);
    try {
      const job = kind === "keyframe" ? await generateVideoProductionKeyframe(project.production_id, selectedShot.id) : await generateVideoProductionShot(project.production_id, selectedShot.id, 2);
      setNotice((kind === "keyframe" ? "Keyframe" : "Two take variants") + " queued: " + job.title + ".");
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not queue this generation."); }
    finally { setBusyShotId(null); }
  }

  async function selectTake(assetId: string) {
    if (!project || !selectedShot) return;
    setBusyShotId(selectedShot.id); setError(null);
    try {
      setProject(await updateVideoProductionShot(project.production_id, selectedShot.id, { selected_video_asset_id: assetId }));
      setNotice("Take selected for the edit decision.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not select this take."); }
    finally { setBusyShotId(null); }
  }

  async function review() {
    if (!project || !selectedShot) return;
    setThinking(true); setError(null);
    try {
      setProject(await runVideoProductionEditReviewer(project.production_id, "Review available takes and describe tradeoffs. Do not select or replace a take.", [selectedShot.id]));
      setTab("review"); setNotice("Take review is ready; selection remains a human decision.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not complete take review."); }
    finally { setThinking(false); }
  }

  async function render() {
    if (!project) return;
    setRendering(true); setError(null);
    try {
      const job = await renderVideoProductionFirstCut(project.production_id, false);
      setNotice("Approved cut queued: " + job.title + "."); await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not render the approved cut."); }
    finally { setRendering(false); }
  }

  async function cancelOperation(jobId: string) {
    setError(null);
    try {
      await cancelJob(jobId);
      setNotice("Cancellation requested. The project keeps its existing inputs and completed outputs.");
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not cancel this operation."); }
  }

  async function retryOperation(jobId: string) {
    if (!selectedShot) return;
    if (jobId === selectedShot.keyframe_job_id) await createMedia("keyframe");
    else if (jobId === selectedShot.video_job_id) await createMedia("take");
  }

  async function retryProjectOperation(jobId: string) {
    if (!project) return;
    if (jobId === project.audio_plan.job_id) await generateSoundtrack();
    else if (jobId === project.render_job_id) await render();
  }

  async function saveScript() {
    if (!project || savingScript || project.script.status === "locked") return;
    setSavingScript(true); setError(null);
    try {
      setProject(await updateVideoProduction(project.production_id, {
        stage: "script",
        script: { ...project.script, raw_script: scriptDraft, status: "draft", updated_at: new Date().toISOString() },
        expected_revision: project.state_revision,
      }));
      setNotice("Working script saved. It stays editable until the team locks it.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the working script."); }
    finally { setSavingScript(false); }
  }

  async function draftScript() {
    if (!project || thinking || project.script.status === "locked") return;
    setThinking(true); setError(null);
    try {
      const next = await runVideoProductionScriptAgent(project.production_id, "Draft a timed, editable production script from the approved brief and input assets. Preserve the team’s stated constraints.");
      setProject(next); setScriptDraft(next.script.raw_script); setNotice("A structured script draft is ready for team review.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not prepare the script draft."); }
    finally { setThinking(false); }
  }

  async function lockScript() {
    if (!project || project.script.status === "locked") return;
    if (!window.confirm("Lock this script and create its editable storyboard? You can still branch later, but this revision becomes the production baseline.")) return;
    setSavingScript(true); setError(null);
    try {
      const next = await lockVideoProductionScript(project.production_id);
      setProject(next); setScriptDraft(next.script.raw_script); setWorkspaceView("storyboard"); setSelectedShotId(next.shots[0]?.id ?? null);
      setNotice("Script locked. The resulting storyboard is now ready for team editing.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not lock this script."); }
    finally { setSavingScript(false); }
  }

  async function restoreScriptCheckpoint(revisionId: string, revision: number) {
    if (!project || savingScript) return;
    if (!window.confirm(`Restore script checkpoint r${revision} as a new editable draft? The current storyboard approval will be cleared for review.`)) return;
    setSavingScript(true); setError(null);
    try {
      const next = await restoreVideoProductionScriptRevision(project.production_id, revisionId);
      setProject(next); setScriptDraft(next.script.raw_script); setWorkspaceView("script");
      setNotice(`Script checkpoint r${revision} was restored as draft r${next.script.revision}. Review and lock it before generating.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not restore this script checkpoint."); }
    finally { setSavingScript(false); }
  }

  async function addShot() {
    if (!project || savingStoryboard) return;
    setSavingStoryboard(true); setError(null);
    try {
      const next = await createVideoProductionShot(project.production_id, { title: `Shot ${String(project.shots.length + 1).padStart(2, "0")}`, purpose: "Define the story beat, visual intent and movement.", duration_seconds: 5 });
      setProject(next); setSelectedShotId(next.shots.at(-1)?.id ?? null); setWorkspaceView("storyboard"); setTab("storyboard"); setNotice("New storyboard frame added. Define it before generating media.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not add a storyboard frame."); }
    finally { setSavingStoryboard(false); }
  }

  async function moveShot(direction: -1 | 1) {
    if (!project || !selectedShot || savingStoryboard) return;
    const from = project.shots.findIndex((shot) => shot.id === selectedShot.id);
    const to = from + direction;
    if (from < 0 || to < 0 || to >= project.shots.length) return;
    const ids = project.shots.map((shot) => shot.id);
    [ids[from], ids[to]] = [ids[to], ids[from]];
    setSavingStoryboard(true); setError(null);
    try {
      setProject(await reorderVideoProductionShots(project.production_id, ids));
      setNotice("Storyboard order saved.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not reorder storyboard frames."); }
    finally { setSavingStoryboard(false); }
  }

  async function removeShot() {
    if (!project || !selectedShot || savingStoryboard) return;
    if (!window.confirm(`Delete “${selectedShot.title}”? Its media links will be removed from this storyboard.`)) return;
    setSavingStoryboard(true); setError(null);
    try {
      const next = await deleteVideoProductionShot(project.production_id, selectedShot.id);
      setProject(next); setSelectedShotId(next.shots[0]?.id ?? null); setNotice("Storyboard frame deleted.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not delete this storyboard frame."); }
    finally { setSavingStoryboard(false); }
  }

  async function saveShotPlan() {
    if (!project || !selectedShot || savingStoryboard || !shotDraft.title.trim()) return;
    const duration = Number(shotDraft.duration);
    if (!Number.isFinite(duration) || duration <= 0) { setError("Shot duration must be a positive number of seconds."); return; }
    setSavingStoryboard(true); setError(null);
    try {
      setProject(await updateVideoProductionShot(project.production_id, selectedShot.id, {
        title: shotDraft.title.trim(), purpose: shotDraft.purpose.trim(), visual: shotDraft.visual.trim(), action: shotDraft.action.trim(), duration_seconds: duration,
      }));
      setNotice("Storyboard frame saved. Existing media remains attached as an earlier decision.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save this storyboard frame."); }
    finally { setSavingStoryboard(false); }
  }

  async function saveEditDecision() {
    if (!project || !selectedShot || savingEdit) return;
    const trimIn = Number(editDraft.trimIn || "0");
    const trimOut = editDraft.trimOut.trim() ? Number(editDraft.trimOut) : null;
    if (!Number.isFinite(trimIn) || trimIn < 0 || (trimOut !== null && (!Number.isFinite(trimOut) || trimOut <= trimIn))) { setError("Use a non-negative in-point and an out-point later than the in-point."); return; }
    setSavingEdit(true); setError(null);
    try {
      setProject(await updateVideoProductionShot(project.production_id, selectedShot.id, { include_in_edit: editDraft.include, trim_in_seconds: trimIn, trim_out_seconds: trimOut }));
      setNotice(editDraft.include ? "Edit decision saved without changing the source take." : "Shot excluded from this cut; its takes remain preserved.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the edit decision."); }
    finally { setSavingEdit(false); }
  }

  async function planAudio() {
    if (!project || audioBusy) return;
    setAudioBusy(true); setError(null);
    try {
      setProject(await runVideoProductionAudioProducer(project.production_id, "Prepare a reviewable cue sheet and instrumental music direction from the locked script, selected takes and target duration. Do not generate audio yet."));
      setNotice("Audio plan is ready for review. Audio generation remains a separate team action.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not prepare the audio plan."); }
    finally { setAudioBusy(false); }
  }

  async function generateSoundtrack() {
    if (!project || audioBusy) return;
    setAudioBusy(true); setError(null);
    try {
      const job = await generateVideoProductionSoundtrack(project.production_id);
      setNotice("Soundtrack queued: " + job.title + "."); await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not queue soundtrack generation."); }
    finally { setAudioBusy(false); }
  }

  async function addOverlay() {
    if (!project || savingOverlay || !overlayDraft.text.trim()) return;
    const start = Number(overlayDraft.start || "0"); const end = overlayDraft.end.trim() ? Number(overlayDraft.end) : null;
    if (!Number.isFinite(start) || start < 0 || (end !== null && (!Number.isFinite(end) || end <= start))) { setError("Use a non-negative overlay start and an end later than the start."); return; }
    setSavingOverlay(true); setError(null);
    try {
      const overlay: VideoProductionEditOverlay = { id: `overlay_${crypto.randomUUID().slice(0, 8)}`, kind: overlayDraft.kind, text: overlayDraft.text.trim(), start_seconds: start, end_seconds: end, position: overlayDraft.position };
      setProject(await updateVideoProduction(project.production_id, { stage: "edit", edit_plan: { ...project.edit_plan, overlays: [...project.edit_plan.overlays, overlay] }, expected_revision: project.state_revision }));
      setOverlayDraft((current) => ({ ...current, text: "" })); setNotice("Deterministic overlay saved for the final render.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the overlay."); }
    finally { setSavingOverlay(false); }
  }

  async function removeOverlay(overlayId: string) {
    if (!project || savingOverlay) return;
    if (!window.confirm("Remove this deterministic overlay from the edit plan?")) return;
    setSavingOverlay(true); setError(null);
    try {
      setProject(await updateVideoProduction(project.production_id, { stage: "edit", edit_plan: { ...project.edit_plan, overlays: project.edit_plan.overlays.filter((overlay) => overlay.id !== overlayId) }, expected_revision: project.state_revision }));
      setNotice("Overlay removed from the edit plan.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not remove the overlay."); }
    finally { setSavingOverlay(false); }
  }

  async function approveStoryboard() {
    if (!project || savingStoryboard || project.storyboard_approved_at) return;
    if (!window.confirm("Approve this reviewed storyboard? Any later frame edit will require another approval before generation.")) return;
    setSavingStoryboard(true); setError(null);
    try {
      setProject(await approveVideoProductionStoryboard(project.production_id));
      setNotice("Storyboard approved. Keyframe generation is now explicitly unlocked.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not approve the storyboard."); }
    finally { setSavingStoryboard(false); }
  }

  async function createContinuityPack() {
    if (!project || designBusyId || !newPack.title.trim()) return;
    setDesignBusyId("new"); setError(null);
    try {
      setProject(await createVideoProductionDesignSheet(project.production_id, { title: newPack.title.trim(), asset_pack_type: newPack.type, purpose: newPack.purpose.trim(), design_mode: "asset" }));
      setNewPack({ title: "", type: "environment", purpose: "" }); setNotice("Continuity pack created. Review its prompt and generate candidates only when ready.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create the continuity pack."); }
    finally { setDesignBusyId(null); }
  }

  async function generateContinuityPack(sheet: VideoProductionDesignSheet) {
    if (!project || designBusyId) return;
    setDesignBusyId(sheet.id); setError(null);
    try {
      const job = await generateVideoProductionDesignSheet(project.production_id, sheet.id);
      setNotice("Design candidates queued: " + job.title + "."); await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not generate continuity candidates."); }
    finally { setDesignBusyId(null); }
  }

  async function selectContinuityCandidate(sheet: VideoProductionDesignSheet, panel: number) {
    if (!project || designBusyId) return;
    setDesignBusyId(sheet.id); setError(null);
    try {
      setProject(await selectVideoProductionDesignSheetPanel(project.production_id, sheet.id, panel));
      setNotice("Continuity candidate selected and approved for reuse.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not select this continuity candidate."); }
    finally { setDesignBusyId(null); }
  }

  if (!project) return <main className="grid min-h-[calc(100vh-72px)] place-items-center bg-white text-sm text-[#5f6673]">{error ?? <Loader2 className="size-5 animate-spin" />}</main>;

  return <main className="min-h-[calc(100vh-72px)] min-w-[1060px] bg-white text-[#101318]">
    <header className="grid h-16 grid-cols-[270px_minmax(0,1fr)_330px] items-center border-b border-[#e6e8ec] bg-white px-5">
      <div className="flex min-w-0 items-center gap-3 border-r border-[#e6e8ec] pr-5"><Link href="/video-production" className="grid size-8 place-items-center rounded-lg text-[#5f6673] hover:bg-[#f6f8fb] hover:text-[#171a20]" aria-label="Back to projects"><ArrowLeft className="size-4" /></Link><div className="min-w-0"><p className="truncate text-sm font-semibold">{project.title || "Untitled production"}</p><p className="mt-0.5 text-[11px] text-[#5f6673]">{project.video_setup.video_type || "Production draft"} · {project.aspect_ratio} · {project.target_seconds}s</p></div></div>
      <nav className="flex items-center justify-center gap-5" aria-label="Production phase">{phases.map((phase, index) => <div key={phase} className={"flex items-center gap-2 text-xs font-semibold " + (index === activePhase ? "text-[#101318]" : index < activePhase ? "text-[#2d8a64]" : "text-[#8b919c]")}><span className={"grid size-7 place-items-center rounded-full text-[11px] " + (index === activePhase ? "bg-[#171a20] text-white" : index < activePhase ? "bg-[#effaf5] text-[#2d8a64]" : "bg-[#f6f8fb] text-[#5f6673]")}>{index < activePhase ? <Check className="size-3.5" /> : index + 1}</span>{phase}</div>)}</nav>
      <div className="flex items-center justify-end gap-2 border-l border-[#e6e8ec] pl-5"><button type="button" onClick={() => void openModelSettings()} disabled={modelLoading} className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold hover:bg-[#fafbfc] disabled:opacity-45">{modelLoading ? <Loader2 className="size-3.5 animate-spin" /> : null}Models</button><button type="button" onClick={() => setWorkspaceView("script")} className={"inline-flex h-9 items-center gap-2 rounded-lg border px-3 text-xs font-semibold " + (workspaceView === "script" ? "border-[#171a20] bg-[#171a20] text-white" : "border-[#e6e8ec] bg-white hover:bg-[#fafbfc]")}>Script</button><Link href="/video-production/assets" className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold hover:bg-[#fafbfc]"><Layers3 className="size-3.5" />Assets</Link><button type="button" onClick={() => void render()} disabled={rendering || !includedCount || selectedCount !== includedCount} className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white hover:bg-[#30343c] disabled:cursor-not-allowed disabled:opacity-40">{rendering ? <Loader2 className="size-3.5 animate-spin" /> : <Film className="size-3.5" />}Render</button></div>
    </header>
    {error ? <div className="border-b border-red-200 bg-[#fff7f7] px-5 py-2 text-xs text-red-700">{error}</div> : null}
    {notice ? <div className="border-b border-[#cfe8dc] bg-[#effaf5] px-5 py-2 text-xs text-[#1d6b4d]">{notice}</div> : null}
    {editingModels && modelCapabilities && modelDraft ? <section className="border-b border-[#e6e8ec] bg-[#fafbfc] px-5 py-4"><div className="mx-auto grid max-w-[1180px] gap-4 lg:grid-cols-[minmax(0,1fr)_auto]"><div><p className="text-xs font-semibold text-[#101318]">Project model selections</p><p className="mt-1 text-[11px] leading-5 text-[#5f6673]">Only models currently configured by the platform are available. Endpoints, credentials and regions are not editable from a production.</p><div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><ProjectModelSelect label="Planning" operation="text" options={modelCapabilities.text} value={modelDraft.text} onChange={chooseModel} required /><ProjectModelSelect label="Visual development" operation="image" options={modelCapabilities.image} value={modelDraft.image} onChange={chooseModel} required /><ProjectModelSelect label="Shot generation" operation="video" options={modelCapabilities.video} value={modelDraft.video} onChange={chooseModel} required /><ProjectModelSelect label="Soundtrack" operation="audio" options={modelCapabilities.audio} value={modelDraft.audio} onChange={chooseModel} /></div></div><div className="flex items-end gap-2"><button type="button" onClick={() => setEditingModels(false)} disabled={modelSaving} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold hover:bg-[#f6f8fb] disabled:opacity-45">Cancel</button><button type="button" onClick={() => void saveModelSettings()} disabled={modelSaving} className="h-9 rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white disabled:opacity-45">{modelSaving ? "Saving…" : "Save models"}</button></div></div></section> : null}

    <div className="grid min-h-[calc(100vh-136px)] grid-cols-[250px_minmax(0,1fr)_330px]">
      <aside className="border-r border-[#e6e8ec] bg-[#fafbfc] p-4"><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Project workspace</p><div className="mt-4 space-y-1">{[{ icon: Clapperboard, label: "Overview", detail: "Project details and settings" }, { icon: ImagePlus, label: "Inputs", detail: project.reference_asset_ids.length + " attached assets" }].map((item) => { const Icon = item.icon; return <div key={item.label} className="flex items-start gap-3 rounded-lg px-3 py-2.5 text-[#5f6673]"><Icon className="mt-0.5 size-4" /><div><p className="text-xs font-semibold text-[#171a20]">{item.label}</p><p className="mt-0.5 text-[11px]">{item.detail}</p></div></div>; })}</div><button type="button" onClick={() => setWorkspaceView("assets")} className={"mt-3 flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left " + (workspaceView === "assets" ? "bg-white shadow-sm ring-1 ring-[#d7dbe2]" : "text-[#5f6673] hover:bg-white")}><Layers3 className="mt-0.5 size-4" /><span><span className="block text-xs font-semibold text-[#171a20]">Visual continuity</span><span className="mt-0.5 block text-[11px] text-[#5f6673]">{project.design_bible.asset_packs.length} reusable states</span></span></button><button type="button" onClick={() => setWorkspaceView("script")} className={"mt-3 flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left " + (workspaceView === "script" ? "bg-white shadow-sm ring-1 ring-[#d7dbe2]" : "text-[#5f6673] hover:bg-white")}><MessageSquare className="mt-0.5 size-4" /><span><span className="block text-xs font-semibold text-[#171a20]">Working script</span><span className="mt-0.5 block text-[11px] text-[#5f6673]">{project.script.status === "locked" ? "Locked baseline" : "Draft — needs team lock"}</span></span></button>
        <div className="mt-5 border-t border-[#e6e8ec] pt-5"><div className="flex items-center justify-between"><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Storyboard</p><button type="button" onClick={() => void addShot()} disabled={savingStoryboard || project.script.status !== "locked"} title={project.script.status === "locked" ? "Add storyboard frame" : "Lock the script before adding frames"} className="rounded-md border border-[#e6e8ec] bg-white px-2 py-1 text-[10px] font-semibold hover:bg-[#fafbfc] disabled:cursor-not-allowed disabled:opacity-40">+ Add</button></div><p className="mt-1 text-[11px] text-[#5f6673]">{project.shots.length} shots · {project.script.status === "locked" ? "editable plan" : "lock script to begin"}</p><div className="mt-3 space-y-1">{project.shots.length ? project.shots.map((shot) => <button key={shot.id} type="button" onClick={() => { setWorkspaceView("storyboard"); setSelectedShotId(shot.id); setTab("storyboard"); }} className={"flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition " + (workspaceView === "storyboard" && shot.id === selectedShot?.id ? "bg-white shadow-sm ring-1 ring-[#d7dbe2]" : "hover:bg-white")}><span className={"grid size-7 shrink-0 place-items-center rounded-md text-[10px] font-semibold " + (workspaceView === "storyboard" && shot.id === selectedShot?.id ? "bg-[#171a20] text-white" : "bg-[#f0f2f5] text-[#5f6673]")}>{String(shot.order).padStart(2, "0")}</span><span className="min-w-0"><span className="block truncate text-xs font-semibold">{shot.title}</span><span className="mt-0.5 block truncate text-[10px] text-[#5f6673]">{shotState(shot)}</span></span></button>) : <button type="button" onClick={() => setWorkspaceView("script")} className="w-full rounded-lg border border-dashed border-[#d7dbe2] bg-white p-3 text-left text-xs leading-5 text-[#5f6673] hover:border-[#171a20] hover:text-[#171a20]">Review and lock script first</button>}</div></div>
      </aside>

      <section className="min-w-0 overflow-y-auto bg-white p-7">{workspaceView === "script" ? <ScriptPanel project={project} draft={scriptDraft} saving={savingScript} thinking={thinking} onChange={setScriptDraft} onDraft={() => void draftScript()} onSave={() => void saveScript()} onLock={() => void lockScript()} onRestore={(revisionId, revision) => void restoreScriptCheckpoint(revisionId, revision)} /> : workspaceView === "assets" ? <DesignBoard project={project} assets={assetById} busyId={designBusyId} newPack={newPack} onPackChange={setNewPack} onCreate={() => void createContinuityPack()} onGenerate={(sheet) => void generateContinuityPack(sheet)} onSelect={(sheet, panel) => void selectContinuityCandidate(sheet, panel)} /> : !selectedShot ? <EmptyStoryboard project={project} thinking={thinking} onCreate={() => setWorkspaceView("script")} /> : <><div className="flex items-start justify-between gap-4"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Shot {String(selectedShot.order).padStart(2, "0")} · {selectedShot.duration_seconds}s</p><h1 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em]">{selectedShot.title}</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#5f6673]">{selectedShot.purpose || "Define the visual, motion and continuity before generating a take."}</p></div><div className="flex gap-2"><button type="button" onClick={() => setSelectedShotId(project.shots[Math.max(0, selectedIndex - 1)]?.id ?? selectedShot.id)} disabled={selectedIndex <= 0} className="grid size-9 place-items-center rounded-lg border border-[#e6e8ec] bg-white text-[#5f6673] disabled:opacity-30"><ChevronLeft className="size-4" /></button><button type="button" onClick={() => setSelectedShotId(project.shots[Math.min(project.shots.length - 1, selectedIndex + 1)]?.id ?? selectedShot.id)} disabled={selectedIndex >= project.shots.length - 1} className="grid size-9 place-items-center rounded-lg border border-[#e6e8ec] bg-white text-[#5f6673] disabled:opacity-30"><ChevronRight className="size-4" /></button></div></div>
        <div className="mt-5 flex items-center justify-between rounded-xl border border-[#e6e8ec] bg-[#fafbfc] px-4 py-3"><p className="text-[11px] text-[#5f6673]">{storyboardApproved ? "Approved plan. Any frame change revokes generation approval until reviewed again." : "Plan controls save immediately. Approve the complete plan before generating media."}</p><div className="flex gap-2"><button type="button" onClick={() => void approveStoryboard()} disabled={savingStoryboard || storyboardApproved} className="h-8 rounded-lg bg-[#171a20] px-2.5 text-[11px] font-semibold text-white disabled:opacity-40">{storyboardApproved ? "Approved" : "Approve plan"}</button><button type="button" onClick={() => void moveShot(-1)} disabled={savingStoryboard || selectedIndex <= 0} className="h-8 rounded-lg border border-[#e6e8ec] bg-white px-2.5 text-[11px] font-semibold disabled:opacity-40">Move earlier</button><button type="button" onClick={() => void moveShot(1)} disabled={savingStoryboard || selectedIndex >= project.shots.length - 1} className="h-8 rounded-lg border border-[#e6e8ec] bg-white px-2.5 text-[11px] font-semibold disabled:opacity-40">Move later</button><button type="button" onClick={() => void removeShot()} disabled={savingStoryboard} className="h-8 rounded-lg border border-[#f1cccc] bg-white px-2.5 text-[11px] font-semibold text-[#b43b3b] hover:bg-[#fff7f7] disabled:opacity-40">Delete</button></div></div>
        <div className="mt-6 flex gap-6 border-b border-[#e6e8ec]">{(["storyboard", "versions", "review"] as Tab[]).map((item) => <button key={item} type="button" onClick={() => setTab(item)} className={"border-b-2 px-1 pb-3 text-xs font-semibold capitalize transition " + (tab === item ? "border-[#171a20] text-[#171a20]" : "border-transparent text-[#5f6673] hover:text-[#171a20]")}>{item === "review" ? "Take review" : item}</button>)}</div>
        {tab === "storyboard" ? <><ShotPlanEditor draft={shotDraft} saving={savingStoryboard} onChange={setShotDraft} onSave={() => void saveShotPlan()} /><StoryboardPanel asset={selectedFrame} shot={selectedShot} busy={busyShotId === selectedShot.id} approved={storyboardApproved} onGenerate={() => void createMedia("keyframe")} onGenerateTakes={() => void createMedia("take")} /></> : <><TakesPanel shot={selectedShot} tab={tab} assets={assetById} busy={busyShotId === selectedShot.id} thinking={thinking} editDraft={editDraft} savingEdit={savingEdit} onEditChange={setEditDraft} onSaveEdit={() => void saveEditDecision()} onSelect={selectTake} onReview={review} />{tab === "review" ? <OverlayEditor overlays={project.edit_plan.overlays} draft={overlayDraft} saving={savingOverlay} onChange={setOverlayDraft} onAdd={() => void addOverlay()} onRemove={(overlayId) => void removeOverlay(overlayId)} /> : null}</>}
        <OperationStatus jobIds={selectedOperationIds} jobStates={jobStates} onCancel={(jobId) => void cancelOperation(jobId)} onRetry={(jobId) => void retryOperation(jobId)} />
        <OperationStatus jobIds={projectOperationIds} jobStates={jobStates} onCancel={(jobId) => void cancelOperation(jobId)} onRetry={(jobId) => void retryProjectOperation(jobId)} title="Project operations" />
        <ProjectActivity project={project} events={activityEvents} loading={activityLoading} error={activityError} onRetry={() => setActivityReload((value) => value + 1)} />
      </>}</section>

      <aside className="flex min-h-0 flex-col border-l border-[#e6e8ec] bg-[#fafbfc]"><div className="flex items-center gap-2 border-b border-[#e6e8ec] px-5 py-4"><span className="grid size-7 place-items-center rounded-lg bg-[#171a20] text-white"><Bot className="size-4" /></span><div><p className="text-sm font-semibold">Production assistant</p><p className="text-[11px] text-[#5f6673]">Contextual, never silent</p></div></div><div className="min-h-0 flex-1 overflow-y-auto p-5"><div className="rounded-xl border border-[#e6e8ec] bg-white p-3 text-xs leading-5 text-[#5f6673]">Brief, approved assets, shot decisions and selected takes remain linked. Generation and final selection require explicit team action.</div><p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Suggestions</p><div className="mt-2 space-y-2">{["Improve this shot", "Check continuity", "Plan next shot"].map((suggestion) => <button key={suggestion} type="button" onClick={() => void copilot(suggestion + (selectedShot ? " for shot " + selectedShot.order + "." : "."))} className="flex w-full items-center justify-between rounded-lg border border-[#e6e8ec] bg-white px-3 py-2.5 text-left text-xs font-medium hover:border-[#d7dbe2]"><span>{suggestion}</span><ArrowRight className="size-3.5 text-[#5f6673]" /></button>)}</div><section className="mt-5 rounded-xl border border-[#e6e8ec] bg-white p-3"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold">Soundtrack plan</p><p className="mt-1 text-[11px] leading-5 text-[#5f6673]">{project.audio_plan.music_prompt || "Prepare a cue sheet before generating any soundtrack."}</p></div><span className="rounded-full bg-[#f6f8fb] px-2 py-1 text-[10px] font-semibold text-[#5f6673]">{project.audio_plan.status}</span></div><p className="mt-3 text-[11px] text-[#5f6673]">{project.audio_plan.cue_sheet.length} cues · {project.audio_plan.bpm ? project.audio_plan.bpm + " BPM" : "BPM not set"}</p><div className="mt-3 flex gap-2"><button type="button" onClick={() => void planAudio()} disabled={audioBusy || project.script.status !== "locked"} className="h-8 flex-1 rounded-lg border border-[#e6e8ec] px-2 text-[10px] font-semibold hover:bg-[#fafbfc] disabled:opacity-40">Plan audio</button><button type="button" onClick={() => void generateSoundtrack()} disabled={audioBusy || !project.audio_plan.music_prompt} className="h-8 flex-1 rounded-lg bg-[#171a20] px-2 text-[10px] font-semibold text-white disabled:opacity-40">{audioBusy ? "Working…" : "Generate"}</button></div></section><p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Conversation</p><div className="mt-3 space-y-3">{project.conversation.slice(-4).map((item, index) => <div key={item.created_at + index} className={item.role === "user" ? "ml-8" : "mr-5"}><p className="mb-1 text-[10px] font-semibold text-[#5f6673]">{item.role === "user" ? "You" : "Linglong"}</p><div className={"rounded-xl p-3 text-xs leading-5 " + (item.role === "user" ? "bg-[#eaf1ff] text-[#174dba]" : "bg-white text-[#5f6673]")}>{item.text}</div></div>)}</div></div><div className="border-t border-[#e6e8ec] p-4"><textarea value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void copilot(message); setMessage(""); } }} placeholder="Ask about this shot…" className="min-h-[76px] w-full resize-none rounded-lg border border-[#e6e8ec] bg-white p-3 text-xs outline-none placeholder:text-[#8b919c] focus:border-[#171a20]" /><button type="button" onClick={() => { void copilot(message); setMessage(""); }} disabled={!message.trim() || thinking} className="mt-2 inline-flex h-8 w-full items-center justify-center gap-2 rounded-lg bg-[#171a20] text-xs font-semibold text-white disabled:opacity-40"><Send className="size-3.5" />Send</button></div></aside>
    </div>
  </main>;
}

function ScriptPanel({ project, draft, saving, thinking, onChange, onDraft, onSave, onLock, onRestore }: { project: VideoProduction; draft: string; saving: boolean; thinking: boolean; onChange: (value: string) => void; onDraft: () => void; onSave: () => void; onLock: () => void; onRestore: (revisionId: string, revision: number) => void }) {
  const locked = project.script.status === "locked";
  return <div className="mx-auto max-w-4xl"><div className="flex items-start justify-between gap-6"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Script · revision {project.script.revision}</p><h1 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em]">Working script</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#5f6673]">This is the human review point. Draft with the assistant, make your changes, then lock the version that will seed the editable storyboard.</p></div><span className={"rounded-full px-3 py-1 text-[11px] font-semibold " + (locked ? "bg-[#effaf5] text-[#1d6b4d]" : "bg-[#f6f8fb] text-[#5f6673]")}>{locked ? "Locked baseline" : "Editable draft"}</span></div><div className="mt-7 rounded-2xl border border-[#e6e8ec] bg-white p-5"><div className="flex items-center justify-between gap-4"><div><p className="text-xs font-semibold">Timed production script</p><p className="mt-1 text-[11px] text-[#5f6673]">Structured scenes: {project.script.scenes.length} · Beats: {project.script.beats.length}</p></div><button type="button" onClick={onDraft} disabled={thinking || locked} className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold hover:bg-[#fafbfc] disabled:opacity-40">{thinking ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}Restructure draft</button></div><textarea value={draft} onChange={(event) => onChange(event.target.value)} readOnly={locked} placeholder="Use Restructure draft to turn the saved brief into a timed production script, then refine the working copy here." className="mt-5 min-h-[420px] w-full resize-y rounded-xl border border-[#e6e8ec] bg-[#fafbfc] p-4 font-mono text-xs leading-6 text-[#101318] outline-none placeholder:text-[#8b919c] focus:border-[#171a20] read-only:cursor-default read-only:bg-white" /><div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[#e6e8ec] pt-4"><p className="max-w-xl text-[11px] leading-5 text-[#5f6673]">{locked ? "This baseline has already produced a storyboard. Create a safe branch before changing its production logic." : "After a manual text edit, save it, then use Restructure draft before locking. The server blocks lock when the structured scenes no longer match this text."}</p><div className="flex gap-2">{!locked ? <><button type="button" onClick={onSave} disabled={saving || !draft.trim()} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold hover:bg-[#fafbfc] disabled:opacity-40">{saving ? "Saving…" : "Save draft"}</button><button type="button" onClick={onLock} disabled={saving || !draft.trim() || !project.script.scenes.length} className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white disabled:opacity-40"><Check className="size-3.5" />Lock & create storyboard</button></> : null}</div></div></div><div className="mt-5 grid gap-4 md:grid-cols-3"><PromptCard label="Creative goal" value={project.script.creative_goal || "Set from the approved brief."} /><PromptCard label="Audience" value={project.script.audience || "Set from the approved brief."} /><PromptCard label="Production guardrails" value={project.script.risks.length ? project.script.risks.join(" · ") : "No additional risks recorded."} /></div>{project.script_revisions.length ? <section className="mt-5 rounded-xl border border-[#e6e8ec] bg-[#fafbfc] p-4"><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Revision receipts</p><p className="mt-1 text-[11px] leading-5 text-[#5f6673]">Restoring a checkpoint creates a new editable draft and clears storyboard approval; it never overwrites the current baseline in place.</p><div className="mt-3 space-y-2">{project.script_revisions.slice(-4).reverse().map((revision) => <div key={revision.revision_id} className="flex items-center justify-between gap-3 border-t border-[#e6e8ec] pt-2 text-xs first:border-t-0 first:pt-0"><span><span className="font-semibold text-[#171a20]">r{revision.revision} · {revision.status}</span><span className="ml-2 text-[#5f6673]">{revision.reason}</span></span><span className="flex shrink-0 items-center gap-2"><span className="text-[10px] text-[#8b919c]">{revision.scene_count} scenes · {revision.beat_count} beats</span>{revision.script ? <button type="button" onClick={() => onRestore(revision.revision_id, revision.revision)} disabled={saving} className="rounded-md border border-[#d7dbe2] bg-white px-2 py-1 text-[10px] font-semibold text-[#171a20] hover:border-[#171a20] disabled:cursor-not-allowed disabled:opacity-40">Restore as draft</button> : <span className="text-[10px] text-[#8b919c]">Legacy receipt</span>}</span></div>)}</div></section> : null}</div>;
}

function DesignBoard({ project, assets, busyId, newPack, onPackChange, onCreate, onGenerate, onSelect }: { project: VideoProduction; assets: Map<string, AssetSummary>; busyId: string | null; newPack: { title: string; type: VideoProductionDesignSheet["asset_pack_type"]; purpose: string }; onPackChange: (value: { title: string; type: VideoProductionDesignSheet["asset_pack_type"]; purpose: string }) => void; onCreate: () => void; onGenerate: (sheet: VideoProductionDesignSheet) => void; onSelect: (sheet: VideoProductionDesignSheet, panel: number) => void }) {
  const packs = project.design_bible.asset_packs;
  return <div className="mx-auto max-w-5xl"><div className="flex items-start justify-between gap-6"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Visual continuity</p><h1 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em]">Reusable production states</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#5f6673]">Approved character, environment, prop, UI, lighting and transition states are reusable production inputs.</p></div><span className="rounded-full bg-[#f6f8fb] px-3 py-1 text-[11px] font-semibold text-[#5f6673]">{project.design_bible.status}</span></div><section className="mt-6 rounded-xl border border-[#e6e8ec] bg-[#fafbfc] p-4"><p className="text-xs font-semibold">Create continuity pack</p><div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_150px_minmax(0,1fr)_auto]"><input value={newPack.title} onChange={(event) => onPackChange({ ...newPack, title: event.target.value })} placeholder="Pack name" className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs outline-none focus:border-[#171a20]" /><select value={newPack.type} onChange={(event) => onPackChange({ ...newPack, type: event.target.value as VideoProductionDesignSheet["asset_pack_type"] })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs outline-none focus:border-[#171a20]"><option value="character">Character</option><option value="environment">Environment</option><option value="prop">Prop</option><option value="ui">UI</option><option value="lighting">Lighting</option><option value="transition">Transition</option></select><input value={newPack.purpose} onChange={(event) => onPackChange({ ...newPack, purpose: event.target.value })} placeholder="Purpose" className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs outline-none focus:border-[#171a20]" /><button type="button" onClick={onCreate} disabled={busyId !== null || !newPack.title.trim()} className="h-9 rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white disabled:opacity-40">Create</button></div></section><div className="mt-6 grid gap-4 md:grid-cols-2">{packs.map((pack) => { const selected = assets.get(pack.selected_asset_id ?? "") || assets.get(pack.approved_asset_ids[0] ?? ""); const busy = busyId === pack.id; return <article key={pack.id} className="overflow-hidden rounded-2xl border border-[#e6e8ec] bg-white"><div className="grid min-h-36 grid-cols-[132px_minmax(0,1fr)]"><div className="grid place-items-center bg-[#20242b]">{selected ? <MediaPreview asset={selected} className="size-full object-cover" /> : <Layers3 className="size-5 text-white/60" />}</div><div className="p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">{pack.title}</p><p className="mt-1 text-[11px] text-[#5f6673]">{pack.asset_pack_type}</p></div><span className="rounded-full bg-[#f6f8fb] px-2 py-1 text-[10px] font-semibold text-[#5f6673]">{pack.status}</span></div><p className="mt-3 text-xs leading-5 text-[#5f6673]">{pack.purpose || "No purpose recorded."}</p></div></div><div className="border-t border-[#e6e8ec] bg-[#fafbfc] px-4 py-3"><p className="text-[11px] text-[#5f6673]">{pack.failure_reason || `${pack.scene_ids.length} linked scenes · ${pack.approved_asset_ids.length} approved states`}</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => onGenerate(pack)} disabled={busy || pack.status === "generating"} className="h-8 rounded-lg border border-[#e6e8ec] bg-white px-2.5 text-[10px] font-semibold disabled:opacity-40">{pack.status === "failed" ? "Retry generation" : "Generate candidates"}</button>{pack.grid_asset_id ? [0, 1, 2, 3].map((panel) => <button key={panel} type="button" onClick={() => onSelect(pack, panel)} disabled={busy} className={"h-8 rounded-lg border px-2.5 text-[10px] font-semibold disabled:opacity-40 " + (pack.selected_panel === panel ? "border-[#171a20] bg-[#171a20] text-white" : "border-[#e6e8ec] bg-white")}>Use {String.fromCharCode(65 + panel)}</button>) : null}</div></div></article>; })}</div>{!packs.length ? <div className="mt-5 rounded-xl border border-dashed border-[#d7dbe2] p-6 text-center text-xs text-[#5f6673]">Create a reusable state before keyframe generation.</div> : null}</div>;
}

function EmptyStoryboard({ project, thinking, onCreate }: { project: VideoProduction; thinking: boolean; onCreate: () => void }) {
  return <div className="grid min-h-[600px] place-items-center"><div className="max-w-md text-center"><span className="mx-auto grid size-12 place-items-center rounded-2xl bg-[#f6f8fb] text-[#171a20]"><Clapperboard className="size-5" /></span><h1 className="mt-5 font-display text-3xl font-semibold tracking-[-0.04em]">Build the first storyboard.</h1><p className="mt-3 text-sm leading-6 text-[#5f6673]">Turn the saved brief and approved input assets into an editable shot plan. No media generation starts in this step.</p><button type="button" onClick={onCreate} disabled={thinking} className="mt-6 inline-flex h-10 items-center gap-2 rounded-lg bg-[#171a20] px-4 text-xs font-semibold text-white disabled:opacity-40">{thinking ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}Create shot plan</button><p className="mt-4 text-[11px] text-[#5f6673]">{project.script.status === "locked" ? "Script is locked." : "Script remains a draft until the team explicitly approves it."}</p></div></div>;
}

function ShotPlanEditor({ draft, saving, onChange, onSave }: { draft: { title: string; purpose: string; visual: string; action: string; duration: string }; saving: boolean; onChange: (draft: { title: string; purpose: string; visual: string; action: string; duration: string }) => void; onSave: () => void }) {
  return <details className="mt-5 rounded-xl border border-[#e6e8ec] bg-[#fafbfc] p-4"><summary className="cursor-pointer list-none text-xs font-semibold"><span className="inline-flex items-center gap-2">Edit storyboard frame <span className="text-[11px] font-normal text-[#5f6673]">Title, intent, visual and movement</span></span></summary><div className="mt-4 grid gap-3"><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Title<input value={draft.title} onChange={(event) => onChange({ ...draft, title: event.target.value })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-medium text-[#101318] outline-none focus:border-[#171a20]" /></label><div className="grid gap-3 md:grid-cols-[130px_minmax(0,1fr)]"><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Duration (seconds)<input inputMode="decimal" value={draft.duration} onChange={(event) => onChange({ ...draft, duration: event.target.value })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-medium text-[#101318] outline-none focus:border-[#171a20]" /></label><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Story purpose<input value={draft.purpose} onChange={(event) => onChange({ ...draft, purpose: event.target.value })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-medium text-[#101318] outline-none focus:border-[#171a20]" /></label></div><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Visual<textarea value={draft.visual} onChange={(event) => onChange({ ...draft, visual: event.target.value })} className="min-h-20 resize-y rounded-lg border border-[#e6e8ec] bg-white p-3 text-xs font-medium text-[#101318] outline-none focus:border-[#171a20]" /></label><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Motion and action<textarea value={draft.action} onChange={(event) => onChange({ ...draft, action: event.target.value })} className="min-h-20 resize-y rounded-lg border border-[#e6e8ec] bg-white p-3 text-xs font-medium text-[#101318] outline-none focus:border-[#171a20]" /></label></div><div className="mt-4 flex justify-end border-t border-[#e6e8ec] pt-3"><button type="button" onClick={onSave} disabled={saving || !draft.title.trim()} className="h-9 rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white disabled:opacity-40">{saving ? "Saving…" : "Save frame"}</button></div></details>;
}

function StoryboardPanel({ asset, shot, busy, approved, onGenerate, onGenerateTakes }: { asset?: AssetSummary; shot: VideoProductionShot; busy: boolean; approved: boolean; onGenerate: () => void; onGenerateTakes: () => void }) {
  return <><article className="mt-5 overflow-hidden rounded-2xl border border-[#e6e8ec] bg-white"><div className="grid min-h-[380px] grid-cols-[minmax(0,1fr)_280px]"><div className="grid min-h-[380px] place-items-center bg-[#20242b]"><MediaPreview asset={asset} className="size-full max-h-[540px] object-contain" />{!asset ? <div className="text-center text-white/70"><ImagePlus className="mx-auto size-7" /><p className="mt-3 text-xs font-semibold">No keyframe yet</p><p className="mt-1 text-[11px] text-white/50">Lock the composition before animation.</p></div> : null}</div><dl className="divide-y divide-[#e6e8ec] bg-[#fafbfc] p-5 text-xs"><div className="pb-4"><dt className="font-semibold uppercase tracking-[0.12em] text-[#5f6673]">Camera / framing</dt><dd className="mt-2 leading-5 text-[#101318]">{shot.camera || "Not set"}</dd></div><div className="py-4"><dt className="font-semibold uppercase tracking-[0.12em] text-[#5f6673]">Continuity</dt><dd className="mt-2 leading-5 text-[#101318]">{shot.continuity || "Not set"}</dd></div><div className="pt-4"><dt className="font-semibold uppercase tracking-[0.12em] text-[#5f6673]">Audio cue</dt><dd className="mt-2 leading-5 text-[#101318]">{shot.audio_cue || "Not set"}</dd></div></dl></div><div className="flex items-center justify-between border-t border-[#e6e8ec] px-5 py-4"><span className="text-xs text-[#5f6673]">{approved ? shotState(shot) : "Approve the storyboard to unlock generation"}</span><div className="flex gap-2"><button type="button" onClick={onGenerate} disabled={!approved || busy} className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#e6e8ec] px-3 text-xs font-semibold hover:bg-[#fafbfc] disabled:opacity-40"><Wand2 className="size-3.5" />Generate keyframe</button><button type="button" onClick={onGenerateTakes} disabled={!approved || !shot.keyframe_asset_id || busy} className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white disabled:opacity-40"><Play className="size-3.5" />Generate takes</button></div></div></article><div className="mt-4 grid gap-4 lg:grid-cols-2"><PromptCard label="Image prompt" value={shot.visual || "Use the creative direction to define a shot-specific image prompt."} /><PromptCard label="Motion prompt" value={shot.action || shot.veo_prompt || "Describe the movement and camera action before generating."} /></div></>;
}

function PromptCard({ label, value }: { label: string; value: string }) {
  return <article className="rounded-xl border border-[#e6e8ec] bg-white p-4"><p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#5f6673]">{label}</p><p className="mt-3 text-xs leading-5 text-[#101318]">{value}</p></article>;
}

function OperationStatus({ jobIds, jobStates, onCancel, onRetry, title = "Shot operations" }: { jobIds: string[]; jobStates: Record<string, JobSummary | null>; onCancel: (jobId: string) => void; onRetry: (jobId: string) => void; title?: string }) {
  if (!jobIds.length) return null;
  return <section className="mt-4 rounded-xl border border-[#e6e8ec] bg-[#fafbfc] p-4"><div className="flex items-center justify-between"><p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#5f6673]">{title}</p><span className="text-[11px] text-[#5f6673]">Refresh-safe status</span></div><div className="mt-3 space-y-2">{jobIds.map((jobId) => { const job = jobStates[jobId]; const active = job?.status === "running" || job?.status === "queued"; const failed = job?.status === "failed"; return <div key={jobId} className="flex items-center gap-3 rounded-lg border border-[#e6e8ec] bg-white px-3 py-2.5"><span className={"size-2 rounded-full " + (failed ? "bg-[#d04444]" : job?.status === "completed" ? "bg-[#2d8a64]" : "bg-[#356fec]")} /><div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold">{job?.title || "Loading operation…"}</p><p className={"mt-0.5 text-[11px] " + (failed ? "text-[#b43b3b]" : "text-[#5f6673]")}>{job ? (job.message || job.status + " · " + job.progress + "%") : jobId}</p></div>{active ? <button type="button" onClick={() => onCancel(jobId)} className="rounded-md border border-[#e6e8ec] px-2 py-1 text-[10px] font-semibold hover:bg-[#fafbfc]">Cancel</button> : failed ? <button type="button" onClick={() => onRetry(jobId)} className="rounded-md border border-[#171a20] px-2 py-1 text-[10px] font-semibold hover:bg-[#fafbfc]">Retry</button> : null}</div>; })}</div></section>;
}

function OverlayEditor({ overlays, draft, saving, onChange, onAdd, onRemove }: { overlays: VideoProductionEditOverlay[]; draft: { kind: VideoProductionEditOverlay["kind"]; text: string; start: string; end: string; position: VideoProductionEditOverlay["position"] }; saving: boolean; onChange: (draft: { kind: VideoProductionEditOverlay["kind"]; text: string; start: string; end: string; position: VideoProductionEditOverlay["position"] }) => void; onAdd: () => void; onRemove: (overlayId: string) => void }) {
  return <section className="mt-5 rounded-xl border border-[#e6e8ec] bg-white p-4"><div><p className="text-xs font-semibold">Captions & deterministic overlays</p><p className="mt-1 text-[11px] leading-5 text-[#5f6673]">Add text, logo or store-badge layers to the edit plan. These are composited during rendering; they are never delegated to the video model.</p></div>{overlays.length ? <div className="mt-4 space-y-2">{overlays.map((overlay) => <div key={overlay.id} className="flex items-center justify-between gap-3 rounded-lg border border-[#e6e8ec] bg-[#fafbfc] px-3 py-2.5"><div className="min-w-0"><p className="truncate text-xs font-semibold">{overlay.kind}: {overlay.text || "Asset overlay"}</p><p className="mt-1 text-[10px] text-[#5f6673]">{overlay.position} · {overlay.start_seconds}s–{overlay.end_seconds ?? "end"}</p></div><button type="button" onClick={() => onRemove(overlay.id)} disabled={saving} className="text-[10px] font-semibold text-[#b43b3b] disabled:opacity-40">Remove</button></div>)}</div> : null}<div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Layer kind<select value={draft.kind} onChange={(event) => onChange({ ...draft, kind: event.target.value as VideoProductionEditOverlay["kind"] })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs text-[#101318] outline-none focus:border-[#171a20]"><option value="subtitle">Subtitle</option><option value="logo">Logo text</option><option value="store_badges">Store badge text</option></select></label><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Position<select value={draft.position} onChange={(event) => onChange({ ...draft, position: event.target.value as VideoProductionEditOverlay["position"] })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs text-[#101318] outline-none focus:border-[#171a20]"><option value="bottom_center">Bottom center</option><option value="top_left">Top left</option><option value="top_right">Top right</option><option value="center">Center</option></select></label><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Start (seconds)<input inputMode="decimal" value={draft.start} onChange={(event) => onChange({ ...draft, start: event.target.value })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs text-[#101318] outline-none focus:border-[#171a20]" /></label><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">End (optional)<input inputMode="decimal" value={draft.end} onChange={(event) => onChange({ ...draft, end: event.target.value })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs text-[#101318] outline-none focus:border-[#171a20]" /></label></div><label className="mt-3 grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Text<textarea value={draft.text} onChange={(event) => onChange({ ...draft, text: event.target.value })} placeholder="Exact approved copy" className="min-h-20 resize-y rounded-lg border border-[#e6e8ec] bg-white p-3 text-xs text-[#101318] outline-none focus:border-[#171a20]" /></label><div className="mt-3 flex justify-end"><button type="button" onClick={onAdd} disabled={saving || !draft.text.trim()} className="h-8 rounded-lg bg-[#171a20] px-3 text-[11px] font-semibold text-white disabled:opacity-40">{saving ? "Saving…" : "Add overlay"}</button></div></section>;
}

function ProjectActivity({ project, events, loading, error, onRetry }: { project: VideoProduction; events: VideoProductionEvent[]; loading: boolean; error: string | null; onRetry: () => void }) {
  const selected = project.shots.filter((shot) => shot.selected_video_asset_id).length;
  return <section className="mt-4 rounded-xl border border-[#e6e8ec] bg-[#fafbfc] p-4"><div className="flex items-center justify-between"><p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#5f6673]">Project trace</p><span className="text-[11px] text-[#5f6673]">Revision {project.state_revision}</span></div><div className="mt-3 grid gap-2 sm:grid-cols-3"><PromptCard label="Assets" value={`${project.asset_links.length} attached · ${project.asset_links.filter((link) => link.rights_note).length} rights notes`} /><PromptCard label="Selections" value={`${selected}/${project.shots.length} takes selected`} /><PromptCard label="Plan" value={project.storyboard_approved_at ? "Storyboard approved" : "Approval pending"} /></div><div className="mt-3 rounded-lg border border-[#e6e8ec] bg-white p-3"><div className="flex items-center justify-between gap-3"><p className="text-[11px] font-semibold text-[#5f6673]">Durable project activity</p>{loading ? <Loader2 className="size-3 animate-spin text-[#5f6673]" /> : null}</div>{error ? <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-[#b42318]"><span>{error}</span><button type="button" onClick={onRetry} className="font-semibold underline">Retry</button></div> : null}{!loading && !error && !events.length ? <p className="mt-2 text-[11px] text-[#5f6673]">No persisted activity yet.</p> : null}<div className="mt-2 space-y-1">{events.slice(0, 5).map((event) => <p key={event.event_id} className="text-[11px] leading-5 text-[#101318]">r{event.state_revision} · {event.summary} <span className="text-[#5f6673]">({event.actor_user_id === "system" ? "system" : event.actor_user_id})</span></p>)}</div></div></section>;
}

function TakesPanel({ shot, tab, assets, busy, thinking, editDraft, savingEdit, onEditChange, onSaveEdit, onSelect, onReview }: { shot: VideoProductionShot; tab: Tab; assets: Map<string, AssetSummary>; busy: boolean; thinking: boolean; editDraft: { include: boolean; trimIn: string; trimOut: string }; savingEdit: boolean; onEditChange: (value: { include: boolean; trimIn: string; trimOut: string }) => void; onSaveEdit: () => void; onSelect: (assetId: string) => void; onReview: () => void }) {
  return <div className="mt-5">{shot.video_asset_ids.length ? <div className="grid gap-3 lg:grid-cols-2">{shot.video_asset_ids.map((takeId, index) => <article key={takeId} className={"overflow-hidden rounded-xl border bg-white " + (takeId === shot.selected_video_asset_id ? "border-[#171a20]" : "border-[#e6e8ec]")}><div className="aspect-video bg-[#20242b]"><MediaPreview asset={assets.get(takeId)} className="size-full object-contain" /></div><div className="flex items-center justify-between p-4"><div><p className="text-sm font-semibold">Take {index + 1}</p><p className="mt-1 text-xs text-[#5f6673]">{takeId === shot.selected_video_asset_id ? "Selected for edit" : "Available for review"}</p></div><button type="button" onClick={() => onSelect(takeId)} disabled={busy} className={"h-8 rounded-lg px-3 text-xs font-semibold " + (takeId === shot.selected_video_asset_id ? "bg-[#171a20] text-white" : "border border-[#e6e8ec] hover:bg-[#fafbfc]")}>{takeId === shot.selected_video_asset_id ? "Selected" : "Select take"}</button></div></article>)}</div> : <div className="rounded-xl border border-dashed border-[#d7dbe2] bg-[#fafbfc] p-10 text-center text-sm text-[#5f6673]">Generate a take from an approved keyframe first.</div>}{shot.selected_video_asset_id ? <section className="mt-4 rounded-xl border border-[#e6e8ec] bg-[#fafbfc] p-4"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold">Edit decision</p><p className="mt-1 text-[11px] leading-5 text-[#5f6673]">Trims are non-destructive. Excluding a shot retains its selected take and history.</p></div><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={editDraft.include} onChange={(event) => onEditChange({ ...editDraft, include: event.target.checked })} className="size-3.5 accent-[#171a20]" />Include in this cut</label></div><div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Trim in (seconds)<input inputMode="decimal" value={editDraft.trimIn} onChange={(event) => onEditChange({ ...editDraft, trimIn: event.target.value })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs text-[#101318] outline-none focus:border-[#171a20]" /></label><label className="grid gap-1.5 text-[11px] font-semibold text-[#5f6673]">Trim out (seconds, optional)<input inputMode="decimal" value={editDraft.trimOut} onChange={(event) => onEditChange({ ...editDraft, trimOut: event.target.value })} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs text-[#101318] outline-none focus:border-[#171a20]" /></label></div><div className="mt-4 flex justify-end"><button type="button" onClick={onSaveEdit} disabled={savingEdit} className="h-8 rounded-lg bg-[#171a20] px-3 text-[11px] font-semibold text-white disabled:opacity-40">{savingEdit ? "Saving…" : "Save edit decision"}</button></div></section> : null}{tab === "review" ? <button type="button" onClick={onReview} disabled={thinking || !shot.video_asset_ids.length} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold hover:bg-[#fafbfc] disabled:opacity-40"><MessageSquare className="size-3.5" />{thinking ? "Reviewing…" : "Ask assistant to review"}</button> : null}</div>;
}
