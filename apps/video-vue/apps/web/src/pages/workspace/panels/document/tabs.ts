export function canonicalDocumentPath(path: string) {
  return path.replaceAll('\\', '/').replace(/^(?:\.\/)+/, '').replace(/\/+/g, '/');
}
export function documentKey(selection: { filePath: string } | { canvasPath: string; nodeId: string }) {
  return 'filePath' in selection ? JSON.stringify(['file', canonicalDocumentPath(selection.filePath)])
    : JSON.stringify(['node', canonicalDocumentPath(selection.canvasPath), selection.nodeId]);
}
/** A document can be visible in only one pane, but hidden tabs stay mounted. */
export function assignPane(ids: (string | null)[], id: string, pane: number) {
  return ids.map((current, index) => index === pane ? id : current === id ? null : current);
}
export function findBackingTab<T extends { id: string; filePath?: string }>(tabs: T[], path: string | undefined, excludeId?: string) {
  if (!path) return undefined;
  const canonical = canonicalDocumentPath(path);
  return tabs.find(tab => tab.id !== excludeId && tab.filePath && canonicalDocumentPath(tab.filePath) === canonical);
}
