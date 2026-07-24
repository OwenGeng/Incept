// Client-safe pipeline API — no Node.js imports

export type PipelineStatus = "idle" | "running" | "success" | "failed";

export type PipelineStatusResponse = {
  status: PipelineStatus;
  started_at: number | null;
  finished_at: number | null;
  message: string;
};

export function runPipeline(): Promise<PipelineStatusResponse> {
  return fetch("/api/incept/api/v1/supply-smb/run-pipeline", { method: "POST" }).then(
    (r) => r.json()
  );
}

export function getPipelineStatus(): Promise<PipelineStatusResponse> {
  return fetch("/api/incept/api/v1/supply-smb/pipeline-status").then(
    (r) => r.json()
  );
}
