import unittest
from unittest.mock import patch, Mock
import test_missions
from apex.kernel.worker_health import record,status
from apex.kernel.worker import serve


class HealthTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown

    def test_absent_fresh_stale_and_clock_rollback(self):
        self.assertEqual(status(self.ledger),{'state':'NOT_OBSERVED'})
        with patch('apex.kernel.worker_health.time.time',return_value=1000):
            record(self.ledger,'CYCLE_COMPLETED',60)
        self.assertTrue(status(self.ledger,now=1120)['fresh'])
        self.assertFalse(status(self.ledger,now=1121)['fresh'])
        self.assertFalse(status(self.ledger,now=999)['fresh'])

    def test_audit_failure_rolls_back_observation(self):
        record(self.ledger,'STOPPED',60)
        prior=status(self.ledger)
        with patch.object(self.ledger,'_append',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):record(self.ledger,'CYCLE_COMPLETED',60)
        self.assertEqual(status(self.ledger)['state'],prior['state'])
        self.ledger.verify()

    def test_three_failures_exit_and_redact_error_messages(self):
        event=Mock();event.is_set.return_value=False
        with patch('threading.Event',return_value=event),patch('apex.kernel.worker.signal.signal'),patch('builtins.print'),patch('apex.kernel.worker.cycle',side_effect=OSError('SECRET')) as execute:
            with self.assertRaises(SystemExit) as stopped:serve(self.root)
        self.assertEqual(stopped.exception.code,78)
        self.assertEqual(execute.call_count,3)
        self.assertEqual(event.wait.call_count,2)
        self.assertEqual(status(self.ledger)['state'],'RETRY_EXHAUSTED')
        self.assertNotIn('SECRET',str(self.ledger.records('opportunity')))

    def test_clean_shutdown_is_recorded(self):
        event=Mock();event.is_set.side_effect=[False,True]
        with patch('threading.Event',return_value=event),patch('apex.kernel.worker.signal.signal'),patch('builtins.print'),patch('apex.kernel.worker.cycle',return_value={'state':'STOPPED'}):
            serve(self.root)
        self.assertEqual(status(self.ledger)['state'],'EXITED')
