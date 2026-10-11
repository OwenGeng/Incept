// Hosted adaptation of Toonflow's runtime/sessions.ts deleteAgentMessage (MIT).
// Pi has tree navigation but no physical message-delete API. Keep this journal
// storage operation outside the model loop, preserving IDs and SDK ownership.
import { readFileSync, writeFileSync, renameSync } from 'node:fs';
import { SessionManager } from '@earendil-works/pi-coding-agent';

export function redactSessionEntries(history: SessionManager, ids: string[], cwd: string, sessionDir: string) {
  const branch = history.getBranch();
  const targets = new Set(ids);
  if (ids.some(id => !branch.some(entry => entry.id === id && entry.type === 'message'
    && ['user', 'assistant'].includes(entry.message.role)))) throw Error('Deleted message is not in the current SDK branch');
  let removingTurn = false;
  for (const entry of branch) {
    if (entry.type === 'message' && entry.message.role === 'user') removingTurn = targets.has(entry.id);
    if (removingTurn) targets.add(entry.id);
  }
  const affected = new Set(targets);
  const entries = history.getEntries();
  for (const entry of entries) {
    if (entry.parentId && affected.has(entry.parentId)) affected.add(entry.id);
    if ((entry.type === 'compaction' || entry.type === 'branch_summary') && affected.has(entry.id)) targets.add(entry.id);
  }
  const path = history.getSessionFile();
  if (!path) throw Error('No persisted SDK journal for deletion');
  const header = JSON.parse(readFileSync(path, 'utf8').split('\n')[0]);
  const redacted = entries.map(entry => targets.has(entry.id) ? { type: 'custom', id: entry.id,
    parentId: entry.parentId, timestamp: entry.timestamp, customType: 'linglonglabDeletedEntry' } : entry);
  const temporary = path + '.redacted.tmp';
  writeFileSync(temporary, [header, ...redacted].map(entry => JSON.stringify(entry)).join('\n') + '\n', { mode: 0o600, flag: 'wx' });
  renameSync(temporary, path);
  return SessionManager.open(path, sessionDir, cwd);
}
