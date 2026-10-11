import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runSession } from './runtime.ts';
import { SessionManager } from '@earendil-works/pi-coding-agent';

const model = { provider: 'managed', id: 'deployment-owned-model', contextWindow: 32768, maxTokens: 4096 };
const usage = { input: 20, output: 10, cacheRead: 0, cacheWrite: 0, totalTokens: 30,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };

function seedSdkSession(dir: string, contents: string[]) {
  const history = SessionManager.create(dir, join(dir, 'sessions'));
  contents.forEach((text, index) => history.appendMessage(index % 2
    ? { role: 'assistant', api: 'openai-completions', provider: model.provider, model: model.id,
      timestamp: Date.now(), usage, stopReason: 'stop', content: [{ type: 'text', text }] }
    : { role: 'user', content: text, timestamp: Date.now() }));
  return history.getSessionFile();
}

test('resend branches through Pi entry IDs and retains earlier tool receipts', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const observed: any[] = [];
  const bridge = async (kind: string, payload: any) => {
    if (kind === 'tool') return { draft: 'Bronco approved receipt' };
    observed.push(payload.context.messages);
    const hasReceipt = payload.context.messages.some((message: any) => message.role === 'toolResult');
    return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
      timestamp: Date.now(), usage, stopReason: hasReceipt ? 'stop' : 'toolUse',
      content: hasReceipt ? [{ type: 'text', text: 'Continue the approved draft.' }]
        : [{ type: 'toolCall', id: 'save-draft', name: 'canvas', arguments: {} }] };
  };
  const config = { cwd: dir, sessionDir: join(dir, 'sessions'), model, systemPrompt: '',
    tools: [{ name: 'canvas', description: 'Draft tool', parameters: { type: 'object', properties: {} } }] };
  try {
    const first = await runSession({ ...config, prompt: 'Keep Bronco draft.' }, bridge);
    assert.ok(first.userEntryId && first.assistantEntryId);
    const second = await runSession({ ...config, sessionFile: first.sessionFile, prompt: 'Abandon Tesla branch.' }, bridge);
    await runSession({ ...config, sessionFile: second.sessionFile, resumeEntryId: first.assistantEntryId,
      prompt: 'Confirmed, continue.' }, bridge);
    const resumed = JSON.stringify(observed.at(-1));
    assert.match(resumed, /Bronco approved receipt/);
    assert.doesNotMatch(resumed, /Abandon Tesla/);
    assert.ok(observed.at(-1).some((message: any) => message.role === 'toolResult'));
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('deleting an SDK user turn removes its tool receipts and downstream compaction content', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  let seen: any[] = [];
  const bridge = async (kind: string, payload: any) => {
    if (kind === 'tool') return { receipt: 'Tesla secret tool receipt' };
    seen = payload.context.messages;
    const userIndex = seen.findLastIndex(message => message.role === 'user');
    const removedTurn = JSON.stringify(seen[userIndex]).includes('Remove Tesla secret');
    const needsTool = removedTurn && !seen.slice(userIndex + 1).some(message => message.role === 'toolResult');
    return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
      timestamp: Date.now(), usage, stopReason: needsTool ? 'toolUse' : 'stop', content: needsTool
        ? [{ type: 'toolCall', id: 'tesla-tool', name: 'draft', arguments: {} }]
        : [{ type: 'text', text: 'Reply retained.' }] };
  };
  const config = { cwd: dir, sessionDir: join(dir, 'sessions'), model, systemPrompt: '',
    tools: [{ name: 'draft', description: 'Draft tool', parameters: { type: 'object', properties: {} } }] };
  try {
    const first = await runSession({ ...config, prompt: 'Keep Bronco.' }, bridge);
    const second = await runSession({ ...config, sessionFile: first.sessionFile, prompt: 'Remove Tesla secret.' }, bridge);
    assert.ok(seen.some(message => message.role === 'toolResult'));
    const journal = SessionManager.open(second.sessionFile!, config.sessionDir, dir);
    journal.appendCompaction('Summary containing Tesla secret tool receipt.', second.userEntryId, 60000);
    await runSession({ ...config, sessionFile: second.sessionFile, deletedEntryIds: [second.userEntryId], prompt: 'Continue.' }, bridge);
    assert.match(JSON.stringify(seen), /Keep Bronco/);
    assert.doesNotMatch(JSON.stringify(seen), /Tesla secret/);
    assert.ok(!seen.some(message => message.role === 'toolResult'));
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('actual SDK persists complete context and executes its own tool loop', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const observed: any[] = [];
  let calls = 0;
  let executedTools = 0;
  const bridge = async (kind: string, payload: any) => {
    if (kind === 'tool') { executedTools++; return { result: 'Saved draft node' }; }
    observed.push(payload.context);
    calls++;
    return { role: 'assistant', api: 'openai-completions', provider: model.provider, model: model.id,
      timestamp: Date.now(), usage, stopReason: calls === 1 ? 'toolUse' : 'stop',
      content: calls === 1 ? [{ type: 'toolCall', id: 'call-1', name: 'canvas', arguments: {} }]
        : [{ type: 'text', text: '3W Bronco: approved 30-second plan continues.' }] };
  };
  try {
    const first = await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model,
      prompt: 'Client 3W Liners Ford Bronco; approved 30-second plan.', systemPrompt: 'Continue existing work.',
      tools: [{ name: 'canvas', description: 'Create authorized draft node', parameters: { type: 'object', properties: {} } }],
      }, bridge);
    assert.equal(calls, 2);
    assert.equal(executedTools, 1);
    assert.deepEqual(observed[1].tools.map((tool: any) => tool.name).sort(), ['canvas', 'cancelSubAgent', 'delegateTask', 'listSubAgents', 'messageSubAgent'].sort());
    assert.equal(observed[1].messages.find((m: any) => m.role === 'toolResult').isError, false);
    assert.ok(observed[1].messages.some((m: any) => m.role === 'toolResult'));
    assert.match(first.text, /30-second/);
    await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), sessionFile: first.sessionFile, model,
      prompt: 'Continue.', systemPrompt: 'Continue existing work.', tools: [] }, bridge);
    assert.ok(JSON.stringify(observed.at(-1).messages).includes('Ford Bronco'));
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('provider failure does not invoke an alternate model or the old agent', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  try {
    await assert.rejects(runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model,
      prompt: 'Hello', systemPrompt: '', tools: [] }, async () => { throw Error('HTTP 400'); }), /400/);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('actual SDK automatically compacts long history and resumes approved work', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const requests: any[] = [];
  const largeModel = { ...model, contextWindow: 65536 };
  const bridge = async (_kind: string, payload: any) => {
    requests.push(payload);
    return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
      timestamp: Date.now(), usage: { ...usage, input: 60000, totalTokens: 60010 }, stopReason: 'stop',
      content: [{ type: 'text', text: payload.compacting ? '3W Ford Bronco: 30-second draft approved. Continue production, no paid authorization.' : 'Approved 30-second Bronco draft retained.' }] };
  };
  try {
    const config = { cwd: dir, sessionDir: join(dir, 'sessions'), model: largeModel,
      prompt: '3W Ford Bronco 30 seconds.', systemPrompt: 'Continue approved work.', tools: [],
      sessionFile: seedSdkSession(dir, Array.from({ length: 8 }, () => 'Approved 3W Bronco draft context. '.repeat(1500))) };
    const first = await runSession(config, bridge);
    await runSession({ ...config, sessionFile: first.sessionFile, prompt: 'Continue.' }, bridge);
    assert.ok(requests.some(request => request.compacting));
    assert.match(JSON.stringify(requests.at(-1).context.messages), /30-second/);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

for (const provider of ['openai', 'anthropic']) test(`${provider} uses the native SDK transport and only current image selection`, async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const originalFetch = globalThis.fetch;
  const requests: any[] = [];
  globalThis.fetch = async (_input, init) => {
    requests.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ error: { type: 'invalid_request_error', message: 'Simulated HTTP 400' } }),
      { status: 400, headers: { 'content-type': 'application/json' } });
  };
  try {
    await assert.rejects(runSession({ cwd: dir, sessionDir: join(dir, 'sessions'),
      model: { ...model, provider }, apiKey: 'test-only-key',
      images: [{ data: 'Y3VycmVudC1pbWFnZQ==', mimeType: 'image/png' }],
      prompt: 'Analyze my selection.', systemPrompt: 'Inspect current selection only.', tools: [],
      sessionFile: seedSdkSession(dir, ['Historical request without replaying its binary image.', 'Previous review.'])
      }, async () => { throw Error('Native transport must not call Python model adapter'); }), /400/);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].model, model.id);
    const messages = provider === 'openai' ? requests[0].input : requests[0].messages;
    assert.ok(!JSON.stringify(messages[0]).includes('Y3VycmVudC1pbWFnZQ=='));
    assert.ok(JSON.stringify(messages.at(-1)).includes('Y3VycmVudC1pbWFnZQ=='));
  } finally {
    globalThis.fetch = originalFetch;
    await rm(dir, { recursive: true, force: true });
  }
});

