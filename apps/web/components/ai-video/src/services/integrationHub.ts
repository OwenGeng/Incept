import { aiVideoApiBase } from '../runtime'

type Envelope<T> = { data?: T | null; detail?: string; message?: string }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${aiVideoApiBase}/api/v1/studio${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const payload = await response.json().catch(() => ({})) as Envelope<T>
  if (!response.ok || payload.data == null) throw new Error(payload.detail ?? payload.message ?? `Request failed (${response.status})`)
  return payload.data
}

export type CustomEndpoint = {
  id: string
  name: string
  category: 'text' | 'image' | 'video' | 'speech' | 'music' | 'workflow'
  base_url: string
  status: 'draft' | 'testing' | 'active' | 'disabled'
  auth_type: 'none' | 'bearer' | 'header'
  auth_header: string
  credential_env?: string | null
  request_contract: Record<string, unknown>
  response_contract: Record<string, unknown>
  polling_contract: Record<string, unknown>
  capabilities: Record<string, unknown>
  source_market_entry_id?: string | null
  config_version: number
  last_test_status?: string | null
  last_test_detail: Record<string, unknown>
}

export type ComfyWorkflow = {
  id: string
  name: string
  description: string
  endpoint_id?: string | null
  workflow: Record<string, unknown>
  input_schema: Record<string, unknown>
  bindings: Record<string, unknown>
  capabilities: Record<string, unknown>
  version: number
  status: string
}

export type MarketEntry = {
  id: string
  name: string
  description: string
  publisher: string
  trust_level: 'local' | 'reviewed' | 'unverified'
  status: 'draft' | 'published' | 'deprecated'
  version: string
  categories: string[]
  template: Record<string, unknown>
  credential_destination: string
  source_url?: string | null
}

export type AutomationKey = {
  id: string
  name: string
  key_prefix: string
  scopes: string[]
  status: string
  last_used_at?: string | null
  created_at: string
}

export const listCustomEndpoints = () => request<CustomEndpoint[]>('/integrations/endpoints')
export const createCustomEndpoint = (value: Omit<CustomEndpoint, 'id' | 'config_version' | 'last_test_status' | 'last_test_detail' | 'source_market_entry_id'>) =>
  request<CustomEndpoint>('/integrations/endpoints', { method: 'POST', body: JSON.stringify(value) })
export const updateCustomEndpoint = (id: string, value: Record<string, unknown>) =>
  request<CustomEndpoint>(`/integrations/endpoints/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(value) })
export const validateCustomEndpoint = (id: string, sampleResponse: Record<string, unknown>) =>
  request<Record<string, unknown>>(`/integrations/endpoints/${encodeURIComponent(id)}/validate`, { method: 'POST', body: JSON.stringify({ sample_response: sampleResponse }) })
export const previewEndpointExecution = (id: string, input: Record<string, unknown>) =>
  request<Record<string, unknown>>(`/integrations/endpoints/${encodeURIComponent(id)}/execute`, { method: 'POST', body: JSON.stringify({ input, confirm_external_call: false, wait_for_result: false }) })
export const executeCustomEndpoint = (id: string, input: Record<string, unknown>) =>
  request<Record<string, unknown>>(`/integrations/endpoints/${encodeURIComponent(id)}/execute`, { method: 'POST', body: JSON.stringify({ input, confirm_external_call: true, wait_for_result: true }) })

export const listComfyWorkflows = () => request<ComfyWorkflow[]>('/integrations/comfy-workflows')
export const importComfyWorkflow = (value: Record<string, unknown>) =>
  request<ComfyWorkflow>('/integrations/comfy-workflows', { method: 'POST', body: JSON.stringify(value) })
export const executeComfyWorkflow = (id: string, value: Record<string, unknown>) =>
  request<Record<string, unknown>>(`/integrations/comfy-workflows/${encodeURIComponent(id)}/execute`, { method: 'POST', body: JSON.stringify(value) })

export const listMarketEntries = () => request<MarketEntry[]>('/integrations/market')
export const publishMarketEntry = (value: Record<string, unknown>) =>
  request<MarketEntry>('/integrations/market', { method: 'POST', body: JSON.stringify(value) })
export const installMarketEntry = (id: string, credentialEnv?: string) =>
  request<Record<string, unknown>>(`/integrations/market/${encodeURIComponent(id)}/install`, { method: 'POST', body: JSON.stringify({ credential_env: credentialEnv || null }) })

export const listAutomationKeys = () => request<AutomationKey[]>('/automation/api-keys')
export const createAutomationKey = (name: string, scopes: string[]) =>
  request<AutomationKey & { token: string }>('/automation/api-keys', { method: 'POST', body: JSON.stringify({ name, scopes }) })
export const revokeAutomationKey = (id: string) =>
  request<AutomationKey>(`/automation/api-keys/${encodeURIComponent(id)}/revoke`, { method: 'POST' })

export const mcpEndpointUrl = `${aiVideoApiBase}/api/v1/automation/mcp`
