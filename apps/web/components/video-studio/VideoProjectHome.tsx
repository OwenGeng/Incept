"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownUp, ArrowUp, Download, Edit3, Folder, FolderOpen, FolderPlus, Grid2X2, List, Settings, Trash2 } from "lucide-react";
import { videoStudioApi } from "./api";
import type { ProjectSummary } from "./types";
import { useStudioLanguage } from "./useStudioLanguage";
import { StudioSettingsDialog } from "./StudioSettingsDialog";

function escapeHtml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

export function VideoProjectHome() {
  const router = useRouter();
  const { language, setLanguage, isChinese } = useStudioLanguage();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [prompt, setPrompt] = useState("");
  const [creating, setCreating] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [descending, setDescending] = useState(true);
  const importInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setProjects(await videoStudioApi.listProjects()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Failed to load projects"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const sortedProjects = useMemo(() => [...projects].sort((left, right) => {
    const delta = new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
    return descending ? delta : -delta;
  }), [descending, projects]);

  const createProject = async (event?: FormEvent, usePrompt = true) => {
    event?.preventDefault();
    if (creating) return;
    setCreating(true);
    setError("");
    try {
      const brief = usePrompt ? prompt.trim() : "";
      const name = brief ? brief.slice(0, 32) : (isChinese ? "未命名工作区" : "Untitled workspace");
      const project = await videoStudioApi.createProject(name, brief);
      if (brief) {
        await videoStudioApi.saveDocument(project.id, `<h1>${escapeHtml(name)}</h1><p>${escapeHtml(brief).replaceAll("\n", "<br>")}</p>`);
        try {
          await videoStudioApi.runAgent(project.id, brief, null, () => undefined, { agentId: "workflow" });
        } catch {
          // The project and brief are already durable. Open the workspace so
          // the user can retry Agent work without losing the initial request.
        }
      }
      router.push(`/video/${project.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create project");
      setCreating(false);
    }
  };

  const renameProject = async (project: ProjectSummary) => {
    const name = window.prompt(isChinese ? "请输入项目名称" : "Enter a project name", project.name)?.trim();
    if (!name || name === project.name) return;
    const updated = await videoStudioApi.updateProject(project.id, { name });
    setProjects((items) => items.map((item) => item.id === project.id ? updated : item));
  };

  const removeProject = async (project: ProjectSummary) => {
    if (!window.confirm(isChinese ? `确定删除“${project.name}”吗？` : `Delete “${project.name}”?`)) return;
    await videoStudioApi.deleteProject(project.id);
    setProjects((items) => items.filter((item) => item.id !== project.id));
  };

  const importProject = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    try {
      const project = await videoStudioApi.importProject(file);
      router.push(`/video/${project.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not import project");
    } finally {
      event.target.value = "";
    }
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-white text-[#303133]">
      <CreativeBackground />
      <header className="relative z-10 flex h-[72px] items-center justify-between px-5 sm:px-14">
        <button onClick={() => setShowSettings(true)} className="inline-flex h-10 items-center gap-2 rounded-full border border-[#ebeef5] bg-white px-5 text-sm shadow-sm transition hover:border-[#c4b5fd]"><Settings className="size-4" />{isChinese ? "设置" : "Settings"}</button>
        <div className="flex items-center gap-3">
          <div className="flex h-10 items-center rounded-full border border-[#ebeef5] bg-white p-1 shadow-sm"><button onClick={() => setLanguage("zh-CN")} className={`rounded-full px-3 py-1.5 text-xs ${language === "zh-CN" ? "bg-[#f2eafe] font-semibold text-[#8b5cf6]" : "text-[#909399]"}`}>中文</button><button onClick={() => setLanguage("en-US")} className={`rounded-full px-3 py-1.5 text-xs ${language === "en-US" ? "bg-[#f2eafe] font-semibold text-[#8b5cf6]" : "text-[#909399]"}`}>EN</button></div>
          <Link href="/" className="inline-flex h-10 items-center rounded-full border border-[#ebeef5] bg-white px-5 text-sm no-underline shadow-sm">{isChinese ? "返回 LinglongLab" : "Back to LinglongLab"}</Link>
        </div>
      </header>

      <div className="relative z-[1] px-5 pb-14 pt-6 sm:px-14">
        <section className="mx-auto mb-14 mt-8 max-w-[800px] sm:mt-12" aria-label={isChinese ? "创建项目" : "Create project"}>
          <div className="mb-9 flex items-center justify-center gap-4">
            <Image src="/logo.png" alt="LinglongLab" width={48} height={48} className="size-12 object-contain" priority />
            <h1 className="text-[38px] font-semibold tracking-[-1px]">LinglongLab</h1>
          </div>
          <form onSubmit={(event) => void createProject(event)} className="relative">
            <div className="absolute bottom-full left-3 flex h-8 items-center gap-1 pr-10 text-[13px] text-[#8b5cf6]"><span>{isChinese ? "灵感创作模式" : "Create from an idea"}</span><span className="text-3xl font-light leading-none">↝</span></div>
            <div className="overflow-hidden rounded-[28px] border border-[#ebeef5] bg-white shadow-[0_10px_35px_rgba(80,60,120,.08)] focus-within:border-[#c4b5fd]">
              <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={5} disabled={creating} className="block w-full resize-none border-0 bg-transparent px-5 py-6 text-[15px] leading-7 outline-none placeholder:text-[#a8abb2]" placeholder={isChinese ? "为你的主角设计独特的外形和性格…" : "Design a distinctive look and personality for your lead…"} aria-label={isChinese ? "创作描述" : "Creative brief"} />
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#f2f3f5] bg-[#fafafa] px-5 py-3">
                <button type="button" onClick={() => void createProject(undefined, false)} className="inline-flex items-center gap-2 text-sm text-[#606266]"><Folder className="size-4" />{isChinese ? "工作目录" : "Workspace"}<span className="text-xs">⌄</span></button>
                <div className="ml-auto flex items-center gap-3"><button type="button" onClick={() => setShowSettings(true)} className="flex max-w-[190px] items-center gap-2 text-xs text-[#606266]"><span className="flex size-4 items-center justify-center rounded-full bg-[#f2eafe] text-[10px] text-[#8b5cf6]">?</span><span className="truncate">LinglongLab Agent</span><span>·</span><span>{isChinese ? "默认" : "Default"}</span><span>⌄</span></button><button type="submit" disabled={creating} aria-label={isChinese ? "发送" : "Send"} className="flex size-9 items-center justify-center rounded-full bg-[#b881ee] text-white shadow-sm disabled:opacity-50"><ArrowUp className="size-4" /></button></div>
              </div>
            </div>
          </form>
        </section>

        <section className="mx-auto max-w-[1040px]" aria-labelledby="video-projects-title">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#ebeef5] pb-4">
            <h2 id="video-projects-title" className="text-lg font-semibold">{isChinese ? "项目列表" : "Projects"}</h2>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => importInput.current?.click()} className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#dcdfe6] bg-white px-4 text-sm"><FolderOpen className="size-4" />{isChinese ? "导入项目" : "Import project"}</button><input ref={importInput} type="file" accept="application/zip,.zip" onChange={(event) => void importProject(event)} className="hidden" />
              <button onClick={() => void createProject(undefined, false)} className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#dcdfe6] bg-white px-4 text-sm"><FolderPlus className="size-4" />{isChinese ? "添加项目" : "Add project"}</button>
              <button onClick={() => setDescending((value) => !value)} aria-label={descending ? (isChinese ? "按时间降序" : "Newest first") : (isChinese ? "按时间升序" : "Oldest first")} className="flex size-9 items-center justify-center rounded-full border border-[#dcdfe6] bg-white"><ArrowDownUp className="size-4" /></button>
              <div className="flex h-9 overflow-hidden rounded-lg border border-[#dcdfe6] bg-white"><button onClick={() => setViewMode("grid")} aria-label={isChinese ? "网格视图" : "Grid view"} className={`px-3 ${viewMode === "grid" ? "bg-[#7c3aed] text-white" : "text-[#606266]"}`}><Grid2X2 className="size-4" /></button><button onClick={() => setViewMode("list")} aria-label={isChinese ? "列表视图" : "List view"} className={`px-3 ${viewMode === "list" ? "bg-[#7c3aed] text-white" : "text-[#606266]"}`}><List className="size-4" /></button></div>
            </div>
          </div>
          {error && <p role="alert" className="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
          {loading ? <div className="mt-4 grid gap-4 sm:grid-cols-3">{[0, 1, 2].map((item) => <div key={item} className="h-28 animate-pulse rounded-xl border border-[#ebeef5] bg-white/80" />)}</div> : <div className={`mt-4 grid gap-4 ${viewMode === "grid" ? "sm:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"}`}>
            {sortedProjects.map((project) => <article key={project.id} className="group relative rounded-xl border border-[#ebeef5] bg-white shadow-sm transition hover:shadow-md"><button onClick={() => router.push(`/video/${project.id}`)} className="flex w-full items-start gap-3 px-5 py-5 pr-28 text-left"><Folder className="mt-0.5 size-7 shrink-0 text-[#8b5cf6]" /><span className="flex min-w-0 flex-col gap-1.5"><span className="truncate font-semibold">{project.name}</span><span className="truncate text-[13px] text-[#606266]">LinglongLab Cloud · {project.id.slice(0, 8)}</span><span className="text-xs text-[#909399]">{isChinese ? "最近打开" : "Last opened"} {new Date(project.updated_at).toLocaleString()}</span></span></button><div className="absolute right-2 top-3 flex"><a href={videoStudioApi.projectArchiveUrl(project.id)} title={isChinese ? "导出项目" : "Export project"} className="p-2 text-[#909399] hover:text-[#7c3aed]"><Download className="size-4" /></a><button onClick={() => void renameProject(project)} title={isChinese ? "重命名" : "Rename"} className="p-2 text-[#909399] hover:text-[#7c3aed]"><Edit3 className="size-4" /></button><button onClick={() => void removeProject(project)} title={isChinese ? "删除" : "Delete"} className="p-2 text-[#909399] hover:text-red-500"><Trash2 className="size-4" /></button></div></article>)}
          </div>}
        </section>
      </div>
      <StudioSettingsDialog open={showSettings} onClose={() => setShowSettings(false)} isChinese={isChinese} />
    </main>
  );
}

function CreativeBackground() {
  const frames = [
    { left: "4%", top: "22%", width: 132, delay: "-1s", rotate: "-7deg" },
    { left: "17%", top: "72%", width: 104, delay: "-5s", rotate: "5deg" },
    { left: "76%", top: "13%", width: 118, delay: "-8s", rotate: "6deg" },
    { left: "88%", top: "48%", width: 148, delay: "-3s", rotate: "-5deg" },
    { left: "67%", top: "82%", width: 112, delay: "-10s", rotate: "4deg" },
  ];

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden bg-white">
      <div className="absolute inset-[-12%] bg-[radial-gradient(ellipse_48%_36%_at_38%_8%,rgba(124,58,237,.15),transparent),radial-gradient(ellipse_34%_38%_at_94%_58%,rgba(14,165,233,.10),transparent),radial-gradient(ellipse_32%_34%_at_5%_82%,rgba(45,212,191,.09),transparent)]" />
      <div className="video-frame-grid absolute inset-0 opacity-30" />
      <div className="absolute left-1/2 top-[17%] h-[420px] w-[760px] -translate-x-1/2 rounded-full bg-[radial-gradient(ellipse,rgba(255,255,255,.96),rgba(255,255,255,.3)_52%,transparent_72%)] blur-xl" />

      {frames.map((frame, index) => (
        <div
          key={index}
          className="video-ghost-frame absolute aspect-video rounded-[18px] border border-white/80 bg-white/45 p-2 shadow-[0_18px_55px_rgba(76,58,130,.08)] backdrop-blur-sm"
          style={{ left: frame.left, top: frame.top, width: frame.width, animationDelay: frame.delay, "--frame-rotate": frame.rotate } as React.CSSProperties}
        >
          <div className="h-full rounded-[12px] bg-[linear-gradient(135deg,rgba(124,58,237,.13),rgba(14,165,233,.08)_50%,rgba(45,212,191,.12))]">
            <span className="absolute bottom-3 left-3 h-1.5 w-1.5 rounded-full bg-[#8b5cf6]/50" />
            <span className="absolute bottom-3 left-6 h-1 w-10 rounded-full bg-[#8b5cf6]/15" />
          </div>
        </div>
      ))}

      <div className="video-timeline absolute bottom-[9%] left-1/2 h-10 w-[min(72vw,760px)] -translate-x-1/2 rounded-2xl border border-white/75 bg-white/45 px-4 shadow-[0_16px_50px_rgba(76,58,130,.06)] backdrop-blur-sm">
        <div className="absolute left-4 right-4 top-1/2 h-px -translate-y-1/2 bg-gradient-to-r from-transparent via-[#8b5cf6]/30 to-transparent" />
        {[12, 29, 48, 67, 84].map((left) => <span key={left} className="absolute top-1/2 size-2 -translate-y-1/2 rounded-[3px] border border-[#8b5cf6]/30 bg-white" style={{ left: `${left}%` }} />)}
        <span className="video-playhead absolute bottom-1 top-1 w-px bg-gradient-to-b from-[#7c3aed] to-[#0ea5e9] shadow-[0_0_10px_rgba(124,58,237,.45)]" />
      </div>

      <style jsx>{`
        .video-frame-grid {
          background-image: linear-gradient(rgba(124, 58, 237, .035) 1px, transparent 1px), linear-gradient(90deg, rgba(14, 165, 233, .03) 1px, transparent 1px);
          background-size: 42px 42px;
          mask-image: linear-gradient(to bottom, #000, transparent 88%);
        }
        .video-ghost-frame {
          animation: frameDrift 12s ease-in-out infinite alternate;
        }
        .video-timeline {
          animation: timelineBreathe 7s ease-in-out infinite;
        }
        .video-playhead {
          animation: playheadTravel 8s cubic-bezier(.45, 0, .55, 1) infinite;
        }
        @keyframes frameDrift {
          from { transform: translate3d(0, -6px, 0) rotate(var(--frame-rotate)); opacity: .42; }
          to { transform: translate3d(12px, 12px, 0) rotate(0deg); opacity: .8; }
        }
        @keyframes timelineBreathe {
          0%, 100% { transform: translateX(-50%) scaleX(.97); opacity: .55; }
          50% { transform: translateX(-50%) scaleX(1); opacity: .9; }
        }
        @keyframes playheadTravel {
          0%, 10% { left: 4%; opacity: 0; }
          18% { opacity: 1; }
          82% { opacity: 1; }
          90%, 100% { left: 96%; opacity: 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          .video-ghost-frame, .video-timeline, .video-playhead { animation: none; }
          .video-playhead { left: 52%; opacity: .35; }
        }
      `}</style>
    </div>
  );
}
