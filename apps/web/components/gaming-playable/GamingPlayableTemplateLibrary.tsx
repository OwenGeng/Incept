"use client";

// `useTemplate` is a click handler retained for the deferred product surface,
// not a React Hook. The current compact source shape confuses the hook-name
// heuristic; this module is not part of the Image + Video release profile.
/* eslint-disable react-hooks/rules-of-hooks */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Heart, Loader2, Sparkles, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { forkPlayableTemplate, listPlayableTemplates, togglePlayableTemplateFavorite, type PlayableTemplateRecord } from "@/lib/gaming-playable";

const WORKSPACE_ID = "wsp_q2";

export function GamingPlayableTemplateLibrary() {
  const router = useRouter();
  const [templates, setTemplates] = useState<PlayableTemplateRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try { setTemplates(await listPlayableTemplates(WORKSPACE_ID)); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load templates."); }
    finally { setLoading(false); }
  };

  useEffect(() => { void refresh(); }, []);

  const favorite = async (templateId: string) => {
    setWorkingId(`favorite-${templateId}`);
    try { const updated = await togglePlayableTemplateFavorite(templateId); setTemplates((current) => current.map((template) => template.template_id === templateId ? updated : template).sort((a, b) => b.favorite_count - a.favorite_count || b.fork_count - a.fork_count)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update this template."); }
    finally { setWorkingId(null); }
  };

  const useTemplate = async (template: PlayableTemplateRecord) => {
    setWorkingId(template.template_id);
    try { const project = await forkPlayableTemplate(template.template_id, `${template.title} copy`); router.push(`/gaming-playable/projects/${project.project_id}`); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create a project from this template."); setWorkingId(null); }
  };

  return <main className="mx-auto max-w-[1440px] px-5 py-8 md:px-8"><div><p className="text-sm font-medium text-[#C2410C]">Reusable gameplay recipes</p><h1 className="mt-1 text-3xl font-semibold tracking-tight">Templates</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Templates contain gameplay configuration and required slots only. They do not include a creator’s uploaded artwork, video, logos, or source files.</p></div>{error && <p className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}<section className="mt-8">{loading ? <div className="flex min-h-64 items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white text-sm text-slate-500"><Loader2 className="size-4 animate-spin" />Loading templates…</div> : templates.length === 0 ? <div className="flex min-h-72 flex-col items-center justify-center rounded-2xl border border-dashed border-[#FED7AA] bg-white px-6 text-center"><span className="flex size-12 items-center justify-center rounded-2xl bg-[#FFEDD5] text-[#C2410C]"><Sparkles className="size-6" /></span><h2 className="mt-4 text-lg font-semibold">No reusable templates yet</h2><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">Open a playable project and save its gameplay configuration as a private or workspace template. Customer art will be removed automatically.</p></div> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{templates.map((template) => <article key={template.template_id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_8px_20px_rgba(15,23,42,0.03)]"><div className="flex items-start justify-between gap-3"><span className="flex size-10 items-center justify-center rounded-xl bg-[#FFEDD5] text-[#C2410C]"><Sparkles className="size-5" /></span><button aria-label={template.is_favorited ? "Remove favorite" : "Favorite template"} onClick={() => void favorite(template.template_id)} disabled={workingId === `favorite-${template.template_id}`} className={cn("rounded-lg p-2 transition", template.is_favorited ? "bg-rose-50 text-rose-600" : "text-slate-400 hover:bg-slate-100 hover:text-slate-700")}><Heart className={cn("size-4", template.is_favorited && "fill-current")} /></button></div><div className="mt-6 flex items-center gap-2"><h2 className="font-semibold">{template.title}</h2><span className="rounded-full bg-[#FFF7ED] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#C2410C]">{template.visibility}</span></div><p className="mt-2 min-h-12 text-sm leading-5 text-slate-500">{template.description || "Reusable gameplay configuration with an empty background-art slot."}</p><p className="mt-4 flex items-center gap-1.5 text-xs text-slate-500"><Users className="size-3.5" />{template.favorite_count} saves · {template.fork_count} uses · {template.category}</p><div className="mt-5 flex items-center justify-between gap-3"><span className="text-xs text-slate-500">v{template.version} · slots only</span><Button size="sm" onClick={() => void useTemplate(template)} disabled={workingId === template.template_id} className="bg-[#F97316] hover:bg-[#EA580C]">{workingId === template.template_id && <Loader2 className="mr-1.5 size-3.5 animate-spin" />}Use template</Button></div></article>)}</div>}</section></main>;
}
