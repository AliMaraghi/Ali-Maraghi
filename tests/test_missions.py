"""Dependency scheduling uses real SQLite jobs; fixtures are synthetic."""
from dataclasses import asdict
import json
import unittest
from unittest.mock import patch
import test_jobs
from apex.kernel.missions import Missions
from apex.kernel.policy import KillState


class MissionTests(unittest.TestCase):
    setUp = test_jobs.JobTests.setUp
    tearDown = test_jobs.JobTests.tearDown
    submit = test_jobs.JobTests.submit
    # Reuse isolated workspace setup, not inherited test methods.
    def packet(self):
        nodes=[]
        for nid,deps in [('research',[]),('critic',['research'])]:
            task=asdict(self.task);task['task_id']='graph-'+nid
            nodes.append({'id':nid,'depends_on':deps,'role':'8-12','task':task,'case':json.loads(json.dumps(asdict(self.case)))})
        return {'trace_id':'graph','nodes':nodes,'paid_budget_pence':0}

    def test_dependency_replay_restart_and_exact_job_selection(self):
        s=Missions(self.ledger);s.submit(self.packet());s.submit(self.packet())
        self.submit('unrelated')
        s.tick('graph',self.root,'worker')
        states=s.status('graph')['nodes'];self.assertEqual([n['state'] for n in states],['COMPLETE','WAITING'])
        s=Missions(self.ledger);s.tick('graph',self.root,'worker')
        count=self.ledger.verify();s.tick('graph',self.root,'worker')
        self.assertEqual(count,self.ledger.verify())
        self.assertEqual(self.jobs.status()['jobs'][-1]['state'],'QUEUED')

    def test_cycles_unknown_roles_cost_and_code_changes_rejected(self):
        s=Missions(self.ledger)
        for kind in ['cycle','role','cost']:
            p=self.packet()
            if kind=='cycle':p['nodes'][0]['depends_on']=['critic']
            if kind=='role':p['nodes'][0]['role']='8-01'
            if kind=='cost':p['paid_budget_pence']=True
            with self.assertRaises(ValueError):s.submit(p)
        s.submit(self.packet())
        with patch('apex.kernel.missions.code_digest',return_value='changed'):
            with self.assertRaises(ValueError):s.tick('graph',self.root,'worker')

    def test_stop_and_submit_audit_failure_atomic(self):
        s=Missions(self.ledger)
        with patch.object(self.ledger,'_append',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):s.submit(self.packet())
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM mission_graphs').fetchone()[0],0)
        s.submit(self.packet());self.jobs.set_stop(KillState.STOP_EXECUTION)
        with self.assertRaises(PermissionError):s.tick('graph',self.root,'worker')
        self.assertTrue(all(n['state']=='WAITING' for n in s.status('graph')['nodes']))


