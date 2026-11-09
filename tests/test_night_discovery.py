"""Artificial cases only; no verified public/market evidence is implied."""
from dataclasses import replace
from pathlib import Path
from decimal import Decimal
import tempfile
import unittest
from test_kernel import document, NOW, WORK
from apex.kernel.schema import Case
from apex.kernel.discovery import propose
from apex.kernel.opportunities import rank_opportunities
from apex.kernel.lab import compare, Trial
from apex.kernel.memory import Ledger
from apex.domains import Interval, OpportunityScenario

class NightDiscoveryTests(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=WORK)
        self.root = Path(self.tmp.name)
        self.doc = document(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def public_fixture(self):
        # Deliberately labelled public for integrity gate tests, not authentic evidence.
        self.doc['evidence'][0].update(synthetic=False, sensitivity='public')
        return Case.parse(self.doc)

    def scenario(self, cost=0):
        return OpportunityScenario('case-1','Hypothetical task',Interval('.2','.5'),
            Interval(100,200),Interval(cost,cost),Interval(1,2),Interval(1,2),
            ('Synthetic assumed inputs',),'Measure a public process',10)

    def test_synthetic_observations_do_not_generate_evidence_backed_claims(self):
        result = propose(Case.parse(self.doc),self.root,NOW)
        self.assertEqual(result['hypotheses'],[])
        self.assertFalse(result['empirical_superiority_proven'])

    def test_proposals_retain_source_and_different_falsifiers(self):
        result = propose(self.public_fixture(),self.root,NOW)
        self.assertEqual(len(result['hypotheses']),3)
        self.assertEqual(len({x['falsifier'] for x in result['hypotheses']}),3)
        self.assertTrue(all(x['evidence_refs']==['e1'] for x in result['hypotheses']))
        self.assertFalse(result['empirical_superiority_proven'])

    def test_corruption_blocks_proposals(self):
        case = self.public_fixture()
        (self.root/'source.txt').write_text('tampered')
        self.assertEqual(propose(case,self.root,NOW)['hypotheses'],[])

    def test_refutation_retained_not_silently_omitted(self):
        self.public_fixture()
        self.doc['evidence'].append(dict(self.doc['evidence'][0],id='e2',stance='refutes'))
        self.doc['claims'][0]['evidence_ids'].append('e2')
        r=propose(Case.parse(self.doc),self.root,NOW)
        self.assertTrue(all(x['contrary_refs']==['e2'] for x in r['hypotheses']))

    def test_no_support_abstains(self):
        self.public_fixture()
        self.doc['evidence'][0]['stance']='refutes'
        self.assertFalse(propose(Case.parse(self.doc),self.root,NOW)['hypotheses'])

    def test_ranking_enforces_evidence_and_zero_funding(self):
        r=rank_opportunities([(Case.parse(self.doc),self.scenario(1))],self.root,NOW)
        self.assertEqual(r['ranking'][0]['review_status'],'BLOCKED')
        self.assertIn('FUNDING_NOT_AUTHORIZED',r['ranking'][0]['blockers'])
        self.assertFalse(r['verified_demand'])

    def test_rank_is_order_independent_and_does_not_call_validated_demand(self):
        case=self.public_fixture()
        other=replace(case,id='case-2')
        pair=(case,self.scenario())
        second=(other,replace(self.scenario(),opportunity_id='case-2',revenue_if_success_gbp=Interval(10,20)))
        a=rank_opportunities([pair,second],self.root,NOW)
        b=rank_opportunities([second,pair],self.root,NOW)
        self.assertEqual(a,b)
        self.assertEqual(a['ranking'][0]['id'],'case-1')
        self.assertFalse(a['verified_demand'])

    def test_mismatched_scenario_rejected(self):
        with self.assertRaises(ValueError):
            rank_opportunities([(replace(self.public_fixture(),id='other'),self.scenario())],self.root,NOW)

    def test_receipt_requires_case_observations_and_detects_tampering(self):
        trials=tuple(Trial(str(i),{'i':i},i%2==0) for i in range(4))
        receipt=compare('v1',lambda d:d['i']%2==0,'baseline',lambda d:True,trials)
        with self.assertRaises(ValueError): replace(receipt,observations=()).validate()
        rows=list(receipt.observations)
        rows[0]=dict(rows[0],candidate=False)
        with self.assertRaises(ValueError): replace(receipt,observations=tuple(rows)).validate()
        with Ledger(self.root) as ledger: ledger.consider('experiment-1','opportunity',receipt)
        with Ledger(self.root) as ledger:
            saved=ledger.records('opportunity')[0]['payload']['receipt']
            self.assertEqual(len(saved['observations']),4)
            self.assertEqual(saved['dataset_sha256'],receipt.dataset_sha256)
