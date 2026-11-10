from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sqlite3,tempfile,unittest
from unittest.mock import patch
from test_kernel import document,NOW,WORK
from apex.kernel.schema import Case
from apex.kernel.workflow import Task,run,read_report
from apex.kernel.memory import Ledger
from apex.kernel.policy import Policy,KillState

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True); self.tmp=tempfile.TemporaryDirectory(dir=WORK)
        self.root=Path(self.tmp.name); self.doc=document(self.root)
        self.task=Task('task1','opportunity','2026-11-20T00:00:00Z',2,10000,0)
    def tearDown(self): self.tmp.cleanup()
    def execute(self,task=None,**kwargs):
        with Ledger(self.root) as ledger:
            return run(task or self.task,Case.parse(self.doc),self.root,ledger,Policy('opportunity'),NOW,**kwargs)
    def test_slice_blocked_and_replay_survives_restart(self):
        first=self.execute(); second=self.execute()
        self.assertEqual(first['report']['status'],'BLOCKED_PENDING_EVIDENCE')
        self.assertEqual(first['ledger_seq'],second['ledger_seq'])
        self.assertTrue(second['replayed']); self.assertFalse(second['evidence_rechecked'])
        with Ledger.read_only(self.root) as ledger:
            self.assertEqual(read_report(ledger,'opportunity','task1')['report'],first['report'])
            with self.assertRaises(ValueError): read_report(ledger,'studio','task1')
            with self.assertRaises(sqlite3.OperationalError): ledger.append('bad','decision','opportunity',{})
    def test_expiry_and_source_limit_logged_before_reads(self):
        for task in [replace(self.task,expires_at=NOW.isoformat()),replace(self.task,max_sources=1)]:
            self.doc['evidence'].append(dict(self.doc['evidence'][0],id='e'+str(len(self.doc['evidence'])+1)))
            with patch('apex.kernel.workflow.propose',side_effect=AssertionError('Must not execute')):
                r=self.execute(replace(task,task_id='task'+str(len(self.doc['evidence']))))
                self.assertEqual(r['report']['status'],'DENIED')
    def test_time_budget_fails_closed_no_proposals_published(self):
        ticks=iter([0,11])
        r=self.execute(clock=lambda:next(ticks))
        self.assertEqual(r['report']['reason'],'ELAPSED_TIME_BUDGET_EXCEEDED')
        self.assertNotIn('discovery',r['report'])
    def test_invalid_budget_types(self):
        for kwargs in [{'max_sources':True},{'max_runtime_ms':0},{'paid_budget_pence':1},{'paid_budget_pence':False}]:
            with self.assertRaises(ValueError): self.execute(replace(self.task,**kwargs))
    def test_key_conflict(self):
        self.execute(); self.doc['problem']='Changed problem'
        with self.assertRaises(ValueError): self.execute()
    def test_stop_denies_before_record(self):
        with Ledger(self.root) as ledger:
            with self.assertRaises(PermissionError):
                run(self.task,Case.parse(self.doc),self.root,ledger,Policy('opportunity',KillState.STOP_EXECUTION),NOW)
            self.assertEqual(ledger.verify(),0)
    def test_exception_rolls_back_and_retry_is_explicit(self):
        with patch('apex.kernel.workflow.propose',side_effect=SystemExit('interrupted stage')):
            with self.assertRaises(SystemExit): self.execute()
        with Ledger.read_only(self.root) as ledger: self.assertEqual(ledger.verify(),0)
        self.assertEqual(self.execute()['ledger_seq'],1)
    def test_failure_is_persisted_redacted_and_not_retried(self):
        with patch('apex.kernel.workflow.propose',side_effect=RuntimeError('secret-detail')):
            result=self.execute()
        self.assertEqual(result['report']['status'],'FAILED')
        self.assertNotIn('secret-detail',str(result))
        self.assertTrue(self.execute()['replayed'])
    def test_read_only_does_not_create_store(self):
        with self.assertRaises(ValueError): Ledger.read_only(self.root)
        self.assertFalse((self.root/'runtime').exists())
    def test_malicious_ssrf_metadata_is_not_fetched(self):
        self.doc['evidence'][0]['source_uri']='https://127.0.0.1/admin'
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            r=self.execute()
        codes=r['report']['discovery']['source_review']['problem_discovery']['missing_evidence']
        self.assertIn('INVALID_PUBLIC_URI',codes)
    def test_integrity_eligible_fixture_still_cannot_promote(self):
        self.doc['evidence'][0].update(synthetic=False,sensitivity='public')
        r=self.execute()['report']
        self.assertEqual(len(r['discovery']['hypotheses']),3)
        self.assertEqual(r['promotion'],'REJECT_NO_INDEPENDENT_EVALUATION')
        self.assertEqual(r['evaluation_status'],'NO_EMPIRICAL_EXPERIMENT_RUN')
