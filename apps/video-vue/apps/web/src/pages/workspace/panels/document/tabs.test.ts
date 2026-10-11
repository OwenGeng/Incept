import assert from 'node:assert/strict';
import test from 'node:test';
import { assignPane, documentKey, findBackingTab } from './tabs.ts';
test('path aliases reuse the same tab instead of editing a document twice', () => {
  assert.equal(documentKey({ filePath: './research\\brief.md' }), documentKey({ filePath: 'research/brief.md' }));
  assert.notEqual(documentKey({ canvasPath: 'a.json', nodeId: '1' }), documentKey({ canvasPath: 'a.json', nodeId: '2' }));
});
test('moving a tab between panes clears its old pane and preserves other tabs', () => {
  assert.deepEqual(assignPane(['a', 'b'], 'a', 1), [null, 'a']);
  assert.deepEqual(assignPane(['a', 'b'], 'c', 0), ['c', 'b']);
});
test('a node and file sharing a backing path reuse the existing draft tab', () => {
  const draft = { id: 'file-tab', filePath: 'research/brief.md', text: 'unsaved draft' };
  const temporary = { id: 'new-node-tab', filePath: 'research/brief.md', text: 'disk text' };
  assert.equal(findBackingTab([draft, temporary], './research\\brief.md', temporary.id), draft);
  assert.equal(draft.text, 'unsaved draft');
  assert.equal(findBackingTab([draft], undefined), undefined);
});
