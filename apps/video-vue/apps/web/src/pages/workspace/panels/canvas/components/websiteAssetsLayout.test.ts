import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('./websiteAssets.vue', import.meta.url), 'utf8');
const style = source.slice(source.indexOf('<style scoped>'));
test('raw media cannot expand its preview track into the text area', () => {
  assert.match(style, /\.assetVisual\s*\{[^}]*overflow: hidden/);
  assert.match(style, /\.assetVisual\s*\{[^}]*display: flex/);
  assert.match(style, /\.assetVisual video, \.assetVisual img, \.assetVisual \.el-image\s*\{[^}]*max-height: 100%/);
});
test('long names have an independent bounded heading, not a checkbox label', () => {
  assert.match(source, /<h3 class="assetName" :title="item.name"/);
  assert.doesNotMatch(source, /<el-checkbox[^>]*><span[^>]*>\{\{ item.name \}\}/);
  assert.match(style, /-webkit-line-clamp: 2/);
  assert.match(style, /\.assetName\s*\{[^}]*height: 40px/);
});
test('filtering and batch actions wrap independently on small screens', () => {
  assert.match(source, /class="catalogFilters"/);
  assert.match(source, /class="catalogActions"/);
  assert.match(style, /@media \(max-width: 640px\)/);
  assert.match(style, /\.catalogSearch\s*\{ grid-column: 1 \/ -1/);
});
