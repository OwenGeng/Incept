import test from 'node:test';
import assert from 'node:assert/strict';
import { costLabel, eventCursor, runEventURL, supportedThinkingLevels } from './runtimeControls.ts';
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
