"""One bounded offline workflow, with atomic terminal records and historical replay.

No workers, leases, model calls, source fetches or external execution are implied.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import time
import json

from .schema import Case, fields, identifier, timestamp, DOMAINS
from .engine import canonical, code_digest
from .discovery import propose
from .policy import Action, enforce_durable_stop


@dataclass(frozen=True)
class Task:
    task_id: str
    domain: str
    expires_at: str
    max_sources: int
    max_runtime_ms: int
    paid_budget_pence: int

    @classmethod
    def parse(cls, raw):
        d = fields(raw, set(cls.__dataclass_fields__))
        identifier(d['task_id'])
        identifier('wf-' + d['task_id'])
        if not isinstance(d['domain'],str) or d['domain'] not in DOMAINS:
            raise ValueError('Unsupported domain')
        timestamp(d['expires_at'])
        for key, maximum in [('max_sources',8),('max_runtime_ms',10000)]:
            if type(d[key]) is not int or not 1 <= d[key] <= maximum:
                raise ValueError('Invalid bounded task budget')
        if type(d['paid_budget_pence']) is not int or d['paid_budget_pence'] != 0:
            raise ValueError('Only zero paid budget is supported')
        return cls(**d)


def run(task: Task, case: Case, workspace, ledger, policy, now=None, clock=time.monotonic):
    # Validate even when a caller constructs dataclasses without parse().
    task = Task.parse(asdict(task))
    case = Case.parse(json.loads(canonical(asdict(case))))
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Timezone required')
    fingerprint = hashlib.sha256(canonical({'task':asdict(task),'case':asdict(case), 'code':code_digest()}).encode()).hexdigest()
    key = 'wf-' + task.task_id
    identifier(key)
    # Enforce operator scope before reading any historical domain payload.
    allowed, reason = policy.authorize(Action(key,'record_decision',task.domain))
    if not allowed:
        raise PermissionError(reason)
    start = clock()
    with ledger.transaction():
        enforce_durable_stop(ledger)
        for event in ledger.records(task.domain):
            if event['key'] == key:
                saved = event['payload']
                if saved.get('request_sha256') != fingerprint:
                    raise ValueError('Task id conflicts with previous request/code')
                return {'report':saved,'replayed':True,'evidence_rechecked':False,'ledger_seq':event['seq']}
        reason = None
        if task.domain != case.domain:
            reason = 'CASE_DOMAIN_MISMATCH'
        elif timestamp(task.expires_at) <= now:
            reason = 'TASK_EXPIRED'
        elif len(case.evidence) > task.max_sources:
            reason = 'SOURCE_BUDGET_EXCEEDED'
        report = {'schema_version':'apex.workflow.v1','task_id':task.task_id,'domain':task.domain,
                  'request_sha256':fingerprint,'created_at':now.isoformat(),
                  'status':'DENIED' if reason else 'REVIEW_COMPLETED', 'reason':reason,
                  'paid_spend_pence':0,'actions_executed':[], 'production_status':'NOT_DEPLOYED',
                  'evaluation_status':'NO_EMPIRICAL_EXPERIMENT_RUN','promotion':'REJECT_NO_INDEPENDENT_EVALUATION'}
        if not reason:
            try:
                result = propose(case,workspace,now)
            except Exception as error:
                report.update(status='FAILED', reason='STAGE_FAILED', error_type=type(error).__name__)
                result = None
            elapsed = (clock()-start)*1000
            if elapsed > task.max_runtime_ms:
                report.update(status='DENIED',reason='ELAPSED_TIME_BUDGET_EXCEEDED')
            elif result is not None:
                report['discovery'] = result
                if result['source_review']['status'] != 'READY_FOR_HUMAN_REVIEW':
                    report.update(status='BLOCKED_PENDING_EVIDENCE')
            report['elapsed_ms'] = elapsed
        report['limits'] = {'source_count':task.max_sources,'bytes_per_artifact':1048576,
                            'time_ms':task.max_runtime_ms,'time_enforcement':'COOPERATIVE_POST_STAGE_NOT_PREEMPTIVE',
                            'automatic_retries':0,'external_calls':0}
        report = json.loads(canonical(report))
        seq = ledger._append(key,'decision',task.domain,report)
        return {'report':report,'replayed':False,'evidence_rechecked':True if not reason else False,'ledger_seq':seq}


def read_report(ledger, domain, task_id):
    key = 'wf-' + identifier(task_id)
    for event in ledger.records(domain):
        if event['key'] == key:
            return {'report':event['payload'],'ledger_seq':event['seq'],
                    'historical_record':True,'evidence_rechecked':False}
    raise ValueError('No report in this domain')
