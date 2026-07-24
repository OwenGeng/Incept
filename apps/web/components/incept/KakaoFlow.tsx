"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronRight, Loader2, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { cleanKakaoImage, getJob, listAssets, uploadAsset } from "@/lib/incept-api";

interface KakaoSource {
  url: string;
  name: string;
  file: File;
  uploadedId: string | null;
}

interface KakaoCleaned {
  sourceIdx: number;
  assetId: string;
  url: string;
  title: string;
  accepted: boolean;
  error?: string;
}

type CleanStatus = "pending" | "processing" | "done" | "error";
type Step = "upload" | "cleaning" | "confirm";

const STEPS: { key: Step; label: string }[] = [
  { key: "upload", label: "Upload & Clean" },
  { key: "confirm", label: "Confirm" },
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollForCleanedAsset(
  jobId: string,
  workspaceId: string,
): Promise<{ id: string; url: string }> {
  for (let i = 0; i < 90; i++) {
    await sleep(2000);
    const job = await getJob(jobId);
    if (!job) throw new Error("Job disappeared");
    if (job.status === "failed") throw new Error(job.message ?? "Cleanup failed");
    if (job.status === "needs_clarification") {
      throw new Error(
        job.clarificationQuestion ??
        job.message ??
        "AI could not automatically locate the elements to remove.",
      );
    }
    if (job.status === "completed") {
      const assets = await listAssets(workspaceId);
      const asset = assets.find((a) => a.jobId === jobId);
      if (!asset) throw new Error("Output asset not found");
      return { id: asset.id, url: asset.url };
    }
  }
  throw new Error("Cleanup timed out");
}

export function KakaoFlow({
  activeWorkspaceId,
  currentThreadId,
  onThreadResolved,
  onAssetsCreated,
  onOpenBuilder,
}: {
  activeWorkspaceId: string;
  currentThreadId?: string | null;
  onThreadResolved?: (threadId: string) => void;
  onAssetsCreated: () => void;
  onOpenBuilder: (assets: Array<{
    id: string;
    url: string;
    title: string;
    type: "image";
    threadId?: string | null;
  }>) => void;
}) {
  const [step, setStep] = useState<Step>("upload");
  const [sources, setSources] = useState<KakaoSource[]>([]);
  const [cleaned, setCleaned] = useState<KakaoCleaned[]>([]);
  const [cleanStatus, setCleanStatus] = useState<Record<number, CleanStatus>>({});
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [resolvedThreadId, setResolvedThreadId] = useState<string | null>(currentThreadId ?? null);

  const sourceInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setResolvedThreadId(currentThreadId ?? null);
  }, [currentThreadId]);

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (step !== "upload" || sources.length >= 10) return;
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (step !== "upload") return;
    const imageFiles = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
    if (imageFiles.length === 0) return;
    const dt = new DataTransfer();
    imageFiles.forEach((f) => dt.items.add(f));
    addSources(dt.files);
  }

  function addSources(files: FileList | null) {
    if (!files) return;
    const toAdd = Array.from(files).slice(0, 10 - sources.length);
    setSources((prev) => [
      ...prev,
      ...toAdd.map((f) => ({
        url: URL.createObjectURL(f),
        name: f.name,
        file: f,
        uploadedId: null,
      })),
    ]);
  }

  async function handleClean() {
    if (sources.length === 0) return;
    setStep("cleaning");
    setError(null);
    setCleanStatus(Object.fromEntries(sources.map((_, i) => [i, "pending" as CleanStatus])));

    const results: KakaoCleaned[] = [];

    for (let i = 0; i < sources.length; i++) {
      const src = sources[i];
      setCleanStatus((prev) => ({ ...prev, [i]: "processing" }));
      try {
        let assetId = src.uploadedId;
        if (!assetId) {
          const uploaded = await uploadAsset(
            src.file,
            activeWorkspaceId,
            "upload",
            resolvedThreadId ?? currentThreadId ?? undefined,
          );
          if (!uploaded) throw new Error("Upload failed");
          assetId = uploaded.id;
          setSources((prev) => prev.map((s, idx) => (idx === i ? { ...s, uploadedId: assetId } : s)));
        }

        const jobResp = await cleanKakaoImage({
          workspaceId: activeWorkspaceId,
          assetId,
          threadId: resolvedThreadId ?? undefined,
        });
        if (jobResp.thread_id) {
          setResolvedThreadId(jobResp.thread_id);
          onThreadResolved?.(jobResp.thread_id);
        }
        const output = await pollForCleanedAsset(jobResp.job_id, activeWorkspaceId);
        results.push({
          sourceIdx: i,
          assetId: output.id,
          url: output.url,
          title: src.name,
          accepted: true,
        });
        setCleanStatus((prev) => ({ ...prev, [i]: "done" }));
      } catch (e) {
        const message = e instanceof Error ? e.message : "Cleanup failed";
        setCleanStatus((prev) => ({ ...prev, [i]: "error" }));
        setError((prev) => prev ?? `Cleanup failed for ${src.name}: ${message}`);
        results.push({
          sourceIdx: i,
          assetId: "",
          url: src.url,
          title: src.name,
          accepted: false,
          error: message,
        });
      }
    }

    setCleaned(results);
    if (results.some((item) => item.assetId)) onAssetsCreated();
    setStep("confirm");
  }

  const acceptedCount = cleaned.filter((c) => c.accepted && c.assetId).length;
  const isProcessing = step === "cleaning";
  const activeIdx = ["upload", "cleaning"].includes(step) ? 0 : 1;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-border px-6 py-3">
        {STEPS.map(({ key, label }, i) => {
          const done = i < activeIdx;
          const current = i === activeIdx;
          return (
            <div key={key} className="flex items-center gap-1">
              {i > 0 && <div className="h-px w-5 bg-border" />}
              <div
                className={cn(
                  "flex items-center gap-1.5 text-xs",
                  done ? "text-accent" : current ? "font-medium text-foreground" : "text-muted-foreground",
                )}
              >
                <span
                  className={cn(
                    "flex size-4 items-center justify-center rounded-full text-[9px] font-bold",
                    done ? "bg-accent text-white" : current ? "bg-foreground text-background" : "bg-muted text-muted-foreground",
                  )}
                >
                  {done ? <Check className="size-2.5" /> : i + 1}
                </span>
                {label}
              </div>
            </div>
          );
        })}
      </div>

      <div
        className="min-h-0 flex-1 overflow-y-auto px-6 py-4 [scrollbar-width:thin]"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {(step === "upload" || step === "cleaning") && (
          <div className="space-y-4">
            <div>
              <p className="mb-1 text-sm font-medium text-foreground">Source Images</p>
              <p className="mb-3 text-xs text-muted-foreground">
                Upload up to 10 creatives. We clean each image first, then pass the accepted cleaned result into the Kakao Bizboard builder.
              </p>

              {sources.length < 10 && step === "upload" && (
                <button
                  type="button"
                  onClick={() => sourceInputRef.current?.click()}
                  className={cn(
                    "flex w-full items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-5 text-sm transition-colors",
                    isDragging
                      ? "border-accent bg-soft-accent text-accent"
                      : "border-border bg-muted/30 text-muted-foreground hover:border-accent/60 hover:text-foreground",
                  )}
                >
                  <Plus className="size-4" />
                  {isDragging ? "Drop images here" : `Add images (${sources.length}/10)`}
                </button>
              )}

              {sources.length > 0 && (
                <div className="mt-3 grid grid-cols-5 gap-2">
                  {sources.map((src, i) => {
                    const status = cleanStatus[i];
                    return (
                      <div
                        key={i}
                        className="group relative aspect-video overflow-hidden rounded-lg border border-border bg-muted"
                      >
                        <img src={src.url} alt={src.name} className="h-full w-full object-cover" />

                        {step === "cleaning" && (
                          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                            {status === "processing" && <Loader2 className="size-4 animate-spin text-white" />}
                            {status === "done" && <Check className="size-4 text-green-400" />}
                            {status === "error" && <X className="size-4 text-red-400" />}
                            {status === "pending" && <div className="size-1.5 rounded-full bg-white/50" />}
                          </div>
                        )}

                        {step === "upload" && (
                          <button
                            type="button"
                            onClick={() => setSources((prev) => prev.filter((_, idx) => idx !== i))}
                            className="absolute right-1 top-1 hidden size-5 items-center justify-center rounded-full bg-black/60 group-hover:flex"
                          >
                            <X className="size-3 text-white" />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {step === "cleaning" && (
              <p className="text-xs text-muted-foreground">
                Cleaning {Object.values(cleanStatus).filter((s) => s === "done").length} / {sources.length}...
              </p>
            )}
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
        )}

        {step === "confirm" && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-foreground">Review cleaned images</p>
            <p className="text-xs text-muted-foreground">
              Select the cleaned images you want to keep, then continue into the Kakao Bizboard builder.
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              {cleaned.map((c, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setCleaned((prev) => prev.map((x, xi) => (xi === i ? { ...x, accepted: !x.accepted } : x)))}
                  className={cn(
                    "relative overflow-hidden rounded-xl border-2 text-left transition-opacity",
                    c.accepted ? "border-accent" : "border-border opacity-50",
                  )}
                >
                  <div className="relative">
                    <img
                      src={c.url}
                      alt={c.assetId ? "Cleaned result" : "Cleanup failed"}
                      className="aspect-[16/9] w-full object-cover"
                    />
                    <span className="absolute bottom-2 left-2 rounded bg-black/60 px-2 py-1 text-[10px] font-medium text-white">
                      {c.assetId ? "Cleaned" : "Cleanup failed"}
                    </span>
                  </div>
                  {c.assetId === "" && (
                    <div className="absolute inset-0 flex items-center justify-center bg-destructive/20">
                      <div className="rounded-lg bg-background/90 px-3 py-2 text-center shadow-sm">
                        <p className="text-xs font-medium text-destructive">Cleanup failed</p>
                        {c.error && (
                          <p className="mt-1 max-w-[260px] text-[10px] leading-4 text-destructive/80">
                            {c.error}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                  {c.accepted && (
                    <div className="absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full bg-accent">
                      <Check className="size-3 text-white" />
                    </div>
                  )}
                  <div className="border-t border-border bg-card px-3 py-2">
                    <p className="truncate text-[11px] font-medium text-foreground">
                      {sources[c.sourceIdx]?.name ?? `Image ${i + 1}`}
                    </p>
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      {c.assetId ? "This cleaned image is ready for the Kakao builder." : "Cleanup did not produce a valid cleaned asset."}
                    </p>
                  </div>
                </button>
              ))}
            </div>

            {acceptedCount > 0 && (
              <div className="rounded-xl border border-border bg-muted/20 p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Next Step
                </p>
                <p className="mt-1 text-sm text-foreground">
                  Continue to the Kakao Bizboard builder to enter subtitle, main copy, and preview the final `1029x258` asset.
                </p>
              </div>
            )}

            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
        )}
      </div>

      {!isProcessing && (
        <div className="flex items-center justify-end border-t border-border px-6 py-3">
          {step === "upload" && (
            <button
              type="button"
              disabled={sources.length === 0}
              onClick={handleClean}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-colors",
                sources.length > 0
                  ? "bg-foreground text-background hover:bg-foreground/90"
                  : "cursor-not-allowed bg-muted text-muted-foreground",
              )}
            >
              Clean {sources.length > 0 ? `${sources.length} image${sources.length !== 1 ? "s" : ""}` : "images"}
              <ChevronRight className="size-3.5" />
            </button>
          )}

          {step === "confirm" && (
            <button
              type="button"
              disabled={acceptedCount === 0}
              onClick={() => {
                const acceptedAssets = cleaned
                  .filter((item) => item.accepted && item.assetId)
                  .map((item) => ({
                    id: item.assetId,
                    url: item.url,
                    title: item.title,
                    type: "image" as const,
                    threadId: resolvedThreadId ?? currentThreadId ?? null,
                  }));
                onOpenBuilder(acceptedAssets);
              }}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-colors",
                acceptedCount > 0
                  ? "bg-foreground text-background hover:bg-foreground/90"
                  : "cursor-not-allowed bg-muted text-muted-foreground",
              )}
            >
              Continue with {acceptedCount} image{acceptedCount !== 1 ? "s" : ""}
              <ChevronRight className="size-3.5" />
            </button>
          )}
        </div>
      )}

      <input
        ref={sourceInputRef}
        type="file"
        accept="image/*"
        multiple
        className="sr-only"
        onChange={(e) => {
          addSources(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
