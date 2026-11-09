import copy
import unittest
from test_kernel import NOW
from apex.kernel.operations import plan_due_jobs, health
from apex.kernel.policy import Policy, KillState
from apex.studio import edit_package
from unittest.mock import Mock

class OperationalTests(unittest.TestCase):
    def job(self, id='job1', **values):
        return dict({'id':id,'kind':'evidence_review','domain':'opportunity','due_at':'2026-11-09T11:00:00Z','seconds':30,'estimated_pence':0,'sensitivity':'public'},**values)

    def test_schedule_time_budget_and_stable_order(self):
        r=plan_due_jobs([self.job('b'),self.job('a')],Policy('opportunity'),NOW,30)
        self.assertEqual(r['selected'],['a'])
        self.assertEqual(r['deferred'][0]['reason'],'TIME_BUDGET')
        self.assertFalse(r['executed'])

    def test_denies_future_paid_private_and_unknown(self):
        for change in ({'due_at':'2027-01-01T00:00:00Z'},{'estimated_pence':1},{'sensitivity':'private'},{'kind':'shell'}):
            with self.subTest(change=change):
                self.assertFalse(plan_due_jobs([self.job(**change)],Policy('opportunity'),NOW)['selected'])

    def test_stop_and_duplicate(self):
        self.assertFalse(plan_due_jobs([self.job()],Policy('opportunity',KillState.STOP_EXECUTION),NOW)['selected'])
        with self.assertRaises(ValueError): plan_due_jobs([self.job(),self.job()],Policy('opportunity'),NOW)

    def test_health_no_mutation_and_redacted_failure(self):
        ledger=Mock(); ledger.verify.return_value=3
        self.assertEqual(health(ledger)['journal_events'],3)
        ledger.append.assert_not_called()
        ledger.verify.side_effect=ValueError('secret detail')
        self.assertNotIn('secret',str(health(ledger)))

    def manifest(self):
        return {'duration_seconds':75,'timeline':[{'shot_id':'a','start_seconds':0,'end_seconds':30,'narration':'A <quiet> beginning.'},{'shot_id':'b','start_seconds':30,'end_seconds':75,'narration':'A measured ending.'}]}

    def test_caption_export_is_reproducible_and_not_film(self):
        a=edit_package(self.manifest()); b=edit_package(self.manifest())
        self.assertEqual(a,b)
        self.assertIn('00:00:30,000 --> 00:01:15,000',a['subtitles_srt'])
        self.assertIn('&lt;quiet&gt;',a['subtitles_srt'])
        self.assertFalse(a['film_completed'])
        self.assertEqual(a['qc']['audio_loudness'],'NOT_TESTED')

    def test_timeline_gaps_and_caption_injection_fail(self):
        for field,value in [('start_seconds',31),('narration','injected\n\n2'),('end_seconds',True)]:
            m=self.manifest(); m['timeline'][1][field]=value
            with self.assertRaises(ValueError): edit_package(m)
