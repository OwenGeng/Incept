import type {
  AssetSummary,
  CreativeThreadSummary,
  ImageGenerationRequest,
  ImageGenerationResponse,
  InceptUser,
  JobSummary,
  ProviderConfig,
  ThemeCreatePresetSummary,
  ThemeCreateStyleReportSummary,
  UsageEvent,
  WorkspaceSummary
} from "@incept/shared";

/**
 * All incept API calls go through the Next.js proxy at /api/incept/[...path].
 * The proxy enforces auth (NextAuth session) and forwards user identity to
 * incept-api via trusted internal headers.  No env var needed — works in both
 * local dev (relative URL) and production (same domain as the portal).
 */
const API_BASE_URL = "/api/incept";

/** Resolve preview URLs that come back as relative paths from the local API. */
export function resolveAssetUrl(url: string): string {
  if (!url || url.startsWith("data:") || url.startsWith("http")) return url;
  if (url.startsWith("/") && API_BASE_URL) return `${API_BASE_URL}${url}`;
  return url;
}

export async function createImageGenerationJob(
  request: ImageGenerationRequest
): Promise<ImageGenerationResponse> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is required to run real image generation jobs.");
  }

  const response = await fetch(`${API_BASE_URL}/workflows/image-generation`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(request)
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    let msg = `Image generation failed (${response.status})`;
    try {
      const parsed = JSON.parse(detail) as { detail?: string | unknown[] };
      if (typeof parsed.detail === "string") msg = parsed.detail;
      else if (Array.isArray(parsed.detail) && parsed.detail.length > 0)
        msg = JSON.stringify(parsed.detail[0]);
    } catch { if (detail) msg += `: ${detail.slice(0, 200)}`; }
    throw new Error(msg);
  }

  return response.json() as Promise<ImageGenerationResponse>;
}

function sanitizeDownloadFilename(name: string): string {
  const cleaned = name.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^_+|_+$/g, "");
  return cleaned || "incept_asset";
}

