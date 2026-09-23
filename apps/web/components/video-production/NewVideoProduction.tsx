"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, Clapperboard, LayoutPanelTop, Loader2, MonitorPlay, ShieldCheck, Sparkles, Tv2 } from "lucide-react";
import {
  createVideoProduction,
  getVideoProductionCapabilities,
  type VideoProductionProviderCapabilities,
  type VideoProductionProviderSelection,
  type VideoProductionSetup,
} from "@/lib/incept-api";

const WORKSPACE_ID = "wsp_q2";
type Mode = "commercial" | "short_drama" | "repair" | "ctv";
type Step = 1 | 2 | 3 | 4;
type Intake = { title: string; market: string; audience: string; platform: string; conversionGoal: string; visualStyle: string; spokenLanguage: string; subtitleLanguage: string; brief: string };

const choices: Array<{ id: Mode; icon: typeof Clapperboard; title: string; detail: string; type: string; example: string }> = [
  { id: "commercial", icon: Clapperboard, title: "Commercial", detail: "A campaign, product, or performance story for a defined audience.", type: "Commercial video", example: "Product launch, game performance creative, app install, retail campaign" },
  { id: "short_drama", icon: Tv2, title: "Original short drama", detail: "An original character-led story from your own brief or supplied script.", type: "Original short drama", example: "Original episode, character vignette, branded narrative" },
  { id: "repair", icon: ShieldCheck, title: "Repair", detail: "Improve approved footage while retaining its intended story and claims.", type: "Video repair", example: "Cleanup, reframing, version repair, controlled enhancement" },
  { id: "ctv", icon: LayoutPanelTop, title: "CTV composition", detail: "Build a screen-ready version for connected TV and streaming placements.", type: "CTV composition", example: "Streaming spot, CTV cutdown, landscape delivery version" },
];
const stepLabels = ["Production", "Models", "Creative brief", "Review"] as const;

function defaultProviderSelection(capabilities: VideoProductionProviderCapabilities): VideoProductionProviderSelection {
  const first = (options: VideoProductionProviderCapabilities["text"]) => {
    const option = options[0];
    return option ? { provider: option.provider, model: option.model } : { provider: "", model: "" };
  };
  return { text: first(capabilities.text), image: first(capabilities.image), video: first(capabilities.video), audio: first(capabilities.audio) };
}

function FieldLabel({ children, required = false }: { children: React.ReactNode; required?: boolean }) {
  return <span className="text-xs font-semibold text-[#171a20]">{children}{required ? <span className="ml-1 text-[#356fec]">*</span> : null}</span>;
}
function Input({ className = "", ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`mt-2 h-10 w-full rounded-lg border border-[#e6e8ec] bg-white px-3 text-sm text-[#171a20] outline-none placeholder:text-[#8b919c] focus:border-[#171a20] focus:ring-2 focus:ring-[#171a20]/10 ${className}`} />;
}
function SelectButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return <button type="button" onClick={onClick} className={`rounded-lg border px-3 py-2 text-left text-xs transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#171a20]/25 ${active ? "border-[#171a20] bg-[#171a20] text-white" : "border-[#e6e8ec] bg-white text-[#5f6673] hover:border-[#c7ccd4]"}`}>{children}</button>;
}

