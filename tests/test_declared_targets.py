import json,unittest
from unittest.mock import Mock
import test_missions,test_google_web
from apex.declared_targets import TARGETS,COMPARTMENTS,directory
from apex.console_server import ConsoleApp

MANDATED=['Santander UK','HSBC UK','Halifax','NatWest','Lloyds Bank','PayPal','American Express UK','Capital One UK','Argos Pay',
 'Tinder','Bumble','Badoo','Happn','Feeld','Hinge','OnlyFans','Pornhub','Facebook','Instagram','Threads','TikTok','LinkedIn',
 'X','YouTube','Reddit','Snapchat','WhatsApp','Telegram','Discord','NHS']

class DeclaredTargetTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    call=test_google_web.GoogleWebTests.call
    def test_all_mandated_present_and_none_live_without_receipt(self):
        names=' | '.join(t['target'] for t in TARGETS)
        for name in MANDATED:self.assertIn(name,names)
        rows=directory(self.ledger)
        self.assertFalse([r for r in rows if r['state'].startswith('LIVE')])
        for r in rows:
            if r['compartment'] in ('health','intimate','dating'):self.assertFalse(r['briefing_default'])
        self.assertTrue(all(r['compartment'] in COMPARTMENTS for r in rows))
    def test_live_only_from_retrieval_receipt(self):
        with self.ledger.transaction():
            self.ledger._append('finance-amex-1','decision','personal',{'slug':'amex','phase':'CONSENT_AUTHORIZED'})
            self.ledger._append('finance-paypal-1','decision','personal',{'slug':'paypal','phase':'STATEMENT_IMPORTED'})
        state={r['adapter']:r['state'] for r in directory(self.ledger)}
        self.assertEqual((state['finance:amex'],state['finance:paypal']),('IMPLEMENTED_NOT_AUTHORIZED','IMPORTED_STATEMENT'))
        with self.ledger.transaction():
            self.ledger._append('finance-amex-2','decision','personal',{'slug':'amex','phase':'AIS_RETRIEVAL','http_verified_accounts':1})
        self.assertEqual({r['adapter']:r for r in directory(self.ledger)}['finance:amex']['state'],'LIVE')
    def test_page_owner_only(self):
        app=ConsoleApp(self.root,Mock(valid=Mock(return_value=True)))
        r,body=self.call(app,'/connections')
        self.assertTrue(r['status'].startswith('200'));self.assertIn(b'Pornhub',body);self.assertIn(b'segregated',body)
        app.verifier.valid.return_value=False
        self.assertTrue(self.call(app,'/connections')[0]['status'].startswith('401'))

if __name__=='__main__':unittest.main()
