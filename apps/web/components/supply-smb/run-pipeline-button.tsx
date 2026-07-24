"use client";

import { useEffect, useRef, useState } from "react";
import { Play, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { getPipelineStatus, runPipeline, type PipelineStatus } from "@/lib/pipeline-api";

const POLL_INTERVAL = 6000;

export function RunPipelineButton() {
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [message, setMessage] = useState("");
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  };

  const applyResponse = (data: Awaited<ReturnType<typeof getPipelineStatus>>) => {
    setStatus(data.status);
    setMessage(data.message);
    if (data.started_at) setStartedAt(data.started_at);
    if (data.status !== "running") stopPolling();
  };

  const startPolling = () => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        applyResponse(await getPipelineStatus());
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL);
  };

  // On mount: check if a pipeline is already running from a previous session
  useEffect(() => {
    getPipelineStatus().then((data) => {
      applyResponse(data);
      if (data.status === "running") startPolling();
    });
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRun = async () => {
    if (status === "running") return;
    setStatus("running");
    setMessage("Starting pipeline…");
    try {
      applyResponse(await runPipeline());
      startPolling();
    } catch {
      setStatus("failed");
      setMessage("Failed to start pipeline.");
    }
  };

  const elapsedMin =
    status === "running" && startedAt
      ? Math.floor((Date.now() / 1000 - startedAt) / 60)
      : null;

  const icon =
    status === "running" ? (
      <Loader2 className="size-3.5 animate-spin" />
    ) : status === "success" ? (
      <CheckCircle2 className="size-3.5 text-[#16A34A]" />
    ) : status === "failed" ? (
      <XCircle className="size-3.5 text-destructive" />
    ) : (
      <Play className="size-3.5" />
    );

  const label =
    status === "running"
      ? elapsedMin !== null && elapsedMin > 0
        ? `Running… ${elapsedMin}m`
        : "Running…"
      : status === "success"
        ? "Completed"
        : status === "failed"
          ? "Failed"
          : "Run Pipeline";

  return (
    <button
      onClick={handleRun}
      disabled={status === "running"}
      title={message || "Trigger save_cold_prospect_table pipeline"}
      className="flex items-center gap-1.5 rounded-full border border-border bg-background px-3.5 py-1.5 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
    >
      {icon}
      {label}
    </button>
  );
}
