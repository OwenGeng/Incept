import { aiVideoApiBase } from '../runtime'
import { StudioFilesService } from './generated'

export type ResearchEntryMode = 'research' | 'preset'
export type ResearchStatus = 'draft' | 'researching' | 'ready' | 'approved'
export type ResearchSourceType =
  | 'product_page'
  | 'product_asset'
  | 'competitor_video'
  | 'reference_video'
  | 'brand_guideline'

export type CreativeBrief = {
  advertiser_vertical: string
  delivery_channel: string
  product_name: string
  product_description: string
  product_url?: string | null
  product_asset_file_ids: string[]
  market?: string | null
  target_audience: string
  conversion_goal: string
  key_messages: string[]
  cta: string
  legal: string
  prohibited_claims: string[]
  claim_evidence: Array<Record<string, string>>
  target_duration_seconds?: number | null
  aspect_ratios: Array<'16:9' | '9:16' | '1:1' | '4:3' | '3:4' | '21:9'>
  language: string
  required_overlays: Array<'logo' | 'cta' | 'legal' | 'end_card'>
  logo_file_id?: string | null
  brand_colors: string[]
  brand_font_family: string
  safe_area_percent: number
  budget_amount?: string | number | null
  budget_currency?: string | null
  default_image_model_id?: string | null
  default_video_model_id?: string | null
  creative_format?: string | null
  creative_playbook?: string | null
  visual_direction?: string | null
  script_direction?: string | null
}

export type ResearchSource = {
  id: string
  type: ResearchSourceType
  title: string
  url?: string | null
  file_id?: string | null
  notes: string
  rights_confirmed: boolean
}

export type ResearchFinding = {
  id: string
  title: string
  observation: string
  source_ids: string[]
}

export type CreativeDirection = {
  id: string
  name: string
  creative_format: string
  creative_playbook: string
  visual_direction: string
  script_direction: string
  rationale: string
  evidence_finding_ids: string[]
}

export type ProjectResearch = {
  project_id: string
  exists: boolean
  entry_mode: ResearchEntryMode
  status: ResearchStatus
  brief: CreativeBrief
  sources: ResearchSource[]
  findings: ResearchFinding[]
  creative_directions: CreativeDirection[]
  approved_direction_id?: string | null
}

type ApiEnvelope<T> = { data?: T | null; message?: string }

const researchUrl = (projectId: string, suffix = '') =>
  `${aiVideoApiBase}/api/v1/studio/projects/${encodeURIComponent(projectId)}/research${suffix}`

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const payload = (await response.json().catch(() => ({}))) as ApiEnvelope<T> & { detail?: string }
  if (!response.ok || !payload.data) {
    throw new Error(payload.detail ?? payload.message ?? `Request failed (${response.status})`)
  }
  return payload.data
}

export const getProjectResearch = (projectId: string) => request<ProjectResearch>(researchUrl(projectId))

export const saveProjectResearch = (projectId: string, value: Omit<ProjectResearch, 'project_id' | 'exists'>) =>
  request<ProjectResearch>(researchUrl(projectId), { method: 'PUT', body: JSON.stringify(value) })

export const approveProjectDirection = (projectId: string, directionId: string) =>
  request<ProjectResearch>(researchUrl(projectId, '/approve'), {
    method: 'POST',
    body: JSON.stringify({ direction_id: directionId }),
  })

export async function uploadResearchFile(projectId: string, file: File): Promise<string> {
  const response = await StudioFilesService.uploadFileApiApiV1StudioFilesUploadPost({
    formData: {
      file: file as unknown as string,
      project_id: projectId,
      usage_kind: 'upload',
      source_ref: 'project_research',
    },
    name: file.name,
  })
  if (!response.data?.id) throw new Error('The uploaded file did not return an ID')
  return response.data.id
}