test('bridge sends genuine text deltas before final response and does not replay them', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const events: any[] = [];
  let released = false;
  try {
    const result = await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model,
      prompt: 'Stream please.', systemPrompt: '', tools: [] }, async (_kind, payload, _signal, onDelta) => {
      onDelta?.({ type: 'text_delta', delta: 'Hello ' });
      await new Promise(resolve => setTimeout(resolve, 10));
      assert.ok(events.some(event => event.type === 'text' && event.delta === 'Hello '));
      assert.equal(released, false);
      onDelta?.({ type: 'text_delta', delta: 'world.' });
      released = true;
      return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), usage, stopReason: 'stop', content: [{ type: 'text', text: 'Hello world.' }] };
    }, event => events.push(event));
    assert.equal(events.filter(event => event.type === 'text').map(event => event.delta ?? '').join(''), 'Hello world.');
    assert.equal(events.findLast(event => event.type === 'text').done, true);
    assert.equal(result.parts[0].content, result.text);
    assert.equal(result.stats.tokens.total, 30);
    assert.equal(result.stats.cost, null);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

for (const commandType of ['steer', 'followUp'] as const) test(`actual SDK handles ${commandType} and persists added user entry`, async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  let control: any;
  const contexts: any[] = [];
  const controlsEvents: any[] = [];
  try {
    const result = await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model,
      prompt: 'First instruction.', systemPrompt: '', tools: [] }, async (_kind, payload) => {
      contexts.push(payload.context.messages);
      if (contexts.length === 1) await control({ type: commandType, prompt: 'Use blue.' });
      return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), usage, stopReason: 'stop', content: [{ type: 'text', text: contexts.length === 1 ? 'First answer.' : 'Blue answer.' }] };
    }, event => controlsEvents.push(event), { register(handler) { control = handler; } });
    assert.equal(contexts.length, 2);
    assert.match(JSON.stringify(contexts[1]), /Use blue/);
    assert.equal(result.text, 'Blue answer.');
    assert.equal(result.extraUserEntries.length, 1);
    const journal = SessionManager.open(result.sessionFile!, join(dir, 'sessions'), dir);
    assert.equal(journal.getEntry(result.userEntryId)?.type, 'message');
    assert.equal(result.extraUserEntries[0].content, 'Use blue.');
    const consumed = controlsEvents.find(event => event.type === 'userMessage');
    assert.equal(consumed.id, result.extraUserEntries[0].id);
    assert.equal(consumed.content, 'Use blue.');
    assert.equal(result.messageEntries.filter(entry => entry.role === 'user').length, 2);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('configured supported thinking level reaches Pi bridge; unsupported models use off', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const levels: any[] = [];
  const bridge = async (_kind: string, payload: any) => {
    levels.push(payload.thinkingLevel);
    return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
      timestamp: Date.now(), usage, stopReason: 'stop', content: [{ type: 'text', text: 'Answer.' }] };
  };
  try {
    await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model: { ...model, reasoning: true },
      thinkingLevel: 'high', prompt: 'Think.', systemPrompt: '', tools: [] }, bridge);
    await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model,
      thinkingLevel: 'high', prompt: 'Think.', systemPrompt: '', tools: [] }, bridge);
    assert.deepEqual(levels, ['high', 'off']);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('delegation uses a separate persistent Pi journal, scopes tools, reports, and resumes', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const saved = new Map<string, any>();
  const events: any[] = [];
  let childFile: string | undefined;
  let childToolId = '';
  const bridge = async (kind: string, payload: any) => {
    if (kind === 'tool') {
      if (payload.name === 'subAgentSession') {
        if (payload.arguments.action === 'save') { saved.set(payload.arguments.file, payload.arguments); return { saved: true }; }
        return saved.get(payload.arguments.file);
      }
      childToolId = payload.id;
      assert.equal(payload.conversationFile, childFile);
      return { receipt: 'child draft' };
    }
    const messages = payload.context.messages;
    const user = messages.findLast((message: any) => message.role === 'user');
    const userText = typeof user.content === 'string' ? user.content : user.content.map((part: any) => part.text ?? '').join('');
    const isChild = userText.includes('child task') || userText.includes('Continue child');
    const receipt = messages.some((message: any) => message.role === 'toolResult');
    if (isChild) {
      assert.ok(!payload.context.tools.some((tool: any) => tool.name === 'delegateTask'));
      if (userText.includes('Continue child')) assert.match(JSON.stringify(messages), /child draft/);
    }
    const toolCall = isChild ? { type: 'toolCall', id: 'child-write', name: 'canvas', arguments: {} }
      : { type: 'toolCall', id: 'delegate-1', name: childFile ? 'messageSubAgent' : 'delegateTask',
        arguments: childFile ? { file: childFile, prompt: 'Continue child' } : { name: 'Research', task: 'child task' } };
    return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
      timestamp: Date.now(), usage, stopReason: receipt ? 'stop' : 'toolUse',
      content: receipt ? [{ type: 'text', text: isChild ? 'Child result.' : 'Parent result.' }] : [toolCall] };
  };
  const config = { cwd: dir, sessionDir: join(dir, 'sessions'), model, conversationFile: 'agent/parent.json',
    systemPrompt: '', tools: [{ name: 'canvas', description: 'Draft tool', parameters: { type: 'object', properties: {} } }] };
  try {
    const first = await runSession({ ...config, prompt: 'Parent task.' }, bridge, event => {
      events.push(event); if (event.type === 'subAgent') childFile = event.agent.file;
    });
    const metadata = saved.get(childFile!);
    assert.ok(metadata.sessionFile.startsWith(join(config.sessionDir, 'children')));
    assert.notEqual(metadata.sessionFile, first.sessionFile);
    assert.match(childToolId, /^[a-f0-9]{32}:child-write$/);
    assert.ok(events.some(event => event.type === 'report' && event.content === 'Child result.'));
    assert.ok(events.some(event => event.type === 'subAgentEvent' && event.event.type === 'tool' && event.event.tool.id === childToolId));
    assert.ok(metadata.parts.some((part: any) => part.type === 'tool' && part.tool.id === childToolId));
    const priorJournal = metadata.sessionFile;
    await runSession({ ...config, prompt: 'Parent continuation.' }, bridge);
    assert.notEqual(saved.get(childFile!).sessionFile, priorJournal);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('shared delegation budget is enforced by Pi stream wrapper without another model loop', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  let calls = 0;
  try {
    await assert.rejects(runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model,
      prompt: 'Task.', systemPrompt: '', maxModelCalls: 1,
      tools: [{ name: 'canvas', description: 'Draft', parameters: { type: 'object', properties: {} } }] }, async (kind, payload) => {
      if (kind === 'tool') return { receipt: 'draft' };
      calls++;
      return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), usage, stopReason: 'toolUse', content: [{ type: 'toolCall', id: 'write', name: 'canvas', arguments: {} }] };
    }), /budget exhausted/);
    assert.equal(calls, 1);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

