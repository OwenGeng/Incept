"use client";

import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Film,
  History,
  Image as ImageIcon,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { videoStudioApi } from "./api";
import type { AssetEntry, MediaJob, ProductionShot, ProductionState, TimelineClip } from "./types";

export type ProductionCandidate = {
  nodeId: string;
  label: string;
  assetPath: string;
  mimeType: string;
  sourceJobId?: string;
  duration: number;
};

function blankShot(index: number, isChinese: boolean): ProductionShot {
  return {
    id: `shot-${crypto.randomUUID()}`,
    title: `${isChinese ? "镜头" : "Shot"} ${index}`,
    purpose: "",
    duration: 4,
    status: "draft",
    notes: "",
    keyframe_prompt: "",
    video_prompt: "",
    camera: "",
    continuity: "",
    audio_cue: "",
    keyframes: [],
    selected_keyframe_id: null,
    takes: [],
    selected_take_id: null,
    active_generation_job_id: null,
  };
}

export function ProductionPanel({
  projectId,
  isChinese,
  state,
  candidates,
  assets,
  defaultRatio,
  onChange,
  onCommit,
  onQa,
}: {
  projectId: string;
  isChinese: boolean;
  state: ProductionState;
  candidates: ProductionCandidate[];
  assets: AssetEntry[];
  defaultRatio: string;
  onChange: (state: ProductionState) => void;
  onCommit: (label: string) => Promise<void>;
  onQa: () => Promise<void>;
}) {
  const [busy, setBusy] = useState<"commit" | "qa" | "">("");
  const [busyShots, setBusyShots] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const resumedJobs = useRef(new Set<string>());
  const stateRef = useRef(state);
  useEffect(() => { stateRef.current = state; }, [state]);

  const shots = useMemo(() => new Map(state.shots.map((shot) => [shot.id, shot])), [state.shots]);
  const imageAssets = useMemo(() => assets.filter((asset) => asset.kind === "file" && asset.mime_type?.startsWith("image/")), [assets]);
  const total = state.timeline.filter((clip) => clip.included).reduce((sum, clip) => sum + clip.duration, 0);

  const applyShot = useCallback((shotId: string, update: (shot: ProductionShot) => ProductionShot) => {
    const current = stateRef.current;
    const next = {
      ...current,
      qa: { status: "not_run" as const, issues: [], checked_at: null },
      shots: current.shots.map((shot) => shot.id === shotId ? update(shot) : shot),
    };
    stateRef.current = next;
    onChange(next);
  }, [onChange]);

  const finishJob = useCallback((shotId: string, job: MediaJob) => {
    applyShot(shotId, (shot) => {
      if (job.status !== "completed" || !job.result_asset_path) return { ...shot, active_generation_job_id: null };
      if (job.request.media_type === "image") {
        if (shot.keyframes.some((item) => item.source_job_id === job.id)) return { ...shot, active_generation_job_id: null };
        const id = `keyframe-${crypto.randomUUID()}`;
        return {
          ...shot,
          active_generation_job_id: null,
          selected_keyframe_id: id,
          keyframes: [{
            id,
            asset_path: job.result_asset_path,
            source_job_id: job.id,
            label: `Keyframe ${shot.keyframes.length + 1}`,
            prompt: shot.keyframe_prompt,
            status: "draft",
            created_at: new Date().toISOString(),
          }, ...shot.keyframes],
        };
      }
      if (shot.takes.some((item) => item.source_job_id === job.id)) return { ...shot, active_generation_job_id: null };
      const id = `take-${crypto.randomUUID()}`;
      return {
        ...shot,
        active_generation_job_id: null,
        selected_take_id: id,
        takes: [{
          id,
          asset_path: job.result_asset_path,
          source_job_id: job.id,
          label: `Take ${shot.takes.length + 1}`,
          created_at: new Date().toISOString(),
        }, ...shot.takes],
      };
    });
  }, [applyShot]);

  const pollJob = useCallback(async (shotId: string, jobId: string) => {
    setBusyShots((items) => ({ ...items, [shotId]: isChinese ? "生成中" : "Generating" }));
    try {
      let job = await videoStudioApi.getMediaJob(projectId, jobId);
      while (job.status === "queued" || job.status === "running") {
        setBusyShots((items) => ({ ...items, [shotId]: `${job.message || (isChinese ? "生成中" : "Generating")} · ${job.progress}%` }));
        await new Promise((resolve) => window.setTimeout(resolve, 1_000));
        job = await videoStudioApi.getMediaJob(projectId, jobId);
      }
      if (job.status === "completed") finishJob(shotId, job);
      else {
        applyShot(shotId, (shot) => ({ ...shot, active_generation_job_id: null }));
        setError(job.message || (isChinese ? "生成失败" : "Generation failed"));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Generation status unavailable");
    } finally {
      setBusyShots((items) => { const next = { ...items }; delete next[shotId]; return next; });
    }
  }, [applyShot, finishJob, isChinese, projectId]);

  useEffect(() => {
    for (const shot of state.shots) {
      const jobId = shot.active_generation_job_id;
      if (!jobId || resumedJobs.current.has(jobId)) continue;
      resumedJobs.current.add(jobId);
      void pollJob(shot.id, jobId);
    }
  }, [pollJob, state.shots]);

  const generate = async (shot: ProductionShot, mediaType: "image" | "video") => {
    const prompt = (mediaType === "image" ? shot.keyframe_prompt : shot.video_prompt).trim();
    if (!prompt) return setError(isChinese ? "请先填写该镜头的提示词。" : "Add a prompt for this shot first.");
    const selectedKeyframe = shot.keyframes.find((item) => item.id === shot.selected_keyframe_id && item.status === "approved");
    if (mediaType === "video" && !selectedKeyframe) return setError(isChinese ? "生成 Take 前必须先选择并批准关键帧。" : "Select and approve a keyframe before generating a take.");
    const approved = window.confirm(mediaType === "image"
      ? (isChinese ? `现在为“${shot.title}”调用 Vertex 生成关键帧？这会产生云端模型费用。` : `Generate a Vertex keyframe for “${shot.title}” now? This is a billable cloud model call.`)
      : (isChinese ? `现在为“${shot.title}”调用 Vertex 生成视频 Take？这会产生云端模型费用。` : `Generate a Vertex video take for “${shot.title}” now? This is a billable cloud model call.`));
    if (!approved) return;
    setError("");
    const job = await videoStudioApi.createMediaJob(projectId, {
      idempotency_key: crypto.randomUUID(),
      media_type: mediaType,
      prompt,
      ratio: defaultRatio,
      ...(mediaType === "video" ? { duration: Math.max(1, Math.round(shot.duration)), first_frame_path: selectedKeyframe?.asset_path } : {}),
    });
    applyShot(shot.id, (current) => ({ ...current, active_generation_job_id: job.id }));
    resumedJobs.current.add(job.id);
    await pollJob(shot.id, job.id);
  };

  const addShot = () => {
    const shot = blankShot(state.shots.length + 1, isChinese);
    onChange({
      ...state,
      qa: { status: "not_run", issues: [], checked_at: null },
      shots: [...state.shots, shot],
      timeline: [...state.timeline, { shot_id: shot.id, duration: shot.duration, transition: "cut", included: true }],
    });
  };

  const syncCanvas = () => {
    const nextShots = [...state.shots];
    const nextTimeline = [...state.timeline];
    for (const candidate of candidates) {
      const alreadyLinked = nextShots.some((shot) => shot.takes.some((take) => take.asset_path === candidate.assetPath) || shot.keyframes.some((keyframe) => keyframe.asset_path === candidate.assetPath));
      if (alreadyLinked) continue;
      const shot = blankShot(nextShots.length + 1, isChinese);
      shot.title = candidate.label;
      shot.duration = candidate.duration;
      if (candidate.mimeType.startsWith("image/")) {
        const id = `keyframe-${crypto.randomUUID()}`;
        shot.selected_keyframe_id = id;
        shot.keyframes = [{ id, asset_path: candidate.assetPath, source_job_id: candidate.sourceJobId || null, label: "Keyframe 1", prompt: "", status: "draft", created_at: new Date().toISOString() }];
      } else {
        const id = `take-${crypto.randomUUID()}`;
        shot.selected_take_id = id;
        shot.takes = [{ id, asset_path: candidate.assetPath, source_job_id: candidate.sourceJobId || null, label: "Take 1", created_at: new Date().toISOString() }];
      }
      nextShots.push(shot);
      nextTimeline.push({ shot_id: shot.id, duration: shot.duration, transition: "cut", included: true });
    }
    onChange({ ...state, qa: { status: "not_run", issues: [], checked_at: null }, shots: nextShots, timeline: nextTimeline });
  };

  const attachKeyframe = (shotId: string, path: string) => {
    if (!path) return;
    applyShot(shotId, (shot) => {
      const existing = shot.keyframes.find((item) => item.asset_path === path);
      if (existing) return { ...shot, selected_keyframe_id: existing.id };
      const id = `keyframe-${crypto.randomUUID()}`;
      return { ...shot, selected_keyframe_id: id, keyframes: [{ id, asset_path: path, source_job_id: null, label: `Keyframe ${shot.keyframes.length + 1}`, prompt: "", status: "draft", created_at: new Date().toISOString() }, ...shot.keyframes] };
    });
  };

  const approveKeyframe = (shotId: string) => applyShot(shotId, (shot) => ({
    ...shot,
    keyframes: shot.keyframes.map((item) => ({ ...item, status: item.id === shot.selected_keyframe_id ? "approved" as const : item.status === "approved" ? "draft" as const : item.status })),
  }));

  const removeShot = (shotId: string) => {
    if (!window.confirm(isChinese ? "删除这个镜头及其时间线片段？素材文件不会被删除。" : "Delete this shot and its timeline clip? Asset files will be kept.")) return;
    onChange({ ...state, shots: state.shots.filter((shot) => shot.id !== shotId), timeline: state.timeline.filter((clip) => clip.shot_id !== shotId), qa: { status: "not_run", issues: [], checked_at: null } });
  };

  const updateShot = (shotId: string, patch: Partial<ProductionShot>) => applyShot(shotId, (shot) => ({ ...shot, ...patch }));
  const updateClip = (index: number, patch: Partial<TimelineClip>) => onChange({ ...state, qa: { status: "not_run", issues: [], checked_at: null }, timeline: state.timeline.map((clip, clipIndex) => clipIndex === index ? { ...clip, ...patch } : clip) });
  const moveClip = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= state.timeline.length) return;
    const timeline = [...state.timeline];
    [timeline[index], timeline[target]] = [timeline[target], timeline[index]];
    onChange({ ...state, qa: { status: "not_run", issues: [], checked_at: null }, timeline });
  };
  const commit = async () => {
    const label = window.prompt(isChinese ? "版本名称" : "Revision name", `${isChinese ? "时间线" : "Timeline"} r${state.revision + 1}`)?.trim();
    if (!label) return;
    setBusy("commit");
    try { await onCommit(label); } finally { setBusy(""); }
  };
  const qa = async () => {
    setBusy("qa");
    try { await onQa(); } finally { setBusy(""); }
  };

  return (
    <section className="absolute inset-0 overflow-y-auto bg-[#f7f8fb] px-[max(24px,4vw)] pb-24 pt-24">
      <div className="mx-auto max-w-[1500px]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h2 className="text-xl font-semibold">{isChinese ? "制作时间线" : "Production timeline"}</h2><p className="mt-1 text-xs text-[#909399]">{state.timeline.length} {isChinese ? "个镜头" : "shots"} · {total.toFixed(1)}s · r{state.revision} · {isChinese ? "脚本" : "script"} r{state.script_revision || 0}</p></div>
          <div className="flex flex-wrap gap-2"><button onClick={addShot} className="inline-flex items-center gap-2 rounded-xl border border-[#dcdfe6] bg-white px-3 py-2 text-xs"><Plus className="size-4" />{isChinese ? "新建镜头" : "New shot"}</button><button onClick={syncCanvas} className="inline-flex items-center gap-2 rounded-xl border border-[#dcdfe6] bg-white px-3 py-2 text-xs"><RefreshCw className="size-4" />{isChinese ? "同步画布素材" : "Sync canvas assets"}</button><button onClick={() => void commit()} disabled={busy !== ""} className="inline-flex items-center gap-2 rounded-xl bg-[#8b5cf6] px-3 py-2 text-xs text-white disabled:opacity-50">{busy === "commit" ? <LoaderCircle className="size-4 animate-spin" /> : <History className="size-4" />}{isChinese ? "保存时间线版本" : "Commit timeline"}</button></div>
        </div>
        {error && <div role="alert" className="mt-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-xs text-red-700">{error}</div>}
        <div className="mt-5 grid gap-4 xl:grid-cols-[1.2fr_1fr_0.75fr]">
          <div className="rounded-2xl border border-[#ebeef5] bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold">{isChinese ? "镜头、关键帧与 Take" : "Shots, keyframes & takes"}</h3>
            <div className="mt-3 space-y-3">{state.shots.length === 0 ? <p className="rounded-xl bg-[#f7f8fb] p-6 text-center text-xs text-[#909399]">{isChinese ? "新建镜头，或同步画布中的图片与视频素材" : "Create a shot or sync image and video assets from the canvas"}</p> : state.shots.map((shot, shotIndex) => {
              const selectedKeyframe = shot.keyframes.find((item) => item.id === shot.selected_keyframe_id);
              const keyframeApproved = selectedKeyframe?.status === "approved";
              return <article key={shot.id} className="rounded-xl border border-[#ebeef5] p-3">
                <div className="flex items-center gap-2"><span className="rounded-md bg-[#f2eafe] px-2 py-1 text-[10px] font-semibold text-[#7c3aed]">S{String(shotIndex + 1).padStart(2, "0")}</span><input value={shot.title} onChange={(event) => updateShot(shot.id, { title: event.target.value })} className="min-w-0 flex-1 border-0 text-sm font-medium outline-none" /><button onClick={() => removeShot(shot.id)} className="p-1 text-[#909399] hover:text-red-500" aria-label={isChinese ? "删除镜头" : "Delete shot"}><Trash2 className="size-3.5" /></button></div>
                <textarea value={shot.purpose} onChange={(event) => updateShot(shot.id, { purpose: event.target.value })} placeholder={isChinese ? "镜头目的与可见动作" : "Shot purpose and visible action"} className="mt-2 w-full resize-y rounded-lg bg-[#f7f8fb] p-2 text-xs outline-none" />
                <div className="mt-3 rounded-lg border border-[#ebeef5] p-2"><div className="flex items-center justify-between"><p className="flex items-center gap-1.5 text-[11px] font-semibold"><ImageIcon className="size-3.5 text-[#8b5cf6]" />{isChinese ? "关键帧" : "Keyframe"}</p>{keyframeApproved && <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600"><Check className="size-3" />{isChinese ? "已批准" : "Approved"}</span>}</div><select value={shot.selected_keyframe_id || ""} onChange={(event) => updateShot(shot.id, { selected_keyframe_id: event.target.value || null })} className="mt-2 w-full rounded-lg border border-[#dcdfe6] bg-white px-2 py-1.5 text-[11px]"><option value="">{isChinese ? "选择关键帧" : "Select keyframe"}</option>{shot.keyframes.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.status} · {item.asset_path}</option>)}</select><select value="" onChange={(event) => attachKeyframe(shot.id, event.target.value)} className="mt-2 w-full rounded-lg border border-dashed border-[#c4b5fd] bg-[#faf8ff] px-2 py-1.5 text-[11px] text-[#7c3aed]"><option value="">{isChinese ? "从素材库添加关键帧…" : "Add keyframe from assets…"}</option>{imageAssets.map((asset) => <option key={asset.path} value={asset.path}>{asset.path}</option>)}</select><textarea value={shot.keyframe_prompt} onChange={(event) => updateShot(shot.id, { keyframe_prompt: event.target.value })} placeholder={isChinese ? "关键帧画面提示词" : "Keyframe visual prompt"} className="mt-2 w-full resize-y rounded-lg bg-[#f7f8fb] p-2 text-[11px] outline-none" /><div className="mt-2 grid grid-cols-2 gap-2"><button onClick={() => void generate(shot, "image")} disabled={Boolean(shot.active_generation_job_id)} className="inline-flex items-center justify-center gap-1 rounded-lg border border-[#dcdfe6] px-2 py-1.5 text-[11px] disabled:opacity-40"><ImageIcon className="size-3" />{isChinese ? "生成关键帧" : "Generate keyframe"}</button><button onClick={() => approveKeyframe(shot.id)} disabled={!selectedKeyframe || keyframeApproved} className="inline-flex items-center justify-center gap-1 rounded-lg bg-emerald-50 px-2 py-1.5 text-[11px] text-emerald-700 disabled:opacity-40"><Check className="size-3" />{isChinese ? "批准关键帧" : "Approve keyframe"}</button></div></div>
                <div className="mt-3 rounded-lg border border-[#ebeef5] p-2"><p className="flex items-center gap-1.5 text-[11px] font-semibold"><Film className="size-3.5 text-[#8b5cf6]" />{isChinese ? "视频 Take" : "Video take"}</p><textarea value={shot.video_prompt} onChange={(event) => updateShot(shot.id, { video_prompt: event.target.value })} placeholder={isChinese ? "只描述这个镜头的动作与摄影运动" : "Describe only this shot's action and camera motion"} className="mt-2 w-full resize-y rounded-lg bg-[#f7f8fb] p-2 text-[11px] outline-none" /><div className="mt-2 flex gap-2"><select value={shot.selected_take_id || ""} onChange={(event) => updateShot(shot.id, { selected_take_id: event.target.value || null })} className="min-w-0 flex-1 rounded-lg border border-[#dcdfe6] bg-white px-2 py-1.5 text-[11px]"><option value="">{isChinese ? "选择 Take" : "Select take"}</option>{shot.takes.map((take) => <option key={take.id} value={take.id}>{take.label} · {take.asset_path}</option>)}</select><button onClick={() => void generate(shot, "video")} disabled={!keyframeApproved || Boolean(shot.active_generation_job_id)} className="inline-flex items-center gap-1 rounded-lg bg-[#8b5cf6] px-2 py-1.5 text-[11px] text-white disabled:opacity-40"><Film className="size-3" />{isChinese ? "生成 Take" : "Generate take"}</button></div>{busyShots[shot.id] && <p className="mt-2 flex items-center gap-1.5 text-[10px] text-[#7c3aed]"><LoaderCircle className="size-3 animate-spin" />{busyShots[shot.id]}</p>}</div>
                <div className="mt-2 grid grid-cols-2 gap-2"><label className="text-[10px] text-[#909399]">{isChinese ? "镜头时长" : "Duration"}<input type="number" min={1} max={60} value={shot.duration} onChange={(event) => updateShot(shot.id, { duration: Number(event.target.value) })} className="mt-1 w-full rounded-lg border border-[#dcdfe6] px-2 py-1.5 text-xs text-[#303133]" /></label><label className="text-[10px] text-[#909399]">{isChinese ? "审核状态" : "Review status"}<select value={shot.status} onChange={(event) => updateShot(shot.id, { status: event.target.value as ProductionShot["status"] })} className="mt-1 w-full rounded-lg border border-[#dcdfe6] bg-white px-2 py-1.5 text-xs"><option value="draft">{isChinese ? "待审" : "Draft"}</option><option value="approved" disabled={!keyframeApproved || !shot.selected_take_id}>{isChinese ? "已批准" : "Approved"}</option><option value="changes_requested">{isChinese ? "需修改" : "Changes requested"}</option></select></label></div>
              </article>;
            })}</div>
          </div>
          <div className="rounded-2xl border border-[#ebeef5] bg-white p-4 shadow-sm"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold">{isChinese ? "非破坏性时间线" : "Non-destructive timeline"}</h3><span className="text-xs text-[#909399]">{total.toFixed(1)}s</span></div><div className="mt-3 space-y-2">{state.timeline.map((clip, index) => { const shot = shots.get(clip.shot_id); return <article key={`${clip.shot_id}-${index}`} className={`grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-xl border p-3 ${clip.included ? "border-[#e2dafb] bg-[#faf8ff]" : "border-[#ebeef5] bg-[#f7f8fb] opacity-60"}`}><input type="checkbox" checked={clip.included} onChange={(event) => updateClip(index, { included: event.target.checked })} /><div className="min-w-0"><p className="truncate text-xs font-medium">{index + 1}. {shot?.title || clip.shot_id}</p><div className="mt-2 flex gap-2"><label className="text-[10px] text-[#909399]">{isChinese ? "时长" : "Duration"}<input type="number" min={0.1} max={600} step={0.1} value={clip.duration} onChange={(event) => updateClip(index, { duration: Number(event.target.value) })} className="ml-1 w-16 rounded-md border border-[#dcdfe6] px-1.5 py-1 text-xs text-[#303133]" /></label><select value={clip.transition} onChange={(event) => updateClip(index, { transition: event.target.value as TimelineClip["transition"] })} className="rounded-md border border-[#dcdfe6] bg-white px-1.5 py-1 text-[10px]"><option value="cut">Cut</option><option value="crossfade">Crossfade</option></select></div></div><div className="flex flex-col"><button onClick={() => moveClip(index, -1)} disabled={index === 0} className="p-1 disabled:opacity-20"><ChevronUp className="size-3.5" /></button><button onClick={() => moveClip(index, 1)} disabled={index === state.timeline.length - 1} className="p-1 disabled:opacity-20"><ChevronDown className="size-3.5" /></button></div></article>; })}</div></div>
          <div className="space-y-4"><div className="rounded-2xl border border-[#ebeef5] bg-white p-4 shadow-sm"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold">QA</h3><button onClick={() => void qa()} disabled={busy !== ""} className="inline-flex items-center gap-1.5 rounded-lg bg-[#303133] px-2.5 py-1.5 text-xs text-white disabled:opacity-50">{busy === "qa" ? <LoaderCircle className="size-3.5 animate-spin" /> : <ShieldCheck className="size-3.5" />}{isChinese ? "运行检查" : "Run checks"}</button></div><div className="mt-3 flex items-center gap-2 text-xs">{state.qa.status === "pass" ? <CheckCircle2 className="size-4 text-emerald-500" /> : <CircleAlert className="size-4 text-amber-500" />}<span>{state.qa.status}</span></div>{state.qa.issues.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-[11px] leading-5 text-[#606266]">{state.qa.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>}</div><div className="rounded-2xl border border-[#ebeef5] bg-white p-4 shadow-sm"><h3 className="text-sm font-semibold">{isChinese ? "版本记录" : "Revision history"}</h3><div className="mt-3 space-y-2">{state.timeline_revisions.slice().reverse().slice(0, 8).map((revision) => <div key={revision.id} className="rounded-lg bg-[#f7f8fb] px-3 py-2"><p className="text-xs font-medium">r{revision.revision} · {revision.label}</p><p className="mt-1 text-[10px] text-[#909399]">{revision.clips.length} clips · {new Date(revision.created_at).toLocaleString()}</p></div>)}</div></div><div className="rounded-2xl border border-[#ebeef5] bg-white p-4 shadow-sm"><h3 className="text-sm font-semibold">{isChinese ? "交付清单" : "Delivery manifests"}</h3><div className="mt-3 space-y-2">{state.deliveries.slice(0, 6).map((delivery) => <div key={delivery.id} className="rounded-lg bg-[#f7f8fb] px-3 py-2"><p className="truncate text-xs font-medium">{delivery.asset_path}</p><p className="mt-1 truncate font-mono text-[9px] text-[#909399]">sha256 {delivery.sha256}</p></div>)}</div></div><div className="rounded-2xl border border-[#ebeef5] bg-white p-4 shadow-sm"><h3 className="text-sm font-semibold">{isChinese ? "审计记录" : "Audit trail"}</h3><div className="mt-3 space-y-2">{state.audit_events.slice(0, 8).map((event) => <div key={event.id} className="text-[10px] leading-4 text-[#606266]"><p className="font-medium">{event.kind}</p><p>{event.detail}</p></div>)}</div></div></div>
        </div>
      </div>
    </section>
  );
}
