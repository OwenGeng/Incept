"use client";

import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, FileImage, Film, Gamepad2, ImagePlus, Loader2, Paperclip, Plus, Send, Sparkles, X } from "lucide-react";
import { savePlayableProject, type PlayablePlanningModel, type PlayableSchema } from "@/lib/gaming-playable";
import { uploadAsset } from "@/lib/incept-api";
import { cn } from "@/lib/utils";

const WORKSPACE_ID = "wsp_q2";

type ReferenceFile = {
  file: File;
  previewUrl?: string;
};

const quickStarts = [
  { title: "Puzzle loop", detail: "Create a simple, satisfying puzzle game.", brief: "Create a simple, satisfying puzzle game with a clear one-touch loop and an escalating objective." },
  { title: "Match game", detail: "Design a match-3 game with unique mechanics.", brief: "Create a match-3 playable with one distinctive mechanic, a fast tutorial, and a compelling reward moment." },
  { title: "Merge game", detail: "Build a merge game with progression.", brief: "Create a merge playable with clear progression, a visible upgrade goal, and a satisfying final merge." },
];

function projectTitle(brief: string) {
  const firstLine = brief.trim().split(/[\n.!?。！？]/)[0]?.trim();
  return (firstLine || "New playable").slice(0, 120);
}

function isPreviewableImage(file: File) {
  return file.type.startsWith("image/");
}

