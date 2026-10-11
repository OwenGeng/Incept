type Candidate = { id: string; kind: string; status: string; name: string; product_url?: string };
export function selectAssetIds(ids: string[], id: string, checked: boolean) {
  return checked ? [...new Set([...ids, id])].slice(0,20) : ids.filter(value=>value!==id);
}
export function importBatches(assets: Candidate[], ids: string[]) {
  const missing = assets.filter(item=>ids.includes(item.id) && item.status!=='imported').map(item=>item.id);
  const batches: string[][] = [];
  for(let i=0;i<missing.length;i+=12) batches.push(missing.slice(i,i+12));
  return batches;
}
export function filterAssets<T extends Candidate>(assets: T[], kind: string, status: string, query: string): T[] {
  const search = query.trim().toLowerCase();
  return assets.filter(item=>(kind==='all'||item.kind===kind) && (status==='all'||item.status===status)
    && (!search||`${item.name} ${item.product_url??''}`.toLowerCase().includes(search)));
}
// Discovery has already validated public URLs server-side. Reject obviously unsafe persisted values too.
export function previewUrl(value: string) {
  try {
    const url = new URL(value);
    if(url.protocol!=='https:'||url.username||url.password||url.port && url.port!=='443'
      || /^(localhost|.*\.local|.*\.localhost|\[.*\]|[\d.]+)$/i.test(url.hostname)) return '';
    return url.href;
  } catch { return ''; }
}
