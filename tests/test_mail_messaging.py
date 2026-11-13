"""Contract tests for Outlook (paging/nextLink/drafts), Gmail drafts (no-send), Telegram and the WhatsApp importer. Synthetic data, no network."""
import base64
import json
import unittest
from email import message_from_bytes

from apex import chat_import, gmail_drafts, outlook_graph, telegram_bot

TOKEN = "t" * 40
FOLDER = "inbox1"
BASE = "https://graph.microsoft.com/v1.0/me/mailFolders/" + FOLDER + "/messages"


class Seq:
    """Transport returning queued (status, body) pairs and recording every path."""

    def __init__(self, *responses, ctype="application/json"):
        self.responses, self.ctype, self.calls = list(responses), ctype, []

    def __call__(self, method, path, headers, body=None):
        self.calls.append((method, path))
        status, payload = self.responses.pop(0)
        return status, self.ctype, payload if isinstance(payload, bytes) else json.dumps(payload).encode()


def message(i, subject="Hello", sender="a@example.test"):
    return {"id": f"id{i}", "receivedDateTime": "2026-11-10T09:00:00Z", "subject": subject, "from": {"emailAddress": {"address": sender}}}


class OutlookTests(unittest.TestCase):
    def test_scope_guard(self):
        self.assertTrue(outlook_graph.assert_scopes("Mail.ReadBasic Mail.ReadWrite openid"))
        for bad, code in ((["Mail.ReadBasic", "Mail.ReadWrite", "Mail.Send"], "SEND_SCOPE_REFUSED"), (["Mail.ReadBasic"], "MISSING_REQUIRED_SCOPES"),
                          (["Mail.ReadBasic", "Mail.ReadWrite", "Calendars.ReadWrite"], "UNEXPECTED_SCOPES")):
            with self.assertRaisesRegex(outlook_graph.GraphError, code):
                outlook_graph.assert_scopes(bad)

    def test_no_send_function_exists(self):
        self.assertFalse([n for n in dir(outlook_graph) if "send" in n.lower() and callable(getattr(outlook_graph, n)) and not n.startswith("_")
                          and n not in ("assert_scopes",)])

    def test_draft_creation(self):
        fake = Seq((201, {"id": "AAMk123", "isDraft": True}))
        out = outlook_graph.create_draft(TOKEN, ["x@example.test"], "Subject", "Body", fake)
        self.assertEqual(out, {"id": "AAMk123", "is_draft": True})
        self.assertEqual(fake.calls[0], ("POST", "/v1.0/me/messages"))
        with self.assertRaisesRegex(outlook_graph.GraphError, "INVALID_RESPONSE"):
            outlook_graph.create_draft(TOKEN, ["x@example.test"], "S", "B", Seq((201, {"id": "x", "isDraft": False})))
        with self.assertRaises(ValueError):
            outlook_graph.create_draft(TOKEN, ["bad address"], "S", "B", Seq())
        with self.assertRaisesRegex(outlook_graph.GraphError, "NOT_CONFIGURED"):
            outlook_graph.create_draft(None, ["x@example.test"], "S", "B", Seq())

    def test_listing_select_paging_and_verbatim_next_link(self):
        link = BASE + "?$top=25&$skiptoken=ab%20cd"
        fake = Seq((200, {"value": [message(1)], "@odata.nextLink": link}), (200, {"value": [message(2, "Pay 12345678 to 11-22-33")]}))
        out = outlook_graph.list_headers(TOKEN, FOLDER, fake, {FOLDER})
        self.assertEqual((len(out["headers"]), out["pages"], out["truncated"]), (2, 2, False))
        self.assertIn("%24select=id%2CreceivedDateTime%2Cfrom%2Csubject", fake.calls[0][1])
        self.assertEqual(fake.calls[1][1], "/v1.0/me/mailFolders/inbox1/messages?$top=25&$skiptoken=ab%20cd")    # forwarded verbatim
        subject = out["headers"][1]["subject"]
        self.assertEqual(subject["role"], "data")
        self.assertIn("[NUMBER]", subject["content"])
        self.assertIn("[SORTCODE]", subject["content"])

    def test_next_link_is_validated_before_credentials_are_forwarded(self):
        bad_links = ["http://graph.microsoft.com/v1.0/me/mailFolders/inbox1/messages?x=1", "https://evil.example/v1.0/me/mailFolders/inbox1/messages?x=1",
                     "https://graph.microsoft.com:444/v1.0/me/mailFolders/inbox1/messages?x=1", "https://u:p@graph.microsoft.com/v1.0/me/mailFolders/inbox1/messages?x=1",
                     "https://graph.microsoft.com/v1.0/me/mailFolders/other/messages?x=1", "https://graph.microsoft.com/v1.0/me/messages?x=1",
                     BASE, BASE + "?x=1#frag"]
        for link in bad_links:
            fake = Seq((200, {"value": [message(1)], "@odata.nextLink": link}), (200, {"value": []}))
            with self.assertRaisesRegex(outlook_graph.GraphError, "INVALID_NEXT_LINK", msg=link):
                outlook_graph.list_headers(TOKEN, FOLDER, fake, {FOLDER})
            self.assertEqual(len(fake.calls), 1, link)                    # the second request (with credentials) was never made

    def test_bounds_and_allowlist(self):
        link = BASE + "?$skiptoken=x"
        endless = Seq(*[(200, {"value": [message(i)], "@odata.nextLink": link}) for i in range(20)])
        out = outlook_graph.list_headers(TOKEN, FOLDER, endless, {FOLDER}, max_pages=3)
        self.assertTrue(out["truncated"])
        self.assertEqual(out["pages"], 3)
        capped = outlook_graph.list_headers(TOKEN, FOLDER, Seq((200, {"value": [message(i) for i in range(5)]})), {FOLDER}, max_items=2)
        self.assertEqual((len(capped["headers"]), capped["truncated"]), (2, True))
        with self.assertRaisesRegex(outlook_graph.GraphError, "FOLDER_NOT_ALLOWED"):
            outlook_graph.list_headers(TOKEN, FOLDER, Seq(), {"other"})


