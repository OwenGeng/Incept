// Canonical identity/persistence boundary for directly opened child sessions.
// Native active-session/branch/delegation behavior is re-exported unchanged.
export * from './upstream/runtime/sessions.ts';
import * as sessions from './upstream/runtime/sessions.ts';
import { context, redactCredential } from './adapters.ts';
export function getSubAgentInfo(history:Parameters<typeof sessions.getSubAgentInfo>[0]){
  const saved=sessions.getSubAgentInfo(history);if(saved)return saved;
  const ctx=context();const parent=(ctx.config as typeof ctx.config & {parentFile?:string}).parentFile??ctx.scope.parentFile;
  if(!parent)return undefined;
  // Legacy SDK journals have no Toonflow child-info custom entry. Canonical
  // ownership metadata supplies only identity; model history stays untouched.
  return {type:'custom',id:'host-child-identity',parentId:null,timestamp:new Date().toISOString(),customType:'toonflowSubAgentInfo',data:{file:ctx.scope.file,parentFile:parent,name:ctx.scope.name??'Sub-agent',task:ctx.scope.task??'',status:'running'}} as ReturnType<typeof sessions.getSubAgentInfo>;
}
export function getParentSessionFile(history: Parameters<typeof sessions.getParentSessionFile>[0]) {
  const ctx=context();
  return (ctx.config as typeof ctx.config & {parentFile?:string}).parentFile && !ctx.scope.parentFile
    ? (ctx.config as typeof ctx.config & {parentFile:string}).parentFile : ctx.scope.parentFile ?? sessions.getParentSessionFile(history);
}
export async function updateSubAgent(cwd:string,parentFile:string,agent:Parameters<typeof sessions.updateSubAgent>[2]){
  const ctx=context();
  if(parentFile===(ctx.config as typeof ctx.config & {parentFile?:string}).parentFile&&!ctx.scope.parentFile)return;
  const child=ctx.scopes.get(agent.file);if(child?.status==='cancelled')agent={...agent,status:'cancelled'};
  return sessions.updateSubAgent(cwd,parentFile,agent);
}
export async function reportToParent(cwd:string,parentFile:string,file:string,name:string,content:string){
  const ctx=context();
  if(parentFile===(ctx.config as typeof ctx.config & {parentFile?:string}).parentFile&&!ctx.scope.parentFile){
    const id=crypto.randomUUID();
    const saved=await ctx.bridge('tool',redactCredential({id,name:'nativeParentReport',arguments:{id,parentFile,file:ctx.scope.canonical,name,content},conversationFile:ctx.scope.canonical}));
    return saved?.id??id;
  }
  return sessions.reportToParent(cwd,parentFile,file,name,content);
}
