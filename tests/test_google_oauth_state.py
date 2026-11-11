import hashlib,base64
import unittest
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch
from cryptography.fernet import Fernet
import test_missions
from apex.google_oauth_state import OAuthState
from apex.kernel.policy import KillState

class GoogleStateTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown
    def broker(self,key=None,client='client-test'):
        return OAuthState(self.ledger,key or Fernet.generate_key(),client,'https://console.apexcorelab.uk/auth/google/callback','owner@example.org')
    def start(self,broker):return parse_qs(urlsplit(broker.begin('s'*32,['gmail'])).query)
    def test_pkce_session_binding_replay_and_no_plaintext(self):
        broker=self.broker();query=self.start(broker)
        with self.assertRaises(PermissionError):broker.consume(query['state'][0],'x'*32)
        material=broker.consume(query['state'][0],'s'*32)
        expected=base64.urlsafe_b64encode(hashlib.sha256(material['code_verifier'].encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(expected,query['code_challenge'][0])
        with self.assertRaises(PermissionError):broker.consume(query['state'][0],'s'*32)
        self.assertNotIn(material['code_verifier'],str(self.ledger.records('personal')))
    def test_consume_audit_failure_rolls_back_state_deletion(self):
        broker=self.broker();state=self.start(broker)['state'][0];original=self.ledger._append
        def fail(*args):original(*args);raise RuntimeError('audit fault')
        count=self.ledger.verify()
        with patch.object(self.ledger,'_append',side_effect=fail):
            with self.assertRaises(RuntimeError):broker.consume(state,'s'*32)
        self.assertEqual(count,self.ledger.verify())
        broker.consume(state,'s'*32)
    def test_expiry_and_stop(self):
        broker=self.broker()
        with patch('apex.google_oauth_state.time.time',return_value=1000):state=self.start(broker)['state'][0]
        with patch('apex.google_oauth_state.time.time',return_value=1600):
            with self.assertRaises(PermissionError):broker.consume(state,'s'*32)
        self.jobs.set_stop(KillState.STOP_EXECUTION)
        with self.assertRaises(PermissionError):self.start(broker)
    def test_changed_binding_cannot_redeem_and_state_survives_reopen(self):
        key=Fernet.generate_key();broker=self.broker(key);state=self.start(broker)['state'][0]
        with self.assertRaises(PermissionError):self.broker(key,'other-client').consume(state,'s'*32)
        from apex.kernel.memory import Ledger
        with Ledger(self.root) as reopened:
            OAuthState(reopened,key,'client-test','https://console.apexcorelab.uk/auth/google/callback','owner@example.org').consume(state,'s'*32)
    def test_invalid_redirect_and_nonreviewed_scopes(self):
        with self.assertRaises(ValueError):OAuthState(self.ledger,Fernet.generate_key(),'client','https://evil.example/callback','owner@example.org')
        with self.assertRaises(ValueError):self.broker().begin('s'*32,['drive'])
