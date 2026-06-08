"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Brush, Loader2, RotateCcw, Square, X } from "lucide-react";
import { cn } from "@/lib/utils";

type Tool = "rect" | "brush";

export interface InpaintingCanvasProps {
  imageUrl: string;
  assetId: string;
  naturalWidth: number;
  naturalHeight: number;
  onClose: () => void;
  onSubmit: (maskDataUrl: string, prompt: string) => void;
  submitting?: boolean;
}

const BRUSH_SIZE = 30; // px on the display canvas

export function InpaintingCanvas({
  imageUrl,
  assetId,
  naturalWidth,
  naturalHeight,
  onClose,
  onSubmit,
  submitting = false,
}: InpaintingCanvasProps) {
  const [tool, setTool] = useState<Tool>("rect");
  const [prompt, setPrompt] = useState("");
  const [hasMask, setHasMask] = useState(false);

  // Two canvases stacked:
  //  bgRef  → the original image (never changes)
  //  maskRef → semi-transparent red overlay (user drawing)
  const bgRef   = useRef<HTMLCanvasElement>(null);
  const maskRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Drawing state
  const drawing = useRef(false);
  const rectStart = useRef<{ x: number; y: number } | null>(null);

  // ── Compute display dimensions (fit inside 80vw × 70vh) ─────────────────
  const [display, setDisplay] = useState({ w: naturalWidth, h: naturalHeight });

  useEffect(() => {
    const maxW = Math.min(window.innerWidth * 0.8, 1000);
    const maxH = window.innerHeight * 0.6;
    const ratio = Math.min(maxW / naturalWidth, maxH / naturalHeight, 1);
    setDisplay({ w: Math.round(naturalWidth * ratio), h: Math.round(naturalHeight * ratio) });
  }, [naturalWidth, naturalHeight]);

  // ── Draw background image ────────────────────────────────────────────────
  useEffect(() => {
    const canvas = bgRef.current;
    if (!canvas) return;
    canvas.width  = display.w;
    canvas.height = display.h;
    const ctx = canvas.getContext("2d")!;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => ctx.drawImage(img, 0, 0, display.w, display.h);
    img.src = imageUrl;
  }, [imageUrl, display]);

  // ── Init mask canvas ─────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = maskRef.current;
    if (!canvas) return;
    canvas.width  = display.w;
    canvas.height = display.h;
    // transparent start
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, display.w, display.h);
  }, [display]);

  // ── Pointer helpers ──────────────────────────────────────────────────────
  function getPos(e: React.MouseEvent<HTMLCanvasElement>) {
    const rect = maskRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function paintBrush(x: number, y: number) {
    const ctx = maskRef.current!.getContext("2d")!;
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(239,68,68,0.55)";
    ctx.beginPath();
    ctx.arc(x, y, BRUSH_SIZE / 2, 0, Math.PI * 2);
    ctx.fill();
    setHasMask(true);
  }

  // Temp rect preview drawn each frame
  const [rectPreview, setRectPreview] = useState<{
    x: number; y: number; w: number; h: number
  } | null>(null);

  function commitRect(x1: number, y1: number, x2: number, y2: number) {
    const ctx = maskRef.current!.getContext("2d")!;
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(239,68,68,0.55)";
    const rx = Math.min(x1, x2), ry = Math.min(y1, y2);
    const rw = Math.abs(x2 - x1), rh = Math.abs(y2 - y1);
    ctx.fillRect(rx, ry, rw, rh);
    setHasMask(true);
    setRectPreview(null);
  }

  // ── Mouse events ─────────────────────────────────────────────────────────
  function onMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    drawing.current = true;
    const pos = getPos(e);
    if (tool === "brush") {
      paintBrush(pos.x, pos.y);
    } else {
      rectStart.current = pos;
    }
  }

  function onMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const pos = getPos(e);
    if (tool === "brush") {
      paintBrush(pos.x, pos.y);
    } else if (rectStart.current) {
      setRectPreview({
        x: Math.min(rectStart.current.x, pos.x),
        y: Math.min(rectStart.current.y, pos.y),
        w: Math.abs(pos.x - rectStart.current.x),
        h: Math.abs(pos.y - rectStart.current.y),
      });
    }
  }

  function onMouseUp(e: React.MouseEvent<HTMLCanvasElement>) {
    drawing.current = false;
    if (tool === "rect" && rectStart.current) {
      const pos = getPos(e);
      commitRect(rectStart.current.x, rectStart.current.y, pos.x, pos.y);
      rectStart.current = null;
    }
  }

  // ── Clear mask ───────────────────────────────────────────────────────────
  function clearMask() {
    const ctx = maskRef.current!.getContext("2d")!;
    ctx.clearRect(0, 0, display.w, display.h);
    setHasMask(false);
    setRectPreview(null);
  }

  // ── Export mask → base64 PNG ─────────────────────────────────────────────
  // OpenAI convention: transparent = edit area, opaque white = preserve area.
  // We invert: where user painted red → transparent; rest → opaque white.
  function exportMask(): string {
    const out = document.createElement("canvas");
    out.width  = naturalWidth;
    out.height = naturalHeight;
    const ctx = out.getContext("2d")!;

    // Start: everything opaque white (preserved)
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, naturalWidth, naturalHeight);

    // Scale the mask overlay to natural size
    const scale = naturalWidth / display.w;
    const maskCanvas = maskRef.current!;

    // Draw mask overlay scaled up; red pixels become the "edit" zone
    // We need to make those pixels transparent.
    // Trick: draw mask on a temp canvas, read pixel data, make red → transparent.
    const tmp = document.createElement("canvas");
    tmp.width  = naturalWidth;
    tmp.height = naturalHeight;
    const tc = tmp.getContext("2d")!;
    tc.drawImage(maskCanvas, 0, 0, naturalWidth, naturalHeight);

    const maskData = tc.getImageData(0, 0, naturalWidth, naturalHeight);
    const outData  = ctx.getImageData(0, 0, naturalWidth, naturalHeight);

    for (let i = 0; i < maskData.data.length; i += 4) {
      // If mask pixel has any alpha (user painted here) → make output transparent
      if (maskData.data[i + 3] > 10) {
        outData.data[i]     = 0;
        outData.data[i + 1] = 0;
        outData.data[i + 2] = 0;
        outData.data[i + 3] = 0; // transparent = edit zone
      }
    }

    ctx.putImageData(outData, 0, 0);
    return out.toDataURL("image/png");
  }

  function handleSubmit() {
    if (!prompt.trim() || !hasMask || submitting) return;
    onSubmit(exportMask(), prompt.trim());
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="flex max-h-[95vh] w-full max-w-5xl flex-col gap-4 overflow-hidden rounded-2xl bg-card shadow-2xl">

        {/* ── Header ── */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <h2 className="text-sm font-semibold">Edit Image</h2>
            <p className="text-[11px] text-muted-foreground">
              Paint the area you want to change, then describe the edit
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>

        {/* ── Tool bar ── */}
        <div className="flex shrink-0 items-center gap-2 px-5">
          <button
            type="button"
            onClick={() => setTool("rect")}
            className={cn(
              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
              tool === "rect"
                ? "border-accent/40 bg-soft-accent text-accent"
                : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            <Square className="size-3.5" />
            Rectangle
          </button>
          <button
            type="button"
            onClick={() => setTool("brush")}
            className={cn(
              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
              tool === "brush"
                ? "border-accent/40 bg-soft-accent text-accent"
                : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            <Brush className="size-3.5" />
            Brush
          </button>
          <button
            type="button"
            onClick={clearMask}
            className="ml-auto flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="size-3.5" />
            Clear
          </button>
        </div>

        {/* ── Canvas area ── */}
        <div
          ref={containerRef}
          className="relative mx-5 flex-shrink-0 overflow-hidden rounded-xl border border-border"
          style={{ width: display.w, height: display.h, alignSelf: "flex-start" }}
        >
          {/* Background: original image */}
          <canvas ref={bgRef} className="absolute inset-0" />

          {/* Mask overlay (user draws here) */}
          <canvas
            ref={maskRef}
            className="absolute inset-0"
            style={{ cursor: tool === "brush" ? "crosshair" : "crosshair", opacity: 1 }}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={() => { if (tool === "rect" && drawing.current) drawing.current = false; }}
          />

          {/* Live rect preview */}
          {rectPreview && (
            <div
              className="pointer-events-none absolute border-2 border-red-400 bg-red-400/30"
              style={{
                left: rectPreview.x,
                top:  rectPreview.y,
                width:  rectPreview.w,
                height: rectPreview.h,
              }}
            />
          )}

          {/* Empty state hint */}
          {!hasMask && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <p className="rounded-lg bg-black/50 px-4 py-2 text-xs text-white">
                {tool === "rect" ? "Click and drag to select an area" : "Click and drag to paint the area"}
              </p>
            </div>
          )}
        </div>

        {/* ── Prompt + submit ── */}
        <div className="flex shrink-0 items-end gap-3 border-t border-border px-5 py-4">
          <div className="flex-1">
            <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              What should go in the painted area?
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Remove this element and fill with matching background…"
              rows={2}
              className="w-full resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent/60"
            />
          </div>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!hasMask || !prompt.trim() || submitting}
            className={cn(
              "flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all",
              hasMask && prompt.trim() && !submitting
                ? "bg-foreground text-background hover:opacity-80"
                : "cursor-not-allowed bg-muted text-muted-foreground"
            )}
          >
            {submitting && <Loader2 className="size-4 animate-spin" />}
            {submitting ? "Editing…" : "Apply Edit"}
          </button>
        </div>

      </div>
    </div>
  );
}