export async function downloadAssetFile(
  asset: Pick<AssetSummary, "url" | "title" | "type" | "width" | "height">
): Promise<void> {
  const response = await fetch(asset.url);
  if (!response.ok) {
    throw new Error(`Asset download failed (${response.status})`);
  }

  const blob = await response.blob();
  const fallbackExt = asset.type === "gif" ? "gif" : "png";
  const sizeSuffix =
    asset.width && asset.height ? `_${asset.width}x${asset.height}` : "";
  const filename = `${sanitizeDownloadFilename(asset.title)}${sizeSuffix}.${fallbackExt}`;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function fetchJson<T>(path: string): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is required.");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json"
    }
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${path} ${response.status}`);
  }

  return response.json() as Promise<T>;
}

interface ApiAsset {
  id: string;
  title: string;
  type: "image" | "video" | "gif" | "report";
  gcs_uri: string;
  preview_url: string;
  provider: string;
  model: string;
  workspace_id: string;
  job_id: string;
  prompt_hash: string;
  created_at: string;
  width?: number | null;
  height?: number | null;
  theme?: string | null;
  asset_role?: import("@incept/shared").AssetRole | null;
  analysis?: Record<string, unknown> | null;
  thread_id?: string | null;
  parent_asset_id?: string | null;
  root_asset_id?: string | null;
}

interface ApiJob {
  job_id: string;
  title: string;
  tool_id: string;
  status: JobSummary["status"];
  progress: number;
  lineage_key?: string;
  thread_id?: string | null;
  source_asset_id?: string | null;
  message?: string;
}

interface ApiThread {
  thread_id: string;
  workspace_id: string;
  title: string;
  generation_mode: import("@incept/shared").GenerationMode;
  created_by?: string;
  origin_asset_id?: string | null;
  cover_asset_id?: string | null;
  latest_asset_id?: string | null;
  latest_job_id?: string | null;
  preview_url?: string | null;
  asset_count?: number;
  job_count?: number;
  created_at: string;
  updated_at: string;
}

interface ApiWorkspace {
  id: string;
  title: string;
  description: string;
  updated_at: string;
  owner_user_id: string;
  team: string;
  status: WorkspaceSummary["status"];
}

export async function listAssets(workspaceId?: string): Promise<AssetSummary[]> {
  const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  if (!API_BASE_URL) {
    return [];
  }
  const assets = await fetchJson<ApiAsset[]>(`/assets${query}`);
  return assets.map((asset) => ({
    id: asset.id,
    title: asset.title,
    type: asset.type,
    url: resolveAssetUrl(asset.preview_url),
    gcsUri: asset.gcs_uri,
    provider: asset.provider,
    model: asset.model,
    workspaceId: asset.workspace_id,
    jobId: asset.job_id,
    promptHash: asset.prompt_hash,
    createdAt: asset.created_at,
    width: asset.width ?? undefined,
    height: asset.height ?? undefined,
    theme: asset.theme ?? undefined,
    assetRole: asset.asset_role ?? undefined,
    analysis: asset.analysis ?? undefined,
    threadId: asset.thread_id ?? undefined,
    parentAssetId: asset.parent_asset_id ?? undefined,
    rootAssetId: asset.root_asset_id ?? undefined,
  }));
}

export async function listJobs(): Promise<JobSummary[]> {
  if (!API_BASE_URL) {
    return [];
  }
  const jobs = await fetchJson<ApiJob[]>("/jobs");
  return jobs.map((job) => ({
    id: job.job_id,
    jobId: job.job_id,
    title: job.title,
    toolId: job.tool_id,
    status: job.status,
    progress: job.progress,
    eta: job.status === "completed" ? "Completed" : job.status === "failed" ? "Failed" : "Running",
    lineageKey: job.lineage_key,
    threadId: job.thread_id ?? undefined,
    sourceAssetId: job.source_asset_id ?? undefined,
    message: job.message ?? undefined,
  }));
}

export async function listThreads(workspaceId?: string): Promise<CreativeThreadSummary[]> {
  const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  if (!API_BASE_URL) {
    return [];
  }
  const threads = await fetchJson<ApiThread[]>(`/threads${query}`);
  return threads.map((thread) => ({
    id: thread.thread_id,
    workspaceId: thread.workspace_id,
    title: thread.title,
    generationMode: thread.generation_mode,
    createdBy: thread.created_by ?? undefined,
    originAssetId: thread.origin_asset_id ?? undefined,
    coverAssetId: thread.cover_asset_id ?? undefined,
    latestAssetId: thread.latest_asset_id ?? undefined,
    latestJobId: thread.latest_job_id ?? undefined,
    previewUrl: thread.preview_url ? resolveAssetUrl(thread.preview_url) : undefined,
    assetCount: thread.asset_count ?? 0,
    jobCount: thread.job_count ?? 0,
    createdAt: thread.created_at,
    updatedAt: thread.updated_at,
  }));
}

export async function listWorkspaces(): Promise<WorkspaceSummary[]> {
  if (!API_BASE_URL) {
    return [];
  }
  const workspaces = await fetchJson<ApiWorkspace[]>("/workspaces");
  return workspaces.map((workspace) => ({
    id: workspace.id,
    title: workspace.title,
    description: workspace.description,
    updatedAt: workspace.updated_at,
    thumbnailUrl: "",
    owner: workspace.owner_user_id,
    status: workspace.status
  }));
}

interface ApiProviderConfig {
  default_image_provider: string;
  openai_image_model: string;
  vertex_imagen_model: string;
  vertex_ai_enabled: boolean;
  gcp_project_id?: string | null;
  gcp_location: string;
  asset_bucket: string;
  max_image_variants: number;
  max_output_sizes: number;
}

interface ApiUsageEvent {
  id: string;
  job_id: string;
  workspace_id: string;
  user_id: string;
  user_email: string;
  provider: string;
  model: string;
  operation: string;
  prompt_hash: string;
  variants: number;
  output_size_count: number;
  output_format: string;
  estimated_provider_generations: number;
  output_asset_count: number;
  estimated_cost_usd: number;
  actual_cost_usd?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  created_at: string;
}

interface ApiThemeCreateStyleReport {
  report_id: string;
  workspace_id: string;
  title: string;
  summary: string;
  theme_create_mode: import("@incept/shared").ThemeCreateMode;
  prompt_template: string;
  source_asset_id?: string | null;
  reference_asset_ids: string[];
  source_job_id?: string | null;
  recommended_preset_name?: string | null;
  visual_dna: string[];
  composition_rules: string[];
  do_not_copy: string[];
  tags: string[];
  taxonomy: Record<string, string[]>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

interface ApiThemeCreatePreset {
  preset_id: string;
  workspace_id?: string | null;
  name: string;
  description: string;
  theme_create_mode: import("@incept/shared").ThemeCreateMode;
  visibility: import("@incept/shared").ThemeCreatePresetVisibility;
  prompt_template: string;
  style_name?: string | null;
  style_details?: string | null;
  tags: string[];
  taxonomy: Record<string, string[]>;
  source_report_id?: string | null;
  source_job_id?: string | null;
  source_asset_id?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  usage_count: number;
  is_official: boolean;
}

export async function getCurrentUser(): Promise<InceptUser | null> {
  if (!API_BASE_URL) {
    return null;
  }
  return fetchJson<InceptUser>("/me");
}

export async function getProviderConfig(): Promise<ProviderConfig | null> {
  if (!API_BASE_URL) {
    return null;
  }
  const config = await fetchJson<ApiProviderConfig>("/provider-config");
  return {
    defaultImageProvider: config.default_image_provider,
    openaiImageModel: config.openai_image_model,
    vertexImagenModel: config.vertex_imagen_model,
    vertexAiEnabled: config.vertex_ai_enabled,
    gcpProjectId: config.gcp_project_id ?? undefined,
    gcpLocation: config.gcp_location,
    assetBucket: config.asset_bucket,
    maxImageVariants: config.max_image_variants,
    maxOutputSizes: config.max_output_sizes
  };
}

export async function getJob(jobId: string): Promise<JobSummary | null> {
  if (!API_BASE_URL) return null;
  try {
    const job = await fetchJson<ApiJob>(`/jobs/${encodeURIComponent(jobId)}`);
    return {
      id: job.job_id,
      jobId: job.job_id,
      title: job.title,
      toolId: job.tool_id,
      status: job.status,
      progress: job.progress,
      eta: job.status === "completed" ? "Completed" : job.status === "failed" ? "Failed" : "Running…",
      lineageKey: job.lineage_key,
      threadId: job.thread_id ?? undefined,
      sourceAssetId: job.source_asset_id ?? undefined,
      message: job.message ?? undefined,
    };
  } catch {
    return null;
  }
}

export async function uploadAsset(
  file: File,
  workspaceId: string,
  assetRole: string
): Promise<{ id: string; url: string } | null> {
  if (!API_BASE_URL) return null;
  const form = new FormData();
  form.append("file", file);
  form.append("workspace_id", workspaceId);
  form.append("asset_role", assetRole);
  const response = await fetch(`${API_BASE_URL}/assets/upload`, {
    method: "POST",
    body: form
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Upload failed: ${response.status}${detail ? ` ${detail}` : ""}`);
  }
  const asset = (await response.json()) as { id: string; preview_url: string };
  return { id: asset.id, url: resolveAssetUrl(asset.preview_url) };
}

