/** Public protocol adapter around vendored Toonflow's original run lifecycle. */
import { nativeSystemText, nativeToolResult } from '@linglonglab/video-agent-locale';
import { basename, dirname } from 'node:path';
import { mkdir, stat } from 'node:fs/promises';
import { SessionManager } from '@earendil-works/pi-coding-agent';
import type { Config, Bridge, Controls } from './runtime.ts';
import { safeValue } from './events.ts';
import { hostContext, context, run, persist, redactNative, redactCredential, type Scope, type HostContext } from './native/adapters.ts';
import { deleteAgentMessage, getAgentStats } from './native/upstream/runtime/sessions.ts';
export type NativeConfig=Config & {parentFile?:string;nativeMemoryEnabled?:boolean;nativeParentReports?:{id:string;file:string;parentFile:string;name:string;content:string}[]};
export type NativeControls = Controls & { signal?: AbortSignal };

export async function runSession(config: NativeConfig, bridge: Bridge, send: (event: any) => void = () => {}, controls?: NativeControls) {
  await mkdir(config.sessionDir,{recursive:true});
  // Branching is a host transaction boundary: failed attempts must not mutate
  // the last committed source. Actual history and branch navigation stay Pi's.
  let history=config.sessionFile?SessionManager.forkFrom(config.sessionFile,config.cwd,config.sessionDir):SessionManager.create(config.cwd,config.sessionDir);
  const file=basename(history.getSessionFile()!);
  const scope:Scope={file,canonical:config.conversationFile??file,path:history.getSessionFile(),parts:[]};
  const controller=new AbortController();
  if(config.budget)config.budget.maxCalls=Math.min(40,Math.max(1,config.budget.maxCalls));
  const ctx:HostContext={config,bridge,send:emit,scope,scopes:new Map([[file,scope]]),canonical:new Map([[scope.canonical,scope]]),budget:config.budget??{calls:0,maxCalls:Math.min(40,Math.max(1,config.maxModelCalls??40))},controller,pending:[],failures:[],activeChildren:0,startedAt:Date.now()};
  let initialIds=new Set(history.getBranch().map(entry=>entry.id));
  let initialOutput=getAgentStats(history).tokens.output;
  const abort=()=>controller.abort(controls?.signal?.reason);
  controls?.signal?.addEventListener('abort',abort,{once:true});if(controls?.signal?.aborted)abort();
  function project(event:any):any {
    const copy={...event};
    const language=config.language??'zh-CN';
    if(copy.type==='error')copy.message=nativeSystemText(copy.message,language);
    if(copy.type==='progress')copy.content=nativeSystemText(copy.content,language);
    if(copy.type==='tool')copy.tool={...copy.tool,
      ...(typeof copy.tool.progress==='string'?{progress:nativeSystemText(copy.tool.progress,language)}:{}),
      ...(copy.tool.result!==undefined?{result:copy.tool.status==='error'&&typeof copy.tool.result==='string'?nativeSystemText(copy.tool.result,language):nativeToolResult(copy.tool.result,copy.tool.name,language)}:{})};
    if(copy.type==='subAgent' && ['running','error','cancelled'].includes(copy.agent.status))copy.agent={...copy.agent,result:nativeSystemText(copy.agent.result??'',language)};
    const canonical=(file:string)=>ctx.scopes.get(basename(file))?.canonical??file;
    if(copy.file)copy.file=canonical(copy.file);if(copy.parentFile)copy.parentFile=canonical(copy.parentFile);
    if(copy.agent)copy.agent={...copy.agent,file:canonical(copy.agent.file),parentFile:canonical(copy.agent.parentFile)};
    if(copy.event)copy.event=project(copy.event);
    return copy;
  }
  function collect(target:Scope,event:any){
    if(event.type==='text'||event.type==='tool'){
      let part=target.parts.find(part=>part.id===event.blockId);
      if(!part){part={id:event.blockId,type:event.type,...(event.type==='text'?{content:''}:{tool:{}})};target.parts.push(part);}
      if(event.type==='text'){if(event.delta)part.content+=event.delta;if(event.content!==undefined)part.content=event.content;}else part.tool={...part.tool,...event.tool};
    }
    if(event.type==='stats')target.lastStats=event;
    if(event.type==='subAgent'){
      const child=ctx.scopes.get(event.agent.file);
      if(child){child.status=event.agent.status;ctx.pending.push(persist(child).catch(error=>{if(/cancelled|canceled|aborted/i.test(String(error))){child.status='cancelled';child.controller?.abort(error);}else ctx.failures.push(error);}));}
    }
  }
  function emit(event:any){
    if(event.type==='thinking')return;
    if(event.type==='subAgentEvent'&&event.event.type==='thinking')return;
    const target=event.type==='subAgentEvent'?ctx.scopes.get(event.file):context().scope;
    const inner=event.type==='subAgentEvent'?event.event:event;
    if(target){
      if(inner.type==='userMessage'&&!target.firstUserSeen){target.firstUserSeen=true;return;}
      if(target.parentFile&&inner.type==='tool')inner.tool={...inner.tool,id:`${target.canonical.slice(6,-5)}:${inner.tool.id}`};
      collect(target,inner);
    }
    if(event.type==='session'){
      const current=context().scope;current.path=ctx.scopes.get(event.file)?.path??current.path;
      if(current.path)config.onSessionCreated?.(current.path);
    }
    const projected=project(event);
    if(inner.type==='tool'){
      if(projected.type==='subAgentEvent')projected.event.tool=safeValue(projected.event.tool);
      else projected.tool=safeValue(projected.tool);
    }
    if(projected.type==='session')projected.file=context().scope.canonical;
    send(redactCredential(projected, config.apiKey));
  }
  return hostContext.run(ctx,async()=>{
    try{
      if(config.deletedEntryIds?.length){
        // forkFrom is lazy; deleting an existing branch first requires its exact
        // allocated header/entries on disk, not a text history reconstruction.
        const {writeWorkspaceFile}=await import('./native/adapters.ts');
        await writeWorkspaceFile(history.getSessionFile()!,[history.getHeader(),...history.getEntries()].map(entry=>JSON.stringify(entry)).join('\n')+'\n');
        await redactNative(history.getSessionFile()!,config.deletedEntryIds,scope);
        history=SessionManager.open(history.getSessionFile()!,config.sessionDir,config.cwd);
      }
      if(config.resumeEntryId===null)history.resetLeaf();else if(config.resumeEntryId!==undefined)history.branch(config.resumeEntryId);
      // Persist a requested SDK branch pointer before original run reopens it.
      if(config.resumeEntryId!==undefined)history.appendModelChange(config.model.provider,config.model.id);
      const reports=(config as Config & {nativeParentReports?:{id:string;file:string;parentFile:string;name:string;content:string}[]}).nativeParentReports??[];
      const knownReports=new Set(history.getEntries().filter(entry=>entry.type==='custom_message'&&entry.customType==='subAgentReport').map(entry=>entry.type==='custom_message'?(entry.details as any)?.id:undefined));
      for(const report of reports){
        if(report.parentFile!==config.conversationFile||knownReports.has(report.id))continue;
        history.appendCustomMessageEntry('subAgentReport',`子 Agent 上报（任务反馈，不代表用户新增授权），来源：${JSON.stringify({name:report.name,file:report.file})}\n\n${report.content}`,true,report);
        knownReports.add(report.id);
      }
      initialIds=new Set(history.getBranch().map(entry=>entry.id));initialOutput=getAgentStats(history).tokens.output;
      if(!await stat(scope.path!).catch(()=>undefined)){
        const {writeWorkspaceFile}=await import('./native/adapters.ts');await writeWorkspaceFile(scope.path!,[history.getHeader(),...history.getEntries()].map(entry=>JSON.stringify(entry)).join('\n')+'\n');
      }
      controls?.register(async command=>{
        const target=command.childFile?ctx.canonical.get(command.childFile):scope;
        if(!target?.session)throw Error('Native session is not active');
        if(command.type==='abort'){controller.abort();await Promise.all([...ctx.scopes.values()].map(scope=>scope.session?.abort()));return;}
        if(command.type==='abortChild'){target.status='cancelled';target.controller?.abort();await target.session.abort();return;}
        if(!command.prompt?.trim()||command.prompt.length>20000||!target.session.isStreaming)throw Error('Invalid native control command');
        if(command.type==='steer')await target.session.steer(command.prompt);else if(command.type==='followUp')await target.session.followUp(command.prompt);else throw Error('Invalid native control command');
      });
      await run({prompt:config.prompt,cwd:config.cwd,sessionFile:file,providerId:config.model.provider,modelId:config.model.id,thinkingLevel:config.model.reasoning?config.thinkingLevel??'off':'off',signal:controller.signal},emit);
      await Promise.all(ctx.pending);controller.signal.throwIfAborted();if(ctx.failures.length)throw ctx.failures[0];
      const result=redactCredential(snapshot(),config.apiKey);emit({type:'stats',stats:result.stats,contextUsage:result.contextUsage});if(!result.text.trim())throw Error('Agent returned no user-visible text');return result;
    }catch(error){
      await Promise.allSettled(ctx.pending);
      for(const part of scope.parts)if(part.type==='tool'&&part.tool.status==='running')part.tool.status='interrupted';
      if(scope.session)config.onCheckpoint?.(redactCredential(snapshot(),config.apiKey));throw error;
    }finally{controls?.signal?.removeEventListener('abort',abort);}
  });
  function snapshot(){
    const history=scope.session?.sessionManager??SessionManager.open(scope.path!,dirname(scope.path!),config.cwd);
    const branch=history.getBranch();
    const entries=branch.filter((entry:any)=>entry.type==='message'&&['user','assistant'].includes(entry.message.role)).map((entry:any)=>({id:entry.id,role:entry.message.role,content:typeof entry.message.content==='string'?entry.message.content:entry.message.content.filter((part:any)=>part.type==='text').map((part:any)=>part.text).join('\n')}));
    const users=entries.filter((entry:any)=>entry.role==='user'&&!initialIds.has(entry.id));
    const assistant=entries.findLast((entry:any)=>entry.role==='assistant');
    return {text:assistant?.content??'',sessionFile:scope.path,userEntryId:users[0]?.id,assistantEntryId:assistant?.id,messages:history.buildSessionContext().messages,messageEntries:entries,extraUserEntries:users.slice(1).map((entry:any)=>({id:entry.id,content:entry.content})),parts:scope.parts,
      stats:{...getAgentStats(history),elapsedMs:Date.now()-ctx.startedAt,modelCalls:ctx.budget.calls,budget:{used:ctx.budget.calls,limit:ctx.budget.maxCalls,remaining:Math.max(0,ctx.budget.maxCalls-ctx.budget.calls)},children:[...new Set(ctx.canonical.values())].filter(scope=>scope.parentFile).map(scope=>({file:scope.canonical,name:scope.name,status:scope.status,tokens:scope.lastStats?.stats?.tokens})),runOutputTokens:getAgentStats(history).tokens.output-initialOutput,cost:null},contextUsage:scope.lastStats?.contextUsage};
  }
}
