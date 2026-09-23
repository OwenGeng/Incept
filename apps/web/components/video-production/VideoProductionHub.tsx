"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArchiveRestore, ArrowRight, Clapperboard, Copy, Loader2, Search, Sparkles } from "lucide-react";
import { archiveVideoProduction, forkVideoProduction, listVideoProductions, restoreVideoProduction, type VideoProduction } from "@/lib/incept-api";

const WORKSPACE_ID = "wsp_q2";
type Filter = "all" | "preparation" | "script" | "production" | "completed" | "archived";

function phase(project: VideoProduction): Exclude<Filter, "all"> {
  if (project.archived_at) return "archived";
  if (project.final_asset_id || project.stage === "deliver") return "completed";
  if (["generate", "audio", "edit"].includes(project.stage) || project.shots.some((shot) => shot.video_asset_ids.length)) return "production";
  if (["script", "design", "storyboard"].includes(project.stage) || project.shots.length) return "script";
  return "preparation";
}

function phaseLabel(project: VideoProduction) {
  const labels = { preparation: "Preparation", script: "Script", production: "Production", completed: "Completed", archived: "Archived" };
  return labels[phase(project)];
}

function projectType(project: VideoProduction) {
  return project.video_setup.video_type || "Commercial video";
}

function timeAgo(value: string) {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "Recently updated";
  const hours = Math.max(0, Math.floor((Date.now() - then) / 3_600_000));
  if (hours < 1) return "Updated just now";
  if (hours < 24) return `Updated ${hours}h ago`;
  return `Updated ${Math.floor(hours / 24)}d ago`;
}

function projectCover(project: VideoProduction) {
  const words = (project.title || "Untitled production").split(/\s+/).slice(0, 2);
  return words.map((word) => word[0]).join("").toUpperCase() || "LP";
}

function filterLabel(filter: Filter) {
  return filter === "all" ? "All" : filter[0].toUpperCase() + filter.slice(1);
}

