"""Durable dependency scheduling over the existing fenced evidence job queue.

Only the implemented deterministic evidence-review handler is dispatched. Role
slots and dependencies do not imply independent agents or external verification.
Maximum one handler per tick; no daemon or service installation.
"""
from dataclasses import asdict
import hashlib
from .engine import canonical, code_digest
from .schema import identifier, fields, strict_json, Case
from .workflow import Task
from .jobs import Jobs, integer
from .policy import enforce_durable_stop


class Missions:
    @classmethod
    def read_only(cls,ledger):
        obj=cls.__new__(cls);obj.ledger=ledger;obj.queue=Jobs.read_only(ledger);return obj

    def __init__(self, ledger):
        self.ledger=ledger;self.queue=Jobs(ledger)
        with ledger.transaction():
            ledger.db.execute('CREATE TABLE IF NOT EXISTS mission_graphs (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, packet TEXT NOT NULL)')

    def submit(self, packet):
        fields(packet,{'trace_id','nodes','paid_budget_pence'})
        trace=identifier(packet['trace_id'])
        if len(trace)>30:raise ValueError('Trace too long')
        integer(packet['paid_budget_pence'],0,0)
        nodes=packet['nodes']
        if not isinstance(nodes,list) or not 1<=len(nodes)<=16:raise ValueError('Bounded graph required')
        seen=set()
        for node in nodes:
            fields(node,{'id','depends_on','role','task','case'})
            nid=identifier(node['id'])
            if len(nid)>20 or nid in seen:raise ValueError('Invalid node identity')
            deps=node['depends_on']
            if not isinstance(deps,list) or len(deps)!=len(set(deps)) or not set(deps)<=seen:
                raise ValueError('Topologically ordered acyclic dependencies required')
            if node['role']!='8-12':raise ValueError('Only implemented bounded evidence-review capability may run')
            task=Task.parse(node['task']);case=Case.parse(node['case'])
            if task.task_id!=trace+'-'+nid or task.domain!=case.domain:raise ValueError('Task trace/domain mismatch')
            seen.add(nid)
        encoded=canonical(packet)
        if len(encoded.encode())>524288:raise ValueError('Graph too large')
        digest=hashlib.sha256((encoded+code_digest()).encode()).hexdigest()
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            prior=self.ledger.db.execute('SELECT fingerprint FROM mission_graphs WHERE id=?',(trace,)).fetchone()
            if prior:
                if prior[0]!=digest:raise ValueError('Mission identity/code conflict')
                return trace
            if self.ledger.db.execute('SELECT count(*) FROM mission_graphs').fetchone()[0]>=100:raise ValueError('Mission retention cap')
            self.ledger.db.execute('INSERT INTO mission_graphs VALUES(?,?,?)',(trace,digest,encoded))
            self.ledger._append('mission-'+trace,'decision','opportunity',{'trace_id':trace,'graph':packet,'code_sha256':code_digest(),'status':'SCHEDULED','actions_executed':[]})
        return trace

    def status(self, trace):
        identifier(trace)
        row=self.ledger.db.execute('SELECT packet FROM mission_graphs WHERE id=?',(trace,)).fetchone()
        if row is None:raise ValueError('Unknown mission')
        packet=strict_json(row[0]);jobs={j['id']:j for j in self.queue.status()['jobs']}
        return {'trace_id':trace,'nodes':[{'id':n['id'],'role':n['role'],'depends_on':n['depends_on'],
            **jobs.get('mg-'+trace+'-'+n['id'],{'state':'WAITING','result_seq':None})} for n in packet['nodes']],
            'concurrency_limit':1,'independent_external_verification':'NOT_PERFORMED',
            'scope':'Deterministic evidence review only; no autonomous external effects'}

    def tick(self,trace,root,worker):
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            row=self.ledger.db.execute('SELECT packet,fingerprint FROM mission_graphs WHERE id=?',(trace,)).fetchone()
            if row is None:raise ValueError('Unknown mission')
            if hashlib.sha256((row[0]+code_digest()).encode()).hexdigest()!=row[1]:raise ValueError('Mission code changed; new reviewed identity required')
            packet=strict_json(row[0]);states={n['id'].removeprefix('mg-'+trace+'-'):n['state'] for n in self.status(trace)['nodes']}
            chosen=None
            for node in packet['nodes']:
                if states[node['id']] in {'COMPLETE','DEAD'}:continue
                if all(states[d]=='COMPLETE' for d in node['depends_on']):
                    jid='mg-'+trace+'-'+node['id']
                    self.queue.submit(jid,Task.parse(node['task']),Case.parse(node['case']))
                    chosen=jid;break
            claim=self.queue.claim(worker,job_id=chosen) if chosen else None
        if claim:self.queue.execute(claim,root)
        return self.status(trace)