/** Delete a project/thread. */
export async function deleteThread(threadId: string): Promise<void> {
  if (!API_BASE_URL) return;
  await fetch(`${API_BASE_URL}/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
}

/** Rename a project/thread. */
export async function renameThread(threadId: string, title: string): Promise<void> {
  if (!API_BASE_URL) return;
  await fetch(`${API_BASE_URL}/threads/${encodeURIComponent(threadId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

/** Delete all empty threads (0 assets, 0 jobs). One-time cleanup. */
export async function cleanupEmptyThreads(): Promise<number> {
  if (!API_BASE_URL) return 0;
  const res = await fetch(`${API_BASE_URL}/threads`, { method: "DELETE" });
  if (!res.ok) return 0;
  const data = await res.json() as { deleted: number };
  return data.deleted;
}

/** Permanently delete a single asset. */
export async function deleteAsset(assetId: string): Promise<void> {
  if (!API_BASE_URL) return;
  const res = await fetch(
    `${API_BASE_URL}/assets/${encodeURIComponent(assetId)}`,
    { method: "DELETE" }
  );
  if (!res.ok && res.status !== 404)
    throw new Error(`deleteAsset failed: ${res.status}`);
}

/** Delete multiple assets in parallel. */
export async function deleteAssets(assetIds: string[]): Promise<void> {
  await Promise.all(assetIds.map((id) => deleteAsset(id)));
}

/** Outpaint: extend canvas in a direction. */
export async function outpaintImage(params: {
  workspaceId: string;
  assetId: string;
  direction: "left" | "right" | "top" | "bottom" | "all";
  ratio: number;
  prompt?: string;
  model?: string;
  sessionId?: string;
  threadId?: string;
  outputSizes?: string[];
}): Promise<import("@incept/shared").ImageGenerationResponse> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const res = await fetch(`${API_BASE_URL}/workflows/outpaint`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: params.workspaceId,
      asset_id: params.assetId,
      direction: params.direction,
      ratio: params.ratio,
      prompt: params.prompt ?? "",
      model: params.model ?? "gpt-image-2",
      session_id: params.sessionId ?? null,
      thread_id: params.threadId ?? null,
      output_sizes: params.outputSizes ?? [],
    }),
  });
  if (!res.ok) throw new Error(`outpaint failed: ${res.status}`);
  return res.json();
}

