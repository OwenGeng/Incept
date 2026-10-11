import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { costLabel, eventCursor, isConversationFile, runEventURL, supportedThinkingLevels } from './runtimeControls.ts';
test('thinking levels come only from the exact configured model capability', () => {
  const models = [{ providerId: 'p', modelId: 'm', thinkingLevels: ['off', 'high', 'high'] }];
  assert.deepEqual(supportedThinkingLevels(models, 'p', 'm'), ['off', 'high']);
  assert.deepEqual(supportedThinkingLevels(models, 'p', 'unknown'), []);
});
test('reconnect cursor rejects already applied deltas and retains unsequenced control events', () => {
  assert.deepEqual(eventCursor(20, 19), { accept: false, sequence: 20 });
  assert.deepEqual(eventCursor(20, 21), { accept: true, sequence: 21 });
  assert.deepEqual(eventCursor(20), { accept: true, sequence: 20 });
  const url = new URL(runEventURL({ directory: '/project & one', sessionFile: 'a.jsonl', runId: 'r' }, 20), 'http://local');
  assert.equal(url.searchParams.get('after'), '20');
  assert.equal(url.searchParams.get('directory'), '/project & one');
});
test('missing model prices are never displayed as free', () => {
  assert.equal(costLabel(null, 'en'), 'Price unknown');
  assert.equal(costLabel(undefined, 'zh'), '价格未知');
  assert.equal(costLabel(0, 'zh'), '$0.0000');
});

test('hosted canonical history identifiers and native journal basenames can be removed without accepting traversal', () => {
  assert.equal(isConversationFile('agent/' + 'a'.repeat(32) + '.json'), true);
  assert.equal(isConversationFile('2026-10-12_native-session.jsonl'), true);
  for (const file of ['agent/../secret.json', '../session.jsonl', 'agent/invalid.json', '/absolute/session.jsonl', 'agent/' + 'a'.repeat(32) + '.json/other']) assert.equal(isConversationFile(file), false);
});

test('a new owned run cannot send a live instruction with the previous turn identity', () => {
  const source = readFileSync(new URL('./conversation.vue', import.meta.url), 'utf8');
  const start = source.slice(source.indexOf('async function sendMessage('), source.indexOf('function addAttachments('));
  assert.ok(start.indexOf('currentRunId.value = undefined') < start.indexOf('busy.value = true'));
  assert.match(start, /if \(!remoteRunning\.value\) \{ currentRunId\.value = undefined; activeRun = undefined; \}/);
  const instruction = source.slice(source.indexOf('async function sendInstruction('), source.indexOf('async function observeRun('));
  assert.ok(instruction.indexOf('if (!scope?.runId)') < instruction.indexOf('axios.post("/api/agent/control"'));
  assert.ok(instruction.indexOf('if (!scope?.runId)') < instruction.indexOf('sender?.reset()'));
});

test('the native session acknowledgement retains the authenticated run identity when it has no runId', () => {
  const source = readFileSync(new URL('./conversation.vue', import.meta.url), 'utf8');
  assert.match(source, /runId: event\.runId \?\? requestRun\?\.runId \?\? currentRunId\.value/);
  const projector = source.slice(source.indexOf('function applyEvent('), source.indexOf('function receiveEvent('));
  assert.match(projector, /if \(event\.runId\) currentRunId\.value = event\.runId/);
});

test('interrupted accepted instructions are display-only and resume as new composer text', () => {
  const source = readFileSync(new URL('./conversation.vue', import.meta.url), 'utf8');
  assert.match(source, /v-if="item\.pendingInstruction"[^>]*@click="fillPrompt\(item\.content\)"/);
  assert.match(source, /item\.role === 'user' && !item\.pendingInstruction/);
  assert.match(source, /v-if="!item\.report && !item\.pendingInstruction"/);
  assert.match(source, /Interrupted; resend this instruction to continue\./);
});
