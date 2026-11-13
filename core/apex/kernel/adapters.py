"""Bind the draft/notice adapters to the Action Gateway's adapter protocol. Status: TESTS_NOT_RUN.

An adapter is `configured()` only when its token file loads safely; otherwise the Gateway reports NOT_CONFIGURED and nothing is
sent or reserved. Token file PATHS come from the caller (never from model output or payloads); no default path is read.
Only draft creation (Gmail, Outlook) and an allow-listed owner notice (Telegram) exist: no send, delete or bank-write capability.
"""
from __future__ import annotations

import json

from .. import gmail_drafts, outlook_graph, telegram_bot
from ..bridge_auth import load_key
from ..bridge_queue import BridgeQueue
from ..private_token import PrivateTokenError, load


class _TokenAdapter:
    name = ""

    def __init__(self, token_path, transport):
        self.token_path, self.transport = token_path, transport

    def _token(self):
        return load(self.token_path)

    def configured(self):
        try:
            self._token()
            return self.transport is not None
        except (PrivateTokenError, ValueError):
            return False


class GmailDraftAdapter(_TokenAdapter):
    name = "gmail"

    def dispatch(self, payload, idempotency_key):
        gmail_drafts.create_draft(self._token(), [payload["to"]], payload["subject"], payload["body"], self.transport)
        return {"actual_units": 0}


class OutlookDraftAdapter(_TokenAdapter):
    name = "outlook"

    def dispatch(self, payload, idempotency_key):
        outlook_graph.create_draft(self._token(), [payload["to"]], payload["subject"], payload["body"], self.transport)
        return {"actual_units": 0}


class TelegramNoticeAdapter(_TokenAdapter):
    """Owner notices only: the destination is fixed configuration, never taken from the payload."""
    name = "telegram"

    def __init__(self, token_path, transport, owner_chat_id, allowlist):
        super().__init__(token_path, transport)
        self.owner_chat_id, self.allowlist = owner_chat_id, frozenset(allowlist)

    def dispatch(self, payload, idempotency_key):
        telegram_bot.send_message(self._token(), self.owner_chat_id, payload["text"], self.transport, self.allowlist)
        return {"actual_units": 0}


class LaptopBrowserAdapter:
    """Dispatch only ENQUEUES onto the bridge queue; the laptop owner still approves each task there with y/N.
    `configured()` is true only once a bridge key exists (created by the owner on the /bridge console page)."""
    name = "laptop_browser"

    def __init__(self, ledger, bridge_root):
        self.ledger, self.bridge_root = ledger, bridge_root

    def configured(self):
        try:
            return load_key(self.bridge_root) is not None
        except PermissionError:
            return False

    def dispatch(self, payload, idempotency_key):
        BridgeQueue(self.ledger).enqueue(payload["purpose"], payload["url"], json.loads(payload["steps_json"]))
        return {"actual_units": 0}


def build_adapters(token_paths, transports, telegram_chat_id=None, telegram_allowlist=(), ledger=None, bridge_root=None):
    """Return the adapters dict for ActionGateway. Missing paths or transports leave an adapter unconfigured."""
    adapters = {
        "gmail": GmailDraftAdapter(token_paths.get("gmail"), transports.get("gmail")),
        "outlook": OutlookDraftAdapter(token_paths.get("outlook"), transports.get("outlook")),
        "telegram": TelegramNoticeAdapter(token_paths.get("telegram"), transports.get("telegram"),
                                          telegram_chat_id, telegram_allowlist),
    }
    if ledger is not None and bridge_root is not None:
        adapters["laptop_browser"] = LaptopBrowserAdapter(ledger, bridge_root)
    return adapters
