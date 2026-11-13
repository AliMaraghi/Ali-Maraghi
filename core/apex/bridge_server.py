"""Public-facing (through the Cloudflare route apexcorelab.uk/bridge) HTTP endpoint for the laptop agent. Binds 127.0.0.1 only; Cloudflare Tunnel is the only way in.

POST /bridge/poll   {}                                  -> 200 {"task": {...}} | 204 (nothing to do)
POST /bridge/result {"id","lease_token","result":{...}} -> 200 {"ok":true} | 409
GET  /bridge/health                                     -> 200 {"ok":true}   (no data)
Everything else is 404. Every POST must carry a valid HMAC signature (bridge_auth); failures return a bare 401 with no detail. The endpoint cannot ENQUEUE work.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import bridge_auth
from .bridge_queue import BridgeQueue, QueueError
from .kernel.memory import Ledger

MAX_BODY = 16_384
RATE_PER_MINUTE = 240


def make_server(root, port=8770, host="127.0.0.1", clock=time.time):
    if host != "127.0.0.1":
        raise ValueError("The bridge endpoint binds loopback only")
    root = Path(root)
    nonces, lock, hits = bridge_auth.NonceCache(clock), threading.Lock(), deque()

    class Handler(BaseHTTPRequestHandler):
        server_version = "APEX-Bridge"
        sys_version = ""

        def log_message(self, *args):          # never log paths, headers or bodies
            pass

        def _send(self, status, payload=None, key=None, nonce=None):
            body = b"" if payload is None else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if key is not None and nonce is not None:
                self.send_header("X-Apex-Resp-Sig", bridge_auth.sign_response(key, nonce, status, body))
            self.end_headers()
            self.wfile.write(body)

        def _limited(self):
            now = clock()
            with lock:
                while hits and hits[0] <= now - 60:
                    hits.popleft()
                if len(hits) >= RATE_PER_MINUTE:
                    return True
                hits.append(now)
            return False

        def do_GET(self):
            self._send(200, {"ok": True}) if self.path == "/bridge/health" else self._send(404)

        def do_POST(self):
            if self.path not in ("/bridge/poll", "/bridge/result"):
                return self._send(404)
            if self._limited():
                return self._send(429)
            length = self.headers.get("Content-Length", "")
            if not length.isdecimal() or int(length) > MAX_BODY:
                return self._send(400)
            body = self.rfile.read(int(length))
            try:
                loaded = bridge_auth.load_key(root)
                if loaded is None:
                    return self._send(401)
                key_id, key = loaded
                nonce = bridge_auth.verify_request(key_id, key, {k.lower(): v for k, v in self.headers.items()}, "POST", self.path, body, nonces, clock())
                data = json.loads(body or b"{}")
                with Ledger(root) as ledger:
                    queue = BridgeQueue(ledger, clock)
                    if self.path == "/bridge/poll":
                        queue.touch_poll()
                        task = queue.lease_next()
                        return self._send(204, None, key, nonce) if task is None else self._send(200, {"task": task}, key, nonce)
                    ok = queue.submit_result(data["id"], data["lease_token"], data["result"])
                    return self._send(200 if ok else 409, {"ok": ok}, key, nonce)
            except bridge_auth.AuthError:
                return self._send(401)
            except (QueueError, KeyError, TypeError, ValueError):
                return self._send(400)

    return ThreadingHTTPServer((host, port), Handler)
