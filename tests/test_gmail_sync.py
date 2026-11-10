import unittest
from unittest.mock import Mock,patch
from cryptography.fernet import Fernet
import test_missions
from apex.gmail_sync import GmailSync,GmailError

class GmailTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def sync(self):return GmailSync(self.ledger,Fernet.generate_key(),'owner@example.org')
    def thread(self,incoming=False):
        msgs=[{'id':'m1','threadId':'abc','internalDate':'100','labelIds':['SENT'],'payload':{'headers':[{'name':'Subject','value':'PRIVATE SUBJECT'}]}}]
        if incoming:msgs.append({'id':'m2','threadId':'abc','internalDate':'200','labelIds':['INBOX']})
        return {'id':'abc','messages':msgs}
    def client(self,incoming=False):
        return Mock(get=Mock(side_effect=lambda resource,params: {'emailAddress':'owner@example.org','historyId':'10'} if resource=='profile' else {'threads':[{'id':'abc'}]} if resource=='threads' else self.thread(incoming)))
    def test_sent_and_inbox_reconstruction_and_encryption(self):
        sync=self.sync();client=self.client();sync.step(client)
        self.assertEqual(len(sync.review()),1)
        self.assertNotIn('labelIds',client.get.call_args_list[1].args[1])
        blobs=self.ledger.db.execute('SELECT encrypted FROM google_private_sync').fetchone()[0]
        self.assertNotIn(b'PRIVATE SUBJECT',blobs)
        self.assertNotIn('PRIVATE SUBJECT',str(self.ledger.records('personal')))
    def test_later_incoming_is_not_unanswered_claim(self):
        sync=self.sync();sync.step(self.client(True));self.assertEqual(sync.review(),[])
    def test_wrong_owner_and_audit_failure_do_not_commit_cursor(self):
        sync=self.sync()
        with self.assertRaises(PermissionError):sync.step(Mock(get=Mock(return_value={'emailAddress':'other'})))
        with patch.object(self.ledger,'_append',side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):sync.step(self.client())
        self.assertIsNone(sync.load()[0]['cursor'])
    def test_expired_history_requires_explicit_resync(self):
        sync=self.sync();sync.step(self.client());before=sync.load()
        client=Mock(get=Mock(side_effect=[{'emailAddress':'owner@example.org','historyId':'20'},GmailError(404)]))
        self.assertEqual(sync.step(client)['status'],'RESYNC_REQUIRED')
        self.assertEqual(sync.load(),before)
    def test_incremental_deleted_thread_and_cursor_commit(self):
        sync=self.sync();sync.step(self.client())
        client=Mock(get=Mock(side_effect=[{'emailAddress':'owner@example.org','historyId':'20'},
          {'history':[{'messagesDeleted':[{'message':{'threadId':'abc'}}]}],'historyId':'20'},GmailError(404)]))
        sync.step(client);self.assertEqual(sync.review(),[]);self.assertEqual(sync.load()[0]['cursor'],'20')
