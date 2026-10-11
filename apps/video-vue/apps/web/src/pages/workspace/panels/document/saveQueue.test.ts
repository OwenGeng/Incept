import assert from 'node:assert/strict';
import test from 'node:test';
import { flushUntilStable } from './saveQueue.ts';
test('flush waits for edits entered during an in-flight save before allowing close', async () => {
  let draft = 'first', saved = '', calls = 0;
  await flushUntilStable(async () => {
    const current = draft;
    calls++;
    if (calls === 1) draft = 'last typing';
    await Promise.resolve();
    saved = current;
  }, () => saved !== draft);
  assert.equal(saved, 'last typing');
  assert.equal(calls, 2);
});
test('save errors reject flush and preserve dirty state rather than permit close', async () => {
  await assert.rejects(flushUntilStable(async () => { throw new Error('conflict'); }, () => true), /conflict/);
});
test('panel flush also drains an early-finished tab edited while another tab saves', async () => {
  let a = 'draft', savedA = '', rounds = 0;
  await flushUntilStable(async () => {
    rounds++;
    await Promise.all([
      Promise.resolve().then(() => { savedA = a; }),
      Promise.resolve().then(async () => { await Promise.resolve(); if (rounds === 1) a = 'typed while another tab saves'; }),
    ]);
  }, () => a !== savedA);
  assert.equal(savedA, 'typed while another tab saves');
  assert.equal(rounds, 2);
});
