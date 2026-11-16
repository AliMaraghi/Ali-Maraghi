"""Optional owner-only Open Banking routes mounted by the existing console after Access.

Config /etc/apex/banking-runtime.json (apexdev 0600): owner, encryption_key, scopes, and
`config` (the BankingConnection config dict: host, authorize_path, token_path, accounts_path,
transactions_path [optional], client_id, client_secret, redirect_uri, provider_id). Missing
config leaves routes off - same fail-closed default as meta_web.py/google_web.py. No aggregator
is pre-selected here: `config` must name a real, reviewed Account Information Service Provider
the owner has actually registered an application with - see banking_connect.py's own docstring.
"""
import html
import json
from .kernel.memory import Ledger
from .google_web import protected_json, owner_session, require_csrf, ORIGIN
from .banking_connect import BankingConnection

PATHS = frozenset({'/connections/banking', '/connections/banking/accounts', '/connections/banking/transactions',
                   '/auth/banking/start', '/auth/banking/callback', '/auth/banking/disconnect'})


def load_config(path, access_owner):
    cfg = protected_json(path)
    if cfg.get('owner') != access_owner:
        raise PermissionError('Banking and Access owner mismatch')
    if cfg.get('config', {}).get('redirect_uri') != ORIGIN + '/auth/banking/callback':
        raise PermissionError('Banking redirect_uri must match this console origin exactly')
    return cfg


class BankingRoutes:
    def __init__(self, root, path, owner):
        self.root, self.path, self.owner = root, path, owner
        cfg = load_config(path, owner)
        with Ledger(root) as ledger:
            self.connection(ledger, cfg)  # Fail startup on invalid explicit config.

    def connection(self, ledger, cfg):
        return BankingConnection(ledger, cfg['encryption_key'].encode(), cfg['owner'], cfg['config'], cfg['scopes'])

    def handle(self, environ):
        cfg = load_config(self.path, self.owner)
        if environ.get('HTTP_HOST') != 'console.apexcorelab.uk':
            raise PermissionError('Exact origin required')
        method = environ.get('REQUEST_METHOD'); path = environ.get('PATH_INFO')
        if method not in {'GET', 'POST'}:
            return 405, b'{"error":"METHOD_NOT_ALLOWED"}', [], 'application/json'
        with Ledger(self.root) as ledger:
            sid, row, headers = owner_session(ledger, environ, path, method)
            connection = self.connection(ledger, cfg)
            if method == 'POST':
                require_csrf(environ, row)
                if path == '/auth/banking/start':
                    return 303, b'', headers + [('Location', connection.begin(self.owner, sid))], 'text/plain'
                if path == '/auth/banking/disconnect':
                    connection.disconnect()
                    return 303, b'', headers + [('Location', '/connections/banking')], 'text/plain'
                return 404, b'{}', headers, 'application/json'
            if path == '/auth/banking/callback':
                from urllib.parse import parse_qs
                query = environ.get('QUERY_STRING', '')
                if len(query) > 8192:
                    raise ValueError('Callback too large')
                fields = parse_qs(query, strict_parsing=True, max_num_fields=10)
                if 'error' in fields:
                    raise PermissionError('Consent not completed')
                if any(len(fields.get(k, [])) != 1 for k in ('state', 'code')):
                    raise ValueError('Invalid callback')
                connection.callback(self.owner, sid, fields['state'][0], fields['code'][0])
                return 303, b'', headers + [('Location', '/connections/banking')], 'text/plain'
            if path == '/connections/banking/accounts':
                return 200, json.dumps(connection.accounts()).encode(), headers, 'application/json'
            if path == '/connections/banking/transactions':
                return 200, json.dumps(connection.transactions()).encode(), headers, 'application/json'
            if path != '/connections/banking':
                return 405, b'{}', headers, 'application/json'
            status = connection.status()
            detail = html.escape(status['status'])
            if 'reconnect_within_days' in status:
                detail += ' (reconnect within ' + str(status['reconnect_within_days']) + ' days)'
            controls = ''.join('<form method="post" action="' + route + '"><input type="hidden" name="csrf" value="'
                               + html.escape(row[1]) + '"><button>' + label + '</button></form>'
                               for route, label in [('/auth/banking/start', 'Connect / reconnect bank'),
                                                    ('/auth/banking/disconnect', 'Disconnect locally')])
            links = ('<p><a href="/connections/banking/accounts">View accounts (JSON)</a> · '
                     '<a href="/connections/banking/transactions">View transactions (JSON)</a></p>'
                     if status['status'] == 'CONNECTED' else '')
            page = ('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>Banking connection</title><body><main><h1>Banking connection</h1><p>' + detail + '</p>'
                    '<p>Read-only: account list and recent transactions only. Payment Initiation is blocked at '
                    'the code level, not just by policy. Local disconnect does not revoke the grant with the '
                    'provider.</p>' + links + controls + '<a href="/console">Founder console</a></main></body></html>')
            return 200, page.encode(), headers, 'text/html; charset=utf-8'
