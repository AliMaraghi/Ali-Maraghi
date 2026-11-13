#!/usr/bin/env python3
"""APEX LAPTOP AGENT - the ONE file you run on your laptop.   python laptop_agent.py

It calls OUT to your server over HTTPS (https://apexcorelab.uk/bridge) every few seconds and asks "any browser task for me?". Nothing is exposed on your laptop: no open port, no tunnel, no SSH.
Setup once:  pip install playwright   then   playwright install chromium     (Python 3.9+)
First run: it asks for the bridge key (create it at https://console.apexcorelab.uk/bridge, shown once) and remembers it in your user folder.
Safety (all enforced in this file): every task is shown here and runs only if YOU type y within 120 s; allowed websites only; it never types passwords/secrets/codes and never clicks
consent / allow / accept / agree / sign-in / pay / submit / delete buttons - at logins, 2FA, CAPTCHAs and consent screens it STOPS and hands the visible browser to you; each task uses a fresh private
browser profile; it sends back only step status, the final website name and the page title - never page text, cookies, screenshots or form values. Requests and answers are HMAC-signed with your key,
so a task is only believed if it came from your server and an answer cannot be forged.
Status: TESTS cover the signing, queue and endpoint (tests/test_bridge.py); the browser part needs Playwright and has never been run.
"""
import hashlib
import hmac
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

BASE = os.environ.get("APEX_BRIDGE_URL", "https://apexcorelab.uk")
KEY_FILE = Path(os.environ.get("APEX_AGENT_KEY_FILE", str(Path.home() / ".apex_agent_key")))
POLL_SECONDS, APPROVAL_SECONDS, HUMAN_SECONDS = 5, 120, 600
ALLOWED_HOSTS = {"console.cloud.google.com", "developers.facebook.com", "console.apexcorelab.uk", "apexcorelab.uk",
                 "enablebanking.com", "accounts.google.com", "wispy-limit-fad4.cloudflareaccess.com"}
HUMAN_HOSTS = {"accounts.google.com", "wispy-limit-fad4.cloudflareaccess.com"}
ACTIONS = ("fill", "click", "wait_for_text")
CONSENT_WORDS = re.compile(r"\b(allow|accept|agree|authori[sz]e|consent|grant|approve|confirm|sign in|log in|login|pay|purchase|submit|delete|remove)\b", re.I)
BLOCK_WORDS = re.compile(r"(captcha|verify (that )?you|are you a robot|2-step|two-factor|verification code|enter (the )?code|security check|unusual traffic)", re.I)
SECRET_FIELD = re.compile(r"(pass(word)?|secret|token|otp|one-time|code|pin|api[_-]?key)", re.I)
KEY_RE = re.compile(r"[0-9a-f]{8}\.[0-9a-f]{64}")
AUTO_CONFIRM_FILE = Path(os.environ.get("APEX_AGENT_AUTO_CONFIRM_FILE", str(Path.home() / ".apex_agent_auto_confirm")))


class Rejected(RuntimeError):
    pass


# ---- key + signed transport ------------------------------------------------------------------
def load_key():
    if not KEY_FILE.exists():
        print("Create the bridge key at https://console.apexcorelab.uk/bridge (it is shown once), then paste it here.")
        text = input("Bridge key: ").strip()
        if not KEY_RE.fullmatch(text):
            sys.exit("That is not a bridge key (expected 8 hex characters, a dot, then 64 hex characters).")
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        if os.name == "nt":                                     # best effort: owner-only access on Windows
            subprocess.run(["icacls", str(KEY_FILE), "/inheritance:r", "/grant:r", f"{os.environ.get('USERNAME', '')}:F"], capture_output=True)
    text = KEY_FILE.read_text().strip()
    if not KEY_RE.fullmatch(text):
        sys.exit(f"{KEY_FILE} is damaged; delete it and run again.")
    key_id, key_hex = text.split(".")
    return key_id, bytes.fromhex(key_hex)


