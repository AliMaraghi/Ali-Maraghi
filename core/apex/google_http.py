"""Private Gmail metadata transport. No consent, token storage or mounted routes.

Only the owner-authorized caller may supply a short-lived access token. Secrets
travel over subprocess stdin, never argv/environment/logs. No redirects/retries.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
from .gmail_sync import GmailError, METADATA_HEADERS
from .sources.public_http import Connection, resolve_public, LIMIT
from .kernel.schema import strict_json

HOST = 'gmail.googleapis.com'


def request_path(resource, params):
    if not isinstance(resource, str) or not isinstance(params, dict):
        raise ValueError('Invalid Gmail request')
    detail = re.fullmatch(r'(threads|messages)/[A-Za-z0-9]{1,128}', resource)
    allowed = set()
    if resource in {'threads', 'messages'}:
        allowed = {'maxResults', 'pageToken', 'labelIds'}
    elif resource == 'history':
        allowed = {'maxResults', 'pageToken', 'startHistoryId'}
    elif detail:
        allowed = {'format', 'metadataHeaders'}
        if params.get('format') != 'metadata' or params.get('metadataHeaders') != list(METADATA_HEADERS):
            raise ValueError('Only minimized metadata permitted')
    elif resource not in {'profile', 'labels'}:
        raise ValueError('Unsupported Gmail resource')
    if set(params) - allowed:
        raise ValueError('Unsupported Gmail parameter')
    for key, value in params.items():
        if key == 'maxResults':
            if type(value) is not int or not 1 <= value <= 20:
                raise ValueError('Page bound exceeded')
        elif key == 'labelIds':
            if not isinstance(value, list) or not 1 <= len(value) <= 10 or any(
                not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', x) for x in value):
                raise ValueError('Invalid labels')
        elif key not in {'format', 'metadataHeaders'}:
            if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(ord(x) < 33 or ord(x) > 126 for x in value):
                raise ValueError('Invalid cursor')
            if key == 'startHistoryId' and not value.isdecimal():
                raise ValueError('Invalid history ID')
    if resource in {'threads', 'messages', 'history'} and 'maxResults' not in params:
        raise ValueError('Explicit page bound required')
    query = urlencode(params, doseq=True)
    return '/gmail/v1/users/me/' + resource + ('?' + query if query else '')


def fetch(resource, params, token):
    path = request_path(resource, params)
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,4096}', token):
        raise ValueError('Invalid bearer token')
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.request('GET', path, headers={'Authorization': 'Bearer ' + token,
                     'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'})
        response = conn.getresponse()
        if response.status != 200:
            return {'status': response.status}  # Never expose provider error bodies.
        length = response.getheader('Content-Length')
        if (response.getheader('Content-Encoding', 'identity').lower() != 'identity'
                or response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json'
                or (length is not None and (not length.isascii() or not length.isdecimal() or int(length) > LIMIT))):
            raise ValueError('Invalid bounded response')
        body = response.read(LIMIT + 1)
        if len(body) > LIMIT or (length is not None and len(body) != int(length)):
            raise ValueError('Response size mismatch')
        data = strict_json(body.decode('utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Invalid JSON object')
        return {'status': 200, 'data': data}
    finally:
        conn.close()


class GmailClient:
    """Fits GmailSync.step; policy/STOP checked before each credential access.

    token_supplier must be an approved credential broker, not ChatGPT credentials.
    This client deliberately provides no automatic retries or scope escalation.
    """
    def __init__(self, ledger, owner, policy, token_supplier):
        from .google_policy import ImportPolicy
        if not isinstance(policy, ImportPolicy) or not callable(token_supplier):
            raise PermissionError('Reviewed policy and credential supplier required')
        policy.require(owner, 'gmail')
        self.ledger, self.owner, self.policy, self.token_supplier = ledger, owner, policy, token_supplier

    def get(self, resource, params):
        from .kernel.policy import enforce_durable_stop
        request_path(resource, params)
        self.policy.require(self.owner, 'gmail')
        enforce_durable_stop(self.ledger)
        try:
            token = self.token_supplier()
            result = subprocess.run([sys.executable, '-B', '-m', 'apex.google_http'],
                input=json.dumps({'resource': resource, 'params': params, 'token': token}).encode(),
                capture_output=True, timeout=20,
                env={'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'LANG': 'C.UTF-8'})
            if result.returncode or len(result.stdout) > 2_000_000:
                raise ValueError('Transport failed')
            reply = strict_json(result.stdout.decode())
        except Exception:
            raise GmailError(0) from None
        if reply.get('status') != 200:
            raise GmailError(reply.get('status', 0)) from None
        return reply['data']


if __name__ == '__main__':
    try:
        args = strict_json(sys.stdin.buffer.read(16385).decode())
        print(json.dumps(fetch(**args), allow_nan=False))
    except Exception:
        print('{"status":0}')
