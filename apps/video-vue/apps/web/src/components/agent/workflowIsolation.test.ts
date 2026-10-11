import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('chat does not render automatic or legacy research consent cards', () => {
  const source = readFileSync(new URL('./conversation.vue', import.meta.url), 'utf8');
  const template = source.slice(0, source.indexOf('<script'));
  assert.doesNotMatch(template, /researchChoiceCard|researchQuestion/);
});

test('website collection remains a localized standalone Asset Library entry', () => {
  const source = readFileSync(new URL('../../pages/workspace/panels/canvas/components/assetLibrary.vue', import.meta.url), 'utf8');
  assert.match(source, /t\('网站素材采集 · 图片 \/ 视频 \/ Logo', 'Website asset collection · Images \/ Videos \/ Logos'\)/);
  assert.match(source, /<websiteAssets[^>]+:directory="directory"/);
});
