import test from 'node:test';
import assert from 'node:assert/strict';
import { usageSummary } from './usageSummary.ts';
import { readFileSync } from 'node:fs';
test('Pi runtime empty children arrays retain usage and never blank the popover', () => {
  const usage = usageSummary({ tokens: { input: 10, output: 5, total: 15 }, children: [], cost: null, budget: { used: 2, limit: 40, remaining: 38 } });
  assert.equal(usage.tokens.total, 15);
  assert.deepEqual(usage.children, []);
  assert.equal(usage.cost, undefined);
  assert.deepEqual(usage.modelBudget, { used: 2, limit: 40, remaining: 38 });
});
test('Pi parent totals already include child tokens and must not be double counted', () => {
  const usage = usageSummary({ tokens: { input: 60, output: 40, total: 100 }, children: [
    { name: 'Writer', tokens: { input: 20, output: 10, total: 30 } }, { name: 'Waiting', tokens: null },
  ] });
  assert.equal(usage.tokens.total, 100);
  assert.equal(usage.childTokens.total, 30);
  assert.equal(usage.ownTokens.total, 70);
  assert.equal(usage.children[1]!.tokens, undefined);
});
test('partial historical snapshots and legacy aggregate children remain renderable', () => {
  assert.equal(usageSummary(undefined).tokens.total, 0);
  assert.equal(usageSummary({ tokens: null, children: [] }).tokens.total, 0);
  const usage = usageSummary({ tokens: { output: 10 }, children: { tokens: { output: 2 } }, elapsedMs: null, tokensPerSecond: NaN });
  assert.equal(usage.childTokens.output, 2);
  assert.equal(usage.ownTokens.output, 8);
  assert.equal(usage.tokensPerSecond, undefined);
});
test('production popover uses normalized runtime usage instead of unsafe child-array property access', () => {
  const source = readFileSync(new URL('./conversation.vue', import.meta.url), 'utf8');
  assert.match(source, /usageSummary\(stats.value\)/);
  assert.match(source, /statsSummary.tokens.output/);
  assert.doesNotMatch(source, /stats.children.tokens|stats.totals.tokens|stats.tokens.output/);
  assert.match(source, /尚无用量数据/);
});
