import { randomUUID } from 'node:crypto';
import { join, resolve, sep } from 'node:path';
import { mkdir } from 'node:fs/promises';
import type { ToolDefinition } from '@earendil-works/pi-coding-agent';
import type { Bridge, Config, Control } from './runtime.ts';

const names = ['delegateTask', 'messageSubAgent', 'listSubAgents', 'cancelSubAgent', 'delegateTeam'];
const filePattern = /^agent\/([a-f0-9]{32})\.json$/;
const emptyTokens = () => ({ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 });
type Child = { agent: any; control?: (command: Control) => Promise<void>; result?: any; promise?: Promise<any>; cancelled?: boolean };

export function createDelegationTools(config: Config, bridge: Bridge, send: (event: any) => void, runSession: typeof import('./runtime.ts').runSession) {
  let runOutputTokens = 0;
  const children = new Map<string, Child>();
  const enabled = config.enableDelegation !== false;
  const persist = async (child: Child) => {
    const saved = await bridge('tool', { id: `child-save-${randomUUID()}`, name: 'subAgentSession', arguments: {
      ...child.result, ...child.agent, action: 'save',
    }, conversationFile: config.conversationFile });
    if (saved?.status === 'cancelled' && child.agent.status !== 'cancelled') {
      child.cancelled = true; throw Error('Child Agent cancelled');
    }
  };
  const publish = (child: Child) => send({ type: 'subAgent', agent: { ...child.agent } });
  const cancel = async (file: string) => {
    const child = children.get(file);
    if (!child) throw Error('Sub-agent is not running in this request');
    if (child.agent.status === 'cancelled') return;
    if (child.agent.status !== 'running') throw Error('Sub-agent has already ended');
    child.cancelled = true;
    if (child.control) await child.control({ type: 'abort' });
  };
  const launch = async (child: Child, prompt: string, parentSignal?: AbortSignal) => {
    const match = filePattern.exec(child.agent.file);
    if (!match) throw Error('Invalid sub-agent identity');
    const sessionDir = join(config.sessionDir, 'children', match[1]);
    await mkdir(sessionDir, { recursive: true });
    const sessionFile = child.result?.sessionFile;
    if (sessionFile && !resolve(sessionFile).startsWith(resolve(sessionDir) + sep))
      throw Error('Sub-agent journal is outside its authorized directory');
    const scopeEvent = (event: any) => event.type === 'tool' ? { ...event,
      id: `tool-${match[1]}:${event.tool.id}`, blockId: `tool-${match[1]}:${event.tool.id}`,
      tool: { ...event.tool, id: `${match[1]}:${event.tool.id}` } } : event;
    const abort = () => { void cancel(child.agent.file).catch(() => {}); };
    parentSignal?.addEventListener('abort', abort, { once: true });
    if (child.agent.teamId && !config.teamAgents?.some(role => role.id === child.agent.teamId))
      throw Error('Sub-agent team role is no longer configured');
    child.agent.providerId = config.model.provider; child.agent.modelId = config.model.id;
    child.agent.thinkingLevel = config.model.reasoning ? config.thinkingLevel ?? 'off' : 'off';
    child.agent.status = 'running'; child.cancelled = false; publish(child);
    const scopedBridge: Bridge = (kind, payload, signal, onDelta) => bridge(kind,
      { ...payload, ...(kind === 'tool' ? { id: `${match[1]}:${payload.id}` } : {}),
        conversationFile: child.agent.file, parentFile: config.conversationFile }, signal, onDelta);
    child.promise = (async () => {
      try {
        await persist(child);
        child.result = await runSession({ ...config, sessionDir, sessionFile,
          conversationFile: child.agent.file, prompt, onSessionCreated(file) { child.result = { ...child.result, sessionFile: file }; },
          onCheckpoint(snapshot) { child.result = { ...child.result, ...snapshot, parts: snapshot.parts.map(scopeEvent) }; }, resumeEntryId: undefined, deletedEntryIds: child.result?.deletedEntryIds,
          enableDelegation: false, images: undefined,
          tools: config.tools.filter(tool => !names.includes(tool.name)),
          systemPrompt: config.systemPrompt + (child.agent.teamId ? '\nConfigured team role:\n' + (config.teamAgents?.find(role => role.id === child.agent.teamId)?.instructions ?? '') : '') + '\nYou are a delegated LinglongLab agent. Work only on the assigned task; report results and unresolved limits clearly.',
        }, scopedBridge, event => send({ type: 'subAgentEvent', file: child.agent.file, event: scopeEvent(event) }), {
          register(handler) { child.control = handler; if (parentSignal?.aborted || child.cancelled) void handler({ type: 'abort' }); },
        });
        runOutputTokens += child.result.stats.runOutputTokens;
        child.result.parts = child.result.parts.map(scopeEvent);
        child.agent.status = 'completed'; child.agent.result = child.result.text;
        await persist(child);
        publish(child);
        send({ type: 'report', parentFile: config.conversationFile ?? '', file: child.agent.file,
          name: child.agent.name, content: child.result.text, id: randomUUID() });
        return { file: child.agent.file, status: 'completed', result: child.result.text };
      } catch (error) {
        child.agent.status = child.cancelled || parentSignal?.aborted || /cancelled|canceled|aborted/i.test(String(error)) ? 'cancelled'
          : String(error).includes('budget exhausted') ? 'limited' : 'error';
        // Error summaries are public transport errors only; never dump model messages.
        child.agent.result = (config.apiKey ? String(error).replaceAll(config.apiKey, '[redacted]') : String(error)).slice(0, 2000); publish(child);
        await persist(child).catch(() => {});
        return { file: child.agent.file, status: child.agent.status, error: child.agent.result };
      } finally { child.control = undefined; parentSignal?.removeEventListener('abort', abort); }
    })();
    return child.promise;
  };
  const tool = (name: string, description: string, properties: any, required: string[], execute: (args: any, signal?: AbortSignal) => Promise<any>): ToolDefinition => ({
    name, label: name, description, parameters: { type: 'object', properties, required, additionalProperties: false } as any,
    executionMode: name === 'delegateTask' || name === 'delegateTeam' ? 'parallel' : 'sequential', async execute(_id, args, signal) {
      const result = await execute(args, signal);
      return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result };
    },
  });
  const tools = !enabled ? [] : [
    tool('delegateTask', 'Run an independent Pi agent on one scoped task, inheriting authorized tools and the shared model budget. Waits for and reports its result.',
      { name: { type: 'string', maxLength: 100 }, task: { type: 'string', maxLength: 20000 } }, ['name', 'task'], async (args, signal) => {
        if (!args.name?.trim() || !args.task?.trim()) throw Error('Sub-agent name and task are required');
        if (children.size >= 4) throw Error('Sub-agent limit reached (4 per request)');
        const file = `agent/${randomUUID().replaceAll('-', '')}.json`;
        const child: Child = { agent: { file, parentFile: config.conversationFile ?? '', name: args.name.slice(0, 100),
          task: args.task, status: 'running', providerId: config.model.provider, modelId: config.model.id,
          thinkingLevel: config.model.reasoning ? config.thinkingLevel ?? 'off' : 'off' } };
        children.set(file, child); return launch(child, args.task, signal);
      }),
    tool('messageSubAgent', 'Continue an existing independent Pi agent using its durable journal.',
      { file: { type: 'string', pattern: filePattern.source }, prompt: { type: 'string', maxLength: 20000 } }, ['file', 'prompt'], async (args, signal) => {
        if (!filePattern.test(args.file) || !args.prompt?.trim()) throw Error('Invalid sub-agent continuation');
        let child = children.get(args.file);
        if (!child) {
          if (children.size >= 4) throw Error('Sub-agent limit reached (4 per request)');
          const saved = await bridge('tool', { id: `child-get-${randomUUID()}`, name: 'subAgentSession',
            arguments: { action: 'get', file: args.file }, conversationFile: config.conversationFile });
          if (!saved || saved.parentFile !== config.conversationFile || !saved.sessionFile)
            throw Error('Sub-agent does not belong to this conversation or has no resumable journal');
          child = { agent: { file: saved.file, parentFile: saved.parentFile, name: saved.name, task: saved.task,
            providerId: saved.providerId, modelId: saved.modelId, thinkingLevel: saved.thinkingLevel, teamId: saved.teamId }, result: saved };
          children.set(args.file, child);
        }
        if (child.control) { await child.control({ type: 'followUp', prompt: args.prompt }); return { file: args.file, status: 'queued' }; }
        return launch(child, args.prompt, signal);
      }),
    tool('listSubAgents', 'List delegated tasks created or continued during this request.', {}, [], async () => [...children.values()].map(child => child.agent)),
    tool('cancelSubAgent', 'Cancel an active delegated Pi task.', { file: { type: 'string', pattern: filePattern.source } }, ['file'], async args => {
      await cancel(args.file); return { file: args.file, status: 'cancelled' };
    }),
  ];
  if (enabled && config.teamAgents?.length) tools.push(tool('delegateTeam',
    'Run selected configured team roles in independent Pi sessions concurrently. Inherits authorized business tools and the shared budget; maximum 4 delegates per request.',
    { task: { type: 'string', maxLength: 20000 }, ids: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 4, uniqueItems: true } },
    ['task', 'ids'], async (args, signal) => {
      if (!args.task?.trim() || !Array.isArray(args.ids) || !args.ids.length || args.ids.length > 4 || new Set(args.ids).size !== args.ids.length)
        throw Error('A team task and 1 to 4 distinct configured role IDs are required');
      const roles = args.ids.map((id: string) => config.teamAgents!.find(role => role.id === id));
      if (roles.some((role: any) => !role)) throw Error('Unknown configured team role');
      if (children.size + roles.length > 4) throw Error('Sub-agent limit reached (4 per request)');
      return Promise.all(roles.map((role: any) => {
        const file = `agent/${randomUUID().replaceAll('-', '')}.json`;
        const child: Child = { agent: { file, parentFile: config.conversationFile ?? '', name: role.name.slice(0, 100),
          task: args.task, teamId: role.id, status: 'running', providerId: config.model.provider, modelId: config.model.id,
          thinkingLevel: config.model.reasoning ? config.thinkingLevel ?? 'off' : 'off' } };
        children.set(file, child); return launch(child, args.task, signal);
      }));
    }));
  return { names, tools, runOutputTokens: () => runOutputTokens,
    stats: () => [...children.values()].map(child => ({ file: child.agent.file, name: child.agent.name, status: child.agent.status,
      tokens: child.result?.stats?.tokens ?? null })), async control(file: string, command: Control) {
    if (!filePattern.test(file)) throw Error('Invalid sub-agent identity');
    const child = children.get(file);
    if (child?.agent.status === 'cancelled' && ['abortChild', 'abort'].includes(command.type)) return;
    if (!child?.control) throw Error('Sub-agent is not running');
    if (command.type === 'abortChild' || command.type === 'abort') await cancel(file);
    else await child.control({ type: command.type, prompt: command.prompt });
  }, tokens: () => {
    const total = emptyTokens();
    for (const child of children.values()) if (child.result?.stats?.tokens)
      for (const key of Object.keys(total) as (keyof typeof total)[]) total[key] += child.result.stats.tokens[key];
    return total;
  }, cancel, async abort() {
    await Promise.all([...children.values()].filter(child => child.control).map(child => cancel(child.agent.file)));
    await Promise.all([...children.values()].map(child => child.promise));
  } };
}
