"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, FilePlus2, LayoutTemplate, Loader2, Play, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { listPlayableProjects, listPlayableTemplates, type PlayableProjectRecord, type PlayableTemplateRecord } from "@/lib/gaming-playable";

const WORKSPACE_ID = "wsp_q2";

function formatUpdated(date: string) {
  const parsed = new Date(date);
  return Number.isNaN(parsed.valueOf()) ? "Recently" : parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function projectState(project: PlayableProjectRecord) {
  return project.schema.assets.backgroundDataUri ? "Ready to playtest" : "Needs assets";
}

export function GamingPlayableHub() {
  const [projects, setProjects] = useState<PlayableProjectRecord[]>([]);
  const [templates, setTemplates] = useState<PlayableTemplateRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([listPlayableProjects(WORKSPACE_ID), listPlayableTemplates(WORKSPACE_ID)])
      .then(([nextProjects, nextTemplates]) => { if (active) { setProjects(nextProjects); setTemplates(nextTemplates); } })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Could not load your playable workspace."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const states = useMemo(() => ({
    drafts: projects.filter((project) => !project.schema.assets.backgroundDataUri).length,
    playtest: projects.filter((project) => Boolean(project.schema.assets.backgroundDataUri)).length,
  }), [projects]);

  return <main className="mx-auto max-w-[1440px] px-5 py-8 md:px-8">
    <div className="flex flex-wrap items-end justify-between gap-5"><div><p className="text-sm font-medium text-[#C2410C]">GamingPlayable workspace</p><h1 className="mt-1 text-3xl font-semibold tracking-tight">My Playables</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Turn approved game art and gameplay ideas into private, editable HTML5 playable projects.</p></div><Button asChild className="h-10 bg-[#F97316] px-4 hover:bg-[#EA580C]"><Link href="/gaming-playable/new"><FilePlus2 className="mr-2 size-4" />New playable</Link></Button></div>
    <section className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Project status overview">
      {[["Draft", states.drafts, "Projects waiting for a first saved state"], ["Needs assets", states.drafts, "Projects without a linked background asset"], ["Ready to playtest", states.playtest, "Projects with a preview-ready art slot"], ["Ready to deliver", 0, "Only shown after the delivery gate passes"]].map(([label, value, detail]) => <article key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_8px_20px_rgba(15,23,42,0.03)]"><p className="text-sm font-medium text-slate-500">{label}</p><p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p><p className="mt-2 text-xs leading-5 text-slate-500">{detail}</p></article>)}
    </section>
    {error && <p className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
    <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_8px_20px_rgba(15,23,42,0.03)] md:p-6"><div className="flex items-center justify-between gap-4"><div><h2 className="text-lg font-semibold">Recent playables</h2><p className="mt-1 text-sm text-slate-500">Continue a private project or start a new draft.</p></div>{projects.length > 0 && <Link href="/gaming-playable/new" className="text-sm font-semibold text-[#C2410C] hover:text-[#EA580C]">New draft</Link>}</div>
      {loading ? <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-slate-500"><Loader2 className="size-4 animate-spin" />Loading projects…</div> : projects.length === 0 ? <div className="mt-5 flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-[#FED7AA] bg-[#FFF7ED] px-6 text-center"><span className="flex size-12 items-center justify-center rounded-2xl bg-[#FFEDD5] text-[#EA580C]"><Play className="size-6" /></span><h3 className="mt-4 text-base font-semibold">Start your first playable</h3><p className="mt-2 max-w-md text-sm leading-6 text-slate-600">Bring a gameplay idea, screenshots, a recording, or a logo. We’ll turn it into a private project with an editable gameplay loop.</p><div className="mt-5 flex flex-wrap justify-center gap-3"><Button asChild className="bg-[#F97316] hover:bg-[#EA580C]"><Link href="/gaming-playable/new">New playable</Link></Button><Button asChild variant="outline" className="border-[#FED7AA] bg-white hover:bg-[#FFF7ED]"><Link href="/gaming-playable/templates">Browse templates</Link></Button></div></div> : <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{projects.slice(0, 6).map((project) => <Link key={project.project_id} href={`/gaming-playable/projects/${project.project_id}`} className="group rounded-xl border border-slate-200 p-4 transition hover:-translate-y-0.5 hover:border-[#FDBA74] hover:shadow-sm"><div className="flex items-start justify-between gap-3"><span className="rounded-full bg-[#FFF7ED] px-2.5 py-1 text-xs font-semibold text-[#C2410C]">{projectState(project)}</span><span className="text-xs text-slate-400">{formatUpdated(project.updated_at)}</span></div><h3 className="mt-8 text-base font-semibold group-hover:text-[#C2410C]">{project.title}</h3><p className="mt-1 text-sm text-slate-500">{project.schema.gameplay.template} gameplay · {project.schema.metadata.orientation}</p><span className="mt-5 flex items-center gap-1 text-sm font-semibold text-[#C2410C]">Continue <ArrowRight className="size-4" /></span></Link>)}</div>}</section>
    <section className="mt-8"><div className="flex items-end justify-between gap-4"><div><h2 className="text-lg font-semibold">Popular templates</h2><p className="mt-1 text-sm text-slate-500">Reusable gameplay configurations. Customer assets are never included.</p></div><Link href="/gaming-playable/templates" className="text-sm font-semibold text-[#C2410C] hover:text-[#EA580C]">View library</Link></div>{loading ? null : templates.length === 0 ? <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">No workspace template is available yet. Save a safe, asset-free gameplay recipe from a project to make the first one.</div> : <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{templates.slice(0, 3).map((template) => <article key={template.template_id} className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex size-10 items-center justify-center rounded-xl bg-[#FFEDD5] text-[#C2410C]"><Sparkles className="size-5" /></div><h3 className="mt-5 font-semibold">{template.title}</h3><p className="mt-2 min-h-10 text-sm leading-5 text-slate-500">{template.description || "Reusable gameplay configuration with an empty artwork slot."}</p><p className="mt-4 text-xs text-slate-500">{template.favorite_count} saves · {template.fork_count} uses · {template.category}</p></article>)}</div>}</section>
  </main>;
}
