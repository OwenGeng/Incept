"use client";

// `useTemplate` is a click handler retained for the deferred product surface,
// not a React Hook. The current compact source shape confuses the hook-name
// heuristic; this module is not part of the Image + AI Video release profile.
/* eslint-disable react-hooks/rules-of-hooks */

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Download, Gamepad2, Heart, ImagePlus, Loader2, Play, Save, ShieldCheck, Upload, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { uploadAsset } from "@/lib/incept-api";
import { PhaserMergePreview } from "@/components/gaming-playable/PhaserMergePreview";
import {
  buildStandalonePlayable,
  createPlayableTemplate,
  forkPlayableTemplate,
  getPlayableProject,
  listPlayableTemplates,
  PLAYABLE_TEMPLATES,
  preflightPlayable,
  savePlayableProject,
  togglePlayableTemplateFavorite,
  type GamingPlayableTemplate,
  type PlayablePlanningModel,
  type PlayableSchema,
  type PlayableTemplateRecord,
  type PlayableTemplateVisibility,
} from "@/lib/gaming-playable";

const WORKSPACE_ID = "wsp_q2";

async function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function formatBytes(bytes: number) {
  return `${(bytes / 1024).toFixed(0)} KB`;
}

function isGameplayTemplate(value: unknown): value is GamingPlayableTemplate {
  return typeof value === "string" && PLAYABLE_TEMPLATES.some((template) => template.id === value);
}

function isOrientation(value: unknown): value is "portrait" | "landscape" {
  return value === "portrait" || value === "landscape";
}

function isPlanningModel(value: unknown): value is PlayablePlanningModel {
  return value === "gemini-3.8-flash" || value === "gemini-3.1-pro-preview";
}

