/** Private, long-lived native SDK host. Authentication and business authority stay in Python. */
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const MAX_BYTES = 64 * 1024 * 1024;
const MAX_PENDING = 64;
export type HostBridge = (kind: string, payload: any, signal?: AbortSignal, onDelta?: (event: any) => void) => Promise<any>;
export type HostRunner = (config: any, bridge: HostBridge, send: (event: any) => void,
  controls: { signal: AbortSignal; register(handler: (command: any) => Promise<void> | void): void }) => Promise<any>;

type Pending = { resolve(value: any): void; reject(error: Error): void; onDelta?: (event: any) => void };
type Run = { id: string; controller: AbortController; pending: Map<string, Pending>;
  emit(record: any): void; control(command: any): void; abort(reason: string): void };

function authenticate(request: IncomingMessage, secret: string) {
  const value = request.headers['x-linglonglab-native-host'];
  if (typeof value !== 'string') return false;
  const actual = Buffer.from(value), expected = Buffer.from(secret);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

async function readBody(request: IncomingMessage, maximum = MAX_BYTES) {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const raw of request) {
    const chunk = Buffer.isBuffer(raw) ? raw : Buffer.from(raw);
    size += chunk.length;
    if (size > maximum) throw Error('Private host request exceeds the transport budget');
    chunks.push(chunk);
  }
  const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('Private host request must be an object');
  return value;
}

function json(response: ServerResponse, status: number, value: any) {
  response.writeHead(status, { 'content-type': 'application/json', connection: 'close' });
  response.end(JSON.stringify(value));
}

