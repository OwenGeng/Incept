"use client";

import { useCallback, useEffect, useState } from "react";
import type { AssetSummary, JobSummary } from "@incept/shared";
import { listAssets, listJobs } from "@/lib/incept-api";
import { ComfyUIView } from "./ComfyUIView";

const DEFAULT_WORKSPACE_ID = "wsp_q2";

/**
 * A product-level shell, deliberately separate from Studio. It shares the
 * workspace asset library and API, while the canvas's own rail is the only
 * navigation within this focused production surface.
 */
export function ComfyWorkflowShell() {
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [jobs, setJobs] = useState<JobSummary[]>([]);

  const refresh = useCallback(() => {
    void Promise.all([listAssets(DEFAULT_WORKSPACE_ID, "mine"), listJobs(DEFAULT_WORKSPACE_ID, "mine")])
      .then(([nextAssets, nextJobs]) => { setAssets(nextAssets); setJobs(nextJobs); })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 5000);
    return () => window.clearInterval(id);
  }, [refresh]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <ComfyUIView
        activeWorkspaceId={DEFAULT_WORKSPACE_ID}
        liveAssets={assets}
        liveJobs={jobs}
      />
    </div>
  );
}