export function GamingPlayableWorkspace({ embedded = false, initialProjectId }: { embedded?: boolean; initialProjectId?: string }) {
  const [title, setTitle] = useState("Garden Quest");
  const [cta, setCta] = useState("Play now");
  const [templateId, setTemplateId] = useState<GamingPlayableTemplate>("merge");
  const [orientation, setOrientation] = useState<"portrait" | "landscape">("portrait");
  const [targetValue, setTargetValue] = useState(16);
  const [tutorialText, setTutorialText] = useState("Tap two matching pieces to merge them");
  const [planningModel, setPlanningModel] = useState<PlayablePlanningModel>("gemini-3.8-flash");
  const [brief, setBrief] = useState("");
  const [referenceAssetIds, setReferenceAssetIds] = useState<string[]>([]);
  const [referenceNames, setReferenceNames] = useState<string[]>([]);
  const [art, setArt] = useState<{ file: File; dataUrl: string } | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [sourceTemplateId, setSourceTemplateId] = useState<string | null>(null);
  const [templates, setTemplates] = useState<PlayableTemplateRecord[]>([]);
  const [templateTitle, setTemplateTitle] = useState("Garden Quest template");
  const [templateDescription, setTemplateDescription] = useState("");
  const [templateVisibility, setTemplateVisibility] = useState<Exclude<PlayableTemplateVisibility, "community">>("private");
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState<"project" | "template" | string | null>(null);
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [loadingProject, setLoadingProject] = useState(Boolean(initialProjectId));
  const [notice, setNotice] = useState("Test the real Phaser Merge scene here. Standalone delivery export remains gated until its no-XHR runtime build passes validation.");
  const fileRef = useRef<HTMLInputElement>(null);
  const activeTemplate = PLAYABLE_TEMPLATES.find((item) => item.id === templateId) || PLAYABLE_TEMPLATES[0];

  const schema = useMemo<PlayableSchema>(() => ({
    schemaVersion: 1,
    runtime: "phaser-preview-v1",
    metadata: { title, ctaLabel: cta, orientation, brief: brief || undefined, planningModel },
    assets: { backgroundDataUri: art?.dataUrl, referenceAssetIds, referenceNames },
    gameplay: { template: templateId, accentColor: activeTemplate.accent, targetValue, tutorialText },
  }), [activeTemplate.accent, art?.dataUrl, brief, cta, orientation, planningModel, referenceAssetIds, referenceNames, targetValue, templateId, title, tutorialText]);
  const html = useMemo(() => buildStandalonePlayable(schema), [schema]);
  const preflight = useMemo(() => preflightPlayable(html), [html]);

  const applyProjectSchema = (nextSchema: PlayableSchema) => {
    const nextTemplate = isGameplayTemplate(nextSchema.gameplay?.template) ? nextSchema.gameplay.template : "merge";
    const nextDefault = PLAYABLE_TEMPLATES.find((item) => item.id === nextTemplate) || PLAYABLE_TEMPLATES[0];
    setTemplateId(nextTemplate);
    setTitle(nextSchema.metadata?.title || "Untitled playable");
    setCta(nextSchema.metadata?.ctaLabel || "Play now");
    setOrientation(isOrientation(nextSchema.metadata?.orientation) ? nextSchema.metadata.orientation : "portrait");
    setTargetValue(Math.max(4, Number(nextSchema.gameplay?.targetValue) || 16));
    setTutorialText(nextSchema.gameplay?.tutorialText || nextDefault.defaultInstruction);
    setBrief(nextSchema.metadata?.brief || "");
    setPlanningModel(isPlanningModel(nextSchema.metadata?.planningModel) ? nextSchema.metadata.planningModel : "gemini-3.8-flash");
    setReferenceAssetIds(nextSchema.assets?.referenceAssetIds || []);
    setReferenceNames(nextSchema.assets?.referenceNames || []);
    // Data-URI art is deliberately never retained by a shareable template.
    setArt(null);
  };

  const refreshTemplates = async () => {
    setLoadingTemplates(true);
    try {
      setTemplates(await listPlayableTemplates(WORKSPACE_ID));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load templates.");
    } finally {
      setLoadingTemplates(false);
    }
  };

  useEffect(() => { void refreshTemplates(); }, []);

  useEffect(() => {
    if (!initialProjectId) return;
    let active = true;
    void getPlayableProject(initialProjectId)
      .then((project) => {
        if (!active) return;
        applyProjectSchema(project.schema);
        setProjectId(project.project_id);
        setSourceTemplateId(project.source_template_id || null);
        setNotice(`Loaded “${project.title}”. Continue editing and save when ready.`);
      })
      .catch((error) => { if (active) setNotice(error instanceof Error ? error.message : "Could not load this playable project."); })
      .finally(() => { if (active) setLoadingProject(false); });
    return () => { active = false; };
    // applyProjectSchema only writes the local editor state for this project id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialProjectId]);

  const selectTemplate = (next: GamingPlayableTemplate) => {
    const template = PLAYABLE_TEMPLATES.find((item) => item.id === next) || PLAYABLE_TEMPLATES[0];
    setTemplateId(next);
    setTutorialText(template.defaultInstruction);
  };

  const downloadPrototype = () => {
    if (!preflight.valid) return setNotice(preflight.errors[0]);
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-") || "playable"}.html`;
    anchor.click();
    URL.revokeObjectURL(url);
    setNotice("Downloaded the lightweight prototype shell. It is not the Phaser delivery artifact; use it only for concept review.");
  };

  const saveToLibrary = async () => {
    if (!preflight.valid) return setNotice(preflight.errors[0]);
    setUploading(true);
    try {
      const file = new File([html], `${title.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-") || "playable"}.html`, { type: "text/html" });
      const saved = await uploadAsset(file, WORKSPACE_ID, "generated");
      if (!saved) throw new Error("The playable was not saved.");
      setNotice("Prototype shell saved to Library. It is not yet approved for external delivery.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not save playable.");
    } finally {
      setUploading(false);
    }
  };

  const saveProject = async () => {
    setSaving("project");
    try {
      const project = await savePlayableProject({ workspaceId: WORKSPACE_ID, projectId, title, schema, sourceTemplateId });
      setProjectId(project.project_id);
      setNotice("Private playable project saved. Your uploaded artwork stays only with this project.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not save the playable project.");
    } finally {
      setSaving(null);
    }
  };

  const saveTemplate = async () => {
    const cleanTitle = templateTitle.trim() || `${title.trim() || "Playable"} template`;
    setSaving("template");
    try {
      const created = await createPlayableTemplate({ workspaceId: WORKSPACE_ID, title: cleanTitle, description: templateDescription, visibility: templateVisibility, category: templateId, schema });
      setTemplates((current) => [created, ...current]);
      setNotice(templateVisibility === "workspace"
        ? "Workspace template saved. The gameplay setup is shared; uploaded artwork was removed and is now a slot for each creator."
        : "Private template saved. Uploaded artwork was removed, so it can be safely reused as a fresh campaign starting point.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not save the template.");
    } finally {
      setSaving(null);
    }
  };

  const useTemplate = async (template: PlayableTemplateRecord) => {
    setSaving(template.template_id);
    try {
      const project = await forkPlayableTemplate(template.template_id, `${template.title} copy`);
      applyProjectSchema(project.schema);
      setProjectId(project.project_id);
      setSourceTemplateId(template.template_id);
      setNotice(`Created an independent project from “${template.title}”. Add your campaign artwork to fill its background-art slot.`);
      await refreshTemplates();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not create a project from this template.");
    } finally {
      setSaving(null);
    }
  };

  const favoriteTemplate = async (templateIdToToggle: string) => {
    setSaving(`favorite-${templateIdToToggle}`);
    try {
      const updated = await togglePlayableTemplateFavorite(templateIdToToggle);
      setTemplates((current) => current
        .map((template) => template.template_id === updated.template_id ? updated : template)
        .sort((a, b) => b.favorite_count - a.favorite_count || b.fork_count - a.fork_count));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not update the template favorite.");
    } finally {
      setSaving(null);
    }
  };

  return (
    <main className={cn("min-h-screen text-slate-950", embedded ? "bg-transparent" : "bg-[#F7F8FB]")}>
      {!embedded && <header className="sticky top-0 z-20 border-b border-slate-200/90 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-5 py-3 sm:px-8">
          <div className="flex items-center gap-3"><Link href="/" className="rounded-xl p-2 text-slate-500 hover:bg-slate-100"><ArrowLeft className="size-4" /></Link><div className="flex size-9 items-center justify-center rounded-xl bg-[#F97316] text-white"><Gamepad2 className="size-5" /></div><div><p className="text-base font-semibold tracking-tight">GamingPlayable</p><p className="text-xs text-slate-500">Playable project workspace</p></div></div>
          <div className="hidden items-center gap-2 text-xs text-slate-500 sm:flex"><ShieldCheck className="size-4 text-emerald-600" />No external references · CTA ready</div>
        </div>
      </header>}
      <div className="mx-auto max-w-[1440px] px-5 py-7 lg:px-8">
        {loadingProject && <div className="mb-5 flex items-center gap-2 rounded-xl border border-[#FED7AA] bg-[#FFF7ED] px-4 py-3 text-sm text-[#9A3412]"><Loader2 className="size-4 animate-spin" />Loading playable project…</div>}
        <div className="grid gap-7 lg:grid-cols-[440px_minmax(0,1fr)]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_12px_28px_rgba(15,23,42,0.05)] sm:p-6">
            <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-[#C2410C]">Gameplay · Phaser preview</p><h1 className="mt-1 text-xl font-semibold tracking-tight">Build the long game loop first.</h1><p className="mt-2 text-sm leading-6 text-slate-500">Merge Garden now runs in Phaser with repeatable level progression. The same versioned configuration will later drive the delivery exporter and the LittleJS comparison build.</p></div>
            <div className="mt-7"><p className="text-sm font-semibold">Gameplay template</p><div className="mt-3 grid gap-2">{PLAYABLE_TEMPLATES.map((item) => <button key={item.id} disabled={item.id !== "merge"} onClick={() => selectTemplate(item.id)} className={cn("rounded-xl border p-3.5 text-left transition", templateId === item.id ? "border-slate-950 bg-slate-950 text-white" : item.id === "merge" ? "border-slate-200 hover:border-slate-400" : "cursor-not-allowed border-slate-100 bg-slate-50 text-slate-400")}><div className="flex items-center justify-between gap-3"><p className="text-sm font-semibold">{item.name}</p>{item.id !== "merge" && <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide">Next</span>}</div><p className={cn("mt-1 text-xs leading-5", templateId === item.id ? "text-slate-300" : item.id === "merge" ? "text-slate-500" : "text-slate-400")}>{item.description}</p></button>)}</div></div>
            <div className="mt-6 grid grid-cols-2 gap-3"><label className="text-xs font-medium text-slate-600">Game / campaign name<input value={title} onChange={(event) => { setTitle(event.target.value); setTemplateTitle(`${event.target.value || "Playable"} template`); }} className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500" /></label><label className="text-xs font-medium text-slate-600">CTA label<input value={cta} onChange={(event) => setCta(event.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500" /></label></div>
            <label className="mt-4 block text-xs font-medium text-slate-600">Creative brief<textarea value={brief} onChange={(event) => setBrief(event.target.value)} placeholder="What should players do?" className="mt-1.5 min-h-20 w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm leading-5 text-slate-950 outline-none focus:border-slate-500" /></label>
            <div className="mt-4 grid grid-cols-[1fr_132px] gap-3"><label className="text-xs font-medium text-slate-600">Tutorial instruction<input value={tutorialText} onChange={(event) => setTutorialText(event.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500" /></label><label className="text-xs font-medium text-slate-600">Merge goal<input type="number" min="4" max="64" value={targetValue} onChange={(event) => setTargetValue(Number(event.target.value) || 4)} className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500" /></label></div>
            <div className="mt-5"><p className="text-sm font-semibold">Delivery format</p><div className="mt-2 flex gap-2"><button onClick={() => setOrientation("portrait")} className={cn("rounded-lg border px-3 py-2 text-sm", orientation === "portrait" ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200")}>Portrait</button><button onClick={() => setOrientation("landscape")} className={cn("rounded-lg border px-3 py-2 text-sm", orientation === "landscape" ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200")}>Landscape</button></div></div>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={async (event) => { const file = event.target.files?.[0]; if (file) setArt({ file, dataUrl: await fileToDataUrl(file) }); event.target.value = ""; }} />
            <div className="mt-5 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4"><div className="flex items-center justify-between gap-3"><div><p className="text-sm font-medium">Game artwork</p><p className="mt-1 text-xs leading-5 text-slate-500">Use a background, world frame, or approved game art. It remains private to this project and is never copied into a reusable template.</p></div><Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}><ImagePlus className="mr-1.5 size-3.5" />{art ? "Replace" : "Add image"}</Button></div>{referenceNames.length > 0 && <p className="mt-3 text-xs leading-5 text-slate-500">{referenceNames.length} reference{referenceNames.length === 1 ? "" : "s"} attached: {referenceNames.join(", ")}</p>}{art && <div className="mt-3 flex items-center gap-3"><img src={art.dataUrl} alt="Playable artwork" className="size-12 rounded-lg object-cover" /><div className="min-w-0"><p className="truncate text-xs font-medium">{art.file.name}</p><button onClick={() => setArt(null)} className="mt-1 text-xs font-medium text-slate-600 underline underline-offset-4">Remove image</button></div></div>}</div>
            <div className={cn("mt-6 rounded-xl p-4", preflight.valid ? "bg-slate-950 text-white" : "border border-red-200 bg-red-50 text-red-950")}><div className="flex items-center justify-between"><p className="text-sm font-semibold">Prototype-shell preflight</p><span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", preflight.valid ? "bg-emerald-400/20 text-emerald-200" : "bg-red-200 text-red-800")}>{formatBytes(preflight.byteSize)} {preflight.valid ? "· shell ready" : "· blocked"}</span></div><ul className={cn("mt-3 space-y-1.5 text-xs leading-5", preflight.valid ? "text-slate-300" : "text-red-800")}>{preflight.valid ? <><li>✓ One self-contained prototype shell with approved art embedded</li><li>✓ No external requests, XHR, redirects, or mraid.js</li><li>✓ CTA uses `FbPlayableAd.onCTAClick()`</li></> : preflight.errors.map((error) => <li key={error}>× {error}</li>)}</ul><p className={cn("mt-3 text-[11px] leading-4", preflight.valid ? "text-amber-200" : "text-red-700")}>Phaser 4’s stock bundle contains a Loader/XHR module, so its delivery export remains deliberately blocked until we produce and validate a no-XHR custom build.</p></div>
          </section>
          <section className="min-w-0"><div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_12px_28px_rgba(15,23,42,0.05)] sm:p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Playable preview</h2><p className="mt-1 text-sm text-slate-500">This is a live Phaser scene, not a simulated video. Merge three objectives to advance, then continue playing indefinitely.</p></div><span className="rounded-full bg-[#FFF7ED] px-3 py-1.5 text-xs font-semibold text-[#C2410C]">{orientation === "portrait" ? "9:16" : "16:9"} · Phaser 4.2.1</span></div><div className="mt-5 flex min-h-[620px] items-center justify-center overflow-hidden rounded-2xl bg-[#dce9df] p-5"><div className={cn("overflow-hidden rounded-[28px] border-[8px] border-slate-950 bg-white shadow-2xl", orientation === "portrait" ? "h-[610px] w-[343px] max-w-full" : "aspect-video w-full max-w-[850px]")}><PhaserMergePreview schema={schema} /></div></div><div className="mt-5 flex flex-wrap items-center gap-3"><Button onClick={downloadPrototype} disabled={!preflight.valid} className="bg-[#F97316] hover:bg-[#EA580C]"><Download className="mr-2 size-4" />Download prototype shell</Button><Button onClick={() => void saveToLibrary()} disabled={!preflight.valid || uploading} variant="outline">{uploading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Upload className="mr-2 size-4" />}Save prototype to Library</Button><Button onClick={() => void saveProject()} disabled={saving === "project"} variant="outline">{saving === "project" ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Save className="mr-2 size-4" />}Save project</Button><p className="max-w-xl text-sm leading-6 text-slate-500 lg:ml-auto">{notice}</p></div></div><div className="mt-5 rounded-2xl border border-[#FED7AA] bg-[#FFF7ED] p-5"><div className="flex gap-3"><Play className="mt-0.5 size-5 shrink-0 text-[#C2410C]" /><div><h2 className="font-semibold">Delivery path</h2><p className="mt-1 text-sm leading-6 text-slate-600">Phaser is now the first gameplay runtime. Next we build a no-XHR Phaser delivery bundle, validate it through Creative Core, and only then enable a client-ready HTML export. LittleJS will reuse this same configuration as a later size-and-performance comparator.</p></div></div></div></section>
        </div>

        <section className="mt-7 rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_12px_28px_rgba(15,23,42,0.05)] sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><Users className="size-5 text-[#C2410C]" /><h2 className="text-lg font-semibold">Template library</h2></div><p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">Save a reusable gameplay recipe, then make a fully independent copy from it. Workspace templates are shared only with signed-in Studio users; community publishing is intentionally not enabled yet.</p></div><span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600">{templates.length} available</span></div>
          <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{loadingTemplates ? <div className="col-span-full flex min-h-32 items-center gap-2 rounded-xl border border-dashed border-slate-200 px-4 text-sm text-slate-500"><Loader2 className="size-4 animate-spin" />Loading templates…</div> : templates.length === 0 ? <div className="col-span-full rounded-xl border border-dashed border-slate-200 p-5 text-sm leading-6 text-slate-500">No saved templates yet. Save this configuration as a private template, or share its gameplay recipe with the workspace.</div> : templates.map((template) => <article key={template.template_id} className="rounded-xl border border-slate-200 p-4"><div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><p className="font-semibold">{template.title}</p><span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", template.visibility === "workspace" ? "bg-[#FFF7ED] text-[#C2410C]" : "bg-slate-100 text-slate-600")}>{template.visibility}</span></div><p className="mt-1 text-xs text-slate-500">v{template.version} · {template.category} · by {template.owner_name || "Studio"}</p></div><button aria-label={template.is_favorited ? "Remove favorite" : "Favorite template"} onClick={() => void favoriteTemplate(template.template_id)} disabled={saving === `favorite-${template.template_id}`} className={cn("rounded-lg p-2 transition", template.is_favorited ? "bg-rose-50 text-rose-600" : "text-slate-400 hover:bg-slate-100 hover:text-slate-700")}><Heart className={cn("size-4", template.is_favorited && "fill-current")} /></button></div><p className="mt-3 min-h-10 text-xs leading-5 text-slate-500">{template.description || "Reusable gameplay configuration with an empty artwork slot."}</p><div className="mt-4 flex items-center justify-between gap-3"><p className="text-xs text-slate-500">{template.favorite_count} saves · {template.fork_count} uses</p><Button size="sm" variant="outline" onClick={() => void useTemplate(template)} disabled={saving === template.template_id}>{saving === template.template_id && <Loader2 className="mr-1.5 size-3.5 animate-spin" />}Use template</Button></div></article>)}</div>
            <aside className="rounded-xl border border-[#FED7AA] bg-[#FFF7ED] p-4"><p className="text-sm font-semibold">Save as template</p><p className="mt-1 text-xs leading-5 text-slate-600">Only the configuration is saved. Uploaded artwork is removed so no client image can leak into another creator’s project.</p><label className="mt-4 block text-xs font-medium text-slate-600">Template name<input value={templateTitle} onChange={(event) => setTemplateTitle(event.target.value)} className="mt-1.5 w-full rounded-lg border border-[#FED7AA] bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-[#F97316]" /></label><label className="mt-3 block text-xs font-medium text-slate-600">Description<input value={templateDescription} onChange={(event) => setTemplateDescription(event.target.value)} placeholder="What future creators can reuse" className="mt-1.5 w-full rounded-lg border border-[#FED7AA] bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-[#F97316]" /></label><label className="mt-3 block text-xs font-medium text-slate-600">Visibility<select value={templateVisibility} onChange={(event) => setTemplateVisibility(event.target.value as Exclude<PlayableTemplateVisibility, "community">)} className="mt-1.5 w-full rounded-lg border border-[#FED7AA] bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-[#F97316]"><option value="private">Private — only me</option><option value="workspace">Workspace — signed-in Studio users</option></select></label><Button className="mt-4 w-full bg-[#F97316] hover:bg-[#EA580C]" onClick={() => void saveTemplate()} disabled={saving === "template"}>{saving === "template" ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Save className="mr-2 size-4" />}Save template</Button></aside>
          </div>
        </section>
      </div>
    </main>
  );
}
