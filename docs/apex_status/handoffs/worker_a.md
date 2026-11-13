# Worker A handoff
Status: TESTS_NOT_RUN. Only py_compile was run (Python 3.12, PYTHONDONTWRITEBYTECODE=1): telegram_bot.py OK, outlook_graph.py OK, chat_import.py OK. Correctness is not claimed.
Task: Telegram bot, Outlook Graph draft/header adapter, WhatsApp export importer. Baseline path: /tmp/claude-1000/-home-apexdev-apex-work/5f5e302b-9067-458f-887d-4f5b6fe6916e/scratchpad/work_a

Changed files (all new): core/apex/telegram_bot.py, core/apex/outlook_graph.py, core/apex/chat_import.py, docs/apex_status/integrations/{telegram,outlook_graph,chat_import}.md, this file.

Interfaces:
- telegram_bot: send_message(token, chat_id, text, transport, allowlist); verify_webhook_secret(header_value, expected); parse_update(update, allowlist); approval_notification(proposal_id, kind, deadline_text, console_base); live_transport(method, path, headers, body); TelegramError. transport(method, path, headers, body) -> (status, content_type, bytes).
- outlook_graph: assert_scopes(granted); create_draft(token, to, subject, body, transport); list_headers(token, folder_id, transport, allowlist, top=25); redact_sensitive(subject); live_transport; GraphError.
- chat_import: parse_chat(text, file_name, date_order="dmy") -> {records, system_lines, issues, provenance}.

Verified from official docs: Telegram (https://core.telegram.org/bots/api) URL form, sendMessage text 1-4096, secret header name/charset/length, Update/Message fields. Graph (user-post-messages, mailfolder-list-messages on learn.microsoft.com) endpoints, Mail.ReadWrite for drafts, Mail.ReadBasic for listing, 201/200 codes.
Not verified: Telegram chat_id type constraints beyond integer, rate limits; Graph $select/$top, from field shape, nextLink; WhatsApp line formats (no official spec; WhatsApp FAQ page loaded but shows no layout). Details in the integration docs.
Notes: wrap_untrusted allows only email/web/feed/file/mcp, so Telegram and chat import now use "chat" (lead changed after the shared contract gained it), Outlook "email", chat import "file"; the shared contract was not edited. live_transport functions reuse sources.public_http (as monzo.py does) and were not exercised.
Blockers: none for compile; no tokens/OAuth flows exist; no tests written by instruction.
