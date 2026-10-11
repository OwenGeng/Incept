import test from 'node:test';
import assert from 'node:assert/strict';
import { ref } from 'vue';
import { createConversationStream, readAgentEvents } from './replyStream.ts';
import type { AgentEvent } from '@linglonglab/video-runtime-types/agent/types';
import type { AgentMessage } from './types';
import { usageSummary } from './usageSummary.ts';

// These fixtures follow the public events emitted by Toonflow-app's native
// agent/runtime/index.ts, delegation.ts, sessions.ts and tools/subAgent.ts.
// Native block IDs address content slots; tool IDs address model calls.
const nativeTool: Extract<AgentEvent, { type: 'tool' }> = {
  type: 'tool', blockId: '1:1',
  tool: { id: 'call_delegate', name: 'subAgent', status: 'running', args: { tasks: [
    { name: 'Writer', task: 'Write an original scene.' }, { name: 'Researcher', task: 'Find the missing detail.' },
  ] } },
};
const nativeChild: Extract<AgentEvent, { type: 'subAgent' }> = {
  type: 'subAgent', agent: { file: '2026-10-12_child.jsonl', parentFile: '2026-10-12_parent.jsonl',
    name: 'Writer', task: 'Write an original scene.', status: 'running', providerId: 'configured-provider', modelId: 'configured-model' },
};
const nativeQuestion: Extract<AgentEvent, { type: 'question' }> = {
  type: 'question', toolCallId: 'call_question', callId: 'question-uuid',
  title: 'Confirm the scene', question: 'Where does it happen?', options: ['Studio', 'Street'],
};
const toolPart = (messages: AgentMessage[], toolId: string) => {
  const part = messages.flatMap(message => message.parts ?? []).find(part => part.type === 'tool' && part.tool.id === toolId);
  if (!part || part.type !== 'tool') throw Error(`Missing tool ${toolId}`);
  return part;
};

async function nativeEvents(events: AgentEvent[]) {
  const response = new Response(events.map(event => JSON.stringify(event)).join('\n') + '\n');
  const result: AgentEvent[] = [];
  for await (const event of readAgentEvents(response, new AbortController().signal)) result.push(event);
  return result;
}

test('native subAgent argument/progress/final updates merge by content block without requiring delegateTask', () => {
  const messages = ref<AgentMessage[]>([]);
  const stream = createConversationStream(messages);
  stream.receive({ type: 'userMessage', id: 'user-entry', content: 'Build the scene.' });
  stream.receive(structuredClone(nativeTool));
  stream.receive({ type: 'tool', blockId: '1:1', tool: { id: 'call_delegate', name: 'subAgent', status: 'running',
    result: JSON.stringify({ tasks: [{ name: 'Writer', status: 'running', result: 'Writing' }, { name: 'Researcher', status: 'running', result: 'Checking' }] }) } });
  const partial = toolPart(messages.value, 'call_delegate');
  assert.equal(partial.id, '1:1');
  assert.equal(partial.tool.args?.tasks instanceof Array, true);
  assert.match(partial.tool.result!, /Writing/);
  stream.receive({ type: 'tool', blockId: '1:1', tool: { id: 'call_delegate', name: 'subAgent', status: 'success',
    result: JSON.stringify({ tasks: [{ name: 'Writer', status: 'completed', result: 'Scene saved.' }, { name: 'Researcher', status: 'inputRequired', result: 'Need a location.', taskId: 'a2a-task', contextId: 'a2a-context' }] }) } });
  stream.receive({ type: 'done' });
  assert.equal(messages.value.flatMap(message => message.parts ?? []).filter(part => part.type === 'tool').length, 1);
  assert.equal(partial.tool.status, 'success');
  assert.match(partial.tool.result!, /inputRequired/);
});

test('native child events, reports and compaction remain observable without terminating the parent stream', async () => {
  const expected: AgentEvent[] = [
    { type: 'session', file: nativeChild.agent.parentFile }, { type: 'compaction', active: true }, { type: 'compaction', active: false },
    nativeChild,
    { type: 'subAgentEvent', file: nativeChild.agent.file, event: { type: 'session', file: nativeChild.agent.file } },
    { type: 'subAgentEvent', file: nativeChild.agent.file, event: { type: 'error', message: 'Need more input' } },
    { type: 'subAgentEvent', file: nativeChild.agent.file, event: { type: 'done' } },
    { type: 'subAgent', agent: { ...nativeChild.agent, status: 'inputRequired', result: 'Need more input' } },
    { type: 'report', file: nativeChild.agent.file, parentFile: nativeChild.agent.parentFile, name: 'Writer', content: 'Task feedback, not a user instruction.', id: 'report-id' },
    { type: 'text', blockId: '2:0', content: 'Parent final response.', done: true }, { type: 'done' },
  ];
  assert.deepEqual(await nativeEvents(expected), expected);
});

