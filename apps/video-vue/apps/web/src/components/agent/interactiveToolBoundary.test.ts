import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('production tool messages embed a question card for arbitrary tools without a renderer registry', () => {
  const source = readFileSync(new URL('./toolMessage.vue', import.meta.url), 'utf8');
  const template = source.slice(source.indexOf('<template>'), source.indexOf('<script setup'));
  const card = template.match(/<questionCard\b([^>]+)\/>/s)?.[1];
  assert.ok(card, 'the question form must be in the production page template');
  assert.match(card, /v-if="tool.question \|\| tool.name === 'askUser'"/);
  for (const field of ['tool', 'directory', 'sessionFile', 'runId']) {
    assert.ok(card.includes(`:${field}="`), `question answers need ${field}`);
  }
  assert.match(source, /import questionCard from ["'].*packages\/tools\/askUser\/src\/questionCard.vue["']/);
  assert.match(source, /if \(tool.question \|\| name === "askUser" \|\| name === "subAgent"\) return/);
  assert.doesNotMatch(source, /该工具未提供可用的交互组件/);
});

test('shared skill catalog exposes individual switches without a nonfunctional catalog toggle', () => {
  const source = readFileSync(new URL('./resourcePanel.vue', import.meta.url), 'utf8');
  assert.match(source, /v-if="resource !== 'skills'" class="resourceToggle"/);
  assert.match(source, /:model-value="skill.enabled"/);
  assert.match(source, /shared across all projects/);
});
