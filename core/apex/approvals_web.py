"""Owner-only approval console mounted by the existing Access-protected ConsoleApp.

Config /etc/apex/approvals-runtime.json (apexdev 0600): owner, approval_secret (>=32 chars).
Viewing a page never changes a proposal. Approve / deny / execute are POST-only, need the
Access-bound owner session, a same-origin form and the session CSRF value, and approval also
requires the payload hash the owner actually saw. Execution is a local mock record only.
"""
import hmac
import html
import json
import re
import time
from urllib.parse import parse_qs

from .google_web import ORIGIN, owner_session, protected_json
from .kernel.approvals import ApprovalBook
from .kernel.engine import canonical
from .kernel.memory import Ledger
from .kernel.policy import Policy

ID = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}'
PATH = re.compile(r'/approvals(?:/(' + ID + r')(?:/(approve|deny|execute))?)?')


def is_approvals_path(path):
    return isinstance(path, str) and PATH.fullmatch(path) is not None


def load_config(path, access_owner):
    cfg = protected_json(path)
    secret = cfg.get('approval_secret')
    if cfg.get('owner') != access_owner or not isinstance(secret, str) or len(secret) < 32:
        raise PermissionError('Approval configuration invalid or owner mismatch')
    return cfg


def read_form(environ, row, fields):
    """Same-origin, bounded, CSRF-checked form with an exact field set."""
    if environ.get('HTTP_ORIGIN') != ORIGIN or environ.get('CONTENT_TYPE') != 'application/x-www-form-urlencoded':
        raise PermissionError('Same-origin form required')
    length = environ.get('CONTENT_LENGTH', '')
    if not length.isdecimal() or not 1 <= int(length) <= 512:
        raise ValueError('Bounded form required')
    raw = environ['wsgi.input'].read(int(length))
    if len(raw) != int(length):
        raise ValueError('Incomplete form')
    form = parse_qs(raw.decode(), strict_parsing=True, max_num_fields=len(fields))
    if set(form) != set(fields) or any(len(v) != 1 for v in form.values()):
        raise ValueError('Unexpected form fields')
    if not hmac.compare_digest(form['csrf'][0], row[1]):
        raise PermissionError('CSRF rejected')
    return {k: v[0] for k, v in form.items()}


def stamp(epoch):
    return time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(epoch))


def page(title, inner):
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<link rel="stylesheet" href="/assets/console.css"><title>' + html.escape(title) + '</title>'
            '<main><h1>' + html.escape(title) + '</h1>' + inner + '</main></html>').encode()


def button(action, csrf, digest, label):
    return ('<form method="post" action="' + action + '"><input type="hidden" name="csrf" value="' + html.escape(csrf) +
            '"><input type="hidden" name="payload_hash" value="' + digest + '"><button>' + label + '</button></form>')


