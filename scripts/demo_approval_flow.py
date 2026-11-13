"""Synthetic end-to-end approval demo through the real ConsoleApp. No network, no real data.

Run: PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/demo_approval_flow.py
Uses a throw-away workspace; the execution step is a local mock record only.
"""
import hashlib
import io
import json
import sys
import tempfile
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.approvals_web import ApprovalRoutes  # noqa: E402
from apex.console_server import ConsoleApp  # noqa: E402
from apex.kernel.approvals import ApprovalBook  # noqa: E402
from apex.kernel.memory import Ledger  # noqa: E402

OWNER, SECRET = "owner@example.org", "d" * 40


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = root / "approvals.json"
        config.write_text(json.dumps({"owner": OWNER, "approval_secret": SECRET}))
        config.chmod(0o600)
        app = ConsoleApp(root, Mock(valid=Mock(return_value=True)), None, None, None,
                         ApprovalRoutes(root, config, OWNER))

        def call(path, cookie="", method="GET", data=""):
            out = {}
            env = {"HTTP_HOST": "console.apexcorelab.uk", "HTTP_CF_ACCESS_JWT_ASSERTION": "demo", "PATH_INFO": path,
                   "HTTP_COOKIE": cookie, "REQUEST_METHOD": method, "HTTP_ORIGIN": "https://console.apexcorelab.uk",
                   "CONTENT_TYPE": "application/x-www-form-urlencoded", "CONTENT_LENGTH": str(len(data)),
                   "wsgi.input": io.BytesIO(data.encode())}
            body = b"".join(app(env, lambda status, headers: out.update(status=status, headers=dict(headers))))
            return out, body

        with Ledger(root) as ledger:
            book = ApprovalBook(ledger, SECRET.encode())
            print("1 propose      ->", book.propose("demo-1", "opportunity", "record_review", "agent:discovery",
                                                     {"title": "Synthetic public tender", "value_pence": 0}, ["ev-synthetic-1"],
                                                     commentary="Model note: looks promising (untrusted)."))
            response, _ = call("/approvals/demo-1")
            parsed = SimpleCookie(); parsed.load(response["headers"]["Set-Cookie"])
            cookie = response["headers"]["Set-Cookie"].split(";")[0]
            sid = parsed["__Host-apex-owner"].value
            csrf = ledger.db.execute("SELECT csrf FROM owner_web_sessions WHERE id=?",
                                     (hashlib.sha256(sid.encode()).hexdigest(),)).fetchone()[0]
            digest = ledger.db.execute("SELECT payload_hash FROM proposals WHERE id='demo-1'").fetchone()[0]
            print("2 view (GET)   ->", response["status"], "state still", book.state("demo-1"))
            form = urlencode({"csrf": csrf, "payload_hash": digest})
            print("3 bad CSRF     ->", call("/approvals/demo-1/approve", cookie, "POST",
                                             urlencode({"csrf": "x", "payload_hash": digest}))[0]["status"])
            print("4 approve      ->", call("/approvals/demo-1/approve", cookie, "POST", form)[0]["status"], book.state("demo-1"))
            print("5 replay       ->", call("/approvals/demo-1/approve", cookie, "POST", form)[0]["status"])
            print("6 execute mock ->", call("/approvals/demo-1/execute", cookie, "POST", form)[0]["status"], book.state("demo-1"))
            print("7 audit chain  ->", [r["payload"]["event"] for r in ledger.records("opportunity")], "verified events:", ledger.verify())


if __name__ == "__main__":
    main()
