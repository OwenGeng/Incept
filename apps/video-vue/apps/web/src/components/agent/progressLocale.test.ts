import assert from 'node:assert/strict';
import test from 'node:test';
import { progressText } from './progressLocale.ts';
test('system status follows interface language and preserves dynamic names',()=>{
  assert.equal(progressText('仍在处理中，可点击停止；已发出的模型请求无法撤回。','en'),'Still processing. You can stop; requests already sent to the model cannot be recalled.');
  assert.equal(progressText('正在分析本轮请求（第 3 轮）…','en'),'Analyzing your request (round 3)…');
  assert.equal(progressText('正在准备附件：客户.png','en'),'Preparing attachment: 客户.png');
  assert.equal(progressText('正在执行 web_fetch…','en'),'Running web_fetch…');
  assert.equal(progressText('正在准备请求…','zh-CN'),'正在准备请求…');
  assert.equal(progressText('Customer-generated text','en'),'Customer-generated text');
});
