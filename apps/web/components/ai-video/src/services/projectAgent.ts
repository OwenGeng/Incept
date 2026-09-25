import { aiVideoApiBase } from '../runtime'

export type ProjectAgentSession = {
  id: string
  project_id: string
  title: string
  status: string
  created_at: string
  updated_at: string
}

export type ProjectAgentMessage = {
  id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  message_metadata: Record<string, unknown>
  created_at: string
}

type ChatResponse = {
  session: ProjectAgentSession
  user_message: ProjectAgentMessage
  assistant_message: ProjectAgentMessage
}

export type ProjectMemory = {
  id: string
  project_id?: string | null
  owner_key: string
  scope: 'project' | 'user'
  kind: 'preference' | 'fact' | 'decision' | 'summary'
  content: string
  tags: string[]
  source: string
  pinned: boolean
  confidence: number
  status: string
  created_at: string
  updated_at: string
}

type Envelope<T> = { data?: T | null; message?: string; detail?: string }

const base = (projectId: string) =>
  `${aiVideoApiBase}/api/v1/studio/projects/${encodeURIComponent(projectId)}/agent`

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const payload = (await response.json().catch(() => ({}))) as Envelope<T>
  if (!response.ok || payload.data == null) {
    throw new Error(payload.detail ?? payload.message ?? `Request failed (${response.status})`)
  }
  return payload.data
}

export const listProjectAgentSessions = (projectId: string) =>
  request<ProjectAgentSession[]>(`${base(projectId)}/sessions`)

export const listProjectAgentMessages = (projectId: string, sessionId: string) =>
  request<ProjectAgentMessage[]>(`${base(projectId)}/sessions/${encodeURIComponent(sessionId)}/messages`)

export const deleteProjectAgentSession = (projectId: string, sessionId: string) =>
  request<{ deleted: boolean }>(`${base(projectId)}/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })

export const chatWithProjectAgent = (projectId: string, content: string, sessionId?: string | null) =>
  request<ChatResponse>(`${base(projectId)}/chat`, {
    method: 'POST',
    body: JSON.stringify({ content, session_id: sessionId || null }),
  })

const memoryBase = (projectId: string) =>
  `${aiVideoApiBase}/api/v1/studio/projects/${encodeURIComponent(projectId)}/memories`

export const listProjectMemories = (projectId: string, query?: string) =>
  request<ProjectMemory[]>(`${memoryBase(projectId)}${query?.trim() ? `?q=${encodeURIComponent(query.trim())}` : ''}`)

export const createProjectMemory = (
  projectId: string,
  value: Pick<ProjectMemory, 'scope' | 'kind' | 'content' | 'tags' | 'pinned' | 'confidence'>,
) => request<ProjectMemory>(memoryBase(projectId), {
  method: 'POST',
  body: JSON.stringify({ ...value, source: 'manual' }),
})

export const archiveProjectMemory = (projectId: string, memoryId: string) =>
  request<ProjectMemory>(`${memoryBase(projectId)}/${encodeURIComponent(memoryId)}/archive`, { method: 'POST' })
