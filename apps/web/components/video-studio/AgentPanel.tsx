"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Bot, LoaderCircle, MessageSquarePlus, Paperclip, Send, Trash2, UserRound, X } from "lucide-react";
import { videoStudioApi } from "./api";
import type { AgentConversation, AgentMessage, AssetEntry, CanvasDocument, ExtensionDefinition } from "./types";

export function AgentPanel({
  projectId,
  isChinese,
  onCanvas,
}: {
  projectId: string;
  isChinese: boolean;
  onCanvas: (canvas: CanvasDocument) => void;
}) {
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [agentId, setAgentId] = useState("workflow");
  const [assetChoices, setAssetChoices] = useState<AssetEntry[]>([]);
  const [agentChoices, setAgentChoices] = useState<ExtensionDefinition[]>([]);
  const [attachedAssets, setAttachedAssets] = useState<string[]>([]);
  const [showAssets, setShowAssets] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(async () => {
    const list = await videoStudioApi.listConversations(projectId);
    setConversations(list);
    if (conversationId) {
      const active = list.find((item) => item.id === conversationId);
      if (active) setMessages(active.messages);
    }
  }, [conversationId, projectId]);

  useEffect(() => { void loadConversations(); }, [loadConversations]);
  useEffect(() => {
    let active = true;
    const loadOptions = async () => {
      try {
        const [catalog] = await Promise.all([videoStudioApi.getCatalog()]);
        const files: AssetEntry[] = [];
        const pending = [""];
        while (pending.length > 0 && files.length < 500) {
          const path = pending.shift() || "";
          const entries = await videoStudioApi.listAssets(projectId, path);
          for (const entry of entries) {
            if (entry.kind === "directory") pending.push(entry.path);
            else files.push(entry);
          }
        }
        if (!active) return;
        setAssetChoices(files);
        const enabledAgents = catalog.extensions.filter((item) => item.category === "agent" && item.enabled);
        setAgentChoices(enabledAgents);
        if (!enabledAgents.some((item) => item.id === `agent-${agentId}`)) {
          setAgentId(enabledAgents[0]?.id.replace(/^agent-/, "") || "");
        }
      } catch {
        if (active) {
          setAssetChoices([]);
          setAgentChoices([]);
        }
      }
    };
    void loadOptions();
    return () => { active = false; };
  }, [agentId, projectId]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }); }, [messages, running]);

  const selectConversation = (conversation: AgentConversation) => {
    setConversationId(conversation.id);
    setMessages(conversation.messages);
    setError("");
  };

  const newConversation = () => {
    setConversationId(null);
    setMessages([]);
    setError("");
  };

  const renameConversation = async (conversation: AgentConversation) => {
    const name = window.prompt(isChinese ? "重命名对话" : "Rename conversation", conversation.name)?.trim();
    if (!name) return;
    await videoStudioApi.renameConversation(projectId, conversation.id, name);
    await loadConversations();
  };

  const deleteConversation = async (conversation: AgentConversation) => {
    if (!window.confirm(isChinese ? `删除对话“${conversation.name}”？` : `Delete “${conversation.name}”?`)) return;
    await videoStudioApi.deleteConversation(projectId, conversation.id);
    if (conversationId === conversation.id) newConversation();
    await loadConversations();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = prompt.trim();
    if (!value || running) return;
    const optimistic: AgentMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: value,
      created_at: new Date().toISOString(),
    };
    setMessages((items) => [...items, optimistic]);
    setPrompt("");
    setError("");
    setRunning(true);
    let nextConversationId = conversationId;
    try {
      await videoStudioApi.runAgent(projectId, value, conversationId, (agentEvent) => {
        if (agentEvent.type === "canvas") onCanvas(agentEvent.canvas);
        if (agentEvent.type === "message") {
          nextConversationId = agentEvent.conversation_id;
          setConversationId(agentEvent.conversation_id);
          setMessages((items) => [...items, {
            id: crypto.randomUUID(),
            role: "assistant",
            content: agentEvent.message,
            created_at: new Date().toISOString(),
          }]);
        }
        if (agentEvent.type === "error") setError(agentEvent.message);
      }, { agentId, assetPaths: attachedAssets });
      setConversationId(nextConversationId);
      await loadConversations();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agent failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <select aria-label={isChinese ? "选择智能体" : "Select agent"} value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={agentChoices.length === 0} className="min-w-0 rounded-md border-0 bg-transparent text-xs font-semibold outline-none disabled:opacity-50">{agentChoices.map((agent) => <option key={agent.id} value={agent.id.replace(/^agent-/, "")}>{agent.name}</option>)}</select>
        <button onClick={newConversation} aria-label={isChinese ? "新对话" : "New conversation"} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"><MessageSquarePlus className="size-4" /></button>
      </div>
      {conversations.length > 0 && (
        <div className="flex gap-1 overflow-x-auto border-b border-border-soft px-2 py-2">
          {conversations.slice(0, 6).map((conversation) => <span key={conversation.id} className={`flex max-w-40 shrink-0 items-center rounded-md ${conversation.id === conversationId ? "bg-[#f2eafe] text-[#8b5cf6]" : "text-muted-foreground hover:bg-muted"}`}><button onClick={() => selectConversation(conversation)} onDoubleClick={() => void renameConversation(conversation)} className="min-w-0 flex-1 truncate px-2 py-1 text-[11px]">{conversation.name}</button><button onClick={() => void deleteConversation(conversation)} aria-label={isChinese ? "删除对话" : "Delete conversation"} className="p-1 opacity-60 hover:opacity-100"><Trash2 className="size-3" /></button></span>)}
        </div>
      )}
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 && <div className="flex h-full flex-col items-center justify-center px-3 text-center"><span className="flex size-10 items-center justify-center rounded-xl bg-soft-accent text-[#356fec]"><Bot className="size-5" /></span><p className="mt-3 text-sm font-medium">{isChinese ? "让智能体搭建工作流" : "Build with the agent"}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{isChinese ? "描述视频目标，它可以创建、修改和连接画布节点。" : "Describe the video goal. It can create, edit, and connect canvas nodes."}</p></div>}
        {messages.map((message) => <div key={message.id} className={`flex gap-2 ${message.role === "user" ? "flex-row-reverse" : ""}`}><span className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md ${message.role === "user" ? "bg-foreground text-white" : "bg-soft-accent text-[#356fec]"}`}>{message.role === "user" ? <UserRound className="size-3.5" /> : <Bot className="size-3.5" />}</span><p className={`max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-xs leading-5 ${message.role === "user" ? "bg-foreground text-white" : "bg-muted text-foreground"}`}>{message.content}</p></div>)}
        {running && <div className="flex items-center gap-2 text-xs text-muted-foreground"><LoaderCircle className="size-3.5 animate-spin" />{isChinese ? "智能体正在规划并更新画布…" : "Agent is planning and updating the canvas…"}</div>}
        {error && <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
      </div>
      <form onSubmit={(event) => void submit(event)} className="border-t border-border p-2">
        {attachedAssets.length > 0 && <div className="mb-2 flex flex-wrap gap-1">{attachedAssets.map((path) => <span key={path} className="inline-flex max-w-full items-center gap-1 rounded-full bg-[#f2eafe] px-2 py-1 text-[10px] text-[#7c3aed]"><span className="truncate">{path}</span><button type="button" onClick={() => setAttachedAssets((items) => items.filter((item) => item !== path))}><X className="size-3" /></button></span>)}</div>}
        <div className="rounded-xl border border-border bg-white p-2 focus-within:border-[#356fec]">
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} rows={3} className="w-full resize-none border-0 bg-transparent px-1 text-xs leading-5 outline-none" placeholder={isChinese ? "例如：创建一个 15 秒产品发布视频工作流" : "e.g. Build a 15-second product launch workflow"} />
          <div className="relative flex justify-between"><button type="button" onClick={() => setShowAssets((value) => !value)} aria-label={isChinese ? "添加项目素材" : "Attach project asset"} className="flex size-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"><Paperclip className="size-3.5" /></button>{showAssets && <div className="absolute bottom-9 left-0 z-40 max-h-52 w-64 overflow-y-auto rounded-xl border border-border bg-white p-1 shadow-xl">{assetChoices.length === 0 ? <p className="p-3 text-[11px] text-muted-foreground">{isChinese ? "项目中没有可附加素材" : "No project assets to attach"}</p> : assetChoices.map((asset) => <button key={asset.path} type="button" title={asset.path} onClick={() => { setAttachedAssets((items) => items.includes(asset.path) ? items : [...items, asset.path]); setShowAssets(false); }} className="block w-full truncate rounded-lg px-2 py-2 text-left text-[11px] hover:bg-muted">{asset.path}</button>)}</div>}<button type="submit" disabled={!prompt.trim() || running || !agentId} aria-label={isChinese ? "发送" : "Send"} className="flex size-7 items-center justify-center rounded-lg bg-foreground text-white disabled:opacity-35"><Send className="size-3.5" /></button></div>
        </div>
      </form>
    </div>
  );
}
