import { nativeSystemText } from "@linglonglab/video-agent-locale";
import { defaultSystemPrompt } from "./upstream/runtime/prompt.ts";
/** Authenticated storage/model/tool boundaries for unchanged Toonflow lifecycle.
 * Source modules are pinned in provenance.json; no agent/model loop lives here.
 */
import { AsyncLocalStorage } from 'node:async_hooks';
import { basename, dirname, join, resolve, sep } from 'node:path';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { randomUUID, createHash } from 'node:crypto';
import { z } from 'zod';
import { createAgentSession as sdkCreate, ModelRuntime as SdkModelRuntime, SessionManager } from '@earendil-works/pi-coding-agent';
import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';
import type { ToolDefinition, CreateAgentSessionOptions } from '@earendil-works/pi-coding-agent';
import type { Config, Bridge } from '../runtime.ts';
import type { AgentEvent } from './upstream/runtime/types.ts';

export type Scope = { file: string; canonical: string; path?: string; parentFile?: string; name?: string; task?: string; status?: string; controller?: AbortController; session?: any; initialIds?: Set<string>; parts: any[]; instructions?:string; firstUserSeen?:boolean; lastStats?: any; deletedEntryIds?: string[] };
export type HostContext = { config: Config; bridge: Bridge; send: (event: any) => void; scope: Scope; scopes: Map<string, Scope>; canonical: Map<string, Scope>; budget: { calls: number; maxCalls: number }; controller: AbortController; pending: Promise<any>[]; failures: unknown[]; activeChildren: number; startedAt: number };
export const hostContext = new AsyncLocalStorage<HostContext>();
export function context() { const value = hostContext.getStore(); if (!value) throw Error('Native Agent requires authenticated run scope'); return value; }
export function redactCredential<T>(value: T, credential: string | undefined = context().config.apiKey): T {
  if (!credential) return value;
  if (typeof value === 'string') return value.replaceAll(credential, '[redacted]') as T;
  if (Array.isArray(value)) return value.map(item => redactCredential(item, credential)) as T;
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key.replaceAll(credential, '[redacted]'), redactCredential(item, credential)])) as T;
  return value;
}
export function canonicalFile(file: string) { return context().scopes.get(basename(file))?.canonical ?? file; }
const locks = new Set<string>();
export function lockWorkspaceFiles(paths: string[]) { const keys = paths.map(path => resolve(path)); if (keys.some(path => locks.has(path))) throw Error('Native session is already running'); for (const path of keys) locks.add(path); return () => { for (const path of keys) locks.delete(path); }; }
export async function resolveWorkspacePath(cwd: string, relative: string, create = false) {
  const ctx = context(); let path: string;
  if (relative === '.agent/sessions') path = ctx.config.sessionDir;
  else if (relative.startsWith('.agent/sessions/')) {
    const file = relative.slice('.agent/sessions/'.length);
    if (!/^[\w.-]+\.jsonl$/.test(file)) throw Error('Invalid native session filename');
    path = ctx.scopes.get(file)?.path ?? join(ctx.config.sessionDir, file);
  } else if (resolve(cwd) === resolve(ctx.config.sessionDir) && /^[\w.-]+\.jsonl$/.test(relative))
    path = ctx.scopes.get(relative)?.path ?? join(ctx.config.sessionDir, relative);
  else {
    path = resolve(cwd, relative);
    if (!path.startsWith(resolve(cwd) + sep)) throw Error('Workspace path escapes authenticated project');
    if (relative.split(/[\\/]/).includes('.agent') && relative !== 'AGENTS.md') throw Error('Private native state is not a business asset');
  }
  if (create) await mkdir(path, { recursive: true });
  return { path };
}
export async function writeWorkspaceFile(path: string, text: string, exclusive = false) {
  const ctx = context();
  if (!resolve(path).startsWith(resolve(ctx.config.sessionDir) + sep)) throw Error('Native journal escapes authenticated private directory');
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, text, { flag: exclusive ? 'wx' : 'w', mode: 0o600 });
  const entries = text.split('\n').filter(Boolean).map(line => JSON.parse(line));
  const info = entries.find(entry => entry.type === 'custom' && entry.customType === 'toonflowSubAgentInfo')?.data;
  if (info && !ctx.scopes.has(basename(path))) {
    const id = randomUUID().replaceAll('-', '');
    const scope: Scope = { file: basename(path), canonical: `agent/${id}.json`, path: join(ctx.config.sessionDir, 'children', id, basename(path)), parentFile: info.parentFile, name: info.name, task: info.task, parts: [], status: 'running' };
    ctx.scopes.set(scope.file, scope); ctx.canonical.set(scope.canonical, scope);
    await mkdir(dirname(scope.path!), { recursive: true }); await writeFile(scope.path!, text, { mode: 0o600 });
    await persist(scope);
  }
}
export async function persist(scope: Scope) {
  const ctx = context(); if (!scope.parentFile || !scope.path) return;
  const history = scope.session?.sessionManager ?? SessionManager.open(scope.path, dirname(scope.path), ctx.config.cwd);
  const branch = history.getBranch();
  const messageEntries = branch.filter((entry: any) => entry.type === 'message' && ['user', 'assistant'].includes(entry.message.role)).map((entry: any) => ({ id: entry.id, role: entry.message.role,
    content: typeof entry.message.content === 'string' ? entry.message.content : entry.message.content.filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n') }));
  const messages = history.buildSessionContext().messages;
  const result = await ctx.bridge('tool', redactCredential({ id: `native-${scope.file}`, name: 'subAgentSession', conversationFile: ctx.config.conversationFile,
    arguments: { action: 'save', file: scope.canonical, parentFile: canonicalFile(scope.parentFile), name: scope.name, task: scope.task,
      status: scope.status ?? 'running', sessionFile: scope.path, messages, messageEntries,
      parts: scope.parts, stats: scope.lastStats?.stats, contextUsage: scope.lastStats?.contextUsage,
      providerId: ctx.config.model.provider, modelId: ctx.config.model.id, thinkingLevel: ctx.config.model.reasoning?(ctx.config.thinkingLevel??'off'):'off',
      userEntryId: messageEntries.find((entry: any) => entry.role === 'user')?.id, assistantEntryId: messageEntries.findLast((entry: any) => entry.role === 'assistant')?.id,
      result: messageEntries.findLast((entry: any) => entry.role === 'assistant')?.content } }));
  if (result?.status === 'cancelled' && scope.status !== 'cancelled') throw Error('Child Agent cancelled');
}

// Original model.ts still builds/registers its deployment model. This proxy
// only installs the authenticated provider transport and never selects a model.
export const ModelRuntime = { async create(options: any) {
  const runtime = await SdkModelRuntime.create(options); const original = runtime.registerProvider.bind(runtime);
  runtime.registerProvider = (providerId: string, options: any) => {
    const ctx = context(); const native = ['openai','anthropic'].includes(providerId) && !!ctx.config.apiKey;
    return original(providerId, { ...options, ...(native ? { apiKey: ctx.config.apiKey, baseUrl: runtime.getModels(providerId)[0]?.baseUrl } : { apiKey: 'authenticated-business-bridge', streamSimple: bridgeStream }) });
  };
  return runtime;
} };
function bridgeStream(model: any, requestContext: any, options: any = {}) {
  const ctx = context(); const stream = createAssistantMessageEventStream();
  void (async () => {
    let message: any = { role: 'assistant', content: [], api: model.api, provider: model.provider, model: model.id,
      usage: { input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0} }, stopReason:'error', timestamp:Date.now() };
    let started = false; let streamed = '';
    try {
      const payload = { context:requestContext, model, maxTokens:options.maxTokens, thinkingLevel:options.reasoning ?? 'off', reasoning:options.reasoning ?? 'off', compacting:ctx.scope.session?.isCompacting ?? false, conversationFile: ctx.scope.parentFile ? ctx.scope.canonical : undefined, parentFile:ctx.scope.parentFile ? canonicalFile(ctx.scope.parentFile) : undefined };
      const modified = await options.onPayload?.(payload, model);
      message = await ctx.bridge('model', modified ?? payload, options.signal, event => {
        if (event.type !== 'text_delta' || options.signal?.aborted) return;
        if (!started) { started = true; message.content = [{type:'text',text:''}]; stream.push({type:'start',partial:message}); stream.push({type:'text_start',contentIndex:0,partial:message}); }
        streamed += event.delta; message.content[0] = {type:'text',text:streamed}; stream.push({type:'text_delta',contentIndex:0,delta:event.delta,partial:message});
      });
      options.signal?.throwIfAborted();
      if (!started) stream.push({type:'start',partial:message});
      for (const [contentIndex, part] of message.content.entries()) {
        if (part.type === 'text') { if (!started || contentIndex !== 0) { stream.push({type:'text_start',contentIndex,partial:message}); stream.push({type:'text_delta',contentIndex,delta:part.text,partial:message}); } stream.push({type:'text_end',contentIndex,content:part.text,partial:message}); }
        if (part.type === 'toolCall') { stream.push({type:'toolcall_start',contentIndex,partial:message}); stream.push({type:'toolcall_end',contentIndex,toolCall:part,partial:message}); }
      }
      if (message.stopReason === 'error' || message.stopReason === 'aborted') stream.push({type:'error',reason:message.stopReason,error:message});
      else stream.push({type:'done',reason:message.stopReason,message});
    } catch (error) { if(/cancelled|canceled|aborted|取消|停止/i.test(String(error)))ctx.scope.controller?.abort(error);message={...message,stopReason:options.signal?.aborted?'aborted':'error',errorMessage:String(error)}; stream.push({type:'error',reason:message.stopReason,error:message}); }
    stream.end();
  })(); return stream;
}
export function getConfiguredModel(providerId: string, modelId: string) {
  const {config} = context(); if (providerId !== config.model.provider || modelId !== config.model.id) throw Error('Model is outside authenticated deployment selection');
  return {provider:{protocol:['openai','anthropic'].includes(providerId)&&config.apiKey?(providerId==='openai'?'openai-responses':'anthropic-messages'):'openai-completions',apiKey:config.apiKey ?? 'authenticated-business-bridge'},model:{id:modelId,label:modelId,contextWindow:config.model.contextWindow,maxOutputTokens:config.model.maxTokens},baseUrl:'http://127.0.0.1'};
}
export async function createAgentSession(options: CreateAgentSessionOptions) {
  const ctx = context();
  if (ctx.scope.parentFile || (ctx.config as any).parentFile || ctx.config.enableDelegation === false) {
    options = {...options, customTools: options.customTools?.filter(tool => tool.name !== 'subAgent'), tools: options.tools?.filter(tool => tool !== 'subAgent')};
  } else if (options.customTools) {
    options = {...options,customTools:options.customTools.map(tool => tool.name !== 'subAgent' ? tool : {...tool,description:tool.description.replace('任务数量、并发数、执行轮次和总时长不设固定上限，可由用户停止。','宿主限制最多四个并行子任务，共享四十次模型请求预算，子任务不能继续委派。'),async execute(...args:Parameters<ToolDefinition['execute']>){if(!Array.isArray((args[1] as any).tasks)||(args[1] as any).tasks.length>4)throw Error('Native delegation permits at most four tasks');return tool.execute(...args);}})};
  }
  options={...options,customTools:options.customTools?.map(tool=>({...tool,label:nativeSystemText(tool.label??tool.name,ctx.config.language??"zh-CN"),execute(...args:Parameters<ToolDefinition['execute']>){return hostContext.run(ctx,()=>tool.execute(...args));}}))};
  const result = await sdkCreate(options); const session = result.session;
  ctx.scope.session = session; ctx.scope.path = session.sessionManager.getSessionFile();
  ctx.scope.initialIds = new Set(session.sessionManager.getBranch().map(entry => entry.id));
  const original = session.agent.streamFunction;
  session.agent.streamFunction = async (...args) => {
    if (ctx.controller.signal.aborted) throw Error('Agent request cancelled');
    if (ctx.budget.calls >= ctx.budget.maxCalls) throw Error('Agent request budget exhausted; no further model/tool calls.');
    ctx.budget.calls++; return hostContext.run(ctx,()=>original(...args));
  };
  const previousPayload = session.agent.onPayload;
  session.agent.onPayload = async (payload, model) => {
    const body: any = await previousPayload?.(payload,model) ?? payload;
    if (!session.isCompacting && ctx.config.images?.length && !ctx.scope.parentFile && ['openai','anthropic'].includes(ctx.config.model.provider) && ctx.config.apiKey) {
      const messages = ctx.config.model.provider === 'openai' ? body.input : body.messages;
      const user = [...messages].reverse().find(message => message.role === 'user');
      if (user) { if (typeof user.content === 'string') user.content=[{type:'text',text:user.content}]; for (const image of ctx.config.images) user.content.push(ctx.config.model.provider==='openai'?{type:'input_image',image_url:`data:${image.mimeType};base64,${image.data}`}:{type:'image',source:{type:'base64',media_type:image.mimeType,data:image.data}}); }
    } return body;
  };
  return result;
}
export async function createAgentTools(_cwd: string, _canvas?: any, _questions?: any): Promise<ToolDefinition[]> {
  const ctx = context();
  const tools: ToolDefinition[] = ctx.config.tools.filter(tool => !['subAgent','report','memory','delegateTask','messageSubAgent','delegateTeam','listSubAgents','cancelSubAgent'].includes(tool.name)).map(tool => ({...tool,label:tool.name,executionMode:'sequential', async execute(id,args,signal) {
    signal?.throwIfAborted(); const scope = ctx.scope; const scopedId = scope.parentFile ? `${scope.canonical.slice(6,-5)}:${id}` : id;
    let details;try{details = await ctx.bridge('tool',{id:scopedId,name:tool.name,arguments:args,...(scope.parentFile?{conversationFile:scope.canonical,parentFile:canonicalFile(scope.parentFile)}:{})},signal);}catch(error){if(/cancelled|canceled|aborted|取消|停止/i.test(String(error)))ctx.scope.controller?.abort(error);throw error;}
    return {content:[{type:'text',text:JSON.stringify(details)}],details};
  }}));
  tools.push(...compatibilityTools()); return tools;
}

export async function run(options: any, send: (event: AgentEvent) => void) {
  const parent = context(); const scope = parent.scopes.get(options.sessionFile) ?? parent.scope;
  if (scope !== parent.scope) {
    if (parent.scope.parentFile) throw Error('Recursive delegation is disabled by authenticated host policy');
    if (parent.activeChildren >= 4) throw Error('Concurrent child limit reached (4)');
    parent.activeChildren++;
  }
  if(scope.parentFile && scope.path){
    scope.parts=[];scope.lastStats=undefined;scope.firstUserSeen=false;
    const fork=SessionManager.forkFrom(scope.path,parent.config.cwd,dirname(scope.path));
    const oldFile=scope.file;scope.file=basename(fork.getSessionFile()!);scope.path=fork.getSessionFile();
    parent.scopes.set(oldFile,scope);parent.scopes.set(scope.file,scope);
    await writeFile(scope.path!,[{...fork.getHeader(),parentSession:scope.parentFile},...fork.getEntries()].map(entry=>JSON.stringify(entry)).join('\n')+'\n',{mode:0o600});
    options={...options,sessionFile:scope.file};
  }
  scope.controller = new AbortController();
  const nativeOptions = {...options,signal:options.signal?AbortSignal.any([options.signal,scope.controller.signal]):scope.controller.signal};
  const scoped={...parent,scope};
  try { return await hostContext.run(scoped, async () => {
    const native = await import('./upstream/runtime/index.ts');
    if(scope.deletedEntryIds?.length&&scope.path)await redactNative(scope.path,scope.deletedEntryIds,scope);
    await native.run(nativeOptions,event=>hostContext.run(scoped,()=>send(event)));nativeOptions.signal?.throwIfAborted();
  }); } finally { if (scope !== parent.scope) parent.activeChildren--; }
}

export async function loadChild(file: string): Promise<Scope> {
  const ctx = context(); const existing = ctx.canonical.get(file); if (existing) return existing;
  if (!/^agent\/[a-f0-9]{32}\.json$/.test(file)) throw Error('Invalid child session identity');
  const saved = await ctx.bridge('tool',{id:`load-${file}`,name:'subAgentSession',arguments:{action:'get',file},conversationFile:ctx.config.conversationFile});
  if (!saved?.sessionFile || saved.parentFile !== ctx.config.conversationFile) throw Error('Child session does not belong to this parent');
  const childDir=join(ctx.config.sessionDir,'children',file.slice(6,-5));
  if (!resolve(saved.sessionFile).startsWith(resolve(childDir)+sep)) throw Error('Child journal escapes owned directory');
  const scope: Scope={file:basename(saved.sessionFile),canonical:file,path:saved.sessionFile,parentFile:ctx.scope.file,name:saved.name,task:saved.task,status:saved.status,parts:[],deletedEntryIds:saved.deletedEntryIds};
  ctx.scopes.set(scope.file,scope);ctx.canonical.set(file,scope);
  const priorParent=SessionManager.open(scope.path!,dirname(scope.path!),ctx.config.cwd).getHeader()?.parentSession;
  if(priorParent)ctx.scopes.set(basename(priorParent),ctx.scope);
  return scope;
}
function compatibilityTools(): ToolDefinition[] {
  const tool=(name:string,properties:any,required:string[],execute:(args:any,signal?:AbortSignal)=>Promise<any>):ToolDefinition=>({name,label:name,description:'Compatibility alias for native Toonflow session/delegation tools.',parameters:{type:'object',properties,required} as any,executionMode:'sequential',async execute(_id,args,signal){const details=await execute(args,signal);const usage=details._usage;delete details._usage;return {content:[{type:'text',text:JSON.stringify(details)}],details,...(usage?{usage}:{})};}});
  const ctx=context(); if(ctx.scope.parentFile||(ctx.config as any).parentFile||ctx.config.enableDelegation===false)return [];
  return [tool('delegateTask',{name:{type:'string'},task:{type:'string'}},['name','task'],async(args,signal)=>{
    const {runDelegatedAgent}=await import('./upstream/runtime/delegation.ts');const output=await runDelegatedAgent({cwd:ctx.config.cwd,parentFile:ctx.scope.file,name:args.name,task:args.task,providerId:ctx.config.model.provider,modelId:ctx.config.model.id,thinkingLevel:ctx.config.model.reasoning?(ctx.config.thinkingLevel??'off'):'off',signal,send:emitNative});
    const scope=[...ctx.scopes.values()].findLast(scope=>scope.name===args.name&&scope.task===args.task);if(scope&&scope.status==='completed'&&output.result.status==='completed')emitNative({type:'report',id:randomUUID(),parentFile:ctx.scope.file,file:scope.file,name:args.name,content:output.result.result});
    return {file:scope?.canonical,status:scope?.status??output.result.status,result:output.result.result,_usage:output.usage};
  }),tool('messageSubAgent',{file:{type:'string'},prompt:{type:'string'}},['file','prompt'],async(args,signal)=>{
    const scope=await loadChild(args.file);scope.status='running';await persist(scope);
    await run({cwd:ctx.config.cwd,prompt:args.prompt,sessionFile:scope.file,providerId:ctx.config.model.provider,modelId:ctx.config.model.id,thinkingLevel:ctx.config.model.reasoning?(ctx.config.thinkingLevel??'off'):'off',signal},event=>emitNative({type:'subAgentEvent',file:scope.file,event}));
    await persist(scope);return {file:scope.canonical,status:scope.status,result:scope.session?.messages.findLast((message:any)=>message.role==='assistant')?.content.filter((part:any)=>part.type==='text').map((part:any)=>part.text).join('\n')};
  }),tool('listSubAgents',{},[],async()=>({agents:[...ctx.canonical.values()].filter(scope=>scope.parentFile).map(scope=>({file:scope.canonical,name:scope.name,status:scope.status}))})),tool('cancelSubAgent',{file:{type:'string'}},['file'],async(args)=>{const scope=ctx.canonical.get(args.file);if(!scope?.session)throw Error('Child is not active');scope.status='cancelled';await scope.session.abort();return {file:scope.canonical,status:'cancelled'};}),
    ...(ctx.config.teamAgents?.length ? [tool('delegateTeam',{ids:{type:'array',items:{type:'string'},maxItems:4},task:{type:'string'}},['ids','task'],async(args,signal)=>{
      const roles=args.ids.map((id:string)=>{const role=ctx.config.teamAgents?.find(role=>role.id===id);if(!role)throw Error('Unknown configured team role');return role;});
      const results=await Promise.all(roles.map(async(role:any)=>{const runner=await createTeamRunner({cwd:ctx.config.cwd,name:role.id});return runner.run(args.task,signal);}));
      const {emptyUsage,addUsage}=await import('./upstream/runtime/subAgent.ts');const usage=emptyUsage();results.forEach(output=>addUsage(usage,output.usage));return {agents:results.map(result=>result.result),_usage:usage};})]:[])];
}
export function emitNative(event: AgentEvent) { context().send(event); }
export function isMemoryEnabled(){return (context().config as Config & {nativeMemoryEnabled?:boolean}).nativeMemoryEnabled!==false && context().config.tools.some(tool=>tool.name==='memoryOperator');}
export const maxDocumentLength=50000;
function memoryRevision(revision:unknown){
  if(typeof revision!=='string'||!revision)throw Error('Authenticated memory revision is unavailable');
  const ctx=context();
  return createHash('sha256').update(JSON.stringify([ctx.config.sessionDir,ctx.scope.canonical,'user',revision])).digest('hex');
}
function memoryDocument(document:any){return {...document,content:document.enabled===false?'':document.content,revision:memoryRevision(document.revision)};}
export async function readDocument(name:string){
  if(name!=='memory'||!isMemoryEnabled())return {content:''};
  return memoryDocument(await scopedBusiness('native-memory-read','memoryOperator',{action:'read',scope:'user'}));
}
export async function saveDocument(name:string,content:string,revision:string){
  if(name!=='memory'||!isMemoryEnabled())throw Error('Scoped memory is disabled');
  const current=await scopedBusiness('native-memory-read','memoryOperator',{action:'read',scope:'user'});
  if(current.enabled===false)throw Error('Scoped memory is disabled');
  if(memoryRevision(current.revision)!==revision)throw Error('Memory revision conflict; read the current revision before saving');
  // The business adapter checks this original opaque revision again under its
  // resource lock, so a concurrent edit between read and write stays protected.
  return memoryDocument(await scopedBusiness('native-memory-save','memoryOperator',{action:'write',scope:'user',content,expected_revision:current.revision}));
}
export function loadAgentSkills(_cwd:string):{skills:any[];diagnostics:any[]}{return {skills:[],diagnostics:[]};}
export const providerSchema=z.object({id:z.string(),models:z.array(z.any())});
export function getModelLimits(_provider:string,_model:any){return {contextWindow:context().config.model.contextWindow};}
const conf={get(_key:string,_fallback:any){const {config}=context();return {agentSystemPrompt:defaultSystemPrompt+'\n\n'+config.systemPrompt+(context().scope.task?.startsWith('Configured team role:')?'\n'+context().scope.task:'' ),customProviders:[{id:config.model.provider,models:[{id:config.model.id}]}]};}};
export default conf;
export async function readAiReferences(..._args:any[]):Promise<any>{throw Error('Media must pass the authenticated business adapter');}
export function referenceContent(..._args:any[]):any {throw Error('Media must pass the authenticated business adapter');}
export function createCanvasContext(_cwd:string,canvas:any,_send:any){return {context:canvas,dispose(){}};}
export function createQuestionContext(_cwd:string,_send:any,_cancel:any){return {context:{ask(){throw Error('Questions require authenticated business adapter');}},dispose(){}};}
export async function listTeams(){return (context().config.teamAgents??[]).map(role=>({name:role.id,description:role.instructions,kind:'local',enabled:true,loadError:undefined}));}
export function getRemoteTeam(_name:string){return undefined;}
export async function runRemoteTeam(_options:any):Promise<any>{throw Error('Remote teams require the authenticated remoteTeam business tool');}
export async function createTeamRunner(options:any){const ctx=context();const role=ctx.config.teamAgents?.find(role=>role.id===options.name);if(!role)throw Error('Team role is not configured');return {async run(task:string,signal?:AbortSignal,onProgress?:(text:string)=>void){const {runDelegatedAgent}=await import('./upstream/runtime/delegation.ts');const output=await runDelegatedAgent({cwd:ctx.config.cwd,parentFile:ctx.scope.file,name:role.name,task:`Configured team role:\n${role.instructions}\n\n${task}`,providerId:ctx.config.model.provider,modelId:ctx.config.model.id,thinkingLevel:ctx.config.model.reasoning?(ctx.config.thinkingLevel??'off'):'off',signal,send:emitNative,onProgress});const scope=[...ctx.scopes.values()].findLast(scope=>scope.name===role.name);if(scope&&scope.status==='completed'&&output.result.status==='completed')emitNative({type:'report',id:randomUUID(),parentFile:ctx.scope.file,file:scope.file,name:role.name,content:output.result.result});return output;}};}

// User-turn deletion also removes the delegated intake text from native child
// metadata. Native deleteAgentMessage remains responsible for message/tool/
// timing/compaction/tree redaction; this only adapts hosted privacy metadata.
export async function redactNative(path:string,ids:string[],scope:Scope){
  const ctx=context();const history=SessionManager.open(path,dirname(path),ctx.config.cwd);
  const targets=new Set(ids);let removing=false;
  const firstUser=history.getBranch().find(entry=>entry.type==='message'&&entry.message.role==='user');
  for(const entry of history.getBranch()){
    if(entry.type==='message'&&entry.message.role==='user')removing=targets.has(entry.id);
    if(removing&&entry.type==='message'&&['user','assistant'].includes(entry.message.role))targets.add(entry.id);
  }
  const {deleteAgentMessage}=await import('./upstream/runtime/sessions.ts');
  await deleteAgentMessage(ctx.config.cwd,path,{entryIds:[...targets]});
  if(firstUser&&targets.has(firstUser.id)){
    const entries=(await readFile(path,'utf8')).split('\n').filter(Boolean).map(line=>JSON.parse(line));
    let changed=false;for(const entry of entries)if(entry.type==='custom'&&entry.customType==='toonflowSubAgentInfo'){entry.data={...entry.data,task:''};changed=true;}
    if(changed){scope.task='';await writeWorkspaceFile(path,entries.map(entry=>JSON.stringify(entry)).join('\n')+'\n');}
  }
}

async function scopedBusiness(id:string,name:string,args:any,signal?:AbortSignal){
 const ctx=context();const scope=ctx.scope;
 return ctx.bridge('tool',{id:scope.parentFile?`${scope.canonical.slice(6,-5)}:${id}`:id,name,arguments:args,...(scope.parentFile?{conversationFile:scope.canonical,parentFile:canonicalFile(scope.parentFile)}:{})},signal);
}
