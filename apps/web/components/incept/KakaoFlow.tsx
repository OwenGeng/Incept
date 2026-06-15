"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronRight, ImageIcon, Loader2, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  cleanKakaoImage,
  createKakaoBizboardJob,
  getJob,
  listAssets,
  uploadAsset,
} from "@/lib/incept-api";
import {
  composeKakaoBizboard,
  loadSpoqaFonts,
  validateKakaoBizboardInputs,
} from "@/lib/kakao-compositor";

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
  accepted: boolean;
  error?: string;
}

type CleanStatus = "pending" | "processing" | "done" | "error";
type Step = "upload" | "cleaning" | "confirm" | "metadata" | "composing" | "done";

const STEPS: { key: Step; label: string }[] = [
  { key: "upload", label: "Upload & Clean" },
  { key: "confirm", label: "Confirm" },
  { key: "metadata", label: "Bizboard" },
  { key: "done", label: "Done" },
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
  onAssetsCreated,
}: {
  activeWorkspaceId: string;
  onAssetsCreated: () => void;
}) {
  const [step, setStep] = useState<Step>("upload");
  const [sources, setSources] = useState<KakaoSource[]>([]);
  const [cleaned, setCleaned] = useState<KakaoCleaned[]>([]);
  const [cleanStatus, setCleanStatus] = useState<Record<number, CleanStatus>>({});
  const [appIconUrl, setAppIconUrl] = useState<string | null>(null);
  const [mainCopy, setMainCopy] = useState("");
  const [appDownloadCopy, setAppDownloadCopy] = useState("앱에서 확인 >");
  const [dspName, setDspName] = useState("Moloco");
  const [gacha, setGacha] = useState(false);
  const [composedCount, setComposedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [mainCopyWidthPx, setMainCopyWidthPx] = useState(0);

  const sourceInputRef = useRef<HTMLInputElement>(null);
  const iconInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadSpoqaFonts().catch(() => {});
  }, []);

  useEffect(() => {
    const firstAccepted = cleaned.find((c) => c.accepted && c.assetId);
    if (!firstAccepted || (step !== "metadata" && step !== "composing")) {
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setValidationErrors([]);
      setMainCopyWidthPx(0);
      return;
    }

    let cancelled = false;
    let previewObjectUrl: string | null = null;

    async function buildPreview() {
      const validation = await validateKakaoBizboardInputs({
        thumbnailUrl: firstAccepted.url,
        appIconUrl,
        mainCopy,
        appDownloadCopy,
        dspName,
        gacha,
      });
      if (cancelled) return;

      setValidationErrors(validation.errors);
      setMainCopyWidthPx(validation.mainCopyWidthPx);

      if (validation.errors.length > 0) {
        setPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return null;
        });
        return;
      }

      const blob = await composeKakaoBizboard({
        thumbnailUrl: firstAccepted.url,
        appIconUrl,
        mainCopy,
        appDownloadCopy,
        dspName,
        gacha,
      });
      if (cancelled) return;

      previewObjectUrl = URL.createObjectURL(blob);
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return previewObjectUrl;
      });
    }

    buildPreview().catch((err) => {
      if (cancelled) return;
      setValidationErrors([err instanceof Error ? err.message : "Preview generation failed."]);
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    });

    return () => {
      cancelled = true;
      if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    };
  }, [cleaned, step, appIconUrl, mainCopy, appDownloadCopy, dspName, gacha]);

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
          const uploaded = await uploadAsset(src.file, activeWorkspaceId, "upload");
          if (!uploaded) throw new Error("Upload failed");
          assetId = uploaded.id;
          setSources((prev) => prev.map((s, idx) => (idx === i ? { ...s, uploadedId: assetId } : s)));
        }

        const jobResp = await cleanKakaoImage({ workspaceId: activeWorkspaceId, assetId });
        const output = await pollForCleanedAsset(jobResp.job_id, activeWorkspaceId);
        results.push({ sourceIdx: i, assetId: output.id, url: output.url, accepted: true });
        setCleanStatus((prev) => ({ ...prev, [i]: "done" }));
      } catch (e) {
        const message = e instanceof Error ? e.message : "Cleanup failed";
        setCleanStatus((prev) => ({ ...prev, [i]: "error" }));
        setError((prev) => prev ?? `Cleanup failed for ${src.name}: ${message}`);
        results.push({ sourceIdx: i, assetId: "", url: src.url, accepted: false, error: message });
      }
    }

    setCleaned(results);
    if (results.some((item) => item.assetId)) onAssetsCreated();
    setStep("confirm");
  }

  async function handleCompose() {
    const accepted = cleaned.filter((c) => c.accepted && c.assetId);
    if (accepted.length === 0) return;
    if (validationErrors.length > 0) return;

    setStep("composing");
    setError(null);
    let count = 0;

    for (const item of accepted) {
      try {
        const blob = await composeKakaoBizboard({
          thumbnailUrl: item.url,
          appIconUrl,
          mainCopy,
          appDownloadCopy,
          dspName,
          gacha,
        });
        const sourceName = (sources[item.sourceIdx]?.name ?? `image_${item.sourceIdx + 1}`)
          .replace(/\.[^.]+$/, "")
          .replace(/[^a-zA-Z0-9_-]+/g, "_");
        const file = new File([blob], `${sourceName}_kakao_bizboard_1029x258.png`, {
          type: "image/png",
        });
        const uploaded = await uploadAsset(file, activeWorkspaceId, "upload");
        if (!uploaded) throw new Error("Bizboard upload failed");
        const jobResp = await createKakaoBizboardJob({
          workspaceId: activeWorkspaceId,
          cleanedAssetId: item.assetId,
          composedAssetId: uploaded.id,
          mainCopy,
          appDownloadCopy,
          dspName,
          gacha,
        });
        await pollForCleanedAsset(jobResp.job_id, activeWorkspaceId);
        count += 1;
        setComposedCount(count);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Bizboard composition failed";
        setError((prev) => prev ?? message);
      }
    }

    onAssetsCreated();
    setComposedCount(count);
    setStep("done");
  }

  function reset() {
    setStep("upload");
    setSources([]);
    setCleaned([]);
    setCleanStatus({});
    setMainCopy("");
    setAppDownloadCopy("앱에서 확인 >");
    setDspName("Moloco");
    setGacha(false);
    setAppIconUrl(null);
    setComposedCount(0);
    setError(null);
    setValidationErrors([]);
    setMainCopyWidthPx(0);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }

  const acceptedCount = cleaned.filter((c) => c.accepted).length;
  const isProcessing = step === "cleaning" || step === "composing";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-border px-6 py-3">
        {STEPS.map(({ key, label }, i) => {
          const activeIdx = ["upload", "cleaning"].includes(step) ? 0
            : step === "confirm" ? 1
            : ["metadata", "composing"].includes(step) ? 2
            : 3;
          const done = i < activeIdx;
          const current = i === activeIdx;
          return (
            <div key={key} className="flex items-center gap-1">
              {i > 0 && <div className="h-px w-5 bg-border" />}
              <div className={cn(
                "flex items-center gap-1.5 text-xs",
                done ? "text-accent" : current ? "font-medium text-foreground" : "text-muted-foreground",
              )}>
                <span className={cn(
                  "flex size-4 items-center justify-center rounded-full text-[9px] font-bold",
                  done ? "bg-accent text-white" : current ? "bg-foreground text-background" : "bg-muted text-muted-foreground",
                )}>
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
                Upload up to 10 creatives. We clean each image first, then turn the accepted cleaned result into a fixed Kakao Bizboard `1029×258` asset.
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
                Cleaning {Object.values(cleanStatus).filter((s) => s === "done").length} / {sources.length}…
              </p>
            )}
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
        )}

        {step === "confirm" && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-foreground">Review cleaned images</p>
            <p className="text-xs text-muted-foreground">
              Accepted cleaned images will be center-cropped into the locked Bizboard thumbnail slot.
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
                      {c.assetId ? "This cleaned image has been added to project history." : "Cleanup did not produce a valid cleaned asset."}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {(step === "metadata" || step === "composing") && (
          <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
            <div className="space-y-4">
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  App Icon
                </p>
                {appIconUrl ? (
                  <div className="flex items-center gap-3">
                    <div className="size-10 overflow-hidden rounded-lg border border-border">
                      <img src={appIconUrl} alt="App icon" className="h-full w-full object-cover" />
                    </div>
                    <button
                      type="button"
                      onClick={() => setAppIconUrl(null)}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => iconInputRef.current?.click()}
                    className="flex items-center gap-2 rounded-lg border border-dashed border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:border-accent/60 hover:text-foreground"
                  >
                    <ImageIcon className="size-4" />
                    Upload app icon (required, 38×38)
                  </button>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Main Copy <span className="text-destructive">*</span>
                </label>
                <input
                  value={mainCopy}
                  onChange={(e) => setMainCopy(e.target.value)}
                  placeholder="게임 제목 또는 브랜드명"
                  className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-accent/60"
                />
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Must include the advertised subject. Width must stay between 290 px and 585 px at 48pt.
                </p>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Current measured width: {Math.round(mainCopyWidthPx)} px
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  App Download Copy
                </label>
                <input
                  value={appDownloadCopy}
                  onChange={(e) => setAppDownloadCopy(e.target.value)}
                  placeholder="앱에서 확인 >"
                  className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-accent/60"
                />
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Must include the word `앱` and end with the `&gt;` icon.
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  DSP Name
                </label>
                <input
                  value={dspName}
                  onChange={(e) => setDspName(e.target.value)}
                  placeholder="Moloco"
                  className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-accent/60"
                />
                <p className="mt-1 text-[10px] text-muted-foreground">
                  This drives the fixed AD disclosure line.
                </p>
              </div>

              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={gacha}
                  onChange={(e) => setGacha(e.target.checked)}
                  className="rounded"
                />
                <span className="text-sm text-foreground">확률형 아이템 포함 (Gacha items)</span>
              </label>

              {validationErrors.length > 0 && (
                <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-destructive">
                    Bizboard Validation
                  </p>
                  <div className="mt-2 space-y-1">
                    {validationErrors.map((msg) => (
                      <p key={msg} className="text-[11px] leading-4 text-destructive">
                        {msg}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {step === "composing" && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Composing {composedCount} / {acceptedCount}…
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div>
                <p className="text-sm font-medium text-foreground">Bizboard Preview</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Fixed transparent `1029×258` Bizboard. The cleaned image is inserted into the locked thumbnail slot on the right.
                </p>
              </div>
              <div className="overflow-hidden rounded-2xl border border-border bg-muted/30 p-4">
                {previewUrl ? (
                  <img
                    src={previewUrl}
                    alt="Kakao Bizboard preview"
                    className="w-full rounded-lg border border-border bg-[linear-gradient(45deg,#f5f5f5_25%,transparent_25%,transparent_75%,#f5f5f5_75%,#f5f5f5),linear-gradient(45deg,#f5f5f5_25%,transparent_25%,transparent_75%,#f5f5f5_75%,#f5f5f5)] bg-[length:16px_16px] bg-[position:0_0,8px_8px]"
                  />
                ) : (
                  <div className="flex aspect-[1029/258] items-center justify-center rounded-lg border border-dashed border-border bg-card text-xs text-muted-foreground">
                    Fix validation issues to generate a preview.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-accent/10">
              <Check className="size-6 text-accent" />
            </div>
            <p className="text-base font-semibold text-foreground">
              {composedCount} Bizboard{composedCount !== 1 ? "s" : ""} saved to Library
            </p>
            <p className="text-xs text-muted-foreground">
              Find them in the Assets panel on the right.
            </p>
            <button
              type="button"
              onClick={reset}
              className="mt-2 rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
            >
              Start new batch
            </button>
          </div>
        )}
      </div>

      {!isProcessing && step !== "done" && (
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
              onClick={() => setStep("metadata")}
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

          {step === "metadata" && (
            <button
              type="button"
              disabled={acceptedCount === 0 || validationErrors.length > 0}
              onClick={handleCompose}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-colors",
                acceptedCount > 0 && validationErrors.length === 0
                  ? "bg-foreground text-background hover:bg-foreground/90"
                  : "cursor-not-allowed bg-muted text-muted-foreground",
              )}
            >
              Compose {acceptedCount} Bizboard{acceptedCount !== 1 ? "s" : ""}
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
      <input
        ref={iconInputRef}
        type="file"
        accept="image/*"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          setAppIconUrl(URL.createObjectURL(file));
          e.target.value = "";
        }}
      />
    </div>
  );
}
