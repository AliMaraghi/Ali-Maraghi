import io,json,os,unittest
from unittest.mock import Mock,patch
from urllib.parse import urlencode
from http.cookies import SimpleCookie
from cryptography.fernet import Fernet
import test_missions
from apex.google_web import GoogleRoutes
from apex.console_server import ConsoleApp

class GoogleWebTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def app(self):
        path=self.root/'google.json'
        path.write_text(json.dumps({'owner':'owner@example.org','client_id':'client','client_secret':'secret',
            'redirect_uri':'https://console.apexcorelab.uk/auth/google/callback','encryption_key':Fernet.generate_key().decode(),
            'review_reference':'review','retention_days':30,'mixed_content_reviewed':True}))
        path.chmod(0o600)
        return ConsoleApp(self.root,Mock(valid=Mock(return_value=True)),GoogleRoutes(self.root,path,'owner@example.org'))
    def call(self,app,path='/connections/google',cookie='',method='GET',data='',origin='https://console.apexcorelab.uk',token='verified'):
        result={}
        env={'HTTP_HOST':'console.apexcorelab.uk','HTTP_CF_ACCESS_JWT_ASSERTION':token,'PATH_INFO':path,
             'HTTP_COOKIE':cookie,'REQUEST_METHOD':method,'HTTP_ORIGIN':origin,'CONTENT_TYPE':'application/x-www-form-urlencoded',
             'CONTENT_LENGTH':str(len(data)),'wsgi.input':io.BytesIO(data.encode())}
        body=b''.join(app(env,lambda status,headers:result.update(status=status,headers=dict(headers))))
        return result,body
    def test_owner_gate_before_session(self):
        app=self.app();app.verifier.valid.return_value=False
        self.assertTrue(self.call(app)[0]['status'].startswith('401'))
        self.assertIsNone(self.ledger.db.execute("SELECT name FROM sqlite_master WHERE name='owner_web_sessions'").fetchone())
    def test_cookie_csrf_and_begin(self):
        app=self.app();response,body=self.call(app)
        self.assertTrue(response['status'].startswith('200'))
        cookie=response['headers']['Set-Cookie']
        for flag in ['Secure','HttpOnly','SameSite=Lax','Path=/']:self.assertIn(flag,cookie)
        parsed=SimpleCookie();parsed.load(cookie);sid=parsed['__Host-apex-owner'].value
        import hashlib
        csrf=self.ledger.db.execute('SELECT csrf FROM owner_web_sessions WHERE id=?',(hashlib.sha256(sid.encode()).hexdigest(),)).fetchone()[0]
        bad,_=self.call(app,'/auth/google/start',cookie,'POST','csrf=wrong')
        self.assertTrue(bad['status'].startswith('403'))
        good,_=self.call(app,'/auth/google/start',cookie,'POST',urlencode({'csrf':csrf}))
        self.assertTrue(good['status'].startswith('303'))
        self.assertTrue(good['headers']['Location'].startswith('https://accounts.google.com/'))
        changed,_=self.call(app,'/auth/google/start',cookie,'POST',urlencode({'csrf':csrf}),token='different')
        self.assertTrue(changed['status'].startswith('403'))
    def test_private_config_required(self):
        app=self.app();app.google_routes.path.chmod(0o644)
        self.assertTrue(self.call(app)[0]['status'].startswith('403'))
