import type {
  AgentConversation,
  AgentEvent,
  AssetEntry,
  CanvasSummary,
  CanvasDocument,
  ProjectDetail,
  ProjectSummary,
  StudioSettings,
  CatalogSnapshot,
  ExportJob,
  MediaJob,
  ProjectDocument,
  DirectorScene,
  ProductionState,
} from "./types";

const BASE = "/api/incept/video-studio";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "content-type": "application/json" }),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const videoStudioApi = {
  listProjects: () => request<ProjectSummary[]>("/projects"),
  createProject: (name: string, description = "") => request<ProjectDetail>("/projects", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  }),
  importProject: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<ProjectDetail>("/projects/import", { method: "POST", body });
  },
  projectArchiveUrl: (projectId: string) => `${BASE}/projects/${projectId}/archive`,
  getProject: (projectId: string) => request<ProjectDetail>(`/projects/${projectId}`),
  updateProject: (projectId: string, body: { name?: string; description?: string }) =>
    request<ProjectDetail>(`/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteProject: (projectId: string) => request<void>(`/projects/${projectId}`, { method: "DELETE" }),
  saveCanvas: (projectId: string, canvas: Omit<CanvasDocument, "updated_at">) =>
    request<CanvasDocument>(`/projects/${projectId}/canvas`, {
      method: "PUT",
      body: JSON.stringify(canvas),
    }),
  listCanvases: (projectId: string) => request<CanvasSummary[]>(`/projects/${projectId}/canvases`),
  createCanvas: (projectId: string, name: string) => request<ProjectDetail>(`/projects/${projectId}/canvases`, {
    method: "POST",
    body: JSON.stringify({ name }),
  }),
  getCanvas: (projectId: string, canvasId: string) =>
    request<CanvasDocument>(`/projects/${projectId}/canvases/${canvasId}`),
  saveProjectCanvas: (projectId: string, canvasId: string, canvas: Omit<CanvasDocument, "updated_at">) =>
    request<CanvasDocument>(`/projects/${projectId}/canvases/${canvasId}`, {
      method: "PUT",
      body: JSON.stringify(canvas),
    }),
  renameCanvas: (projectId: string, canvasId: string, name: string) =>
    request<CanvasSummary[]>(`/projects/${projectId}/canvases/${canvasId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  activateCanvas: (projectId: string, canvasId: string) =>
    request<ProjectDetail>(`/projects/${projectId}/canvases/${canvasId}/activate`, { method: "POST" }),
  deleteCanvas: (projectId: string, canvasId: string) =>
    request<ProjectDetail>(`/projects/${projectId}/canvases/${canvasId}`, { method: "DELETE" }),
  listAssets: (projectId: string, path = "") =>
    request<AssetEntry[]>(`/projects/${projectId}/assets?path=${encodeURIComponent(path)}`),
  uploadAsset: (projectId: string, file: File, path = "") => {
    const body = new FormData();
    body.append("file", file);
    return request<AssetEntry>(
      `/projects/${projectId}/assets/upload?path=${encodeURIComponent(path)}`,
      { method: "POST", body },
    );
  },
  deleteAsset: (projectId: string, path: string) =>
    request<void>(`/projects/${projectId}/assets?path=${encodeURIComponent(path)}`, { method: "DELETE" }),
  createAssetDirectory: (projectId: string, path: string) =>
    request<{ path: string }>(`/projects/${projectId}/assets/directory`, {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  renameAsset: (projectId: string, path: string, target: string) =>
    request<{ path: string }>(`/projects/${projectId}/assets/rename`, {
      method: "POST",
      body: JSON.stringify({ path, target }),
    }),
  assetUrl: (projectId: string, path: string) =>
    `${BASE}/projects/${projectId}/assets/file?path=${encodeURIComponent(path)}`,
  getSettings: () => request<StudioSettings>("/settings"),
  saveSettings: (settings: StudioSettings) => request<StudioSettings>("/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  }),
  getDocument: (projectId: string) => request<ProjectDocument>(`/projects/${projectId}/document`),
  saveDocument: (projectId: string, content: string) => request<ProjectDocument>(`/projects/${projectId}/document`, {
    method: "PUT",
    body: JSON.stringify({ content }),
  }),
  getCatalog: () => request<CatalogSnapshot>("/catalog"),
  saveCatalog: (catalog: CatalogSnapshot) => request<CatalogSnapshot>("/catalog", {
    method: "PUT",
    body: JSON.stringify(catalog),
  }),
  listConversations: (projectId: string) =>
    request<AgentConversation[]>(`/projects/${projectId}/conversations`),
  renameConversation: (projectId: string, conversationId: string, name: string) =>
    request<AgentConversation>(`/projects/${projectId}/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteConversation: (projectId: string, conversationId: string) =>
    request<void>(`/projects/${projectId}/conversations/${conversationId}`, { method: "DELETE" }),
  runAgent: async (
    projectId: string,
    prompt: string,
    conversationId: string | null,
    onEvent: (event: AgentEvent) => void,
    options?: { agentId?: string; assetPaths?: string[] },
  ) => {
    const response = await fetch(`${BASE}/projects/${projectId}/agent`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        prompt,
        conversation_id: conversationId,
        agent_id: options?.agentId,
        asset_paths: options?.assetPaths || [],
      }),
    });
    if (!response.ok || !response.body) throw new Error(`Agent request failed (${response.status})`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffered = "";
    while (true) {
      const { value, done } = await reader.read();
      buffered += decoder.decode(value, { stream: !done });
      const lines = buffered.split("\n");
      buffered = lines.pop() || "";
      for (const line of lines) {
        if (line.trim()) onEvent(JSON.parse(line) as AgentEvent);
      }
      if (done) break;
    }
    if (buffered.trim()) onEvent(JSON.parse(buffered) as AgentEvent);
  },
  generateMedia: async (body: {
    media_type: "image" | "video";
    prompt: string;
    ratio?: string;
    duration?: number;
  }) => {
    const response = await fetch("/api/incept/api/video-runtime/media/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(payload?.detail || `Generation failed (${response.status})`);
    }
    return response.json() as Promise<{ media_type: "image" | "video"; mime_type: string; data: string }>;
  },
  createMediaJob: (
    projectId: string,
    body: {
      media_type: "image" | "video";
      idempotency_key?: string;
      prompt: string;
      ratio?: string;
      size?: string;
      duration?: number;
      first_frame_path?: string;
      last_frame_path?: string;
    },
  ) => request<MediaJob>(`/projects/${projectId}/media-jobs`, {
    method: "POST",
    body: JSON.stringify(body),
  }),
  getMediaJob: (projectId: string, jobId: string) =>
    request<MediaJob>(`/projects/${projectId}/media-jobs/${jobId}`),
  cancelMediaJob: (projectId: string, jobId: string) =>
    request<MediaJob>(`/projects/${projectId}/media-jobs/${jobId}/cancel`, { method: "POST" }),
  generateDirectorPlan: (projectId: string, prompt: string) =>
    request<{ scene: DirectorScene }>(`/projects/${projectId}/director/plan`, {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  getProductionState: (projectId: string) =>
    request<ProductionState>(`/projects/${projectId}/production`),
  saveProductionState: (projectId: string, state: ProductionState) =>
    request<ProductionState>(`/projects/${projectId}/production`, {
      method: "PUT",
      body: JSON.stringify(state),
    }),
  lockProductionScript: (projectId: string, content: string) =>
    request<ProductionState>(`/projects/${projectId}/production/script/lock`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  unlockProductionScript: (projectId: string) =>
    request<ProductionState>(`/projects/${projectId}/production/script/unlock`, { method: "POST" }),
  commitTimeline: (projectId: string, label: string) =>
    request<ProductionState>(`/projects/${projectId}/production/timeline/commit`, {
      method: "POST",
      body: JSON.stringify({ label }),
    }),
  runProductionQa: (projectId: string) =>
    request<ProductionState>(`/projects/${projectId}/production/qa`, { method: "POST" }),
  recordDelivery: (projectId: string, assetPath: string) =>
    request<ProductionState>(`/projects/${projectId}/production/deliveries`, {
      method: "POST",
      body: JSON.stringify({ asset_path: assetPath }),
    }),
  createExport: (
    projectId: string,
    body: {
      name: string;
      idempotency_key?: string;
      clips: Array<{ asset_path: string; duration?: number; transition?: "cut" | "crossfade" }>;
      soundtrack_path?: string;
      width?: number;
      height?: number;
      fps?: number;
    },
  ) => request<{ asset_path: string; mime_type: string; size: number }>(
    `/projects/${projectId}/exports`,
    { method: "POST", body: JSON.stringify(body) },
  ),
  createExportJob: (
    projectId: string,
    body: {
      name: string;
      idempotency_key?: string;
      clips: Array<{ asset_path: string; duration?: number; transition?: "cut" | "crossfade" }>;
      soundtrack_path?: string;
      width?: number;
      height?: number;
      fps?: number;
    },
  ) => request<ExportJob>(`/projects/${projectId}/export-jobs`, {
    method: "POST",
    body: JSON.stringify(body),
  }),
  getExportJob: (projectId: string, jobId: string) =>
    request<ExportJob>(`/projects/${projectId}/export-jobs/${jobId}`),
  cancelExportJob: (projectId: string, jobId: string) =>
    request<ExportJob>(`/projects/${projectId}/export-jobs/${jobId}/cancel`, { method: "POST" }),
};
