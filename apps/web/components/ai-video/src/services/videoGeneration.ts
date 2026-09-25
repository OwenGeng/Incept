import { aiVideoApiBase } from '../runtime'

export type VideoGenerationRequest = {
  shot_id: string
  reference_mode: 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'
  prompt?: string | null
  images: string[]
  ratio: '16:9' | '4:3' | '1:1' | '3:4' | '9:16' | '21:9'
  model_id?: string | null
  provider_params: Record<string, unknown>
}

export type VideoGenerationQuote = {
  complete: true
  currency: string
  amount: string
  quantity: string
  unit: string
  unit_amount: string
  model_id: string
  estimate_kind?: string | null
  estimate_scope?: string | null
  exclusions: string[]
  pricing_snapshot?: Record<string, unknown> | null
  quote_fingerprint: string
}

type ApiEnvelope<T> = { data?: T | null; message?: string; detail?: string | Record<string, unknown> }

async function request<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${aiVideoApiBase}/api/v1/film${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = (await response.json().catch(() => ({}))) as ApiEnvelope<T>
  if (!response.ok || payload.data === undefined || payload.data === null) {
    const detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail ?? {})
    throw new Error(detail || payload.message || `Request failed (${response.status})`)
  }
  return payload.data
}

export const preflightVideoGeneration = (value: VideoGenerationRequest) =>
  request<VideoGenerationQuote>('/tasks/video/preflight', value)

export const createConfirmedVideoGeneration = (
  value: VideoGenerationRequest,
  quoteFingerprint: string,
) =>
  request<{ task_id: string }>('/tasks/video', {
    ...value,
    quote_fingerprint: quoteFingerprint,
    confirmed_by: 'studio-user',
  })
