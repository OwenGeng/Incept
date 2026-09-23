export type WorkflowTemplate = "script" | "image" | "video" | "commercial";
export type WorkflowNodeStatus = "draft" | "valid" | "blocked" | "queued" | "running" | "succeeded" | "approved" | "stale" | "failed" | "cancelled";

export interface StudioWorkflowNode {
  id: string;
  type: string;
  label: string;
  params: Record<string, unknown>;
  position: { x: number; y: number };
  status: WorkflowNodeStatus;
}
export interface StudioWorkflowEdge { id: string; source_node_id: string; source_port: string; target_node_id: string; target_port: string; }
export interface StudioWorkflowGraph { nodes: StudioWorkflowNode[]; edges: StudioWorkflowEdge[]; viewport: { x: number; y: number; zoom: number }; }
export interface StudioWorkflow { workflow_id: string; workspace_id: string; title: string; template: WorkflowTemplate; status: "draft" | "archived"; revision: number; graph: StudioWorkflowGraph; created_by: string; created_at: string; updated_at: string; }
export interface StudioWorkflowRevision { workflow_id: string; revision: number; created_by: string; created_at: string; workflow: StudioWorkflow; }
export interface WorkflowValidationResult { valid: boolean; issues: Array<{ node_id?: string | null; port_id?: string | null; message: string }>; }
export interface StudioWorkflowRun { run_id: string; workflow_id: string; workspace_id: string; revision: number; status: "queued" | "running" | "succeeded" | "failed" | "cancelled"; requested_output_node_ids: string[]; priority: number; created_by: string; created_at: string; updated_at: string; }
export interface StudioWorkflowEvent { event_id: string; run_id: string; node_id?: string | null; type: string; message: string; progress?: number | null; created_at: string; }
export interface StudioWorkflowOutput { output_id: string; workflow_id: string; workspace_id: string; run_id: string; node_id: string; output_type: "image" | "video" | "script" | "commercial"; value_id: string; created_by: string; metadata: Record<string, unknown>; created_at: string; }
export interface StudioWorkflowLineage { workflow_id: string; workspace_id: string; graph_revision: number; graph: StudioWorkflowGraph; outputs: StudioWorkflowOutput[]; runs: StudioWorkflowRun[]; run_nodes?: StudioWorkflowRunNode[]; }
export interface StudioWorkflowNodeDefinition { type: string; display_name: string; category: string; description: string; operation: "input" | "agent" | "image" | "video" | "approval" | "delivery"; requires_approval: boolean; costed: boolean; inputs: Array<{ id: string; value_type: string; required: boolean; multiple: boolean }>; outputs: Array<{ id: string; value_type: string; required: boolean; multiple: boolean }>; }

const BASE = "/api/incept";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!response.ok) {
    const raw = await response.text().catch(() => "");
    try { throw new Error((JSON.parse(raw) as { detail?: string }).detail || raw || `Request failed (${response.status})`); }
    catch (error) { if (error instanceof Error && error.message !== raw) throw error; throw new Error(raw || `Request failed (${response.status})`); }
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export const listStudioWorkflows = (workspaceId: string) => request<StudioWorkflow[]>(`/studio-workflows?workspace_id=${encodeURIComponent(workspaceId)}`);
export const listStudioWorkflowRevisions = (workflowId: string, workspaceId: string) => request<StudioWorkflowRevision[]>(`/studio-workflows/${encodeURIComponent(workflowId)}/revisions?workspace_id=${encodeURIComponent(workspaceId)}`);
export const listStudioWorkflowOutputs = (workflowId: string, workspaceId: string) => request<StudioWorkflowOutput[]>(`/studio-workflows/${encodeURIComponent(workflowId)}/outputs?workspace_id=${encodeURIComponent(workspaceId)}`);
export const getStudioWorkflowLineage = (workflowId: string, workspaceId: string) => request<StudioWorkflowLineage>(`/studio-workflows/${encodeURIComponent(workflowId)}/lineage?workspace_id=${encodeURIComponent(workspaceId)}`);
export const listStudioWorkflowNodeDefinitions = () => request<StudioWorkflowNodeDefinition[]>("/studio-workflow-node-definitions");
export const createStudioWorkflow = (workspaceId: string, template: WorkflowTemplate, title?: string) => request<StudioWorkflow>("/studio-workflows", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, template, title }) });
export const updateStudioWorkflow = (workflow: StudioWorkflow, graph: StudioWorkflowGraph, title?: string) => request<StudioWorkflow>(`/studio-workflows/${encodeURIComponent(workflow.workflow_id)}?workspace_id=${encodeURIComponent(workflow.workspace_id)}`, { method: "PUT", body: JSON.stringify({ title, graph, expected_revision: workflow.revision }) });
export const deleteStudioWorkflow = (workflowId: string, workspaceId: string) => request<void>(`/studio-workflows/${encodeURIComponent(workflowId)}?workspace_id=${encodeURIComponent(workspaceId)}`, { method: "DELETE" });
export const validateStudioWorkflow = (workflowId: string, workspaceId: string) => request<WorkflowValidationResult>(`/studio-workflows/${encodeURIComponent(workflowId)}/validate?workspace_id=${encodeURIComponent(workspaceId)}`, { method: "POST" });
export const runStudioWorkflow = (workflowId: string, workspaceId: string, outputNodeIds: string[] = [], priority = 0) => request<StudioWorkflowRun>(`/studio-workflows/${encodeURIComponent(workflowId)}/runs?workspace_id=${encodeURIComponent(workspaceId)}`, { method: "POST", body: JSON.stringify({ output_node_ids: outputNodeIds, priority }) });
export const getStudioWorkflowEvents = (runId: string, workspaceId: string) => request<StudioWorkflowEvent[]>(`/studio-workflow-runs/${encodeURIComponent(runId)}/events?workspace_id=${encodeURIComponent(workspaceId)}`);
export interface StudioWorkflowRunNode { run_id: string; node_id: string; node_type: string; status: WorkflowNodeStatus; progress: number; message: string; result: Record<string, unknown>; created_at: string; updated_at: string; }
export const getStudioWorkflowRunNodes = (runId: string, workspaceId: string) => request<StudioWorkflowRunNode[]>(`/studio-workflow-runs/${encodeURIComponent(runId)}/nodes?workspace_id=${encodeURIComponent(workspaceId)}`);
export const cancelStudioWorkflowRun = (runId: string, workspaceId: string) => request<StudioWorkflowRun>(`/studio-workflow-runs/${encodeURIComponent(runId)}/cancel?workspace_id=${encodeURIComponent(workspaceId)}`, { method: "POST" });
export const retryStudioWorkflowRun = (runId: string, workspaceId: string) => request<StudioWorkflowRun>(`/studio-workflow-runs/${encodeURIComponent(runId)}/retry?workspace_id=${encodeURIComponent(workspaceId)}`, { method: "POST" });
