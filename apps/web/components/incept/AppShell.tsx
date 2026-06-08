"use client";

import { useEffect, useRef, useState } from "react";
import { Sidebar } from "./Sidebar";
import type { AppView } from "./Sidebar";
import { Workspace } from "./Workspace";
import type { AssetSummary, CreativeThreadSummary, InceptUser, JobSummary, WorkspaceSummary } from "@incept/shared";
import { getCurrentUser, getJob, listAssets, listJobs, listThreads, listWorkspaces } from "@/lib/incept-api";

const ANONYMOUS_USER: InceptUser = { id: "anon", name: "User", email: "", role: "user", team: "nbs" };

export function AppShell() {
  const [activeView, setActiveView] = useState<AppView>("Home");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [liveAssets, setLiveAssets] = useState<AssetSummary[]>([]);
  const [liveJobs, setLiveJobs] = useState<JobSummary[]>([]);
  const [liveThreads, setLiveThreads] = useState<CreativeThreadSummary[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState("wsp_q2");
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<InceptUser>(ANONYMOUS_USER);

  // Track which job IDs need polling
  const pollingJobs = useRef<Set<string>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let mounted = true;
    async function boot() {
      try {
        const [user, assets, jobs, threads, wsList] = await Promise.all([
          getCurrentUser(),
          listAssets("wsp_q2"),
          listJobs(),
          listThreads("wsp_q2"),
          listWorkspaces(),
        ]);
        if (!mounted) return;
        if (user) setCurrentUser(user);
        setLiveAssets(assets);
        setLiveJobs(jobs);
        setLiveThreads(threads);
        setWorkspaces(wsList);

        // Resume polling for any still-running jobs from a previous session
        for (const job of jobs) {
          if (job.status === "running" || job.status === "queued") {
            pollingJobs.current.add(job.jobId ?? job.id);
          }
        }
        if (pollingJobs.current.size > 0) startPolling();
      } catch {
        if (!mounted) return;
      }
    }
    void boot();
    return () => { mounted = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reload assets when workspace changes
  useEffect(() => {
    let mounted = true;
    Promise.all([listAssets(activeWorkspaceId), listThreads(activeWorkspaceId)]).then(([assets, threads]) => {
      if (!mounted) return;
      setLiveAssets(assets);
      setLiveThreads(threads);
    }).catch(() => {});
    return () => { mounted = false; };
  }, [activeWorkspaceId]);

  function startPolling() {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(async () => {
      if (pollingJobs.current.size === 0) {
        clearInterval(intervalRef.current!);
        intervalRef.current = null;
        return;
      }
      const ids = Array.from(pollingJobs.current);
      const results = await Promise.all(ids.map((id) => getJob(id)));
      let anyCompleted = false;
      setLiveJobs((prev) => {
        const next = [...prev];
        for (const updated of results) {
          if (!updated) continue;
          const idx = next.findIndex((j) => (j.jobId ?? j.id) === (updated.jobId ?? updated.id));
          if (idx >= 0) next[idx] = updated;
          if (
            updated.status === "completed" ||
            updated.status === "failed" ||
            updated.status === "needs_clarification"
          ) {
            pollingJobs.current.delete(updated.jobId ?? updated.id);
            anyCompleted = true;
          }
        }
        return next;
      });
      if (anyCompleted) {
        const [assets, threads] = await Promise.all([
          listAssets(activeWorkspaceId),
          listThreads(activeWorkspaceId),
        ]);
        setLiveAssets(assets);
        setLiveThreads(threads);
      }
    }, 2500);
  }

  function trackJob(job: JobSummary) {
    if (job.status === "running" || job.status === "queued") {
      pollingJobs.current.add(job.jobId ?? job.id);
      startPolling();
    }
  }

  function handleThreadSelect(workspaceId: string, threadId: string) {
    setActiveWorkspaceId(workspaceId);
    setActiveThreadId(threadId);
    setActiveView("Create");
    setSidebarOpen(false);
  }

  return (
    <div className="relative flex min-h-screen bg-background text-foreground">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar — sticky, self-manages collapse width */}
      <div className={sidebarOpen ? "max-[980px]:block" : "max-[980px]:hidden"}>
        <Sidebar
          activeView={activeView}
          onViewChange={(v) => { setActiveView(v); setSidebarOpen(false); }}
        />
      </div>

      <Workspace
        activeView={activeView}
        onViewChange={setActiveView}
        liveAssets={liveAssets}
        setLiveAssets={setLiveAssets}
        liveJobs={liveJobs}
        setLiveJobs={setLiveJobs}
        liveThreads={liveThreads}
        setLiveThreads={setLiveThreads}
        currentUser={currentUser}
        activeWorkspaceId={activeWorkspaceId}
        activeThreadId={activeThreadId}
        onThreadSelect={(id) => setActiveThreadId(id)}
        workspaces={workspaces}
        onJobCreated={trackJob}
        onMobileMenuOpen={() => setSidebarOpen(true)}
        onThreadSelectFromHome={handleThreadSelect}
      />
    </div>
  );
}
