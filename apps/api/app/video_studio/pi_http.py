"""Detached HTTP observation of authenticated Pi runs; no model orchestration."""
import asyncio
import json
import time
from collections import Counter

from . import store
from .agent_turns import AgentCancelled, agent_error_message
from .pi_runs import RunJournal,LEASE_SECONDS
from .workspace_documents import document_lock

_tasks=set()


def launch(journal,worker,finalize=None):
    async def work():
        try:
            result=await worker()
            if finalize:
                for event in finalize(result): journal.emit(event)
            journal.emit({'type':'done'})
            journal.finish('completed')
        except Exception as error:
            journal.emit({'type':'error','message':agent_error_message(error)})
            journal.emit({'type':'done'})
            journal.finish('cancelled' if isinstance(error,AgentCancelled) else 'failed')
    task=asyncio.create_task(work())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def recover(journal):
    state=journal.state()
    value=store.get_conversation(journal.email,journal.project_id,journal.conversation_id)
    if value.parent_file and state['status']=='running':
        parent_id=value.parent_file.removeprefix('agent/').removesuffix('.json')
        try:
            parent=RunJournal(journal.email,journal.project_id,parent_id,journal.run_id).state()
            if parent['status']=='running' and time.time()-parent['heartbeat']<=LEASE_SECONDS:
                return state
        except FileNotFoundError: pass
    if state['status']=='running' and time.time()-state['heartbeat']>LEASE_SECONDS:
        # A lost process cannot resume an unknown paid side effect automatically.
        # Retain event/journal receipts and the successful canonical SDK snapshot.
        with document_lock(journal.path):
            state=journal.state()
            if state['status']=='running' and time.time()-state['heartbeat']>LEASE_SECONDS:
                journal.emit({'type':'error','message':'Agent host was interrupted. Stored progress is retained; review receipts before retrying.'})
                journal.emit({'type':'done'})
                journal.finish('failed')
                conv=store.get_conversation(journal.email,journal.project_id,journal.conversation_id)
                if conv.run_id==journal.run_id and conv.run_status=='running':
                    conv.run_status='failed'
                    conv.run_error='Agent host interrupted'
                    store.save_conversation(journal.email,journal.project_id,conv)
    return journal.state()


async def events(journal,request,after=0,replay=False):
    cursor=after
    while True:
        batch=await asyncio.to_thread(journal.events,cursor)
        for event in batch:
            if not event: raise ValueError('Stored Agent event is missing')
            cursor=event['sequence']
            if not (replay and event['type']=='canvasCall'):
                yield json.dumps(event,ensure_ascii=False)+'\n'
        state=await asyncio.to_thread(recover,journal)
        if state['status']!='running' and cursor>=state['sequence']: return
        if await request.is_disconnected(): return
        await asyncio.sleep(.2)


