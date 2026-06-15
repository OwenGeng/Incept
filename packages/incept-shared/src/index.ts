export type InceptRole = "user" | "manager" | "admin";

export type JobStatus = "queued" | "running" | "completed" | "failed" | "pending" | "needs_clarification";

export type ToolCategory =
  | "image_generation"
  | "video_generation"
  | "gif_generation"
  | "performance_analysis"
  | "retrieval";

export type AssetRole =
  | "upload"
  | "working"
  | "reference_ad"
  | "client_character"
  | "client_logo"
  | "client_product"
  | "client_background"
  | "brand_element"
  | "generated";

export type GenerationMode = "free_create" | "style_match" | "theme_create" | "resize";
export type ThemeCreateMode = "style_modify" | "style_transfer" | "asset_text_replace";
export type ThemeCreatePresetVisibility = "private" | "team" | "global";

export interface CreativeThreadSummary {
  id: string;
  workspaceId: string;
  title: string;
  generationMode: GenerationMode;
  createdBy?: string;
  originAssetId?: string;
  coverAssetId?: string;
  latestAssetId?: string;
  latestJobId?: string;
  previewUrl?: string;
  assetCount: number;
  jobCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface InceptUser {
  id: string;
  name: string;
  email: string;
  role: InceptRole;
  team: string;
  avatarUrl?: string;
}

export interface ProviderConfig {
  defaultImageProvider: string;
  openaiImageModel: string;
  vertexImagenModel: string;
  vertexAiEnabled: boolean;
  gcpProjectId?: string;
  gcpLocation: string;
  assetBucket: string;
  maxImageVariants: number;
  maxOutputSizes: number;
}

export interface WorkspaceSummary {
  id: string;
  title: string;
  description: string;
  updatedAt: string;
  thumbnailUrl: string;
  owner: string;
  status: JobStatus;
}

export interface ToolDefinition {
  id: string;
  name: string;
  category: ToolCategory;
  status: "enabled" | "mock" | "disabled";
  provider: "openai" | "gemini" | "bigquery" | "internal" | "mock";
  owner: string;
  description: string;
}

export interface JobSummary {
  id: string;
  jobId?: string;
  title: string;
  toolId: string;
  status: JobStatus;
  progress: number;
  eta: string;
  lineageKey?: string;
  threadId?: string;
  sourceAssetId?: string;
  message?: string;
  clarificationQuestion?: string;
  clarificationReason?: string;
  clarificationOptions?: Array<{ id: string; label: string; note?: string }>;
  clarificationManifest?: Record<string, unknown>;
}

export interface AssetSummary {
  id: string;
  title: string;
  type: "image" | "video" | "gif" | "report";
  url: string;
  gcsUri?: string;
  provider: string;
  model: string;
  workspaceId: string;
  jobId?: string;
  promptHash?: string;
  createdAt: string;
  width?: number;
  height?: number;
  theme?: string;
  assetRole?: AssetRole;
  analysis?: Record<string, unknown>;
  threadId?: string;
  parentAssetId?: string;
  rootAssetId?: string;
}

export interface ImageGenerationRequest {
  workspace_id: string;
  prompt: string;
  provider: "openai" | "gemini";
  model: string;
  variants: number;
  aspect_ratio: string;
  created_by: string;
  source_asset_ids: string[];
  theme?: string;
  output_sizes?: string[];
  output_format?: "image" | "gif" | "image_and_gif";
  reference_asset_ids?: string[];
  preserve_layout?: boolean;
  use_reference_style?: boolean;
  client_asset_ids?: string[];
  session_id?: string;
  thread_id?: string;
  source_asset_id?: string;
  generation_mode?: GenerationMode;
  include_gif?: boolean;
  clarification_note?: string;
  resize_prompt_overrides?: Record<string, string>;
  resize_negative_prompt_override?: string;
  theme_create_mode?: ThemeCreateMode;
  theme_create_style_name?: string;
  theme_create_style_details?: string;
  theme_create_logo_position?: string;
  theme_create_element_position?: string;
  theme_create_old_text?: string;
  theme_create_new_text?: string;
  theme_create_font_style?: string;
}

export interface ImageGenerationResponse {
  job_id: string;
  workspace_id: string;
  status: JobStatus;
  progress: number;
  lineage_key: string;
  message: string;
  tool_id: string;
  title: string;
  output_asset_ids: string[];
  thread_id?: string;
  source_asset_id?: string;
  clarification_question?: string;
  clarification_reason?: string;
  clarification_options?: Array<{ id: string; label: string; note?: string }>;
  clarification_manifest?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface UsageEvent {
  id: string;
  jobId: string;
  workspaceId: string;
  userId: string;
  userEmail: string;
  provider: string;
  model: string;
  operation: string;
  promptHash: string;
  variants: number;
  outputSizeCount: number;
  outputFormat: string;
  estimatedProviderGenerations: number;
  outputAssetCount: number;
  estimatedCostUsd: number;
  actualCostUsd?: number;
  inputTokens?: number;
  outputTokens?: number;
  createdAt: string;
}

export interface ThemeCreateStyleReportSummary {
  id: string;
  workspaceId: string;
  title: string;
  summary: string;
  themeCreateMode: ThemeCreateMode;
  promptTemplate: string;
  sourceAssetId?: string;
  referenceAssetIds: string[];
  sourceJobId?: string;
  recommendedPresetName?: string;
  visualDna: string[];
  compositionRules: string[];
  doNotCopy: string[];
  tags: string[];
  taxonomy: Record<string, string[]>;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface ThemeCreatePresetSummary {
  id: string;
  workspaceId?: string;
  name: string;
  description: string;
  themeCreateMode: ThemeCreateMode;
  visibility: ThemeCreatePresetVisibility;
  promptTemplate: string;
  styleName?: string;
  styleDetails?: string;
  tags: string[];
  taxonomy: Record<string, string[]>;
  sourceReportId?: string;
  sourceJobId?: string;
  sourceAssetId?: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  usageCount: number;
  isOfficial: boolean;
}
