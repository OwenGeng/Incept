"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  addEdge,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Bot,
  Clapperboard,
  Copy,
  FileText,
  ImageIcon,
  LayoutTemplate,
  Library,
  MoreHorizontal,
  PanelRight,
  Pencil,
  Play,
  Plus,
  Redo2,
  Sparkles,
  Trash2,
  Undo2,
  Workflow,
  X,
} from "lucide-react";
import type { AssetSummary, JobSummary } from "@linglonglab/shared";
import { AppHeader } from "@/components/ui/app-header";
import { AppSidebar } from "@/components/ui/app-sidebar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listAssets } from "@/lib/incept-api";
import { signOut, useSession } from "next-auth/react";
import {
  createStudioWorkflow,
  cancelStudioWorkflowRun,
  deleteStudioWorkflow,
  getStudioWorkflowLineage,
  getStudioWorkflowRunNodes,
  listStudioWorkflowNodeDefinitions,
  listStudioWorkflowOutputs,
  listStudioWorkflowRevisions,
  listStudioWorkflows,
  runStudioWorkflow,
  retryStudioWorkflowRun,
  updateStudioWorkflow,
  validateStudioWorkflow,
  type StudioWorkflow,
  type StudioWorkflowGraph,
  type StudioWorkflowRunNode,
  type StudioWorkflowNodeDefinition,
  type StudioWorkflowOutput,
  type StudioWorkflowRevision,
  type StudioWorkflowLineage,
} from "@/lib/workflow-api";

type WorkflowTemplate = "script" | "image" | "video" | "commercial";

type WorkflowNodeData = {
  title: string;
  subtitle: string;
  nodeType?: string;
  kind: "input" | "agent" | "generate" | "output";
  status?: string;
  params?: Record<string, unknown>;
  inputs?: StudioWorkflowNodeDefinition["inputs"];
  outputs?: StudioWorkflowNodeDefinition["outputs"];
};
type GraphSnapshot = { nodes: Node<WorkflowNodeData>[]; edges: Edge[]; selectedNode: string | null };

const TEMPLATE_META: Record<WorkflowTemplate, { label: string; detail: string; icon: typeof FileText }> = {
  script: { label: "Write a script", detail: "Reference → strategy → screenplay", icon: FileText },
  image: { label: "Create an image", detail: "Prompt + assets → image candidates", icon: ImageIcon },
  video: { label: "Create a video shot", detail: "Keyframe + prompt → video take", icon: Clapperboard },
  commercial: { label: "Create a commercial", detail: "Strategy → script → assets → storyboard", icon: Workflow },
};

const TEMPLATE_NODES: Record<WorkflowTemplate, Node<WorkflowNodeData>[]> = {
  script: [
    { id: "reference", type: "workflow", position: { x: 32, y: 170 }, data: { title: "Creative reference", subtitle: "Video, image, or brief", kind: "input", status: "draft" } },
    { id: "strategy", type: "workflow", position: { x: 310, y: 170 }, data: { title: "Creative Strategist", subtitle: "Analyse reference and brand", kind: "agent", status: "draft" } },
    { id: "screenwriter", type: "workflow", position: { x: 610, y: 170 }, data: { title: "Senior Screenwriter", subtitle: "Build the timed script", kind: "agent", status: "draft" } },
    { id: "script", type: "workflow", position: { x: 910, y: 170 }, data: { title: "Approved script", subtitle: "Editable screenplay output", kind: "output", status: "draft" } },
  ],
  image: [
    { id: "prompt", type: "workflow", position: { x: 32, y: 170 }, data: { title: "Prompt & references", subtitle: "Brief, aspect ratio, assets", kind: "input", status: "draft" } },
    { id: "image", type: "workflow", position: { x: 350, y: 170 }, data: { title: "Generate image", subtitle: "Configured image provider", kind: "generate", status: "draft" } },
    { id: "selection", type: "workflow", position: { x: 670, y: 170 }, data: { title: "Select candidate", subtitle: "Approve a visual state", kind: "output", status: "draft" } },
  ],
  video: [
    { id: "keyframe", type: "workflow", position: { x: 32, y: 170 }, data: { title: "Approved keyframe", subtitle: "Selected visual starting state", kind: "input", status: "draft" } },
    { id: "shot", type: "workflow", position: { x: 350, y: 170 }, data: { title: "Generate video shot", subtitle: "Prompt, motion, duration", kind: "generate", status: "draft" } },
    { id: "take", type: "workflow", position: { x: 670, y: 170 }, data: { title: "Select take", subtitle: "Approve video output", kind: "output", status: "draft" } },
  ],
  commercial: [
    { id: "reference", type: "workflow", position: { x: 32, y: 260 }, data: { title: "Reference & brand assets", subtitle: "Source contract", kind: "input", status: "draft" } },
    { id: "strategy", type: "workflow", position: { x: 300, y: 120 }, data: { title: "Creative Strategist", subtitle: "Original campaign direction", kind: "agent", status: "draft" } },
    { id: "script", type: "workflow", position: { x: 580, y: 120 }, data: { title: "Senior Screenwriter", subtitle: "Locked timed script", kind: "agent", status: "draft" } },
    { id: "design", type: "workflow", position: { x: 580, y: 370 }, data: { title: "Production Designer", subtitle: "Character, environment, UI", kind: "agent", status: "draft" } },
    { id: "director", type: "workflow", position: { x: 860, y: 245 }, data: { title: "Storyboard Director", subtitle: "Shots and continuity", kind: "agent", status: "draft" } },
    { id: "delivery", type: "workflow", position: { x: 1160, y: 245 }, data: { title: "Commercial delivery", subtitle: "Approved shots and CTA", kind: "output", status: "draft" } },
  ],
};

function templateEdges(template: WorkflowTemplate): Edge[] {
  const ids = TEMPLATE_NODES[template].map((node) => node.id);
  if (template === "commercial") {
    return [
      { id: "reference-strategy", source: "reference", target: "strategy", animated: true },
      { id: "strategy-script", source: "strategy", target: "script", animated: true },
      { id: "strategy-design", source: "strategy", target: "design", animated: true },
      { id: "script-director", source: "script", target: "director", animated: true },
      { id: "design-director", source: "design", target: "director", animated: true },
      { id: "director-delivery", source: "director", target: "delivery", animated: true },
    ];
  }
  return ids.slice(1).map((target, index) => ({ id: `${ids[index]}-${target}`, source: ids[index], target, animated: true }));
}

function WorkflowNode({ data, selected }: NodeProps<Node<WorkflowNodeData>>) {
  if (data.nodeType === "incept.group.v1") {
    const count = Array.isArray(data.params?.group_member_ids) ? data.params.group_member_ids.length : 0;
    return <div className={cn("min-h-40 min-w-72 rounded-2xl border-2 border-dashed border-orange-300 bg-orange-50/60 p-3 text-orange-950", selected && "ring-2 ring-orange-400")}>
      <p className="text-xs font-semibold">{data.title}</p><p className="mt-1 text-[10px] text-orange-800">{count} grouped node{count === 1 ? "" : "s"}</p>
    </div>;
  }
  const icon = data.kind === "agent" ? <Bot className="size-4" /> : data.kind === "generate" ? <Sparkles className="size-4" /> : data.kind === "output" ? <Library className="size-4" /> : <LayoutTemplate className="size-4" />;
  return (
    <div className={cn("w-56 rounded-2xl border bg-card p-4 shadow-sm transition-shadow", selected ? "border-foreground/60 shadow-lg" : "border-border")}>
      {(data.inputs ?? []).map((port, index) => <div key={port.id} className="relative ml-1 flex items-center gap-1 text-[9px] text-muted-foreground" style={{ minHeight: 14 }}><Handle id={port.id} type="target" position={Position.Left} style={{ top: 8 + index * 14 }} className="!size-2 !border-2 !border-background !bg-orange-500" /><span className="truncate">{port.id} · {port.value_type}</span></div>)}
      <div className="flex items-start gap-2.5">
        <div className="rounded-lg bg-muted p-2 text-foreground">{icon}</div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{data.title}</p>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{data.subtitle}</p>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between border-t pt-3">
        <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{data.kind}</span>
        <Badge variant="outline" className={cn("h-5 px-1.5 text-[10px]", ["ready", "valid", "succeeded", "approved"].includes(data.status ?? "") && "border-emerald-200 bg-emerald-50 text-emerald-700", ["failed", "blocked", "cancelled"].includes(data.status ?? "") && "border-red-200 bg-red-50 text-red-700", ["queued", "stale"].includes(data.status ?? "") && "border-amber-200 bg-amber-50 text-amber-700", data.status === "running" && "border-sky-200 bg-sky-50 text-sky-700")}>{data.status ?? "draft"}</Badge>
      </div>
      {(data.outputs ?? []).map((port, index) => <div key={port.id} className="relative mr-1 flex justify-end text-[9px] text-muted-foreground" style={{ minHeight: 14 }}><span className="truncate">{port.id} · {port.value_type}</span><Handle id={port.id} type="source" position={Position.Right} style={{ top: 8 + index * 14 }} className="!size-2 !border-2 !border-background !bg-sky-600" /></div>)}
    </div>
  );
}

