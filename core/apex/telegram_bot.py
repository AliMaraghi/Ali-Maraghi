"""Telegram Bot API: allow-listed outbound notices and inbound webhook parsing for the owner's own bot.

Verified against https://core.telegram.org/bots/api on 2026-11-12:
requests are HTTPS `https://api.telegram.org/bot<token>/METHOD_NAME`; sendMessage takes `chat_id` and `text`
(1-4096 characters after entities parsing); responses are `{"ok": bool, "result"|"description", ...}`;
setWebhook `secret_token` (1-256 chars, A-Z a-z 0-9 _ -) is echoed in header X-Telegram-Bot-Api-Secret-Token;
Update has `update_id` and optional `message`; Message has `chat.id` and optional `text`.
A bot only sees chats where users message it; it cannot read anyone's personal chat history.
The bot token is part of the URL path, so no path or URL is ever put in an exception. Nothing here has been run live.
"""
from __future__ import annotations

import hmac
import json
import re

from .agent_contract import wrap_untrusted

HOST = "api.telegram.org"
MAX_TEXT = 4096
LIMIT = 1_000_000
TOKEN = re.compile(r"\d{3,20}:[A-Za-z0-9_-]{20,128}")
SECRET = re.compile(r"[A-Za-z0-9_-]{1,256}")
PROPOSAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
KIND = re.compile(r"[A-Za-z0-9 _.-]{1,40}")
CONSOLE_BASE = re.compile(r"https://[A-Za-z0-9.-]{1,253}(?::\d{1,5})?(?:/[A-Za-z0-9._~/-]{0,200})?")
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class TelegramError(RuntimeError):
    pass


def _allowed(chat_id, allowlist):
    return type(chat_id) is int and type(allowlist) in (set, frozenset, tuple, list) and chat_id in allowlist


def send_message(token, chat_id, text, transport, allowlist):
    """Send one plain-text message to an allow-listed chat. `transport(method, path, headers, body)` -> (status, content_type, bytes)."""
    if token is None:
        raise TelegramError("NOT_CONFIGURED")
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError("Invalid bot token")
    if not _allowed(chat_id, allowlist):
        raise TelegramError("CHAT_NOT_ALLOWED")
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT:
        raise ValueError("text must be 1..4096 characters")
    body = json.dumps({"chat_id": chat_id, "text": text}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "identity"}
    try:
        status, content_type, raw = transport("POST", f"/bot{token}/sendMessage", headers, body)
    except Exception:                                       # transport errors can embed the URL (and so the token)
        raise TelegramError("TRANSPORT_ERROR") from None
    if status != 200:
        raise TelegramError(f"TELEGRAM_HTTP_{status}")      # upstream body is never surfaced or logged
    if len(raw) > LIMIT or content_type.split(";")[0].strip() != "application/json":
        raise TelegramError("INVALID_RESPONSE")
    from .kernel.schema import strict_json
    try:
        data = strict_json(raw.decode())
    except ValueError:
        raise TelegramError("INVALID_RESPONSE") from None
    if not isinstance(data, dict) or data.get("ok") is not True:
        raise TelegramError("TELEGRAM_NOT_OK")
    return {"ok": True}


def live_transport(method, path, headers, body):           # pragma: no cover - not exercised offline
    from .sources.public_http import Connection, resolve_public
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.request(method, path, body, {**headers, "Connection": "close"})
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read(LIMIT + 1)
    finally:
        conn.close()


def verify_webhook_secret(header_value, expected):
    """Constant-time check of the X-Telegram-Bot-Api-Secret-Token header value."""
    if not isinstance(header_value, str) or not isinstance(expected, str):
        return False
    if not SECRET.fullmatch(expected) or not SECRET.fullmatch(header_value):
        return False
    return hmac.compare_digest(header_value.encode(), expected.encode())


def parse_update(update, allowlist):
    """Return {chat_id, text, update_id} for an allow-listed text message, else None. Text is wrapped as untrusted data."""
    if not isinstance(update, dict) or type(update.get("update_id")) is not int:
        raise ValueError("Invalid update")
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    if not _allowed(chat_id, allowlist):
        return None
    text = message.get("text")
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT:
        return None
    return {"chat_id": chat_id, "update_id": update["update_id"], "text": wrap_untrusted("chat", text)}


def approval_notification(proposal_id, kind, deadline_text, console_base):
    """Plain-text notice with a link only. Approval happens in the Access-protected console with CSRF; never here."""
    if not isinstance(proposal_id, str) or not PROPOSAL_ID.fullmatch(proposal_id):
        raise ValueError("Invalid proposal_id")
    if not isinstance(kind, str) or not KIND.fullmatch(kind):
        raise ValueError("Invalid kind")
    if not isinstance(deadline_text, str) or not 1 <= len(deadline_text) <= 80 or any(ord(c) < 32 for c in deadline_text):
        raise ValueError("Invalid deadline_text")
    if not isinstance(console_base, str) or not CONSOLE_BASE.fullmatch(console_base):
        raise ValueError("console_base must be an https URL")
    link = console_base.rstrip("/") + "/approvals/" + proposal_id
    return f"Approval needed ({kind}). Deadline: {deadline_text}\nReview in the console: {link}"