export function GamingPlayableStarter() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [brief, setBrief] = useState("");
  const [planningModel, setPlanningModel] = useState<PlayablePlanningModel>("gemini-3.8-flash");
  const [references, setReferences] = useState<ReferenceFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addFiles = (incoming: FileList | File[]) => {
    const files = Array.from(incoming).filter((file) => file.type.startsWith("image/") || file.type.startsWith("video/") || file.name.endsWith(".html") || file.name.endsWith(".htm"));
    if (!files.length) {
      setError("Add an image, video, or playable HTML file.");
      return;
    }
    setError(null);
    setReferences((current) => [...current, ...files.map((file) => ({ file, previewUrl: isPreviewableImage(file) ? URL.createObjectURL(file) : undefined }))]);
  };

  const removeReference = (index: number) => {
    setReferences((current) => {
      const removed = current[index];
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
      return current.filter((_, itemIndex) => itemIndex !== index);
    });
  };

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = "";
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
  };

  const createPlayable = async () => {
    if (!brief.trim() && !references.length) {
      setError("Write a brief, add game references, or use both to get started.");
      return;
    }
    setIsCreating(true);
    setError(null);
    try {
      const uploaded = await Promise.all(references.map(async ({ file }) => {
        const asset = await uploadAsset(file, WORKSPACE_ID, "reference");
        if (!asset) throw new Error(`Could not upload ${file.name}.`);
        return asset;
      }));
      const firstImage = references.find(({ file }) => isPreviewableImage(file));
      const backgroundDataUri = firstImage ? await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = reject;
        reader.readAsDataURL(firstImage.file);
      }) : undefined;
      const schema: PlayableSchema = {
        schemaVersion: 1,
        runtime: "phaser-preview-v1",
        metadata: { title: projectTitle(brief), ctaLabel: "Play now", orientation: "portrait", brief: brief.trim() || undefined, planningModel },
        assets: {
          backgroundDataUri,
          referenceAssetIds: uploaded.map((asset) => asset.id),
          referenceNames: references.map(({ file }) => file.name),
        },
        gameplay: { template: "merge", accentColor: "#F97316", targetValue: 16, tutorialText: "Tap two matching pieces to merge them" },
      };
      const project = await savePlayableProject({ workspaceId: WORKSPACE_ID, title: schema.metadata.title, schema });
      router.push(`/gaming-playable/projects/${project.project_id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the playable. Try again.");
      setIsCreating(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-[calc(100vh-72px)] max-w-[1120px] flex-col px-5 py-10 md:px-8 md:py-14">
      <section className="mx-auto flex w-full max-w-[920px] flex-1 flex-col justify-center pb-10">
        <div className="text-center">
          <span className="mx-auto flex size-16 items-center justify-center rounded-[22px] bg-[#FFEDD5] text-[#F97316] shadow-[0_12px_28px_rgba(249,115,22,0.14)]"><Gamepad2 className="size-8" /></span>
          <h1 className="mt-6 text-balance text-4xl font-semibold tracking-[-0.035em] text-slate-950 sm:text-5xl">What should players do?</h1>
          <p className="mx-auto mt-4 max-w-2xl text-pretty text-base leading-7 text-slate-500 sm:text-lg">Describe the game you want to create, add reference images or videos, or combine both.</p>
        </div>

        <div className={cn("mt-10 overflow-hidden rounded-2xl bg-white shadow-[0_18px_42px_rgba(15,23,42,0.08)] ring-1 ring-slate-200 transition", isDragging && "ring-2 ring-[#F97316]")} onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={(event) => { event.preventDefault(); setIsDragging(false); }} onDrop={handleDrop}>
          <label htmlFor="playable-brief" className="sr-only">Playable brief</label>
          <textarea id="playable-brief" value={brief} onChange={(event) => { setBrief(event.target.value); setError(null); }} placeholder="Describe the playable you want to create…" className="min-h-36 w-full resize-none border-0 bg-transparent px-6 pt-6 text-base leading-7 text-slate-900 outline-none placeholder:text-slate-400 sm:text-lg" />

          {references.length > 0 && <div className="flex gap-3 overflow-x-auto px-6 pb-5" aria-label="Game references">{references.map((reference, index) => <div key={`${reference.file.name}-${index}`} className="group relative h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-slate-100 ring-1 ring-slate-200"><button type="button" onClick={() => removeReference(index)} aria-label={`Remove ${reference.file.name}`} className="absolute right-1.5 top-1.5 z-10 flex size-6 items-center justify-center rounded-full bg-white/95 text-slate-600 shadow-sm opacity-100 transition hover:bg-slate-950 hover:text-white sm:opacity-0 sm:group-hover:opacity-100"><X className="size-3.5" /></button>{reference.previewUrl ? <img src={reference.previewUrl} alt={reference.file.name} className="size-full object-cover" /> : <div className="flex size-full flex-col items-center justify-center gap-1.5 px-2 text-center text-slate-500">{reference.file.type.startsWith("video/") ? <Film className="size-5" /> : <FileImage className="size-5" />}<span className="line-clamp-2 text-[10px] font-medium leading-3">{reference.file.name}</span></div>}</div>)}</div>}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4">
            <div className="flex flex-wrap items-center gap-2"><label className="relative inline-flex h-10 items-center rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 transition hover:border-[#FDBA74] hover:bg-[#FFF7ED] focus-within:ring-2 focus-within:ring-[#FB923C]"><Sparkles className="ml-3 size-4 text-[#EA580C]" /><select value={planningModel} onChange={(event) => setPlanningModel(event.target.value as PlayablePlanningModel)} aria-label="Planning model" className="h-full appearance-none bg-transparent py-0 pl-2 pr-8 outline-none"><option value="gemini-3.8-flash">Gemini 3.8 Flash</option><option value="gemini-3.1-pro-preview">Gemini 3.1 Pro Preview</option></select><ChevronDown className="pointer-events-none absolute right-3 size-4 text-slate-500" /></label><input ref={fileInputRef} id="playable-references" type="file" multiple accept="image/*,video/*,.html,.htm" className="hidden" onChange={handleFileInput} /><button type="button" onClick={() => fileInputRef.current?.click()} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-700 transition hover:border-[#FDBA74] hover:bg-[#FFF7ED] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FB923C]"><Paperclip className="size-4" />Add references</button><span className="hidden text-xs text-slate-400 sm:inline">Images, videos, or playable HTML</span></div>
            <button type="button" onClick={() => void createPlayable()} disabled={isCreating} className="inline-flex h-11 items-center gap-2 rounded-xl bg-[#F97316] px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-[#EA580C] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FB923C] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60">{isCreating ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}Create playable</button>
          </div>
        </div>
        {error && <p role="alert" className="mx-auto mt-3 max-w-[920px] text-sm text-red-600">{error}</p>}
        <p className="mt-3 text-center text-xs text-slate-400">Drag files anywhere into the composer, or use the attachment button.</p>

        <div className="mt-9 grid gap-3 md:grid-cols-3">{quickStarts.map((item) => <button key={item.title} type="button" onClick={() => { setBrief(item.brief); setError(null); document.getElementById("playable-brief")?.focus(); }} className="group flex min-h-28 items-center gap-4 rounded-2xl border border-slate-200 bg-white px-4 text-left transition hover:-translate-y-0.5 hover:border-[#FDBA74] hover:shadow-[0_10px_24px_rgba(15,23,42,0.06)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FB923C]"><span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-[#FFF7ED] text-[#EA580C]">{item.title === "Merge game" ? <Plus className="size-5" /> : <ImagePlus className="size-5" />}</span><span><span className="block text-sm font-semibold text-slate-900 group-hover:text-[#C2410C]">{item.title}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{item.detail}</span></span></button>)}</div>
      </section>
    </main>
  );
}
