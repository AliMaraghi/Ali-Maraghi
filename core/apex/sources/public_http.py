"""Bounded, pinned public HTTP transport for reviewed read-only endpoints.

No cookies, proxies, credentials, compression, retries or arbitrary destinations.
Each call runs in a time-limited subprocess; every redirect resolves all addresses
again and must retain the exact endpoint and query. POST is TED search only.
"""
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import re
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from urllib.parse import urlsplit, urljoin

from .contracts_finder import resolve_public, SourceError
from apex.kernel.schema import strict_json

LIMIT = 1_048_576
TIMEOUT = 20
ROUTES = {
    'www.find-tender.service.gov.uk': {
        '/Developer/Documentation', '/apidocumentation/1.0/GET-ocdsReleasePackages',
        '/api/1.0/ocdsReleasePackages', '/Home/TermsAndConditions',
    },
    'api.ted.europa.eu': {
        '/swagger-ui/index.html', '/swagger-ui/swagger-initializer.js',
        '/v3/api-docs', '/v3/api-docs/swagger-config', '/v3/notices/search', '/api-v3.yaml',
    },
}


def validate(url, method='GET', body=None):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 for c in url):
        raise SourceError('Invalid URL')
    p = urlsplit(url)
    notice_path = p.netloc == 'www.find-tender.service.gov.uk' and re.fullmatch(
        r'/api/1\.0/ocdsReleasePackages/(?:[0-9]{6}-[0-9]{4}|ocds-h6vhtk-[0-9a-f]{6})', p.path)
    if (p.scheme != 'https' or p.netloc not in ROUTES or p.fragment
            or (p.path not in ROUTES[p.netloc] and not notice_path)):
        raise SourceError('Destination outside reviewed endpoint scope')
    if method == 'POST':
        if (p.netloc, p.path, p.query) != ('api.ted.europa.eu', '/v3/notices/search', ''):
            raise SourceError('Only read-only TED search POST allowed')
        if not isinstance(body, dict) or len(json.dumps(body, allow_nan=False).encode()) > 4096:
            raise SourceError('Invalid bounded search body')
    elif method != 'GET' or body is not None:
        raise SourceError('Unsupported HTTP operation')
    return p


class Connection(http.client.HTTPSConnection):
    def __init__(self, host, family, address):
        super().__init__(host, timeout=5, context=ssl.create_default_context())
        self.family, self.address = family, address

    def connect(self):
        raw = socket.socket(self.family, socket.SOCK_STREAM)
        try:
            raw.settimeout(5)
            raw.connect((self.address, 443))
            if ipaddress.ip_address(raw.getpeername()[0]) != ipaddress.ip_address(self.address):
                raise SourceError('Peer differs from validated destination')
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def fetch(url, method='GET', body=None):
    original = validate(url, method, body)
    hops = []
    for attempt in range(2):
        p = validate(url, method, body)
        family, address = resolve_public(p.hostname)
        conn = Connection(p.hostname, family, address)
        try:
            headers = {'Accept': '*/*',
                       'Accept-Encoding': 'identity', 'Connection': 'close',
                       'User-Agent': 'APEX-PublicResearch/0.2'}
            encoded = None
            if body is not None:
                encoded = json.dumps(body, allow_nan=False).encode()
                headers['Content-Type'] = 'application/json'
            conn.request(method, p.path + ('?' + p.query if p.query else ''), encoded, headers)
            response = conn.getresponse()
            hops.append({'url': url, 'peer_ip': address, 'status': response.status})
            if response.status in {301, 302, 303, 307, 308}:
                target = urljoin(url, response.getheader('Location', ''))
                dest = validate(target, method, body)
                if attempt or method != 'GET' or dest != original:
                    raise SourceError('Redirect changes request or exceeds limit')
                url = target
                continue
            # Retain status/hops on HTTP rejection, never the remote error body.
            receipt = {'retrieved_at': datetime.now(timezone.utc).isoformat(),
                       'hops': hops, 'http_status': response.status}
            if response.status != 200:
                return {**receipt, 'error': 'HTTP_' + str(response.status)}
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise SourceError('Compressed responses unsupported')
            length = response.getheader('Content-Length')
            if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > LIMIT):
                raise SourceError('Invalid or oversized response length')
            data = response.read(LIMIT + 1)
            if len(data) > LIMIT or (length is not None and len(data) != int(length)):
                raise SourceError('Truncated or oversized response')
            return {**receipt, 'body_b64': base64.b64encode(data).decode(),
                    'content_type': response.getheader('Content-Type', ''),
                    'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        finally:
            conn.close()
    raise SourceError('No response')


def retrieve(url, method='GET', body=None):
    """Internal transport: caller must enforce operator authority and durable stop."""
    validate(url, method, body)
    core = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run([sys.executable, '-B', '-m', 'apex.sources.public_http'],
            input=json.dumps({'url': url, 'method': method, 'body': body}).encode(),
            capture_output=True, timeout=TIMEOUT,
            env={'PYTHONPATH': str(core), 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8'})
    except subprocess.TimeoutExpired:
        return {'error': 'HARD_TIMEOUT', 'http_status': None, 'hops': [], 'retrieved_at': None}
    if proc.returncode or len(proc.stdout) > 1_500_000:
        return {'error': 'TRANSPORT_FAILED', 'http_status': None, 'hops': [], 'retrieved_at': None}
    return strict_json(proc.stdout.decode())


if __name__ == '__main__':
    try:
        args = strict_json(sys.stdin.buffer.read(8193).decode())
        print(json.dumps(fetch(**args), allow_nan=False))
    except Exception as error:
        print(json.dumps({'error': type(error).__name__, 'http_status': None,
                          'hops': [], 'retrieved_at': None}))
