import unittest
from unittest.mock import Mock,patch
from cryptography.fernet import Fernet
import test_missions
from apex.gmail_sync import GmailSync,GmailError
from apex.google_policy import ImportPolicy

class GmailTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def sync(self):return GmailSync(self.ledger,Fernet.generate_key(),'owner@example.org',ImportPolicy('owner@example.org',frozenset({'gmail'}),'synthetic-review',30,True))
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

    def test_failure_after_audit_insert_rolls_back_ciphertext_cursor_and_audit(self):
        from apex.kernel.memory import Ledger
        sync=self.sync();sync.step(self.client())
        before=self.ledger.db.execute('SELECT * FROM google_private_sync').fetchall()
        events=self.ledger.db.execute('SELECT * FROM events ORDER BY seq').fetchall()
        original=self.ledger._append
        def append_then_fail(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('Injected failure after audit insertion')
        client=Mock(get=Mock(side_effect=[{'emailAddress':'owner@example.org','historyId':'20'},
            {'history':[{'messages':[{'threadId':'abc'}]}],'historyId':'20'},self.thread(True)]))
        with patch.object(self.ledger,'_append',side_effect=append_then_fail):
            with self.assertRaises(RuntimeError):sync.step(client)
        self.assertEqual(before,self.ledger.db.execute('SELECT * FROM google_private_sync').fetchall())
        self.assertEqual(events,self.ledger.db.execute('SELECT * FROM events ORDER BY seq').fetchall())
        with Ledger.read_only(self.root) as reopened:
            self.assertEqual(before,reopened.db.execute('SELECT * FROM google_private_sync').fetchall())
            self.assertEqual(events,reopened.db.execute('SELECT * FROM events ORDER BY seq').fetchall())
            reopened.verify()
        self.assertEqual(sync.load()[0]['cursor'],'10')
        self.assertEqual(len(sync.review()),1)

    def test_nested_outer_rollback_keeps_all_three_unchanged(self):
        sync=self.sync();sync.step(self.client())
        before=self.ledger.db.execute('SELECT * FROM google_private_sync').fetchall()
        count=self.ledger.verify()
        client=Mock(get=Mock(side_effect=[{'emailAddress':'owner@example.org','historyId':'20'},
            {'history':[],'historyId':'20'}]))
        with self.assertRaises(RuntimeError):
            with self.ledger.transaction():
                sync.step(client)
                raise RuntimeError('Outer transaction aborted')
        self.assertEqual(before,self.ledger.db.execute('SELECT * FROM google_private_sync').fetchall())
        self.assertEqual(count,self.ledger.verify())

    def test_unrequested_headers_and_extra_fields_not_retained(self):
        sync=self.sync();thread=self.thread()
        thread['messages'][0]['payload']['headers']=[
            {'name':'Subject','value':'allowed','extra':'NOT_ALLOWED'},
            {'name':'Bcc','value':'PRIVATE_UNREQUESTED'},
            {'name':'X-Private','value':'PRIVATE_UNREQUESTED'}]
        thread['messages'][0]['payload']['body']={'data':'BODY_NOT_ALLOWED'}
        client=Mock(get=Mock(side_effect=[{'emailAddress':'owner@example.org','historyId':'10'},
            {'threads':[{'id':'abc'}]},thread]))
        sync.step(client);state=sync.load()[0]
        self.assertEqual(state['threads']['abc'][0]['headers'],[{'name':'Subject','value':'allowed'}])
        self.assertNotIn('NOT_ALLOWED',str(state));self.assertNotIn('PRIVATE_UNREQUESTED',str(state))

    def test_import_policy_missing_or_wrong_denies_before_client(self):
        for policy in [None,ImportPolicy('other@example.org',frozenset({'gmail'}),'test',30,True),
                       ImportPolicy('owner@example.org',frozenset({'gmail'}),'test',30,'true')]:
            sync=GmailSync(self.ledger,Fernet.generate_key(),'owner@example.org',policy)
            client=Mock()
            with self.assertRaises(PermissionError):sync.step(client)
            client.get.assert_not_called()

class GmailCoverageTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def make(self):return GmailSync(self.ledger,Fernet.generate_key(),'owner@example.org',ImportPolicy('owner@example.org',frozenset({'gmail'}),'synthetic-review',30,True))
    def feed(self,pages):
        """pages: list of thread-id lists for the initial listing; history returns one new thread 'new1'."""
        calls={'n':0}
        def get(resource,params):
            if resource=='profile':return {'emailAddress':'owner@example.org','historyId':'10'}
            if resource=='threads':
                i=calls['n'];calls['n']+=1
                return {'threads':[{'id':t} for t in pages[i]],'nextPageToken':'p%d'%(i+1) if i+1<len(pages) else None}
            if resource=='history':return {'history':[{'messagesAdded':[{'message':{'threadId':'new1'}}]}],'historyId':'30'}
            tid=resource.split('/')[1]
            return {'id':tid,'messages':[{'id':'m'+tid,'threadId':tid,'internalDate':'9999' if tid=='new1' else str(100+int(tid[1:])),'labelIds':['INBOX'] if tid!='new1' else ['SENT']}]}
        return Mock(get=Mock(side_effect=get))
    def test_initial_coverage_is_bounded_reported_and_then_incremental_with_counted_eviction(self):
        import apex.gmail_sync as g
        with patch.object(g,'THREAD_CAP',40):
            sync=self.make();client=self.feed([['t%d'%i for i in range(p*20,p*20+20)] for p in range(5)])
            r1=sync.step(client);r2=sync.step(client)
            self.assertEqual((r2['thread_count'],r2['more_pages'],r2['coverage']['stopped']),(40,True,'IN_PROGRESS'))
            r3=sync.step(client)                                   # no room for another page: stop honestly, do not fail
            self.assertEqual(r3['status'],'PAGE_SYNCHRONIZED')
            self.assertEqual(r3['coverage'],{'initial_complete':False,'stopped':'CAPACITY','cap':40,'order':'newest first'})
            self.assertEqual((r3['phase'],r3['thread_count'],r3['threads_with_inbox']),('INCREMENTAL',40,40))
            r4=sync.step(client)                                   # incremental: one new thread arrives, the oldest is evicted and counted
            self.assertEqual((r4['thread_count'],r4['evicted_oldest'],r4['threads_with_sent']),(40,1,1))
            self.assertNotEqual(r3['cursor_digest'],r4['cursor_digest'])
            self.assertEqual(r4['coverage']['initial_complete'],False)
            self.assertTrue(r4['trace_id'].startswith('google-sync-'))
    def test_small_mailbox_reports_complete_coverage(self):
        sync=self.make();r=sync.step(self.feed([['t1','t2']]))
        self.assertEqual(r['coverage'],{'initial_complete':True,'cap':2000})