/** Remove or replace background. */
export async function removeBackground(params: {
  workspaceId: string;
  assetId: string;
  replacementPrompt?: string;
  model?: string;
  sessionId?: string;
  threadId?: string;
  outputSizes?: string[];
}): Promise<import("@incept/shared").ImageGenerationResponse> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const res = await fetch(`${API_BASE_URL}/workflows/remove-background`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: params.workspaceId,
      asset_id: params.assetId,
      replacement_prompt: params.replacementPrompt ?? "",
      model: params.model ?? "gpt-image-2",
      session_id: params.sessionId ?? null,
      thread_id: params.threadId ?? null,
      output_sizes: params.outputSizes ?? [],
    }),
  });
  if (!res.ok) throw new Error(`removeBackground failed: ${res.status}`);
  return res.json();
}

/** Add text overlay to an image (Pillow-based, instant). */
export async function addTextToImage(params: {
  workspaceId: string;
  assetId: string;
  text: string;
  position?: "top" | "center" | "bottom";
  fontSizeRatio?: number;
  sessionId?: string;
  threadId?: string;
  outputSizes?: string[];
}): Promise<import("@incept/shared").ImageGenerationResponse> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const res = await fetch(`${API_BASE_URL}/workflows/add-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: params.workspaceId,
      asset_id: params.assetId,
      text: params.text,
      position: params.position ?? "bottom",
      font_size_ratio: params.fontSizeRatio ?? 0.06,
      session_id: params.sessionId ?? null,
      thread_id: params.threadId ?? null,
      output_sizes: params.outputSizes ?? [],
    }),
  });
  if (!res.ok) throw new Error(`addText failed: ${res.status}`);
  return res.json();
}

/** Cancel a running generation job. */
export async function cancelJob(jobId: string): Promise<void> {
  if (!API_BASE_URL) return;
  await fetch(`${API_BASE_URL}/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}

/** Create a new conversation session for a workspace. */
export async function createSession(workspaceId: string): Promise<{ session_id: string }> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const res = await fetch(
    `${API_BASE_URL}/sessions?workspace_id=${encodeURIComponent(workspaceId)}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`createSession failed: ${res.status}`);
  return res.json();
}

/** Submit an inpainting / natural-language edit request. */
export async function editImage(params: {
  workspaceId: string;
  assetId: string;
  extraAssetIds?: string[];   // logos / additional references
  maskDataUrl?: string;
  prompt: string;
  model?: string;
  variants?: number;
  theme?: string;
  sessionId?: string;
  threadId?: string;
  outputSizes?: string[];
}): Promise<import("@incept/shared").ImageGenerationResponse> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const res = await fetch(`${API_BASE_URL}/workflows/image-edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id:    params.workspaceId,
      asset_id:        params.assetId,
      extra_asset_ids: params.extraAssetIds ?? [],
      mask_data:       params.maskDataUrl ?? null,
      prompt:          params.prompt,
      model:           params.model ?? "gpt-image-2",
      variants:        params.variants ?? 1,
      theme:           params.theme ?? "",
      session_id:      params.sessionId ?? null,
      thread_id:       params.threadId ?? null,
      output_sizes:    params.outputSizes ?? [],
    }),
  });
  if (!res.ok) throw new Error(`editImage failed: ${res.status}`);
  return res.json();
}

export async function cleanKakaoImage(params: {
  workspaceId: string;
  assetId: string;
  threadId?: string;
}): Promise<import("@incept/shared").ImageGenerationResponse> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const res = await fetch(`${API_BASE_URL}/workflows/kakao-clean`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: params.workspaceId,
      asset_id: params.assetId,
      thread_id: params.threadId ?? null,
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`kakaoClean failed: ${res.status}${detail ? ` ${detail}` : ""}`);
  }
  return res.json();
}

