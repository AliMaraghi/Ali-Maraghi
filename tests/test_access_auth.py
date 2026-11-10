"""Real RSA signatures, isolated keys; no Cloudflare live connection claimed."""
import json
import time
import unittest
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from apex.kernel.access_auth import AccessVerifier


class AccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key()))
        cls.jwk.update(kid='test-key',alg='RS256',use='sig')

    def setUp(self):
        now=int(time.time())
        self.config={'issuer':'https://example.cloudflareaccess.com','audience':'a'*64,
                     'owner_email':'owner@example.org','retrieved_at':now-1,'expires_at':now+600,
                     'source_url':'https://example.cloudflareaccess.com/cdn-cgi/access/certs',
                     'jwks':{'keys':[self.jwk.copy()]}}
        self.claims={'iss':self.config['issuer'],'aud':self.config['audience'],
                     'email':self.config['owner_email'],'sub':'owner-id','iat':now-1,'exp':now+60}
        self.verifier=AccessVerifier(self.config)

    def token(self, **updates):
        claims=dict(self.claims,**updates)
        return jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'})

    def test_valid_owner(self):
        self.assertTrue(self.verifier.valid(self.token()))

    def test_other_owner_issuer_audience_expiry_and_future_rejected(self):
        for update in [{'email':'other@example.org'},{'iss':'https://attacker.example'},
                       {'aud':'b'*64},{'exp':int(time.time())-1},{'iat':int(time.time())+20}]:
            with self.subTest(update=update):self.assertFalse(self.verifier.valid(self.token(**update)))

    def test_none_hmac_and_invalid_signature_rejected(self):
        self.assertFalse(self.verifier.valid(jwt.encode(self.claims,key='',algorithm='none')))
        self.assertFalse(self.verifier.valid(jwt.encode(self.claims,key='x'*32,algorithm='HS256')))
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.assertFalse(self.verifier.valid(jwt.encode(self.claims,other,algorithm='RS256',headers={'kid':'test-key'})))

    def test_token_supplied_url_unknown_key_and_missing_claim_rejected(self):
        for header in [{'kid':'other'},{'kid':'test-key','jku':'http://127.0.0.1'},
                       {'kid':'test-key','crit':['untrusted']}]:
            self.assertFalse(self.verifier.valid(jwt.encode(self.claims,self.key,algorithm='RS256',headers=header)))
        del self.claims['email']
        self.assertFalse(self.verifier.valid(self.token()))

    def test_snapshot_expiry_fails_closed(self):
        with patch('apex.kernel.access_auth.time.time',return_value=self.config['expires_at']):
            self.assertFalse(self.verifier.valid(self.token()))

    def test_malformed_and_noninteger_times_rejected(self):
        for token in [None,'bad','x'*16385,'é']:
            self.assertFalse(self.verifier.valid(token))
        self.assertFalse(self.verifier.valid(self.token(iat=True)))
        self.assertFalse(self.verifier.valid(self.token(exp=float('nan'))))

    def test_bad_configuration_rejected(self):
        for update in [{'issuer':'http://localhost'},{'audience':''},{'owner_email':'*'},
                       {'expires_at':True},{'source_url':'https://attacker.example'},
                       {'jwks':{'keys':[self.jwk,self.jwk]}}]:
            with self.subTest(update=update),self.assertRaises(ValueError):
                AccessVerifier(dict(self.config,**update))

    def test_http_requires_verified_assertion_not_basic_or_identity_header(self):
        import http.client
        import threading
        from http.server import HTTPServer
        from apex.kernel.owner_view import handler
        server=HTTPServer(('127.0.0.1',0),handler(None,'unused',None,0,self.verifier))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            for headers,expected in [({},401),({'Cf-Access-Authenticated-User-Email':'owner@example.org'},401),
                                     ({'Authorization':'Basic b3duZXI6dG9rZW4='},401),
                                     ({'Cf-Access-Jwt-Assertion':self.token()},404)]:
                conn=http.client.HTTPConnection(*server.server_address,timeout=3)
                conn.request('GET','/unknown',headers=headers)
                response=conn.getresponse();self.assertEqual(response.status,expected)
                response.read();conn.close()
        finally:server.shutdown();thread.join();server.server_close()
