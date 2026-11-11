"""Owner-only Financial Intelligence routes mounted by the existing console.

Config /etc/apex/finance-runtime.json (apexdev 0600): owner, encryption_key and,
once registered, enablebanking_app_id + private_key_pem. Read-only AIS only.
"""
import html
import json
import re
from urllib.parse import parse_qs
from .kernel.memory import Ledger
from .google_web import protected_json, owner_session, require_csrf
from .finance import Finance, TARGETS, BY_SLUG


def is_finance_path(path):
    return isinstance(path, str) and (path == '/connections/finance' or path == '/auth/finance/callback'
                                      or re.fullmatch(r'/(auth/finance/(start|disconnect)|connections/finance/sync)/[a-z]+(/[0-9])?', path) is not None)


def load_config(path, access_owner):
    cfg = protected_json(path)
    if cfg.get('owner') != access_owner:
        raise PermissionError('Finance and Access owner mismatch')
    return cfg


def service(ledger, cfg):
    return Finance(ledger, cfg['encryption_key'].encode(), cfg['owner'], cfg.get('enablebanking_app_id'),
                   cfg.get('private_key_pem'))


def pounds(value):
    return '—' if value is None else ('-' if value < 0 else '') + '£{:,.2f}'.format(abs(value) / 100)


class FinanceRoutes:
    def __init__(self, root, path, owner):
        self.root, self.path, self.owner = root, path, owner
        cfg = load_config(path, owner)
        with Ledger(root) as ledger:
            service(ledger, cfg)

    def handle(self, environ):
        cfg = load_config(self.path, self.owner)
        if environ.get('HTTP_HOST') != 'console.apexcorelab.uk':
            raise PermissionError('Exact origin required')
        method = environ.get('REQUEST_METHOD'); path = environ.get('PATH_INFO')
        if method not in {'GET', 'POST'}:
            return 405, b'{"error":"METHOD_NOT_ALLOWED"}', [], 'application/json'
        parts = path.strip('/').split('/')
        with Ledger(self.root) as ledger:
            sid, row, headers = owner_session(ledger, environ, path, method)
            finance = service(ledger, cfg)
            if method == 'POST':
                require_csrf(environ, row)
                slug = parts[2] if len(parts) > 2 else ''
                if slug not in BY_SLUG:
                    return 404, b'{}', headers, 'application/json'
                if path.startswith('/auth/finance/start/'):
                    url = finance.begin(self.owner, sid, slug, int(parts[3]) if len(parts) > 3 else 0)
                    if not re.fullmatch(r'https://[A-Za-z0-9.-]+/[\x21-\x7e]{0,4000}', url):
                        raise ValueError('Unexpected consent URL')
                    # Plain navigation link: consent host varies by bank; avoids CSP form-action on redirects.
                    body = ('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">'
                            '<title>Bank consent</title><main><h1>' + html.escape(BY_SLUG[slug]['name']) + '</h1>'
                            '<p>Read-only account access. You will sign in on the bank\'s own screen; APEX never sees your password.</p>'
                            '<p><a href="' + html.escape(url) + '" rel="noreferrer">Continue to bank consent</a></p></main>')
                    return 200, body.encode(), headers, 'text/html; charset=utf-8'
                if path.startswith('/auth/finance/disconnect/'):
                    finance.disconnect(slug)
                elif path.startswith('/connections/finance/sync/'):
                    return 200, json.dumps(finance.sync(slug)).encode(), headers, 'application/json'
                return 303, b'', headers + [('Location', '/connections/finance')], 'text/plain'
            if path == '/auth/finance/callback':
                query = environ.get('QUERY_STRING', '')
                if len(query) > 8192:
                    raise ValueError('Callback too large')
                fields = parse_qs(query, strict_parsing=True, max_num_fields=10)
                if 'error' in fields:
                    raise PermissionError('Bank consent not completed')
                if any(len(fields.get(k, [])) != 1 for k in ('state', 'code')):
                    raise ValueError('Invalid callback')
                finance.callback(self.owner, sid, fields['state'][0], fields['code'][0])
                return 303, b'', headers + [('Location', '/connections/finance')], 'text/plain'
            if path != '/connections/finance':
                return 405, b'{}', headers, 'application/json'
            return 200, self.page(finance, row[1]).encode(), headers, 'text/html; charset=utf-8'

    def page(self, finance, csrf):
        board = finance.dashboard()
        try:
            coverage, coverage_note = finance.coverage(), ''
        except PermissionError:
            coverage, coverage_note = {}, 'Enable Banking application not provisioned: live consent unavailable.'
        except Exception:
            coverage, coverage_note = {}, 'Aggregator coverage check failed; retry later.'
        def form(action, label):
            return ('<form method="post" action="' + action + '"><input type="hidden" name="csrf" value="'
                    + html.escape(csrf) + '"><button>' + html.escape(label) + '</button></form>')
        t = board['totals_gbp']
        out = ['<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">'
               '<title>Financial Intelligence</title><body><main><h1>Financial Intelligence</h1>'
               '<p>Read-only. No payments, transfers or credit applications. Bank login happens only on the bank\'s own screen.</p>',
               '<p>Live accounts: ' + str(board['live_count']) + ' of ' + str(len(TARGETS)) + '</p>',
               '<p>Assets ' + pounds(t['assets_minor']) + ' · Liabilities ' + pounds(t['liabilities_minor'])
               + ' · Income 30d ' + pounds(t['income_30d_minor']) + ' · Spending 30d ' + pounds(t['spending_30d_minor'])
               + ' (GBP, live accounts only)</p>', '<p>' + html.escape(coverage_note) + '</p>']
        for e in board['entries']:
            out.append('<section><h2>' + html.escape(e['name']) + '</h2><p>Status: <b>' + e['status'] + '</b>'
                       + (' · via ' + html.escape(e['aspsp']) if e['aspsp'] else '')
                       + (' · consent until ' + html.escape(e['consent_valid_until']) if e['consent_valid_until'] else '') + '</p>')
            for a in e['accounts']:
                b = a.get('balance') or {}
                out.append('<p>' + html.escape(a['name'] or '') + ': ' + ('owed ' if a['liability'] else 'balance ')
                           + pounds(b.get('minor')) + (' (' + html.escape(b.get('type', '')) + ')' if b else '')
                           + (' · limit ' + pounds(a['credit_limit_minor']) if a.get('credit_limit_minor') is not None else '')
                           + ' · ' + str(a['transactions']) + ' transactions · due date: not supplied</p>')
            for err in e['errors']:
                out.append('<p>Error: ' + html.escape(err['account'] + ': ' + err['error']) + '</p>')
            if e['note']:
                out.append('<p><small>' + html.escape(e['note']) + '</small></p>')
            names = coverage.get(e['slug'], [])
            if coverage and not names:
                out.append('<p>Not listed by the aggregator for UK personal accounts: statement import only.</p>')
            for i, name in enumerate(names[:6]):
                out.append(form('/auth/finance/start/' + e['slug'] + '/' + str(i), 'Connect via ' + name))
            if e['status'] in ('LIVE', 'AUTHORIZED_NOT_YET_SYNCED', 'RECONNECT_REQUIRED'):
                out.append(form('/connections/finance/sync/' + e['slug'], 'Refresh now'))
                out.append(form('/auth/finance/disconnect/' + e['slug'], 'Disconnect locally'))
            out.append('</section>')
        out.append('<a href="/console">Founder console</a></main></body></html>')
        return ''.join(out)