const nodeTypes = { workflow: WorkflowNode };

function CandidateReviewDialog({ candidates, active, selectedId, onClose, onChoose, onActive }: { candidates: AssetSummary[]; active: AssetSummary; selectedId: string; onClose: () => void; onChoose: (assetId: string) => void; onActive: (asset: AssetSummary) => void }) {
  const labels = ["A", "B", "C", "D"];
  return <div role="dialog" aria-modal="true" aria-label="Candidate contact sheet review" className="fixed inset-0 z-[70] grid place-items-center bg-black/70 p-5" onClick={onClose}>
    <div className="flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-background p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
      <div className="mb-4 flex items-start justify-between gap-4"><div><h2 className="text-lg font-semibold">Review candidates</h2><p className="mt-1 text-sm text-muted-foreground">Compare A/B/C/D, open a full preview, then explicitly approve one.</p></div><Button variant="ghost" size="icon" onClick={onClose}><X className="size-4" /></Button></div>
      <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[minmax(0,1fr)_17rem]"><div className="min-h-0 rounded-xl bg-muted/50 p-2">{active.type === "video" ? <video src={active.url} controls autoPlay className="max-h-[54vh] w-full rounded-lg bg-black" /> : <img src={active.url} alt={active.title} className="max-h-[54vh] w-full rounded-lg object-contain" />}</div><div className="grid content-start grid-cols-2 gap-2 overflow-auto pr-1">{candidates.map((asset, index) => <button type="button" key={asset.id} onClick={() => onActive(asset)} className={cn("group relative overflow-hidden rounded-lg border bg-muted text-left ring-offset-background", asset.id === active.id && "ring-2 ring-foreground", asset.id === selectedId && "border-emerald-500")}><span className="absolute left-1.5 top-1.5 z-10 grid size-6 place-items-center rounded-full bg-background/90 text-xs font-bold">{labels[index] ?? index + 1}</span>{asset.type === "video" ? <video src={asset.url} muted preload="metadata" className="aspect-[4/5] w-full object-cover" /> : <img src={asset.url} alt={asset.title} className="aspect-[4/5] w-full object-cover" />}<span className="block truncate px-2 py-1.5 text-[10px] font-medium">{asset.id === selectedId ? "Approved choice" : asset.title}</span></button>)}</div></div>
      <div className="mt-4 flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Keep reviewing</Button><Button onClick={() => onChoose(active.id)}>Use candidate {labels[candidates.findIndex((candidate) => candidate.id === active.id)] ?? ""}</Button></div>
    </div>
  </div>;
}

function nodeKind(type: string): WorkflowNodeData["kind"] {
  if (type.includes("agent")) return "agent";
  if (type.includes("image") || type.includes("video") || type.includes("delivery")) return "generate";
  if (type.includes("approval")) return "output";
  return "input";
}

function flowNodes(workflow: StudioWorkflow, definitions: StudioWorkflowNodeDefinition[] = []): Node<WorkflowNodeData>[] {
  return workflow.graph.nodes.map((node) => ({
    id: node.id,
    type: "workflow",
    position: node.position,
    data: { title: node.label, subtitle: node.type.replace("incept.", "").replace(/\.v1$/, "").replaceAll(".", " · "), nodeType: node.type, kind: nodeKind(node.type), status: node.status, params: node.params, inputs: definitions.find((definition) => definition.type === node.type)?.inputs ?? [], outputs: definitions.find((definition) => definition.type === node.type)?.outputs ?? [] },
  }));
}

function flowEdges(workflow: StudioWorkflow, definitions: StudioWorkflowNodeDefinition[] = []): Edge[] {
  const typeById = new Map(workflow.graph.nodes.map((node) => [node.id, node.type]));
  const definition = (nodeId: string) => definitions.find((item) => item.type === typeById.get(nodeId));
  return workflow.graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source_node_id,
    sourceHandle: edge.source_port === "output" ? definition(edge.source_node_id)?.outputs[0]?.id ?? edge.source_port : edge.source_port,
    target: edge.target_node_id,
    targetHandle: edge.target_port === "input" ? definition(edge.target_node_id)?.inputs[0]?.id ?? edge.target_port : edge.target_port,
    animated: true,
  }));
}

function graphForSave(workflow: StudioWorkflow, nodes: Node<WorkflowNodeData>[], edges: Edge[]): StudioWorkflowGraph {
  const originalNodes = new Map(workflow.graph.nodes.map((node) => [node.id, node]));
  return {
    nodes: nodes.map((node) => ({ ...(originalNodes.get(node.id) ?? { id: node.id, type: node.data.nodeType ?? "incept.asset.reference.v1", label: node.data.title, params: {}, status: "draft" as const }), position: { x: node.position.x, y: node.position.y }, label: node.data.title, params: node.data.params ?? {} })),
    edges: edges.map((edge) => ({ id: edge.id, source_node_id: edge.source, source_port: edge.sourceHandle ?? "output", target_node_id: edge.target, target_port: edge.targetHandle ?? "input" })),
    viewport: workflow.graph.viewport,
  };
}

function readDirection(value: unknown): { referenceSummary: string; commercialType: string; outputLanguage: string; strengths: string[]; story: string[]; characters: string[]; assets: string[]; risks: string[] } | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const list = (item: unknown) => Array.isArray(item) ? item.filter((entry): entry is string => typeof entry === "string" && Boolean(entry.trim())) : [];
  return {
    referenceSummary: typeof record.reference_summary === "string" ? record.reference_summary : "",
    commercialType: typeof record.commercial_type === "string" ? record.commercial_type : "",
    outputLanguage: typeof record.output_language === "string" ? record.output_language : "",
    strengths: list(record.strengths_to_adapt), story: list(record.story_structure), characters: list(record.scene_and_character_notes), assets: list(record.asset_request), risks: list(record.risks),
  };
}

