import unittest
from datetime import datetime,timezone
from unittest.mock import Mock,patch
import test_banking
from apex.banking_analysis import normalize,receipt_projection

class BankingAnalysisTests(unittest.TestCase):
    setUp=test_banking.BankingTests.setUp
    tearDown=test_banking.BankingTests.tearDown
    def test_minor_units_reject_unsafe_values(self):
        self.assertEqual(normalize('balance',{'currency':'GBP','current_balance_in_minor':-100})['data']['current_balance_in_minor'],-100)
        for invalid in (True,1.5,float('nan'),float('inf'),2**64,'100'):
            with self.assertRaises(ValueError):normalize('balance',{'currency':'GBP','current_balance_in_minor':invalid})
    def test_accounts_minimize_and_never_claim_full_coverage(self):
        result=normalize('accounts',{'items':[{'id':'a','type':'account','currency':'GBP','account_holder_names':['PRIVATE'],'account_identifiers':[{'account_number':'PRIVATE'}]}],'pagination':{}})
        self.assertNotIn('PRIVATE',str(result))
        self.assertEqual(result['coverage'],'BOUNDED_PAGE_NOT_COMPLETE_INVENTORY')
        self.assertEqual(result['data']['count'],1)
    def test_unverified_transaction_shape_is_not_guessed(self):
        self.assertEqual(normalize('transactions_poll',{'status':'completed','result':{}})['status'],'BLOCKED_SCHEMA')
    @patch('apex.banking.subprocess.run')
    def test_projection_uses_real_encrypted_receipt_contract(self,run):
        run.return_value=Mock(returncode=0,stdout=b'{"status":200,"data":{"currency":"GBP","current_balance_in_minor":125050,"available_balance_in_minor":172550,"overdraft_in_minor":50000}}')
        self.client.request('balance-example','balance',account='abc')
        result=receipt_projection(self.client,'balance-example')
        self.assertEqual(result['data']['current_balance_in_minor'],125050)
        self.assertEqual(result['verification'],'STRUCTURE_ONLY_NOT_INDEPENDENT_BANK_VERIFICATION')
        result=receipt_projection(self.client,'balance-example',datetime(2098,1,1,tzinfo=timezone.utc))
        self.assertEqual(result['source']['freshness'],'STALE')
        self.assertEqual(receipt_projection(self.client,'missing')['status'],'NO_RECEIPT')
