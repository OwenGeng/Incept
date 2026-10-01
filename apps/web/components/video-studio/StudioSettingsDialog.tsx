"use client";

import { Download, LoaderCircle, Plus, Settings, Upload, X } from "lucide-react";
import { ChangeEvent, useEffect, useRef, useState } from "react";
import { videoStudioApi } from "./api";
import type { CatalogSnapshot, StudioSettings } from "./types";

const defaultSettings: StudioSettings = {
  language: "zh-CN",
  theme: "light",
  default_image_ratio: "16:9",
  default_video_duration: 5,
  agent_system_prompt: "",
  default_agent: "workflow",
  default_text_model: "deployment-default",
  privacy_mode: "private",
};

export function StudioSettingsDialog({
  open,
  onClose,
  isChinese,
}: {
  open: boolean;
  onClose: () => void;
  isChinese: boolean;
}) {
  const [tab, setTab] = useState<"general" | "skills" | "extensions">("general");
  const [settings, setSettings] = useState<StudioSettings>(defaultSettings);
  const [catalog, setCatalog] = useState<CatalogSnapshot>({ skills: [], extensions: [] });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const importInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError("");
    Promise.all([videoStudioApi.getSettings(), videoStudioApi.getCatalog()])
      .then(([nextSettings, nextCatalog]) => {
        setSettings(nextSettings);
        setCatalog(nextCatalog);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Failed to load settings"))
      .finally(() => setLoading(false));
  }, [open]);

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const [nextSettings, nextCatalog] = await Promise.all([
        videoStudioApi.saveSettings(settings),
        videoStudioApi.saveCatalog(catalog),
      ]);
      setSettings(nextSettings);
      setCatalog(nextCatalog);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const exportCatalog = () => {
    const blob = new Blob([JSON.stringify(catalog, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "linglonglab-video-catalog.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const importCatalog = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const value = JSON.parse(await file.text()) as CatalogSnapshot;
      if (!Array.isArray(value.skills) || !Array.isArray(value.extensions)) throw new Error("Invalid catalog file");
      setCatalog(value);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invalid catalog file");
    } finally {
      event.target.value = "";
    }
  };

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/30 p-4" onMouseDown={onClose}>
      <section className="flex h-[min(760px,90vh)] w-full max-w-4xl overflow-hidden rounded-2xl border border-border bg-white shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <aside className="w-48 shrink-0 border-r border-border bg-[#f8fafc] p-3">
          <div className="flex items-center gap-2 px-2 py-2 text-sm font-semibold"><Settings className="size-4" />{isChinese ? "视频设置" : "Video settings"}</div>
          {(["general", "skills", "extensions"] as const).map((item) => <button key={item} onClick={() => setTab(item)} className={`mt-1 w-full rounded-lg px-3 py-2 text-left text-sm ${tab === item ? "bg-white font-medium shadow-sm" : "text-muted-foreground hover:bg-white"}`}>{item === "general" ? (isChinese ? "常规" : "General") : item === "skills" ? (isChinese ? "技能" : "Skills") : (isChinese ? "扩展" : "Extensions")}</button>)}
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 items-center justify-between border-b border-border px-5"><h2 className="font-semibold">{tab === "general" ? (isChinese ? "常规与模型" : "General & models") : tab === "skills" ? (isChinese ? "智能体技能" : "Agent skills") : (isChinese ? "节点、工具与智能体" : "Nodes, tools & agents")}</h2><button onClick={onClose} className="rounded-lg p-2 text-muted-foreground hover:bg-muted"><X className="size-4" /></button></header>
          <div className="flex-1 overflow-y-auto p-5">
            {loading ? <div className="flex h-full items-center justify-center"><LoaderCircle className="size-5 animate-spin" /></div> : tab === "general" ? <div className="max-w-xl space-y-5">
              <Field label={isChinese ? "界面语言" : "Language"}><select value={settings.language} onChange={(event) => setSettings({ ...settings, language: event.target.value as StudioSettings["language"] })} className="w-full rounded-lg border border-border px-3 py-2 text-sm"><option value="zh-CN">中文</option><option value="en-US">English</option></select></Field>
              <div className="grid grid-cols-2 gap-4"><Field label={isChinese ? "默认画幅" : "Default ratio"}><select value={settings.default_image_ratio} onChange={(event) => setSettings({ ...settings, default_image_ratio: event.target.value })} className="w-full rounded-lg border border-border px-3 py-2 text-sm"><option>16:9</option><option>9:16</option><option>1:1</option><option>4:3</option></select></Field><Field label={isChinese ? "默认视频时长（秒）" : "Default duration (seconds)"}><input type="number" min={1} max={60} value={settings.default_video_duration} onChange={(event) => setSettings({ ...settings, default_video_duration: Number(event.target.value) })} className="w-full rounded-lg border border-border px-3 py-2 text-sm" /></Field></div>
              <Field label={isChinese ? "默认智能体" : "Default agent"}><select value={settings.default_agent} onChange={(event) => setSettings({ ...settings, default_agent: event.target.value })} className="w-full rounded-lg border border-border px-3 py-2 text-sm"><option value="workflow">{isChinese ? "工作流智能体" : "Workflow agent"}</option><option value="storyboard">{isChinese ? "分镜团队" : "Storyboard team"}</option></select></Field>
              <Field label={isChinese ? "文本模型" : "Text model"}><input disabled value={settings.default_text_model} className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm text-muted-foreground" /><p className="mt-1.5 text-xs text-muted-foreground">{isChinese ? "模型、区域和服务账号由 LinglongLab 部署配置统一管理。" : "Model, location, and service account are managed by the LinglongLab deployment."}</p></Field>
              <Field label={isChinese ? "自定义智能体指令" : "Custom agent instructions"}><textarea value={settings.agent_system_prompt} onChange={(event) => setSettings({ ...settings, agent_system_prompt: event.target.value })} className="min-h-32 w-full resize-y rounded-lg border border-border px-3 py-2 text-sm" /></Field>
              <div className="rounded-xl border border-border bg-[#f8fafc] p-4"><p className="text-sm font-medium">{isChinese ? "隐私" : "Privacy"}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{isChinese ? "项目、素材、对话和扩展配置按登录用户隔离；浏览器不接触云端凭据。" : "Projects, assets, conversations, and extension settings are isolated per signed-in user; cloud credentials never reach the browser."}</p></div>
            </div> : tab === "skills" ? <div className="space-y-3">
              {catalog.skills.map((skill, index) => <div key={skill.id} className="rounded-xl border border-border p-4"><div className="flex items-start justify-between gap-4"><div><input value={skill.name} onChange={(event) => setCatalog({ ...catalog, skills: catalog.skills.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item) })} className="font-medium outline-none" /><p className="mt-1 text-xs text-muted-foreground">{skill.id}{skill.builtin ? ` · ${isChinese ? "内置" : "Built in"}` : ""}</p></div><Toggle checked={skill.enabled} onChange={(enabled) => setCatalog({ ...catalog, skills: catalog.skills.map((item, itemIndex) => itemIndex === index ? { ...item, enabled } : item) })} /></div><textarea value={skill.instructions} onChange={(event) => setCatalog({ ...catalog, skills: catalog.skills.map((item, itemIndex) => itemIndex === index ? { ...item, instructions: event.target.value } : item) })} className="mt-3 min-h-24 w-full resize-y rounded-lg border border-border px-3 py-2 text-xs" /></div>)}
              <button onClick={() => setCatalog({ ...catalog, skills: [...catalog.skills, { id: `custom-${Date.now()}`, name: isChinese ? "新技能" : "New skill", description: "", instructions: "", enabled: true, builtin: false, order: catalog.skills.length }] })} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"><Plus className="size-4" />{isChinese ? "添加技能" : "Add skill"}</button>
            </div> : <div>
              <div className="mb-4 flex justify-end gap-2"><button onClick={() => importInput.current?.click()} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs"><Upload className="size-3.5" />{isChinese ? "导入清单" : "Import manifest"}</button><button onClick={exportCatalog} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs"><Download className="size-3.5" />{isChinese ? "导出清单" : "Export manifest"}</button><input ref={importInput} type="file" accept="application/json" onChange={(event) => void importCatalog(event)} className="hidden" /></div>
              {(["node", "tool", "agent"] as const).map((category) => <section key={category} className="mb-6"><h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{category}s</h3><div className="grid gap-2 sm:grid-cols-2">{catalog.extensions.filter((item) => item.category === category).map((extension) => <div key={extension.id} className="flex items-start justify-between gap-3 rounded-xl border border-border p-3"><div><p className="text-sm font-medium">{extension.name}</p><p className="mt-1 text-xs leading-4 text-muted-foreground">{extension.description}</p></div><Toggle checked={extension.enabled} onChange={(enabled) => setCatalog({ ...catalog, extensions: catalog.extensions.map((item) => item.id === extension.id ? { ...item, enabled } : item) })} /></div>)}</div></section>)}
            </div>}
            {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
          </div>
          <footer className="flex items-center justify-end gap-2 border-t border-border px-5 py-3"><button onClick={onClose} className="rounded-lg border border-border px-4 py-2 text-sm">{isChinese ? "取消" : "Cancel"}</button><button onClick={() => void save()} disabled={saving || loading} className="inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving && <LoaderCircle className="size-4 animate-spin" />}{isChinese ? "保存设置" : "Save settings"}</button></footer>
        </div>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><span className="mb-2 block text-xs font-medium">{label}</span>{children}</label>;
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className={`relative h-5 w-9 shrink-0 rounded-full transition ${checked ? "bg-[#356fec]" : "bg-slate-300"}`}><span className={`absolute top-0.5 size-4 rounded-full bg-white transition ${checked ? "left-[18px]" : "left-0.5"}`} /></button>;
}
