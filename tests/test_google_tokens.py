import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import test_missions
from apex.google_tokens import TokenBroker
from apex.google_policy import ImportPolicy
from apex.google_oauth_state import SCOPES
from apex.kernel.policy import KillState

class TokenTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def broker(self):
        return TokenBroker(self.ledger,Fernet.generate_key(),'owner@example.org','client',
            ImportPolicy('owner@example.org',frozenset({'gmail'}),'review-1',30,True))
    def response(self):
        return {'access_token':'access-secret','refresh_token':'refresh-secret','token_type':'Bearer','expires_in':3600,'scope':SCOPES['gmail']}
    def test_encryption_expiry_refresh_disconnect(self):
        broker=self.broker()
        with patch('apex.google_tokens.time.time',return_value=1000):broker.install(self.response(),'owner@example.org')
        self.assertNotIn('access-secret',str(self.ledger.records('personal')))
        with patch('apex.google_tokens.time.time',return_value=2000):self.assertEqual(broker.access_token(),'access-secret')
        with patch('apex.google_tokens.time.time',return_value=5000):
            with self.assertRaises(PermissionError):broker.access_token()
            refreshed=self.response();refreshed.pop('refresh_token');refreshed['access_token']='new-secret'
            self.assertEqual(broker.access_token(lambda token:refreshed),'new-secret')
        broker.disconnect()
        with self.assertRaises(PermissionError):broker.access_token()
    def test_audit_failure_rolls_back_credentials(self):
        broker=self.broker();original=self.ledger._append
        def fail(*args):original(*args);raise RuntimeError('fault')
        with patch.object(self.ledger,'_append',side_effect=fail):
            with self.assertRaises(RuntimeError):broker.install(self.response(),'owner@example.org')
        self.assertEqual(broker.status(),{'status':'AUTH_REQUIRED'})
    def test_owner_scope_costless_stop(self):
        broker=self.broker()
        with self.assertRaises(PermissionError):broker.install(self.response(),'other@example.org')
        for expiry in (True,float('nan'),-1):
            response=self.response();response['expires_in']=expiry
            with self.assertRaises(ValueError):broker.install(response,'owner@example.org')
        self.jobs.set_stop(KillState.STOP_EXECUTION)
        with self.assertRaises(PermissionError):broker.install(self.response(),'owner@example.org')

class TokenTransportTests(unittest.TestCase):
    def test_grant_contract(self):
        from apex.google_token_http import validate
        validate({'client_id':'id','client_secret':'secret','grant_type':'refresh_token','refresh_token':'token'})
        with self.assertRaises(ValueError):validate({'grant_type':'password'})
        with self.assertRaises(ValueError):validate({'client_id':'id','client_secret':'secret','grant_type':'refresh_token','refresh_token':'token','url':'https://evil.test'})
    def test_errors_do_not_disclose_token(self):
        from apex.google_token_http import exchange
        with patch('apex.google_token_http.subprocess.run',side_effect=RuntimeError('secret-value')):
            with self.assertRaises(PermissionError) as error:exchange({'client_id':'id','client_secret':'secret','grant_type':'refresh_token','refresh_token':'token'})
        self.assertNotIn('secret-value',str(error.exception))

class ConnectionTests(unittest.TestCase):
    setUp=TokenTests.setUp
    tearDown=TokenTests.tearDown
    broker=TokenTests.broker
    response=TokenTests.response
    def test_controller_owner_binding_and_callback_identity(self):
        from apex.google_connect import GoogleConnection
        from apex.google_oauth_state import OAuthState
        from urllib.parse import urlsplit,parse_qs
        broker=self.broker()
        state=OAuthState(self.ledger,Fernet.generate_key(),'client','https://console.apexcorelab.uk/auth/google/callback','owner@example.org')
        connection=GoogleConnection(state,broker,'client-secret')
        with self.assertRaises(PermissionError):connection.begin('other@example.org','s'*32)
        query=parse_qs(urlsplit(connection.begin('owner@example.org','s'*32)).query)
        with patch('apex.google_connect.exchange',return_value=self.response()), patch('apex.google_connect.GmailClient') as client:
            client.return_value.get.return_value={'emailAddress':'wrong@example.org'}
            with self.assertRaises(PermissionError):connection.callback('owner@example.org','s'*32,query['state'][0],'code')
        self.assertEqual(broker.status(),{'status':'AUTH_REQUIRED'})
