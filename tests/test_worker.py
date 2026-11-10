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
