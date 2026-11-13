"""Owner-only console page /bridge: create or rotate the laptop-bridge key (shown ONCE) and see queue status. Mounted by ConsoleApp behind Cloudflare Access + CSRF."""
import html
import re
import time
from pathlib import Path

from . import bridge_auth
from .bridge_queue import BridgeQueue
from .google_web import owner_session, require_csrf
from .kernel.memory import Ledger

PATHS = re.compile(r"/bridge(?:/key|/agent\.py)?")
AGENT_FILE = Path(__file__).resolve().parents[2] / "scripts" / "laptop_agent.py"


def is_bridge_path(path):
    return isinstance(path, str) and PATHS.fullmatch(path) is not None


def page(title, inner):
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<link rel="stylesheet" href="/assets/console.css"><title>' + html.escape(title) + '</title><main><h1>' + html.escape(title) + '</h1>' + inner + '</main></html>').encode()


class BridgeRoutes:
    def __init__(self, root, owner, clock=time.time):
        self.root, self.owner, self.clock = root, owner, clock

    def handle(self, environ):
        if environ.get('HTTP_HOST') != 'console.apexcorelab.uk':
            raise PermissionError('Exact origin required')
        method, path = environ.get('REQUEST_METHOD'), environ.get('PATH_INFO')
        if (method, path) not in {('GET', '/bridge'), ('POST', '/bridge/key'), ('GET', '/bridge/agent.py')}:
            return 405, b'{"error":"METHOD_NOT_ALLOWED"}', [], 'application/json'
        with Ledger(self.root) as ledger:
            sid, row, headers = owner_session(ledger, environ, path, method)
            headers = headers + [('Cache-Control', 'no-store')]
            if path == '/bridge/agent.py':
                return 200, AGENT_FILE.read_bytes(), headers + [('Content-Disposition', 'attachment; filename="laptop_agent.py"')], 'text/x-python; charset=utf-8'
            if method == 'POST':
                require_csrf(environ, row)
                shown = bridge_auth.create_key(self.root, self.clock())
                inner = ('<p><b>Copy this key now. It is shown only once</b> and is not stored on this page.</p><pre>' + html.escape(shown) + '</pre>'
                         '<p>Paste it into the laptop agent window when it asks for the bridge key. Creating a new key replaces the old one.</p>'
                         '<p><a href="/bridge">Back</a></p>')
                return 200, page('Bridge key created', inner), headers, 'text/html; charset=utf-8'
            summary = BridgeQueue(ledger, self.clock).summary()
            poll = summary['last_poll']
            seen = 'never' if poll is None else f"{int(self.clock() - poll)} seconds ago"
            have_key = bridge_auth.load_key(self.root) is not None
            inner = ('<table><tr><th>Bridge key</th><td>' + ('created' if have_key else 'not created yet') + '</td></tr>'
                     '<tr><th>Laptop agent last polled</th><td>' + html.escape(seen) + '</td></tr>'
                     '<tr><th>Tasks</th><td>' + html.escape(', '.join(f'{k}: {v}' for k, v in sorted(summary['counts'].items())) or 'none') + '</td></tr></table>'
                     '<form method="post" action="/bridge/key"><input type="hidden" name="csrf" value="' + html.escape(row[1]) + '">'
                     '<button>' + ('Create a NEW bridge key (replaces the old one)' if have_key else 'Create the bridge key') + '</button></form>'
                     '<p><a href="/bridge/agent.py">Download laptop_agent.py</a> (the one file to run on your laptop)</p>')
            return 200, page('Laptop bridge', inner), headers, 'text/html; charset=utf-8'
