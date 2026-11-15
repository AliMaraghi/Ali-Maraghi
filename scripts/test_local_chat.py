"""Localhost chat + memory, real pipeline, zero cost (mission 2026-11-15). Tests the REAL
scripts/voice_api.py WSGI app in-process - same WSGI-calling convention as
tests/test_console_server.py - not a mock, not a new parallel backend. Uses a locally-
handled intent ("system status") so no Anthropic API call and no spend happens; a real LLM
call path exists in voice_api.py but is intentionally not exercised by an automated test
that could otherwise spend real money against a real budget cap.
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import voice_api  # noqa: E402


def post_chat(app, text, session_id=None):
    body = json.dumps({"text": text, **({"session_id": session_id} if session_id else {})}).encode()
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {"PATH_INFO": "/api/chat", "REQUEST_METHOD": "POST",
              "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
    result = app(environ, start_response)
    return captured, json.loads(b"".join(result))


class LocalChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = voice_api.VoiceChatApp(Path(self.tmp.name))

    def tearDown(self):
        self.app.ledger.close()
        self.tmp.cleanup()

    def test_locally_handled_status_query_gets_a_real_response_no_llm_call(self):
        captured, data = post_chat(self.app, "system status", session_id="test-session")
        self.assertTrue(captured["status"].startswith("200"))
        self.assertIn("reply", data)
        self.assertEqual(data["intent"], "SYSTEM_STATUS")

    def test_the_turn_is_actually_persisted_to_the_real_sqlite_ledger(self):
        """The mission's own required assertion: the text is saved in SQLite - checked by
        querying the real voice_turns table this app just wrote to, not by trusting the
        HTTP response alone."""
        post_chat(self.app, "system status", session_id="memory-test-session")
        rows = self.app.ledger.db.execute(
            "SELECT role, content FROM voice_turns WHERE session=? ORDER BY seq", ("memory-test-session",)
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ("user", "system status"))
        self.assertEqual(rows[1][0], "assistant")

    def test_history_is_recalled_on_a_second_call_same_session(self):
        post_chat(self.app, "system status", session_id="history-session")
        history_before = self.app._history("history-session")
        self.assertEqual(len(history_before), 2)
        post_chat(self.app, "system status", session_id="history-session")
        history_after = self.app._history("history-session")
        self.assertEqual(len(history_after), 4)

    def test_malformed_body_is_a_clean_400_not_a_crash(self):
        environ = {"PATH_INFO": "/api/chat", "REQUEST_METHOD": "POST",
                  "CONTENT_LENGTH": "9", "wsgi.input": io.BytesIO(b"not json!")}
        captured = {}
        self.app(environ, lambda status, headers: captured.update(status=status))
        self.assertTrue(captured["status"].startswith("400"))


if __name__ == "__main__":
    unittest.main()
