import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

// Exercise the actual component handler without mounting the editor or making requests.
const source = readFileSync(new URL('./conversation.vue', import.meta.url), 'utf8');
const handler = source.slice(source.indexOf('async function deleteMessage('), source.indexOf('\nfunction setSenderHeight('));
const javascript = ts.transpileModule(handler, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;

test('deleting a persisted turn renders the canonical response without orphan replies', async () => {
  const user = { id: 'user', entryId: 'user', role: 'user' };
  const orphanReply = { id: 'answer', replyTo: 'user', role: 'assistant' };
  const nextTurn = { id: 'next', entryId: 'next', role: 'user', attachments: [{ name: 'kept.png', path: 'assets/kept.png', mimeType: 'image/png' }] };
  const messages = { value: [user, orphanReply, nextTurn] };
  const stats = { value: undefined };
  const contextUsage = { value: undefined };
  const deletingId = { value: undefined };
  const researchQuestion = { value: { id: 'old-question' } as unknown };
  const axios = { delete: async () => ({ data: { code: 200, data: { messages: [nextTurn] } } }), isAxiosError: () => false };
  const remove = new Function('locked', 'remoteRunning', 'deletingId', 'directory', 'props', 'axios', 'stats', 'contextUsage', 'messages', 'ElMessage', 'editingId', 'editingText', 'researchQuestion', `${javascript}; return deleteMessage;`)(
    { value: false }, { value: false }, deletingId, { value: 'synthetic' }, { sessionFile: 'session.json' }, axios, stats, contextUsage, messages,
    { error: (message: string) => { throw new Error(message); } }, { value: 'user' }, { value: 'editing' }, researchQuestion,
  );
  await remove(user);
  assert.deepEqual(messages.value, [nextTurn]);
  assert.equal(deletingId.value, undefined);
  assert.equal(researchQuestion.value, null);
});
