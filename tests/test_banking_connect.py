import unittest
from urllib.parse import urlsplit, parse_qs
from cryptography.fernet import Fernet
import test_missions
from apex.banking_connect import BankingConnection, require_read_only

SESSION = 's' * 43
CONFIG = {'host': 'auth.example-aisp.test', 'authorize_path': '/connect/authorize',
          'token_path': '/connect/token', 'accounts_path': '/data/v1/accounts',
          'client_id': 'client-1', 'client_secret': 'secret-1',
          'redirect_uri': 'https://console.apexcorelab.uk/auth/banking/callback',
          'provider_id': 'example-aisp'}


def transport_ok(calls=None):
    calls = calls if calls is not None else []
    def transport(op, config, **args):
        calls.append(op)
        if op == 'code':
            return {'access_token': 'ACCESSTOKEN', 'refresh_token': 'REFRESHTOKEN', 'expires_in': 3600}
        if op == 'accounts':
            return {'accounts': [{'account_id': 'acc-1', 'display_name': 'Current Account', 'currency': 'GBP'}]}
        raise AssertionError(op)
    return transport, calls


class RequireReadOnlyTests(unittest.TestCase):
    def test_payment_scope_rejected(self):
        with self.assertRaises(PermissionError):
            require_read_only(['accounts:read', 'payments:write'])
        with self.assertRaises(PermissionError):
            require_read_only(['pisp.initiate'])

    def test_read_only_scopes_accepted_and_deduped(self):
        self.assertEqual(require_read_only(['accounts:read', 'accounts:read', 'balances:read']),
                         ['accounts:read', 'balances:read'])


class BankingConnectionTests(unittest.TestCase):
    setUp = test_missions.MissionTests.setUp
    tearDown = test_missions.MissionTests.tearDown

    def conn(self, scopes=('accounts:read', 'balances:read')):
        return BankingConnection(self.ledger, Fernet.generate_key(), 'owner@example.org', CONFIG, scopes)

    def state(self, c):
        return parse_qs(urlsplit(c.begin('owner@example.org', SESSION)).query)['state'][0]

    def test_defaults_to_auth_required(self):
        c = self.conn()
        self.assertEqual(c.status()['status'], 'AUTH_REQUIRED')
        with self.assertRaises(PermissionError):
            c.accounts()

    def test_construction_rejects_payment_scope(self):
        with self.assertRaises(PermissionError):
            self.conn(scopes=('accounts:read', 'payments:write'))

    def test_full_flow_encrypts_token_and_rejects_replay(self):
        c = self.conn()
        url = c.begin('owner@example.org', SESSION)
        q = parse_qs(urlsplit(url).query)
        self.assertTrue(url.startswith('https://auth.example-aisp.test/connect/authorize?'))
        self.assertEqual(q['redirect_uri'], [CONFIG['redirect_uri']])
        self.assertNotIn('payments', q['scope'][0])
        t, calls = transport_ok()
        self.assertEqual(c.callback('owner@example.org', SESSION, q['state'][0], 'CODE', t)['status'], 'CONNECTED')
        self.assertEqual(calls, ['code'])
        accounts = c.accounts(t)
        self.assertEqual(accounts, [{'id': 'acc-1', 'display_name': 'Current Account', 'currency': 'GBP'}])
        self.assertEqual(calls, ['code', 'accounts'])
        dump = '\n'.join(str(r) for r in self.ledger.db.iterdump())
        self.assertNotIn('ACCESSTOKEN', dump)
        self.assertNotIn('REFRESHTOKEN', dump)
        with self.assertRaises(PermissionError):
            c.callback('owner@example.org', SESSION, q['state'][0], 'CODE', t)
        c.disconnect()
        self.assertEqual(c.status()['status'], 'AUTH_REQUIRED')
        with self.assertRaises(PermissionError):
            c.accounts(t)

    def test_wrong_session_and_owner_rejected(self):
        c = self.conn()
        t, calls = transport_ok()
        with self.assertRaises(PermissionError):
            c.callback('owner@example.org', 'x' * 43, self.state(c), 'CODE', t)
        self.assertEqual(calls, [])  # No remote exchange on state/session mismatch.
        with self.assertRaises(PermissionError):
            c.begin('other@example.org', SESSION)
        self.assertEqual(c.status()['status'], 'AUTH_REQUIRED')

    def test_account_number_never_in_projection(self):
        c = self.conn()
        q = parse_qs(urlsplit(c.begin('owner@example.org', SESSION)).query)

        def transport(op, config, **args):
            if op == 'code':
                return {'access_token': 'TOK', 'expires_in': 3600}
            return {'accounts': [{'account_id': 'acc-1', 'display_name': 'Current',
                                  'currency': 'GBP', 'account_number': '12345678', 'sort_code': '12-34-56'}]}
        c.callback('owner@example.org', SESSION, q['state'][0], 'CODE', transport)
        accounts = c.accounts(transport)
        self.assertEqual(set(accounts[0]), {'id', 'display_name', 'currency'})

    def test_transactions_requires_connected_and_projects_bounded_fields(self):
        config_with_tx = dict(CONFIG, transactions_path='/data/v1/transactions')
        c = BankingConnection(self.ledger, Fernet.generate_key(), 'owner@example.org', config_with_tx,
                              ('accounts:read', 'balances:read'))
        with self.assertRaises(PermissionError):
            c.transactions()
        q = parse_qs(urlsplit(c.begin('owner@example.org', SESSION)).query)

        def transport(op, config, **args):
            if op == 'code':
                return {'access_token': 'TOK', 'expires_in': 3600}
            return {'transactions': [{'date': '2026-11-01T00:00:00Z', 'description': 'TESCO',
                                      'pence': -500, 'account_number': '12345678'}]}
        c.callback('owner@example.org', SESSION, q['state'][0], 'CODE', transport)
        rows = c.transactions(transport)
        self.assertEqual(rows, [{'date': '2026-11-01T00:00:00Z', 'description': 'TESCO', 'pence': -500}])


if __name__ == '__main__':
    unittest.main()
