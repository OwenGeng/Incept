import assert from 'node:assert/strict';
import test from 'node:test';
import { countLiteral, replaceLiteral, scanDocuments, replaceSearchFiles } from './search.ts';

test('literal replacement treats regex symbols and dollar substitutions as text', () => {
  assert.equal(replaceLiteral('a.* a.*', 'a.*', '$&'), '$& $&');
  assert.equal(countLiteral('aaaa', 'aa'), 2);
  assert.equal(countLiteral('text', ''), 0);
});
test('search skips binary and hidden directories and preserves read errors', async () => {
  const result = await scanDocuments({
    list: async () => ({ entries: [{ path: '.git', name: '.git', type: 'directory' }, { path: 'a.md', name: 'a.md', type: 'file' }, { path: 'bad.txt', name: 'bad.txt', type: 'file' }, { path: 'image.png', name: 'image.png', type: 'file' }] }),
    readTextSnapshot: async path => { if (path === 'bad.txt') throw new Error('denied'); return { text: 'hello\nhello', revision: 'r1', encoding: 'utf-8' }; },
  }, 'hello');
  assert.equal(result.files.length, 1);
  assert.equal(result.files[0]?.count, 2);
  assert.equal(result.files[0]?.matches[1]?.line, 2);
  assert.equal(result.errors.length, 1);
});
test('search stops at resource bounds and preserves already found results', async () => {
  const result = await scanDocuments({ list: async () => ({ entries: [{ path: 'a.md', name: 'a.md', type: 'file' }, { path: 'b.md', name: 'b.md', type: 'file' }] }), readTextSnapshot: async () => ({ text: 'find', revision: 'r', encoding: 'utf-8' }) }, 'find', undefined, { files: 1 });
  assert.equal(result.files.length, 1);
  assert.equal(result.partial, true);
});
test('cancelled search retains scanned results', async () => {
  const controller = new AbortController();
  const result = await scanDocuments({ list: async () => ({ entries: [{ path: 'a.md', name: 'a.md', type: 'file' }, { path: 'b.md', name: 'b.md', type: 'file' }] }), readTextSnapshot: async () => { controller.abort(); return { text: 'find', revision: 'r', encoding: 'utf-8' }; } }, 'find', controller.signal);
  assert.equal(result.partial, true);
});
test('batch replacement preserves snapshots and stops on conflict before later files', async () => {
  const files = ['a.md', 'b.md', 'c.md'].map(path => ({ path, snapshot: { text: 'a', revision: path, encoding: 'utf-8' as const }, count: 1, matches: [] }));
  const saved: string[] = [];
  await assert.rejects(replaceSearchFiles(files, 'a', 'b', async (file, text) => {
    assert.equal(text, 'b');
    assert.equal(file.snapshot.revision, file.path);
    if (file.path === 'b.md') throw new Error('conflict');
    saved.push(file.path);
  }, () => true), /b.md/);
  assert.deepEqual(saved, ['a.md']);
});
test('replacement refuses an open draft before attempting write', async () => {
  let writes = 0;
  await assert.rejects(replaceSearchFiles([{ path: 'draft.md', snapshot: { text: 'a', revision: 'r', encoding: 'utf-8' }, count: 1, matches: [] }], 'a', 'b', async () => { writes++; }, () => false), /已打开/);
  assert.equal(writes, 0);
});
