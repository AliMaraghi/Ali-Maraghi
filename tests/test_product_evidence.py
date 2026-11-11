import unittest
import test_missions
from apex.kernel.product_evidence import product_snapshot

class ProductEvidenceTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def test_missing_source_is_not_invented_and_personal_payload_is_not_projected(self):
        self.ledger.append('private-test','decision','personal',{'content':'PRIVATE_SENTINEL'})
        result=product_snapshot(self.ledger,self.root)
        self.assertEqual(len(result['roles']),18)
        self.assertEqual(result['manifesto']['status'],'MISSING')
        self.assertNotIn('PRIVATE_SENTINEL',str(result))
        self.assertIsNone(result['provider_inventory']['recovered'])
    def test_no_receipts_means_no_live_providers(self):
        result=product_snapshot(self.ledger,self.root)
        metric=next(m for m in result['metrics'] if m['id']=='historical_providers')
        self.assertEqual(metric['value'],0)
        self.assertTrue(all(not r['fully_accepted'] for r in result['roles']))
