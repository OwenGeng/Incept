import assert from 'node:assert/strict';
import test from 'node:test';
import { ref } from 'vue';
import type { AgentMessage } from "./types";
import { createConversationStream, readAgentEvents } from './replyStream.ts';

test('completion reaches UI subscribers so assets refresh and progress stops', async () => {
  const response = new Response('{"type":"progress","content":"研究中"}\n{"type":"done"}\n');
  const events = [];
  for await (const event of readAgentEvents(response, new AbortController().signal)) events.push(event);
  assert.deepEqual(events, [{ type: 'progress', content: '研究中' }, { type: 'done' }]);
});

test('a new stream clears the stale error indicator before rendering a retry', () => {
  const reply = { id: 'reply', role: 'assistant' as const, content: '', parts: [], error: 'old failure' };
  const stream = createConversationStream(ref([reply]));
  stream.begin(reply);
  assert.equal(reply.error, undefined);
  stream.finish();
});

test('HTTP conflict shows the backend explanation instead of a generic status', async () => {
  const response = new Response(JSON.stringify({ detail: { message: 'Agent 正在运行，请先停止' } }), { status: 409 });
  await assert.rejects(async () => {
    for await (const _event of readAgentEvents(response, new AbortController().signal)) { /* consume */ }
  }, /Agent 正在运行，请先停止/);
});


test('accepted instructions and runtime failures terminate with an observable event', async () => {
  for (const event of [{ type: 'accepted', streamingBehavior: 'steer' }, { type: 'error', message: 'Budget reached' }]) {
    const received = [];
    for await (const item of readAgentEvents(new Response(JSON.stringify(event) + '\n'), new AbortController().signal)) received.push(item);
    assert.deepEqual(received, [event]);
  }
});

test('tool arguments, progress and interactive questions survive incremental updates', () => {
  const messages = ref<AgentMessage[]>([]);
  const stream = createConversationStream(messages);
  stream.receive({ type: 'userMessage', id: 'u', content: 'Make it' });
  stream.receive({ type: 'tool', blockId: 't', tool: { id: 'call', name: 'askUser', status: 'running', args: {}, progress: 'Waiting' } });
  stream.receive({ type: 'question', callId: 'q', toolCallId: 'call', title: 'Confirm', question: 'Choose', sessionFile: 'session.jsonl', runId: 'run' });
  const part = messages.value[1]!.parts![0]!;
  if (part.type !== 'tool') throw new Error('Expected a tool card');
  assert.equal(part.tool.question?.sessionFile, 'session.jsonl');
  stream.receive({ type: 'tool', blockId: 't', tool: { id: 'call', name: 'askUser', status: 'success', result: 'Answered' } });
  assert.equal(part.tool.progress, 'Waiting');
  assert.equal(part.tool.question?.callId, 'q');
  stream.receive({ type: 'done' });
  assert.equal(part.tool.status, 'success');
});
