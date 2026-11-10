import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from apex.kernel.owp import plan_search, inspect_coverage
from apex.kernel.policy import Policy, KillState
from test_kernel import NOW, WORK


def request():
    return {'task_id': 'owp-example', 'expires_at': '2026-11-20T00:00:00Z',
            'axes': [{'geography': 'worldwide', 'industry': 'materials reuse',
                      'mechanism': 'repair', 'customer_problem': 'access to replacement parts'},
                     {'geography': 'Portugal', 'industry': 'coastal services',
                      'mechanism': 'shared equipment', 'customer_problem': 'seasonal capacity'}],
            'sources': [{'id': 'sample', 'family': 'custom registry',
                         'uri': 'https://example.org/catalogue',
                         'access_note': 'Synthetic candidate; rights not verified'}],
            'max_probes': 128, 'paid_budget_pence': 0}


class OWPTests(unittest.TestCase):
    def test_arbitrary_axes_stable_dedupe_and_no_network(self):
        r = request()
        r['axes'].append(copy.deepcopy(r['axes'][0]))
        with patch('socket.socket', side_effect=AssertionError('No network')):
            a = plan_search(r, Policy('opportunity'), NOW)
            b = plan_search(r, Policy('opportunity'), NOW)
        self.assertEqual(a, b)
        self.assertEqual(len(a['probes']), 2)
        self.assertFalse(a['demand_verified'])
        self.assertEqual(a['actions_executed'], [])
        self.assertEqual(a['sources'][0]['adapter_status'], 'BLOCKED_NO_RETRIEVAL_ADAPTER')

    def test_truncation_reports_missing_scope_and_validates_tail(self):
        r = request(); r['max_probes'] = 1
        a = plan_search(r, Policy('opportunity'), NOW)
        self.assertEqual(a['omitted_pairs'], 1)
        r['axes'][-1]['geography'] = ''
        with self.assertRaises(ValueError): plan_search(r, Policy('opportunity'), NOW)

    def test_strict_caps_reject_bool_float_spend_and_unbounded_iterable(self):
        for key, val in [('max_probes', True), ('max_probes', 1.5), ('max_probes', 129),
                         ('paid_budget_pence', 1), ('paid_budget_pence', False),
                         ('axes', iter(request()['axes'])), ('axes', request()['axes'] * 17)]:
            r = request(); r[key] = val
            with self.subTest(key=key, val=str(val)), self.assertRaises(ValueError):
                plan_search(r, Policy('opportunity'), NOW)

    def test_expired_stop_and_domain_denied(self):
        r = request(); r['expires_at'] = NOW.isoformat()
        with self.assertRaises(ValueError): plan_search(r, Policy('opportunity'), NOW)
        for policy in (Policy('studio'), Policy('opportunity', KillState.STOP_EXECUTION)):
            with self.assertRaises(PermissionError): plan_search(request(), policy, NOW)

    def test_hostile_source_or_self_authorization_rejected(self):
        for uri in ('https://127.0.0.1', 'https://user:pass@example.org', 'https://host.internal'):
            r = request(); r['sources'][0]['uri'] = uri
            with self.assertRaises(ValueError): plan_search(r, Policy('opportunity'), NOW)
        r = request(); r['sources'][0]['network_authorized'] = True
        with self.assertRaises(ValueError): plan_search(r, Policy('opportunity'), NOW)

    def test_structured_digest_prevents_delimiter_collision(self):
        r = request(); r['axes'] = [dict(r['axes'][0], geography='alpha | beta', industry='gamma'),
                                   dict(r['axes'][0], geography='alpha', industry='beta | gamma')]
        result = plan_search(r, Policy('opportunity'), NOW)
        self.assertEqual(len({p['id'] for p in result['probes']}), 2)

    def test_duplicate_and_empty_sources_rejected(self):
        for sources in ([], request()['sources'] * 2):
            r = request(); r['sources'] = sources
            with self.assertRaises(ValueError): plan_search(r, Policy('opportunity'), NOW)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=WORK)
        self.root = Path(self.tmp.name)
        raw = b'["a", "b"]'
        (self.root/'snapshot.json').write_bytes(raw)
        self.record = {'search_id': 's1', 'source_uri': 'https://example.org/catalogue',
                       'scope': 'Synthetic local snapshot only', 'artifact': 'snapshot.json',
                       'sha256': hashlib.sha256(raw).hexdigest(),
                       'queried_at': '2026-11-08T00:00:00Z', 'expires_at': '2026-11-20T00:00:00Z',
                       'observed_items': 2, 'inspected_ids': ['a'], 'selected_ids': [], 'synthetic': True}

    def tearDown(self): self.tmp.cleanup()

    def inspect(self): return inspect_coverage(self.record, self.root, NOW)

    def test_counts_membership_and_full_inspection_do_not_prove_market_gap(self):
        self.assertEqual(self.inspect()['uninspected_items'], 1)
        self.record['inspected_ids'].append('b')
        result = self.inspect()
        self.assertTrue(result['snapshot_fully_inspected_declared'])
        self.assertFalse(result['inspection_independently_verified'])
        self.assertFalse(result['unmet_demand_verified'])
        self.assertFalse(result['market_coverage_verified'])

    def test_missing_snapshot_items_and_fractional_counts_rejected(self):
        original = copy.deepcopy(self.record)
        for key, val in [('observed_items', 2.0), ('observed_items', True),
                         ('observed_items', 3), ('inspected_ids', ['c']),
                         ('selected_ids', ['b']), ('inspected_ids', ['a', 'a'])]:
            self.record = dict(original, **{key: val})
            with self.subTest(key=key, val=val), self.assertRaises(ValueError): self.inspect()

    def test_tamper_stale_future_and_unsafe_artifact_rejected(self):
        original = copy.deepcopy(self.record)
        for key, val in [('sha256', '0'*64), ('queried_at', '2027-01-01T00:00:00Z'),
                         ('expires_at', NOW.isoformat()), ('artifact', '../outside.json'),
                         ('source_uri', 123), ('source_uri', None), ('source_uri', 'x'*2049)]:
            self.record = dict(original, **{key: val})
            with self.subTest(key=key), self.assertRaises(ValueError): self.inspect()
        self.record = original
        (self.root/'snapshot.json').unlink()
        (self.root/'snapshot.json').symlink_to('missing.json')
        with self.assertRaises(OSError): self.inspect()

    def test_zero_observed_is_not_full_coverage(self):
        (self.root/'snapshot.json').write_bytes(b'[]')
        self.record.update(sha256=hashlib.sha256(b'[]').hexdigest(), observed_items=0, inspected_ids=[])
        self.assertFalse(self.inspect()['snapshot_fully_inspected_declared'])
        self.assertFalse(self.inspect()['unmet_demand_verified'])

    def test_cli_invalid_request_is_redacted_and_fails_closed(self):
        root = Path(__file__).resolve().parents[1]
        p = subprocess.run([sys.executable, '-B', '-m', 'apex.kernel.cli', 'owp-plan',
                            'examples/evidence_review_synthetic.json'], cwd=root,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)['status'], 'BLOCKED_INVALID_INPUT_OR_POLICY')