export async function createNativeHost(options: { secret: string; generation?: string; runner: HostRunner; maxParents?: number }) {
  if (typeof options.secret !== 'string' || options.secret.length < 32) throw Error('Private host secret is required');
  const maximum = options.maxParents ?? 5;
  if (!Number.isInteger(maximum) || maximum < 1 || maximum > 20) throw Error('Invalid native host admission budget');
  const generation = options.generation ?? randomBytes(16).toString('hex');
  const runs = new Map<string, Run>();
  let closing = false;
  const redact = (error: unknown, config?: any) => {
    let value = String(error).replaceAll(options.secret, '[redacted]');
    if (typeof config?.apiKey === 'string' && config.apiKey) value = value.replaceAll(config.apiKey, '[redacted]');
    return value.slice(0, 2000);
  };
  const server = createServer((request, response) => {
    void (async () => {
      if (!authenticate(request, options.secret)) { json(response, 401, { error: 'Private host authentication failed' }); return; }
      if (request.method === 'GET' && request.url === '/ready') {
        json(response, closing ? 503 : 200, { generation, activeParents: runs.size, maxParents: maximum }); return;
      }
      if (request.method === 'POST' && request.url === '/shutdown') {
        json(response, 202, { closing: true }); void shutdown(); return;
      }
      if (closing) { json(response, 503, { error: 'Native host is shutting down' }); return; }
      if (request.method === 'POST' && request.url === '/run') {
        const body = await readBody(request);
        if (typeof body.runId !== 'string' || !/^[a-f0-9]{32}$/.test(body.runId) || !body.config || typeof body.config !== 'object' || Array.isArray(body.config)) {
          json(response, 400, { error: 'Invalid native host run' }); return;
        }
        if (runs.has(body.runId)) { json(response, 409, { error: 'Run identity is already active' }); return; }
        if (runs.size >= maximum) {
          json(response, 409, { error: `Native host is at its ${maximum} active parent run limit; wait for another run to finish.` }); return;
        }
        response.writeHead(200, { 'content-type': 'application/x-ndjson', connection: 'close', 'x-native-host-generation': generation });
        response.flushHeaders();
        const controller = new AbortController(), pending = new Map<string, Pending>();
        let sequence = 0, finished = false, ending = false, queuedBytes = 0, paused = false;
        let controlHandler: ((command: any) => Promise<void> | void) | undefined;
        let controlTail = Promise.resolve();
        const queuedControls: any[] = [], output: string[] = [];
        const drain = () => {
          if (paused || response.destroyed) return;
          while (output.length) {
            const line = output.shift()!;
            queuedBytes -= Buffer.byteLength(line);
            if (!response.write(line)) { paused = true; return; }
          }
          if (ending) response.end();
        };
        response.on('drain', () => { paused = false; drain(); });
        const abort = (reason: string) => {
          if (!controller.signal.aborted) controller.abort(Error(reason));
          for (const item of pending.values()) item.reject(Error(reason));
          pending.clear();
        };
        const emit = (record: any) => {
          if (finished || response.destroyed) return;
          const line = JSON.stringify(record) + '\n', bytes = Buffer.byteLength(line);
          if (bytes > MAX_BYTES || queuedBytes + response.writableLength + bytes > MAX_BYTES || output.length >= 256) {
            abort('Native host event transport budget exhausted'); response.destroy(); return;
          }
          output.push(line); queuedBytes += bytes; drain();
        };
        const dispatch = (command: any) => {
          if (!controlHandler) {
            if (queuedControls.length >= 100) throw Error('Native host control queue is full');
            queuedControls.push(command); return;
          }
          controlTail = controlTail.then(() => controlHandler!(command)).then(() => {
            emit({ type: 'controlAccepted', controlId: command?.controlId });
          }).catch(error => { emit({ type: 'controlError', controlId: command?.controlId, message: redact(error, body.config) }); });
        };
        const run: Run = { id: body.runId, controller, pending, emit, control: dispatch, abort };
        runs.set(run.id, run);
        response.on('close', () => { if (!ending) abort('Native host client disconnected'); });
        const timeout = setTimeout(() => abort('Native SDK attempt exceeded 1800 seconds'), 1800_000);
        timeout.unref();
        const bridge: HostBridge = (kind, payload, signal, onDelta) => new Promise((resolveBridge, rejectBridge) => {
          if (controller.signal.aborted || signal?.aborted) { rejectBridge(Error('Cancelled')); return; }
          if (pending.size >= MAX_PENDING) { rejectBridge(Error('Native callback budget exhausted')); return; }
          const id = `${run.id}:${++sequence}`;
          const cancelled = () => {
            pending.delete(id); cleanup(); rejectBridge(Error('Cancelled'));
          };
          const cleanup = () => {
            signal?.removeEventListener('abort', cancelled); controller.signal.removeEventListener('abort', cancelled);
          };
          signal?.addEventListener('abort', cancelled, { once: true });
          controller.signal.addEventListener('abort', cancelled, { once: true });
          pending.set(id, { onDelta, resolve(value) { cleanup(); resolveBridge(value); }, reject(error) { cleanup(); rejectBridge(error); } });
          emit({ type: 'request', id, kind, payload });
        });
        void options.runner(body.config, bridge, event => emit({ type: 'event', event }), {
          signal: controller.signal,
          register(handler) { controlHandler = handler; for (const command of queuedControls.splice(0)) dispatch(command); },
        }).then(result => { emit({ ...result, type: 'result' }); }).catch(error => {
          emit({ type: 'error', message: redact(error, body.config) });
        }).finally(() => {
          clearTimeout(timeout); abort('Native SDK attempt finished'); runs.delete(run.id);
          ending = true; drain(); finished = true;
        });
        return;
      }
      const match = /^\/run\/([a-f0-9]{32})\/(reply|control|abort)$/.exec(request.url ?? '');
      if (request.method !== 'POST' || !match) { json(response, 404, { error: 'Unknown native host operation' }); return; }
      const run = runs.get(match[1]);
      if (!run) { json(response, 410, { error: 'Native host run is no longer active' }); return; }
      const body = await readBody(request, match[2] === 'control' ? 256 * 1024 : MAX_BYTES);
      if (run.controller.signal.aborted) { json(response, 410, { error: 'Native host run was cancelled' }); return; }
      if (match[2] === 'abort') { run.abort('Cancelled by the authenticated host'); json(response, 202, { cancelled: true }); return; }
      if (match[2] === 'control') {
        if (!body.command || typeof body.command !== 'object' || Array.isArray(body.command)) { json(response, 400, { error: 'Invalid native control' }); return; }
        run.control(body.command); json(response, 202, { accepted: true }); return;
      }
      const item = typeof body.id === 'string' && body.id.startsWith(run.id + ':') ? run.pending.get(body.id) : undefined;
      if (!item) { json(response, 409, { error: 'Callback identity is stale or belongs to another run' }); return; }
      if ('event' in body) {
        if (body.event?.type !== 'text_delta' || typeof body.event.delta !== 'string') { json(response, 400, { error: 'Invalid callback delta' }); return; }
        item.onDelta?.(body.event); json(response, 202, { delivered: true }); return;
      }
      if (!('result' in body) && typeof body.error !== 'string') { json(response, 400, { error: 'Missing callback result' }); return; }
      run.pending.delete(body.id);
      if (typeof body.error === 'string') item.reject(Error(body.error)); else item.resolve(body.result);
      json(response, 202, { delivered: true });
    })().catch(error => {
      if (!response.headersSent) json(response, 400, { error: redact(error) }); else response.destroy();
    });
  });
  server.requestTimeout = 30_000;
  server.headersTimeout = 10_000;
  await new Promise<void>((resolveListen, reject) => {
    server.once('error', reject); server.listen(0, '127.0.0.1', () => { server.removeListener('error', reject); resolveListen(); });
  });
  const address = server.address();
  if (!address || typeof address === 'string') throw Error('Native host failed to bind loopback');
  const shutdown = async () => {
    if (closing) return;
    closing = true;
    for (const run of runs.values()) run.abort('Native host is shutting down');
    await new Promise<void>(resolveClose => {
      server.close(() => resolveClose());
      const timer = setTimeout(() => { server.closeAllConnections(); resolveClose(); }, 2000);
      timer.unref();
    });
  };
  return { port: address.port, generation, shutdown };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { runSession } = await import('./nativeRuntime.ts');
  const host = await createNativeHost({ secret: process.env.LINGLONGLAB_NATIVE_HOST_TOKEN ?? '',
    generation: process.env.LINGLONGLAB_NATIVE_HOST_GENERATION,
    maxParents: Number(process.env.LINGLONGLAB_NATIVE_HOST_MAX_PARENTS ?? 5), runner: runSession as HostRunner });
  process.stdout.write(JSON.stringify({ type: 'ready', port: host.port, generation: host.generation }) + '\n');
  for (const signal of ['SIGTERM', 'SIGINT'] as const) process.once(signal, () => { void host.shutdown(); });
}