for (const abortType of ['abortChild', 'abort'] as const) test(`actual SDK ${abortType} cancels delegated work and persists its status`, async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  let control: any;
  let childFile: string | undefined;
  let cancelled = false;
  const saved: any[] = [];
  const events: any[] = [];
  const bridge = async (kind: string, payload: any, signal?: AbortSignal) => {
    if (kind === 'tool') { if (payload.name === 'subAgentSession') saved.push(payload.arguments); return { saved: true }; }
    const user = payload.context.messages.findLast((message: any) => message.role === 'user');
    const userText = typeof user.content === 'string' ? user.content : user.content.map((part: any) => part.text ?? '').join('');
    if (userText === 'child cancel task') return new Promise((_resolve, reject) => {
      signal?.addEventListener('abort', () => { cancelled = true; reject(Error('cancelled child')); }, { once: true });
      queueMicrotask(() => { void control({ type: abortType, ...(abortType === 'abortChild' ? { childFile } : {}) }); });
    });
    const done = payload.context.messages.some((message: any) => message.role === 'toolResult');
    return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
      timestamp: Date.now(), usage, stopReason: done ? 'stop' : 'toolUse', content: done
        ? [{ type: 'text', text: 'Parent continued after child cancellation.' }]
        : [{ type: 'toolCall', id: 'delegate-cancel', name: 'delegateTask', arguments: { name: 'Child', task: 'child cancel task' } }] };
  };
  try {
    const operation = runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model, conversationFile: 'agent/parent.json',
      prompt: 'Cancel test.', systemPrompt: '', tools: [] }, bridge, event => {
      events.push(event); if (event.type === 'subAgent') childFile = event.agent.file;
    }, { register(handler) { control = handler; } });
    if (abortType === 'abort') await assert.rejects(operation, /cancel|abort/);
    else assert.match((await operation).text, /Parent continued/);
    assert.equal(cancelled, true);
    assert.equal(saved.at(-1).status, 'cancelled');
    assert.ok(saved.at(-1).sessionFile.includes('/children/'));
    assert.ok(events.some(event => event.type === 'subAgent' && event.agent.status === 'cancelled'));
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('delegation can be disabled by host and does not expose filesystem or global tools', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  try {
    await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model, enableDelegation: false,
      prompt: 'Limited session.', systemPrompt: '', tools: [] }, async (_kind, payload) => {
      assert.deepEqual(payload.context.tools, []);
      return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), usage, stopReason: 'stop', content: [{ type: 'text', text: 'Answer.' }] };
    });
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('configured team roles run concurrently as SDK sessions and usage aggregates their reports', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const events: any[] = [];
  const childContexts: any[] = [];
  let childrenStarted = 0;
  let releaseChildren: () => void;
  const allChildrenStarted = new Promise<void>(resolve => { releaseChildren = resolve; });
  const bridge = async (kind: string, payload: any) => {
    if (kind === 'tool') return { saved: true };
    const isChild = payload.context.systemPrompt.includes('Configured team role:');
    if (isChild) {
      childContexts.push(payload.context);
      if (++childrenStarted === 2) releaseChildren!();
      await allChildrenStarted;
    }
    const done = isChild || payload.context.messages.some((message: any) => message.role === 'toolResult');
    return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
      timestamp: Date.now(), usage, stopReason: done ? 'stop' : 'toolUse', content: done
        ? [{ type: 'text', text: isChild ? 'Team role result.' : 'Combined team result.' }]
        : [{ type: 'toolCall', id: 'team-call', name: 'delegateTeam', arguments: { task: 'Assigned team task.', ids: ['editor', 'critic'] } }] };
  };
  try {
    const result = await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model, conversationFile: 'agent/parent.json',
      prompt: 'Run configured team.', systemPrompt: '', tools: [], teamAgents: [
        { id: 'editor', name: 'Editor', instructions: 'Improve clarity.' },
        { id: 'critic', name: 'Critic', instructions: 'Check factual claims.' },
      ] }, bridge, event => events.push(event));
    assert.equal(childrenStarted, 2);
    assert.ok(childContexts.some(context => context.systemPrompt.includes('Improve clarity.')));
    assert.ok(childContexts.some(context => context.systemPrompt.includes('Check factual claims.')));
    assert.ok(childContexts.every(context => context.tools.length === 0));
    assert.equal(events.filter(event => event.type === 'report').length, 2);
    assert.equal(result.stats.tokens.total, 120);
    assert.equal(result.stats.children.length, 2);
    assert.equal(result.stats.modelCalls, 4);
    assert.equal(result.stats.budget.used, 4);
    assert.equal(result.stats.runOutputTokens, 40);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('team delegation rejects unconfigured role IDs without creating a child', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'linglonglab-pi-'));
  const events: any[] = [];
  let persisted = 0;
  try {
    await runSession({ cwd: dir, sessionDir: join(dir, 'sessions'), model, conversationFile: 'agent/parent.json',
      prompt: 'Team.', systemPrompt: '', tools: [], teamAgents: [{ id: 'editor', name: 'Editor', instructions: 'Edit.' }] }, async (kind, payload) => {
      if (kind === 'tool') { persisted++; return {}; }
      const receipt = payload.context.messages.find((message: any) => message.role === 'toolResult');
      if (receipt) { assert.equal(receipt.isError, true); assert.match(JSON.stringify(receipt.content), /Unknown configured team role/); }
      return { role: 'assistant', api: payload.model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), usage, stopReason: receipt ? 'stop' : 'toolUse', content: receipt
          ? [{ type: 'text', text: 'Role unavailable.' }]
          : [{ type: 'toolCall', id: 'bad-team', name: 'delegateTeam', arguments: { task: 'Task.', ids: ['unconfigured'] } }] };
    }, event => events.push(event));
    assert.equal(persisted, 0);
    assert.ok(!events.some(event => event.type === 'subAgent'));
  } finally { await rm(dir, { recursive: true, force: true }); }
});