export function NewVideoProduction() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [mode, setMode] = useState<Mode>("commercial");
  const [seconds, setSeconds] = useState<15 | 30 | 60>(30);
  const [ratio, setRatio] = useState<"16:9" | "9:16">("9:16");
  const [intake, setIntake] = useState<Intake>({ title: "", market: "", audience: "", platform: "", conversionGoal: "", visualStyle: "", spokenLanguage: "", subtitleLanguage: "", brief: "" });
  const [errors, setErrors] = useState<Partial<Record<keyof Intake, string>>>({});
  const [capabilities, setCapabilities] = useState<VideoProductionProviderCapabilities | null>(null);
  const [providerSelection, setProviderSelection] = useState<VideoProductionProviderSelection | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const submitted = useRef(false);
  const selection = choices.find((choice) => choice.id === mode)!;
  const dirty = Boolean(intake.title || intake.market || intake.audience || intake.platform || intake.conversionGoal || intake.visualStyle || intake.spokenLanguage || intake.subtitleLanguage || intake.brief || mode !== "commercial" || seconds !== 30 || ratio !== "9:16");

  async function loadCapabilities() {
    setCapabilitiesLoading(true); setCapabilitiesError(null);
    try {
      const response = await getVideoProductionCapabilities();
      setCapabilities(response); setProviderSelection((current) => current || defaultProviderSelection(response));
    } catch (cause) {
      setCapabilitiesError(cause instanceof Error ? cause.message : "Could not load the configured model catalogue.");
    } finally { setCapabilitiesLoading(false); }
  }

  useEffect(() => {
    const warnOnUnload = (event: BeforeUnloadEvent) => { if (!dirty || saving) return; event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warnOnUnload);
    return () => window.removeEventListener("beforeunload", warnOnUnload);
  }, [dirty, saving]);

  useEffect(() => { void loadCapabilities(); }, []);

  function setField(field: keyof Intake, value: string) { setIntake((current) => ({ ...current, [field]: value })); setErrors((current) => ({ ...current, [field]: undefined })); setRequestError(null); }
  function validate(target: Step) {
    const next: Partial<Record<keyof Intake, string>> = {};
    if (target >= 1 && intake.title.trim().length < 2) next.title = "Give this production a clear working name.";
    if (target >= 3) {
      if (intake.brief.trim().length < 20) next.brief = "Add a brief of at least 20 characters so the team can review intent before planning.";
      if (!intake.audience.trim()) next.audience = "Name the intended audience.";
      if (!intake.conversionGoal.trim()) next.conversionGoal = "State the desired viewer action or delivery outcome.";
    }
    setErrors(next); return Object.keys(next).length === 0;
  }
  function continueTo(nextStep: Step) {
    if (step === 2 && (!capabilities || !providerSelection)) {
      setCapabilitiesError("Wait for the configured model catalogue before continuing."); return;
    }
    if (validate(step)) setStep(nextStep);
  }
  function setProvider(operation: keyof VideoProductionProviderSelection, raw: string) {
    const [provider, model] = raw.split("::");
    setProviderSelection((current) => current ? { ...current, [operation]: { provider, model } } : current);
  }
  function returnToProjects() { if (!dirty || window.confirm("Leave this new production? Unsaved setup details will be lost.")) router.push("/video-production"); }
  async function createProject() {
    if (!validate(3) || !providerSelection || submitted.current) return;
    submitted.current = true; setSaving(true); setRequestError(null);
    const videoSetup: VideoProductionSetup = { target_market: intake.market.trim(), target_audience: intake.audience.trim(), video_type: selection.type, visual_style: intake.visualStyle.trim(), spoken_language: intake.spokenLanguage.trim(), subtitle_language: intake.subtitleLanguage.trim(), platform: intake.platform.trim() || (mode === "ctv" ? "CTV" : ""), conversion_goal: intake.conversionGoal.trim(), provider_selection: providerSelection, confirmed: true };
    try {
      const production = await createVideoProduction({ workspace_id: WORKSPACE_ID, title: intake.title.trim(), target_seconds: seconds, aspect_ratio: ratio, resolution: "1080p", brief: intake.brief.trim(), video_setup: videoSetup });
      router.push(`/video-production/projects/${production.production_id}`);
    } catch (cause) {
      submitted.current = false; setSaving(false); setRequestError(cause instanceof Error ? cause.message : "Could not create the production. Your details are still available to retry.");
    }
  }

  return <main className="min-h-[calc(100vh-72px)] bg-white px-5 py-9 text-[#101318] md:px-10 md:py-12"><div className="mx-auto max-w-[1240px]">
    <button type="button" onClick={returnToProjects} className="inline-flex items-center gap-2 text-xs font-semibold text-[#5f6673] transition hover:text-[#171a20]"><ArrowLeft className="size-3.5" />All productions</button>
    <header className="mt-8 border-b border-[#e6e8ec] pb-6 md:pb-8"><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5f6673]">New project · controlled setup</p><h1 className="mt-3 font-display text-4xl font-semibold tracking-[-0.055em] sm:text-5xl">Start a production with intent.</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-[#5f6673]">Define the delivery outcome, give the team an actionable brief, then confirm the project record. Setup never starts a model or a billable task.</p></header>
    <ol className="mt-7 grid gap-2 border-b border-[#e6e8ec] pb-6 sm:grid-cols-4" aria-label="New production steps">{stepLabels.map((label, index) => { const number = (index + 1) as Step; const current = step === number; const complete = step > number; return <li key={label} className={`flex items-center gap-3 rounded-xl border px-3 py-3 ${current ? "border-[#171a20] bg-[#171a20] text-white" : "border-[#e6e8ec] bg-white text-[#5f6673]"}`} aria-current={current ? "step" : undefined}><span className={`grid size-6 place-items-center rounded-full text-[11px] font-bold ${current ? "bg-white text-[#171a20]" : complete ? "bg-[#e8f4ec] text-[#2f7a48]" : "bg-[#f6f8fb] text-[#5f6673]"}`}>{complete ? <Check className="size-3.5" /> : number}</span><span><span className="block text-[10px] font-semibold uppercase tracking-[0.12em] opacity-70">Step 0{number}</span><span className="block text-sm font-semibold">{label}</span></span></li>; })}</ol>
    {step === 1 ? <section className="mt-8 grid gap-7 lg:grid-cols-[minmax(0,1fr)_330px]"><div><div className="flex items-end justify-between gap-4"><div><p className="text-lg font-semibold tracking-[-0.025em]">Choose the production outcome</p><p className="mt-1 text-sm text-[#5f6673]">All outcomes use the same reviewable project chain. Novel adaptation is not part of this product.</p></div><span className="hidden text-xs font-medium text-[#5f6673] sm:block">Required</span></div><div className="mt-5 grid gap-3 sm:grid-cols-2">{choices.map((choice) => { const Icon = choice.icon; const active = choice.id === mode; return <button key={choice.id} type="button" onClick={() => setMode(choice.id)} className={`group min-h-[190px] rounded-xl border p-5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#171a20]/25 ${active ? "border-[#171a20] bg-[#171a20] text-white shadow-[0_15px_35px_-28px_rgba(16,19,24,.85)]" : "border-[#e6e8ec] bg-white hover:border-[#c7ccd4] hover:bg-[#fafbfc]"}`}><span className={`grid size-9 place-items-center rounded-lg ${active ? "bg-white text-[#171a20]" : "bg-[#f6f8fb] text-[#171a20]"}`}><Icon className="size-4" /></span><div className="mt-9 flex items-start justify-between gap-3"><div><h2 className="text-xl font-semibold tracking-[-0.035em]">{choice.title}</h2><p className={`mt-2 text-xs leading-5 ${active ? "text-white/75" : "text-[#5f6673]"}`}>{choice.detail}</p></div>{active ? <CheckCircle2 className="size-5 shrink-0" /> : null}</div><p className={`mt-4 border-t pt-3 text-[11px] leading-5 ${active ? "border-white/20 text-white/65" : "border-[#e6e8ec] text-[#8b919c]"}`}>{choice.example}</p></button>; })}</div></div><aside className="h-fit rounded-2xl border border-[#e6e8ec] bg-[#fafbfc] p-5"><p className="text-sm font-semibold">Delivery specification</p><p className="mt-1 text-xs leading-5 text-[#5f6673]">These settings become the initial project record. They can be revised later with an audit trail.</p><label className="mt-5 block"><FieldLabel required>Project name</FieldLabel><Input value={intake.title} onChange={(event) => setField("title", event.target.value)} placeholder="e.g. Spring launch · 15s paid social" aria-invalid={Boolean(errors.title)} aria-describedby={errors.title ? "project-name-error" : undefined} /></label>{errors.title ? <p id="project-name-error" role="alert" className="mt-2 text-xs leading-5 text-[#b42318]">{errors.title}</p> : null}<fieldset className="mt-5"><legend><FieldLabel>Runtime</FieldLabel></legend><div className="mt-2 grid grid-cols-3 gap-2">{([15, 30, 60] as const).map((value) => <SelectButton key={value} active={seconds === value} onClick={() => setSeconds(value)}>{value}s</SelectButton>)}</div></fieldset><fieldset className="mt-5"><legend><FieldLabel>Format</FieldLabel></legend><div className="mt-2 grid grid-cols-2 gap-2">{(["9:16", "16:9"] as const).map((value) => <SelectButton key={value} active={ratio === value} onClick={() => setRatio(value)}><span className="block font-semibold">{value}</span><span className="mt-0.5 block text-[10px] opacity-75">{value === "9:16" ? "Vertical" : "Landscape"}</span></SelectButton>)}</div></fieldset><button type="button" onClick={() => continueTo(2)} className="mt-6 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#171a20] px-4 text-sm font-semibold text-white transition hover:bg-[#30343c]">Continue to creative brief <ArrowRight className="size-4" /></button></aside></section> : null}
    {step === 2 ? <section className="mt-8 grid gap-7 lg:grid-cols-[minmax(0,1fr)_330px]"><div><p className="text-lg font-semibold tracking-[-0.025em]">Choose the project&apos;s configured models</p><p className="mt-1 max-w-2xl text-sm leading-6 text-[#5f6673]">These choices apply only to this project. The catalogue comes from the server; endpoints, regions, credentials, and unconfigured models cannot be edited here.</p>{capabilitiesLoading ? <div className="mt-5 flex items-center gap-2 rounded-2xl border border-[#e6e8ec] bg-[#fafbfc] p-5 text-sm text-[#5f6673]"><Loader2 className="size-4 animate-spin" />Loading configured models…</div> : null}{capabilitiesError ? <div role="alert" className="mt-5 rounded-2xl border border-[#f5c2c0] bg-[#fff7f7] p-5 text-sm leading-6 text-[#8c1d18]"><p>{capabilitiesError}</p><button type="button" onClick={() => void loadCapabilities()} className="mt-3 rounded-lg bg-[#171a20] px-3 py-2 text-xs font-semibold text-white">Retry catalogue</button></div> : null}{capabilities && providerSelection ? <div className="mt-5 grid gap-4 sm:grid-cols-2"><ModelPicker label="Planning & agents" operation="text" options={capabilities.text} selection={providerSelection.text} onChange={setProvider} required /><ModelPicker label="Visual development" operation="image" options={capabilities.image} selection={providerSelection.image} onChange={setProvider} required /><ModelPicker label="Shot generation" operation="video" options={capabilities.video} selection={providerSelection.video} onChange={setProvider} required /><ModelPicker label="Soundtrack" operation="audio" options={capabilities.audio} selection={providerSelection.audio} onChange={setProvider} /></div> : null}</div><aside className="h-fit rounded-2xl border border-[#e6e8ec] bg-[#fafbfc] p-5"><p className="text-sm font-semibold">Configuration boundary</p><p className="mt-2 text-xs leading-5 text-[#5f6673]">Saving this draft records only these server-validated choices. It does not invoke a model or create a job.</p><button type="button" onClick={() => setStep(1)} className="mt-5 inline-flex h-10 items-center text-xs font-semibold text-[#5f6673] hover:text-[#171a20]"><ArrowLeft className="mr-1.5 size-3.5" />Back</button><button type="button" onClick={() => continueTo(3)} disabled={capabilitiesLoading || !capabilities || !providerSelection} className="mt-2 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#171a20] px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">Continue to creative brief <ArrowRight className="size-4" /></button></aside></section> : null}
    {step === 3 ? <section className="mt-8 grid gap-7 lg:grid-cols-[minmax(0,1fr)_330px]"><div><p className="text-lg font-semibold tracking-[-0.025em]">Make the brief reviewable</p><p className="mt-1 text-sm text-[#5f6673]">Describe intent and non-negotiables before anyone builds shots or requests media.</p><div className="mt-5 rounded-2xl border border-[#e6e8ec] bg-white p-5 sm:p-6"><div className="grid gap-5 sm:grid-cols-2"><label><FieldLabel>Target market</FieldLabel><Input value={intake.market} onChange={(event) => setField("market", event.target.value)} placeholder="e.g. US, KR, global" /></label><label><FieldLabel required>Audience</FieldLabel><Input value={intake.audience} onChange={(event) => setField("audience", event.target.value)} placeholder="e.g. returning mobile gamers" aria-invalid={Boolean(errors.audience)} /></label><label><FieldLabel>Platform / placement</FieldLabel><Input value={intake.platform} onChange={(event) => setField("platform", event.target.value)} placeholder={mode === "ctv" ? "CTV" : "e.g. TikTok, YouTube, CTV"} /></label><label><FieldLabel required>Desired action</FieldLabel><Input value={intake.conversionGoal} onChange={(event) => setField("conversionGoal", event.target.value)} placeholder="e.g. install, visit, understand offer" aria-invalid={Boolean(errors.conversionGoal)} /></label><label><FieldLabel>Spoken language</FieldLabel><Input value={intake.spokenLanguage} onChange={(event) => setField("spokenLanguage", event.target.value)} placeholder="e.g. English" /></label><label><FieldLabel>Subtitle language</FieldLabel><Input value={intake.subtitleLanguage} onChange={(event) => setField("subtitleLanguage", event.target.value)} placeholder="e.g. English" /></label></div><label className="mt-5 block"><FieldLabel>Visual direction</FieldLabel><Input value={intake.visualStyle} onChange={(event) => setField("visualStyle", event.target.value)} placeholder="e.g. polished product macro, direct-response proof" /></label><label className="mt-5 block"><FieldLabel required>Production brief</FieldLabel><textarea value={intake.brief} onChange={(event) => setField("brief", event.target.value)} placeholder="Audience, promise, product proof, customer-owned assets, required copy, legal constraints, and delivery objective…" aria-invalid={Boolean(errors.brief)} className="mt-2 min-h-40 w-full resize-y rounded-lg border border-[#e6e8ec] bg-white p-3 text-sm leading-6 text-[#171a20] outline-none placeholder:text-[#8b919c] focus:border-[#171a20] focus:ring-2 focus:ring-[#171a20]/10" /></label>{errors.audience || errors.conversionGoal || errors.brief ? <div role="alert" className="mt-3 rounded-lg border border-[#f5c2c0] bg-[#fff7f7] p-3 text-xs leading-5 text-[#b42318]">{errors.audience || errors.conversionGoal || errors.brief}</div> : null}</div></div><aside className="h-fit rounded-2xl border border-[#e6e8ec] bg-[#fafbfc] p-5"><div className="flex items-center gap-2"><MonitorPlay className="size-4" /><p className="text-sm font-semibold">What happens next</p></div><ol className="mt-4 space-y-3 text-xs leading-5 text-[#5f6673]"><li><span className="mr-2 font-semibold text-[#171a20]">01</span>Save a non-billable project draft.</li><li><span className="mr-2 font-semibold text-[#171a20]">02</span>Attach approved inputs and review the working script.</li><li><span className="mr-2 font-semibold text-[#171a20]">03</span>Approve a storyboard before keyframe or video generation.</li></ol><div className="mt-5 border-t border-[#e6e8ec] pt-4"><button type="button" onClick={() => setStep(2)} className="inline-flex h-10 items-center text-xs font-semibold text-[#5f6673] hover:text-[#171a20]"><ArrowLeft className="mr-1.5 size-3.5" />Back</button><button type="button" onClick={() => continueTo(4)} className="mt-2 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#171a20] px-4 text-sm font-semibold text-white hover:bg-[#30343c]">Review project <ArrowRight className="size-4" /></button></div></aside></section> : null}
    {step === 4 ? <section className="mt-8 grid gap-7 lg:grid-cols-[minmax(0,1fr)_330px]"><div><div className="flex items-center gap-2"><Sparkles className="size-4 text-[#356fec]" /><p className="text-lg font-semibold tracking-[-0.025em]">Review before creating</p></div><p className="mt-1 text-sm text-[#5f6673]">This is a saved project brief, not a generation request. You can edit it after creation.</p><dl className="mt-5 divide-y divide-[#e6e8ec] overflow-hidden rounded-2xl border border-[#e6e8ec] bg-white"><ReviewRow label="Project" value={intake.title} /><ReviewRow label="Outcome" value={selection.title} /><ReviewRow label="Delivery" value={`${seconds}s · ${ratio} · 1080p`} /><ReviewRow label="Planning model" value={providerSelection?.text.model || "Not configured"} /><ReviewRow label="Visual model" value={providerSelection?.image.model || "Not configured"} /><ReviewRow label="Video model" value={providerSelection?.video.model || "Not configured"} /><ReviewRow label="Audience" value={intake.audience} /><ReviewRow label="Desired action" value={intake.conversionGoal} /><ReviewRow label="Market / placement" value={[intake.market, intake.platform || (mode === "ctv" ? "CTV" : "")].filter(Boolean).join(" · ") || "Not specified"} /><ReviewRow label="Brief" value={intake.brief} long /></dl></div><aside className="h-fit rounded-2xl border border-[#171a20] bg-[#171a20] p-5 text-white"><CheckCircle2 className="size-5" /><h2 className="mt-4 text-lg font-semibold">Ready to save a draft</h2><p className="mt-2 text-xs leading-5 text-white/70">No platform configuration is changed. No image, video, audio, agent, render, or delivery job is started.</p>{requestError ? <p role="alert" className="mt-4 rounded-lg bg-white/10 p-3 text-xs leading-5 text-white">{requestError}</p> : null}<button type="button" onClick={() => void createProject()} disabled={saving} className="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-white px-4 text-sm font-semibold text-[#171a20] transition hover:bg-[#f0f2f4] disabled:cursor-not-allowed disabled:opacity-50">{saving ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}{saving ? "Creating project…" : "Create project"}</button><button type="button" onClick={() => setStep(3)} disabled={saving} className="mt-3 inline-flex w-full items-center justify-center gap-1.5 text-xs font-semibold text-white/75 hover:text-white disabled:opacity-40"><ArrowLeft className="size-3.5" />Edit brief</button></aside></section> : null}
  </div></main>;
}

