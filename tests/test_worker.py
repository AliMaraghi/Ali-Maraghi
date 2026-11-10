import unittest
from unittest.mock import patch
import test_missions
from apex.kernel.missions import Missions
from apex.kernel.worker import cycle
from apex.kernel.policy import KillState


class WorkerTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    packet=test_missions.MissionTests.packet

    def test_two_cycles_complete_real_queue_and_stop_prevents_dispatch(self):
        m=Missions(self.ledger);m.submit(self.packet())
        self.jobs.set_stop(KillState.STOP_EXECUTION)
        self.assertEqual(cycle(self.root)['state'],'STOPPED')
        self.jobs.set_stop(KillState.RUNNING)
        self.assertEqual(cycle(self.root)['outcomes'][0]['state'],'TICK_COMPLETED')
        cycle(self.root)
        self.assertTrue(all(n['state']=='COMPLETE' for n in m.status('graph')['nodes']))
        self.assertEqual(cycle(self.root)['outcomes'],[])

    def test_code_mismatch_preserved_as_blocked(self):
        m=Missions(self.ledger);m.submit(self.packet())
        with patch('apex.kernel.missions.code_digest',return_value='changed'):
            r=cycle(self.root)
        self.assertEqual(r['outcomes'][0]['state'],'BLOCKED_INPUT_CODE_OR_STOP')
        self.assertTrue(all(n['state']=='WAITING' for n in m.status('graph')['nodes']))

    def populate(self, count=6):
        missions=Missions(self.ledger)
        for i in range(count):
            packet=self.packet();packet['trace_id']='graph'+str(i)
            for node in packet['nodes']:
                node['task']['task_id']=packet['trace_id']+'-'+node['id']
            missions.submit(packet)
        return missions

    def test_blocked_graphs_do_not_starve_later_graph_after_restart(self):
        missions=self.populate()
        original=Missions.tick
        def blocked(instance, trace, *args):
            if trace in {'graph0','graph1','graph2','graph3'}:
                raise ValueError('Blocked historical code')
            return original(instance,trace,*args)
        with patch.object(Missions,'tick',blocked):
            first=cycle(self.root)
            self.assertEqual([x['trace_id'] for x in first['outcomes']],
                             ['graph0','graph1','graph2','graph3'])
            # cycle opens a fresh connection: the persisted cursor survives it.
            second=cycle(self.root)
        self.assertEqual(second['outcomes'][0]['trace_id'],'graph4')
        self.assertEqual(missions.status('graph4')['nodes'][0]['state'],'COMPLETE')
        self.ledger.verify()

    def test_crash_after_admission_resumes_rotation(self):
        self.populate()
        with patch.object(Missions,'tick',side_effect=SystemExit('crash')):
            with self.assertRaises(SystemExit):cycle(self.root)
        self.assertEqual(cycle(self.root)['outcomes'][0]['trace_id'],'graph4')

    def test_admission_audit_failure_rolls_back_cursor_and_runs_nothing(self):
        self.populate()
        from apex.kernel.memory import Ledger
        with patch.object(Ledger,'_append',side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):cycle(self.root)
        self.assertEqual(cycle(self.root)['outcomes'][0]['trace_id'],'graph0')

    def test_stop_does_not_advance_existing_cursor(self):
        self.populate();cycle(self.root)
        before=self.ledger.db.execute('SELECT * FROM worker_dispatch').fetchall()
        self.jobs.set_stop(KillState.STOP_EXECUTION)
        self.assertEqual(cycle(self.root)['state'],'STOPPED')
        self.assertEqual(before,self.ledger.db.execute('SELECT * FROM worker_dispatch').fetchall())

    def test_process_exit_after_admission_preserves_restart_fairness(self):
        import os
        self.populate()
        child=os.fork()
        if child==0:
            with patch.object(Missions,'tick',side_effect=lambda *a:os._exit(73)):
                cycle(self.root)
            os._exit(74)
        _,status=os.waitpid(child,0)
        self.assertEqual(os.waitstatus_to_exitcode(status),73)
        self.assertEqual(cycle(self.root)['outcomes'][0]['trace_id'],'graph4')
        self.ledger.verify()
