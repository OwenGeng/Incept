import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const directory=new URL('./native/',import.meta.url);
const sha=(text:string)=>createHash('sha256').update(text).digest('hex');
const body=(text:string)=>text.replace(/^\s*import\b[\s\S]*?;/gm,'').replace(/\s+/g,' ').trim();
test('eleven native modules match pinned upstream bytes and preserve executable lifecycle bodies',async()=>{
 const manifest=JSON.parse(await readFile(new URL('provenance.json',directory),'utf8'));
 const source=JSON.parse(await readFile(new URL(manifest.sourceBaseline,directory),'utf8'));
 assert.equal(manifest.commit,'acdf33ce4ec0c33dac3bccf2d6d7c03f4d2f6807');assert.equal(manifest.modules.length,11);
 for(const module of manifest.modules){
  assert.equal(sha(source[module.source]),module.sha256,module.source+' pinned source bytes');
  assert.equal(sha(body(source[module.source])),module.bodySha256,module.source+' source lifecycle body');
  const vendor=await readFile(new URL(module.vendored,directory),'utf8');
  assert.equal(sha(body(vendor)),module.vendoredBodySha256,module.vendored+' raw body drift');
  let normalized=vendor;
  for(const rewrite of module.moduleLinkRewrites){assert.ok(normalized.includes(rewrite.to));normalized=normalized.replace(rewrite.to,rewrite.from);}
  assert.equal(sha(body(normalized)),module.bodySha256,module.vendored+' executable native lifecycle drift');
 }
 const license=await readFile(new URL('LICENSE',directory),'utf8');assert.match(license,/MIT License/);assert.match(license,/HBAI/);
});
