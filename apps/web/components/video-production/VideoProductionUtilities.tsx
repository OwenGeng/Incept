"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, FileImage, Film, Loader2, Paperclip, Search, ShieldCheck } from "lucide-react";
import type { AssetSummary } from "@incept/shared";
import { listAssets, listVideoProductions, updateVideoProduction, uploadAsset, type VideoProduction } from "@/lib/incept-api";

const WORKSPACE_ID = "wsp_q2";
type AssetRole = VideoProduction["asset_links"][number]["role"];
const assetRoles: Array<{ value: AssetRole; label: string }> = [
  { value: "reference", label: "Reference" }, { value: "brand", label: "Brand" },
  { value: "product", label: "Product" }, { value: "logo", label: "Logo" },
  { value: "character", label: "Character" }, { value: "background", label: "Background" },
  { value: "audio", label: "Audio" },
];

export function VideoAssetsPage() {
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [projects, setProjects] = useState<VideoProduction[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [role, setRole] = useState<AssetRole>("reference");
  const [sourceNote, setSourceNote] = useState("");
  const [rightsNote, setRightsNote] = useState("");
  const [assetQuery, setAssetQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyAssetId, setBusyAssetId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    setLoading(true); setError(null);
    try {
      const [nextAssets, nextProjects] = await Promise.all([listAssets(WORKSPACE_ID), listVideoProductions(WORKSPACE_ID)]);
      setAssets(nextAssets); setProjects(nextProjects);
      setSelectedProjectId((current) => current && nextProjects.some((project) => project.production_id === current) ? current : nextProjects[0]?.production_id ?? "");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load shared assets."); }
    finally { setLoading(false); }
  }

  useEffect(() => { void refresh(); }, []);
  const selectedProject = useMemo(() => projects.find((project) => project.production_id === selectedProjectId) ?? null, [projects, selectedProjectId]);
  const visibleAssets = useMemo(() => {
    const query = assetQuery.trim().toLowerCase();
    if (!query) return assets;
    return assets.filter((asset) => [asset.title, asset.type, asset.provider, asset.assetRole].filter(Boolean).join(" ").toLowerCase().includes(query));
  }, [assetQuery, assets]);

  async function attachAsset(asset: AssetSummary) {
    if (!selectedProject || busyAssetId) return;
    setBusyAssetId(asset.id); setError(null); setNotice(null);
    try {
      const existing = selectedProject.asset_links.find((link) => link.asset_id === asset.id);
      const assetLinks = existing
        ? selectedProject.asset_links.map((link) => link.asset_id === asset.id ? { ...link, role, label: asset.title, source_note: sourceNote.trim(), rights_note: rightsNote.trim() } : link)
        : [...selectedProject.asset_links, { asset_id: asset.id, role, label: asset.title, source_note: sourceNote.trim(), rights_note: rightsNote.trim() }];
      const referenceAssetIds = Array.from(new Set([...selectedProject.reference_asset_ids, asset.id]));
      const nextProject = await updateVideoProduction(selectedProject.production_id, { asset_links: assetLinks, reference_asset_ids: referenceAssetIds, expected_revision: selectedProject.state_revision });
      setProjects((current) => current.map((project) => project.production_id === nextProject.production_id ? nextProject : project));
      setNotice(existing ? asset.title + " role updated to " + role + "." : asset.title + " attached to " + (nextProject.title || "this project") + ".");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not attach this asset."); }
    finally { setBusyAssetId(null); }
  }

  async function detachAsset(asset: AssetSummary) {
    if (!selectedProject || busyAssetId) return;
    setBusyAssetId(asset.id); setError(null); setNotice(null);
    try {
      const nextProject = await updateVideoProduction(selectedProject.production_id, {
        asset_links: selectedProject.asset_links.filter((link) => link.asset_id !== asset.id),
        reference_asset_ids: selectedProject.reference_asset_ids.filter((assetId) => assetId !== asset.id),
        expected_revision: selectedProject.state_revision,
      });
      setProjects((current) => current.map((project) => project.production_id === nextProject.production_id ? nextProject : project));
      setNotice(`${asset.title} was detached. The source file remains in the shared library.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not detach this asset."); }
    finally { setBusyAssetId(null); }
  }

  async function uploadSelectedAsset(file: File | undefined) {
    if (!file || uploading) return;
    setUploading(true); setError(null); setNotice(null);
    try {
      const uploaded = await uploadAsset(file, WORKSPACE_ID, role);
      if (!uploaded) throw new Error("The asset upload did not return a saved record.");
      await refresh();
      setNotice(`${file.name} was uploaded to the shared library. Attach it to a project when its role and rights notes are ready.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not upload this asset."); }
    finally {
      setUploading(false);
      if (uploadInputRef.current) uploadInputRef.current.value = "";
    }
  }

  return <main className="mx-auto max-w-6xl px-5 py-10 md:px-8">
    <Link href="/video-production" className="text-sm font-semibold text-[#171a20]">← Productions</Link>
    <div className="mt-5 flex flex-col gap-4 border-b border-[#e6e8ec] pb-6 md:flex-row md:items-end md:justify-between"><div><p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-[#5f6673]">Production assets</p><h1 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em]">Shared asset library</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#5f6673]">Upload source material, then attach it to a project with an explicit production role and rights note. Uploading never starts a generation job.</p></div><div className="flex flex-wrap gap-2"><input ref={uploadInputRef} type="file" accept="image/*,video/*,audio/*,.psd" className="sr-only" onChange={(event) => void uploadSelectedAsset(event.target.files?.[0])} /><button type="button" onClick={() => uploadInputRef.current?.click()} disabled={uploading} className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white hover:bg-[#30343c] disabled:opacity-40">{uploading ? <Loader2 className="size-3.5 animate-spin" /> : <Paperclip className="size-3.5" />}{uploading ? "Uploading…" : "Upload asset"}</button><button type="button" onClick={() => void refresh()} disabled={uploading} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold text-[#171a20] hover:bg-[#fafbfc] disabled:opacity-40">Refresh library</button></div></div>
    {loading ? <div className="mt-8 grid min-h-40 place-items-center border border-[#e6e8ec] bg-white"><Loader2 className="size-5 animate-spin text-[#5f6673]" /></div> : error ? <div className="mt-8 rounded-xl border border-red-200 bg-[#fff7f7] p-4 text-sm text-red-700"><p>{error}</p><button type="button" onClick={() => void refresh()} className="mt-3 text-xs font-semibold underline">Try again</button></div> : <>
      <section className="mt-6 grid gap-3 rounded-2xl border border-[#e6e8ec] bg-[#fafbfc] p-4 md:grid-cols-2"><label className="text-xs font-semibold text-[#171a20]">Attach to project<select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)} className="mt-2 h-10 w-full rounded-lg border border-[#e6e8ec] bg-white px-3 text-sm font-normal outline-none focus:border-[#171a20]" disabled={!projects.length}><option value="">{projects.length ? "Choose a project" : "Create a project first"}</option>{projects.map((project) => <option key={project.production_id} value={project.production_id}>{project.title || "Untitled production"}</option>)}</select></label><label className="text-xs font-semibold text-[#171a20]">Asset role<select value={role} onChange={(event) => setRole(event.target.value as AssetRole)} className="mt-2 h-10 w-full rounded-lg border border-[#e6e8ec] bg-white px-3 text-sm font-normal outline-none focus:border-[#171a20]">{assetRoles.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label className="text-xs font-semibold text-[#171a20]">Source note<input value={sourceNote} onChange={(event) => setSourceNote(event.target.value)} placeholder="e.g. client supplied" className="mt-2 h-10 w-full rounded-lg border border-[#e6e8ec] bg-white px-3 text-sm font-normal outline-none focus:border-[#171a20]" /></label><label className="text-xs font-semibold text-[#171a20]">Usage / rights note<input value={rightsNote} onChange={(event) => setRightsNote(event.target.value)} placeholder="e.g. approved for campaign" className="mt-2 h-10 w-full rounded-lg border border-[#e6e8ec] bg-white px-3 text-sm font-normal outline-none focus:border-[#171a20]" /></label></section>
      <label className="mt-4 flex h-10 max-w-md items-center gap-2 rounded-lg border border-[#e6e8ec] bg-white px-3 text-[#5f6673]"><Search className="size-3.5" /><input value={assetQuery} onChange={(event) => setAssetQuery(event.target.value)} placeholder="Search uploaded assets" className="min-w-0 flex-1 bg-transparent text-xs text-[#171a20] outline-none placeholder:text-[#8b919c]" /></label>
      {notice ? <div className="mt-4 flex items-center gap-2 rounded-xl border border-[#cfe8dc] bg-[#effaf5] p-3 text-sm text-[#1d6b4d]"><Check className="size-4" />{notice}</div> : null}
      {assets.length ? visibleAssets.length ? <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">{visibleAssets.map((asset) => {
        const attachedRole = selectedProject?.asset_links.find((link) => link.asset_id === asset.id)?.role;
        return <article key={asset.id} className="overflow-hidden rounded-2xl border border-[#e6e8ec] bg-white"><div className="aspect-video bg-[#f6f8fb]">{asset.type === "video" ? <video src={asset.url} muted preload="metadata" className="size-full object-cover" /> : asset.type === "audio" ? <div className="flex size-full flex-col items-center justify-center gap-3 px-4 text-center"><Film className="size-6 text-[#5f6673]" /><audio controls preload="metadata" src={asset.url} className="max-w-full" /><span className="text-[11px] text-[#5f6673]">Audio source</span></div> : asset.type === "image" || asset.type === "gif" ? <img src={asset.url} alt={asset.title} className="size-full object-cover" /> : <div className="flex size-full flex-col items-center justify-center gap-2 text-[#5f6673]"><FileImage className="size-6" /><span className="text-xs font-medium">{asset.type} source</span></div>}</div><div className="p-4"><div className="flex min-w-0 items-center justify-between gap-3"><p className="truncate text-sm font-semibold">{asset.title}</p><span className="shrink-0 rounded-full bg-[#f6f8fb] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#5f6673]">{asset.type}</span></div>{attachedRole ? <p className="mt-2 text-xs text-[#2d8a64]">Attached as {attachedRole}</p> : <p className="mt-2 text-xs text-[#5f6673]">Not attached to selected project</p>}<div className="mt-4 flex flex-wrap gap-2"><button type="button" onClick={() => void attachAsset(asset)} disabled={!selectedProject || busyAssetId === asset.id} className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white hover:bg-[#30343c] disabled:cursor-not-allowed disabled:opacity-40">{busyAssetId === asset.id ? <Loader2 className="size-3.5 animate-spin" /> : <Paperclip className="size-3.5" />}{attachedRole ? "Update role" : "Attach to project"}</button>{attachedRole ? <button type="button" onClick={() => void detachAsset(asset)} disabled={busyAssetId === asset.id} className="h-9 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold text-[#5f6673] hover:bg-[#fafbfc] disabled:opacity-40">Detach</button> : null}</div></div></article>;
      })}</div> : <div className="mt-6 rounded-xl border border-dashed border-[#d7dbe2] bg-[#fafbfc] px-6 py-12 text-center"><Search className="mx-auto size-6 text-[#5f6673]" /><h2 className="mt-3 font-semibold">No matching assets</h2><p className="mt-2 text-sm text-[#5f6673]">Clear or change the search to see the shared library.</p></div> : <div className="mt-8 border border-dashed border-[#d7dbe2] bg-[#fafbfc] px-6 py-14 text-center"><FileImage className="mx-auto size-7 text-[#171a20]" /><h2 className="mt-4 font-semibold">No shared assets yet</h2><p className="mt-2 text-sm text-[#5f6673]">Upload source material, then attach it to the right production.</p><button type="button" onClick={() => uploadInputRef.current?.click()} className="mt-5 inline-flex text-sm font-semibold text-[#171a20]">Upload an asset <ArrowRight className="ml-1 size-4" /></button></div>}
    </>}
  </main>;
}

export function VideoDeliveryPage() {
  const [projects, setProjects] = useState<VideoProduction[]>([]); const [assets, setAssets] = useState<AssetSummary[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  useEffect(() => { void Promise.all([listVideoProductions(WORKSPACE_ID), listAssets(WORKSPACE_ID)]).then(([nextProjects, nextAssets]) => { setProjects(nextProjects); setAssets(nextAssets); }).catch(() => setError("Could not load delivery status. Check that the local API is running, then refresh.")) .finally(() => setLoading(false)); }, []);
  const delivered = projects.filter((project) => project.final_asset_id); const pending = projects.filter((project) => !project.final_asset_id);
  const assetById = useMemo(() => new Map(assets.map((asset) => [asset.id, asset])), [assets]);
  return <main className="mx-auto max-w-6xl px-5 py-10 md:px-8"><Link href="/video-production" className="text-sm font-semibold text-[#171a20]">← Productions</Link><h1 className="mt-5 font-display text-3xl font-semibold tracking-[-0.04em]">Delivery control</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#5f6673]">Every export remains attached to selected takes, edit decisions and QA state. A project manifest can be downloaded for handoff and review.</p>{loading ? <div className="mt-8 grid min-h-40 place-items-center border border-[#e6e8ec] bg-white"><Loader2 className="size-5 animate-spin text-[#5f6673]" /></div> : error ? <div className="mt-8 border border-red-200 bg-[#fff7f7] p-4 text-sm text-red-700">{error}</div> : <div className="mt-8 grid gap-3 lg:grid-cols-2"><DeliveryList icon={ShieldCheck} title="Delivered" projects={delivered} assets={assetById} empty="No completed deliveries yet." /><DeliveryList icon={Film} title="In production" projects={pending} assets={assetById} empty="No active productions." /></div>}</main>;
}

function downloadManifest(project: VideoProduction) {
  const manifest = {
    production_id: project.production_id, title: project.title, created_at: project.created_at, updated_at: project.updated_at,
    format: { aspect_ratio: project.aspect_ratio, target_seconds: project.target_seconds, resolution: project.resolution },
    final_asset_id: project.final_asset_id, quality_control: { status: project.edit_plan.qc_status, issues: project.edit_plan.qc_issues },
    source_assets: project.asset_links, selected_takes: project.shots.filter((shot) => shot.selected_video_asset_id).map((shot) => ({ shot_id: shot.id, order: shot.order, selected_video_asset_id: shot.selected_video_asset_id, trim_in_seconds: shot.trim_in_seconds, trim_out_seconds: shot.trim_out_seconds })),
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(manifest, null, 2)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = url; link.download = (project.title || "production") + "-manifest.json"; link.click(); URL.revokeObjectURL(url);
}

function downloadQaReport(project: VideoProduction) {
  const report = {
    report_type: "linglong-production-qa", production_id: project.production_id, title: project.title,
    generated_at: new Date().toISOString(), revision: project.state_revision,
    quality_control: { status: project.edit_plan.qc_status, issues: project.edit_plan.qc_issues, final_duration_seconds: project.edit_plan.final_duration_seconds },
    selected_takes: project.shots.filter((shot) => shot.selected_video_asset_id).map((shot) => ({ shot_id: shot.id, order: shot.order, title: shot.title, include_in_edit: shot.include_in_edit, selected_video_asset_id: shot.selected_video_asset_id, trim_in_seconds: shot.trim_in_seconds, trim_out_seconds: shot.trim_out_seconds, take_outdated: shot.take_outdated })),
    render: { final_asset_id: project.final_asset_id, render_job_id: project.render_job_id },
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = url; link.download = (project.title || "production") + "-qa-report.json"; link.click(); URL.revokeObjectURL(url);
}

function DeliveryList({ icon: Icon, title, projects, assets, empty }: { icon: typeof Film; title: string; projects: VideoProduction[]; assets: Map<string, AssetSummary>; empty: string }) {
  return <section className="rounded-2xl border border-[#e6e8ec] bg-white p-5"><div className="flex items-center gap-2"><Icon className="size-5 text-[#171a20]" /><h2 className="font-semibold">{title}</h2><span className="text-sm text-[#5f6673]">{projects.length}</span></div><div className="mt-5 space-y-3">{projects.length ? projects.map((project) => { const finalAsset = project.final_asset_id ? assets.get(project.final_asset_id) : undefined; const selected = project.shots.filter((shot) => shot.selected_video_asset_id).length; return <article key={project.production_id} className="rounded-xl border border-[#e6e8ec] p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-semibold">{project.title}</p><p className="mt-1 text-xs text-[#5f6673]">{selected}/{project.shots.length} selected takes · QA {project.edit_plan.qc_status}</p></div><Link href={"/video-production/projects/" + project.production_id} className="shrink-0 text-xs font-semibold text-[#171a20]">Open <ArrowRight className="inline size-3.5" /></Link></div><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => downloadManifest(project)} className="h-8 rounded-lg border border-[#e6e8ec] px-3 text-xs font-semibold hover:bg-[#fafbfc]">Download manifest</button><button type="button" onClick={() => downloadQaReport(project)} className="h-8 rounded-lg border border-[#e6e8ec] px-3 text-xs font-semibold hover:bg-[#fafbfc]">Download QA</button>{finalAsset ? <a href={finalAsset.url} download className="inline-flex h-8 items-center rounded-lg bg-[#171a20] px-3 text-xs font-semibold text-white hover:bg-[#30343c]">Download final</a> : <span className="inline-flex h-8 items-center rounded-lg bg-[#f6f8fb] px-3 text-xs font-medium text-[#5f6673]">Final render pending</span>}</div>{project.edit_plan.qc_issues.length ? <p className="mt-3 rounded-lg bg-[#fff7e8] p-2 text-[11px] leading-5 text-[#8a5a08]">{project.edit_plan.qc_issues.join(" · ")}</p> : null}</article>; }) : <p className="rounded-xl border border-dashed border-[#d7dbe2] p-4 text-sm text-[#5f6673]">{empty}</p>}</div></section>;
}
