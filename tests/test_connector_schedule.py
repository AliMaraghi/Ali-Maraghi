import hashlib,json,unittest
from unittest.mock import patch
from urllib.parse import urlencode
from http.cookies import SimpleCookie
import test_missions,test_google_web
from apex.kernel.schedules import Schedules
from apex.kernel.worker import cycle
from apex.kernel.policy import KillState

OWNER=hashlib.sha256(b'owner@example.org').hexdigest()


class ConnectorScheduleTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown

    def due(self):
        with self.ledger.transaction():self.ledger.db.execute('UPDATE connector_schedules SET next_due=0')

    def row(self):return Schedules(self.ledger).connector_status()[0]

    def test_bounds_and_allowlist(self):
        s=Schedules(self.ledger)
        for args in [('shell',OWNER,900,0,5),('gmail','x',900,0,5),('gmail',OWNER,60,0,5),('gmail',OWNER,900,0,5000)]:
            with self.assertRaises(ValueError):s.arm_connector(*args)

    def test_release_is_single_until_settled_and_unconfigured_worker_disables(self):
        s=Schedules(self.ledger);s.arm_connector('gmail',OWNER,900,0,10)
        self.assertEqual(s.poll()['connectors_released'],['gmail'])
        self.assertEqual(s.poll(now=2**40)['connectors_released'],[])  # Pending blocks overlap.
        for expected in (1,2,3):
            outcome=cycle(self.root)['connector_outcomes'][0]
            self.assertEqual((outcome['state'],outcome['error_type']),('CONNECTOR_FAILED','PermissionError'))
            self.assertEqual(self.row()['failures'],expected);self.due()
        self.assertEqual(self.row()['enabled'],0)
        self.assertEqual(cycle(self.root)['connector_outcomes'],[])

    def test_success_resets_failures_and_resync_disables(self):
        s=Schedules(self.ledger);s.arm_connector('gmail',OWNER,900,0,10)
        with patch('apex.google_web.scheduled_gmail_sync',return_value={'status':'PAGE_SYNCHRONIZED'}) as run:
            out=cycle(self.root,'/etc/apex/google-runtime.json')['connector_outcomes']
        run.assert_called_once()
        self.assertEqual(run.call_args.args[1:],('/etc/apex/google-runtime.json',OWNER))
        self.assertEqual(out[0]['state'],'PAGE_SYNCHRONIZED')
        self.assertEqual((self.row()['remaining'],self.row()['failures'],self.row()['pending']),(9,0,0))
        self.due()
        with patch('apex.google_web.scheduled_gmail_sync',return_value={'status':'RESYNC_REQUIRED','cursor_preserved':True}):
            self.assertTrue(cycle(self.root,'cfg')['connector_outcomes'][0]['disabled'])

    def test_durable_stop_prevents_connector_run(self):
        Schedules(self.ledger).arm_connector('gmail',OWNER,900,0,10)
        self.jobs.set_stop(KillState.STOP_EXECUTION)
        with patch('apex.google_web.scheduled_gmail_sync') as run:
            self.assertEqual(cycle(self.root,'cfg')['state'],'STOPPED')
        run.assert_not_called()

    def test_disarm_settles_pending_and_stale_outcome_ignored(self):
        s=Schedules(self.ledger);s.arm_connector('gmail',OWNER,900,0,10);s.poll()
        s.disarm_connector('gmail')
        self.assertIsNone(s.record_connector('gmail',1,'PAGE_SYNCHRONIZED'))
        self.assertEqual((self.row()['enabled'],self.row()['pending']),(0,0))


class ConnectorHandlerTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    app=test_google_web.GoogleWebTests.app
    call=test_google_web.GoogleWebTests.call

    def session(self,app):
        response,_=self.call(app);cookie=response['headers']['Set-Cookie']
        parsed=SimpleCookie();parsed.load(cookie);sid=parsed['__Host-apex-owner'].value
        csrf=self.ledger.db.execute('SELECT csrf FROM owner_web_sessions WHERE id=?',(hashlib.sha256(sid.encode()).hexdigest(),)).fetchone()[0]
        return cookie,urlencode({'csrf':csrf})

    def test_owner_mismatch_and_unconnected_handler_fail_closed(self):
        from apex.google_web import scheduled_gmail_sync
        app=self.app();path=app.google_routes.path
        with self.assertRaises(PermissionError):scheduled_gmail_sync(self.ledger,path,'0'*64)
        with self.assertRaises(PermissionError):scheduled_gmail_sync(self.ledger,path,OWNER)

    def test_owner_route_requires_connection_then_arms_and_disarms(self):
        app=self.app();cookie,form=self.session(app)
        denied,_=self.call(app,'/connections/google/schedule',cookie,'POST',form)
        self.assertTrue(denied['status'].startswith('403'))
        with patch('apex.google_tokens.TokenBroker.status',return_value={'status':'AUTHORIZED_NOT_VERIFIED'}):
            armed,_=self.call(app,'/connections/google/schedule',cookie,'POST',form)
        self.assertTrue(armed['status'].startswith('303'))
        row=Schedules(self.ledger).connector_status()[0]
        self.assertEqual((row['interval_seconds'],row['remaining'],row['enabled']),(900,672,1))
        stored=self.ledger.db.execute('SELECT owner_digest FROM connector_schedules').fetchone()[0]
        self.assertEqual(stored,OWNER)
        page=self.call(app,cookie=cookie)[1].decode()
        self.assertIn('Recurring sync: enabled',page)
        self.call(app,'/connections/google/unschedule',cookie,'POST',form)
        self.assertEqual(Schedules(self.ledger).connector_status()[0]['enabled'],0)
        bad,_=self.call(app,'/connections/google/unschedule',cookie,'POST','csrf=wrong')
        self.assertTrue(bad['status'].startswith('403'))


if __name__=='__main__':unittest.main()