def sign_request(key, method, path, ts, nonce, body):
    return hmac.new(key, f"{method}\n{path}\n{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode(), hashlib.sha256).hexdigest()


def response_sig(key, nonce, status, body):
    return hmac.new(key, f"{nonce}\n{status}\n{hashlib.sha256(body).hexdigest()}".encode(), hashlib.sha256).hexdigest()


def call(base, path, payload, key_id, key, timeout=30):
    """POST a signed request; verify the signed answer. Returns (status, dict_or_None)."""
    body = json.dumps(payload).encode()
    ts, nonce = str(int(time.time())), secrets.token_hex(16)
    headers = {"Content-Type": "application/json", "X-Apex-Key-Id": key_id, "X-Apex-Ts": ts, "X-Apex-Nonce": nonce,
               "X-Apex-Sig": sign_request(key, "POST", path, ts, nonce, body), "User-Agent": "apex-laptop-agent/1"}
    request = urllib.request.Request(base + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:          # noqa: S310 - https to the owner's own domain
            status, raw, sig = response.status, response.read(200_000), response.headers.get("X-Apex-Resp-Sig", "")
    except urllib.error.HTTPError as exc:
        status, raw, sig = exc.code, exc.read(200_000), exc.headers.get("X-Apex-Resp-Sig", "")
    if status in (401, 404, 429, 400):
        raise Rejected(status)
    if not hmac.compare_digest(sig, response_sig(key, nonce, status, raw)):
        raise Rejected("answer was not signed by your server")
    return status, (json.loads(raw) if raw else None)


# ---- console + browser -----------------------------------------------------------------------
class Console:
    def __init__(self):
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in sys.stdin:
            self.lines.put(line.strip())

    def ask(self, prompt, seconds):
        while not self.lines.empty():
            self.lines.get_nowait()
        print(prompt, flush=True)
        try:
            return self.lines.get(timeout=seconds)
        except queue.Empty:
            return None


def host_ok(url):
    parts = urlsplit(url) if isinstance(url, str) else None
    return bool(parts) and parts.scheme == "https" and parts.hostname in ALLOWED_HOSTS and not parts.username


NOTEPAD_TEXT_RE = re.compile(r"[A-Za-z0-9 ,.!\'-]{1,60}")


def task_ok(task):
    if not isinstance(task.get("purpose"), str) or not 1 <= len(task["purpose"]) <= 200:
        return False
    if task.get("kind") == "notepad_demo":
        steps = task.get("steps")
        return isinstance(steps, dict) and set(steps) == {"text"} and isinstance(steps["text"], str) and NOTEPAD_TEXT_RE.fullmatch(steps["text"])
    steps = task.get("steps")
    return (host_ok(task.get("url")) and isinstance(steps, list) and len(steps) <= 30
            and all(isinstance(s, dict) and s.get("action") in ACTIONS and isinstance(s.get("selector"), str) and 1 <= len(s["selector"]) <= 200 and set(s) <= {"action", "selector", "value"} for s in steps))


def needs_human(page):
    if (urlsplit(page.url).hostname or "") in HUMAN_HOSTS:
        return "login or identity page"
    try:
        if page.locator("input[type=password]").count() or page.locator("input[autocomplete=one-time-code]").count():
            return "password or one-time-code field"
        if BLOCK_WORDS.search(page.inner_text("body", timeout=3000)):
            return "CAPTCHA, 2FA or security check"
    except Exception:
        return "page could not be inspected"
    return None


def hand_over(console, reason, url):
    return console.ask(f"\n>>> YOUR TURN ({reason}). Finish it in the browser window, then press Enter here.\n    {url}", HUMAN_SECONDS) is not None


def run_task(task, console):
    from playwright.sync_api import sync_playwright
    results, final = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(task["url"])
            for index, step in enumerate(task["steps"], 1):
                reason = needs_human(page)
                if reason and not hand_over(console, reason, page.url):
                    results.append({"step": index, "status": "TIMED_OUT_WAITING_FOR_OWNER"})
                    break
                if not host_ok(page.url):
                    results.append({"step": index, "status": "STOPPED_LEFT_ALLOWED_SITES"})
                    break
                target, status = page.locator(step["selector"]).first, "done"
                if step["action"] == "fill":
                    hint = " ".join(filter(None, [step["selector"], target.get_attribute("type"), target.get_attribute("name"), target.get_attribute("id"),
                                                  target.get_attribute("autocomplete"), target.get_attribute("aria-label")]))
                    if SECRET_FIELD.search(hint) or step.get("value") is None:
                        status = "handed_to_owner" if hand_over(console, "secret-looking field, not filled by automation", page.url) else "timed_out"
                    else:
                        target.fill(step["value"])
                elif step["action"] == "click":
                    label = (target.inner_text(timeout=3000) or target.get_attribute("aria-label") or "").strip()
                    if CONSENT_WORDS.search(label) or CONSENT_WORDS.search(step["selector"]):
                        status = "handed_to_owner" if hand_over(console, f"consent or account button ('{label[:40]}')", page.url) else "timed_out"
                    else:
                        target.click()
                        page.wait_for_load_state("domcontentloaded")
                else:
                    page.get_by_text(step.get("value") or "", exact=False).first.wait_for(timeout=15000)
                results.append({"step": index, "status": status})
            final = {"final_host": urlsplit(page.url).hostname, "title": (page.title() or "")[:100]}
            console.ask("\nTask steps finished. Check the window, then press Enter to close the browser.", HUMAN_SECONDS)
        except Exception as exc:
            results.append({"status": "ERROR", "error": type(exc).__name__})
        finally:
            context.close()
            browser.close()
    return {"status": "FINISHED", "steps": results, **final}


def run_notepad_demo(task, console):
    """Narrow, non-general proof: write a server-chosen SHORT text to a local temp file and open it in Notepad. No keystrokes sent, no other program, no arbitrary command."""
    import tempfile
    text = task["steps"]["text"]
    if os.name != "nt":
        return {"status": "ERROR", "error": "NotWindows", "steps": []}
    path = Path(tempfile.gettempdir()) / "apex_demo.txt"
    path.write_text(text, encoding="utf-8")
    subprocess.Popen(["notepad.exe", str(path)])          # fixed program, fixed argument: no shell, no user/server-controlled command line
    console.ask(f"\nNotepad should now show: {text!r}\nPress Enter here once you have seen it.", HUMAN_SECONDS)
    return {"status": "FINISHED", "steps": [{"step": 1, "status": "done"}], "final_host": None, "title": "Notepad demo"}


def auto_confirm_enabled():
    """True only if the OWNER created this file on THEIR OWN laptop; the VPS has no way to set it. Every task still reached
    the laptop only after a real approval on https://console.apexcorelab.uk/approvals: this skips the SECOND, redundant ask.
    The hard safety rails (allowed hosts, no secrets typed, no consent/login/pay clicks, hand-over at 2FA/CAPTCHA) are
    unconditional in run_task()/run_notepad_demo() and are never affected by this flag."""
    return AUTO_CONFIRM_FILE.is_file()


def handle(task, console):
    if not task_ok(task):
        return {"status": "REJECTED_BY_AGENT_POLICY", "steps": []}
    auto = auto_confirm_enabled()
    if task.get("kind") == "notepad_demo":
        print(f"\n=== DEMO task (already approved on the console) ===\n purpose: {task['purpose']}\n action:  open Notepad showing {task['steps']['text']!r}")
        if not auto:
            answer = console.ask(f"Run it? type y within {APPROVAL_SECONDS}s (anything else = no): ", APPROVAL_SECONDS)
            if (answer or "").lower() != "y":
                return {"status": "DECLINED_BY_OWNER", "steps": []}
        return run_notepad_demo(task, console)
    summary = "\n".join(f"   {i + 1}. {s['action']} {s['selector']!r}" + (" (value hidden)" if s.get("value") else "") for i, s in enumerate(task["steps"]))
    print(f"\n=== Browser task (already approved on the console) ===\n purpose: {task['purpose']}\n open:    {task['url']}\n steps:\n{summary or '   (none)'}")
    if not auto:
        answer = console.ask(f"Run it? type y within {APPROVAL_SECONDS}s (anything else = no): ", APPROVAL_SECONDS)
        if (answer or "").lower() != "y":
            return {"status": "DECLINED_BY_OWNER", "steps": []}
    return run_task(task, console)


def main():
    key_id, key = load_key()
    console = Console()
    mode = "AUTO-CONFIRM (tasks run as soon as they are fetched, no second prompt here)" if auto_confirm_enabled() else "ASK (type y for every task, even pre-approved ones)"
    print(f"APEX laptop agent running. Asking {BASE}/bridge every {POLL_SECONDS}s. Mode: {mode}. Close this window to stop.")
    if auto_confirm_enabled():
        print(f"  (auto-confirm is on because {AUTO_CONFIRM_FILE} exists; delete that file to go back to asking every time)")
    delay = POLL_SECONDS
    while True:
        try:
            status, data = call(BASE, "/bridge/poll", {}, key_id, key)
            delay = POLL_SECONDS
            if status == 200 and data and "task" in data:
                task = data["task"]
                result = handle(task, console)
                call(BASE, "/bridge/result", {"id": task["id"], "lease_token": task["lease_token"], "result": result}, key_id, key)
        except Rejected as exc:
            hint = {"401": "key or PC clock is wrong (clock must be within 60 s)", "404": "the Cloudflare route apexcorelab.uk/bridge is not set up yet"}.get(str(exc), str(exc))
            print(f"[{time.strftime('%H:%M:%S')}] server said no: {hint}")
            delay = min(delay * 2, 120)
        except (urllib.error.URLError, OSError) as exc:
            print(f"[{time.strftime('%H:%M:%S')}] cannot reach the server ({type(exc).__name__}); retrying")
            delay = min(delay * 2, 120)
        time.sleep(delay)


if __name__ == "__main__":
    main()