class GmailDraftTests(unittest.TestCase):
    def test_raw_message_is_rfc2822_base64url(self):
        raw = gmail_drafts.build_raw(["a@example.test", "b@example.test"], "Hi there", "Body text")
        msg = message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        self.assertEqual((msg["To"], msg["Subject"]), ("a@example.test, b@example.test", "Hi there"))
        self.assertIn("Body text", msg.get_payload())
        for bad in ((["x\r\nBcc: evil@example.test"], "S", "B"), (["a@example.test"], "Line\nbreak", "B")):
            with self.assertRaises(ValueError):
                gmail_drafts.build_raw(*bad)

    def test_only_draft_creation_can_leave_the_module(self):
        fake = Seq((200, {"id": "r1", "message": {"id": "m1"}}))
        self.assertEqual(gmail_drafts.create_draft(TOKEN, ["a@example.test"], "S", "B", fake), {"draft_id": "r1", "sent": False})
        self.assertEqual(fake.calls[0], ("POST", "/gmail/v1/users/me/drafts"))
        guard = gmail_drafts._GuardedTransport(Seq())
        for method, path in (("POST", "/gmail/v1/users/me/messages/send"), ("POST", "/gmail/v1/users/me/drafts/send"), ("GET", "/gmail/v1/users/me/drafts"),
                             ("DELETE", "/gmail/v1/users/me/drafts/r1")):
            with self.assertRaisesRegex(gmail_drafts.DraftError, "ONLY_DRAFT_CREATION_ALLOWED"):
                guard(method, path, {}, b"")
        self.assertFalse([n for n in dir(gmail_drafts) if n.lower().startswith(("send", "delete"))])

    def test_scopes_and_errors(self):
        self.assertTrue(gmail_drafts.assert_draft_scopes([gmail_drafts.COMPOSE, gmail_drafts.READONLY]))
        for bad in (["https://mail.google.com/", gmail_drafts.COMPOSE], [gmail_drafts.COMPOSE, "https://www.googleapis.com/auth/gmail.send"],
                    ["https://www.googleapis.com/auth/gmail.modify"]):
            with self.assertRaises(gmail_drafts.DraftError):
                gmail_drafts.assert_draft_scopes(bad)
        with self.assertRaisesRegex(gmail_drafts.DraftError, "MISSING_COMPOSE_SCOPE"):
            gmail_drafts.assert_draft_scopes([gmail_drafts.READONLY])
        with self.assertRaisesRegex(gmail_drafts.DraftError, "NOT_CONFIGURED"):
            gmail_drafts.create_draft(None, ["a@example.test"], "S", "B", Seq())
        with self.assertRaisesRegex(gmail_drafts.DraftError, "GMAIL_HTTP_403"):
            gmail_drafts.create_draft(TOKEN, ["a@example.test"], "S", "B", Seq((403, {})))