def project_snapshot(journal,base):
    """Display-only projection. Pi journal remains the sole model context."""
    state=recover(journal)
    cursor=0
    parts={}
    children={a['file']:a for a in base.get('subAgents',[])}
    users=[]
    native_users=[]
    reports=[]
    for _ in range(40):
        batch=journal.events(cursor)
        if not batch: break
        for event in batch:
            kind=event['type']
            if kind=='userMessage': native_users.append(event.get('content',''))
            if kind=='text':
                part=parts.setdefault(event['blockId'],{'id':event['blockId'],'type':'text','content':''})
                part['content']=event.get('content',part['content']+event.get('delta',''))
            elif kind=='tool': parts[event['blockId']]={'id':event['blockId'],'type':'tool','tool':event['tool'].copy()}
            elif kind=='question':
                part=next((p for p in parts.values() if p['type']=='tool' and p['tool']['id']==event['toolCallId']),None)
                if part: part['tool']['question']=event
            elif kind=='subAgent': children[event['agent']['file']]=event['agent']
            elif kind=='report': reports.append(event)
            elif kind=='stats': base.update(stats=event['stats'],contextUsage=event.get('contextUsage'))
            elif kind=='userMessage' and not any(m.get('entryId')==event['id'] or m.get('content')==event.get('content') for m in base['messages']):
                users.append({'id':event['id'],'entryId':event['id'],'role':'user','content':event.get('content','')})
        cursor=batch[-1]['sequence']
    if parts and (base.get('running') or state['status'] in {'failed','cancelled'}):
        base['messages'].extend(users)
        if state['status']!='running':
            for part in parts.values():
                if part['type']=='tool' and part['tool']['status']=='running': part['tool']['status']='interrupted'
        base['messages'].append({'id':'run-'+journal.run_id,'role':'assistant','content':'','parts':list(parts.values()),
            'streaming':state['status']=='running','error':base.get('runError') if state['status']!='running' else None})
    if state['status'] in {'failed','cancelled'}:
        # Accepted controls are durable user input. Cancellation can close the
        # SDK transport before its queue flush; retain only a display receipt,
        # never rebuild model context or claim the instruction was executed.
        for user in users:
            if not any(m.get('id')==user['id'] for m in base['messages']): base['messages'].append(user)
        observed=Counter(native_users)
        command_journal=journal
        delegated=False
        current=store.get_conversation(journal.email,journal.project_id,journal.conversation_id)
        if current.parent_file:
            parent_id=current.parent_file.removeprefix('agent/').removesuffix('.json')
            try:
                parent=store.get_conversation(journal.email,journal.project_id,parent_id)
                if parent.run_id==journal.run_id:
                    candidate=RunJournal(journal.email,journal.project_id,parent_id,journal.run_id)
                    candidate.state()
                    command_journal,delegated=candidate,True
            except FileNotFoundError: pass
        for command in command_journal.commands(0):
            if command.get('type') not in {'steer','followUp'}: continue
            target=command.get('childFile')
            if (delegated and target!=f'agent/{journal.conversation_id}.json') or (not delegated and target): continue
            identity='instruction-'+command['controlId']
            if observed[command['prompt']]>0:
                observed[command['prompt']]-=1
                continue
            if any(m.get('id')==identity for m in base['messages']): continue
            base['messages'].append({'id':identity,'role':'user','content':command['prompt'],
                'controlId':command['controlId'],'pendingInstruction':True,'instructionType':command['type']})
    for child in children.values():
        try: current=store.get_conversation(journal.email,journal.project_id,child['file'].removeprefix('agent/').removesuffix('.json'))
        except FileNotFoundError: continue
        if current.parent_file!=f'agent/{journal.conversation_id}.json': continue
        child['status']={'failed':'error'}.get(current.run_status,current.run_status)
        if current.messages and current.messages[-1].role=='assistant': child['result']=current.messages[-1].content
        metadata=store._read_json(store._project_root(journal.email,journal.project_id)/'.agent'/'children'/f'{current.id}.json',{})
        stored=metadata.get('reports',[]) if metadata.get('parentFile')==current.parent_file and metadata.get('file')==child['file'] else []
        for report in [*reports,*stored]:
            if report.get('file')!=child['file'] or report.get('parentFile')!=current.parent_file: continue
            if not isinstance(report.get('id'),str) or not isinstance(report.get('content'),str): continue
            if any(m.get('id')==report['id'] for m in base['messages']): continue
            base['messages'].append({'id':report['id'],'role':'assistant','content':report['content'],
                'parts':[{'id':report['id'],'type':'text','content':report['content']}],
                'report':{'file':child['file'],'name':report.get('name',child['name'])}})
        if child['status']=='completed' and child.get('result') and not any((m.get('report') or {}).get('file')==child['file'] for m in base['messages']):
            report_id='report-'+current.id
            base['messages'].append({'id':report_id,'role':'assistant','content':child['result'],
                'parts':[{'id':report_id,'type':'text','content':child['result']}],
                'report':{'file':child['file'],'name':child['name']}})
    base.update(lastSequence=cursor,subAgents=list(children.values()),running=state['status']=='running')
    return base