export function ComfyUIView({ activeWorkspaceId, liveAssets, liveJobs, onMobileMenuOpen, onOpenVideoProduction }: { activeWorkspaceId: string; liveAssets: AssetSummary[]; liveJobs: JobSummary[]; onMobileMenuOpen?: () => void; onOpenVideoProduction?: () => void }) {
  const { data: session } = useSession();
  const [template, setTemplate] = useState<WorkflowTemplate>("commercial");
  const [nodes, setNodes, onNodesChange] = useNodesState< Node<WorkflowNodeData> >(TEMPLATE_NODES.commercial);
  const [edges, setEdges, onEdgesChange] = useEdgesState(templateEdges("commercial"));
  const [workflows, setWorkflows] = useState<StudioWorkflow[]>([]);
  const [activeWorkflow, setActiveWorkflow] = useState<StudioWorkflow | null>(null);
  const [openWorkflowIds, setOpenWorkflowIds] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>("reference");
  const [runNotice, setRunNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [runNodes, setRunNodes] = useState<StudioWorkflowRunNode[]>([]);
  const [runAssets, setRunAssets] = useState<AssetSummary[]>([]);
  const [previewAsset, setPreviewAsset] = useState<AssetSummary | null>(null);
  const [reviewAsset, setReviewAsset] = useState<AssetSummary | null>(null);
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [costConfirmOpen, setCostConfirmOpen] = useState(false);
  const [runPriority, setRunPriority] = useState(0);
  const [nodeDefinitions, setNodeDefinitions] = useState<StudioWorkflowNodeDefinition[]>([]);
  const [nodeSearch, setNodeSearch] = useState("");
  const [workflowOutputs, setWorkflowOutputs] = useState<StudioWorkflowOutput[]>([]);
  const [workflowRevisions, setWorkflowRevisions] = useState<StudioWorkflowRevision[]>([]);
  const [workflowLineage, setWorkflowLineage] = useState<StudioWorkflowLineage | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const historyRef = useRef<GraphSnapshot[]>([]);
  const redoRef = useRef<GraphSnapshot[]>([]);
  const importInputRef = useRef<HTMLInputElement>(null);
  const selected = useMemo(() => nodes.find((node) => node.id === selectedNode) ?? null, [nodes, selectedNode]);
  const selectedNodes = useMemo(() => nodes.filter((node) => node.selected || node.id === selectedNode).filter((node) => node.data.nodeType !== "incept.group.v1"), [nodes, selectedNode]);
  const visibleNodeDefinitions = useMemo(() => nodeDefinitions.filter((definition) => {
    const query = nodeSearch.trim().toLowerCase();
    return !query || `${definition.display_name} ${definition.category} ${definition.description}`.toLowerCase().includes(query);
  }), [nodeDefinitions, nodeSearch]);
  const openWorkflows = useMemo(() => openWorkflowIds.map((id) => workflows.find((workflow) => workflow.workflow_id === id)).filter((workflow): workflow is StudioWorkflow => Boolean(workflow)), [openWorkflowIds, workflows]);
  const directionResults = useMemo(() => runNodes.flatMap((node) => {
    const direction = readDirection(node.result.creative_direction);
    return direction ? [{ nodeId: node.node_id, direction }] : [];
  }), [runNodes]);
  const runningCount = liveJobs.filter((job) => ["queued", "pending", "running"].includes(job.status)).length;

  const openWorkflow = (workflow: StudioWorkflow) => {
    setActiveWorkflow(workflow); setOpenWorkflowIds((ids) => ids.includes(workflow.workflow_id) ? ids : [...ids, workflow.workflow_id]); setTemplate(workflow.template); setNodes(flowNodes(workflow, nodeDefinitions)); setEdges(flowEdges(workflow, nodeDefinitions)); setSelectedNode(workflow.graph.nodes[0]?.id ?? null); setRunNotice(null); setDirty(false); historyRef.current = []; redoRef.current = [];
  };
  useEffect(() => {
    let live = true;
    listStudioWorkflows(activeWorkspaceId).then((items) => { if (!live) return; setWorkflows(items); if (items[0]) openWorkflow(items[0]); }).catch((error: unknown) => { if (live) setRunNotice(error instanceof Error ? error.message : "Could not load workflows."); });
    return () => { live = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspaceId]);
  useEffect(() => {
    let live = true;
    listStudioWorkflowNodeDefinitions().then((items) => { if (live) setNodeDefinitions(items); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  useEffect(() => {
    if (!nodeDefinitions.length) return;
    setNodes((items) => items.map((node) => {
      const definition = nodeDefinitions.find((item) => item.type === node.data.nodeType);
      return definition ? { ...node, data: { ...node.data, inputs: definition.inputs, outputs: definition.outputs } } : node;
    }));
  }, [nodeDefinitions, setNodes]);
  useEffect(() => {
    if (!activeWorkflow) { setWorkflowOutputs([]); return; }
    let live = true;
    listStudioWorkflowOutputs(activeWorkflow.workflow_id, activeWorkflow.workspace_id).then((items) => { if (live) setWorkflowOutputs(items); }).catch(() => { if (live) setWorkflowOutputs([]); });
    return () => { live = false; };
  // The scalar identity fields are intentional; depending on the full object
  // would refetch when unrelated local workflow state changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkflow?.workflow_id, activeWorkflow?.revision, activeWorkflow?.workspace_id]);
  useEffect(() => {
    if (!activeWorkflow) { setWorkflowLineage(null); return; }
    let live = true;
    getStudioWorkflowLineage(activeWorkflow.workflow_id, activeWorkflow.workspace_id).then((lineage) => { if (live) setWorkflowLineage(lineage); }).catch(() => { if (live) setWorkflowLineage(null); });
    return () => { live = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkflow?.workflow_id, activeWorkflow?.revision, activeWorkflow?.workspace_id]);
  useEffect(() => {
    if (!activeWorkflow) { setWorkflowRevisions([]); return; }
    let live = true;
    listStudioWorkflowRevisions(activeWorkflow.workflow_id, activeWorkflow.workspace_id).then((items) => { if (live) setWorkflowRevisions(items); }).catch(() => { if (live) setWorkflowRevisions([]); });
    return () => { live = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkflow?.workflow_id, activeWorkflow?.revision, activeWorkflow?.workspace_id]);
  useEffect(() => {
    if (!activeRunId) return;
    let stopped = false;
    let retryTimer: number | null = null;
    const load = async () => {
      try {
        const next = await getStudioWorkflowRunNodes(activeRunId, activeWorkspaceId);
        if (stopped) return;
        setRunNodes(next);
        const runStateByNode = new Map(next.map((node) => [node.node_id, node.status]));
        setNodes((items) => items.map((node) => runStateByNode.has(node.id) ? { ...node, data: { ...node.data, status: runStateByNode.get(node.id) } } : node));
        const assetIds = new Set(next.flatMap((node) => Array.isArray(node.result.asset_ids) ? node.result.asset_ids.filter((assetId): assetId is string => typeof assetId === "string") : []));
        if (assetIds.size > 0) {
          const assets = await listAssets(activeWorkspaceId).catch(() => [] as AssetSummary[]);
          if (!stopped) setRunAssets(assets.filter((asset) => assetIds.has(asset.id)));
        }
        const terminal = next.length > 0 && next.every((node) => ["succeeded", "approved", "failed", "blocked", "cancelled"].includes(node.status));
        if (terminal && activeWorkflow) {
          const outputs = await listStudioWorkflowOutputs(activeWorkflow.workflow_id, activeWorkflow.workspace_id).catch(() => [] as StudioWorkflowOutput[]);
          const lineage = await getStudioWorkflowLineage(activeWorkflow.workflow_id, activeWorkflow.workspace_id).catch(() => null);
          if (!stopped) { setWorkflowOutputs(outputs); setWorkflowLineage(lineage); }
        }
        if (!terminal) retryTimer = window.setTimeout(load, 1400);
      } catch (error) { if (!stopped) setRunNotice(error instanceof Error ? error.message : "Could not load workflow progress."); }
    };
    void load();
    const events = new EventSource(`/api/incept/studio-workflow-runs/${encodeURIComponent(activeRunId)}/events/stream?workspace_id=${encodeURIComponent(activeWorkspaceId)}`);
    const refresh = () => { if (!stopped) void load(); };
    ["run.running", "run.succeeded", "run.failed", "run.cancelled", "node.running", "node.succeeded", "node.failed", "node.blocked", "node.approved"].forEach((eventName) => events.addEventListener(eventName, refresh));
    return () => { stopped = true; events.close(); if (retryTimer !== null) window.clearTimeout(retryTimer); };
  }, [activeRunId, activeWorkspaceId, activeWorkflow, setNodes]);
  const chooseTemplate = async (next: WorkflowTemplate) => {
    setSaving(true);
    try { const workflow = await createStudioWorkflow(activeWorkspaceId, next); setWorkflows((items) => [workflow, ...items]); openWorkflow(workflow); }
    catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not create workflow."); }
    finally { setSaving(false); }
  };
  const exportWorkflow = () => {
    if (!activeWorkflow) return;
    const payload = { format: "incept-workflow.v1", exported_at: new Date().toISOString(), workflow: { title: activeWorkflow.title, template, graph: graphForSave(activeWorkflow, nodes, edges) } };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = `${activeWorkflow.title.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "workflow"}.incept-workflow.json`; link.click(); URL.revokeObjectURL(url);
  };
  const importWorkflow = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text()) as { format?: string; workflow?: { title?: string; template?: WorkflowTemplate; graph?: StudioWorkflowGraph } };
      if (parsed.format !== "incept-workflow.v1" || !parsed.workflow?.template || !parsed.workflow.graph) throw new Error("Choose a LinglongLab workflow export (.incept-workflow.json).");
      setSaving(true);
      const created = await createStudioWorkflow(activeWorkspaceId, parsed.workflow.template, `${parsed.workflow.title?.trim() || "Imported workflow"} (imported)`);
      const imported = await updateStudioWorkflow(created, parsed.workflow.graph, created.title);
      setWorkflows((items) => [imported, ...items]); openWorkflow(imported); setRunNotice("Imported as a new workflow. Validate connections before running.");
    } catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not import workflow."); }
    finally { setSaving(false); if (importInputRef.current) importInputRef.current.value = ""; }
  };
  const checkpoint = useCallback(() => {
    historyRef.current = [...historyRef.current.slice(-39), { nodes, edges, selectedNode }];
    redoRef.current = [];
  }, [edges, nodes, selectedNode]);
  const undoGraph = () => {
    const previous = historyRef.current.pop();
    if (!previous) { setRunNotice("Nothing to undo."); return; }
    redoRef.current.push({ nodes, edges, selectedNode });
    setNodes(previous.nodes); setEdges(previous.edges); setSelectedNode(previous.selectedNode); setDirty(true);
  };
  const redoGraph = () => {
    const next = redoRef.current.pop();
    if (!next) { setRunNotice("Nothing to redo."); return; }
    historyRef.current.push({ nodes, edges, selectedNode });
    setNodes(next.nodes); setEdges(next.edges); setSelectedNode(next.selectedNode); setDirty(true);
  };
  const addNodeFromLibrary = (definition: StudioWorkflowNodeDefinition) => {
    checkpoint();
    const id = `node_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
    const position = { x: 180 + (nodes.length % 4) * 280, y: 100 + Math.floor(nodes.length / 4) * 210 };
    setNodes((items) => [...items, { id, type: "workflow", position, selected: true, data: { title: definition.display_name, subtitle: definition.description, nodeType: definition.type, kind: nodeKind(definition.type), status: "draft", params: {}, inputs: definition.inputs, outputs: definition.outputs } }]);
    setSelectedNode(id); setDirty(true); setRunNotice(`Added ${definition.display_name}. Connect compatible ports before running.`);
  };
  const deleteSelectedNode = () => {
    if (!selectedNode) return;
    checkpoint();
    setNodes((items) => items.filter((node) => node.id !== selectedNode));
    setEdges((items) => items.filter((edge) => edge.source !== selectedNode && edge.target !== selectedNode));
    setSelectedNode(null); setDirty(true);
  };
  const duplicateSelectedNode = () => {
    const node = nodes.find((item) => item.id === selectedNode);
    if (!node) return;
    checkpoint();
    const id = `node_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
    setNodes((items) => [...items, { ...node, id, selected: true, position: { x: node.position.x + 48, y: node.position.y + 48 }, data: { ...node.data, title: `${node.data.title} copy`, status: "draft" } }]);
    setSelectedNode(id); setDirty(true);
  };
  const createGroup = () => {
    const memberIds = nodes.filter((node) => node.selected || node.id === selectedNode).filter((node) => node.data.nodeType !== "incept.group.v1").map((node) => node.id);
    if (!memberIds.length) { setRunNotice("Select one or more nodes to create a group."); return; }
    checkpoint();
    const members = nodes.filter((node) => memberIds.includes(node.id));
    const left = Math.min(...members.map((node) => node.position.x)) - 22;
    const top = Math.min(...members.map((node) => node.position.y)) - 52;
    const id = `group_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
    const definition = nodeDefinitions.find((item) => item.type === "incept.group.v1");
    setNodes((items) => [{ id, type: "workflow", position: { x: left, y: top }, data: { title: `Group · ${members[0].data.title}${members.length > 1 ? ` + ${members.length - 1}` : ""}`, subtitle: "Canvas group", nodeType: "incept.group.v1", kind: "input", status: "draft", params: { group_member_ids: memberIds }, inputs: definition?.inputs ?? [], outputs: definition?.outputs ?? [] }, zIndex: -1 }, ...items]);
    setSelectedNode(id); setDirty(true); setRunNotice(`Created a visual group for ${memberIds.length} node${memberIds.length === 1 ? "" : "s"}.`);
  };
  const ungroupSelected = () => {
    const group = nodes.find((node) => node.id === selectedNode && node.data.nodeType === "incept.group.v1");
    if (!group) { setRunNotice("Select a canvas group to remove it."); return; }
    checkpoint(); setNodes((items) => items.filter((node) => node.id !== group.id)); setSelectedNode(null); setDirty(true);
  };
  const autoLayout = () => {
    checkpoint();
    const rank = new Map(nodes.map((node) => [node.id, 0]));
    const queue = nodes.filter((node) => !edges.some((edge) => edge.target === node.id));
    for (let cursor = 0; cursor < queue.length; cursor += 1) {
      const source = queue[cursor];
      for (const edge of edges.filter((item) => item.source === source.id)) {
        rank.set(edge.target, Math.max(rank.get(edge.target) ?? 0, (rank.get(source.id) ?? 0) + 1));
        if (!queue.some((node) => node.id === edge.target)) queue.push(nodes.find((node) => node.id === edge.target)!);
      }
    }
    const rows = new Map<number, number>();
    setNodes((items) => items.map((node) => {
      const column = rank.get(node.id) ?? 0;
      const row = rows.get(column) ?? 0;
      rows.set(column, row + 1);
      return { ...node, position: { x: 48 + column * 300, y: 90 + row * 210 } };
    }));
    setDirty(true); setRunNotice("Applied left-to-right layout. Your graph connections were not changed.");
  };
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const element = event.target as HTMLElement | null;
      if (element?.matches("input, textarea, select")) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redoGraph(); else undoGraph(); }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") { event.preventDefault(); duplicateSelectedNode(); }
      if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); deleteSelectedNode(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  // The command functions intentionally close over the same graph snapshot
  // listed here; the listener is replaced whenever that snapshot changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode, nodes, edges]);
  const handleNodesChange = useCallback((changes: NodeChange<Node<WorkflowNodeData>>[]) => {
    onNodesChange(changes);
    if (changes.some((change) => change.type !== "select" && change.type !== "dimensions")) setDirty(true);
  }, [onNodesChange]);
  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    if (changes.some((change) => change.type === "remove")) checkpoint();
    onEdgesChange(changes);
    if (changes.some((change) => change.type !== "select")) setDirty(true);
  }, [checkpoint, onEdgesChange]);
  const onConnect = useCallback((connection: Connection) => {
    const source = nodes.find((node) => node.id === connection.source);
    const target = nodes.find((node) => node.id === connection.target);
    const sourceDefinition = nodeDefinitions.find((definition) => definition.type === source?.data.nodeType);
    const targetDefinition = nodeDefinitions.find((definition) => definition.type === target?.data.nodeType);
    const output = sourceDefinition?.outputs.find((port) => port.id === connection.sourceHandle) ?? sourceDefinition?.outputs[0];
    const input = targetDefinition?.inputs.find((port) => port.id === connection.targetHandle) ?? targetDefinition?.inputs[0];
    if (!source || !target || !output || !input) { setRunNotice("This connection needs a supported output and input port."); return; }
    if (output.value_type !== input.value_type) { setRunNotice(`${target.data.title} expects ${input.value_type}; ${source.data.title} provides ${output.value_type}.`); return; }
    if (!input.multiple && edges.some((edge) => edge.target === target.id && (edge.targetHandle ?? input.id) === input.id)) { setRunNotice(`${target.data.title} accepts only one connection on ${input.id}.`); return; }
    checkpoint(); setEdges((items) => addEdge({ ...connection, sourceHandle: output.id, targetHandle: input.id, animated: true }, items)); setDirty(true);
  }, [checkpoint, edges, nodeDefinitions, nodes, setEdges]);
  const saveWorkflow = async () => {
    if (!activeWorkflow) return null;
    setSaving(true);
    try {
      const saved = await updateStudioWorkflow(activeWorkflow, graphForSave(activeWorkflow, nodes, edges));
      setActiveWorkflow(saved); setWorkflows((items) => [saved, ...items.filter((item) => item.workflow_id !== saved.workflow_id)]); setDirty(false); return saved;
    } catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not save workflow."); return null; }
    finally { setSaving(false); }
  };
  useEffect(() => {
    if (!activeWorkflow || !dirty || saving) return;
    const timer = window.setTimeout(() => { void saveWorkflow(); }, 900);
    return () => window.clearTimeout(timer);
  // `saveWorkflow` changes identity per render but intentionally reads the latest graph.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkflow?.workflow_id, activeWorkflow?.revision, dirty, nodes, edges, saving]);
  const renameWorkflow = async () => {
    if (!activeWorkflow || !titleDraft.trim()) return;
    setSaving(true);
    try {
      const saved = await updateStudioWorkflow(activeWorkflow, graphForSave(activeWorkflow, nodes, edges), titleDraft.trim());
      setActiveWorkflow(saved); setWorkflows((items) => [saved, ...items.filter((item) => item.workflow_id !== saved.workflow_id)]); setRenameOpen(false);
    } catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not rename workflow."); }
    finally { setSaving(false); }
  };
  const removeWorkflow = async () => {
    if (!activeWorkflow) return;
    setSaving(true);
    try {
      const removedId = activeWorkflow.workflow_id;
      await deleteStudioWorkflow(removedId, activeWorkspaceId);
      const remaining = workflows.filter((item) => item.workflow_id !== removedId);
      setWorkflows(remaining); setDeleteOpen(false);
      if (remaining[0]) openWorkflow(remaining[0]);
      else { setActiveWorkflow(null); setNodes(TEMPLATE_NODES.commercial); setEdges(templateEdges("commercial")); setSelectedNode("reference"); }
    } catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not delete workflow."); }
    finally { setSaving(false); }
  };
  const closeWorkflowTab = (workflowId: string) => {
    const remaining = openWorkflowIds.filter((id) => id !== workflowId);
    setOpenWorkflowIds(remaining);
    if (activeWorkflow?.workflow_id !== workflowId) return;
    const next = workflows.find((workflow) => workflow.workflow_id === remaining[remaining.length - 1]);
    if (next) openWorkflow(next);
    else { setActiveWorkflow(null); setSelectedNode(null); setRunNotice(null); }
  };
  const requestRun = async (costConfirmed = false) => {
    const pendingApproval = nodes.find((node) => node.id === (template === "video" ? "take" : "selection"));
    const startsGeneration = (template === "image" || template === "video") && !pendingApproval?.data.params?.asset_id;
    if (startsGeneration && !costConfirmed) { setCostConfirmOpen(true); return; }
    const saved = await saveWorkflow(); if (!saved) return;
    try {
      const validation = await validateStudioWorkflow(saved.workflow_id, saved.workspace_id);
      if (!validation.valid) { setRunNotice(validation.issues[0]?.message ?? "Fix validation issues before running."); return; }
      const approvalNode = saved.graph.nodes.find((node) => node.id === (saved.template === "video" ? "take" : saved.template === "image" ? "selection" : "script"));
      const outputNodeId = saved.template === "image" ? (approvalNode?.params.asset_id ? "selection" : "image")
        : saved.template === "video" ? (approvalNode?.params.asset_id ? "take" : "shot")
          : saved.template === "script" ? (approvalNode?.params.production_id ? "script" : "screenwriter")
            : "delivery";
      const run = await runStudioWorkflow(saved.workflow_id, saved.workspace_id, [outputNodeId], runPriority);
      setActiveRunId(run.run_id); setRunNodes([]); setRunAssets([]); setRunNotice(`Run ${run.run_id} is queued.`);
    } catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not queue workflow."); }
  };
  const requestNodeRun = async (node: Node<WorkflowNodeData>) => {
    if (node.data.kind === "generate") { setRunNotice("Generation nodes can be costly. Use Validate & run to review the confirmation first."); return; }
    const saved = await saveWorkflow(); if (!saved) return;
    try {
      const validation = await validateStudioWorkflow(saved.workflow_id, saved.workspace_id);
      if (!validation.valid) { setRunNotice(validation.issues[0]?.message ?? "Fix validation issues before rerunning this node."); return; }
      const run = await runStudioWorkflow(saved.workflow_id, saved.workspace_id, [node.id], runPriority);
      setActiveRunId(run.run_id); setRunNodes([]); setRunAssets([]); setRunNotice(`Local rerun queued for ${node.data.title} and its upstream dependencies.`);
    } catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not queue this local rerun."); }
  };
  const cancelActiveRun = async () => {
    if (!activeRunId) return;
    try {
      await cancelStudioWorkflowRun(activeRunId, activeWorkspaceId);
      setRunNotice("Cancellation requested. The worker will stop before the next node.");
      const next = await getStudioWorkflowRunNodes(activeRunId, activeWorkspaceId);
      setRunNodes(next);
    } catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not cancel this workflow run."); }
  };
  const retryActiveRun = async () => {
    if (!activeRunId) return;
    try {
      const next = await retryStudioWorkflowRun(activeRunId, activeWorkspaceId);
      setActiveRunId(next.run_id); setRunNodes([]); setRunAssets([]); setRunNotice(`Retry ${next.run_id} is queued.`);
    } catch (error) { setRunNotice(error instanceof Error ? error.message : "Could not retry this workflow run."); }
  };
  const updateSelectedParams = (params: Record<string, unknown>) => {
    if (!selectedNode) return;
    checkpoint();
    const children = new Map<string, string[]>();
    edges.forEach((edge) => children.set(edge.source, [...(children.get(edge.source) ?? []), edge.target]));
    const staleNodeIds = new Set<string>();
    const pending = [...(children.get(selectedNode) ?? [])];
    while (pending.length > 0) {
      const nodeId = pending.pop()!;
      if (staleNodeIds.has(nodeId)) continue;
      staleNodeIds.add(nodeId);
      pending.push(...(children.get(nodeId) ?? []));
    }
    setNodes((items) => items.map((node) => {
      if (node.id === selectedNode) return { ...node, data: { ...node.data, params: { ...(node.data.params ?? {}), ...params }, status: "valid" } };
      if (!staleNodeIds.has(node.id)) return node;
      const nextParams = { ...(node.data.params ?? {}) };
      if (node.id === "selection" || node.id === "take") delete nextParams.asset_id;
      if (node.id === "script") { delete nextParams.production_id; delete nextParams.script_revision; }
      return { ...node, data: { ...node.data, params: nextParams, status: "stale" } };
    }));
    setDirty(true);
    if (staleNodeIds.size > 0) setRunNotice("Downstream results are stale after this change. Run again to regenerate the affected output.");
  };
  const selectGeneratedCandidate = (assetId: string) => {
    const asset = runAssets.find((item) => item.id === assetId);
    if (!asset) return;
    setReviewAsset(asset);
  };
  const approveGeneratedCandidate = (assetId: string) => {
    const approvalId = template === "video" ? "take" : "selection";
    setNodes((items) => items.map((node) => node.id === approvalId ? { ...node, data: { ...node.data, params: { ...(node.data.params ?? {}), asset_id: assetId }, status: "valid" } } : node));
    setSelectedNode(approvalId); setDirty(true);
    setRunNotice("Candidate selected. Save and run to approve it for downstream use.");
    setReviewAsset(null);
  };
  const approveGeneratedScript = (node: StudioWorkflowRunNode) => {
    const productionId = typeof node.result.production_id === "string" ? node.result.production_id : "";
    if (!productionId) return;
    setNodes((items) => items.map((item) => item.id === "script" ? {
      ...item,
      data: {
        ...item.data,
        params: {
          ...(item.data.params ?? {}),
          production_id: productionId,
          script_revision: node.result.script_revision,
        },
        status: "valid",
      },
    } : item));
    setSelectedNode("script"); setDirty(true);
    setRunNotice("Script approved. Save and run to record the approval.");
  };
  const selectedAssetIds = (selected?.data.params?.asset_ids ?? []) as string[];
  const selectedBrandAssetIds = (selected?.data.params?.brand_asset_ids ?? []) as string[];
  const selectedCandidateId = String(nodes.find((node) => node.id === (template === "video" ? "take" : "selection"))?.data.params?.asset_id ?? "");
  const toggleReferenceAsset = (assetId: string) => {
    updateSelectedParams({ asset_ids: selectedAssetIds.includes(assetId) ? selectedAssetIds.filter((id) => id !== assetId) : [...selectedAssetIds, assetId] });
  };
  const toggleBrandAsset = (assetId: string) => {
    updateSelectedParams({ brand_asset_ids: selectedBrandAssetIds.includes(assetId) ? selectedBrandAssetIds.filter((id) => id !== assetId) : [...selectedBrandAssetIds, assetId] });
  };
  const openProduction = (productionId: string) => {
    window.sessionStorage.setItem("incept.openProductionId", productionId);
    if (onOpenVideoProduction) {
      onOpenVideoProduction();
      return;
    }
    window.location.assign("/linglonglab");
  };

  const workflowRail = (
    <div className="p-3">
      <div className="mb-4 rounded-xl border bg-background px-3 py-3 shadow-sm"><div className="flex items-center gap-2"><div className="flex size-7 items-center justify-center rounded-lg bg-orange-100 text-orange-700"><Workflow className="size-4" /></div><div className="min-w-0 flex-1"><p className="text-sm font-semibold">Start a workflow</p><p className="text-[11px] text-muted-foreground">Choose a guided template below</p></div></div></div>
      <div className="space-y-1">{(Object.keys(TEMPLATE_META) as WorkflowTemplate[]).map((key) => { const item = TEMPLATE_META[key]; const Icon = item.icon; return <button type="button" key={key} disabled={saving} onClick={() => void chooseTemplate(key)} className={cn("flex w-full items-start gap-3 rounded-xl p-3 text-left transition-colors disabled:opacity-50", template === key ? "bg-foreground text-background" : "hover:bg-muted")}> <Icon className="mt-0.5 size-4 shrink-0" /><span><span className="block text-sm font-medium">{item.label}</span><span className={cn("mt-1 block text-xs leading-4", template === key ? "text-background/70" : "text-muted-foreground")}>{item.detail}</span></span></button>; })}</div>
      <div className="mt-5 border-t pt-5"><p className="px-2 text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Node library</p><input value={nodeSearch} onChange={(event) => setNodeSearch(event.target.value)} placeholder="Search nodes…" className="mt-2 w-full rounded-lg border bg-background px-2.5 py-2 text-xs outline-none focus:ring-2 focus:ring-foreground/20" /><div className="mt-2 max-h-48 space-y-1 overflow-auto">{visibleNodeDefinitions.map((definition) => <div key={definition.type} className="rounded-lg px-2 py-2 hover:bg-muted"><div className="flex items-center justify-between gap-2"><p className="truncate text-xs font-medium">{definition.display_name}</p><Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-[10px]" onClick={() => addNodeFromLibrary(definition)}>Add</Button></div><p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-muted-foreground">{definition.description}</p><div className="mt-1 flex gap-1"><span className="text-[9px] uppercase tracking-wide text-muted-foreground">{definition.category}</span>{definition.costed && <span className="text-[9px] uppercase tracking-wide text-amber-700">cost</span>}{definition.requires_approval && <span className="text-[9px] uppercase tracking-wide text-emerald-700">approval</span>}</div></div>)}{nodeDefinitions.length > 0 && visibleNodeDefinitions.length === 0 && <p className="px-2 py-3 text-xs text-muted-foreground">No matching nodes.</p>}</div></div>
      {workflowOutputs.length > 0 && <div className="mt-5 border-t pt-5"><p className="px-2 text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Approved outputs</p><div className="mt-2 space-y-1">{workflowOutputs.slice(0, 4).map((output) => <div key={output.output_id} className="rounded-lg px-2 py-2 text-xs hover:bg-muted"><div className="flex items-center justify-between gap-2"><span className="truncate font-medium">{output.output_type}</span><span className="text-[10px] text-emerald-700">approved</span></div><p className="mt-1 truncate text-[11px] text-muted-foreground">{output.value_id}</p>{["script", "commercial"].includes(output.output_type) && <button type="button" className="mt-1 text-[11px] font-medium underline underline-offset-2" onClick={() => openProduction(output.value_id)}>Open production</button>}</div>)}</div></div>}
      {workflows.length > 0 && <div className="mt-7 border-t pt-5"><p className="px-2 text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Recent workflows</p><div className="mt-2 space-y-1">{workflows.slice(0, 5).map((workflow) => <button type="button" key={workflow.workflow_id} onClick={() => openWorkflow(workflow)} className={cn("w-full truncate rounded-lg px-2 py-2 text-left text-xs hover:bg-muted", activeWorkflow?.workflow_id === workflow.workflow_id && "bg-muted font-medium")}>{workflow.title}</button>)}</div></div>}
      {workflowRevisions.length > 0 && <details className="mt-5 border-t pt-5"><summary className="cursor-pointer px-2 text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Revision history · {workflowRevisions.length}</summary><div className="mt-2 space-y-1">{workflowRevisions.slice(0, 8).map((entry) => <button type="button" key={entry.revision} onClick={() => { setNodes(flowNodes(entry.workflow, nodeDefinitions)); setEdges(flowEdges(entry.workflow, nodeDefinitions)); setSelectedNode(entry.workflow.graph.nodes[0]?.id ?? null); setDirty(true); setRunNotice(`Revision ${entry.revision} loaded as a draft. Save to create a new revision.`); }} className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-xs hover:bg-muted"><span>Revision {entry.revision}</span><span className="text-[10px] text-muted-foreground">Restore</span></button>)}</div></details>}
      {workflowLineage && <details className="mt-5 border-t pt-5"><summary className="cursor-pointer px-2 text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Lineage · {workflowLineage.runs.length} runs</summary><div className="mt-2 space-y-2 px-2 text-xs"><p className="text-muted-foreground">Revision {workflowLineage.graph_revision} · {workflowLineage.outputs.length} approved outputs</p>{workflowLineage.runs.slice(0, 5).map((run) => <div key={run.run_id} className="rounded-lg border p-2"><div className="flex items-center justify-between gap-2"><span className="truncate font-medium">{run.run_id}</span><span className="text-[10px] text-muted-foreground">P{run.priority}</span></div><p className="mt-1 text-[11px] text-muted-foreground">{(workflowLineage.run_nodes ?? []).filter((node) => node.run_id === run.run_id).map((node) => `${node.node_id}: ${node.status}`).join(" · ") || "Queued"}</p></div>)}</div></details>}
      <div className="mt-7 border-t pt-5"><p className="px-2 text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Workspace</p><div className="mt-3 space-y-2 px-2 text-xs text-muted-foreground"><p>{liveAssets.length} available assets</p><p>{runningCount} active runs</p><p className="truncate">{activeWorkspaceId}</p></div></div>
    </div>
  );

  return (
    <div className="flex h-screen min-h-0 bg-background text-foreground">
      <AppSidebar productName="Comfy Workflow" brandTitle="Linglong" brandSubtitle="Lab" logo="/logo.png" storageKey="comfy-workflow" items={[]} isActive={() => false} user={{ email: session?.user?.email, name: session?.user?.name, image: session?.user?.image }} onSignOut={() => signOut({ callbackUrl: "/sign-in" })} content={workflowRail} expandedWidthClassName="w-72" />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <AppHeader title="Comfy Workflow" subtitle="Node-based AI production canvas" docsHref="/docs/linglonglab-comfyui-workflow-engine-implementation-plan" onMobileMenuOpen={onMobileMenuOpen} />
      {openWorkflows.length > 0 && <div className="flex shrink-0 gap-1 overflow-x-auto border-b bg-card px-3 py-1.5" aria-label="Open workflows">{openWorkflows.map((workflow) => <div key={workflow.workflow_id} className={cn("group flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs", activeWorkflow?.workflow_id === workflow.workflow_id ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground")}><button type="button" className="max-w-44 truncate text-left" onClick={() => openWorkflow(workflow)}>{workflow.title}</button><button type="button" aria-label={`Close ${workflow.title}`} className="rounded p-0.5 opacity-60 hover:bg-background/15 hover:opacity-100" onClick={() => closeWorkflowTab(workflow.workflow_id)}><X className="size-3" /></button></div>)}</div>}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <section className="relative min-w-0 flex-1">
          <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between border-b bg-background/90 px-4 py-3 backdrop-blur"><div><p className="text-sm font-semibold">{activeWorkflow?.title ?? TEMPLATE_META[template].label}</p><p className="text-xs text-muted-foreground">{activeWorkflow ? `Revision ${activeWorkflow.revision} · ${saving ? "Saving…" : "Saved"}` : "Choose a template to create a workflow"}</p></div><div className="flex items-center gap-2"><Button variant="ghost" size="icon" title="Rename workflow" disabled={!activeWorkflow || saving} onClick={() => { setTitleDraft(activeWorkflow?.title ?? ""); setRenameOpen(true); }}><Pencil className="size-4" /></Button><Button variant="ghost" size="icon" title="Delete workflow" disabled={!activeWorkflow || saving} onClick={() => setDeleteOpen(true)}><Trash2 className="size-4 text-destructive" /></Button><Button variant="outline" size="sm" disabled={!activeWorkflow || saving} onClick={() => void saveWorkflow()}><Plus className="mr-1.5 size-3.5" />Save</Button><Button size="sm" disabled={!activeWorkflow || saving} onClick={() => void requestRun()}><Play className="mr-1.5 size-3.5" />Validate & run</Button></div></div>
          <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={handleNodesChange} onEdgesChange={handleEdgesChange} onNodeDragStart={() => checkpoint()} onConnect={onConnect} onNodeClick={(_, node) => setSelectedNode(node.id)} onNodeDoubleClick={(_, node) => void requestNodeRun(node)} fitView className="pt-14" proOptions={{ hideAttribution: true }}>
            <Background gap={18} size={1} /><Controls /><MiniMap zoomable pannable className="!bottom-5 !left-5" />
          </ReactFlow>
          <div className="absolute right-[13.5rem] top-3 z-20"><Button type="button" variant="ghost" size="icon" title="Workflow tools" onClick={() => setAdvancedOpen((open) => !open)}><MoreHorizontal className="size-4" /></Button>{advancedOpen && <div className="absolute right-0 top-10 w-64 rounded-xl border bg-background p-2 shadow-xl"><p className="px-2 pb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">Canvas tools</p><div className="grid grid-cols-2 gap-1"><Button variant="ghost" size="sm" className="justify-start text-xs" onClick={undoGraph}><Undo2 className="mr-1.5 size-3.5" />Undo</Button><Button variant="ghost" size="sm" className="justify-start text-xs" onClick={redoGraph}><Redo2 className="mr-1.5 size-3.5" />Redo</Button><Button variant="ghost" size="sm" className="justify-start text-xs" disabled={!selectedNode} onClick={duplicateSelectedNode}><Copy className="mr-1.5 size-3.5" />Duplicate</Button><Button variant="ghost" size="sm" className="justify-start text-xs text-destructive" disabled={!selectedNode} onClick={deleteSelectedNode}><Trash2 className="mr-1.5 size-3.5" />Delete</Button></div><Button variant="ghost" size="sm" className="mt-1 w-full justify-start text-xs" onClick={autoLayout}>Auto-layout canvas</Button><div className="my-2 border-t" /><div className="flex gap-1"><Button variant="ghost" size="sm" className="flex-1 text-xs" disabled={!activeWorkflow} onClick={exportWorkflow}>Export</Button><Button variant="ghost" size="sm" className="flex-1 text-xs" onClick={() => importInputRef.current?.click()}>Import</Button></div><input ref={importInputRef} type="file" accept="application/json,.json,.incept-workflow.json" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importWorkflow(file); }} /><label className="mt-2 block px-2 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">Run priority<select value={runPriority} onChange={(event) => setRunPriority(Number(event.target.value))} className="mt-1 w-full rounded-lg border bg-background px-2 py-1.5 text-xs normal-case tracking-normal text-foreground"><option value={0}>Normal</option><option value={5}>High</option><option value={10}>Urgent</option></select></label></div>}</div>
          {(selectedNodes.length > 1 || selected?.data.nodeType === "incept.group.v1") && <div className="absolute left-1/2 top-20 z-20 flex -translate-x-1/2 items-center gap-1 rounded-xl border bg-background/95 p-1.5 shadow-lg backdrop-blur"><span className="px-2 text-xs text-muted-foreground">{selected?.data.nodeType === "incept.group.v1" ? "Canvas group" : `${selectedNodes.length} selected`}</span>{selectedNodes.length > 1 && <Button size="sm" variant="outline" onClick={createGroup}>Group</Button>}{selected?.data.nodeType === "incept.group.v1" && <Button size="sm" variant="outline" onClick={ungroupSelected}>Ungroup</Button>}</div>}
          {(runNotice || runNodes.length > 0) && <div className="absolute bottom-5 left-5 right-5 z-20 max-h-[42vh] overflow-auto rounded-2xl border bg-background/95 p-3 shadow-lg backdrop-blur"><div className="flex items-center justify-between gap-4"><p className="text-xs font-medium">{runNotice ?? `Run ${activeRunId}`}</p><div className="flex items-center gap-2">{activeRunId && <Badge variant="outline" className="text-[10px]">{activeRunId}</Badge>}{runNodes.some((node) => ["queued", "running"].includes(node.status)) && <Button size="sm" variant="outline" onClick={() => void cancelActiveRun()}>Cancel run</Button>}{runNodes.some((node) => ["failed", "cancelled"].includes(node.status)) && <Button size="sm" variant="outline" onClick={() => void retryActiveRun()}>Retry</Button>}</div></div>{runNodes.length > 0 && <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{runNodes.map((node) => <div key={node.node_id} className="rounded-xl border bg-card px-3 py-2"><div className="flex items-center justify-between gap-2"><p className="truncate text-xs font-medium">{node.node_id}</p><Badge variant="outline" className={cn("h-5 px-1.5 text-[10px]", ["succeeded", "approved"].includes(node.status) && "border-emerald-200 bg-emerald-50 text-emerald-700", ["failed", "blocked"].includes(node.status) && "border-red-200 bg-red-50 text-red-700")}>{node.status}</Badge></div><p className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted-foreground">{node.message}</p></div>)}</div>}{directionResults.map(({ nodeId, direction }) => <details key={nodeId} className="mt-3 rounded-xl border bg-card p-3"><summary className="cursor-pointer text-xs font-medium">Open Creative Contract{direction.commercialType ? ` · ${direction.commercialType}` : ""}</summary><div className="mt-3 grid gap-3 text-xs leading-5 text-muted-foreground md:grid-cols-2"><div><p className="font-medium text-foreground">Reference insight</p><p>{direction.referenceSummary || "No summary returned."}</p></div><div><p className="font-medium text-foreground">Output language</p><p>{direction.outputLanguage || "Inherited from production brief"}</p></div>{[["What to adapt", direction.strengths], ["Story structure", direction.story], ["Characters & staging", direction.characters], ["Required assets", direction.assets], ["Risks", direction.risks]].map(([title, items]) => <div key={title as string}><p className="font-medium text-foreground">{title}</p>{(items as string[]).length ? <ul className="mt-1 list-disc space-y-0.5 pl-4">{(items as string[]).map((item) => <li key={item}>{item}</li>)}</ul> : <p>None recorded.</p>}</div>)}</div></details>)}{runNodes.filter((node) => typeof node.result.script_text === "string" && node.result.script_text.trim()).map((node) => <details key={node.node_id} className="mt-3 rounded-xl border bg-card p-3"><summary className="cursor-pointer text-xs font-medium">Open generated script</summary><pre className="mt-3 whitespace-pre-wrap font-sans text-xs leading-5 text-muted-foreground">{String(node.result.script_text)}</pre>{template === "script" && <Button size="sm" className="mt-3" onClick={() => approveGeneratedScript(node)}>Approve this script</Button>}</details>)}{runAssets.length > 0 && <div className="mt-3"><p className="mb-2 text-xs font-medium">Choose one candidate to approve</p><div className="flex gap-3 overflow-x-auto">{runAssets.map((asset) => <button type="button" key={asset.id} onClick={() => selectGeneratedCandidate(asset.id)} title={`Select ${asset.title}`} className={cn("group relative h-24 w-28 shrink-0 overflow-hidden rounded-lg border bg-muted text-left ring-offset-background hover:ring-2 hover:ring-foreground", selectedCandidateId === asset.id && "ring-2 ring-foreground")} >{asset.type === "video" ? <video src={asset.url} muted preload="metadata" className="size-full object-cover" /> : <img alt={asset.title} src={asset.url} className="size-full object-cover" />}<span className="absolute inset-x-0 bottom-0 truncate bg-background/85 px-1.5 py-1 text-[10px] font-medium">{selectedCandidateId === asset.id ? "Selected" : asset.type === "video" ? "Video take" : "Image candidate"}</span><span className="sr-only">Select {asset.title}</span></button>)}</div></div>}</div>}
        </section>
        <aside className="hidden w-80 shrink-0 border-l bg-card lg:block"><div className="flex items-center gap-2 border-b px-5 py-4"><PanelRight className="size-4" /><span className="text-sm font-semibold">Inspector</span></div>{selected ? <div className="space-y-5 p-5"><div><p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">Selected node</p><h2 className="mt-2 text-lg font-semibold">{selected.data.title}</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">{selected.data.subtitle}</p></div>{selected.id === "prompt" && <><label className="block"><span className="text-xs font-medium">Image prompt</span><textarea value={String(selected.data.params?.prompt ?? "")} onChange={(event) => updateSelectedParams({ prompt: event.target.value })} placeholder="Describe the image you want to create…" className="mt-2 min-h-28 w-full resize-y rounded-xl border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-foreground/20" /></label><label className="block"><span className="text-xs font-medium">Reference images</span><select multiple value={(selected.data.params?.reference_asset_ids ?? []) as string[]} onChange={(event) => updateSelectedParams({ reference_asset_ids: Array.from(event.target.selectedOptions, (option) => option.value) })} className="mt-2 min-h-28 w-full rounded-xl border bg-background p-2 text-sm">{liveAssets.filter((asset) => asset.type === "image").map((asset) => <option key={asset.id} value={asset.id}>{asset.title}</option>)}</select><p className="mt-2 text-xs leading-5 text-muted-foreground">Hold ⌘ or Ctrl to choose more than one reference.</p></label></>}{selected.id === "reference" && <><label className="block"><span className="text-xs font-medium">Creative brief</span><textarea value={String(selected.data.params?.brief ?? "")} onChange={(event) => updateSelectedParams({ brief: event.target.value })} placeholder="Describe the commercial goal or attach a reference asset…" className="mt-2 min-h-28 w-full resize-y rounded-xl border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-foreground/20" /></label><div className="grid grid-cols-3 gap-2"><label className="text-xs font-medium">Duration<select value={String(selected.data.params?.target_seconds ?? 30)} onChange={(event) => updateSelectedParams({ target_seconds: Number(event.target.value) })} className="mt-1 w-full rounded-lg border bg-background p-2 text-sm"><option value={15}>15s</option><option value={30}>30s</option><option value={60}>60s</option></select></label><label className="text-xs font-medium">Ratio<select value={String(selected.data.params?.aspect_ratio ?? "9:16")} onChange={(event) => updateSelectedParams({ aspect_ratio: event.target.value })} className="mt-1 w-full rounded-lg border bg-background p-2 text-sm"><option>9:16</option><option>16:9</option></select></label><label className="text-xs font-medium">Quality<select value={String(selected.data.params?.resolution ?? "720p")} onChange={(event) => updateSelectedParams({ resolution: event.target.value })} className="mt-1 w-full rounded-lg border bg-background p-2 text-sm"><option>720p</option><option>1080p</option></select></label></div><div><span className="text-xs font-medium">Source assets</span><p className="mt-1 text-xs leading-5 text-muted-foreground">Mark creative reference separately from your own brand asset. The Strategist sees both, but will only adapt transferable reference ideas.</p><div className="mt-2 max-h-44 space-y-1 overflow-auto rounded-xl border p-2">{liveAssets.length === 0 ? <p className="px-2 py-1 text-xs text-muted-foreground">No workspace assets yet.</p> : liveAssets.map((asset) => <div key={asset.id} className="flex items-center gap-2 rounded-lg p-2 text-xs hover:bg-muted"><span className="min-w-0 flex-1 truncate">{asset.title}</span><label className="flex items-center gap-1 text-[10px]"><input type="checkbox" checked={selectedAssetIds.includes(asset.id)} onChange={() => toggleReferenceAsset(asset.id)} />Ref</label><label className="flex items-center gap-1 text-[10px]"><input type="checkbox" checked={selectedBrandAssetIds.includes(asset.id)} onChange={() => toggleBrandAsset(asset.id)} />Brand</label></div>)}</div></div></>}{selected.id === "keyframe" && <label className="block"><span className="text-xs font-medium">Approved keyframe</span><select value={String(selected.data.params?.asset_id ?? "")} onChange={(event) => updateSelectedParams({ asset_id: event.target.value })} className="mt-2 w-full rounded-xl border bg-background p-3 text-sm"><option value="">Choose an image asset…</option>{liveAssets.filter((asset) => asset.type === "image").map((asset) => <option key={asset.id} value={asset.id}>{asset.title}</option>)}</select><p className="mt-2 text-xs leading-5 text-muted-foreground">Only a selected keyframe can start a video shot.</p></label>}{selected.id === "shot" && <div className="space-y-3"><label className="block"><span className="text-xs font-medium">Video prompt</span><textarea value={String(selected.data.params?.prompt ?? "")} onChange={(event) => updateSelectedParams({ prompt: event.target.value })} placeholder="Describe camera movement and action…" className="mt-2 min-h-24 w-full resize-y rounded-xl border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-foreground/20" /></label><div className="grid grid-cols-2 gap-2"><label className="text-xs font-medium">Duration<select value={String(selected.data.params?.duration_seconds ?? 4)} onChange={(event) => updateSelectedParams({ duration_seconds: Number(event.target.value) })} className="mt-1 w-full rounded-lg border bg-background p-2 text-sm"><option value={4}>4s</option><option value={6}>6s</option><option value={8}>8s</option></select></label><label className="text-xs font-medium">Ratio<select value={String(selected.data.params?.aspect_ratio ?? "9:16")} onChange={(event) => updateSelectedParams({ aspect_ratio: event.target.value })} className="mt-1 w-full rounded-lg border bg-background p-2 text-sm"><option>9:16</option><option>16:9</option></select></label></div></div>}<div className="rounded-xl border bg-background p-3"><p className="text-xs font-medium">Run status</p><p className="mt-2 text-xs text-muted-foreground">{selected.data.status === "ready" || selected.data.status === "valid" ? "Ready to pass downstream" : "Needs configuration before it can run"}</p></div></div> : <div className="p-5 text-sm text-muted-foreground">Select a node to inspect it.</div>}</aside>
      </div>
      {renameOpen && <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-foreground/30 p-4"><form onSubmit={(event) => { event.preventDefault(); void renameWorkflow(); }} className="w-full max-w-md rounded-2xl border bg-background p-5 shadow-xl"><div className="flex items-center justify-between"><h2 className="text-base font-semibold">Rename workflow</h2><Button type="button" variant="ghost" size="icon" onClick={() => setRenameOpen(false)}><X className="size-4" /></Button></div><p className="mt-2 text-sm text-muted-foreground">Give this workflow a name you can find later.</p><input autoFocus value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} className="mt-4 w-full rounded-xl border bg-background px-3 py-2.5 text-sm" /><div className="mt-5 flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setRenameOpen(false)}>Cancel</Button><Button type="submit" disabled={!titleDraft.trim() || saving}>Save name</Button></div></form></div>}
      {deleteOpen && <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-foreground/30 p-4"><div className="w-full max-w-md rounded-2xl border bg-background p-5 shadow-xl"><div className="flex items-center justify-between"><h2 className="text-base font-semibold">Delete workflow?</h2><Button variant="ghost" size="icon" onClick={() => setDeleteOpen(false)}><X className="size-4" /></Button></div><p className="mt-2 text-sm leading-6 text-muted-foreground">This removes the workflow and its run history. Generated assets stay in your library.</p><div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setDeleteOpen(false)}>Keep workflow</Button><Button variant="destructive" disabled={saving} onClick={() => void removeWorkflow()}>Delete workflow</Button></div></div></div>}
      {costConfirmOpen && <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-foreground/30 p-4"><div className="w-full max-w-md rounded-2xl border bg-background p-5 shadow-xl"><div className="flex items-center justify-between"><h2 className="text-base font-semibold">Confirm generation</h2><Button variant="ghost" size="icon" onClick={() => setCostConfirmOpen(false)}><X className="size-4" /></Button></div><p className="mt-2 text-sm leading-6 text-muted-foreground">This {template === "video" ? "video" : "image"} generation will call your configured provider and may use Studio budget. You can still cancel the workflow after it enters the queue; provider work already in progress may complete but will never be selected automatically.</p><div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setCostConfirmOpen(false)}>Go back</Button><Button onClick={() => { setCostConfirmOpen(false); void requestRun(true); }}>Generate</Button></div></div></div>}
      {reviewAsset && <CandidateReviewDialog candidates={runAssets} active={reviewAsset} selectedId={selectedCandidateId} onClose={() => setReviewAsset(null)} onActive={setReviewAsset} onChoose={approveGeneratedCandidate} />}
      {previewAsset && <div role="dialog" aria-modal="true" className="fixed inset-0 z-[60] grid place-items-center bg-black/65 p-6" onClick={() => setPreviewAsset(null)}><div className="max-h-full w-full max-w-4xl overflow-auto rounded-2xl bg-background p-4 shadow-2xl" onClick={(event) => event.stopPropagation()}><div className="mb-3 flex items-center justify-between"><div><p className="text-sm font-semibold">Candidate review</p><p className="text-xs text-muted-foreground">Selected candidate can still be changed before approval.</p></div><Button variant="ghost" size="icon" onClick={() => setPreviewAsset(null)}><X className="size-4" /></Button></div>{previewAsset.type === "video" ? <video src={previewAsset.url} controls autoPlay className="max-h-[70vh] w-full rounded-xl bg-black" /> : <img src={previewAsset.url} alt={previewAsset.title} className="max-h-[70vh] w-full rounded-xl object-contain" />}<div className="mt-4 flex justify-end gap-2"><Button variant="outline" onClick={() => setPreviewAsset(null)}>Keep reviewing</Button><Button onClick={() => { selectGeneratedCandidate(previewAsset.id); setPreviewAsset(null); }}>Use this candidate</Button></div></div></div>}
      </main>
    </div>
  );
}
