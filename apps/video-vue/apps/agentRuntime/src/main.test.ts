import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

test('private IPC streams deltas and acknowledges native Pi follow-up controls', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-ipc-'));
  const child = spawn(process.execPath, ['--experimental-strip-types', fileURLToPath(new URL('./main.ts', import.meta.url))], {
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const records: any[] = [];
  let stderr = '';
  let buffer = '';
  let requests = 0;
  child.stderr.setEncoding('utf8'); child.stderr.on('data', chunk => { stderr += chunk; });
  child.stdout.setEncoding('utf8'); child.stdout.on('data', chunk => {
    buffer += chunk;
    let index: number;
    while ((index = buffer.indexOf('\n')) >= 0) {
      const record = JSON.parse(buffer.slice(0, index)); buffer = buffer.slice(index + 1); records.push(record);
      if (record.type === 'request' && record.kind === 'model') {
        requests++;
        if (requests === 1) child.stdin.write(JSON.stringify({ type: 'control', command: { type: 'followUp', prompt: 'Continue blue.', controlId: 'ctrl-1' } }) + '\n');
        const text = requests === 1 ? 'First.' : 'Blue.';
        child.stdin.write(JSON.stringify({ id: record.id, event: { type: 'text_delta', delta: text } }) + '\n');
        child.stdin.write(JSON.stringify({ id: record.id, result: { role: 'assistant', api: record.payload.model.api,
          provider: 'managed', model: 'owner-model', timestamp: Date.now(),
          usage: { input: 10, output: 2, cacheRead: 0, cacheWrite: 0, totalTokens: 12,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
          stopReason: 'stop', content: [{ type: 'text', text }] } }) + '\n');
      }
    }
  });
  const exited = new Promise<number | null>((resolve, reject) => { child.on('exit', resolve); child.on('error', reject); });
  try {
    child.stdin.write(JSON.stringify({ config: { cwd: dir, sessionDir: join(dir, 'sessions'),
      model: { provider: 'managed', id: 'owner-model', contextWindow: 32768, maxTokens: 4096 },
      prompt: 'First instruction.', systemPrompt: '', tools: [], enableDelegation: false } }) + '\n');
    const exitCode = await exited;
    assert.equal(exitCode, 0, stderr);
    assert.equal(requests, 2);
    assert.ok(records.some(record => record.type === 'controlAccepted' && record.controlId === 'ctrl-1'));
    assert.equal(records.filter(record => record.type === 'event' && record.event.type === 'text').map(record => record.event.delta ?? '').join(''), 'First.Blue.');
    const result = records.find(record => record.type === 'result');
    assert.equal(result.text, 'Blue.');
    assert.equal(result.extraUserEntries[0].content, 'Continue blue.');
    assert.equal(result.parts.length, 2);
    assert.equal(result.stats.cost, null);
  } finally { child.kill(); await rm(dir, { recursive: true, force: true }); }
});
