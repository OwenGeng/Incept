// Private JSONL process transport. The host owns authentication and tool permissions.
import { runSession } from './runtime.ts';
import { buildSystemPrompt } from './toonflowPrompt.ts';

const write = (value: any) => process.stdout.write(JSON.stringify(value) + '\n');
const pending = new Map<string, { resolve: (value: any) => void; reject: (error: Error) => void; onDelta?: (event: any) => void }>();
let controlHandler: ((command: any) => Promise<void>) | undefined;
const controls: any[] = [];
const dispatchControl = (record: any) => {
  if (!controlHandler) { if (controls.length < 100) controls.push(record); return; }
  void controlHandler(record.command).then(() => write({ type: 'controlAccepted', controlId: record.controlId ?? record.command?.controlId }))
    .catch(error => write({ type: 'controlError', controlId: record.controlId ?? record.command?.controlId, message: String(error) }));
};
let started = false;
let buffer = '';
let nextId = 0;
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  buffer += chunk;
  if (Buffer.byteLength(buffer) > 64 * 1024 * 1024) { process.stderr.write('IPC record too large\n'); process.exit(1); }
  let boundary: number;
  while ((boundary = buffer.indexOf('\n')) >= 0) {
    const line = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 1);
    if (!line.trim()) continue;
    let record: any;
    try { record = JSON.parse(line); }
    catch { write({ type: 'error', message: 'Invalid private IPC record' }); process.exit(1); }
    if (!started) {
      started = true;
      const config = record.config;
      config.systemPrompt = buildSystemPrompt({ tools: config.tools, platform: process.platform })
        .replace('你是 Toonflow 的 AI 创作搭档', '你是 LinglongLab 的 AI 创作搭档') + '\n\n' + config.systemPrompt;
      const bridge = (kind: string, payload: any, signal?: AbortSignal, onDelta?: (event: any) => void) => new Promise((resolve, reject) => {
        const id = String(++nextId);
        const abort = () => { pending.delete(id); reject(Error('Cancelled')); };
        signal?.addEventListener('abort', abort, { once: true });
        if (signal?.aborted) { reject(Error('Cancelled')); return; }
        pending.set(id, { onDelta, resolve: value => { signal?.removeEventListener('abort', abort); resolve(value); },
          reject: error => { signal?.removeEventListener('abort', abort); reject(error); } });
        write({ type: 'request', id, kind, payload });
      });
      void runSession(config, bridge, event => write({ type: 'event', event }), {
        register(handler) { controlHandler = handler; for (const record of controls.splice(0)) dispatchControl(record); },
      }).then(result => { write({ type: 'result', text: result.text, sessionFile: result.sessionFile,
        userEntryId: result.userEntryId, assistantEntryId: result.assistantEntryId,
        parts: result.parts, stats: result.stats, contextUsage: result.contextUsage, extraUserEntries: result.extraUserEntries, messageEntries: result.messageEntries }); process.stdin.destroy(); })
        .catch(error => { write({ type: 'error', message: String(error) }); process.stdin.destroy(); process.exitCode = 1; });
    } else {
      if (record.type === 'control') { dispatchControl(record); continue; }
      const request = pending.get(record.id);
      if (!request) continue;
      if (record.event) { if (record.event.type === 'text_delta' && typeof record.event.delta === 'string') request.onDelta?.(record.event); continue; }
      pending.delete(record.id);
      if (record.error) request.reject(Error(record.error)); else request.resolve(record.result);
    }
  }
});
process.stdin.on('end', () => { for (const request of pending.values()) request.reject(Error('Host disconnected')); });
