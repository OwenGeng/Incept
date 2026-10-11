import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import { importBatches } from './websiteSelection.ts';

const source = readFileSync(new URL('./websiteAssets.vue', import.meta.url),'utf8');
const handlers = source.slice(source.indexOf('async function importSelected()'),source.indexOf('function download('));
const js = ts.transpileModule(handlers,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
function fixture(failBatch = 0) {
  const assets = {value:Array.from({length:30},(_,i)=>({id:String(i),name:String(i),status:i===0?'imported':'discovered'}))};
  const selected = {value:assets.value.slice(0,20).map(a=>a.id)}, importing={value:false}, error={value:''}, notice={value:''};
  const calls: string[][] = [], attached:string[] = [];
  const props={directory:'project'};
  const axios={post:async (_url:string,body:{asset_ids:string[]})=>{
    calls.push(body.asset_ids);
    if(calls.length===failBatch) throw new Error('batch failed');
    return {data:{data:{assets:body.asset_ids.map(id=>({id,name:id,status:'imported'})),imported_count:body.asset_ids.length,failed_count:0}}};
  }};
  const busy={get value(){return importing.value;}};
  const methods = new Function('assets','selected','importing','error','notice','busy','props','axios','importBatches','emit','showError','attach',
    `let requestVersion=0; ${js}; return {importSelected,attachSelected};`)(assets,selected,importing,error,notice,busy,props,axios,importBatches,()=>{},(e:Error)=>{error.value=e.message;},(item:{id:string})=>{attached.push(item.id);return true;});
  return {...methods,assets,selected,calls,attached,error,importing};
}
test('selection action imports only missing selected assets and attaches without sending',async()=>{
  const state=fixture(); await state.attachSelected();
  assert.deepEqual(state.calls.map((c:string[])=>c.length),[12,7]);
  assert.equal(state.attached.length,20);
  assert.equal(state.assets.value[20].status,'discovered');
  assert.equal(state.selected.value.length,20);
});
test('partial network failure preserves imported files and selection for retry, does not attach',async()=>{
  const state=fixture(2); await state.attachSelected();
  assert.equal(state.assets.value.filter((a:{status:string})=>a.status==='imported').length,13);
  assert.equal(state.attached.length,0);
  assert.equal(state.selected.value.length,20);
  assert.equal(state.importing.value,false);
  await state.attachSelected();
  assert.equal(state.calls[2].length,7);
  assert.equal(state.attached.length,20);
});
