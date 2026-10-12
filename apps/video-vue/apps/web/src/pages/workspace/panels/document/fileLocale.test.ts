import assert from 'node:assert/strict';
import test from 'node:test';
import { workspaceFileLabel, documentSystemText } from './fileLocale.ts';

test('recognized default canvases have English display aliases while Chinese labels remain unchanged', () => {
  assert.equal(workspaceFileLabel('画布1.json', 'canvas', 'en'), 'Canvas1.json');
  assert.equal(workspaceFileLabel('画布12.json', 'canvas', 'en-US'), 'Canvas12.json');
  assert.equal(workspaceFileLabel('画布1.json', 'canvas', 'zh-CN'), '画布1.json');
});
test('ordinary files, folders and custom canvas names retain their authored names', () => {
  for (const type of ['file', 'directory', 'node'])
    assert.equal(workspaceFileLabel('画布1.json', type, 'en'), '画布1.json');
  assert.equal(workspaceFileLabel('客户方案.json', 'canvas', 'en'), '客户方案.json');
  assert.equal(workspaceFileLabel('Canvas1.json', 'canvas', 'en'), 'Canvas1.json');
});
test('search errors translate owned explanations and preserve real path prefixes', () => {
  assert.equal(documentSystemText('客户/方案.md: 替换结果超过 5 MiB 上限', 'en'), '客户/方案.md: The replacement exceeds the 5 MiB limit');
  assert.equal(documentSystemText('查找内容不能为空', 'en'), 'Search text is required');
  assert.equal(documentSystemText('查找内容不能为空', 'zh-CN'), '查找内容不能为空');
  assert.equal(documentSystemText('客户的自定义内容', 'en'), '客户的自定义内容');
});
