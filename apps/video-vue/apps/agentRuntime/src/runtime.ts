// SDK lifecycle follows Toonflow-app's runtime/index.ts and resources.ts (MIT).
// Source: https://github.com/earendil-works/pi/blob/v0.85.1/packages/coding-agent/docs/sdk.md
import { createAgentSession, SessionManager, ModelRuntime, SettingsManager, DefaultResourceLoader } from '@earendil-works/pi-coding-agent';
import type { ToolDefinition, AgentSession } from '@earendil-works/pi-coding-agent';
import { InMemoryCredentialStore, createAssistantMessageEventStream } from '@earendil-works/pi-ai';
import type { AssistantMessage, Context, SimpleStreamOptions } from '@earendil-works/pi-ai';
import { redactSessionEntries } from './sessionEdits.ts';
import { existsSync } from 'node:fs';
import { createEventProjector } from './events.ts';
import { createDelegationTools } from './subAgents.ts';

export type Bridge = (kind: 'model' | 'tool', payload: any, signal?: AbortSignal, onDelta?: (event: { type: 'text_delta'; delta: string }) => void) => Promise<any>;
export type Control = { type: 'steer' | 'followUp' | 'abort' | 'abortChild'; prompt?: string; childFile?: string };
export type Controls = { register: (handler: (command: Control) => Promise<void>) => void };
export type Budget = { calls: number; maxCalls: number };
export type Config = {
  language?: string; cwd: string; sessionDir: string; sessionFile?: string; prompt: string; systemPrompt: string;
  model: { provider: string; id: string; contextWindow: number; maxTokens: number; reasoning?: boolean };
  thinkingLevel?: 'off' | 'low' | 'medium' | 'high';
  teamAgents?: { id: string; name: string; instructions: string }[];
  conversationFile?: string; enableDelegation?: boolean; onSessionCreated?: (sessionFile: string) => void; onCheckpoint?: (snapshot: any) => void; budget?: Budget; maxModelCalls?: number; memoryContext?: string;
  apiKey?: string;
  images?: { data: string; mimeType: string }[];
  tools: { name: string; description: string; parameters: any }[];
  resumeEntryId?: string | null;
  deletedEntryIds?: string[];
};

