import assert from 'node:assert/strict';
import test from 'node:test';
import { restoredLocaleText } from './localeRestore.ts';
test('switching from an English first mount does not overwrite reactive Chinese labels',()=>{
  assert.equal(restoredLocaleText('Agent 设置','Agent settings','Agent settings'),'Agent 设置');
  assert.equal(restoredLocaleText('发送消息','Send message','Send message'),'发送消息');
});
test('legacy translated text restores its original Chinese while fresh component changes remain intact',()=>{
  assert.equal(restoredLocaleText('发送消息','发送消息','Send message'),'发送消息');
  assert.equal(restoredLocaleText('Send message','发送消息','Send message'),'发送消息');
  assert.equal(restoredLocaleText('客户内容',undefined,undefined),'客户内容');
});