function ReviewRow({ label, value, long = false }: { label: string; value: string; long?: boolean }) {
  return <div className={`grid gap-2 px-5 py-4 sm:grid-cols-[150px_minmax(0,1fr)] ${long ? "items-start" : "items-center"}`}><dt className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#5f6673]">{label}</dt><dd className={`min-w-0 text-sm text-[#171a20] ${long ? "whitespace-pre-wrap leading-6" : "truncate font-medium"}`}>{value}</dd></div>;
}

function ModelPicker({ label, operation, options, selection, onChange, required = false }: { label: string; operation: keyof VideoProductionProviderSelection; options: VideoProductionProviderCapabilities["text"]; selection: VideoProductionProviderSelection["text"]; onChange: (operation: keyof VideoProductionProviderSelection, value: string) => void; required?: boolean }) {
  const value = selection.provider && selection.model ? `${selection.provider}::${selection.model}` : "";
  return <label className="rounded-2xl border border-[#e6e8ec] bg-white p-5"><FieldLabel required={required}>{label}</FieldLabel><p className="mt-1 min-h-10 text-xs leading-5 text-[#5f6673]">{options.length ? "Configured by the platform team for this operation." : "No configured model is currently available for this optional operation."}</p><select value={value} disabled={!options.length} onChange={(event) => onChange(operation, event.target.value)} className="mt-4 h-10 w-full rounded-lg border border-[#e6e8ec] bg-white px-3 text-sm text-[#171a20] outline-none disabled:cursor-not-allowed disabled:bg-[#f6f8fb]"><option value="" disabled>{options.length ? "Select configured model" : "Not configured"}</option>{options.map((option) => <option key={`${option.provider}:${option.model}`} value={`${option.provider}::${option.model}`}>{option.label} · {option.model}</option>)}</select></label>;
}
