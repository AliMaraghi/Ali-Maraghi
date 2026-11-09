"""Local monitoring and bounded scheduling decisions; no workers are launched."""
from datetime import datetime
from .schema import fields, identifier, timestamp
from .policy import Action


def health(ledger):
    try:
        return {'status': 'ok', 'journal_events': ledger.verify(), 'scope': 'LOCAL_JOURNAL_ONLY'}
    except Exception:
        return {'status': 'degraded', 'reason': 'JOURNAL_VERIFICATION_FAILED', 'scope': 'LOCAL_JOURNAL_ONLY'}


def plan_due_jobs(jobs, policy, now: datetime, max_seconds=60):
    if not isinstance(jobs, list) or len(jobs) > 100 or type(max_seconds) is not int or not 0 <= max_seconds <= 3600:
        raise ValueError('Invalid bounded schedule')
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Timezone required')
    seen, valid = set(), []
    for job in jobs:
        fields(job, {'id','kind','domain','due_at','seconds','estimated_pence','sensitivity'})
        identifier(job['id'])
        if job['id'] in seen or type(job['seconds']) is not int or not 1 <= job['seconds'] <= 3600:
            raise ValueError('Duplicate ID or invalid duration')
        seen.add(job['id'])
        valid.append((timestamp(job['due_at']), job))
    selected, deferred, used = [], [], 0
    for due, job in sorted(valid, key=lambda row: (row[0], row[1]['id'])):
        allowed, reason = policy.authorize(Action(job['id'], 'record_decision', job['domain'],job['estimated_pence'],job['sensitivity']))
        if not allowed: pass
        elif job['kind'] not in ('evidence_review','studio_preflight'):
            reason = 'UNSUPPORTED_JOB'; allowed = False
        elif due > now:
            reason = 'NOT_DUE'; allowed = False
        elif used + job['seconds'] > max_seconds:
            reason = 'TIME_BUDGET'; allowed = False
        if allowed:
            selected.append(job['id']); used += job['seconds']
        else:
            deferred.append({'id':job['id'],'reason':reason})
    return {'selected':selected,'deferred':deferred,'reserved_seconds':used,
            'executed':False,'scope':'DRY_RUN_NO_DISPATCH_NO_DURABLE_QUEUE',
            'retry_policy':{'automatic_retries':0,'on_failure':'Record failure; operator review before retry'}}
