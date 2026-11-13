"""A-19 YouTube agent: token loading, snapshot persistence to the Ledger, read-only end to end."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from apex import youtube_agent
from apex.kernel.memory import Ledger

TOKEN = "t" * 40


class Fake:
    def __init__(self, body, status=200):
        self.body, self.status, self.calls = body, status, []

    def __call__(self, method, path, headers):
        self.calls.append((method, path, headers))
        return self.status, "application/json", json.dumps(self.body).encode()


def channel():
    return {"items": [{"id": "UCabcdefghij1234",
                        "statistics": {"viewCount": "1000", "subscriberCount": "1500",
                                        "hiddenSubscriberCount": False, "videoCount": "12"}}]}


class YouTubeAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_missing_token_file_is_a_clear_error(self):
        with mock.patch.object(youtube_agent, "TOKEN_FILE", Path("/nonexistent/youtube-token.json")):
            with self.assertRaises(youtube_agent.YouTubeAgentError):
                youtube_agent.load_token()

    def test_expired_token_fails_closed(self):
        token_path = self.root / "youtube-token.json"
        token_path.write_text(json.dumps({"access_token": TOKEN, "expires_at": time.time() - 10}))
        token_path.chmod(0o600)
        with mock.patch.object(youtube_agent, "TOKEN_FILE", token_path):
            with self.assertRaisesRegex(youtube_agent.YouTubeAgentError, "YOUTUBE_TOKEN_EXPIRED"):
                youtube_agent.load_token()

    def test_group_readable_token_file_is_refused(self):
        token_path = self.root / "youtube-token.json"
        token_path.write_text(json.dumps({"access_token": TOKEN, "expires_at": time.time() + 3600}))
        token_path.chmod(0o640)
        with mock.patch.object(youtube_agent, "TOKEN_FILE", token_path):
            with self.assertRaises(youtube_agent.YouTubeAgentError):
                youtube_agent.load_token()

    def test_snapshot_saved_read_only_and_is_queryable(self):
        token_path = self.root / "youtube-token.json"
        token_path.write_text(json.dumps({"access_token": TOKEN, "expires_at": time.time() + 3600}))
        token_path.chmod(0o600)
        fake = Fake(channel())
        with mock.patch.object(youtube_agent, "TOKEN_FILE", token_path):
            rows = youtube_agent.run_snapshot(self.ledger, transport=fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(fake.calls[0][0], "GET")  # never POST/PUT - no upload path exists
        saved = self.ledger.db.execute(
            "SELECT platform, account_label, metrics_json FROM social_snapshots").fetchall()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][0], "youtube")
        self.assertEqual(json.loads(saved[0][2])["followers"], 1500)

    def test_no_token_means_no_call_and_no_row(self):
        with mock.patch.object(youtube_agent, "TOKEN_FILE", Path("/nonexistent/youtube-token.json")):
            with self.assertRaises(youtube_agent.YouTubeAgentError):
                youtube_agent.run_snapshot(self.ledger, transport=Fake(channel()))
        self.assertEqual(
            self.ledger.db.execute("SELECT COUNT(*) FROM social_snapshots").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
