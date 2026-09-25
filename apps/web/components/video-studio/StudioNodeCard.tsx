"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Box,
  FileAudio,
  FileText,
  Image as ImageIcon,
  Sparkles,
  Video,
  WandSparkles,
} from "lucide-react";
import type { StudioNode } from "./types";

const iconByKind = {
  text: FileText,
  image: ImageIcon,
  video: Video,
  audio: FileAudio,
  imageGeneration: Sparkles,
  videoGeneration: WandSparkles,
  director3d: Box,
};

export function StudioNodeCard({ data, selected }: NodeProps<StudioNode>) {
  const Icon = iconByKind[data.kind as keyof typeof iconByKind] ?? FileText;
  const summary = String(data.text || data.prompt || data.assetPath || "").trim();
  const previewUrl = typeof data.previewUrl === "string" ? data.previewUrl : "";
  return (
    <div
      className={`w-64 overflow-hidden rounded-xl border bg-white shadow-sm transition ${
        selected ? "border-[#356fec] ring-2 ring-[#356fec]/15" : "border-border"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!size-2.5 !border-2 !border-white !bg-[#356fec]" />
      <div className="flex items-center gap-2 border-b border-border-soft px-3 py-2.5">
        <span className="flex size-7 items-center justify-center rounded-lg bg-soft-accent text-[#356fec]">
          <Icon className="size-4" />
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">{data.label}</span>
        {data.status === "running" && <span className="size-2 animate-pulse rounded-full bg-[#356fec]" />}
      </div>
      <div className="min-h-16 text-xs leading-5 text-muted-foreground">
        {previewUrl && ["image", "imageGeneration"].includes(data.kind) ? (
          <div className="relative aspect-video bg-[#f5f7fa]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={previewUrl} alt={data.label} className="h-full w-full object-contain" draggable={false} />
          </div>
        ) : previewUrl && ["video", "videoGeneration"].includes(data.kind) ? (
          <video className="nodrag nowheel nopan aspect-video w-full bg-black object-contain" src={previewUrl} controls preload="metadata" />
        ) : previewUrl && data.kind === "audio" ? (
          <div className="px-3 py-4"><audio className="nodrag nowheel nopan h-8 w-full" src={previewUrl} controls preload="metadata" /></div>
        ) : data.kind === "director3d" ? (
          <div className="relative h-28 overflow-hidden bg-[linear-gradient(180deg,#eef2ff,#f8fafc_62%,#e2e8f0_63%,#f8fafc)]">
            <span className="absolute left-1/2 top-6 h-12 w-8 -translate-x-1/2 rounded-t-full border border-[#8b5cf6]/45 bg-white/70" />
            <span className="absolute bottom-3 left-4 right-4 h-px bg-[#8b5cf6]/25" />
            <span className="absolute bottom-2 left-1/2 -translate-x-1/2 text-[10px] text-[#7c3aed]">3D blocking scene</span>
          </div>
        ) : (
          <div className="px-3 py-3">{summary ? <p className="line-clamp-4 whitespace-pre-wrap">{summary}</p> : <p className="italic opacity-70">Empty node</p>}</div>
        )}
        {previewUrl && summary && <p className="truncate border-t border-border-soft px-3 py-2 text-[10px]">{summary}</p>}
      </div>
      <Handle type="source" position={Position.Right} className="!size-2.5 !border-2 !border-white !bg-[#356fec]" />
    </div>
  );
}
