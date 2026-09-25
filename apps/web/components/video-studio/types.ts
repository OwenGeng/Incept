import type { Edge, Node } from "@xyflow/react";

export type StudioLanguage = "zh-CN" | "en-US";

export type ProjectSummary = {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  node_count: number;
  thumbnail_url: string | null;
};

export type VideoNodeData = {
  label: string;
  kind: string;
  text?: string;
  prompt?: string;
  assetPath?: string;
  previewUrl?: string;
  mimeType?: string;
  status?: "idle" | "running" | "ready" | "error";
  [key: string]: unknown;
};

export type StudioNode = Node<VideoNodeData>;
export type StudioEdge = Edge;

export type CanvasDocument = {
  version: number;
  nodes: Array<{
    id: string;
    type: string;
    position: { x: number; y: number };
    data: VideoNodeData;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    source_handle?: string | null;
    target_handle?: string | null;
  }>;
  viewport: { x: number; y: number; zoom: number };
  updated_at: string;
};

export type CanvasSummary = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

export type ProjectDetail = ProjectSummary & {
  canvas: CanvasDocument;
  canvases: CanvasSummary[];
  active_canvas_id: string;
};

export type AssetEntry = {
  path: string;
  name: string;
  kind: "file" | "directory";
  size: number;
  modified_at: string | null;
  mime_type: string | null;
};

export type StudioSettings = {
  language: StudioLanguage;
  theme: "light";
  default_image_ratio: string;
  default_video_duration: number;
  agent_system_prompt: string;
  default_agent: string;
  default_text_model: string;
  privacy_mode: "private";
};

export type ProjectDocument = { content: string; updated_at: string };

export type SkillDefinition = {
  id: string;
  name: string;
  description: string;
  instructions: string;
  enabled: boolean;
  builtin: boolean;
  order: number;
};

export type ExtensionDefinition = {
  id: string;
  category: "node" | "tool" | "agent";
  name: string;
  description: string;
  enabled: boolean;
  builtin: boolean;
  config: Record<string, unknown>;
};

export type CatalogSnapshot = {
  skills: SkillDefinition[];
  extensions: ExtensionDefinition[];
};

export type ExportJob = {
  id: string;
  project_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  message: string;
  result: { asset_path: string; mime_type: string; size: number } | null;
};

export type MediaJob = {
  id: string;
  project_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  message: string;
  provider: string;
  model: string;
  location: string;
  request: {
    idempotency_key?: string | null;
    media_type: "image" | "video";
    prompt: string;
    ratio?: string | null;
    size?: string | null;
    duration?: number | null;
    first_frame_path?: string | null;
    last_frame_path?: string | null;
  };
  result_asset_path: string | null;
  result_mime_type: string | null;
  result_size: number | null;
  created_at: string;
  updated_at: string;
};

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type AgentConversation = {
  id: string;
  name: string;
  messages: AgentMessage[];
  created_at: string;
  updated_at: string;
};

export type AgentEvent =
  | { type: "status"; status: string }
  | { type: "canvas"; canvas: CanvasDocument }
  | { type: "message"; conversation_id: string; message: string }
  | { type: "error"; message: string }
  | { type: "done" };

export type DirectorVector = { x: number; y: number; z: number };
export type DirectorObject = {
  id: string;
  name: string;
  shape: "cube" | "sphere" | "cylinder" | "mannequin";
  position: DirectorVector;
  scale: DirectorVector;
  color: string;
};
export type DirectorCamera = {
  position: DirectorVector;
  target: DirectorVector;
  focal_length: number;
};
export type DirectorScene = {
  objects: DirectorObject[];
  camera: DirectorCamera;
  background: string;
};
export type DirectorAnchor = {
  id: string;
  name: string;
  camera: DirectorCamera;
};

export type ProductionTake = {
  id: string;
  asset_path: string;
  source_job_id?: string | null;
  label: string;
  created_at: string;
};
export type ProductionKeyframe = {
  id: string;
  asset_path: string;
  source_job_id?: string | null;
  label: string;
  prompt: string;
  status: "draft" | "approved" | "rejected";
  created_at: string;
};
export type ProductionShot = {
  id: string;
  title: string;
  purpose: string;
  duration: number;
  status: "draft" | "approved" | "changes_requested";
  notes: string;
  keyframe_prompt: string;
  video_prompt: string;
  camera: string;
  continuity: string;
  audio_cue: string;
  keyframes: ProductionKeyframe[];
  selected_keyframe_id: string | null;
  takes: ProductionTake[];
  selected_take_id: string | null;
  active_generation_job_id: string | null;
};
export type TimelineClip = {
  shot_id: string;
  duration: number;
  transition: "cut" | "crossfade";
  included: boolean;
};
export type ProductionState = {
  revision: number;
  script_locked: boolean;
  script_revision: number;
  script_revisions: Array<{ id: string; revision: number; content: string; created_at: string }>;
  shots: ProductionShot[];
  timeline: TimelineClip[];
  timeline_revisions: Array<{ id: string; revision: number; label: string; clips: TimelineClip[]; created_at: string }>;
  qa: { status: "not_run" | "pass" | "warning" | "blocked"; issues: string[]; checked_at: string | null };
  deliveries: Array<{ id: string; asset_path: string; mime_type: string; size: number; sha256: string; timeline_revision: number; created_at: string }>;
  audit_events: Array<{ id: string; kind: string; detail: string; created_at: string }>;
  updated_at: string;
};