export async function runSession(config: Config, bridge: Bridge, send: (event: any) => void = () => {}, controls?: Controls) {
  const budget = config.budget ?? { calls: 0, maxCalls: Math.min(120, Math.max(1, config.maxModelCalls ?? 40)) };
  const projector = createEventProjector(send);
  const startedAt = Date.now();
  // Each attempt branches through the SDK. A failed/cancelled attempt must not
  // mutate the last successfully committed source session.
  let history = config.sessionFile ? SessionManager.forkFrom(config.sessionFile, config.cwd, config.sessionDir)
    : SessionManager.create(config.cwd, config.sessionDir);
  if (config.deletedEntryIds?.length) history = redactSessionEntries(history, config.deletedEntryIds, config.cwd, config.sessionDir);
  const notifyJournal = () => {
    const file = history.getSessionFile();
    if (file && existsSync(file)) config.onSessionCreated?.(file);
  };
  notifyJournal();
  if (config.resumeEntryId === null) history.resetLeaf();
  else if (config.resumeEntryId !== undefined) history.branch(config.resumeEntryId);
  const modelRuntime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null, refreshOnCreate: false });
  const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };
  let activeSession: AgentSession | undefined;
  const streamSimple = (model: any, context: Context, options?: SimpleStreamOptions) => {
    const stream = createAssistantMessageEventStream();
    void (async () => {
      let message: AssistantMessage = { role: 'assistant', content: [], api: model.api,
        provider: model.provider, model: model.id, usage, stopReason: 'error', timestamp: Date.now() };
      try {
        const payload = { context, model, maxTokens: options?.maxTokens, thinkingLevel: options?.reasoning ?? 'off', reasoning: options?.reasoning ?? 'off', compacting: activeSession?.isCompacting ?? false };
        const replacement = await options?.onPayload?.(payload, model);
        let streamedText = '';
        let started = false;
        message = await bridge('model', replacement ?? payload, options?.signal, event => {
          if (options?.signal?.aborted || event.type !== 'text_delta' || !event.delta) return;
          if (!started) { started = true; message.content = [{ type: 'text', text: '' }];
            stream.push({ type: 'start', partial: message });
            stream.push({ type: 'text_start', contentIndex: 0, partial: message }); }
          streamedText += event.delta;
          message.content[0] = { type: 'text', text: streamedText };
          stream.push({ type: 'text_delta', contentIndex: 0, delta: event.delta, partial: message });
        });
        if (options?.signal?.aborted) throw Error('Agent request cancelled');
        if (!started) stream.push({ type: 'start', partial: message });
        for (const [contentIndex, block] of message.content.entries()) {
          if (block.type === 'text') {
            if (!started || contentIndex !== 0) {
              stream.push({ type: 'text_start', contentIndex, partial: message });
              stream.push({ type: 'text_delta', contentIndex, delta: block.text, partial: message });
            }
            stream.push({ type: 'text_end', contentIndex, content: block.text, partial: message });
          }
        }
        if (message.stopReason === 'error' || message.stopReason === 'aborted') {
          stream.push({ type: 'error', reason: message.stopReason, error: message });
        } else stream.push({ type: 'done', reason: message.stopReason as 'stop' | 'length' | 'toolUse', message });
      } catch (error) {
        message = { ...message, stopReason: options?.signal?.aborted ? 'aborted' : 'error', errorMessage: String(error) };
        stream.push({ type: 'error', reason: message.stopReason as 'error' | 'aborted', error: message });
      }
      stream.end();
    })();
    return stream;
  };
  // The URL is an unused in-process transport marker, never an external endpoint.
  // Credentials stay in the authenticated Python process, not SDK auth files.
  const native = ['openai', 'anthropic'].includes(config.model.provider) && !!config.apiKey;
  const nativeModel = native ? modelRuntime.getModels(config.model.provider)[0] : undefined;
  if (native && !nativeModel) throw Error('SDK has no native transport for configured provider');
  modelRuntime.registerProvider(config.model.provider, {
    api: native ? (config.model.provider === 'openai' ? 'openai-responses' : 'anthropic-messages') : 'openai-completions', baseUrl: nativeModel?.baseUrl ?? 'http://127.0.0.1',
    apiKey: native ? config.apiKey : 'python-bridge', ...(native ? {} : { streamSimple }),
    models: [{ id: config.model.id, name: config.model.id, reasoning: config.model.reasoning ?? false, input: ['text', 'image'],
      cost: usage.cost, contextWindow: config.model.contextWindow, maxTokens: config.model.maxTokens }],
  });
  const model = modelRuntime.getModel(config.model.provider, config.model.id);
  if (!model) throw Error('Deployment model is not registered');
  const settingsManager = SettingsManager.inMemory();
  const delegation = createDelegationTools({ ...config, budget }, bridge, projector.emit, runSession);
  const customTools: ToolDefinition[] = config.tools.filter(tool => !delegation.names.includes(tool.name)).map(tool => ({ ...tool, label: tool.name,
    executionMode: 'sequential', async execute(id, args, signal) {
      const result = await bridge('tool', { id, name: tool.name, arguments: args }, signal);
      return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result };
    } }));
  customTools.push(...delegation.tools);
  // Toonflow disables filesystem/global resource auto-discovery too. Never expose
  // built-in bash/read/write tools or developer home credentials to hosted users.
  const resourceLoader = new DefaultResourceLoader({ cwd: config.cwd, agentDir: config.sessionDir,
    settingsManager, noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true,
    noContextFiles: true, agentsFilesOverride: () => ({ agentsFiles: [] }),
    systemPrompt: '', systemPromptOverride: () => config.systemPrompt + (config.memoryContext ? '\n\n' + config.memoryContext : '') });
  await resourceLoader.reload();
  const { session } = await createAgentSession({ cwd: config.cwd, agentDir: config.sessionDir,
    modelRuntime, model, thinkingLevel: config.model.reasoning ? (config.thinkingLevel ?? 'off') : 'off', sessionManager: history,
    settingsManager, resourceLoader, tools: customTools.map(tool => tool.name), customTools });
  activeSession = session;
  // Like Toonflow's lazy attachment conversion, keep media outside persisted
  // model messages and attach only this turn's selection, never during compaction.
  session.agent.onPayload = async payload => {
    if (!native) return { ...payload as Record<string, unknown>, compacting: session.isCompacting };
    if (session.isCompacting || !config.images?.length) return payload;
    const body = payload as Record<string, any>;
    const messages = config.model.provider === 'openai' ? body.input : body.messages;
    const user = [...messages].reverse().find(message => message.role === 'user');
    if (!user) throw Error('No current user message for media');
    if (typeof user.content === 'string') user.content = [{ type: 'text', text: user.content }];
    for (const image of config.images) user.content.push(config.model.provider === 'openai'
      ? { type: 'input_image', image_url: `data:${image.mimeType};base64,${image.data}` }
      : { type: 'image', source: { type: 'base64', media_type: image.mimeType, data: image.data } });
    return body;
  };
  const streamFunction = session.agent.streamFunction;
  const initialOutputTokens = session.getSessionStats().tokens.output;
  const initialEntryIds = new Set(history.getBranch().map(entry => entry.id));
  session.agent.streamFunction = async (...args) => {
    if (budget.calls >= budget.maxCalls) throw Error('Agent request budget exhausted; no further model/tool calls.');
    budget.calls++;
    const compacting = session.isCompacting;
    const stream = await streamFunction(...args);
    if (compacting) {
      const response = await stream.result();
      if (response.stopReason === 'stop' && !response.content.some(part => part.type === 'text' && part.text.trim()))
        throw Error('Empty compaction summary; original context retained');
    }
    return stream;
  };
  let firstUserSeen = false;
  const unsubscribe = session.subscribe(event => {
    projector.accept(event);
    if (event.type === 'message_end' && event.message.role === 'user') {
      const initial = !firstUserSeen; firstUserSeen = true;
      // Pi appends the entry immediately after notifying message_end listeners.
      // Read it in the next microtask so display IDs are real SDK identities.
      queueMicrotask(() => {
        notifyJournal();
        if (initial) return;
        const entry = history.getBranch().findLast(item => item.type === 'message' && item.message.role === 'user');
        if (entry?.type === 'message' && entry.message.role === 'user') send({ type: 'userMessage', id: entry.id,
          content: typeof entry.message.content === 'string' ? entry.message.content
            : entry.message.content.filter(part => part.type === 'text').map(part => part.text).join('\n') });
      });
    }
  });
  let aborted = false;
  controls?.register(async command => {
    if (command.childFile) { await delegation.control(command.childFile, command); return; }
    if (command.type === 'abort') { aborted = true; await Promise.all([session.abort(), delegation.abort()]); return; }
    if (!['steer', 'followUp'].includes(command.type) || typeof command.prompt !== 'string' || !command.prompt.trim() || command.prompt.length > 20000)
      throw Error('Invalid Pi control command');
    if (!session.isStreaming) throw Error('Agent is no longer executing');
    if (command.type === 'steer') await session.steer(command.prompt);
    else if (command.type === 'followUp') await session.followUp(command.prompt);
    else throw Error('Invalid Pi control command');
  });
  try {
    if (aborted) throw Error('Agent request cancelled');
    await session.prompt(config.prompt, { expandPromptTemplates: false });
    const last = [...session.messages].reverse().find(message => message.role === 'assistant');
    if (!last || last.role !== 'assistant') throw Error('Agent returned no response');
    if (last.stopReason === 'error' || last.stopReason === 'aborted') throw Error(last.errorMessage || last.stopReason);
    if (last.stopReason === 'length') throw Error('Agent output reached the configured token limit; incomplete draft was not committed.');
    const text = last.content.filter(part => part.type === 'text').map(part => part.text).join('\n').trim();
    if (!text) throw Error('Agent returned no user-visible text');
    const branch = history.getBranch();
    const newUsers = branch.filter(entry => entry.type === 'message' && entry.message.role === 'user' && !initialEntryIds.has(entry.id));
    const user = newUsers[0] ?? branch.findLast(entry => entry.type === 'message' && entry.message.role === 'user');
    const assistant = branch.findLast(entry => entry.type === 'message' && entry.message.role === 'assistant');
    if (!user || !assistant) throw Error('SDK message identities are missing');
    const stats = session.getSessionStats();
    const childTokens = delegation.tokens();
    for (const key of ['input', 'output', 'cacheRead', 'cacheWrite', 'total'] as const) stats.tokens[key] += childTokens[key];
    const elapsedMs = Date.now() - startedAt;
    const runOutputTokens = stats.tokens.output - childTokens.output - initialOutputTokens + delegation.runOutputTokens();
    const productStats = { tokens: stats.tokens, tokensPerSecond: runOutputTokens / Math.max(0.001, elapsedMs / 1000),
      elapsedMs, modelCalls: budget.calls, runOutputTokens, children: delegation.stats(),
      budget: { used: budget.calls, limit: budget.maxCalls, remaining: Math.max(0, budget.maxCalls - budget.calls) }, cost: null };
    const contextUsage = session.getContextUsage();
    send({ type: 'stats', stats: productStats, contextUsage });
    return { text, sessionFile: history.getSessionFile(), userEntryId: user.id,
      assistantEntryId: assistant.id, messages: session.messages, stats: productStats, contextUsage, parts: projector.parts,
      messageEntries: branch.filter(entry => entry.type === 'message' && ['user', 'assistant'].includes(entry.message.role))
        .map(entry => ({ id: entry.id, role: entry.type === 'message' ? entry.message.role : '',
          content: entry.type === 'message' && (entry.message.role === 'user' || entry.message.role === 'assistant')
            ? (typeof entry.message.content === 'string' ? entry.message.content : entry.message.content.filter(part => part.type === 'text').map(part => part.text).join('\n')) : '' })),
      extraUserEntries: newUsers.slice(1).map(entry => ({ id: entry.id, content: entry.type === 'message' && entry.message.role === 'user' ? (typeof entry.message.content === 'string' ? entry.message.content : entry.message.content.filter(part => part.type === 'text').map(part => part.text).join('\n')) : '' })) };
  } catch (error) {
    projector.interrupt();
    const branch = history.getBranch();
    const sessionFile = history.getSessionFile();
    if (sessionFile && existsSync(sessionFile)) config.onCheckpoint?.({ sessionFile, messages: session.messages,
      messageEntries: branch.filter(entry => entry.type === 'message' && ['user', 'assistant'].includes(entry.message.role))
        .map(entry => ({ id: entry.id, role: entry.type === 'message' ? entry.message.role : '',
          content: entry.type === 'message' && (entry.message.role === 'user' || entry.message.role === 'assistant')
            ? (typeof entry.message.content === 'string' ? entry.message.content : entry.message.content.filter(part => part.type === 'text').map(part => part.text).join('\n')) : '' })),
      parts: projector.parts, stats: { tokens: session.getSessionStats().tokens, cost: null }, contextUsage: session.getContextUsage() });
    throw error;
  }
  finally { await delegation.abort(); unsubscribe(); session.dispose(); }
}
