import { aiVideoApiBase } from '../runtime'

export type ProductionRevisionKind = 'script' | 'shot_plan' | 'keyframe' | 'motion_prompt' | 'edit'
export type ProductionScopeType = 'project' | 'chapter' | 'shot'

export type ProductionRevision = {
  id: string
  project_id: string
  scope_type: ProductionScopeType
  scope_id: string
  kind: ProductionRevisionKind
  revision_number: number
  state: 'draft' | 'approved' | 'superseded'
  parent_revision_id?: string | null
  payload: Record<string, unknown>
  input_fingerprint: string
  created_by?: string | null
  approved_by?: string | null
  approved_at?: string | null
  created_at: string
  updated_at: string
}

export type WorkflowProblem = {
  code: string
  message: string
  target_type?: string | null
  target_id?: string | null
  severity: 'info' | 'warning' | 'blocking'
}

export type WorkflowArtifactSummary = {
  artifact_type: string
  total: number
  current: number
  stale: number
  missing: number
  blocked: number
  selected: number
}

export type ProductionWorkflowPlan = {
  project_id: string
  current_step: string
  steps: Array<{ key: string; complete: boolean }>
  blockers: WorkflowProblem[]
  gates: Array<Record<string, unknown>>
  artifacts: WorkflowArtifactSummary[]
  next_action: {
    type: string
    reason: string
    args: Record<string, unknown>
    requested_ids: string[]
    requires_confirmation: boolean
  }
}

export type ProductionQAReport = {
  id: string
  project_id: string
  edit_revision_id: string
  status: 'passed' | 'failed'
  checks: Array<Record<string, unknown>>
  waivers: Array<Record<string, unknown>>
  run_by?: string | null
  created_at: string
}

export type ProductionDelivery = {
  id: string
  project_id: string
  edit_revision_id: string
  qa_report_id: string
  delivery_type: 'preview' | 'final'
  status: string
  file_ids: string[]
  manifest: Record<string, unknown>
  delivered_by?: string | null
  created_at: string
}

export type ProductionArtifact = {
  id: string
  project_id: string
  shot_id?: string | null
  artifact_type: string
  file_id?: string | null
  source_revision_id?: string | null
  generation_task_id?: string | null
  input_fingerprint: string
  currency: 'current' | 'stale' | 'missing' | 'blocked' | string
  lifecycle: 'candidate' | 'selected' | 'rejected' | string
  metadata_json: Record<string, unknown>
  created_at: string
}

export type GenerationBatch = {
  id: string
  project_id: string
  kind: string
  status: 'blocked' | 'confirmation_required' | 'queued' | string
  requested_ids: string[]
  admission: { admitted?: boolean; all_or_none?: boolean; blockers?: Array<Record<string, unknown>> }
  estimate: {
    complete?: boolean
    currency?: string | null
    total?: string | null
    items?: Array<Record<string, unknown>>
    pricing_contract?: string
    quote_fingerprint?: string
  }
  confirmed_by?: string | null
  confirmed_at?: string | null
  created_at: string
  items: Array<{
    id: string
    target_id: string
    status: string
    task_id?: string | null
    error_code?: string | null
    error_message: string
  }>
}

export type UsageSummary = {
  project_id: string
  by_currency: Record<string, { estimated: string; actual: string }>
  unpriced_entries: number
  total_entries: number
  budget?: { currency: string; amount: string; committed: string; remaining: string } | null
}

export type VideoBatchRequest = {
  confirm_cost: boolean
  confirmed_by?: string | null
  items: Array<{
    shot_id: string
    reference_mode: 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'
    prompt?: string | null
    images: string[]
    ratio: '16:9' | '4:3' | '1:1' | '3:4' | '9:16' | '21:9'
    model_id?: string | null
    provider_params: Record<string, unknown>
  }>
}

export type EditTransition = {
  type: 'cut' | 'fade' | 'dissolve' | 'wipeleft' | 'wiperight' | 'slideleft' | 'slideright'
  duration_ms: number
}

export type EditDocument = {
  schema_version: 1
  canvas: { width: number; height: number; fps: number; background: string; safe_area_percent: number; font_family: string; primary_text_color: string }
  video_clips: Array<{
    id: string
    shot_id: string
    file_id: string
    source_in_ms: number
    source_out_ms: number
    use_source_audio: boolean
    source_audio_volume_db: number
    transition_to_next: EditTransition
  }>
  audio_clips: Array<{
    id: string
    file_id: string
    role: 'dialogue' | 'voice_over' | 'music' | 'sfx'
    timeline_start_ms: number
    source_in_ms: number
    source_out_ms: number
    volume_db: number
    duck_under_dialogue: boolean
  }>
  subtitles: Array<{ id: string; start_ms: number; end_ms: number; text: string; speaker?: string | null }>
  overlays: Array<{
    id: string
    type: 'logo' | 'cta' | 'legal' | 'end_card'
    text: string
    file_id?: string | null
    start_ms: number
    end_ms: number
    position: 'top' | 'center' | 'bottom'
    width_percent: number
  }>
}

