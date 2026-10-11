type Snapshot = { text: string; revision: string; encoding: 'utf-8' | 'utf-8-bom' | 'utf-16le' | 'utf-16be' };
type Entry = { path: string; name: string; type: 'file' | 'directory' };
type SearchIO = { list: (path: string) => Promise<{ entries: Entry[] }>; readTextSnapshot: (path: string, signal?: AbortSignal) => Promise<Snapshot> };
export type SearchFile = { path: string; snapshot: Snapshot; count: number; matches: { line: number; text: string }[] };
export type SearchResult = { files: SearchFile[]; errors: string[]; partial: boolean; scanned: number };
const defaultLimits = { directories: 1000, files: 1000, bytes: 20 * 1024 * 1024, matches: 500 };

export function countLiteral(text: string, query: string) {
  if (!query) return 0;
  let count = 0;
  let offset = 0;
  while ((offset = text.indexOf(query, offset)) !== -1) { count++; offset += query.length; }
  return count;
}

export function replaceLiteral(text: string, query: string, replacement: string) {
  if (!query) throw new Error('查找内容不能为空');
  return text.split(query).join(replacement);
}

export async function replaceSearchFiles(files: SearchFile[], query: string, replacement: string,
  write: (file: SearchFile, text: string) => Promise<unknown>, canWrite: (path: string) => boolean,
  onSaved: () => void = () => {}) {
  for (const file of files) {
    if (!canWrite(file.path)) throw new Error(`${file.path}: 文件已打开或工作区已切换，停止替换`);
    const length = file.snapshot.text.length + file.count * (replacement.length - query.length);
    if (length > 5 * 1024 * 1024) throw new Error(`${file.path}: 替换结果超过 5 MiB 上限`);
    const text = replaceLiteral(file.snapshot.text, query, replacement);
    const bytes = file.snapshot.encoding.startsWith('utf-16') ? text.length * 2 : new TextEncoder().encode(text).byteLength;
    if (bytes > 5 * 1024 * 1024) throw new Error(`${file.path}: 替换结果超过 5 MiB 上限`);
    try { await write(file, text); }
    catch { throw new Error(`${file.path}: 保存失败或内容已被修改，已停止。请重新搜索以读取最新版本。`); }
    onSaved();
  }
}

/** Read-only, bounded scan. Binary/canvas/assets/config are deliberately excluded. */
export async function scanDocuments(io: SearchIO, query: string, signal?: AbortSignal, overrides: Partial<typeof defaultLimits> = {}): Promise<SearchResult> {
  if (!query || query.length > 1000) throw new Error('查找内容需要 1–1000 个字符');
  const limits = { ...defaultLimits, ...overrides };
  const result: SearchResult = { files: [], errors: [], partial: false, scanned: 0 };
  const pending = [''];
  const visited = new Set<string>();
  let directories = 0, bytes = 0, matches = 0;
  while (pending.length) {
    if (signal?.aborted || directories >= limits.directories) { result.partial = true; break; }
    const path = pending.shift()!;
    if (visited.has(path)) continue;
    visited.add(path); directories++;
    let entries: Entry[];
    try { entries = (await io.list(path)).entries; }
    catch (error) { result.errors.push(`${path || '/'}: ${error instanceof Error ? error.message : '无法读取目录'}`); continue; }
    for (const entry of entries) {
      if (signal?.aborted) { result.partial = true; return result; }
      if (entry.type === 'directory') {
        if (!entry.name.startsWith('.') && !['node_modules', 'assets', 'dist', 'build'].includes(entry.name.toLowerCase())) {
          if (pending.length + directories < limits.directories) pending.push(entry.path);
          else result.partial = true;
        }
        continue;
      }
      if (!/\.(md|markdown|txt)$/i.test(entry.name) || entry.name.startsWith('.')) continue;
      if (result.scanned >= limits.files || bytes >= limits.bytes || matches >= limits.matches) { result.partial = true; return result; }
      result.scanned++;
      try {
        const snapshot = await io.readTextSnapshot(entry.path, signal);
        const size = snapshot.encoding.startsWith('utf-16') ? snapshot.text.length * 2 : new TextEncoder().encode(snapshot.text).byteLength;
        if (bytes + size > limits.bytes) { result.partial = true; return result; }
        bytes += size;
        const count = countLiteral(snapshot.text, query);
        if (!count) continue;
        const previews: SearchFile['matches'] = [];
        let line = 1, start = 0, offset = 0;
        while ((offset = snapshot.text.indexOf(query, offset)) !== -1 && previews.length < Math.min(20, limits.matches - matches)) {
          for (let index = start; index < offset; index++) if (snapshot.text[index] === '\n') line++;
          start = offset;
          const lineStart = snapshot.text.lastIndexOf('\n', offset - 1) + 1;
          const lineEnd = snapshot.text.indexOf('\n', offset);
          previews.push({ line, text: snapshot.text.slice(Math.max(lineStart, offset - 80), Math.min(lineEnd === -1 ? snapshot.text.length : lineEnd, offset + query.length + 120)) });
          offset += query.length;
        }
        result.files.push({ path: entry.path, snapshot, count, matches: previews });
        matches += count;
        if (matches >= limits.matches) result.partial = true;
      } catch (error) {
        if (signal?.aborted) { result.partial = true; return result; }
        result.errors.push(`${entry.path}: ${error instanceof Error ? error.message : '读取失败'}`);
      }
    }
  }
  return result;
}
