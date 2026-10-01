export type LinglongLabRole = "user" | "manager" | "admin";

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

export type GenerationMode = "free_create" | "style_match" | "theme_create" | "resize" | "remediation" | "video";
export type ThemeCreateMode = "style_modify" | "style_transfer";
export type ThemeCreatePresetVisibility = "private" | "team" | "global";
export type VideoGenerationMode =
  | "image_to_video"
  | "playable_to_video"
  | "competitor_style_transfer"
  | "video_to_playable"
  | "first_last_frame"
  | "extend_video"
  | "reference_character"
  | "prompt_assist"
  | "multi_shot_storyboard"
  | "video_remediation"
  | "synthetic_recast";

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
  messages?: ThreadMessageSummary[];
  createdAt: string;
  updatedAt: string;
}

export interface ThreadMessageSummary {
  role: "user" | "assistant";
  text: string;
  assetIds: string[];
  jobId?: string;
  timestamp: string;
}

export interface LinglongLabUser {
  id: string;
  name: string;
  email: string;
  role: LinglongLabRole;
  team: string;
  avatarUrl?: string;
}

export interface ProviderConfig {
  defaultImageProvider: string;
  openaiImageModel: string;
  vertexImagenModel: string;
  vertexVeoFastModel?: string;
  vertexVeoModel?: string;
  vertexAiEnabled: boolean;
  gcpProjectId?: string;
  gcpLocation: string;
  assetBucket: string;
  maxImageVariants: number;
  maxOutputSizes: number;
}

export interface VideoBudgetStatus {
  budgetUsd: number;
  pricingEnabled: boolean;
  currentEstimatedSpendUsd: number;
  remainingEstimatedSpendUsd: number;
  requestEstimatedCostUsd: number;
  projectedTotalUsd: number;
  wouldExceedBudget: boolean;
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
  createdAt?: string;
}

export interface AssetSummary {
  id: string;
  title: string;
  type: "image" | "video" | "audio" | "gif" | "report" | "playable";
  url: string;
  gcsUri?: string;
  provider: string;
  model: string;
  workspaceId: string;
  jobId?: string;
  promptHash?: string;
  createdAt: string;
  createdBy?: string;
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
  resize_include_gacha_disclosure?: boolean;
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
  remediation_analysis?: RemediationAnalysisResult[];
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

export interface VideoGenerationRequest {
  workspace_id: string;
  prompt: string;
  provider: "gemini";
  model: string;
  created_by: string;
  thread_id?: string;
  source_asset_id?: string;
  end_frame_asset_id?: string;
  reference_asset_ids?: string[];
  video_generation_mode: VideoGenerationMode;
  aspect_ratio: "16:9" | "9:16";
  duration_seconds: 4 | 6 | 8 | 15 | 30 | 60;
  resolution?: "720p" | "1080p";
  variants: 1 | 2;
  include_audio?: boolean;
  camera_preset?: string;
  enhance_with_veo_fast?: boolean;
  plan_id?: string;
}

export interface VideoGenerationPlan {
  plan_id: string;
  workspace_id: string;
  thread_id: string;
  created_by: string;
  mode: VideoGenerationMode;
  source_asset_id: string;
  reference_asset_ids: string[];
  status: "draft" | "confirmed" | "generated";
  objective: string;
  summary: string;
  keep: string[];
  change: string[];
  avoid: string[];
  recommended_settings: Record<string, string>;
  generation_prompt: string;
  beats: VideoGenerationBeat[];
  questions: string[];
  interaction_concept: Record<string, unknown>;
  execution_intent: "chat" | "generate";
  conversation: VideoPlanConversationMessage[];
  created_at: string;
  updated_at: string;
}

export interface VideoGenerationBeat {
  id: string;
  title: string;
  purpose: string;
  start_state: string;
  end_state: string;
  duration_seconds: number;
  veo_brief: string;
}

export interface VideoPlanConversationMessage {
  role: "user" | "assistant";
  text: string;
  created_at: string;
}

export interface VideoPlanRequest {
  workspace_id: string;
  prompt: string;
  created_by: string;
  thread_id?: string;
  source_asset_id: string;
  reference_asset_ids?: string[];
  video_generation_mode: VideoGenerationMode;
  action: "analyze" | "refine" | "confirm";
  plan_id?: string;
  generation_prompt_override?: string;
  aspect_ratio: "16:9" | "9:16";
  duration_seconds: 4 | 6 | 8 | 15 | 30 | 60;
  resolution: "720p" | "1080p";
  variants: 1 | 2;
  include_audio: boolean;
}

export interface VideoPlanResponse {
  plan: VideoGenerationPlan;
  report_asset_id?: string;
}

export interface VideoGenerationResponse {
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
  created_at: string;
  updated_at: string;
}

export interface RemediationViolation {
  category: string;
  severity: string;
  target: string;
  reason: string;
  fix_instruction: string;
}

export interface RemediationAnalysisResult {
  asset_id: string;
  asset_title: string;
  overall_risk: string;
  summary: string;
  preserve_instructions: string[];
  violations: RemediationViolation[];
  remediation_prompt: string;
}

export interface RemediationAnalysisRequest {
  workspace_id: string;
  source_asset_ids: string[];
  prompt?: string;
  created_by: string;
}

export interface RemediationAnalysisResponse {
  results: RemediationAnalysisResult[];
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
