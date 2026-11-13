# Telegram bot adapter (TESTS_NOT_RUN, never run live)
Module: core/apex/telegram_bot.py. Compiles only.

Verified (https://core.telegram.org/bots/api, fetched 2026-11-12): URL form `https://api.telegram.org/bot<token>/METHOD`; sendMessage `text` 1-4096 chars after entities parsing; `chat_id` (docs mark it optional only for ephemeral callback replies); response `ok`/`result`/`description`; setWebhook `secret_token` 1-256 chars of A-Za-z0-9_- sent in header `X-Telegram-Bot-Api-Secret-Token`; Update.update_id, Update.message, Message.chat.id, Message.text.
Not verified: setWebhook full parameter list, rate limits, parse_mode behaviour (not used; plain text only).

Behaviour: token None -> NOT_CONFIGURED; chat ids outside the explicit allowlist refused (send and parse); token never appears in exceptions (transport errors replaced by TRANSPORT_ERROR); inbound text wrapped with wrap_untrusted source "feed" (the contract has no telegram source; no shared file edited).
approval_notification yields only a link `<console_base>/approvals/<proposal_id>`; approval is Cloudflare Access plus CSRF in the console. No token, payload or approve/deny action in the message.
Limits: a bot sees only chats where users message it or add it; it cannot read a person's personal chat history. MTProto userbots are out of scope. Webhook route, secret storage and bot token are not configured.