export function VideoProductionHub() {
  const searchParams = useSearchParams();
  const [productions, setProductions] = useState<VideoProduction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [busyProjectId, setBusyProjectId] = useState<string | null>(null);

  const loadProductions = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setProductions(await listVideoProductions(WORKSPACE_ID, "mine", true));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load productions. Please try again.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    void loadProductions();
  }, [loadProductions]);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  const counts = useMemo(() => ({
    all: productions.filter((project) => !project.archived_at).length,
    preparation: productions.filter((project) => phase(project) === "preparation").length,
    script: productions.filter((project) => phase(project) === "script").length,
    production: productions.filter((project) => phase(project) === "production").length,
    completed: productions.filter((project) => phase(project) === "completed").length,
    archived: productions.filter((project) => phase(project) === "archived").length,
  }), [productions]);

  const activeProjects = useMemo(() => productions.filter((project) => !project.archived_at && phase(project) !== "completed"), [productions]);
  const featured = activeProjects[0] ?? productions[0];
  const filtered = useMemo(() => productions.filter((project) => {
    const haystack = `${project.title} ${project.brief} ${projectType(project)}`.toLowerCase();
    return (filter === "all" ? !project.archived_at : phase(project) === filter) && haystack.includes(query.trim().toLowerCase());
  }), [productions, filter, query]);

  function replaceProject(next: VideoProduction) {
    setProductions((current) => current.map((project) => project.production_id === next.production_id ? next : project));
  }

  async function archiveProject(project: VideoProduction) {
    if (!window.confirm(`Archive “${project.title || "Untitled production"}”? Its source assets, decisions, and delivery history will remain recoverable.`)) return;
    try {
      setBusyProjectId(project.production_id);
      replaceProject(await archiveVideoProduction(project.production_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not archive the production.");
    } finally { setBusyProjectId(null); }
  }

  async function restoreProject(project: VideoProduction) {
    try {
      setBusyProjectId(project.production_id);
      replaceProject(await restoreVideoProduction(project.production_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not restore the production.");
    } finally { setBusyProjectId(null); }
  }

  async function forkProject(project: VideoProduction) {
    const label = window.prompt("Name this safe variant", "Variant");
    if (label === null) return;
    try {
      setBusyProjectId(project.production_id);
      const branch = await forkVideoProduction(project.production_id, label);
      window.location.assign(`/video-production/projects/${branch.production_id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the variant.");
    } finally { setBusyProjectId(null); }
  }

  return (
    <main className="min-h-[calc(100vh-72px)] bg-white text-[#101318]">
      <div className="mx-auto max-w-[1440px]">
        <section className="border-b border-[#e6e8ec] px-5 pb-7 pt-10 md:px-10 md:pb-9 md:pt-14">
          <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(560px,0.9fr)] xl:items-end">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5f6673]">Linglong · Production desk</p>
              <h1 className="mt-3 max-w-[720px] font-display text-[42px] font-semibold leading-[0.98] tracking-[-0.055em] text-[#101318] sm:text-[58px] md:text-[72px]">
                Make the next frame count.
              </h1>
              <p className="mt-5 text-sm text-[#5f6673]">{counts.completed} productions delivered, {counts.production} in active production.</p>
            </div>
            <div className="grid grid-cols-3 overflow-hidden rounded-2xl border border-[#e6e8ec] bg-white sm:grid-cols-6">
              {(["all", "preparation", "script", "production", "completed", "archived"] as Filter[]).map((item) => (
                <div key={item} className="min-w-0 border-r border-[#e6e8ec] px-3 py-4 last:border-r-0 sm:px-4">
                  <p className="truncate text-[9px] font-semibold uppercase tracking-[0.13em] text-[#5f6673]">{item === "all" ? "Total" : item}</p>
                  <p className="mt-2 font-display text-3xl leading-none tracking-[-0.04em] tabular-nums sm:text-4xl">{counts[item]}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="flex flex-col gap-4 border-b border-[#e6e8ec] px-5 py-4 md:flex-row md:items-center md:justify-between md:px-10">
          <div className="flex gap-2 overflow-x-auto pb-1 md:pb-0">
            {(["all", "preparation", "script", "production", "completed", "archived"] as Filter[]).map((item) => (
              <button key={item} type="button" onClick={() => setFilter(item)} className={`shrink-0 rounded-full border px-3.5 py-2 text-xs font-medium transition ${filter === item ? "border-[#171a20] bg-[#171a20] text-white" : "border-[#e6e8ec] bg-white text-[#5f6673] hover:border-[#d7dbe2] hover:text-[#101318]"}`}>
                {filterLabel(item)} <span className="ml-1 tabular-nums opacity-70">{counts[item]}</span>
              </button>
            ))}
          </div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#5f6673]">Sorted · Recent</p>
        </section>

        {loading ? <div className="grid min-h-80 place-items-center" role="status" aria-live="polite"><Loader2 className="size-5 animate-spin text-[#5f6673]" /><span className="sr-only">Loading productions</span></div> : error ? <div role="alert" className="mx-5 mt-8 rounded-xl border border-[#f0caca] bg-[#fff7f7] p-4 text-sm text-[#b33434] md:mx-10"><p>{error}</p><button type="button" onClick={() => void loadProductions()} className="mt-3 rounded-lg bg-[#171a20] px-3 py-2 text-xs font-semibold text-white hover:bg-[#30343c]">Retry library</button></div> : (
          <>
            {featured ? <section className="px-5 pb-4 pt-9 md:px-10 md:pt-11">
              <p className="mb-5 text-[11px] font-semibold uppercase tracking-[0.15em] text-[#5f6673]">Pick up where you left off · Now editing</p>
              <Link href={`/video-production/projects/${featured.production_id}`} className="group grid overflow-hidden rounded-[22px] border border-[#e6e8ec] bg-white p-3 transition hover:border-[#d7dbe2] hover:shadow-[0_18px_50px_-38px_rgba(16,19,24,.42)] lg:grid-cols-[56%_44%] lg:p-5">
                <div className="relative flex min-h-[270px] overflow-hidden rounded-[15px] bg-[#f2f6ff] p-5 sm:min-h-[350px] lg:min-h-[390px]">
                  <div className="absolute inset-0 opacity-50 [background-image:linear-gradient(#dfe8fb_1px,transparent_1px),linear-gradient(90deg,#dfe8fb_1px,transparent_1px)] [background-size:44px_44px]" />
                  <div className="absolute -right-16 -top-20 size-72 rounded-full bg-[#356fec]/10 blur-3xl" />
                  <p className="relative text-[10px] font-semibold uppercase tracking-[0.16em] text-[#356fec]">Production in progress</p>
                  <div className="relative mt-auto">
                    <span className="mb-4 inline-grid size-12 place-items-center rounded-2xl border border-[#d7dbe2] bg-white text-[#171a20]"><Clapperboard className="size-5" /></span>
                    <h2 className="max-w-[720px] font-display text-4xl font-semibold leading-[0.96] tracking-[-0.055em] text-[#101318] sm:text-5xl">{featured.title || "Untitled production"}</h2>
                  </div>
                </div>
                <div className="flex min-h-[270px] flex-col p-5 sm:p-8 lg:min-h-[390px]">
                  <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#356fec]"><span className="size-1.5 rounded-full bg-[#356fec]" />Continue editing</div>
                  <h3 className="mt-5 font-display text-3xl font-semibold leading-[1] tracking-[-0.045em] sm:text-4xl">{featured.title || "Untitled production"}</h3>
                  <p className="mt-3 line-clamp-2 max-w-xl text-sm leading-6 text-[#5f6673]">{featured.brief || "Set the direction, shape the shots, and bring the final film through review."}</p>
                  <div className="mt-6 border-t border-[#e6e8ec] pt-5">
                    <div className="flex items-center justify-between"><span className="inline-flex items-center gap-2 rounded-full bg-[#f6f8fb] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-[#171a20]"><span className="size-1.5 rounded-full bg-[#356fec]" />{phaseLabel(featured)}</span><span className="text-xs font-medium tabular-nums text-[#5f6673]">{featured.shots.length} shots</span></div>
                    <div className="mt-6 grid grid-cols-3 gap-0 border-t border-[#e6e8ec] pt-5"><div><p className="text-[9px] font-semibold uppercase tracking-[0.13em] text-[#5f6673]">Format</p><p className="mt-2 text-sm font-semibold">{featured.aspect_ratio}</p></div><div className="border-l border-[#e6e8ec] pl-4"><p className="text-[9px] font-semibold uppercase tracking-[0.13em] text-[#5f6673]">Runtime</p><p className="mt-2 text-sm font-semibold">{featured.target_seconds}s</p></div><div className="border-l border-[#e6e8ec] pl-4"><p className="text-[9px] font-semibold uppercase tracking-[0.13em] text-[#5f6673]">Type</p><p className="mt-2 truncate text-sm font-semibold">{projectType(featured)}</p></div></div>
                  </div>
                  <span className="mt-auto inline-flex h-10 w-fit items-center gap-2 rounded-lg bg-[#171a20] px-4 text-xs font-semibold text-white transition group-hover:bg-[#30343c]">Open editor <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" /></span>
                </div>
              </Link>
            </section> : <EmptyProjectState />}

            <section className="px-5 pb-12 pt-8 md:px-10">
              <div className="flex flex-col gap-4 border-b border-[#e6e8ec] pb-4 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-[#5f6673]">All projects · Library</p><h2 className="mt-2 font-display text-2xl font-semibold tracking-[-0.035em]">Production archive</h2></div><label className="relative block"><Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-[#5f6673]" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search projects" className="h-9 w-full rounded-lg border border-[#e6e8ec] bg-[#fafbfc] pl-9 pr-3 text-xs outline-none placeholder:text-[#8b919c] focus:border-[#171a20] sm:w-60" /></label></div>
              {filtered.length ? <div className="mt-3 grid gap-2">{filtered.map((project) => <ProjectRow key={project.production_id} project={project} busy={busyProjectId === project.production_id} onArchive={archiveProject} onRestore={restoreProject} onFork={forkProject} />)}</div> : <p className="py-12 text-center text-sm text-[#5f6673]">No projects match this view.</p>}
            </section>
          </>
        )}
      </div>
    </main>
  );
}

function ProjectRow({ project, busy, onArchive, onRestore, onFork }: {
  project: VideoProduction;
  busy: boolean;
  onArchive: (project: VideoProduction) => Promise<void>;
  onRestore: (project: VideoProduction) => Promise<void>;
  onFork: (project: VideoProduction) => Promise<void>;
}) {
  return <div className="group grid grid-cols-[42px_minmax(0,1fr)_auto] items-center gap-3 rounded-xl border border-transparent px-3 py-3 transition hover:border-[#e6e8ec] hover:bg-[#fafbfc] sm:grid-cols-[42px_minmax(0,1fr)_120px_150px_auto_auto]">
    <span className="grid size-10 place-items-center rounded-xl bg-[#f2f6ff] text-[11px] font-bold text-[#356fec]">{projectCover(project)}</span>
    <Link href={`/video-production/projects/${project.production_id}`} className="min-w-0"><p className="truncate text-sm font-semibold">{project.title || "Untitled production"}</p><p className="mt-0.5 truncate text-[11px] text-[#5f6673]">{projectType(project)} · {project.aspect_ratio} · {project.target_seconds}s{project.archived_at ? " · archived" : ""}</p></Link>
    <span className="hidden text-xs text-[#5f6673] sm:block">{project.shots.length} shots</span>
    <span className="hidden text-xs text-[#5f6673] sm:block">{timeAgo(project.updated_at)}</span>
    <div className="flex items-center gap-1">
      {project.archived_at ? <button type="button" disabled={busy} onClick={() => void onRestore(project)} className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-[11px] font-semibold text-[#171a20] hover:bg-white disabled:opacity-50"><ArchiveRestore className="size-3.5" />Restore</button> : <><button type="button" disabled={busy} onClick={() => void onFork(project)} className="hidden h-8 items-center gap-1 rounded-md px-2 text-[11px] font-semibold text-[#5f6673] hover:bg-white hover:text-[#171a20] sm:inline-flex"><Copy className="size-3.5" />Variant</button><button type="button" disabled={busy} onClick={() => void onArchive(project)} className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-[11px] font-semibold text-[#5f6673] hover:bg-white hover:text-[#171a20] disabled:opacity-50"><ArchiveRestore className="size-3.5" />Archive</button></>}
    </div>
  </div>;
}

function EmptyProjectState() {
  return <section className="px-5 pb-4 pt-9 md:px-10 md:pt-11"><p className="mb-5 text-[11px] font-semibold uppercase tracking-[0.15em] text-[#5f6673]">Start a new production</p><div className="grid min-h-[360px] place-items-center rounded-[22px] border border-dashed border-[#d7dbe2] bg-[#fafbfc] p-8 text-center"><div><span className="mx-auto grid size-12 place-items-center rounded-2xl bg-white text-[#171a20] shadow-sm"><Sparkles className="size-5" /></span><h2 className="mt-5 font-display text-3xl font-semibold tracking-[-0.04em]">Your production desk is ready.</h2><p className="mx-auto mt-3 max-w-md text-sm leading-6 text-[#5f6673]">Create a commercial, original short drama, repair, or CTV production and bring the team from brief to final delivery.</p><Link href="/video-production/new" className="mt-6 inline-flex h-10 items-center gap-2 rounded-lg bg-[#171a20] px-4 text-xs font-semibold text-white hover:bg-[#30343c]"><Sparkles className="size-3.5" />Create project</Link></div></div></section>;
}