type ApiEnvelope<T> = { data?: T | null; message?: string; detail?: string }

const productionUrl = (projectId: string, suffix = '') =>
  `${aiVideoApiBase}/api/v1/studio/projects/${encodeURIComponent(projectId)}/production${suffix}`

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const payload = (await response.json().catch(() => ({}))) as ApiEnvelope<T>
  if (!response.ok || payload.data === undefined || payload.data === null) {
    throw new Error(payload.detail ?? payload.message ?? `Request failed (${response.status})`)
  }
  return payload.data
}

export const getProductionPlan = (projectId: string) =>
  request<ProductionWorkflowPlan>(productionUrl(projectId, '/plan'))

export const listProductionRevisions = (projectId: string) =>
  request<ProductionRevision[]>(productionUrl(projectId, '/revisions'))

export const listProductionArtifacts = (projectId: string) =>
  request<ProductionArtifact[]>(productionUrl(projectId, '/artifacts'))

export const selectProductionArtifact = (projectId: string, artifactId: string) =>
  request<ProductionArtifact>(productionUrl(projectId, `/artifacts/${encodeURIComponent(artifactId)}/select`), {
    method: 'POST',
    body: JSON.stringify({ selected_by: 'studio-user' }),
  })

export const createProductionRevision = (
  projectId: string,
  value: {
    kind: ProductionRevisionKind
    scope_type: ProductionScopeType
    scope_id?: string | null
    parent_revision_id?: string | null
    payload: Record<string, unknown>
    created_by?: string | null
  },
) =>
  request<ProductionRevision>(productionUrl(projectId, '/revisions'), {
    method: 'POST',
    body: JSON.stringify(value),
  })

export const snapshotShotPlan = (projectId: string) =>
  request<ProductionRevision>(productionUrl(projectId, '/shot-plan/snapshot'), {
    method: 'POST',
    body: JSON.stringify({ created_by: 'studio-user' }),
  })

export const approveProductionRevision = (projectId: string, revisionId: string, approvedBy?: string) =>
  request<ProductionRevision>(
    productionUrl(projectId, `/revisions/${encodeURIComponent(revisionId)}/approve`),
    {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy ?? null }),
    },
  )

export const listProductionQAReports = (projectId: string) =>
  request<ProductionQAReport[]>(productionUrl(projectId, '/qa'))

export const runProductionQA = (projectId: string, editRevisionId: string) =>
  request<ProductionQAReport>(productionUrl(projectId, '/qa/run'), {
    method: 'POST',
    body: JSON.stringify({ edit_revision_id: editRevisionId }),
  })

export const listProductionDeliveries = (projectId: string) =>
  request<ProductionDelivery[]>(productionUrl(projectId, '/deliveries'))

export const createProductionDelivery = (
  projectId: string,
  value: {
    edit_revision_id: string
    qa_report_id: string
    delivery_type: 'preview' | 'final'
    file_ids: string[]
  },
) =>
  request<ProductionDelivery>(productionUrl(projectId, '/deliveries'), {
    method: 'POST',
    body: JSON.stringify(value),
  })

export const listGenerationBatches = (projectId: string) =>
  request<GenerationBatch[]>(productionUrl(projectId, '/batches'))

export const createVideoGenerationBatch = (projectId: string, value: VideoBatchRequest) =>
  request<GenerationBatch>(productionUrl(projectId, '/batches/video'), {
    method: 'POST',
    body: JSON.stringify(value),
  })

export const confirmVideoGenerationBatch = (
  projectId: string,
  batchId: string,
  quoteFingerprint: string,
) =>
  request<GenerationBatch>(productionUrl(projectId, `/batches/${encodeURIComponent(batchId)}/confirm`), {
    method: 'POST',
    body: JSON.stringify({ quote_fingerprint: quoteFingerprint, confirmed_by: 'studio-user' }),
  })

export const getUsageSummary = (projectId: string) =>
  request<UsageSummary>(productionUrl(projectId, '/usage/summary'))

export const getDefaultEditDocument = (projectId: string) =>
  request<EditDocument>(productionUrl(projectId, '/edit/default'))

export const createEditRevision = (projectId: string, document: EditDocument) =>
  request<ProductionRevision>(productionUrl(projectId, '/edit/revisions'), {
    method: 'POST',
    body: JSON.stringify({ document }),
  })

export const renderEditRevision = (projectId: string, editRevisionId: string, outputName = 'final-render') =>
  request<{ task_id: string; edit_revision_id: string; manifest_fingerprint: string }>(
    productionUrl(projectId, '/render'),
    { method: 'POST', body: JSON.stringify({ edit_revision_id: editRevisionId, output_name: outputName }) },
  )
