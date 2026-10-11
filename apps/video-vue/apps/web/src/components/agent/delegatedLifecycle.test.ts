import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { canApplyDelegatedSnapshot, isDelegationTerminal } from './delegatedLifecycle.ts';
test('completed, failed and cancelled child updates end delegated observation, but questions do not', () => {
  for (const status of ['completed', 'error', 'limited', 'cancelled']) assert.equal(isDelegationTerminal(status), true);
  for (const status of ['running', 'inputRequired', 'pending']) assert.equal(isDelegationTerminal(status), false);
});
test('old parent completion cannot overwrite or stop a child being continued directly', () => {
  assert.equal(canApplyDelegatedSnapshot(true, false, false), true);
  assert.equal(canApplyDelegatedSnapshot(true, true, true), false);
  assert.equal(canApplyDelegatedSnapshot(true, false, true), false);
  assert.equal(canApplyDelegatedSnapshot(false, false, false), false);
});
test('production parent updates both the live child state and canonical child conversation', () => {
  const parent = readFileSync(new URL('./index.vue', import.meta.url), 'utf8');
  assert.match(parent, /isDelegationTerminal\(event.agent.status\)/);
  assert.match(parent, /finishDelegatedRun\(\)/);
  assert.match(parent, /void refreshDelegatedConversation\(child\)/);
  assert.match(parent, /readConversation\(directory, item.file!\)/);
  assert.match(parent, /view.applySnapshot\(session\)/);
  const child = readFileSync(new URL('./conversation.vue', import.meta.url), 'utf8');
  assert.match(child, /canApplyDelegatedSnapshot\(parentObserved.value, busy.value, !!controller\)/);
  assert.match(child, /defineExpose\(\{ receiveEvent, finishDelegatedRun, applySnapshot, releaseSnapshotLoading \}\)/);
});
