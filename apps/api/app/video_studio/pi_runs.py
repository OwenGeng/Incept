"""Durable host events and commands. Pi, not this journal, runs the Agent."""
import json
import re
import time
import uuid

from . import store
from .workspace_documents import document_lock

MAX_EVENTS = 20000
MAX_EVENT_BYTES = 256 * 1024
LEASE_SECONDS = 90


def control_target(email,project_id,conversation):
    """A delegated run shares its parent's process; direct child turns own one."""
    if conversation.parent_file:
        parent_id=conversation.parent_file.removeprefix('agent/').removesuffix('.json')
        try: parent=store.get_conversation(email,project_id,parent_id)
        except FileNotFoundError: parent=None
        if parent and parent.run_id==conversation.run_id and parent.run_status=='running':
            return RunJournal(email,project_id,parent.id,parent.run_id),f'agent/{conversation.id}.json'
    return RunJournal(email,project_id,conversation.id,conversation.run_id),None


class RunJournal:
    def __init__(self, email, project_id, conversation_id, run_id):
        store.get_project(email, project_id)
        store._conversation_path(email, project_id, conversation_id)
        if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise ValueError('Invalid run identity')
        self.email, self.project_id = email, project_id
        self.conversation_id, self.run_id = conversation_id, run_id
        self.root = store._project_root(email, project_id) / '.agent' / 'runs' / conversation_id / run_id
        self.path = self.root / 'run.json'

    def create(self):
        with document_lock(self.path):
            if store._read_json(self.path, None):
                raise ValueError('Run already exists')
            store._write_json(self.path, {'conversationId':self.conversation_id, 'runId':self.run_id,
                'sequence':0, 'commandSequence':0, 'status':'running', 'heartbeat':time.time()})

    def state(self):
        state = store._read_json(self.path, None)
        if not state or state['conversationId'] != self.conversation_id:
            raise FileNotFoundError('Run is unavailable')
        return state

    def emit(self, event):
        if len(json.dumps(event, ensure_ascii=False).encode()) > MAX_EVENT_BYTES:
            raise ValueError('Agent event exceeds display budget')
        with document_lock(self.path):
            state = self.state()
            if state['sequence'] >= MAX_EVENTS:
                raise ValueError('Agent event budget exhausted')
            number = state['sequence'] + 1
            record = {**event, 'sequence':number}
            store._write_json(self.root / 'events' / f'{number:06}.json', record)
            state.update(sequence=number, heartbeat=time.time())
            store._write_json(self.path, state)
        return record

    def events(self, after=0):
        if not isinstance(after,int) or after < 0:
            raise ValueError('Invalid event cursor')
        state = self.state()
        return [store._read_json(self.root / 'events' / f'{n:06}.json', None)
            for n in range(after+1, min(state['sequence'],after+500)+1)]

    def enqueue(self, action, prompt, child_file=None):
        if action not in {'steer','followUp'} or not isinstance(prompt,str) or not 0 < len(prompt.strip()) <= 20000:
            raise ValueError('Invalid active instruction')
        with document_lock(self.path):
            state = self.state()
            if state['status'] != 'running' or time.time()-state['heartbeat'] > LEASE_SECONDS:
                raise ValueError('Run is no longer active; reload and retry')
            if state['commandSequence'] >= 100:
                raise ValueError('Active instruction budget exhausted')
            number = state['commandSequence']+1
            record = {'type':action,'prompt':prompt.strip(),'controlId':uuid.uuid4().hex,'sequence':number}
            if child_file: record['childFile']=child_file
            store._write_json(self.root / 'commands' / f'{number:06}.json',record)
            state['commandSequence'] = number
            store._write_json(self.path,state)
            return record

    def abort_child(self,child_file):
        if self.state()['status']!='running': raise ValueError('Parent run is no longer active')
        child_id=child_file.removeprefix('agent/').removesuffix('.json')
        with document_lock(store._conversation_path(self.email,self.project_id,child_id)):
            child=store.get_conversation(self.email,self.project_id,child_id)
            if child.parent_file!=f'agent/{self.conversation_id}.json' or child.run_id!=self.run_id:
                raise ValueError('Invalid child owner or run')
            if child.run_status=='cancelled': return
            if child.run_status!='running': raise ValueError('Child run is no longer active')
            child.run_status='cancelled'
            store.save_conversation(self.email,self.project_id,child)
        with document_lock(self.path):
            state=self.state()
            if state['status']!='running': raise ValueError('Parent run is no longer active')
            n=state['commandSequence']+1
            store._write_json(self.root/'commands'/f'{n:06}.json',{'type':'abortChild','childFile':child_file,'sequence':n})
            state['commandSequence']=n
            store._write_json(self.path,state)
        cancel_questions(self.email,self.project_id,child_id,self.run_id)

    def commands(self, after):
        state = self.state()
        return [store._read_json(self.root / 'commands' / f'{n:06}.json',None)
            for n in range(after+1,state['commandSequence']+1)]

    def heartbeat(self):
        with document_lock(self.path):
            state=self.state()
            state['heartbeat']=time.time()
            store._write_json(self.path,state)

    def finish(self,status):
        with document_lock(self.path):
            state=self.state()
            state.update(status=status,heartbeat=time.time())
            store._write_json(self.path,state)

    def question(self,tool_call_id,request):
        if not isinstance(request.get('title'),str) or not 0 < len(request['title']) <= 100:
            raise ValueError('Invalid question title')
        limit=30000 if request.get('paidRequest') or request.get('outboundRequest') else 4000
        if not isinstance(request.get('question'),str) or not 0 < len(request['question']) <= limit:
            raise ValueError('Invalid question')
        options=request.get('options',[])
        fields=request.get('fields',[])
        if not isinstance(options,list) or len(options)>8 or any(not isinstance(v,str) or not v or len(v)>300 for v in options):
            raise ValueError('Invalid question options')
        if not isinstance(fields,list) or len(fields)>12 or (fields and options):
            raise ValueError('Invalid question fields')
        names=[]
        for field in fields:
            key=field.get('field','')
            if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9]{0,63}',key) or key in {'constructor','prototype','__proto__'}:
                raise ValueError('Invalid question field name')
            if field.get('type') not in {'input','textarea','radio','checkbox','select','inputNumber','switch'}:
                raise ValueError('Invalid question field type')
            if field['type'] in {'radio','checkbox','select'} and not field.get('options'):
                raise ValueError('Missing field options')
            names.append(key)
        if len(set(names))!=len(names): raise ValueError('Duplicate question fields')
        call_id=uuid.uuid4().hex
        child_match=re.match(r'^([a-f0-9]{32}):',tool_call_id)
        target_id=child_match[1] if child_match else self.conversation_id
        event={'type':'question','callId':call_id,'toolCallId':tool_call_id,
            **{key:request[key] for key in ('title','question','options','fields') if key in request},
            'sessionFile':f'agent/{target_id}.json','runId':self.run_id}
        path=store._project_root(self.email,self.project_id)/'.agent'/'questions'/f'{call_id}.json'
        store._write_json(path,{'event':event,'status':'pending','runId':self.run_id,'conversationId':target_id})
        if child_match:
            child=RunJournal(self.email,self.project_id,target_id,self.run_id)
            try: child.state()
            except FileNotFoundError: child.create()
            child.emit(event)
            self.emit({'type':'subAgentEvent','file':f'agent/{target_id}.json','event':event})
        else: self.emit(event)
        return call_id

    def ask(self,tool_call_id,request,control):
        call_id=self.question(tool_call_id,request)
        path=store._project_root(self.email,self.project_id)/'.agent'/'questions'/f'{call_id}.json'
        while True:
            control.check()
            question=store._read_json(path,None)
            if not question: raise ValueError('Question disappeared')
            if question['status']=='answered': return question['result']
            if question['status']=='cancelled': raise ValueError('Question cancelled')
            time.sleep(.2)