export async function generateGifFromAsset(params: {
  workspaceId: string;
  assetId: string;
  threadId?: string;
}): Promise<import("@incept/shared").ImageGenerationResponse> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const res = await fetch(`${API_BASE_URL}/workflows/generate-gif`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: params.workspaceId,
      asset_id: params.assetId,
      thread_id: params.threadId ?? null,
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`generateGif failed: ${res.status}${detail ? ` ${detail}` : ""}`);
  }
  return res.json();
}

export async function createKakaoBizboardJob(params: {
  workspaceId: string;
  cleanedAssetId: string;
  composedAssetId: string;
  mainCopy: string;
  appDownloadCopy: string;
  dspName: string;
  gacha: boolean;
  threadId?: string;
}): Promise<import("@incept/shared").ImageGenerationResponse> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const res = await fetch(`${API_BASE_URL}/workflows/kakao-bizboard`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: params.workspaceId,
      cleaned_asset_id: params.cleanedAssetId,
      composed_asset_id: params.composedAssetId,
      main_copy: params.mainCopy,
      app_download_copy: params.appDownloadCopy,
      dsp_name: params.dspName,
      gacha: params.gacha,
      thread_id: params.threadId ?? null,
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`kakaoBizboard failed: ${res.status}${detail ? ` ${detail}` : ""}`);
  }
  return res.json();
}

/**
 * Download selected assets as a named zip file.
 * Files are named: {prefix}_{width}x{height}.png
 * Multiple variants of the same size: {prefix}_{width}x{height}_v2.png
 */
export async function downloadAssetsZip(
  assetIds: string[],
  prefix: string
): Promise<void> {
  if (!API_BASE_URL) throw new Error("API not configured");
  if (assetIds.length === 0) return;

  const response = await fetch(`${API_BASE_URL}/assets/download-zip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asset_ids: assetIds, prefix }),
  });

  if (!response.ok) throw new Error(`Download failed: ${response.status}`);

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${prefix.replace(/\s+/g, "_") || "incept"}_assets.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function listUsageEvents(workspaceId?: string): Promise<UsageEvent[]> {
  if (!API_BASE_URL) {
    return [];
  }
  const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  const events = await fetchJson<ApiUsageEvent[]>(`/usage${query}`);
  return events.map((event) => ({
    id: event.id,
    jobId: event.job_id,
    workspaceId: event.workspace_id,
    userId: event.user_id,
    userEmail: event.user_email,
    provider: event.provider,
    model: event.model,
    operation: event.operation,
    promptHash: event.prompt_hash,
    variants: event.variants,
    outputSizeCount: event.output_size_count,
    outputFormat: event.output_format,
    estimatedProviderGenerations: event.estimated_provider_generations,
    outputAssetCount: event.output_asset_count,
    estimatedCostUsd: event.estimated_cost_usd,
    actualCostUsd: event.actual_cost_usd ?? undefined,
    inputTokens: event.input_tokens ?? undefined,
    outputTokens: event.output_tokens ?? undefined,
    createdAt: event.created_at
  }));
}

export async function listThemeCreatePresets(params?: {
  workspaceId?: string;
  mode?: import("@incept/shared").ThemeCreateMode;
}): Promise<ThemeCreatePresetSummary[]> {
  if (!API_BASE_URL) return [];
  const query = new URLSearchParams();
  if (params?.workspaceId) query.set("workspace_id", params.workspaceId);
  if (params?.mode) query.set("mode", params.mode);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const presets = await fetchJson<ApiThemeCreatePreset[]>(`/theme-create/presets${suffix}`);
  return presets.map((preset) => ({
    id: preset.preset_id,
    workspaceId: preset.workspace_id ?? undefined,
    name: preset.name,
    description: preset.description,
    themeCreateMode: preset.theme_create_mode,
    visibility: preset.visibility,
    promptTemplate: preset.prompt_template,
    styleName: preset.style_name ?? undefined,
    styleDetails: preset.style_details ?? undefined,
    tags: preset.tags,
    taxonomy: preset.taxonomy,
    sourceReportId: preset.source_report_id ?? undefined,
    sourceJobId: preset.source_job_id ?? undefined,
    sourceAssetId: preset.source_asset_id ?? undefined,
    createdBy: preset.created_by,
    createdAt: preset.created_at,
    updatedAt: preset.updated_at,
    usageCount: preset.usage_count,
    isOfficial: preset.is_official,
  }));
}

export async function createThemeCreateReport(payload: {
  workspace_id: string;
  title: string;
  summary: string;
  theme_create_mode: import("@incept/shared").ThemeCreateMode;
  prompt_template: string;
  source_asset_id?: string;
  reference_asset_ids?: string[];
  source_job_id?: string;
  recommended_preset_name?: string;
  visual_dna?: string[];
  composition_rules?: string[];
  do_not_copy?: string[];
  tags?: string[];
  taxonomy?: Record<string, string[]>;
}): Promise<ThemeCreateStyleReportSummary> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const response = await fetch(`${API_BASE_URL}/theme-create/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`createThemeCreateReport failed: ${response.status}`);
  const report = (await response.json()) as ApiThemeCreateStyleReport;
  return {
    id: report.report_id,
    workspaceId: report.workspace_id,
    title: report.title,
    summary: report.summary,
    themeCreateMode: report.theme_create_mode,
    promptTemplate: report.prompt_template,
    sourceAssetId: report.source_asset_id ?? undefined,
    referenceAssetIds: report.reference_asset_ids,
    sourceJobId: report.source_job_id ?? undefined,
    recommendedPresetName: report.recommended_preset_name ?? undefined,
    visualDna: report.visual_dna,
    compositionRules: report.composition_rules,
    doNotCopy: report.do_not_copy,
    tags: report.tags,
    taxonomy: report.taxonomy,
    createdBy: report.created_by,
    createdAt: report.created_at,
    updatedAt: report.updated_at,
  };
}

