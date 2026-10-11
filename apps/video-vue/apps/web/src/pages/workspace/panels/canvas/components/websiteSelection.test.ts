import assert from 'node:assert/strict';
import test from 'node:test';
import { importBatches, selectAssetIds, filterAssets, previewUrl } from './websiteSelection.ts';

test('selection retains imported assets, deduplicates and caps at 20', () => {
  assert.deepEqual(selectAssetIds(['a'], 'a', true), ['a']);
  assert.deepEqual(selectAssetIds(['a','b'], 'a', false), ['b']);
  assert.equal(selectAssetIds(Array.from({length:20},(_,i)=>String(i)), 'new', true).length,20);
});
test('imports only selected missing assets in safe batches, never whole catalog', () => {
  const assets = Array.from({length:30},(_,i)=>({id:String(i),status:i===0?'imported':'discovered',name:'item',kind:'image'}));
  const batches = importBatches(assets, assets.slice(0,20).map(a=>a.id));
  assert.deepEqual(batches.map(b=>b.length),[12,7]);
  assert.equal(batches.flat().includes('0'),false);
  assert.equal(batches.flat().includes('20'),false);
});
test('filters by type, status, name and product URL without inferring media content', () => {
  const assets = [{id:'a',kind:'video',status:'discovered',name:'Bronco',product_url:'https://client.test/products/bronco'}];
  assert.equal(filterAssets(assets,'video','discovered','bronco').length,1);
  assert.equal(filterAssets(assets,'image','all','').length,0);
  assert.equal(filterAssets(assets,'all','imported','').length,0);
});
test('previews reject non HTTPS, credentials and local destinations', () => {
  for(const url of ['javascript:alert(1)','http://client.test/a','https://user:pass@client.test/a','https://127.0.0.1/a','https://localhost/a']) assert.equal(previewUrl(url),'');
  assert.equal(previewUrl('https://cdn.client.test/a.jpg'),'https://cdn.client.test/a.jpg');
});
