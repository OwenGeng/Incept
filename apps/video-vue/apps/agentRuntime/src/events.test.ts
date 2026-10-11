import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createEventProjector, safeValue } from './events.ts';

test('tool cards include streamed args, progress and results with secrets/binary removed', () => {
  const emitted: any[] = [];
  const projector = createEventProjector(event => emitted.push(event));
  projector.accept({ type: 'message_update', assistantMessageEvent: { type: 'toolcall_delta', contentIndex: 0,
    partial: { content: [{ type: 'toolCall', id: '1', name: 'draft', arguments: { apiKey: 'secret', prompt: 'make draft' } }] } } });
  projector.accept({ type: 'tool_execution_start', toolCallId: '1', toolName: 'draft', args: {} });
  projector.accept({ type: 'tool_execution_update', toolCallId: '1', toolName: 'draft', partialResult: { progress: 0.5 } });
  projector.accept({ type: 'tool_execution_end', toolCallId: '1', toolName: 'draft', isError: false,
    result: { content: [{ type: 'text', text: JSON.stringify({ apiKey: 'private', data: 'binary', result: 'Saved.' }) }] } });
  assert.equal(emitted.length, 4);
  assert.equal(emitted[0].tool.args.apiKey, '[redacted]');
  assert.match(emitted[2].tool.result, /0.5/);
  assert.equal(emitted[3].tool.status, 'success');
  assert.doesNotMatch(JSON.stringify(emitted), /private|binary|secret/);
  assert.equal(projector.parts.length, 1);
});

test('reasoning events are never forwarded and active tool cancellation is persisted', () => {
  const events: any[] = [];
  const projector = createEventProjector(event => events.push(event));
  projector.accept({ type: 'message_update', assistantMessageEvent: { type: 'thinking_delta', delta: 'private reasoning' } });
  assert.equal(events.length, 0);
  projector.accept({ type: 'tool_execution_start', toolCallId: '1', toolName: 'draft', args: {} });
  projector.interrupt();
  assert.equal(events.at(-1).tool.status, 'interrupted');
  assert.equal(projector.parts[0].tool.status, 'interrupted');
  assert.equal(safeValue('data:image/png;base64,Ymln')[0], '[');
});

test('large tool summaries stay within the durable display event budget', () => {
  const events: any[] = [];
  const projector = createEventProjector(event => events.push(event));
  const large = Object.fromEntries(Array.from({ length: 100 }, (_, index) => [`field${index}`, 'large receipt '.repeat(2000)]));
  projector.accept({ type: 'tool_execution_start', toolCallId: 'large', toolName: 'draft', args: large });
  projector.accept({ type: 'tool_execution_end', toolCallId: 'large', toolName: 'draft', result: { details: large } });
  assert.ok(events.every(event => Buffer.byteLength(JSON.stringify(event)) < 256 * 1024));
  assert.match(events.at(-1).tool.result, /truncated/);
  for (const text of ['🎬'.repeat(20000), '\u0000'.repeat(30000)]) {
    const unicode = Object.fromEntries(Array.from({ length: 100 }, (_, index) => [`field${index}`, text]));
    projector.accept({ type: 'tool_execution_start', toolCallId: text.slice(0, 4), toolName: 'draft', args: unicode });
    projector.accept({ type: 'tool_execution_end', toolCallId: text.slice(0, 4), toolName: 'draft', result: { details: unicode } });
  }
  assert.ok(events.every(event => Buffer.byteLength(JSON.stringify(event)) < 256 * 1024));
});
