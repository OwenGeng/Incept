export type ThinkingCapability = { providerId: string; modelId: string; thinkingLevels: string[] };
export function supportedThinkingLevels(models: ThinkingCapability[], providerId?: string, modelId?: string): string[] {
  return [...new Set(models.find(model => model.providerId === providerId && model.modelId === modelId)?.thinkingLevels ?? [])];
}
export function eventCursor(current: number, sequence?: number) {
  return sequence === undefined ? { accept: true, sequence: current } : { accept: sequence > current, sequence: Math.max(current, sequence) };
}
export function runEventURL(scope: { directory: string; sessionFile: string; runId?: string }, after: number) {
  const params = new URLSearchParams({ directory: scope.directory, sessionFile: scope.sessionFile, after: String(after) });
  if (scope.runId) params.set('runId', scope.runId);
  return `/api/agent/events?${params}`;
}
export function costLabel(cost: number | null | undefined, language: string) {
  return typeof cost === 'number' && Number.isFinite(cost) ? `$${cost.toFixed(4)}` : language === 'en' ? 'Price unknown' : '价格未知';
}
