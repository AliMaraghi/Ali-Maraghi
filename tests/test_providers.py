import base64
import hashlib
import json
import unittest
from unittest.mock import patch
import test_missions
from apex.providers import probe,request,directory,normalize
from apex.kernel.policy import KillState
from apex.sources.public_http import validate


class ProvidersTests(unittest.TestCase):
    setUp=test_missions.MissionTests.setUp
    tearDown=test_missions.MissionTests.tearDown

    def response(self):
        raw=json.dumps({'status':'ok','message-type':'work-list','message':{'items':[
            {'DOI':'10.1000/test','title':['Fixture only'],'publisher':'Example','type':'journal-article','URL':'https://doi.org/10.1000/test'}]}}).encode()
        return {'body_b64':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),
                'retrieved_at':'2026-11-10T00:00:00+00:00','http_status':200,'hops':[]}

    def test_receipt_replay_and_conflicting_identity(self):
        with patch('apex.providers.retrieve',return_value=self.response()) as fetch:
            self.assertEqual(probe(self.ledger,'crossref','query','test')['state'],'LIVE_VERIFIED')
            self.assertTrue(probe(self.ledger,'crossref','query','test')['replayed'])
            self.assertEqual(fetch.call_count,1)
            with self.assertRaises(ValueError):probe(self.ledger,'crossref','changed','test')
        self.assertIsNotNone(directory(self.ledger)[0]['receipt_seq'])
        self.ledger.verify()

    def test_stop_prevents_network(self):
        self.jobs.set_stop(KillState.STOP_EXECUTION)
        with patch('apex.providers.retrieve') as fetch:
            with self.assertRaises(PermissionError):probe(self.ledger,'crossref','query','test')
            fetch.assert_not_called()

    def test_crashed_attempt_not_automatically_refetched(self):
        with patch('apex.providers.retrieve',side_effect=SystemExit):
            with self.assertRaises(SystemExit):probe(self.ledger,'crossref','query','test')
        with patch('apex.providers.retrieve') as fetch:
            self.assertEqual(probe(self.ledger,'crossref','query','test')['state'],'BLOCKED_AMBIGUOUS_PRIOR_ATTEMPT')
            fetch.assert_not_called()

    def test_invalid_digest_and_http_failure_not_live(self):
        bad=self.response();bad['sha256']='wrong'
        for i,response in enumerate([bad,{'http_status':429,'error':'HTTP_429'}]):
            with patch('apex.providers.retrieve',return_value=response):
                self.assertEqual(probe(self.ledger,'crossref','query','test'+str(i))['state'],'UNAVAILABLE')

    def test_no_arbitrary_provider_or_destination(self):
        with self.assertRaises(ValueError):request('unknown','query')
        with self.assertRaises(ValueError):request('crossref','x'*201)
        validate(request('crossref','query'))
        for url in ['https://api.crossref.org/admin','https://127.0.0.1/works']:
            with self.assertRaises(Exception):validate(url)