export async function draftThemeCreateReport(payload: {
  workspace_id: string;
  theme_create_mode: import("@incept/shared").ThemeCreateMode;
  prompt_template: string;
  source_asset_id: string;
  reference_asset_ids?: string[];
  style_name?: string;
  style_details?: string;
  logo_position?: string;
  element_position?: string;
  old_text?: string;
  new_text?: string;
  font_style?: string;
}): Promise<{
  title: string;
  summary: string;
  theme_create_mode: import("@incept/shared").ThemeCreateMode;
  prompt_template: string;
  source_asset_id?: string;
  reference_asset_ids: string[];
  recommended_preset_name?: string;
  visual_dna: string[];
  composition_rules: string[];
  do_not_copy: string[];
  tags: string[];
  taxonomy: Record<string, string[]>;
}> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const response = await fetch(`${API_BASE_URL}/theme-create/reports/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`draftThemeCreateReport failed: ${response.status}${detail ? ` ${detail}` : ""}`);
  }
  return response.json();
}

export async function createThemeCreatePreset(payload: {
  workspace_id?: string;
  name: string;
  description: string;
  theme_create_mode: import("@incept/shared").ThemeCreateMode;
  visibility?: import("@incept/shared").ThemeCreatePresetVisibility;
  prompt_template: string;
  style_name?: string;
  style_details?: string;
  tags?: string[];
  taxonomy?: Record<string, string[]>;
  source_report_id?: string;
  source_job_id?: string;
  source_asset_id?: string;
}): Promise<ThemeCreatePresetSummary> {
  if (!API_BASE_URL) throw new Error("API not configured");
  const response = await fetch(`${API_BASE_URL}/theme-create/presets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`createThemeCreatePreset failed: ${response.status}`);
  const preset = (await response.json()) as ApiThemeCreatePreset;
  return {
    id: preset.preset_id,
    workspaceId: preset.workspace_id ?? undefined,
    name: preset.name,
    description: preset.description,
    themeCreateMode: preset.theme_create_mode,
    visibility: preset.visibility,
    promptTemplate: preset.prompt_template,
    styleName: preset.style_name ?? undefined,
    styleDetails: preset.style_details ?? undefined,
    tags: preset.tags,
    taxonomy: preset.taxonomy,
    sourceReportId: preset.source_report_id ?? undefined,
    sourceJobId: preset.source_job_id ?? undefined,
    sourceAssetId: preset.source_asset_id ?? undefined,
    createdBy: preset.created_by,
    createdAt: preset.created_at,
    updatedAt: preset.updated_at,
    usageCount: preset.usage_count,
    isOfficial: preset.is_official,
  };
}