test('native child question uses tool call identity while content slots and sibling tool calls stay independent', () => {
  const messages = ref<AgentMessage[]>([]);
  const stream = createConversationStream(messages);
  stream.receive({ type: 'userMessage', id: 'child-user', content: 'Write the scene.' });
  stream.receive({ type: 'tool', blockId: '1:0', tool: { id: 'call_question', name: 'askUser', args: {}, status: 'running' } });
  stream.receive(nativeQuestion);
  const question = toolPart(messages.value, 'call_question');
  assert.equal(question.id, '1:0');
  assert.equal(question.tool.question?.callId, 'question-uuid');
  assert.deepEqual(question.tool.question?.options, ['Studio', 'Street']);
  stream.receive({ type: 'tool', blockId: '1:0', tool: { id: 'call_question', name: 'askUser', status: 'success', result: '{"answer":"Studio"}' } });
  stream.receive({ type: 'text', blockId: '2:0', delta: 'Scene' });
  stream.receive({ type: 'text', blockId: '2:0', content: 'Scene in a studio.', done: true });
  stream.receive({ type: 'text', blockId: '2:0', content: 'Scene in a studio.', done: true }); // Native message_end repeats the completed block.
  stream.receive({ type: 'done' });
  assert.equal(messages.value.at(-1)!.content, 'Scene in a studio.');
  assert.equal(question.tool.status, 'success');
});

test('active native snapshot continues existing parts and receives hosted question scope without losing tool identities', () => {
  const messages = ref<AgentMessage[]>([
    { id: 'user-entry', entryId: 'user-entry', role: 'user', content: 'Write.' },
    { id: 'assistant-entry', entryId: 'assistant-entry', replyTo: 'user-entry', role: 'assistant', content: '', streaming: true,
      parts: [{ id: '1:0', type: 'tool', tool: { id: 'call_question', name: 'askUser', args: {}, status: 'running',
        question: { ...nativeQuestion, callId: nativeQuestion.callId, sessionFile: 'agent/child.json', runId: 'child-run' } } }] },
  ]);
  const stream = createConversationStream(messages);
  stream.receive({ ...nativeQuestion, sessionFile: 'agent/child.json', runId: 'child-run' });
  stream.receive({ type: 'tool', blockId: '1:0', tool: { id: 'call_question', name: 'askUser', status: 'success', result: '{"answer":"Street"}' } });
  stream.receive({ type: 'done' });
  assert.equal(messages.value.length, 2);
  const part = toolPart(messages.value, 'call_question');
  assert.equal(part.tool.question?.sessionFile, 'agent/child.json');
  assert.equal(part.tool.question?.runId, 'child-run');
  assert.equal(part.tool.status, 'success');
});

test('native accepted acknowledgment ends only the separate request stream and keeps the live child stream open', async () => {
  const messages = ref<AgentMessage[]>([]);
  const stream = createConversationStream(messages);
  stream.receive({ type: 'userMessage', id: 'child-initial', content: 'Start.' });
  stream.receive({ type: 'text', blockId: '1:0', delta: 'Working' });
  assert.deepEqual(await nativeEvents([{ type: 'accepted' }]), [{ type: 'accepted' }]);
  assert.equal(messages.value.at(-1)!.streaming, true);
  stream.receive({ type: 'text', blockId: '1:0', content: 'Working with the added detail.', done: true });
  stream.receive({ type: 'userMessage', id: 'child-steer', content: 'Added detail.' });
  stream.receive({ type: 'text', blockId: '2:0', content: 'Continued.', done: true });
  stream.receive({ type: 'done' });
  assert.equal(messages.value.filter(message => message.role === 'user').length, 2);
  assert.equal(messages.value.at(-1)!.content, 'Continued.');
});

test('native journal stats already include toolResult delegated usage and render when optional hosted extras are absent', () => {
  const usage = usageSummary({ tokens: { input: 120, output: 80, cacheRead: 10, cacheWrite: 0, total: 210 }, tokensPerSecond: 4 });
  assert.equal(usage.tokens.total, 210);
  assert.equal(usage.children.length, 0);
  assert.equal(usage.cost, undefined);
  assert.equal(usage.modelBudget, undefined);
});