def answer(email,project_id,call_id,payload):
    store.get_project(email,project_id)
    if not isinstance(call_id,str) or not re.fullmatch(r'[a-f0-9]{32}',call_id):
        raise ValueError('Invalid question identity')
    path=store._project_root(email,project_id)/'.agent'/'questions'/f'{call_id}.json'
    with document_lock(path):
        question=store._read_json(path,None)
        if not question: raise FileNotFoundError('Question not found')
        journal=RunJournal(email,project_id,question['conversationId'],question['runId'])
        current=store.get_conversation(email,project_id,question['conversationId'])
        if current.run_id!=question['runId'] or current.run_status!='running':
            raise ValueError('Question is no longer awaiting an answer')
        if time.time()-journal.state()['heartbeat']>LEASE_SECONDS:
            from .pi_http import recover
            recover(journal)
        if journal.state()['status']!='running' or question['status']!='pending':
            raise ValueError('Question is no longer awaiting an answer')
        if payload.get('sessionFile') and payload['sessionFile']!=f"agent/{question['conversationId']}.json":
            raise ValueError('Question conversation mismatch')
        if payload.get('runId') and payload['runId']!=question['runId']:
            raise ValueError('Question run mismatch')
        if payload.get('cancelled'):
            question['status']='cancelled'
            result={'answer':'','skipped':True}
        elif payload.get('skipped') is True:
            question['status']='answered'
            result={'answer':'','skipped':True}
        else:
            values=payload.get('values')
            fields=question['event'].get('fields',[])
            if fields:
                if not isinstance(values,dict) or set(values)-{f['field'] for f in fields}:
                    raise ValueError('Invalid form answers')
                for f in fields:
                    v=values.get(f['field'])
                    if f.get('required') and (v is None or v=='' or v==[]): raise ValueError('Required answer missing')
                    if v is None: continue
                    kind=f['type']
                    if kind in {'radio','select'} and v not in f['options']: raise ValueError('Invalid option')
                    if kind=='checkbox' and (not isinstance(v,list) or any(x not in f['options'] for x in v)): raise ValueError('Invalid options')
                    if kind in {'input','textarea'} and (not isinstance(v,str) or len(v)>8000): raise ValueError('Invalid text answer')
                    if kind=='switch' and not isinstance(v,bool): raise ValueError('Invalid boolean answer')
                    if kind=='inputNumber' and (isinstance(v,bool) or not isinstance(v,(int,float))): raise ValueError('Invalid numeric answer')
                text=json.dumps(values,ensure_ascii=False,allow_nan=False)
                result={'answer':text,'values':values,'skipped':False}
            else:
                text=payload.get('answer')
                if not isinstance(text,str) or not 0<len(text.strip())<=8000: raise ValueError('Answer must contain 1–8000 characters')
                result={'answer':text.strip(),'skipped':False}
            question['status']='answered'
        question['result']=result
        store._write_json(path,question)
        return result


def cancel_questions(email,project_id,conversation_id,run_id):
    journal=RunJournal(email,project_id,conversation_id,run_id)
    try: journal.state()
    except FileNotFoundError: return
    cursor=0
    while batch:=journal.events(cursor):
        for event in batch:
            if event['type']!='question': continue
            path=store._project_root(email,project_id)/'.agent'/'questions'/f"{event['callId']}.json"
            with document_lock(path):
                question=store._read_json(path,None)
                if question and question['status']=='pending':
                    question['status']='cancelled'
                    store._write_json(path,question)
        cursor=batch[-1]['sequence']