class ApprovalRoutes:
    def __init__(self, root, path, owner, clock=time.time):
        self.root, self.path, self.owner, self.clock = root, path, owner, clock
        load_config(path, owner)

    def book(self, ledger):
        cfg = load_config(self.path, self.owner)
        return ApprovalBook(ledger, cfg['approval_secret'].encode(), clock=self.clock)

    def handle(self, environ):
        if environ.get('HTTP_HOST') != 'console.apexcorelab.uk':
            raise PermissionError('Exact origin required')
        method, path = environ.get('REQUEST_METHOD'), environ.get('PATH_INFO')
        match = PATH.fullmatch(path or '')
        if method not in {'GET', 'POST'} or match is None:
            return 405, b'{"error":"METHOD_NOT_ALLOWED"}', [], 'application/json'
        proposal_id, action = match.group(1), match.group(2)
        if (method == 'POST') != (action is not None):
            return 405, b'{"error":"METHOD_NOT_ALLOWED"}', [], 'application/json'
        with Ledger(self.root) as ledger:
            sid, row, headers = owner_session(ledger, environ, path, method)
            book = self.book(ledger)
            book.expire_stale()
            if method == 'POST':
                return self.mutate(environ, book, row, headers, proposal_id, action)
            book.release_deferred()
            if proposal_id is None:
                return 200, self.listing(book), headers, 'text/html; charset=utf-8'
            try:
                view = book.view(proposal_id)
            except PermissionError:
                return 404, b'{"error":"NOT_FOUND"}', headers, 'application/json'
            return 200, self.detail(view, row[1]), headers, 'text/html; charset=utf-8'

    def mutate(self, environ, book, row, headers, proposal_id, action):
        form = read_form(environ, row, ('csrf', 'payload_hash'))
        view = book.view(proposal_id)
        if not hmac.compare_digest(form['payload_hash'], view['payload_hash']):
            raise PermissionError('Payload changed since it was displayed')
        if action == 'approve':
            book.approve(proposal_id, book.issue(proposal_id, self.owner), self.owner)
        elif action == 'deny':
            book.deny(proposal_id, self.owner)
        else:
            book.execute(proposal_id, Policy(domain=view['domain']))
        return 303, b'', headers + [('Location', '/approvals/' + proposal_id)], 'text/plain'

    def listing(self, book):
        rows = ''.join('<tr><td><a href="/approvals/' + html.escape(r['id']) + '">' + html.escape(r['id']) + '</a></td><td>' +
                       html.escape(r['kind']) + '</td><td><b>' + html.escape(r['state']) + '</b></td><td>' +
                       stamp(r['decision_deadline']) + '</td></tr>' for r in book.listing())
        return page('Approvals', '<p>Synthetic and mock actions only. Nothing here contacts an external system.</p>'
                    '<table><tr><th>Proposal</th><th>Kind</th><th>State</th><th>Decision deadline</th></tr>' + rows + '</table>')

    def detail(self, view, csrf):
        pretty = json.dumps(view['payload'], indent=2, sort_keys=True, ensure_ascii=False)
        base = '/approvals/' + view['id']
        controls = ''
        if view['state'] == 'PENDING':
            controls = button(base + '/approve', csrf, view['payload_hash'], 'Approve this exact action') + \
                button(base + '/deny', csrf, view['payload_hash'], 'Deny')
        elif view['state'] == 'APPROVED':
            controls = button(base + '/execute', csrf, view['payload_hash'], 'Execute (local mock record only)')
        commentary = ''
        if view['model_commentary']:
            commentary = ('<section><h2>Model-generated commentary</h2><p><i>Untrusted. Not part of what you approve and '
                          'not covered by the payload hash.</i></p><pre>' + html.escape(view['model_commentary']) + '</pre></section>')
        inner = ('<section><h2>Application-generated facts</h2><table>'
                 '<tr><th>Proposal</th><td>' + html.escape(view['id']) + '</td></tr>'
                 '<tr><th>State</th><td><b>' + html.escape(view['state']) + '</b></td></tr>'
                 '<tr><th>Domain / kind</th><td>' + html.escape(view['domain']) + ' / ' + html.escape(view['kind']) + '</td></tr>'
                 '<tr><th>Proposed by</th><td>' + html.escape(view['proposer']) + '</td></tr>'
                 '<tr><th>Created</th><td>' + stamp(view['created_at']) + '</td></tr>'
                 '<tr><th>Decision deadline (unanswered = vetoed)</th><td>' + stamp(view['decision_deadline']) + '</td></tr>'
                 '<tr><th>Approval confirmation validity</th><td>' + str(view['approval_token_ttl_seconds'] // 60) + ' minutes</td></tr>'
                 '<tr><th>Evidence</th><td>' + html.escape(', '.join(view['evidence'])) + '</td></tr>'
                 '<tr><th>Payload SHA-256</th><td><code>' + view['payload_hash'] + '</code></td></tr></table>'
                 '<h3>Exact action parameters</h3><pre>' + html.escape(pretty) + '</pre></section>' + commentary +
                 '<section>' + controls + '</section><p><a href="/approvals">All proposals</a></p>')
        return page('Approval ' + view['id'], inner)
