import copy
import unittest
from unittest.mock import patch
import test_missions
from apex.kernel.schedules import Schedules
from apex.kernel.policy import KillState


class ScheduleTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    packet=test_missions.MissionTests.packet

    def test_due_coalescing_restart_limit_and_idempotence(self):
        s=Schedules(self.ledger);s.add('daily',self.packet(),60,100,2)
        s.add('daily',self.packet(),60,100,2)
        self.assertEqual(s.poll(99)['released'],[])
        self.assertEqual(s.poll(100)['released'],['sched-daily-1'])
        self.assertEqual(Schedules(self.ledger).poll(100)['released'],[])
        self.assertEqual(s.poll(1000)['released'],['sched-daily-2'])
        self.assertEqual(s.poll(10000)['released'],[])
        self.assertEqual(s.status()[0]['issued'],2)

    def test_atomic_release_failure_stop_and_code_change(self):
        s=Schedules(self.ledger);s.add('daily',self.packet(),60,100,2)
        original=self.ledger._append
        def fail(key,*args):
            if key.startswith('schedule-release-'):raise RuntimeError('injected')
            return original(key,*args)
        with patch.object(self.ledger,'_append',side_effect=fail):
            with self.assertRaises(RuntimeError):s.poll(100)
        self.assertEqual(s.status()[0]['issued'],0)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM mission_graphs').fetchone()[0],0)
        s.missions.queue.set_stop(KillState.STOP_EXECUTION)
        with self.assertRaises(PermissionError):s.poll(100)
        s.missions.queue.set_stop(KillState.RUNNING)
        with patch('apex.kernel.schedules.code_digest',return_value='changed'):
            with self.assertRaises(ValueError):s.poll(100)

    def test_invalid_caps_and_expiry_preserved(self):
        s=Schedules(self.ledger)
        for interval in [True,0,59,float('nan'),604801]:
            with self.assertRaises(ValueError):s.add('bad',self.packet(),interval,100,2)
        s.add('daily',self.packet(),60,100,1);s.poll(100)
        import json
        saved=json.loads(self.ledger.db.execute('SELECT packet FROM mission_graphs').fetchone()[0])
        self.assertEqual(saved['nodes'][0]['task']['expires_at'],self.packet()['nodes'][0]['task']['expires_at'])
