"""Durable local evidence jobs with fenced leases and atomic workflow/audit.

Dispatch holds the SQLite write transaction. A concurrent stop takes effect
after an in-flight bounded job commits; this is graceful, not preemptive stop.
No arbitrary handlers, external effects, network calls or daemon are provided.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import time
import uuid

from .engine import canonical, code_digest
from .schema import Case, identifier, strict_json
from .workflow import Task, run
from .policy import Policy, KillState


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid job integer bound')
    return value


class Jobs:
    @classmethod
    def read_only(cls, ledger):
        instance = cls.__new__(cls)
        instance.ledger, instance.db = ledger, ledger.db
        if instance.db.execute('SELECT version FROM job_meta WHERE id=1').fetchone() != (1,):
            raise ValueError('Queue schema absent or unsupported')
        return instance

    def __init__(self, ledger):
        self.ledger, self.db = ledger, ledger.db
        with ledger.transaction():
            self.db.execute('CREATE TABLE IF NOT EXISTS job_meta (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, stop TEXT NOT NULL)')
            self.db.execute("INSERT OR IGNORE INTO job_meta VALUES(1,1,'RUNNING')")
            if self.db.execute('SELECT version FROM job_meta').fetchone()[0] != 1:
                raise ValueError('Unknown queue schema')
            self.db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, domain TEXT NOT NULL, payload TEXT NOT NULL,
                fingerprint TEXT NOT NULL, state TEXT NOT NULL,
                attempts INTEGER NOT NULL, max_attempts INTEGER NOT NULL,
                available_at INTEGER NOT NULL, lease_until INTEGER,
                token TEXT, worker TEXT, result_seq INTEGER)''')

    def audit(self, job_id, domain, event, **details):
        return self.ledger._append('job-' + uuid.uuid4().hex, 'job', domain,
                                   {'job_id': job_id, 'event': event, **details})

    def control(self):
        return KillState(self.db.execute('SELECT stop FROM job_meta WHERE id=1').fetchone()[0])

    def set_stop(self, state):
        # Trusted local operator API, not remote owner authentication.
        if not isinstance(state, KillState):
            raise ValueError('Invalid stop state')
        with self.ledger.transaction():
            self.db.execute('UPDATE job_meta SET stop=? WHERE id=1', (state.value,))
            self.audit('queue', 'opportunity', 'OPERATOR_CONTROL', state=state.value)

    def submit(self, job_id, task, case, *, now=None, max_attempts=2):
        identifier(job_id)
        now = integer(int(time.time()) if now is None else now, 0, 2**53)
        integer(max_attempts, 1, 3)
        task = Task.parse(asdict(task))
        case = Case.parse(json.loads(canonical(asdict(case))))
        if task.domain != case.domain:
            raise ValueError('Job domain mismatch')
        payload = canonical({'task': asdict(task), 'case': asdict(case), 'code_sha256': code_digest()})
        if len(payload.encode()) > 262144:
            raise ValueError('Job payload too large')
        fingerprint = hashlib.sha256((payload + str(max_attempts)).encode()).hexdigest()
        with self.ledger.transaction():
            if self.control() is not KillState.RUNNING:
                raise PermissionError('Queue stopped')
            prior = self.db.execute('SELECT fingerprint FROM jobs WHERE id=?', (job_id,)).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise ValueError('Job identity conflicts with prior request')
                return job_id
            if self.db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 1000:
                raise ValueError('Queue retention limit; reviewed archival required')
            if self.db.execute("SELECT count(*) FROM jobs WHERE state IN ('QUEUED','RUNNING')").fetchone()[0] >= 100:
                raise ValueError('Active queue limit reached')
            self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,0,?,?,NULL,NULL,NULL,NULL)',
                            (job_id, task.domain, payload, fingerprint, 'QUEUED', max_attempts, now))
            self.audit(job_id, task.domain, 'SUBMITTED', fingerprint=fingerprint)
        return job_id

    def claim(self, worker, *, now=None, lease_seconds=30, job_id=None):
        identifier(worker)
        if job_id is not None: identifier(job_id)
        now = integer(int(time.time()) if now is None else now, 0, 2**53)
        integer(lease_seconds, 15, 300)
        with self.ledger.transaction():
            if self.control() is not KillState.RUNNING:
                raise PermissionError('Queue stopped')
            for jid, domain in self.db.execute("SELECT id,domain FROM jobs WHERE state='RUNNING' AND lease_until<=? AND attempts>=max_attempts", (now,)).fetchall():
                self.db.execute("UPDATE jobs SET state='DEAD',token=NULL,worker=NULL,lease_until=NULL WHERE id=?", (jid,))
                self.audit(jid, domain, 'DEAD_LEASE_EXHAUSTED')
            row = self.db.execute("""SELECT id,domain,attempts FROM jobs WHERE
                ((state='QUEUED' AND available_at<=?) OR
                (state='RUNNING' AND lease_until<=? AND attempts<max_attempts))
                AND (? IS NULL OR id=?)
                ORDER BY available_at,id LIMIT 1""", (now, now, job_id, job_id)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            self.db.execute("UPDATE jobs SET state='RUNNING',attempts=attempts+1,lease_until=?,token=?,worker=? WHERE id=?",
                            (now+lease_seconds, token, worker, row[0]))
            self.audit(row[0], row[1], 'CLAIMED', attempt=row[2]+1, lease_until=now+lease_seconds)
            return {'id': row[0], 'token': token, 'worker': worker}

    def leased(self, claim, now):
        row = self.db.execute('SELECT domain,payload,attempts,max_attempts,lease_until,token,worker,state FROM jobs WHERE id=?', (claim['id'],)).fetchone()
        if (row is None or row[7] != 'RUNNING' or row[4] <= now
                or row[5] != claim['token'] or row[6] != claim['worker']):
            raise ValueError('Stale, expired or foreign lease')
        return row

    def finish(self, claim, *, now=None, success=True, result_seq=None):
        now = integer(int(time.time()) if now is None else now, 0, 2**53)
        if type(success) is not bool:
            raise ValueError('Invalid success flag')
        with self.ledger.transaction():
            row = self.leased(claim, now)
            state = 'COMPLETE' if success else ('DEAD' if row[2] >= row[3] else 'QUEUED')
            if success:
                result = self.db.execute('SELECT domain,kind,event_key,payload FROM events WHERE seq=?', (result_seq,)).fetchone()
                packet = strict_json(row[1])
                task = packet['task']
                expected = hashlib.sha256(canonical({'task': task, 'case': packet['case'],
                                                     'code': packet['code_sha256']}).encode()).hexdigest()
                if (type(result_seq) is not int or result is None
                        or result[:3] != (row[0], 'decision', 'wf-' + task['task_id'])
                        or strict_json(result[3]).get('request_sha256') != expected):
                    raise ValueError('Matching durable workflow result required')
            elif result_seq is not None:
                raise ValueError('Failed attempt cannot attach a result')
            self.db.execute('UPDATE jobs SET state=?,available_at=?,lease_until=NULL,token=NULL,worker=NULL,result_seq=? WHERE id=?',
                            (state, now + (0 if success else min(120, 5 * 2**row[2])), result_seq, claim['id']))
            self.audit(claim['id'], row[0], state, result_seq=result_seq)
            return state

    def execute(self, claim, workspace, *, now_fn=lambda: int(time.time())):
        with self.ledger.transaction():
            now = integer(now_fn(), 0, 2**53)
            row = self.leased(claim, now)
            if self.control() is not KillState.RUNNING:
                raise PermissionError('Queue stopped before handler')
            payload = strict_json(row[1])
            if payload['code_sha256'] != code_digest():
                state = self.finish(claim, now=now, success=False)
                return {'state': state, 'reason': 'CODE_CHANGED_RESUBMIT_AFTER_REVIEW'}
            task, case = Task.parse(payload['task']), Case.parse(payload['case'])
            result = run(task, case, workspace, self.ledger, Policy(row[0]),
                         datetime.fromtimestamp(now, timezone.utc))
            state = self.finish(claim, now=now_fn(), success=True, result_seq=result['ledger_seq'])
            return {'state': state, 'workflow_status': result['report']['status'],
                    'result_seq': result['ledger_seq'], 'replayed': result['replayed']}

    def run_one(self, workspace, worker, *, now_fn=lambda: int(time.time())):
        claim = self.claim(worker, now=now_fn())
        return {'state': 'EMPTY'} if claim is None else self.execute(claim, workspace, now_fn=now_fn)

    def status(self):
        return {'stop_state': self.control().value,
                'jobs': [dict(zip(('id', 'domain', 'state', 'attempts', 'max_attempts', 'result_seq'), row))
                         for row in self.db.execute('SELECT id,domain,state,attempts,max_attempts,result_seq FROM jobs ORDER BY id')],
                'scope': 'Local evidence jobs only; no external effects or production daemon'}
