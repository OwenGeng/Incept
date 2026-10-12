import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync, readdirSync } from 'node:fs';
import { nativePhraseEntries } from '../../../packages/runtimeTypes/agent-locale.ts';
test('every pinned upstream static Chinese error has an English boundary translation',()=>{
  const known=new Set(nativePhraseEntries.map(([zh])=>zh));
  for(const folder of ['runtime','tools'])for(const name of readdirSync(new URL(`./native/upstream/${folder}/`,import.meta.url))){
    const source=readFileSync(new URL(`./native/upstream/${folder}/${name}`,import.meta.url),'utf8');
    for(const match of source.matchAll(/new Error\("([^"\n]+)"\)/g)){
      if(/\p{Script=Han}/u.test(match[1]!))assert.ok(known.has(match[1]!),`Missing translation: ${match[1]}`);
    }
  }
});
