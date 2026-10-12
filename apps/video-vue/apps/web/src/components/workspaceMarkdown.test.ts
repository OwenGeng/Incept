import assert from 'node:assert/strict';
import test from 'node:test';
import { MarkdownAstParser } from '@markmend/ast';
import { resolveWorkspaceMarkdown, workspaceReferenceUrl } from './workspaceMarkdown.ts';

test('project references resolve through authenticated file reads without changing authored prose or code', () => {
  const tree = new MarkdownAstParser({ mode: 'static' }).markdownToAst('![Boat](generated/船.png) [Brief](brief.md)\n\n`generated/船.png`');
  resolveWorkspaceMarkdown(tree, 'project-a', 'http://localhost:3000');
  const rendered = JSON.stringify(tree);
  assert.match(rendered, /\/api\/workspaces\/files\/read\?directory=project-a&path=generated%2F/);
  assert.match(rendered, /path=brief.md/);
  assert.match(rendered, /"type":"inlineCode","value":"generated\/船.png"/);
});

test('unsafe paths and external destinations are never promoted to owned project references', () => {
  for (const value of ['../private.json', '.agent/secrets.json', 'a/../private.json', '%2e%2e/private', 'javascript:alert(1)', 'https://example.com/a.png', '//example.com/a', '/other-api', '#section'])
    assert.equal(workspaceReferenceUrl(value, 'project-a', 'http://localhost:3000'), value);
  assert.equal(workspaceReferenceUrl('brief.md', '', 'http://localhost:3000'), 'brief.md');
});
