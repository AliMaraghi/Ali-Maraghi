#!/usr/bin/env python3
"""Owner approval over Telegram (stdlib only; runs on a laptop or the server). Status: TESTS_NOT_RUN, never run against Telegram.

request_approval(obstacle_description, action_url) sends ONE message to ONE allow-listed chat and waits for the owner's reply "APPROVED <code>" (or "DENY <code>").
- Only the exact reply with this request's random code counts; replies from any other chat, older messages, or free text never count (older updates are drained first).
- It authorises the assistant to CONTINUE its own work. It is not consent to any provider: the owner still performs every login, 2FA, OAuth "Allow" and terms acceptance personally.
- The bot token is read from a private file (APEX_TELEGRAM_TOKEN_FILE, mode 0600) or the TELEGRAM_BOT_TOKEN environment variable, and never printed; transport errors are collapsed so the token-bearing URL never appears.
- Uses the Telegram Bot API over HTTPS (sendMessage, getUpdates: offset = last update_id + 1, negative offset starts from the end of the queue; getUpdates does not work while a webhook is set).
  The python-telegram-bot library was not used: it is not installed here and there is no pip on the server; the plain Bot API calls need no dependency.
CLI:  python3 approval_bot.py ask "Google needs your click" "https://accounts.google.com/..."   (exit 0 approved, 1 denied, 2 timed out)
Env:  TELEGRAM_BOT_TOKEN or APEX_TELEGRAM_TOKEN_FILE ; APEX_TELEGRAM_CHAT_ID (your numeric chat id)
"""
import json
import os
import re
import secrets
import stat
import sys
import time
import urllib.error
import urllib.request

API = "https://api.telegram.org"
TOKEN_RE = re.compile(r"\d{3,20}:[A-Za-z0-9_-]{20,128}")
REPLY_RE = re.compile(r"\s*(APPROVED|DENY)\s+([0-9a-f]{6})\s*", re.IGNORECASE)
MAX_DESCRIPTION = 300


class BotError(RuntimeError):
    pass


def load_token():
    path = os.environ.get("APEX_TELEGRAM_TOKEN_FILE")
    if path:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid not in (os.getuid(), 0):
            raise BotError("TOKEN_FILE_NOT_PRIVATE")
        with open(path, "r", encoding="ascii") as stream:
            token = stream.read().strip()
    else:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise BotError("NOT_CONFIGURED")
    if not TOKEN_RE.fullmatch(token):
        raise BotError("INVALID_TOKEN_FORMAT")
    return token


def _call(token, method, payload, timeout=15):
    request = urllib.request.Request(f"{API}/bot{token}/{method}", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:      # noqa: S310 - fixed https host
            data = json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as exc:
        raise BotError(f"TELEGRAM_HTTP_{exc.code}") from None
    except Exception:
        raise BotError("TRANSPORT_ERROR") from None                              # the URL contains the token
    if not isinstance(data, dict) or data.get("ok") is not True:
        raise BotError("TELEGRAM_NOT_OK")
    return data.get("result")


def _clean(text, limit):
    if not isinstance(text, str) or not text.strip() or any(ord(c) < 32 for c in text):
        raise ValueError("Invalid text")
    return text.strip()[:limit]


def request_approval(obstacle_description, action_url, token=None, chat_id=None, timeout_seconds=900,
                     call=_call, clock=time.monotonic, sleep=time.sleep):
    """Returns 'APPROVED', 'DENIED' or 'TIMEOUT'. Never raises for a missing reply; raises BotError for configuration or transport problems."""
    token = token or load_token()
    chat_id = int(chat_id if chat_id is not None else os.environ.get("APEX_TELEGRAM_CHAT_ID", "0"))
    if not chat_id:
        raise BotError("NOT_CONFIGURED")
    description = _clean(obstacle_description, MAX_DESCRIPTION)
    if not isinstance(action_url, str) or not re.fullmatch(r"https://[A-Za-z0-9.-]{1,253}(?:/[\x21-\x7e]{0,1500})?", action_url):
        raise ValueError("action_url must be an https URL")
    # Drain everything older than this request so an earlier "APPROVED" can never count.
    latest = call(token, "getUpdates", {"offset": -1, "timeout": 0, "allowed_updates": ["message"]})
    offset = (latest[-1]["update_id"] + 1) if latest else 0
    if offset:
        call(token, "getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["message"]})
    code = secrets.token_hex(3)
    call(token, "sendMessage", {"chat_id": chat_id, "text":
         f"Obstacle: {description}\nTap here to open it: {action_url}\n\nWhen you have done it, reply:  APPROVED {code}\nTo refuse:  DENY {code}"})
    deadline = clock() + timeout_seconds
    while clock() < deadline:
        updates = call(token, "getUpdates", {"offset": offset, "timeout": 2, "allowed_updates": ["message"]}, timeout=15)
        for update in updates or []:
            offset = max(offset, update["update_id"] + 1)
            message = update.get("message") or {}
            if (message.get("chat") or {}).get("id") != chat_id:
                continue                                                          # other chats are ignored entirely
            match = REPLY_RE.fullmatch(message.get("text") or "")
            if match and match.group(2).lower() == code:
                return "APPROVED" if match.group(1).upper() == "APPROVED" else "DENIED"
        sleep(1)
    return "TIMEOUT"


def main(argv):
    if len(argv) != 4 or argv[1] != "ask":
        print(__doc__)
        return 64
    try:
        result = request_approval(argv[2], argv[3])
    except (BotError, ValueError) as exc:
        print(f"approval_bot: {exc}", file=sys.stderr)
        return 3
    print(result)
    return {"APPROVED": 0, "DENIED": 1, "TIMEOUT": 2}[result]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