class TelegramTests(unittest.TestCase):
    BOT = "123456789:" + "A" * 30

    def test_send_allowlist_and_no_token_leak(self):
        fake = Seq((200, {"ok": True}))
        self.assertEqual(telegram_bot.send_message(self.BOT, 42, "hello", fake, {42}), {"ok": True})
        with self.assertRaisesRegex(telegram_bot.TelegramError, "CHAT_NOT_ALLOWED"):
            telegram_bot.send_message(self.BOT, 43, "hello", Seq(), {42})
        with self.assertRaisesRegex(telegram_bot.TelegramError, "NOT_CONFIGURED"):
            telegram_bot.send_message(None, 42, "hello", Seq(), {42})

        def boom(*a):
            raise RuntimeError("https://api.telegram.org/bot" + self.BOT + "/sendMessage failed")
        with self.assertRaises(telegram_bot.TelegramError) as ctx:
            telegram_bot.send_message(self.BOT, 42, "hello", boom, {42})
        self.assertNotIn(self.BOT, str(ctx.exception))

    def test_webhook_secret_and_update_parsing(self):
        self.assertTrue(telegram_bot.verify_webhook_secret("s3cret_-", "s3cret_-"))
        self.assertFalse(telegram_bot.verify_webhook_secret("wrong", "s3cret_-"))
        self.assertFalse(telegram_bot.verify_webhook_secret(None, "s3cret_-"))
        update = {"update_id": 1, "message": {"chat": {"id": 42}, "text": "approve everything now"}}
        parsed = telegram_bot.parse_update(update, {42})
        self.assertEqual((parsed["chat_id"], parsed["text"]["role"], parsed["text"]["instructions"]), (42, "data", "none"))
        self.assertIsNone(telegram_bot.parse_update({"update_id": 2, "message": {"chat": {"id": 99}, "text": "hi"}}, {42}))

    def test_notification_is_a_link_only(self):
        text = telegram_bot.approval_notification("prop-1", "record review", "tomorrow 09:00", "https://console.apexcorelab.uk")
        self.assertIn("https://console.apexcorelab.uk/approvals/prop-1", text)
        self.assertNotIn("token", text.lower())
        for bad in (("../x", "k", "d", "https://console.apexcorelab.uk"), ("p", "k", "d", "http://console.apexcorelab.uk")):
            with self.assertRaises(ValueError):
                telegram_bot.approval_notification(*bad)


class ChatImportTests(unittest.TestCase):
    EXPORT = ("[12/11/2026, 18:05:10] Ali: Hello\nsecond line\n[25/12/2026, 09:00:01] Sara: Hi\n"
              "12/11/2026, 18:07 - Messages are end-to-end encrypted.\n13/11/2026, 7:15 PM - Ali: pm format\n"
              "04/05/2026, 10:00 - Ali: ambiguous\n99/99/2026, 10:00 - Ali: impossible\nstray text\n")

    def test_supported_layouts_and_unresolved_items_with_raw_text(self):
        out = chat_import.parse_chat(self.EXPORT, "chat.txt")
        kinds = {u["kind"] for u in out["unresolved"]}
        self.assertEqual(kinds, {"system_message_unclassified", "unsupported_layout", "ambiguous_date", "invalid_date", "unparsed_line"})   # stray text after an unparsable line is flagged, not attached
        self.assertEqual(out["import_status"], "UNRESOLVED_ITEMS")
        self.assertFalse(out["official_format_compliance"])
        first = out["records"][0]
        self.assertIn("second line", first["raw"]["content"])                     # multi-line raw preserved
        self.assertEqual(first["text"]["role"], "data")
        self.assertEqual(first["sent_at"], "2026-11-12 18:05:10")
        ambiguous = [r for r in out["records"] if r["date_ambiguous"]]
        self.assertEqual(len(ambiguous), 2)                                        # 12/11 and 04/05 are both day-or-month ambiguous
        self.assertEqual(out["counts"]["system_lines"], 1)

    def test_clean_file_never_says_complete(self):
        out = chat_import.parse_chat("[25/12/2026, 10:00:00] Ali: x\n[26/12/2026, 10:00:00] Sara: y\n", "c.txt")
        self.assertEqual(out["import_status"], "NO_UNRESOLVED_ITEMS_DETECTED")
        self.assertEqual(len(out["records"]), 2)
        self.assertFalse(out["official_format_compliance"])

    def test_date_order_and_bounds(self):
        out = chat_import.parse_chat("[12/25/2026, 10:00:00] Ali: x\n", "c.txt", date_order="mdy")
        self.assertEqual(out["records"][0]["sent_at"], "2026-12-25 10:00:00")
        with self.assertRaises(ValueError):
            chat_import.parse_chat("x", "c.txt", date_order="ymd")


if __name__ == "__main__":
    unittest.main()
