import hashlib,json,time,unittest
from unittest.mock import Mock
from urllib.parse import urlencode,urlsplit,parse_qs
from http.cookies import SimpleCookie
from cryptography.fernet import Fernet
import test_missions,test_google_web
from apex.meta_connect import MetaConnection
from apex.meta_web import MetaRoutes
from apex.console_server import ConsoleApp

SESSION='s'*43

def graph(perms=('pages_show_list','pages_read_engagement','instagram_basic')):
    calls=[]
    def transport(op,version,**args):
        calls.append(op)
        return {'code':{'access_token':'SHORT'},'long':{'access_token':'LONGTOKEN','expires_in':5184000},
                'permissions':{'data':[{'permission':p,'status':'granted'} for p in perms]+[{'permission':'email','status':'declined'}]},
                'me':{'id':'12345'}}[op]
    return transport,calls

class MetaConnectTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def conn(self):return MetaConnection(self.ledger,Fernet.generate_key(),'owner@example.org','1234','abcdef0123','v21.0','meta-review')
    def state(self,c):return parse_qs(urlsplit(c.begin('owner@example.org',SESSION)).query)['state'][0]

    def test_full_flow_encrypts_token_and_rejects_replay(self):
        c=self.conn();url=c.begin('owner@example.org',SESSION)
        q=parse_qs(urlsplit(url).query)
        self.assertTrue(url.startswith('https://www.facebook.com/v21.0/dialog/oauth?'))
        self.assertEqual(q['redirect_uri'],['https://console.apexcorelab.uk/auth/meta/callback'])
        t,calls=graph()
        self.assertEqual(c.callback('owner@example.org',SESSION,q['state'][0],'CODE',t)['status'],'CONNECTED')
        self.assertEqual(calls,['code','long','permissions','me'])
        self.assertEqual(c.token(),'LONGTOKEN');b=c.binding();b.require()
        dump='\n'.join(str(r) for r in self.ledger.db.iterdump())
        self.assertNotIn('LONGTOKEN',dump);self.assertNotIn('12345',dump)
        with self.assertRaises(PermissionError):c.callback('owner@example.org',SESSION,q['state'][0],'CODE',t)
        c.disconnect();self.assertEqual(c.status()['status'],'AUTH_REQUIRED')
        with self.assertRaises(PermissionError):c.token()

    def test_missing_permission_wrong_session_and_owner_rejected(self):
        c=self.conn();t,_=graph(('pages_show_list',))
        with self.assertRaises(PermissionError):c.callback('owner@example.org',SESSION,self.state(c),'CODE',t)
        self.assertEqual(c.status()['status'],'AUTH_REQUIRED')
        t,calls=graph()
        with self.assertRaises(PermissionError):c.callback('owner@example.org','x'*43,self.state(c),'CODE',t)
        self.assertEqual(calls,[])  # No remote exchange on state/session mismatch.
        with self.assertRaises(PermissionError):c.begin('other@example.org',SESSION)

class MetaRouteTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    call=test_google_web.GoogleWebTests.call
    def app(self):
        path=self.root/'meta.json'
        path.write_text(json.dumps({'owner':'owner@example.org','app_id':'1234','app_secret':'abcdef0123','graph_version':'v21.0',
            'encryption_key':Fernet.generate_key().decode(),'privacy_review':'meta-review'}));path.chmod(0o600)
        return ConsoleApp(self.root,Mock(valid=Mock(return_value=True)),None,MetaRoutes(self.root,path,'owner@example.org'))
    def test_page_start_csp_and_csrf(self):
        app=self.app();r,body=self.call(app,'/connections/meta')
        self.assertTrue(r['status'].startswith('200'));self.assertIn(b'AUTH_REQUIRED',body)
        self.assertIn('https://www.facebook.com',r['headers']['Content-Security-Policy'])
        parsed=SimpleCookie();parsed.load(r['headers']['Set-Cookie']);sid=parsed['__Host-apex-owner'].value
        csrf=self.ledger.db.execute('SELECT csrf FROM owner_web_sessions WHERE id=?',(hashlib.sha256(sid.encode()).hexdigest(),)).fetchone()[0]
        cookie=r['headers']['Set-Cookie']
        self.assertTrue(self.call(app,'/auth/meta/start',cookie,'POST','csrf=bad')[0]['status'].startswith('403'))
        ok,_=self.call(app,'/auth/meta/start',cookie,'POST',urlencode({'csrf':csrf}))
        self.assertTrue(ok['headers']['Location'].startswith('https://www.facebook.com/v21.0/dialog/oauth'))
        self.assertTrue(self.call(app,'/connections/meta/sync',cookie,'POST',urlencode({'csrf':csrf}))[0]['status'].startswith('403'))
    def test_unauthenticated_denied_and_unconfigured_blocked(self):
        app=self.app();app.verifier.valid.return_value=False
        self.assertTrue(self.call(app,'/connections/meta')[0]['status'].startswith('401'))
        bare=ConsoleApp(self.root,Mock(valid=Mock(return_value=True)))
        self.assertIn(b'BLOCKED_EXTERNAL_AUTH',self.call(bare,'/connections/meta')[1])

if __name__=='__main__':unittest.main()
