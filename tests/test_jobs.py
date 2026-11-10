"""Exercise the actual SQLite queue/workflow, including two-process contention/crash."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from apex.kernel.jobs import Jobs
from apex.kernel.memory import Ledger
from apex.kernel.policy import KillState
from apex.kernel.schema import Case
from apex.kernel.workflow import Task
from test_kernel import document, NOW, WORK

T = int(NOW.timestamp())


class JobTests(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=WORK)
        self.root = Path(self.temp.name)
        self.case = Case.parse(document(self.root))
        self.task = Task('queued-test', 'opportunity', '2026-11-20T00:00:00Z', 2, 10000, 0)
        self.ledger = Ledger(self.root); self.jobs = Jobs(self.ledger)

    def tearDown(self):
        self.ledger.close(); self.temp.cleanup()

    def submit(self, jid='job1', **kwargs):
        return self.jobs.submit(jid, self.task, self.case, now=T, **kwargs)

    def test_actual_workflow_receipt_and_idempotence_survive_reopen(self):
        self.submit(); self.submit()
        result = self.jobs.run_one(self.root, 'worker', now_fn=lambda:T+1)
        self.assertEqual(result['state'], 'COMPLETE')
        self.assertEqual(result['workflow_status'], 'BLOCKED_PENDING_EVIDENCE')
        with Ledger.read_only(self.root) as l:
            status = Jobs.read_only(l).status()
            self.assertEqual(status['jobs'][0]['result_seq'], result['result_seq'])
            self.assertEqual(len([r for r in l.records('opportunity') if r['kind']=='decision']),1)
        self.assertEqual(self.jobs.run_one(self.root,'worker',now_fn=lambda:T+2)['state'],'EMPTY')

    def test_every_stop_persists_and_blocks_before_handler(self):
        self.submit(); claim=self.jobs.claim('worker',now=T)
        for state in KillState:
            if state is KillState.RUNNING: continue
            self.jobs.set_stop(state)
            with Ledger.read_only(self.root) as l:
                self.assertEqual(Jobs.read_only(l).control(),state)
            with patch('apex.kernel.jobs.run', side_effect=AssertionError('Handler executed')):
                with self.assertRaises(PermissionError):self.jobs.claim('w2',now=T+1)
                with self.assertRaises(PermissionError):self.jobs.execute(claim,self.root,now_fn=lambda:T+1)
                with self.assertRaises(PermissionError):self.submit('job2')

    def test_reclaimed_same_worker_has_new_token_and_exact_expiry(self):
        self.submit(); old=self.jobs.claim('worker',now=T,lease_seconds=15)
        with self.assertRaises(ValueError):self.jobs.finish(old,now=T+15,success=False)
        new=self.jobs.claim('worker',now=T+15,lease_seconds=15)
        self.assertNotEqual(old['token'],new['token'])
        with self.assertRaises(ValueError):self.jobs.finish(old,now=T+16,success=False)
        self.assertEqual(self.jobs.execute(new,self.root,now_fn=lambda:T+16)['state'],'COMPLETE')

    def test_submit_and_control_audit_failure_rolls_back_mutation(self):
        with patch.object(self.jobs,'audit',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.submit()
            with self.assertRaises(RuntimeError):self.jobs.set_stop(KillState.STOP_EXECUTION)
        self.assertEqual(self.jobs.status()['jobs'],[])
        self.assertEqual(self.jobs.control(),KillState.RUNNING)
        self.assertEqual(self.ledger.verify(),0)

    def test_completion_audit_failure_rolls_back_workflow_and_job(self):
        self.submit(); claim=self.jobs.claim('worker',now=T)
        before=self.ledger.verify()
        with patch.object(self.jobs,'audit',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.jobs.execute(claim,self.root,now_fn=lambda:T+1)
        self.assertEqual(self.ledger.verify(),before)
        self.assertEqual(self.jobs.status()['jobs'][0]['state'],'RUNNING')
        self.assertEqual(self.jobs.execute(claim,self.root,now_fn=lambda:T+2)['state'],'COMPLETE')

    def test_claim_audit_failure_does_not_consume_attempt(self):
        self.submit()
        with patch.object(self.jobs,'audit',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.jobs.claim('w',now=T)
        row=self.jobs.status()['jobs'][0]
        self.assertEqual((row['state'],row['attempts']),('QUEUED',0))

    def test_queue_bound_and_unknown_control_fail_closed(self):
        for n in range(100):self.submit('bounded-'+str(n))
        with self.assertRaises(ValueError):self.submit('overflow')
        self.ledger.db.execute("UPDATE job_meta SET stop='UNKNOWN' WHERE id=1")
        with patch('apex.kernel.jobs.run',side_effect=AssertionError('Must not execute')):
            with self.assertRaises(ValueError):self.jobs.run_one(self.root,'w',now_fn=lambda:T)

    def test_retry_backoff_limit_and_expired_dead_job_does_not_starve_next(self):
        self.submit(max_attempts=2);claim=self.jobs.claim('w',now=T)
        self.assertEqual(self.jobs.finish(claim,now=T+1,success=False),'QUEUED')
        self.assertIsNone(self.jobs.claim('w',now=T+10))
        claim=self.jobs.claim('w',now=T+11,lease_seconds=15)
        self.assertIsNotNone(claim)
        self.submit('job2')
        self.assertEqual(self.jobs.claim('w',now=T+26)['id'],'job2')
        self.assertEqual(self.jobs.status()['jobs'][0]['state'],'DEAD')

    def test_finite_budget_and_exact_queue_counts_fail_before_state(self):
        for cost in [float('nan'),float('inf'),-1,1,True,0.0]:
            with self.assertRaises(ValueError):self.jobs.submit('bad',replace(self.task,paid_budget_pence=cost),self.case,now=T)
        for attempts in [True,1.5,float('nan'),0,4]:
            with self.assertRaises(ValueError):self.submit(max_attempts=attempts)
        self.assertEqual(self.jobs.status()['jobs'],[])

    def test_identity_collision_and_unrelated_result_rejected(self):
        self.submit()
        with self.assertRaises(ValueError):self.jobs.submit('job1',replace(self.task,max_sources=1),self.case,now=T)
        seq=self.ledger.append('unrelated','decision','opportunity',{})
        claim=self.jobs.claim('worker',now=T)
        with self.assertRaises(ValueError):self.jobs.finish(claim,now=T+1,result_seq=seq)
        self.assertEqual(self.jobs.status()['jobs'][0]['state'],'RUNNING')

    def test_code_change_denies_dispatch(self):
        self.submit();claim=self.jobs.claim('w',now=T)
        with patch('apex.kernel.jobs.code_digest',return_value='0'*64), \
             patch('apex.kernel.jobs.run',side_effect=AssertionError('Must not execute')):
            r=self.jobs.execute(claim,self.root,now_fn=lambda:T+1)
        self.assertEqual(r['reason'],'CODE_CHANGED_RESUBMIT_AFTER_REVIEW')

    def test_two_processes_cannot_claim_same_unexpired_attempt(self):
        self.submit()
        code='''import sys,json
from pathlib import Path
from apex.kernel.memory import Ledger
from apex.kernel.jobs import Jobs
with Ledger(Path(sys.argv[1])) as l:
 print(json.dumps(Jobs(l).claim(sys.argv[2],now=int(sys.argv[3]))))
'''
        procs=[subprocess.Popen([sys.executable,'-B','-c',code,str(self.root),w,str(T)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for w in ('w1','w2')]
        results=[]
        for p in procs:
            out,err=p.communicate(timeout=10);self.assertEqual(p.returncode,0,err);results.append(json.loads(out))
        self.assertEqual(sum(x is not None for x in results),1)

    def test_process_crash_during_completion_rolls_back_and_lease_recovers(self):
        self.submit()
        code='''import os,sys
from pathlib import Path
from apex.kernel.memory import Ledger
from apex.kernel.jobs import Jobs
with Ledger(Path(sys.argv[1])) as l:
 q=Jobs(l);c=q.claim('crashing-worker',now=int(sys.argv[2]),lease_seconds=15)
 q.finish=lambda *a,**k:os._exit(17)
 q.execute(c,Path(sys.argv[1]),now_fn=lambda:int(sys.argv[2])+1)
'''
        p=subprocess.run([sys.executable,'-B','-c',code,str(self.root),str(T)],capture_output=True,timeout=10)
        self.assertEqual(p.returncode,17,p.stderr)
        with Ledger(self.root) as reopened:
            q=Jobs(reopened)
            self.assertEqual(q.status()['jobs'][0]['state'],'RUNNING')
            self.assertFalse(any(r['kind']=='decision' for r in reopened.records('opportunity')))
            result=q.run_one(self.root,'recovery-worker',now_fn=lambda:T+15)
            self.assertEqual(result['state'],'COMPLETE')
            self.assertEqual(q.status()['jobs'][0]['attempts'],2)
            self.assertEqual(len([r for r in reopened.records('opportunity') if r['kind']=='decision']),1)

    def test_nested_transaction_failure_does_not_escape_outer_rollback(self):
        with self.assertRaises(RuntimeError):
            with self.ledger.transaction():
                self.submit()
                raise RuntimeError('outer failure')
        self.assertEqual(self.jobs.status()['jobs'],[])
        self.assertEqual(self.ledger.verify(),0)
