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

    def test_academic_latest_is_a_real_fresh_fetch_free_no_llm(self):
        import orchestrator
        rss_xml = (b"<?xml version='1.0'?><rss version='2.0'><channel>"
                   b"<item><title>Real Live Paper Title</title><link>https://arxiv.org/abs/1</link></item>"
                   b"</channel></rss>")
        orig = orchestrator.academic_latest_titles
        orchestrator.academic_latest_titles = lambda root, fetch=None, limit=10: orig(
            root, fetch=lambda url: rss_xml, limit=limit)
        try:
            captured = {}
            environ = {"PATH_INFO": "/api/academic/latest", "REQUEST_METHOD": "GET"}
            result = self.app(environ, lambda status, headers: captured.update(status=status))
            data = json.loads(b"".join(result))
        finally:
            orchestrator.academic_latest_titles = orig
        self.assertTrue(captured["status"].startswith("200"))
        self.assertEqual(data["titles"][0]["title"], "Real Live Paper Title")

    def test_academic_latest_wrong_method_is_405(self):
        captured = {}
        environ = {"PATH_INFO": "/api/academic/latest", "REQUEST_METHOD": "POST"}
        self.app(environ, lambda status, headers: captured.update(status=status))
        self.assertTrue(captured["status"].startswith("405"))

    def test_dating_draft_empty_body_is_400(self):
        body = json.dumps({"profile_text": "  "}).encode()
        environ = {"PATH_INFO": "/api/dating/draft", "REQUEST_METHOD": "POST",
                  "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        captured = {}
        self.app(environ, lambda status, headers: captured.update(status=status))
        self.assertTrue(captured["status"].startswith("400"))

    def test_dating_draft_zero_budget_by_default_is_402_nothing_spent(self):
        # No price/cap configured on this fresh ledger -> BudgetDenied, same as the voice path.
        body = json.dumps({"profile_text": "Loves hiking and board games."}).encode()
        environ = {"PATH_INFO": "/api/dating/draft", "REQUEST_METHOD": "POST",
                  "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        captured = {}
        result = self.app(environ, lambda status, headers: captured.update(status=status))
        data = json.loads(b"".join(result))
        self.assertTrue(captured["status"].startswith("402"))
        self.assertIn("BUDGET_DENIED", data["error"])

    def test_dating_draft_real_generation_once_priced(self):
        import time
        from apex.kernel.budget import Budget
        import dating_agent
        self.app.budget.set_price("anthropic", "dating-draft-step", 100, time.time(), "test")
        self.app.budget.set_cap("core", "day", 1000)
        orig = dating_agent.generate_openers
        dating_agent.generate_openers = lambda budget, text: "1. Hi\n2. Hey\n3. Hello"
        try:
            body = json.dumps({"profile_text": "Loves hiking."}).encode()
            environ = {"PATH_INFO": "/api/dating/draft", "REQUEST_METHOD": "POST",
                      "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
            captured = {}
            result = self.app(environ, lambda status, headers: captured.update(status=status))
            data = json.loads(b"".join(result))
        finally:
            dating_agent.generate_openers = orig
        self.assertTrue(captured["status"].startswith("200"))
        self.assertIn("drafts", data)

    def test_banking_parse_invalid_csv_is_400_no_budget_touched(self):
        body = json.dumps({"csv_text": "not,a,real,statement"}).encode()
        environ = {"PATH_INFO": "/api/banking/parse", "REQUEST_METHOD": "POST",
                  "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        captured = {}
        result = self.app(environ, lambda status, headers: captured.update(status=status))
        data = json.loads(b"".join(result))
        self.assertTrue(captured["status"].startswith("400"))
        self.assertIn("CSV_PARSE_ERROR", data["error"])

    def test_banking_parse_zero_budget_by_default_is_402(self):
        csv_text = "Date,Description,Amount\n2026-11-01,TESCO,-10.00\n"
        body = json.dumps({"csv_text": csv_text}).encode()
        environ = {"PATH_INFO": "/api/banking/parse", "REQUEST_METHOD": "POST",
                  "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        captured = {}
        result = self.app(environ, lambda status, headers: captured.update(status=status))
        data = json.loads(b"".join(result))
        self.assertTrue(captured["status"].startswith("402"))
        self.assertIn("BUDGET_DENIED", data["error"])

    def test_banking_parse_real_categorization_once_priced(self):
        import time
        import banking_csv
        self.app.budget.set_price("anthropic", "banking-csv-categorize-step", 100, time.time(), "test")
        self.app.budget.set_cap("core", "day", 1000)
        orig = banking_csv.categorize
        banking_csv.categorize = lambda call_anthropic, api_key, transactions: {
            "totals_pence": {"Groceries": -1000}, "transaction_count": 1, "uncategorized_count": 0}
        try:
            csv_text = "Date,Description,Amount\n2026-11-01,TESCO,-10.00\n"
            body = json.dumps({"csv_text": csv_text}).encode()
            environ = {"PATH_INFO": "/api/banking/parse", "REQUEST_METHOD": "POST",
                      "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
            captured = {}
            result = self.app(environ, lambda status, headers: captured.update(status=status))
            data = json.loads(b"".join(result))
        finally:
            banking_csv.categorize = orig
        self.assertTrue(captured["status"].startswith("200"))
        self.assertEqual(data["totals_pence"]["Groceries"], -1000)

    def test_dating_bulk_queue_rejects_more_than_ten(self):
        body = json.dumps({"bios": ["x"] * 11}).encode()
        environ = {"PATH_INFO": "/api/dating/bulk_queue", "REQUEST_METHOD": "POST",
                  "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        captured = {}
        self.app(environ, lambda status, headers: captured.update(status=status))
        self.assertTrue(captured["status"].startswith("400"))

    def test_dating_bulk_queue_one_failure_does_not_hide_the_others(self):
        import dating_agent
        orig = dating_agent.generate_openers
        calls = {"n": 0}

        def fake(budget, text):
            calls["n"] += 1
            if calls["n"] == 1:
                return "1. Hi\n2. Hey\n3. Hello"
            raise dating_agent.ResearchPipelineError("boom")
        dating_agent.generate_openers = fake
        try:
            body = json.dumps({"bios": ["Loves hiking.", "Loves climbing."]}).encode()
            environ = {"PATH_INFO": "/api/dating/bulk_queue", "REQUEST_METHOD": "POST",
                      "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
            captured = {}
            result = self.app(environ, lambda status, headers: captured.update(status=status))
            data = json.loads(b"".join(result))
        finally:
            dating_agent.generate_openers = orig
        self.assertTrue(captured["status"].startswith("200"))
        self.assertEqual(len(data["results"]), 2)
        self.assertIsNone(data["results"][0]["error"])
        self.assertIsNotNone(data["results"][1]["error"])

    def test_wealth_analyze_empty_text_is_400(self):
        body = json.dumps({"portfolio_text": "  "}).encode()
        environ = {"PATH_INFO": "/api/wealth/analyze", "REQUEST_METHOD": "POST",
                  "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        captured = {}
        self.app(environ, lambda status, headers: captured.update(status=status))
        self.assertTrue(captured["status"].startswith("400"))

    def test_wealth_analyze_zero_budget_by_default_is_402(self):
        body = json.dumps({"portfolio_text": "£10,000 in savings"}).encode()
        environ = {"PATH_INFO": "/api/wealth/analyze", "REQUEST_METHOD": "POST",
                  "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        captured = {}
        result = self.app(environ, lambda status, headers: captured.update(status=status))
        data = json.loads(b"".join(result))
        self.assertTrue(captured["status"].startswith("402"))
        self.assertIn("BUDGET_DENIED", data["error"])

    def test_wealth_analyze_real_result_once_priced(self):
        import time
        from apex import wealth_engine
        self.app.budget.set_price("anthropic", "wealth-analysis-step", 100, time.time(), "test")
        self.app.budget.set_cap("core", "day", 1000)
        orig = wealth_engine.propose_action
        wealth_engine.propose_action = lambda budget, ledger, text, *a, **k: {
            "action": "Move £4,000 into a Stocks & Shares ISA", "reasoning": "Unused allowance.",
            "disclaimer": wealth_engine.DISCLAIMER}
        try:
            body = json.dumps({"portfolio_text": "£10,000 in savings"}).encode()
            environ = {"PATH_INFO": "/api/wealth/analyze", "REQUEST_METHOD": "POST",
                      "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
            captured = {}
            result = self.app(environ, lambda status, headers: captured.update(status=status))
            data = json.loads(b"".join(result))
        finally:
            wealth_engine.propose_action = orig
        self.assertTrue(captured["status"].startswith("200"))
        self.assertEqual(data["disclaimer"], wealth_engine.DISCLAIMER)


if __name__ == "__main__":
    unittest.main()
