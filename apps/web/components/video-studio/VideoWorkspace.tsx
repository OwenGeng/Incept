"use client";

/* eslint-disable @next/next/no-img-element -- project asset URLs are private API responses, not optimizable public images */

import Link from "next/link";
import {
  Background,
  MiniMap,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type NodeTypes,
  type OnSelectionChangeParams,
  type ReactFlowInstance,
  type Viewport,
} from "@xyflow/react";
import {
  Bot,
  Box,
  FileAudio,
  FileText,
  FolderOpen,
  Image as ImageIcon,
  LoaderCircle,
  LayoutGrid,
  Play,
  Plus,
  Settings,
  Share,
  Sparkles,
  Trash2,
  Upload,
  Video,
  WandSparkles,
  X,
  Undo2,
  Redo2,
  Copy,
  ClipboardPaste,
  Network,
  Map as MapIcon,
  Paperclip,
  Music2,
  Scan,
  HelpCircle,
  SlidersHorizontal,
  Edit3,
  FolderPlus,
} from "lucide-react";
import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { videoStudioApi } from "./api";
import { AgentPanel } from "./AgentPanel";
import { StudioNodeCard } from "./StudioNodeCard";
import type { AssetEntry, DirectorAnchor, DirectorScene, ProductionState, ProjectDetail, StudioEdge, StudioNode, StudioSettings, VideoNodeData } from "./types";
import { useStudioLanguage } from "./useStudioLanguage";
import { StudioSettingsDialog } from "./StudioSettingsDialog";
import { RichDocumentEditor } from "./RichDocumentEditor";
import { DEFAULT_DIRECTOR_SCENE, Director3DDialog } from "./Director3DDialog";
import { ProductionPanel } from "./ProductionPanel";

const nodeTypes: NodeTypes = { studio: StudioNodeCard };

const NODE_KINDS = [
  { kind: "text", zh: "文本", en: "Text", icon: FileText },
  { kind: "image", zh: "图片", en: "Image", icon: ImageIcon },
  { kind: "video", zh: "视频", en: "Video", icon: Video },
  { kind: "audio", zh: "音频", en: "Audio", icon: FileAudio },
  { kind: "imageGeneration", zh: "图片生成", en: "Image generation", icon: Sparkles },
  { kind: "videoGeneration", zh: "视频生成", en: "Video generation", icon: WandSparkles },
  { kind: "director3d", zh: "3D 导演", en: "3D director", icon: Box },
] as const;

function toNode(node: ProjectDetail["canvas"]["nodes"][number], projectId: string): StudioNode {
  const assetPath = typeof node.data.assetPath === "string" ? node.data.assetPath : "";
  return {
    id: node.id,
    type: "studio",
    position: node.position,
    data: {
      ...node.data,
      label: String(node.data.label || node.type),
      kind: String(node.data.kind || node.type),
      ...(assetPath ? { previewUrl: videoStudioApi.assetUrl(projectId, assetPath) } : {}),
    },
  };
}

function toEdge(edge: ProjectDetail["canvas"]["edges"][number]): StudioEdge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.source_handle,
    targetHandle: edge.target_handle,
  };
}

