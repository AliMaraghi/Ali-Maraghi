import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
from cryptography.fernet import Fernet
from apex.banking import BankingClient,contract,consent_body,fetch
from apex.kernel.memory import Ledger

class BankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.ledger=Ledger(Path(self.tmp.name))
        self.permission={'owner':'owner@example.org','connection_id':'00000000-0000-0000-0000-000000000001','reviewed':True,'review_reference':'synthetic-review','contract_reference':'synthetic-contract','request_cost_pence':0,'scopes':['accounts','balance','transactions'],'consent_expires_at':'2099-01-01T00:00:00Z'}
        self.client=BankingClient(self.ledger,Fernet.generate_key(),self.permission,lambda:{'scope':'data','access_token':'test-token','expires_at':'2099-01-01T00:00:00Z'})
    def tearDown(self): self.ledger.close(); self.tmp.cleanup()
    def test_contract_and_forbidden_routes(self):
        self.assertEqual(contract('balance',account='abc')[1],'/v3/connected-accounts/abc/balance')
        self.assertEqual(contract('transactions_start',account='abc',start='2026-01-01',end='2026-01-31')[2]['page_size'],50)
        for op,acct in [('payments','abc'),('balance','../../payments')]:
            with self.assertRaises(ValueError):contract(op,account=acct)
        with self.assertRaises(ValueError):contract('transactions_start',account='abc',start='2026-01-01',end='2026-03-01')
    def test_consent_is_hosted_not_claimed(self):
        body=consent_body('Owner','owner@example.org','https://console.apexcorelab.uk/auth/banking/callback')
        self.assertEqual(body['user_consent']['type'],'authorization_flow_captured')
        self.assertNotIn('payments',body['scopes'])
    @patch('apex.banking.subprocess.run')
    def test_encrypted_atomic_receipt_and_replay(self,run):
        run.return_value=Mock(returncode=0,stdout=b'{"status":200,"data":{"private":"SECRET"}}')
        result=self.client.request('one','accounts')
        self.assertEqual(result['state'],'RECEIVED_UNVALIDATED')
        self.assertEqual(self.client.request('one','accounts'),result); self.assertEqual(run.call_count,1)
        blob=self.ledger.db.execute('SELECT encrypted FROM banking_private_receipts').fetchone()[0]
        self.assertNotIn(b'SECRET',blob); self.assertNotIn('SECRET',str(self.ledger.records('personal')))
        old=self.ledger._append
        def fail(key,*args):
            old(key,*args)
            if key.endswith('-result'):raise RuntimeError('audit failed')
        with patch.object(self.ledger,'_append',side_effect=fail):
            with self.assertRaises(RuntimeError): self.client.request('two','accounts')
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM banking_private_receipts').fetchone()[0],1)
        with self.assertRaisesRegex(RuntimeError,'AMBIGUOUS'):self.client.request('two','accounts')
    def test_expiry_and_cost_fail_closed(self):
        for update in ({'request_cost_pence':1},{'request_cost_pence':True},{'consent_expires_at':'2000-01-01T00:00:00Z'}):
            with self.assertRaises(PermissionError):BankingClient(self.ledger,Fernet.generate_key(),{**self.permission,**update},lambda:None)
    @patch('apex.banking.resolve_public',return_value=(2,'8.8.8.8'))
    @patch('apex.banking.Connection')
    def test_redirect_body_is_never_read(self,connection,resolver):
        response=connection.return_value.getresponse.return_value;response.status=302
        self.assertEqual(fetch('accounts',self.permission['connection_id'],'test-token'),{'status':302})
        response.read.assert_not_called()
