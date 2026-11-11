"""Optional owner-only Meta routes mounted by the existing console after Access.

Config /etc/apex/meta-runtime.json (apexdev 0600): owner, app_id, app_secret,
graph_version, encryption_key, privacy_review. Missing config leaves routes off.
"""
import html
import json
from .kernel.memory import Ledger
from .google_web import protected_json, owner_session, require_csrf
from .meta_connect import MetaConnection
from .meta_readonly import MetaClient, MetaPageSync

PATHS = frozenset({'/connections/meta', '/connections/meta/sync', '/auth/meta/start',
                   '/auth/meta/callback', '/auth/meta/disconnect'})


def load_config(path, access_owner):
    cfg = protected_json(path)
    if cfg.get('owner') != access_owner:
        raise PermissionError('Meta and Access owner mismatch')
    return cfg


class MetaRoutes:
    def __init__(self, root, path, owner):
        self.root, self.path, self.owner = root, path, owner
        cfg = load_config(path, owner)
        with Ledger(root) as ledger:
            self.connection(ledger, cfg)  # Fail startup on invalid explicit config.

    def connection(self, ledger, cfg):
        return MetaConnection(ledger, cfg['encryption_key'].encode(), cfg['owner'], cfg['app_id'],
                              cfg['app_secret'], cfg['graph_version'], cfg['privacy_review'])

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
                if path == '/auth/meta/start':
                    return 303, b'', headers + [('Location', connection.begin(self.owner, sid))], 'text/plain'
                if path == '/connections/meta/sync':
                    binding = connection.binding()
                    receipt = MetaPageSync(ledger, cfg['encryption_key'].encode(), binding).step(
                        MetaClient(ledger, binding, connection.token))
                    return 200, json.dumps(receipt).encode(), headers, 'application/json'
                if path == '/auth/meta/disconnect':
                    connection.disconnect()
                    return 303, b'', headers + [('Location', '/connections/meta')], 'text/plain'
                return 404, b'{}', headers, 'application/json'
            if path == '/auth/meta/callback':
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
                return 303, b'', headers + [('Location', '/connections/meta')], 'text/plain'
            if path != '/connections/meta':
                return 405, b'{}', headers, 'application/json'
            status = connection.status()
            detail = html.escape(status['status'])
            if 'reconnect_within_days' in status:
                detail += ' (reconnect within ' + str(status['reconnect_within_days']) + ' days)'
            controls = ''.join('<form method="post" action="' + route + '"><input type="hidden" name="csrf" value="'
                               + html.escape(row[1]) + '"><button>' + label + '</button></form>'
                               for route, label in [('/auth/meta/start', 'Connect / reconnect Facebook'),
                                                    ('/connections/meta/sync', 'Discover one page of managed Pages'),
                                                    ('/auth/meta/disconnect', 'Disconnect locally')])
            page = ('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>Meta connection</title><body><main><h1>Meta connection</h1><p>' + detail + '</p>'
                    '<p>Read-only: managed Facebook Pages and linked Instagram professional accounts. '
                    'No posting or messaging. Local disconnect does not revoke the grant in Facebook settings.</p>'
                    + controls + '<a href="/console">Founder console</a></main></body></html>')
            return 200, page.encode(), headers, 'text/html; charset=utf-8'
