import hashlib,io,json,time,unittest
from unittest.mock import Mock
from urllib.parse import urlencode
from http.cookies import SimpleCookie
import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import test_missions,test_google_web
from apex.finance import Finance,TARGETS,minor
from apex.finance_web import FinanceRoutes,is_finance_path
from apex.console_server import ConsoleApp

OWNER='owner@example.org';APP='12345678-1234-1234-1234-123456789abc';UID='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';SES='s'*43
KEY=rsa.generate_private_key(public_exponent=65537,key_size=2048)
PEM=KEY.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
NAMES=['Santander','HSBC UK Personal','HSBC UK Business','Lloyds Bank','Halifax','NatWest','American Express','Capital One','Monzo']

def fake(fail=None):
    calls=[]
    def t(op,token,**a):
        calls.append(op)
        if fail and op==fail:raise RuntimeError('Enable Banking request rejected: 401')
        return {'aspsps':{'aspsps':[{'name':n,'country':'GB'} for n in NAMES]},
            'auth':{'url':'https://auth.example.test/consent?x=1'},
            'session':{'session_id':'sess-1','accounts':[{'uid':UID,'name':'Card','currency':'GBP','cash_account_type':'CARD','credit_limit':{'currency':'GBP','amount':'5000.00'}}],'access':{'valid_until':'2027-02-08T00:00:00Z'}},
            'balances':{'balances':[{'balance_type':'ITAV','balance_amount':{'amount':'4200.00','currency':'GBP'}},{'balance_type':'CLBD','balance_amount':{'amount':'-800.00','currency':'GBP'}}]},
            'transactions':{'transactions':[{'transaction_amount':{'amount':'12.50','currency':'GBP'},'credit_debit_indicator':'DBIT','booking_date':time.strftime('%Y-%m-%d'),'remittance_information':['SECRET SHOP'],'status':'BOOK','entry_reference':'r1'}]},
            'delete_session':{'message':'OK'}}[op]
    return t,calls

class FinanceTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def fin(self,app=True):return Finance(self.ledger,Fernet.generate_key(),OWNER,APP if app else None,PEM if app else None)

    def test_nine_targets_and_coverage_from_live_list_only(self):
        self.assertEqual([t['slug'] for t in TARGETS],['santander','hsbc','halifax','natwest','lloyds','paypal','amex','capitalone','argospay'])
        t,_=fake()
        with self.assertRaises(PermissionError):self.fin(False).coverage(t)
        cov=self.fin().coverage(t)
        self.assertEqual(cov['hsbc'],['HSBC UK Business','HSBC UK Personal']);self.assertEqual(cov['paypal'],[]);self.assertEqual(cov['argospay'],[])

    def test_app_jwt_contract(self):
        tok=self.fin().token();h=jwt.get_unverified_header(tok)
        self.assertEqual((h['alg'],h['kid']),('RS256',APP))
        c=jwt.decode(tok,KEY.public_key(),algorithms=['RS256'],audience='api.enablebanking.com',issuer='enablebanking.com')
        self.assertLessEqual(c['exp']-c['iat'],86400)

    def test_consent_sync_live_and_encrypted(self):
        f=self.fin();t,calls=fake()
        with self.assertRaises(PermissionError):f.begin(OWNER,SES,'paypal',0,t)  # Not covered: no consent offered.
        self.assertTrue(f.begin(OWNER,SES,'amex',0,t).startswith('https://'))
        state=None
        # Recover state from the auth call arguments by re-running begin with a capturing transport.
        captured={}
        def cap(op,token,**a):
            if op=='auth':captured.update(a)
            return t(op,token,**a)
        f.begin(OWNER,SES,'amex',0,cap)
        with self.assertRaises(PermissionError):f.callback(OWNER,'x'*43,captured['state'],'CODE',t)
        self.assertEqual(f.dashboard()['live_count'],0)
        f.begin(OWNER,SES,'amex',0,cap);f.callback(OWNER,SES,captured['state'],'CODE',t)
        with self.assertRaises(PermissionError):f.callback(OWNER,SES,captured['state'],'CODE',t)
        self.assertEqual(f.dashboard()['entries'][6]['status'],'AUTHORIZED_NOT_YET_SYNCED')
        r=f.sync('amex',t);self.assertEqual((r['http_verified_accounts'],r['transaction_count']),(1,1))
        board=f.dashboard();amex=board['entries'][6]
        self.assertEqual((amex['status'],board['live_count']),('LIVE',1))
        acct=amex['accounts'][0]
        self.assertEqual((acct['balance']['type'],acct['balance']['minor'],acct['credit_limit_minor']),('CLBD',-80000,500000))
        self.assertEqual((board['totals_gbp']['liabilities_minor'],board['totals_gbp']['spending_30d_minor']),(80000,1250))
        dump='\n'.join(self.ledger.db.iterdump())
        for secret in ('SECRET SHOP','sess-1',UID):self.assertNotIn(secret,dump)

    def test_expired_consent_marks_reconnect(self):
        f=self.fin();captured={};t,_=fake()
        def cap(op,token,**a):
            if op=='auth':captured.update(a)
            return t(op,token,**a)
        f.begin(OWNER,SES,'natwest',0,cap);f.callback(OWNER,SES,captured['state'],'C',t)
        bad,_=fake('balances');r=f.sync('natwest',bad)
        self.assertEqual((r['http_verified_accounts'],r['errors']),(0,1))
        self.assertEqual(f.dashboard()['entries'][3]['status'],'RECONNECT_REQUIRED')

    def test_paypal_statement_import_is_not_live_and_deduplicated(self):
        path=self.root/'paypal.csv'
        path.write_text('"Date","Time","Time zone","Name","Type","Status","Currency","Gross","Fee","Net","Transaction ID","Balance"\n'
            '"01/11/2026","10:00:00","GMT","Shop A","Payment","Completed","GBP","-1,020.00","0.00","-1,020.00","TX1","80.00"\n'
            '"02/11/2026","10:00:00","GMT","Pending B","Payment","Pending","GBP","-5.00","0.00","-5.00","TX2",""\n')
        f=self.fin(False);r=f.import_statement('paypal',str(path),'paypal')
        self.assertEqual((r['rows'],r['live_connection']),(1,False))
        self.assertEqual(f.import_statement('paypal',str(path),'paypal')['phase'],'ALREADY_IMPORTED')
        e=f.dashboard()['entries'][5]
        self.assertEqual((e['status'],e['accounts'][0]['balance']['minor']),('IMPORTED_STATEMENT',8000))
        self.assertEqual(f.dashboard()['live_count'],0)

    def test_amount_parsing_rejects_garbage(self):
        self.assertEqual(minor('1,234.56'),123456)
        for bad in ['nan','abc','1e20']:
            with self.assertRaises(ValueError):minor(bad)

class FinanceRouteTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    call=test_google_web.GoogleWebTests.call
    def test_dashboard_lists_nine_and_unprovisioned_note(self):
        path=self.root/'fin.json';path.write_text(json.dumps({'owner':OWNER,'encryption_key':Fernet.generate_key().decode()}));path.chmod(0o600)
        app=ConsoleApp(self.root,Mock(valid=Mock(return_value=True)),None,None,FinanceRoutes(self.root,path,OWNER))
        r,body=self.call(app,'/connections/finance')
        self.assertTrue(r['status'].startswith('200'))
        for t in TARGETS:self.assertIn(t['name'].encode(),body)
        self.assertIn(b'not provisioned',body);self.assertIn(b'Live accounts: 0 of 9',body)
        app.verifier.valid.return_value=False
        self.assertTrue(self.call(app,'/connections/finance')[0]['status'].startswith('401'))
    def test_paths_and_unconfigured(self):
        self.assertTrue(is_finance_path('/auth/finance/start/amex/0'));self.assertFalse(is_finance_path('/auth/finance/start/../x'))
        bare=ConsoleApp(self.root,Mock(valid=Mock(return_value=True)))
        self.assertIn(b'Argos Pay',self.call(bare,'/connections/finance')[1])

if __name__=='__main__':unittest.main()
