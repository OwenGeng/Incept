import assert from 'node:assert/strict';
import test from 'node:test';
import { nativePhraseEntries, nativeSystemText, nativeToolResult } from '@linglonglab/video-runtime-types/agent/locale';
import { readAgentEvents } from './replyStream.ts';

test('native owned phrases follow both locales without Chinese in English chrome',()=>{
  for(const [zh,en] of nativePhraseEntries){
    assert.doesNotMatch(en,/\p{Script=Han}/u);
    assert.equal(nativeSystemText(zh,'en'),en);
    assert.equal(nativeSystemText(en,'zh-CN'),zh);
  }
  assert.equal(nativeSystemText('正在调用 memory','en'),'Calling memory');
  assert.equal(nativeSystemText('客户原创内容','en'),'客户原创内容');
});
test('refreshed native task receipts localize pending status without altering task names or completed work',()=>{
  const original=JSON.stringify({tasks:[{name:'客户角色',status:'running',result:'准备执行'},
    {name:'Writer',status:'completed',result:'准备执行'}]});
  const en=JSON.parse(nativeToolResult(original,'subAgent','en') as string);
  assert.equal(en.tasks[0].name,'客户角色');assert.equal(en.tasks[0].result,'Preparing task');
  assert.equal(en.tasks[1].result,'准备执行');
  assert.equal(JSON.parse(nativeToolResult(JSON.stringify(en),'subAgent','zh-CN') as string).tasks[0].result,'准备执行');
  assert.equal(nativeToolResult('已上报父 Agent','report','en'),'Reported to parent agent');
});
test('English stream errors cover HTTP failure, missing body and interrupted transport',async()=>{
  for(const [response,pattern] of [
    [new Response(null,{status:503}),/Request failed \(503\)/],
    [new Response(null),/No response stream/],
    [new Response(''),/connection was interrupted/],
    [new Response(JSON.stringify({detail:{message:'对话正在运行，请等待回复完成'}}),{status:409}),/conversation is running/],
  ] as const){
    await assert.rejects(async()=>{for await(const event of readAgentEvents(response,new AbortController().signal,'en'))void event;},pattern);
  }
});
