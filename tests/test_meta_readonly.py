import time
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import test_missions
from apex.meta_readonly import MetaBinding,MetaClient,MetaPageSync,SCOPES,normalize,request_path,fetch

class MetaTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def binding(self):
        return MetaBinding('owner@example.org','123','v26.0','test-consent',SCOPES,int(time.time())+300,'test-review')
    def test_cursor_reconstruction_and_secret_minimization(self):
        pages,cursor=normalize({'data':[{'id':'1','name':'private','access_token':'SECRET','instagram_business_account':{'id':'2'}}],
            'paging':{'next':'https://evil/?access_token=SECRET','cursors':{'after':'abc'}}})
        self.assertNotIn('SECRET',str(pages));self.assertEqual(cursor,'abc')
        self.assertIn('/me/accounts?',request_path('v26.0',cursor))
        for bad in ['../me','https://evil','v26.0/../../']:
            with self.assertRaises(ValueError):request_path(bad)
    def test_missing_scope_and_expiry(self):
        from dataclasses import replace
        for binding in [replace(self.binding(),granted_scopes=frozenset()),replace(self.binding(),expires_at=0)]:
            with self.assertRaises(PermissionError):binding.require()
    def test_encryption_atomic_audit_cursor_and_completion(self):
        binding=self.binding();sync=MetaPageSync(self.ledger,Fernet.generate_key(),binding)
        client=MetaClient(self.ledger,binding,lambda:'unused')
        with patch.object(client,'pages',return_value=([{'id':'1','name':'PRIVATE'}],'cursor')):
            original=self.ledger._append
            def fail(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('injected')
            with patch.object(self.ledger,'_append',side_effect=fail):
                with self.assertRaises(RuntimeError):sync.step(client)
            self.assertEqual(sync.load()[1],0)
            sync.step(client)
        self.assertNotIn('PRIVATE',str(self.ledger.records('personal')))
        blob=self.ledger.db.execute('SELECT encrypted FROM meta_private_pages').fetchone()[0]
        self.assertNotIn(b'PRIVATE',blob)
        with patch.object(client,'pages',return_value=([],None)):
            sync.step(client)
        with patch.object(client,'pages') as get:
            self.assertEqual(sync.step(client)['state'],'HISTORICAL_DISCOVERY_COMPLETE');get.assert_not_called()
    @patch('apex.meta_readonly.resolve_public',return_value=(2,'8.8.8.8'))
    @patch('apex.meta_readonly.Connection')
    def test_redirect_rejected_without_reading_body(self,connection,resolver):
        response=connection.return_value.getresponse.return_value;response.status=302
        self.assertEqual(fetch('v26.0',None,'test-token'),{'http_status':302})
        response.read.assert_not_called();connection.return_value.close.assert_called_once()
