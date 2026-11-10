"""One bounded public-source mission through the existing evidence/queue ledger.

This is a manually invoked development workflow, not a daemon or a release.
Stop serializes with each bounded read; an in-flight read can finish before a
stop commits. Crash-ambiguous reads are recorded as blocked, never auto-retried.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import time

from .engine import canonical, code_digest
from .schema import fields, identifier, timestamp, text, Case, strict_json
from .policy import KillState
from .jobs import Jobs
from .workflow import Task
from ..sources import procurement


@dataclass(frozen=True)
class Mission:
    trace_id: str
    objective: str
    deadline: str
    sources: tuple
    maximum_spend_pence: int
    privacy_class: str

    @classmethod
    def parse(cls, value):
        d = fields(value, set(cls.__dataclass_fields__))
        identifier(d['trace_id'])
        if len(d['trace_id']) > 40: raise ValueError('Trace ID too long')
        text(d['objective'], 'objective', 500)
        timestamp(d['deadline'])
        if type(d['maximum_spend_pence']) is not int or d['maximum_spend_pence'] != 0:
            raise ValueError('Only exact zero paid spend authorized')
        if d['privacy_class'] != 'public': raise ValueError('Public research only')
        if not isinstance(d['sources'], (list, tuple)) or not 1 <= len(d['sources']) <= 4:
            raise ValueError('One to four bounded source requests required')
        for spec in d['sources']: procurement.request(spec)
        if len({canonical(s) for s in d['sources']}) != len(d['sources']):
            raise ValueError('Duplicate source request')
        return cls(**dict(d, sources=tuple(d['sources'])))


def artifact(root, payload):
    """Content-addressed minimized public evidence, not full contact-bearing JSON."""
    data = canonical(payload).encode()
    if len(data) > 262144: raise ValueError('Minimized evidence exceeds cap')
    digest = hashlib.sha256(data).hexdigest()
    folder = root / 'runtime' / 'public-evidence'
    if folder.is_symlink(): raise ValueError('Evidence symlinks forbidden')
    folder.mkdir(mode=0o700, exist_ok=True)
    if folder.stat().st_mode & 0o077: raise ValueError('Private evidence directory required')
    path = folder / (digest+'.json')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        from .evidence import read_local
        if read_local(root, str(path.relative_to(root)), 262144) != data:
            raise ValueError('Content-addressed evidence conflict')
    else:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
    return str(path.relative_to(root)), digest


def ensure_running(queue):
    if queue.control() is not KillState.RUNNING:
        raise PermissionError('Durable development stop denies field action')


def event(ledger, key):
    for r in ledger.records('opportunity'):
        if r['key'] == key: return r
    return None


def report(ledger, trace):
    identifier(trace)
    row = event(ledger, 'field-result-'+trace)
    if row is None: raise ValueError('Trace is incomplete or absent')
    return {'ledger_seq': row['seq'], 'historical_record': True,
            'evidence_rechecked': False, **row['payload']}


def build_case(root, trace, observations, now):
    evidence, claims = [], []
    for i, observation in enumerate(observations):
        if observation.get('retrieval_status') != 'OBSERVED_UNCORROBORATED': continue
        aid, digest = artifact(root, observation)
        eid, cid = 'source-'+str(i), 'observation-'+str(i)
        # Only assert that this stored observation contains these records.
        excerpt = 'OBSERVED_UNCORROBORATED'
        claims.append({'id': cid, 'kind': 'observation', 'statement':
            'The bounded official response contains '+str(observation['observed_count'])+' records; truth and supplier fit require corroboration.',
            'evidence_ids': [eid]})
        evidence.append({'id': eid, 'claim_id': cid, 'source_uri': observation['source_url'],
            'publisher': observation['publisher'], 'independence_group': observation['source'],
            'retrieved_at': observation['retrieved_at'], 'expires_at': observation['expiry'],
            'artifact': aid, 'sha256': digest, 'excerpt': excerpt, 'method': 'observation',
            'synthetic': False, 'stance': 'supports', 'domain': 'opportunity', 'sensitivity': 'public'})
    claims.append({'id': 'fit', 'kind': 'hypothesis', 'statement':
        'The founder could deliver a profitable bid; capacity, costs and eligibility are unknown.', 'evidence_ids': []})
    return Case.parse({'id': trace, 'domain': 'opportunity', 'problem':
        'Which public notices justify a small internal eligibility check without bidding?',
        'assumptions': ['Headline contract value is not margin or founder income.',
                        'Mirrors of the same buyer statement are not independent evidence.'],
        'baseline': 'Same-input manual checklist; independent timing and usefulness NOT MEASURED.',
        'hypotheses': [
            {'id': 'deliver', 'mechanism': 'Existing supplier capacity can satisfy the stated requirement.',
             'prediction': 'Verified entity, insurance and cost evidence support eligibility.',
             'falsifier': 'Mandatory qualifications or working capital cannot be met.'},
            {'id': 'exclude', 'mechanism': 'The notice is closed, unsuitable or requires an unavailable supplier capability.',
             'prediction': 'Portal or supplier evidence invalidates a viable bid.',
             'falsifier': 'Current primary documents and independent cost review confirm a feasible route.'}],
        'claims': claims, 'evidence': evidence,
        'neglected_need': 'Search a different sector as a probe; absence in one page is not unmet demand.',
        'second_order_effect': 'Delivery financing, travel and subcontractor commitments can exceed headline margin.',
        'smallest_test': 'Owner reviews public portal deadline and supplies only authorized eligibility facts.'})


def assess(observations):
    candidates, excluded, seen = [], [], set()
    for observation in observations:
        for item in observation.get('records', []):
            identity = (observation['source'], item['record_id'])
            if identity in seen: continue
            seen.add(identity)
            negative = any(f in {'DEADLINE_PASSED','NOT_ACTIVE_TENDER','AWARD_OR_CONTRACT_STAGE'}
                           for f in item['disconfirming_flags'])
            row = {**item, 'opportunity_id': '-'.join(identity),
                   'stage': 'EXCLUDED_FROM_BID_REVIEW' if negative else 'CANDIDATE_FOUND_AWAITING_VALIDATION',
                   'supplier_entity': 'UNKNOWN', 'insurance': 'UNKNOWN', 'experience': 'UNKNOWN',
                   'capacity': 'UNKNOWN', 'travel': 'UNKNOWN', 'subcontractors': 'UNKNOWN',
                   'working_capital': 'UNKNOWN', 'eligibility': 'UNKNOWN',
                   'margin_range': None, 'delivery_cost_range': None, 'effort_hours': None,
                   'margin_method': 'headline value minus verified delivery, finance and risk costs; inputs absent',
                   'independent_corroboration': 'NOT_PERFORMED', 'owner_decision': 'PENDING',
                   'measured_income_pence': 0, 'bid_permitted': False}
            (excluded if negative else candidates).append(row)
    # Deterministic review ordering only, not calibrated opportunity/ROI ranking.
    candidates.sort(key=lambda c: (len(c['disconfirming_flags']), c['opportunity_id']))
    for n, candidate in enumerate(candidates, 1): candidate['review_priority'] = n
    return candidates, excluded


def run(mission, root, ledger, *, network_authorized=False):
    mission = Mission.parse(asdict(mission))
    if network_authorized is not True: raise PermissionError('Explicit live public-read authority required')
    root = Path(root).resolve(strict=True)
    queue = Jobs(ledger)
    now = datetime.now(timezone.utc)
    if timestamp(mission.deadline) <= now: raise ValueError('Mission expired; historical reports remain readable')
    payload = canonical(asdict(mission))
    fingerprint = hashlib.sha256((payload + code_digest()).encode()).hexdigest()
    with ledger.transaction():
        ensure_running(queue)
        ledger.db.execute((Path(__file__).parent/'migrations/002_field_runs.sql').read_text())
        prior = ledger.db.execute('SELECT fingerprint,state FROM field_runs WHERE trace_id=?', (mission.trace_id,)).fetchone()
        if prior:
            if prior[0] != fingerprint: raise ValueError('Trace conflicts with request or code')
            if prior[1] == 'COMPLETE': return report(ledger, mission.trace_id)
        else:
            if ledger.db.execute('SELECT count(*) FROM field_runs').fetchone()[0] >= 100:
                raise ValueError('Field retention cap reached; reviewed archival needed')
            ledger.db.execute('INSERT INTO field_runs VALUES(?,?,?,\'STARTED\',NULL)', (mission.trace_id,fingerprint,payload))
            ledger._append('field-start-'+mission.trace_id,'decision','opportunity', {
                'trace_id': mission.trace_id, 'mission': asdict(mission), 'created_at': now.isoformat(),
                'owner': 'authorized local development operator', 'status': 'STARTED',
                'code_sha256': code_digest(), 'actions_executed': [],
                'plan': ['I:bounded_public_sources','II:evidence_critic','III:local_review_queue','IV:journal_owner_review'],
                'expected_outcome': 'Reviewable candidates or exact fetch blockers; no bid or revenue'})
    observations = []
    started = time.monotonic()
    for index, spec in enumerate(mission.sources):
        key = 'field-source-'+mission.trace_id+'-'+str(index)
        saved = event(ledger, key)
        if saved:
            observations.append(saved['payload']); continue
        intent = key+'-intent'
        with ledger.transaction():
            ensure_running(queue)
            if timestamp(mission.deadline) <= datetime.now(timezone.utc): raise ValueError('Mission expired before retrieval')
            attempted = event(ledger, intent)
            if not attempted:
                ledger._append(intent,'decision','opportunity', {
                    'trace_id':mission.trace_id, 'scope':'READ_PUBLIC_PROCUREMENT', 'request':spec,
                    'state':'RESERVED_ONCE', 'budget_pence':0, 'actions_executed':[]})
        with ledger.transaction():
            ensure_running(queue)
            # Another process may have completed this source while this one waited.
            saved = event(ledger, key)
            if saved:
                observation = saved['payload']
            else:
                if attempted:
                    observation = {'source':spec['source'], 'source_url':procurement.request(spec)[0],
                        'retrieval_status':'BLOCKED_EXTERNAL_FETCH', 'error':'CRASH_OR_COMPETING_READ_AMBIGUOUS_NO_AUTORETRY',
                        'retrieved_at':None, 'records':[]}
                else:
                    observation = procurement.collect(spec)
                observation['trace_id'] = mission.trace_id
                ledger._append(key,'decision','opportunity',observation)
            observations.append(observation)
    with ledger.transaction():
        ensure_running(queue)
        # Serialize terminal review and state/audit; concurrent replay cannot duplicate.
        if ledger.db.execute('SELECT state FROM field_runs WHERE trace_id=?',(mission.trace_id,)).fetchone()[0]=='COMPLETE':
            return report(ledger,mission.trace_id)
        case = build_case(root, mission.trace_id, observations, now)
        task = Task(mission.trace_id, 'opportunity', mission.deadline, 4, 10000, 0)
        queue.submit('field-'+mission.trace_id,task,case)
        claim = queue.claim('field-review')
        if claim is None or claim['id'] != 'field-'+mission.trace_id:
            # Do not steal an older queued task. Roll back this claim/submission.
            raise ValueError('Existing queued work must be processed first')
        review = queue.execute(claim,root)
        candidates, excluded = assess(observations)
        result = {'trace_id':mission.trace_id, 'domain':'opportunity', 'schema':'apex.field.v1',
            'status':'CANDIDATE_FOUND_AWAITING_VALIDATION' if candidates else 'BLOCKED_EXTERNAL_FETCH' if not any(o.get('retrieval_status')=='OBSERVED_UNCORROBORATED' for o in observations) else 'NO_ELIGIBLE_CANDIDATE',
            'observations':observations, 'candidates':candidates, 'excluded':excluded,
            'candidate_count':len(candidates), 'excluded_count':len(excluded), 'review':review,
            'uac_invocations':[{'agent_id':role,'role_version':'deterministic-field-v1','task_id':mission.trace_id,
                'trace_id':mission.trace_id, 'capabilities':['local_evidence_review'], 'allowed_domains':['opportunity'],
                'status':'PARTIAL', 'cost_used_pence':0, 'uncertainties':['No independent corroboration or calibrated utility']} for role in ['8-12','8-13']],
            'next_internal_action':{'action_id':'research-'+mission.trace_id, 'state':'AWAITING_OWNER_DECISION',
                'capability':'REVIEW_PUBLIC_ELIGIBILITY', 'expires_at':mission.deadline, 'external_writes_permitted':False},
            'actions_executed':[], 'paid_api_spend_pence':0, 'elapsed_seconds':round(time.monotonic()-started,3),
            'baseline':{'method':'Same-input complete manual checklist', 'independent_reviewer':None,
                        'correction_minutes':None, 'manual_minutes':None, 'time_saved_minutes':None, 'usefulness':None},
            'evolution_verdict':'NO_PROMOTION_MISSING_INDEPENDENT_OUTCOME',
            'production_status':'NOT_DEPLOYED', 'continuous_worker':False}
        seq = ledger._append('field-result-'+mission.trace_id,'decision','opportunity',result)
        ledger.db.execute("UPDATE field_runs SET state='COMPLETE',result_seq=? WHERE trace_id=?",(seq,mission.trace_id))
        return {'ledger_seq':seq, **result}


def owner_decision(ledger, root, trace, approve):
    """Local OS-authenticated owner decision; does not execute even approved research."""
    if type(approve) is not bool or os.geteuid() != Path(root).stat().st_uid:
        raise PermissionError('Workspace owner identity required')
    queue = Jobs(ledger)
    with ledger.transaction():
        ensure_running(queue)
        result = report(ledger,trace)
        action = result['next_internal_action']
        if timestamp(action['expires_at']) <= datetime.now(timezone.utc): raise PermissionError('Decision expired')
        return ledger._append('field-owner-'+trace,'decision','opportunity', {
            'trace_id':trace, 'action_id':action['action_id'], 'owner_uid':os.geteuid(),
            'decision':'APPROVE_INTERNAL_REVIEW' if approve else 'REJECT_INTERNAL_REVIEW',
            'scope':'REVIEW_PUBLIC_ELIGIBILITY', 'external_writes_permitted':False, 'actions_executed':[]})