export function VideoWorkspace({ projectId }: { projectId: string }) {
  const { language, setLanguage, isChinese } = useStudioLanguage();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<StudioNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<StudioEdge>([]);
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, zoom: 1 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [leftPanel, setLeftPanel] = useState<"nodes" | "agent" | "document" | "production">("nodes");
  const [rightPanel, setRightPanel] = useState<"inspector" | "assets">("inspector");
  const [assets, setAssets] = useState<AssetEntry[]>([]);
  const [projectFiles, setProjectFiles] = useState<AssetEntry[]>([]);
  const [assetPath, setAssetPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [generationError, setGenerationError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState("");
  const [documentContent, setDocumentContent] = useState("");
  const [documentState, setDocumentState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [productionState, setProductionState] = useState<ProductionState | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [studioSettings, setStudioSettings] = useState<StudioSettings | null>(null);
  const [agentVisible, setAgentVisible] = useState(true);
  const [canvasMenuVisible, setCanvasMenuVisible] = useState(false);
  const [switchingCanvas, setSwitchingCanvas] = useState(false);
  const [nodeMenuVisible, setNodeMenuVisible] = useState(false);
  const [showMiniMap, setShowMiniMap] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [directorOpen, setDirectorOpen] = useState(false);
  const flow = useRef<ReactFlowInstance<StudioNode, StudioEdge> | null>(null);
  const history = useRef<Array<{ nodes: StudioNode[]; edges: StudioEdge[] }>>([]);
  const historyIndex = useRef(-1);
  const restoringHistory = useRef(false);
  const copiedGraph = useRef<{ nodes: StudioNode[]; edges: StudioEdge[] }>({ nodes: [], edges: [] });
  const resumedMediaJobs = useRef(new Set<string>());
  const hydrated = useRef(false);
  const productionHydrated = useRef(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [detail, document, settings, production] = await Promise.all([
          videoStudioApi.getProject(projectId),
          videoStudioApi.getDocument(projectId),
          videoStudioApi.getSettings(),
          videoStudioApi.getProductionState(projectId),
        ]);
        if (!active) return;
        setProject(detail);
        setNodes(detail.canvas.nodes.map((node) => toNode(node, projectId)));
        setEdges(detail.canvas.edges.map(toEdge));
        setViewport(detail.canvas.viewport);
        setDocumentContent(document.content);
        setStudioSettings(settings);
        setProductionState(production);
        history.current = [{ nodes: detail.canvas.nodes.map((node) => toNode(node, projectId)), edges: detail.canvas.edges.map(toEdge) }];
        historyIndex.current = 0;
        hydrated.current = true;
        productionHydrated.current = true;
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Failed to load workspace");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [projectId, setEdges, setNodes]);

  useEffect(() => {
    let active = true;
    const loadProjectFiles = async () => {
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
      if (active) setProjectFiles(files);
    };
    void loadProjectFiles().catch(() => { if (active) setProjectFiles([]); });
    return () => { active = false; };
  }, [projectId]);

  const save = useCallback(async () => {
    if (!hydrated.current) return;
    setSaveState("saving");
    try {
      const payload = {
        version: 1,
        nodes: nodes.map((node) => ({
          id: node.id,
          type: node.data.kind,
          position: node.position,
          data: node.data,
        })),
        edges: edges.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          source_handle: edge.sourceHandle,
          target_handle: edge.targetHandle,
        })),
        viewport,
      };
      if (project?.active_canvas_id) {
        await videoStudioApi.saveProjectCanvas(projectId, project.active_canvas_id, payload);
      } else {
        await videoStudioApi.saveCanvas(projectId, payload);
      }
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  }, [edges, nodes, project?.active_canvas_id, projectId, viewport]);

  useEffect(() => {
    if (!hydrated.current) return;
    setSaveState("idle");
    const timer = window.setTimeout(() => void save(), 700);
    return () => window.clearTimeout(timer);
  }, [edges, nodes, save]);

  useEffect(() => {
    if (!hydrated.current || restoringHistory.current) {
      restoringHistory.current = false;
      return;
    }
    const timer = window.setTimeout(() => {
      const snapshot = { nodes: structuredClone(nodes), edges: structuredClone(edges) };
      const current = history.current[historyIndex.current];
      if (current && JSON.stringify(current) === JSON.stringify(snapshot)) return;
      history.current = [...history.current.slice(0, historyIndex.current + 1), snapshot].slice(-100);
      historyIndex.current = history.current.length - 1;
    }, 450);
    return () => window.clearTimeout(timer);
  }, [edges, nodes]);

  useEffect(() => {
    if (!hydrated.current) return;
    setDocumentState("saving");
    const timer = window.setTimeout(async () => {
      try {
        await videoStudioApi.saveDocument(projectId, documentContent);
        setDocumentState("saved");
      } catch {
        setDocumentState("error");
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [documentContent, projectId]);

  useEffect(() => {
    if (!productionHydrated.current || !productionState) return;
    const timer = window.setTimeout(() => {
      void videoStudioApi.saveProductionState(projectId, productionState).catch(() => setSaveState("error"));
    }, 700);
    return () => window.clearTimeout(timer);
  }, [productionState, projectId]);

  const loadCanvasDetail = useCallback((detail: ProjectDetail) => {
    const nextNodes = detail.canvas.nodes.map((node) => toNode(node, projectId));
    const nextEdges = detail.canvas.edges.map(toEdge);
    setProject(detail);
    setNodes(nextNodes);
    setEdges(nextEdges);
    setViewport(detail.canvas.viewport);
    setSelectedId(null);
    setSelectedIds([]);
    history.current = [{ nodes: nextNodes, edges: nextEdges }];
    historyIndex.current = 0;
  }, [projectId, setEdges, setNodes]);

  const switchCanvas = async (canvasId: string) => {
    if (!project || canvasId === project.active_canvas_id || switchingCanvas) return;
    setSwitchingCanvas(true);
    setCanvasMenuVisible(false);
    try {
      await save();
      loadCanvasDetail(await videoStudioApi.activateCanvas(projectId, canvasId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not switch canvas");
    } finally {
      setSwitchingCanvas(false);
    }
  };

  const createCanvas = async () => {
    const name = window.prompt(isChinese ? "画布名称" : "Canvas name", isChinese ? `画布 ${(project?.canvases.length || 0) + 1}` : `Canvas ${(project?.canvases.length || 0) + 1}`)?.trim();
    if (!name || !project) return;
    setSwitchingCanvas(true);
    try {
      await save();
      loadCanvasDetail(await videoStudioApi.createCanvas(projectId, name));
      setCanvasMenuVisible(false);
    } finally {
      setSwitchingCanvas(false);
    }
  };

  const renameCanvas = async (canvasId: string, currentName: string) => {
    const name = window.prompt(isChinese ? "重命名画布" : "Rename canvas", currentName)?.trim();
    if (!name || !project) return;
    const canvases = await videoStudioApi.renameCanvas(projectId, canvasId, name);
    setProject({ ...project, canvases });
  };

  const deleteCanvas = async (canvasId: string, name: string) => {
    if (!project || !window.confirm(isChinese ? `删除画布“${name}”？` : `Delete canvas “${name}”?`)) return;
    try {
      loadCanvasDetail(await videoStudioApi.deleteCanvas(projectId, canvasId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete canvas");
    }
  };

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedId) ?? null,
    [nodes, selectedId],
  );
  const selectedGenerations = useMemo(() => {
    const value = selectedNode?.data.generations;
    return Array.isArray(value) ? value.filter((item): item is { jobId: string; assetPath: string; mimeType: string; prompt: string; createdAt: string } => Boolean(item && typeof item === "object" && typeof item.assetPath === "string")) : [];
  }, [selectedNode]);
  const directorScene = useMemo<DirectorScene>(() => {
    const value = selectedNode?.data.scene;
    return value && typeof value === "object" && Array.isArray((value as DirectorScene).objects)
      ? value as DirectorScene
      : structuredClone(DEFAULT_DIRECTOR_SCENE);
  }, [selectedNode]);
  const directorAnchors = useMemo<DirectorAnchor[]>(() => {
    const value = selectedNode?.data.cameraAnchors;
    return Array.isArray(value) ? value as DirectorAnchor[] : [];
  }, [selectedNode]);
  const productionCandidates = useMemo(() => nodes.flatMap((node) => {
    if (!["image", "video", "imageGeneration", "videoGeneration"].includes(node.data.kind) || typeof node.data.assetPath !== "string") return [];
    return [{
      nodeId: node.id,
      label: node.data.label,
      assetPath: node.data.assetPath,
      mimeType: String(node.data.mimeType || (node.data.kind === "image" || node.data.kind === "imageGeneration" ? "image/*" : "video/*")),
      sourceJobId: typeof node.data.mediaJobId === "string" ? node.data.mediaJobId : undefined,
      duration: node.data.kind === "image" || node.data.kind === "imageGeneration" ? 3 : Number(node.data.duration || studioSettings?.default_video_duration || 5),
    }];
  }), [nodes, studioSettings?.default_video_duration]);

  const applyAgentCanvas = (canvas: ProjectDetail["canvas"]) => {
    setNodes(canvas.nodes.map((node) => toNode(node, projectId)));
    setEdges(canvas.edges.map(toEdge));
    setViewport(canvas.viewport);
  };

  const addNode = (kind: string, label?: string, data: Partial<VideoNodeData> = {}) => {
    const definition = NODE_KINDS.find((item) => item.kind === kind);
    const id = `${kind}-${crypto.randomUUID()}`;
    const node: StudioNode = {
      id,
      type: "studio",
      position: { x: 120 + (nodes.length % 4) * 260, y: 100 + Math.floor(nodes.length / 4) * 180 },
      data: {
        label: label || (isChinese ? definition?.zh : definition?.en) || kind,
        kind,
        status: "idle",
        ...data,
      },
    };
    setNodes((items) => [...items, node]);
    setSelectedId(id);
    setRightPanel("inspector");
  };

  const updateSelected = (patch: Partial<VideoNodeData>) => {
    if (!selectedId) return;
    setNodes((items) => items.map((node) => node.id === selectedId ? { ...node, data: { ...node.data, ...patch } } : node));
  };

  const updateNode = useCallback((nodeId: string, patch: Partial<VideoNodeData>) => {
    setNodes((items) => items.map((node) => node.id === nodeId ? { ...node, data: { ...node.data, ...patch } } : node));
  }, [setNodes]);

  useEffect(() => {
    for (const node of nodes) {
      const jobId = typeof node.data.mediaJobId === "string" ? node.data.mediaJobId : "";
      if (node.data.status !== "running" || !jobId || resumedMediaJobs.current.has(jobId)) continue;
      resumedMediaJobs.current.add(jobId);
      void (async () => {
        try {
          let job = await videoStudioApi.getMediaJob(projectId, jobId);
          while (job.status === "queued" || job.status === "running") {
            updateNode(node.id, { progress: job.progress, statusMessage: job.message });
            await new Promise((resolve) => window.setTimeout(resolve, 1_000));
            job = await videoStudioApi.getMediaJob(projectId, jobId);
          }
          if (job.status === "completed" && job.result_asset_path && job.result_mime_type) {
            updateNode(node.id, {
              status: "ready",
              progress: 100,
              statusMessage: job.message,
              assetPath: job.result_asset_path,
              previewUrl: videoStudioApi.assetUrl(projectId, job.result_asset_path),
              mimeType: job.result_mime_type,
            });
          } else {
            updateNode(node.id, { status: "error", statusMessage: job.message });
          }
        } catch (reason) {
          updateNode(node.id, { status: "error", statusMessage: reason instanceof Error ? reason.message : "Generation status unavailable" });
        }
      })();
    }
  }, [nodes, projectId, updateNode]);

  const removeSelected = useCallback(() => {
    const ids = selectedIds.length > 0 ? selectedIds : selectedId ? [selectedId] : [];
    if (ids.length === 0) return;
    const idSet = new Set(ids);
    setNodes((items) => items.filter((node) => !idSet.has(node.id)));
    setEdges((items) => items.filter((edge) => !idSet.has(edge.source) && !idSet.has(edge.target)));
    setSelectedId(null);
    setSelectedIds([]);
  }, [selectedId, selectedIds, setEdges, setNodes]);

  const undo = useCallback(() => {
    if (historyIndex.current <= 0) return;
    historyIndex.current -= 1;
    const snapshot = history.current[historyIndex.current];
    restoringHistory.current = true;
    setNodes(structuredClone(snapshot.nodes));
    setEdges(structuredClone(snapshot.edges));
  }, [setEdges, setNodes]);

  const redo = useCallback(() => {
    if (historyIndex.current >= history.current.length - 1) return;
    historyIndex.current += 1;
    const snapshot = history.current[historyIndex.current];
    restoringHistory.current = true;
    setNodes(structuredClone(snapshot.nodes));
    setEdges(structuredClone(snapshot.edges));
  }, [setEdges, setNodes]);

  const copySelection = useCallback(() => {
    const ids = new Set(selectedIds.length ? selectedIds : selectedId ? [selectedId] : []);
    copiedGraph.current = {
      nodes: nodes.filter((node) => ids.has(node.id)).map((node) => structuredClone(node)),
      edges: edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)).map((edge) => structuredClone(edge)),
    };
  }, [edges, nodes, selectedId, selectedIds]);

  const pasteSelection = useCallback(() => {
    if (copiedGraph.current.nodes.length === 0) return;
    const idMap = new Map<string, string>();
    const pasted = copiedGraph.current.nodes.map((node) => {
      const id = `${node.data.kind}-${crypto.randomUUID()}`;
      idMap.set(node.id, id);
      return { ...structuredClone(node), id, position: { x: node.position.x + 40, y: node.position.y + 40 }, selected: true };
    });
    const pastedEdges = copiedGraph.current.edges.flatMap((edge) => {
      const source = idMap.get(edge.source);
      const target = idMap.get(edge.target);
      return source && target ? [{ ...structuredClone(edge), id: crypto.randomUUID(), source, target }] : [];
    });
    setNodes((items) => [...items.map((item) => ({ ...item, selected: false })), ...pasted]);
    setEdges((items) => [...items, ...pastedEdges]);
    setSelectedIds(pasted.map((node) => node.id));
    setSelectedId(pasted[0]?.id || null);
  }, [setEdges, setNodes]);

  const arrangeCanvas = useCallback(() => {
    if (nodes.length === 0) return;
    const nodeIds = new Set(nodes.map((node) => node.id));
    const incoming = new Map(nodes.map((node) => [node.id, 0]));
    const outgoing = new Map(nodes.map((node) => [node.id, [] as string[]]));
    for (const edge of edges) {
      if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) continue;
      incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
      outgoing.get(edge.source)?.push(edge.target);
    }
    const queue = nodes.filter((node) => incoming.get(node.id) === 0).map((node) => node.id);
    const ranks = new Map<string, number>();
    for (const id of queue) ranks.set(id, 0);
    for (let index = 0; index < queue.length; index += 1) {
      const id = queue[index];
      for (const target of outgoing.get(id) || []) {
        ranks.set(target, Math.max(ranks.get(target) || 0, (ranks.get(id) || 0) + 1));
        incoming.set(target, (incoming.get(target) || 1) - 1);
        if (incoming.get(target) === 0) queue.push(target);
      }
    }
    for (const node of nodes) if (!ranks.has(node.id)) ranks.set(node.id, 0);
    const rows = new Map<number, string[]>();
    for (const node of nodes) {
      const rank = ranks.get(node.id) || 0;
      rows.set(rank, [...(rows.get(rank) || []), node.id]);
    }
    setNodes((items) => items.map((node) => {
      const rank = ranks.get(node.id) || 0;
      const row = rows.get(rank) || [];
      return { ...node, position: { x: 100 + rank * 320, y: 100 + row.indexOf(node.id) * 220 } };
    }));
    window.setTimeout(() => void flow.current?.fitView({ padding: 0.2, duration: 300 }), 0);
  }, [edges, nodes, setNodes]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable=true]")) return;
      const command = event.metaKey || event.ctrlKey;
      if (command && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); }
      if (command && event.key.toLowerCase() === "c") { event.preventDefault(); copySelection(); }
      if (command && event.key.toLowerCase() === "v") { event.preventDefault(); pasteSelection(); }
      if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); removeSelected(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [copySelection, pasteSelection, redo, removeSelected, undo]);

  const generateSelected = async () => {
    if (!selectedNode || !["imageGeneration", "videoGeneration"].includes(selectedNode.data.kind)) return;
    const prompt = String(selectedNode.data.prompt || "").trim();
    if (!prompt) {
      setGenerationError(isChinese ? "请先填写提示词。" : "Add a prompt first.");
      return;
    }
    setGenerationError("");
    const nodeId = selectedNode.id;
    updateNode(nodeId, { status: "running", progress: 0, statusMessage: isChinese ? "排队中" : "Queued" });
    try {
      const mediaType = selectedNode.data.kind === "imageGeneration" ? "image" : "video";
      let job = await videoStudioApi.createMediaJob(projectId, {
        idempotency_key: crypto.randomUUID(),
        media_type: mediaType,
        prompt,
        ratio: String(selectedNode.data.ratio || studioSettings?.default_image_ratio || "16:9"),
        ...(mediaType === "video" ? {
          duration: Number(selectedNode.data.duration || studioSettings?.default_video_duration || 5),
          ...(selectedNode.data.firstFramePath ? { first_frame_path: String(selectedNode.data.firstFramePath) } : {}),
          ...(selectedNode.data.lastFramePath ? { last_frame_path: String(selectedNode.data.lastFramePath) } : {}),
        } : {}),
      });
      updateNode(nodeId, { mediaJobId: job.id, progress: job.progress, statusMessage: job.message });
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 1_000));
        job = await videoStudioApi.getMediaJob(projectId, job.id);
        updateNode(nodeId, { progress: job.progress, statusMessage: job.message });
      }
      if (job.status !== "completed" || !job.result_asset_path || !job.result_mime_type) {
        throw new Error(job.message || "Generation failed");
      }
      const resultAssetPath = job.result_asset_path;
      const resultMimeType = job.result_mime_type;
      setNodes((items) => items.map((node) => {
        if (node.id !== nodeId) return node;
        const history = Array.isArray(node.data.generations) ? node.data.generations : [];
        const generation = {
          jobId: job.id,
          assetPath: resultAssetPath,
          mimeType: resultMimeType,
          prompt,
          createdAt: new Date().toISOString(),
        };
        return {
          ...node,
          data: {
            ...node.data,
            status: "ready",
            progress: 100,
            statusMessage: job.message,
            assetPath: resultAssetPath,
            previewUrl: videoStudioApi.assetUrl(projectId, resultAssetPath),
            mimeType: resultMimeType,
            generations: [generation, ...history].slice(0, 20),
          },
        };
      }));
      setProjectFiles((items) => [{
        path: resultAssetPath,
        name: resultAssetPath.split("/").at(-1) || resultAssetPath,
        kind: "file",
        size: job.result_size || 0,
        modified_at: new Date().toISOString(),
        mime_type: resultMimeType,
      }, ...items.filter((item) => item.path !== resultAssetPath)]);
      if (rightPanel === "assets") await loadAssets(assetPath);
    } catch (reason) {
      updateNode(nodeId, { status: "error" });
      setGenerationError(reason instanceof Error ? reason.message : "Generation failed");
    }
  };

  const cancelSelectedGeneration = async () => {
    if (!selectedNode || typeof selectedNode.data.mediaJobId !== "string") return;
    const job = await videoStudioApi.cancelMediaJob(projectId, selectedNode.data.mediaJobId);
    updateNode(selectedNode.id, { status: "error", statusMessage: job.message });
  };

  const exportVideo = async () => {
    const mediaNodes = [...nodes]
      .filter((node) => ["image", "video", "imageGeneration", "videoGeneration"].includes(node.data.kind) && node.data.assetPath)
      .sort((left, right) => left.position.y - right.position.y || left.position.x - right.position.x);
    let exportClips: Array<{ asset_path: string; duration?: number; transition: "cut" | "crossfade" }> = mediaNodes.map((node) => ({
      asset_path: String(node.data.assetPath),
      ...(node.data.kind === "image" || node.data.kind === "imageGeneration" ? { duration: 3 } : {}),
      transition: "cut" as const,
    }));
    if (productionState?.timeline.some((clip) => clip.included)) {
      await videoStudioApi.saveProductionState(projectId, productionState);
      const checked = await videoStudioApi.runProductionQa(projectId);
      setProductionState(checked);
      if (checked.qa.status === "blocked") {
        setExportResult((isChinese ? "QA 阻止导出：" : "QA blocked export: ") + checked.qa.issues.join("; "));
        return;
      }
      exportClips = checked.timeline.filter((clip) => clip.included).flatMap((clip) => {
        const shot = checked.shots.find((item) => item.id === clip.shot_id);
        const take = shot?.takes.find((item) => item.id === shot.selected_take_id);
        return take ? [{ asset_path: take.asset_path, duration: clip.duration, transition: clip.transition }] : [];
      });
    }
    if (exportClips.length === 0) {
      setExportResult(isChinese ? "请先在画布中添加至少一个图片或视频素材。" : "Add at least one image or video asset to the canvas.");
      return;
    }
    const soundtrack = nodes.find((node) => node.data.kind === "audio" && node.data.assetPath);
    setExporting(true);
    setExportResult("");
    try {
      let job = await videoStudioApi.createExportJob(projectId, {
        idempotency_key: crypto.randomUUID(),
        name: project?.name || "video-export",
        clips: exportClips,
        ...(soundtrack ? { soundtrack_path: String(soundtrack.data.assetPath) } : {}),
      });
      setExportJobId(job.id);
      setExportResult(`${isChinese ? "正在导出" : "Exporting"}: ${job.progress}%`);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        job = await videoStudioApi.getExportJob(projectId, job.id);
        setExportResult(`${job.message || (isChinese ? "正在导出" : "Exporting")}: ${job.progress}%`);
      }
      if (job.status !== "completed" || !job.result) throw new Error(job.message || "Export failed");
      setExportResult(`${isChinese ? "导出完成" : "Export ready"}: ${job.result.asset_path}`);
      setProductionState(await videoStudioApi.recordDelivery(projectId, job.result.asset_path));
      await loadAssets("");
    } catch (reason) {
      setExportResult(reason instanceof Error ? reason.message : "Export failed");
    } finally {
      setExporting(false);
      setExportJobId(null);
    }
  };

  const cancelExport = async () => {
    if (!exportJobId) return;
    const job = await videoStudioApi.cancelExportJob(projectId, exportJobId);
    setExportResult(job.message || (isChinese ? "已请求取消导出" : "Export cancellation requested"));
  };

  const connect = useCallback((connection: Connection) => {
    setEdges((items) => addEdge({ ...connection, id: crypto.randomUUID() }, items));
  }, [setEdges]);

  const onSelectionChange = useCallback(({ nodes: selectedNodes }: OnSelectionChangeParams) => {
    const ids = selectedNodes.map((node) => node.id);
    setSelectedIds(ids);
    setSelectedId(ids[0] || null);
  }, []);

  const loadAssets = useCallback(async (path = assetPath) => {
    try {
      setAssets(await videoStudioApi.listAssets(projectId, path));
      setAssetPath(path);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to load assets");
    }
  }, [assetPath, projectId]);

  useEffect(() => {
    if (rightPanel === "assets") void loadAssets();
  }, [loadAssets, rightPanel]);

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    await videoStudioApi.uploadAsset(projectId, file, assetPath);
    event.target.value = "";
    await loadAssets();
  };

  const insertAsset = (asset: AssetEntry) => {
    if (asset.kind === "directory") {
      void loadAssets(asset.path);
      return;
    }
    const mime = asset.mime_type || "";
    const kind = mime.startsWith("image/") ? "image" : mime.startsWith("video/") ? "video" : mime.startsWith("audio/") ? "audio" : "text";
    addNode(kind, asset.name, { assetPath: asset.path, previewUrl: videoStudioApi.assetUrl(projectId, asset.path), mimeType: asset.mime_type || undefined });
  };

  const createAssetDirectory = async () => {
    const name = window.prompt(isChinese ? "文件夹名称" : "Folder name")?.trim();
    if (!name) return;
    await videoStudioApi.createAssetDirectory(projectId, [assetPath, name].filter(Boolean).join("/"));
    await loadAssets();
  };

  const renameAsset = async (asset: AssetEntry) => {
    const name = window.prompt(isChinese ? "新名称" : "New name", asset.name)?.trim();
    if (!name || name === asset.name) return;
    const parent = asset.path.includes("/") ? asset.path.slice(0, asset.path.lastIndexOf("/")) : "";
    await videoStudioApi.renameAsset(projectId, asset.path, [parent, name].filter(Boolean).join("/"));
    await loadAssets();
  };

  const deleteAsset = async (asset: AssetEntry) => {
    if (!window.confirm(isChinese ? `删除“${asset.name}”？` : `Delete “${asset.name}”?`)) return;
    await videoStudioApi.deleteAsset(projectId, asset.path);
    await loadAssets();
  };

  if (loading) return <div className="flex min-h-screen items-center justify-center bg-white"><LoaderCircle className="size-6 animate-spin text-[#356fec]" /></div>;
  if (error && !project) return <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-muted p-6 text-center"><p className="text-sm text-red-600">{error}</p><Link href="/video" className="rounded-lg bg-foreground px-4 py-2 text-sm text-white">{isChinese ? "返回项目" : "Back to projects"}</Link></div>;

  return (
    <main className="relative h-screen min-h-[640px] overflow-hidden bg-white text-[#303133]">
      <section className={`absolute inset-0 transition-opacity ${leftPanel === "document" || leftPanel === "production" ? "pointer-events-none opacity-0" : "opacity-100"}`} aria-label={isChinese ? "视频工作流画布" : "Video workflow canvas"}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={connect}
          onNodeClick={(_event, node) => { setSelectedId(node.id); setRightPanel("inspector"); }}
          onPaneClick={() => { setSelectedId(null); setNodeMenuVisible(false); }}
          onSelectionChange={onSelectionChange}
          onMoveEnd={(_event, nextViewport) => setViewport(nextViewport)}
          onInit={(instance) => { flow.current = instance; }}
          defaultViewport={viewport}
          fitView={nodes.length > 0}
          minZoom={0.2}
          maxZoom={8}
          selectionOnDrag
          panOnScroll
        >
          <Background color="#d9dce3" gap={16} size={1} />
          {showMiniMap && <MiniMap className="!bottom-20 !right-auto !left-4 !rounded-xl !border !border-[#ebeef5] !bg-white" nodeColor="#c4b5fd" maskColor="rgba(255,255,255,.65)" />}
        </ReactFlow>
      </section>

      {leftPanel === "document" && <section className="absolute inset-0 bg-white px-[max(24px,12vw)] pb-20 pt-24"><div className="mx-auto flex h-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-[#ebeef5] bg-white shadow-sm"><div className="flex items-center justify-between border-b border-[#ebeef5] px-5 py-3"><div><h2 className="font-semibold">{isChinese ? "项目文档与脚本" : "Project document & script"}</h2><p className="mt-0.5 text-[11px] text-[#909399]">{productionState?.script_locked ? `${isChinese ? "已锁定脚本" : "Locked script"} r${productionState.script_revision}` : (isChinese ? "编辑完成后锁定脚本，再进入镜头制作" : "Lock the script before shot production")}</p></div><div className="flex items-center gap-3"><span className="text-xs text-[#909399]">{documentState === "saving" ? (isChinese ? "保存中" : "Saving") : documentState === "error" ? (isChinese ? "保存失败" : "Save failed") : (isChinese ? "已保存" : "Saved")}</span>{productionState?.script_locked ? <button onClick={async () => setProductionState(await videoStudioApi.unlockProductionScript(projectId))} className="rounded-lg border border-[#dcdfe6] px-3 py-1.5 text-xs">{isChinese ? "解锁并修订" : "Unlock to revise"}</button> : <button onClick={async () => { await videoStudioApi.saveDocument(projectId, documentContent); setProductionState(await videoStudioApi.lockProductionScript(projectId, documentContent)); }} disabled={!documentContent.trim()} className="rounded-lg bg-[#8b5cf6] px-3 py-1.5 text-xs text-white disabled:opacity-40">{isChinese ? "锁定脚本" : "Lock script"}</button>}</div></div><div className={`min-h-0 flex-1 ${productionState?.script_locked ? "pointer-events-none bg-[#fafafa] opacity-80" : ""}`}><RichDocumentEditor value={documentContent} onChange={setDocumentContent} placeholder={isChinese ? "在这里编写项目简报、脚本和分镜说明…" : "Write the brief, script, and storyboard notes here…"} /></div></div></section>}
      {leftPanel === "production" && productionState && <ProductionPanel projectId={projectId} isChinese={isChinese} state={productionState} candidates={productionCandidates} assets={projectFiles} defaultRatio={studioSettings?.default_image_ratio || "16:9"} onChange={setProductionState} onCommit={async (label) => { await videoStudioApi.saveProductionState(projectId, productionState); setProductionState(await videoStudioApi.commitTimeline(projectId, label)); }} onQa={async () => { await videoStudioApi.saveProductionState(projectId, productionState); setProductionState(await videoStudioApi.runProductionQa(projectId)); }} />}

      <div className="absolute left-[15px] top-[15px] z-20 flex items-center gap-3">
        <div className="flex h-11 items-center gap-1 rounded-full border border-[#ebeef5] bg-white px-2 shadow-sm"><Link href="/video" aria-label={isChinese ? "退出项目" : "Exit project"} className="rounded-full p-2 text-[#606266] hover:bg-[#f5f7fa]"><X className="size-[17px]" /></Link><button onClick={() => setShowSettings(true)} aria-label={isChinese ? "设置" : "Settings"} className="rounded-full p-2 text-[#606266] hover:bg-[#f5f7fa]"><Settings className="size-[17px]" /></button></div>
        <div className="relative flex h-11 items-center rounded-full border border-[#ebeef5] bg-white px-3 shadow-sm">
          <input value={project?.name || ""} onChange={(event) => setProject((value) => value ? { ...value, name: event.target.value } : value)} onBlur={() => project && videoStudioApi.updateProject(projectId, { name: project.name }).catch(() => undefined)} aria-label={isChinese ? "项目名称" : "Project name"} className="w-28 border-0 bg-transparent px-1 text-sm font-medium outline-none" />
          <span className="mx-2 h-5 w-px bg-[#ebeef5]" />
          <button onClick={() => setCanvasMenuVisible((value) => !value)} disabled={switchingCanvas} className="inline-flex max-w-36 items-center gap-2 px-2 text-sm text-[#606266] disabled:opacity-50"><span className="truncate">{project?.canvases.find((item) => item.id === project.active_canvas_id)?.name || (isChinese ? "选择画布" : "Select canvas")}</span><span>⌄</span></button>
          {canvasMenuVisible && project && <div className="absolute left-28 top-12 z-50 w-64 rounded-2xl border border-[#ebeef5] bg-white p-2 shadow-xl">
            <div className="flex items-center justify-between px-2 py-1.5"><span className="text-xs font-semibold text-[#909399]">{isChinese ? "项目画布" : "Project canvases"}</span><button onClick={() => void createCanvas()} className="rounded-lg p-1.5 text-[#8b5cf6] hover:bg-[#f5f1ff]" aria-label={isChinese ? "新建画布" : "New canvas"}><Plus className="size-4" /></button></div>
            {project.canvases.map((canvas) => <div key={canvas.id} className={`group flex items-center rounded-xl ${canvas.id === project.active_canvas_id ? "bg-[#f2eafe] text-[#7c3aed]" : "hover:bg-[#f5f7fa]"}`}>
              <button onClick={() => void switchCanvas(canvas.id)} className="min-w-0 flex-1 truncate px-3 py-2 text-left text-xs font-medium">{canvas.name}</button>
              <button onClick={() => void renameCanvas(canvas.id, canvas.name)} className="p-1.5 opacity-55 hover:opacity-100" aria-label={isChinese ? "重命名画布" : "Rename canvas"}><Edit3 className="size-3.5" /></button>
              <button onClick={() => void deleteCanvas(canvas.id, canvas.name)} disabled={project.canvases.length === 1} className="mr-1 p-1.5 opacity-55 hover:text-red-500 hover:opacity-100 disabled:hidden" aria-label={isChinese ? "删除画布" : "Delete canvas"}><Trash2 className="size-3.5" /></button>
            </div>)}
          </div>}
        </div>
      </div>

      <div className="absolute left-1/2 top-[15px] z-20 flex h-10 -translate-x-1/2 items-center rounded-full border border-[#ebeef5] bg-white p-1 shadow-sm">
        <button onClick={() => setLeftPanel("nodes")} className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs ${leftPanel === "nodes" ? "bg-[#f2eafe] font-medium text-[#8b5cf6]" : "text-[#606266]"}`}><LayoutGrid className="size-3.5" />{isChinese ? "画布" : "Canvas"}</button>
        <button onClick={() => setLeftPanel("document")} className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs ${leftPanel === "document" ? "bg-[#f2eafe] font-medium text-[#8b5cf6]" : "text-[#606266]"}`}><FileText className="size-3.5" />{isChinese ? "文档" : "Document"}</button>
        <button onClick={() => setLeftPanel("production")} className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs ${leftPanel === "production" ? "bg-[#f2eafe] font-medium text-[#8b5cf6]" : "text-[#606266]"}`}><Video className="size-3.5" />{isChinese ? "制作" : "Production"}</button>
      </div>

      <div className="absolute right-[15px] top-[15px] z-30 flex h-10 items-center rounded-full border border-[#ebeef5] bg-white p-1 shadow-sm"><button onClick={() => setLanguage("zh-CN")} className={`rounded-full px-3 py-1.5 text-xs ${language === "zh-CN" ? "bg-[#f2eafe] font-semibold text-[#8b5cf6]" : "text-[#909399]"}`}>中文</button><button onClick={() => setLanguage("en-US")} className={`rounded-full px-3 py-1.5 text-xs ${language === "en-US" ? "bg-[#f2eafe] font-semibold text-[#8b5cf6]" : "text-[#909399]"}`}>EN</button></div>

      {!agentVisible && leftPanel === "nodes" && <button onClick={() => setAgentVisible(true)} aria-label="LinglongLab Agent" className="absolute right-[116px] top-[15px] z-20 flex size-11 items-center justify-center rounded-full border border-[#ebeef5] bg-gradient-to-br from-[#f7f1ff] to-white text-[#8b5cf6] shadow-sm"><Bot className="size-5" /></button>}

      {agentVisible && leftPanel === "nodes" && <aside id="agentPanel" className="absolute bottom-[14px] right-[14px] top-[136px] z-20 flex w-[min(420px,calc(100vw-28px))] flex-col overflow-hidden rounded-[20px] border border-[#e4e7ed] bg-white shadow-[0_12px_40px_rgba(30,20,50,.12)]">
        <div className="flex h-12 shrink-0 items-center justify-between px-4"><span className="text-sm font-semibold">LinglongLab Agent</span><div className="flex items-center gap-1 text-[#909399]"><button onClick={() => setShowSettings(true)} className="p-1.5" aria-label={isChinese ? "媒体生成控制" : "Media controls"}><SlidersHorizontal className="size-4" /></button><button onClick={() => setAgentVisible(false)} className="p-1.5" aria-label={isChinese ? "关闭对话" : "Close chat"}><X className="size-4" /></button></div></div>
        <div className="min-h-0 flex-1"><AgentPanel projectId={projectId} isChinese={isChinese} onCanvas={applyAgentCanvas} /></div>
      </aside>}

      {leftPanel === "nodes" && nodeMenuVisible && <div className="absolute bottom-[74px] left-[15px] z-30 w-56 rounded-2xl border border-[#ebeef5] bg-white p-2 shadow-xl"><p className="px-2 py-2 text-xs font-semibold text-[#909399]">{isChinese ? "添加节点" : "Add node"}</p>{NODE_KINDS.map(({ kind, zh, en, icon: Icon }) => <button key={kind} onClick={() => { addNode(kind); setNodeMenuVisible(false); }} className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-[#f5f1ff]"><Icon className="size-4 text-[#8b5cf6]" />{isChinese ? zh : en}</button>)}</div>}

      {rightPanel === "assets" && <aside className="absolute bottom-[74px] left-[15px] z-30 flex max-h-[55vh] w-80 flex-col overflow-hidden rounded-2xl border border-[#ebeef5] bg-white shadow-xl"><div className="flex items-center justify-between border-b border-[#ebeef5] px-4 py-3"><button onClick={() => void loadAssets(assetPath.includes("/") ? assetPath.slice(0, assetPath.lastIndexOf("/")) : "")} className="truncate text-sm font-semibold">/{assetPath || (isChinese ? "素材库" : "Assets")}</button><div className="flex items-center gap-1"><button onClick={() => void createAssetDirectory()} className="rounded-lg p-2 text-[#8b5cf6] hover:bg-[#f5f1ff]" aria-label={isChinese ? "新建文件夹" : "New folder"}><FolderPlus className="size-4" /></button><label className="cursor-pointer rounded-lg p-2 text-[#8b5cf6] hover:bg-[#f5f1ff]"><Upload className="size-4" /><input type="file" className="sr-only" onChange={(event) => void upload(event)} /></label><button onClick={() => setRightPanel("inspector")} className="rounded-lg p-2 text-[#909399]"><X className="size-4" /></button></div></div><div className="overflow-y-auto p-2">{assets.length === 0 ? <p className="p-8 text-center text-xs text-[#909399]">{isChinese ? "这个文件夹还没有素材" : "No assets in this folder"}</p> : assets.map((asset) => <div key={asset.path} className="group flex items-center rounded-lg hover:bg-[#f5f7fa]"><button onDoubleClick={() => insertAsset(asset)} onClick={() => asset.kind === "directory" && void loadAssets(asset.path)} className="flex min-w-0 flex-1 items-center gap-3 px-3 py-2 text-left"><FolderOpen className="size-4 text-[#8b5cf6]" /><span className="min-w-0 flex-1 truncate text-xs">{asset.name}</span>{asset.kind === "file" && <Plus className="size-3.5" />}</button><button onClick={() => void renameAsset(asset)} aria-label={isChinese ? "重命名" : "Rename"} className="p-1.5 text-[#909399] opacity-0 group-hover:opacity-100"><Edit3 className="size-3.5" /></button><button onClick={() => void deleteAsset(asset)} aria-label={isChinese ? "删除" : "Delete"} className="mr-1 p-1.5 text-[#909399] opacity-0 hover:text-red-500 group-hover:opacity-100"><Trash2 className="size-3.5" /></button></div>)}</div></aside>}

      {leftPanel === "nodes" && selectedNode && rightPanel === "inspector" && (
        <aside className={`absolute bottom-[74px] z-30 w-72 overflow-hidden rounded-2xl border border-[#ebeef5] bg-white shadow-xl ${agentVisible ? "right-[450px]" : "right-[15px]"}`}>
          <div className="flex items-center justify-between border-b border-[#ebeef5] px-4 py-3">
            <span className="text-sm font-semibold">{isChinese ? "节点属性" : "Node properties"}</span>
            <button onClick={() => setSelectedId(null)}><X className="size-4 text-[#909399]" /></button>
          </div>
          <div className="max-h-[55vh] overflow-y-auto p-4">
            <label className="text-xs font-medium">
              {isChinese ? "名称" : "Label"}
              <input value={selectedNode.data.label} onChange={(event) => updateSelected({ label: event.target.value })} className="mt-2 w-full rounded-lg border border-[#dcdfe6] px-3 py-2 text-sm outline-none focus:border-[#8b5cf6]" />
            </label>
            <label className="mt-4 block text-xs font-medium">
              {selectedNode.data.kind.includes("Generation") ? (isChinese ? "提示词" : "Prompt") : (isChinese ? "内容" : "Content")}
              <textarea value={String(selectedNode.data.prompt || selectedNode.data.text || "")} onChange={(event) => updateSelected(selectedNode.data.kind.includes("Generation") ? { prompt: event.target.value } : { text: event.target.value })} className="mt-2 min-h-24 w-full resize-y rounded-lg border border-[#dcdfe6] px-3 py-2 text-sm outline-none focus:border-[#8b5cf6]" />
            </label>
            {["imageGeneration", "videoGeneration"].includes(selectedNode.data.kind) && (
              <div className="mt-3 space-y-3">
                <label className="block text-xs font-medium">
                  {isChinese ? "画面比例" : "Aspect ratio"}
                  <select value={String(selectedNode.data.ratio || studioSettings?.default_image_ratio || "16:9")} onChange={(event) => updateSelected({ ratio: event.target.value })} className="mt-1.5 w-full rounded-lg border border-[#dcdfe6] bg-white px-3 py-2 text-sm outline-none focus:border-[#8b5cf6]">
                    {["16:9", "9:16", "1:1", "4:3", "3:4"].map((ratio) => <option key={ratio} value={ratio}>{ratio}</option>)}
                  </select>
                </label>
                {selectedNode.data.kind === "videoGeneration" && (
                  <div className="space-y-3">
                    <label className="block text-xs font-medium">
                      {isChinese ? "时长（秒）" : "Duration (seconds)"}
                      <input type="number" min={1} max={60} value={Number(selectedNode.data.duration || studioSettings?.default_video_duration || 5)} onChange={(event) => updateSelected({ duration: Number(event.target.value) })} className="mt-1.5 w-full rounded-lg border border-[#dcdfe6] px-3 py-2 text-sm outline-none focus:border-[#8b5cf6]" />
                    </label>
                    <label className="block text-xs font-medium">
                      {isChinese ? "首帧（可选）" : "First frame (optional)"}
                      <select value={String(selectedNode.data.firstFramePath || "")} onChange={(event) => updateSelected({ firstFramePath: event.target.value })} className="mt-1.5 w-full rounded-lg border border-[#dcdfe6] bg-white px-2 py-2 text-xs outline-none focus:border-[#8b5cf6]"><option value="">{isChinese ? "无" : "None"}</option>{projectFiles.filter((asset) => asset.mime_type?.startsWith("image/")).map((asset) => <option key={asset.path} value={asset.path}>{asset.path}</option>)}</select>
                    </label>
                    <label className="block text-xs font-medium">
                      {isChinese ? "尾帧（可选）" : "Last frame (optional)"}
                      <select value={String(selectedNode.data.lastFramePath || "")} onChange={(event) => updateSelected({ lastFramePath: event.target.value })} className="mt-1.5 w-full rounded-lg border border-[#dcdfe6] bg-white px-2 py-2 text-xs outline-none focus:border-[#8b5cf6]"><option value="">{isChinese ? "无" : "None"}</option>{projectFiles.filter((asset) => asset.mime_type?.startsWith("image/")).map((asset) => <option key={asset.path} value={asset.path}>{asset.path}</option>)}</select>
                    </label>
                  </div>
                )}
                {selectedNode.data.status === "running" ? (
                  <div className="space-y-2">
                    <div className="h-1.5 overflow-hidden rounded-full bg-[#eeeaf7]"><div className="h-full rounded-full bg-[#8b5cf6] transition-[width]" style={{ width: `${Number(selectedNode.data.progress || 0)}%` }} /></div>
                    <p className="text-[11px] text-[#909399]">{String(selectedNode.data.statusMessage || (isChinese ? "生成中" : "Generating"))} · {Number(selectedNode.data.progress || 0)}%</p>
                    <button onClick={() => void cancelSelectedGeneration()} className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[#dcdfe6] px-3 py-2 text-sm text-[#606266]">{isChinese ? "取消生成" : "Cancel generation"}</button>
                  </div>
                ) : (
                  <button onClick={() => void generateSelected()} className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[#8b5cf6] px-3 py-2 text-sm font-medium text-white"><Play className="size-4" />{isChinese ? "生成" : "Generate"}</button>
                )}
                {selectedGenerations.length > 0 && <div><p className="mb-1.5 text-[11px] font-semibold text-[#909399]">{isChinese ? "生成历史" : "Generation history"}</p><div className="flex gap-2 overflow-x-auto pb-1">{selectedGenerations.map((generation) => <button key={generation.jobId} title={generation.prompt} onClick={() => updateSelected({ assetPath: generation.assetPath, previewUrl: videoStudioApi.assetUrl(projectId, generation.assetPath), mimeType: generation.mimeType })} className={`relative size-12 shrink-0 overflow-hidden rounded-lg border ${selectedNode.data.assetPath === generation.assetPath ? "border-[#8b5cf6]" : "border-[#dcdfe6]"}`}>{generation.mimeType.startsWith("image/") ? <img src={videoStudioApi.assetUrl(projectId, generation.assetPath)} alt="" className="size-full object-cover" /> : <Video className="m-auto size-4 text-[#8b5cf6]" />}</button>)}</div></div>}
              </div>
            )}
            {selectedNode.data.kind === "director3d" && <button onClick={() => setDirectorOpen(true)} className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[#8b5cf6] px-3 py-2 text-sm font-medium text-white"><Box className="size-4" />{isChinese ? "打开 3D 导演台" : "Open 3D director"}</button>}
            {generationError && <p className="mt-2 text-xs text-red-600">{generationError}</p>}
            <button onClick={removeSelected} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm text-red-600"><Trash2 className="size-4" />{isChinese ? "删除节点" : "Delete node"}</button>
          </div>
        </aside>
      )}

      {leftPanel === "nodes" && <div className="absolute bottom-[14px] left-[15px] z-20 flex h-12 items-center gap-1 rounded-2xl border border-[#ebeef5] bg-white px-2 shadow-sm">
        <button onClick={() => { setRightPanel("assets"); void loadAssets(); }} aria-label={isChinese ? "素材库" : "Assets"} className="rounded-lg p-2 text-[#606266] hover:bg-[#f5f1ff] hover:text-[#8b5cf6]"><FolderOpen className="size-[18px]" /></button>
        <button onClick={() => setNodeMenuVisible((value) => !value)} aria-label={isChinese ? "节点" : "Nodes"} className="rounded-lg p-2 text-[#606266] hover:bg-[#f5f1ff] hover:text-[#8b5cf6]"><Network className="size-[18px]" /></button>
        <button onClick={() => setShowMiniMap((value) => !value)} aria-label={isChinese ? "地图" : "Map"} className="rounded-lg p-2 text-[#606266] hover:bg-[#f5f1ff] hover:text-[#8b5cf6]"><MapIcon className="size-[18px]" /></button>
        <label className="cursor-pointer rounded-lg p-2 text-[#606266] hover:bg-[#f5f1ff] hover:text-[#8b5cf6]"><Paperclip className="size-[18px]" /><input type="file" className="sr-only" onChange={(event) => void upload(event)} /></label>
        <button onClick={() => addNode("audio")} aria-label={isChinese ? "音频" : "Audio"} className="rounded-lg p-2 text-[#8b5cf6] hover:bg-[#f5f1ff]"><Music2 className="size-[18px]" /></button>
        <button onClick={arrangeCanvas} aria-label={isChinese ? "自动整理画布" : "Auto-arrange canvas"} className="rounded-lg p-2 text-[#606266] hover:bg-[#f5f1ff]"><LayoutGrid className="size-[18px]" /></button>
        <button onClick={() => void flow.current?.fitView({ padding: 0.2, duration: 300 })} aria-label={isChinese ? "适应视图" : "Fit view"} className="rounded-lg p-2 text-[#606266] hover:bg-[#f5f1ff]"><Scan className="size-[18px]" /></button>
        <span className="px-2 text-sm text-[#606266]">{Math.round(viewport.zoom * 100)}%</span>
        <button onClick={() => setShowHelp(true)} aria-label={isChinese ? "帮助" : "Help"} className="rounded-lg p-2 text-[#606266] hover:bg-[#f5f1ff]"><HelpCircle className="size-[18px]" /></button>
      </div>}

      {leftPanel === "nodes" && <div className="absolute bottom-[14px] left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-full border border-[#ebeef5] bg-white p-1 shadow-sm"><button onClick={undo} className="rounded-full p-2 text-[#606266] hover:bg-[#f5f1ff]"><Undo2 className="size-4" /></button><button onClick={redo} className="rounded-full p-2 text-[#606266] hover:bg-[#f5f1ff]"><Redo2 className="size-4" /></button><button onClick={copySelection} className="rounded-full p-2 text-[#606266] hover:bg-[#f5f1ff]"><Copy className="size-4" /></button><button onClick={pasteSelection} className="rounded-full p-2 text-[#606266] hover:bg-[#f5f1ff]"><ClipboardPaste className="size-4" /></button><span className="mx-1 h-5 w-px bg-[#ebeef5]" /><button onClick={() => void exportVideo()} disabled={exporting} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-[#606266] hover:bg-[#f5f1ff]">{exporting ? <LoaderCircle className="size-3.5 animate-spin" /> : <Share className="size-3.5" />}{isChinese ? "导出" : "Export"}</button></div>}

      {saveState === "error" && <div className="absolute left-1/2 top-16 z-40 -translate-x-1/2 rounded-full bg-red-50 px-4 py-2 text-xs text-red-700">{isChinese ? "画布保存失败" : "Canvas save failed"}</div>}
      {exportResult && <div role="status" className="absolute bottom-20 left-1/2 z-50 flex max-w-lg -translate-x-1/2 items-center gap-3 rounded-lg border border-[#ebeef5] bg-white px-4 py-2.5 text-xs shadow-lg"><span>{exportResult}</span>{exportJobId && <button onClick={() => void cancelExport()} className="rounded-md border border-[#dcdfe6] px-2 py-1 text-[#606266]">{isChinese ? "取消" : "Cancel"}</button>}</div>}
      {showHelp && <div className="absolute inset-0 z-[70] flex items-center justify-center bg-[#182033]/25 p-6" onMouseDown={() => setShowHelp(false)}><section role="dialog" aria-modal="true" aria-label={isChinese ? "工作台帮助" : "Workspace help"} onMouseDown={(event) => event.stopPropagation()} className="w-full max-w-lg rounded-3xl border border-[#ebeef5] bg-white p-6 shadow-2xl"><div className="flex items-center justify-between"><h2 className="text-base font-semibold">{isChinese ? "工作台快捷指南" : "Workspace quick guide"}</h2><button onClick={() => setShowHelp(false)} className="rounded-lg p-2 text-[#909399] hover:bg-[#f5f7fa]"><X className="size-4" /></button></div><div className="mt-5 grid gap-3 text-sm leading-6 text-[#606266]"><p>{isChinese ? "从左下角添加节点或上传素材；双击素材可放入当前画布。" : "Add nodes or upload assets from the lower-left toolbar. Double-click an asset to place it on the current canvas."}</p><p>{isChinese ? "选择生成节点后，在属性面板设置提示词、比例与视频时长。生成任务会保存到项目中。" : "Select a generation node to set its prompt, ratio, and video duration. Generation jobs are saved with the project."}</p><p>{isChinese ? "⌘/Ctrl+C、⌘/Ctrl+V、⌘/Ctrl+Z 支持复制、粘贴与撤销；Delete 删除选中节点。" : "Use Cmd/Ctrl+C, Cmd/Ctrl+V, and Cmd/Ctrl+Z for copy, paste, and undo. Delete removes selected nodes."}</p><p>{isChinese ? "导出会按画布从上到下、从左到右的顺序组合素材。" : "Export assembles media from top to bottom, then left to right on the canvas."}</p></div></section></div>}
      <Director3DDialog
        open={directorOpen && selectedNode?.data.kind === "director3d"}
        isChinese={isChinese}
        scene={directorScene}
        anchors={directorAnchors}
        onClose={() => setDirectorOpen(false)}
        onSceneChange={(scene) => updateSelected({ scene })}
        onAnchorsChange={(cameraAnchors) => updateSelected({ cameraAnchors })}
        onGenerate={async (prompt) => (await videoStudioApi.generateDirectorPlan(projectId, prompt)).scene}
        onExport={async (blob) => {
          const file = new File([blob], `director-frame-${Date.now()}.png`, { type: "image/png" });
          const asset = await videoStudioApi.uploadAsset(projectId, file, "generated");
          addNode("image", isChinese ? "导演关键帧" : "Director keyframe", { assetPath: asset.path, previewUrl: videoStudioApi.assetUrl(projectId, asset.path), mimeType: asset.mime_type || "image/png", status: "ready" });
          setProjectFiles((items) => [asset, ...items.filter((item) => item.path !== asset.path)]);
        }}
      />
      <StudioSettingsDialog open={showSettings} onClose={() => setShowSettings(false)} isChinese={isChinese} />
    </main>
  );

}
