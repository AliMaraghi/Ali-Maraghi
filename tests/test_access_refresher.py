import io,json,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy/production'))
import refresh_access_jwks as r
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from apex.kernel.access_auth import AccessVerifier

ISS='https://apexteam.cloudflareaccess.com';AUD='a'*64;OWNER='owner@example.org'

class Resp(io.BytesIO):
    status=200
    def __enter__(self):return self
    def __exit__(self,*a):pass

class Opener:
    def __init__(self,doc):self.doc=doc;self.urls=[]
    def open(self,req,timeout):self.urls.append(req.full_url);return Resp(json.dumps(self.doc).encode())

class RefresherTests(unittest.TestCase):
    def setUp(self):
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk=dict(jwk,kid='k1',alg='RS256',use='sig')
    def test_snapshot_accepted_by_real_verifier_and_token_checked(self):
        opener=Opener({'keys':[self.jwk]});now=int(time.time())
        cfg=r.build(ISS,AUD,OWNER,now,opener)
        self.assertEqual(opener.urls,[ISS+'/cdn-cgi/access/certs'])
        verifier=AccessVerifier(json.loads(json.dumps(cfg)))
        claims={'iss':ISS,'aud':AUD,'sub':'u','email':OWNER,'iat':now,'exp':now+60}
        self.assertTrue(verifier.valid(jwt.encode(claims,self.key,'RS256',headers={'kid':'k1'})))
        self.assertFalse(verifier.valid(jwt.encode(dict(claims,email='x@example.org'),self.key,'RS256',headers={'kid':'k1'})))
    def test_rejects_private_or_malformed_keys_and_identity(self):
        for doc in [{'keys':[dict(self.jwk,d='secret')]},{'keys':[dict(self.jwk,alg='HS256')]},{'keys':[]},{'keys':[self.jwk]*5}]:
            with self.assertRaises(ValueError):r.build(ISS,AUD,OWNER,1,Opener(doc))
        for iss,aud,owner in [('https://evil.example.com',AUD,OWNER),(ISS,'short',OWNER),(ISS,AUD,'a@b.c,d@e.f')]:
            with self.assertRaises(ValueError):r.build(iss,aud,owner,1,Opener({'keys':[self.jwk]}))
    def test_non_root_directory_refused_and_root_required(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(PermissionError):r.write_atomic(d+'/c.json',{})
        with self.assertRaises(PermissionError):r.main(['--init','--team','apexteam','--aud',AUD,'--owner',OWNER])

if __name__=='__main__':unittest.main()
