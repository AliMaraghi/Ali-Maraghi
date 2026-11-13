"""A-19 YouTube: read-only channel analytics snapshot, saved to the existing Ledger. Status: TESTS_NOT_RUN, NOT_CONNECTED.

Uses the already-reviewed core/apex/youtube_stats.py (GET /youtube/v3/channels, youtube.readonly
scope only - see that module's docstring for the exact verified API details and its REFUSED set
of write/upload-capable scopes). This file adds nothing new to what can be called; it only adds
where the result is stored (a dedicated Ledger table) and how the token is supplied.

No OAuth consent flow is implemented here (that is a separate, larger piece - see
core/apex/google_oauth_state.py/google_tokens.py for the pattern an owner-facing consent flow
would reuse, currently scoped to Gmail only). Instead this reads a pre-obtained access token from
a protected file, the same pattern already used for /etc/apex/anthropic-key:

  Setup (run once, after creating an OAuth client in Google Cloud Console with the
  `https://www.googleapis.com/auth/youtube.readonly` scope and obtaining a token - e.g. via
  Google's OAuth 2.0 Playground, https://developers.google.com/oauthplayground, using your own
  client ID/secret so the token is issued to an app you control):
    sudo install -d -m 0755 /etc/apex
    sudo sh -c 'cat > /etc/apex/youtube-token.json && chmod 600 /etc/apex/youtube-token.json && chown apexdev:apexdev /etc/apex/youtube-token.json'
    (paste {"access_token": "...", "expires_at": 1234567890} then Ctrl-D)

  When the token expires, this script fails closed (YOUTUBE_TOKEN_EXPIRED) rather than guessing a
  refresh - refresh the file manually. A fuller refresh-token flow is future work, not this file.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import youtube_stats
from .social_snapshots import validate_row

TOKEN_FILE = Path("/etc/apex/youtube-token.json")


class YouTubeAgentError(RuntimeError):
    pass


def load_token() -> str:
    if not TOKEN_FILE.is_file():
        raise YouTubeAgentError(f"{TOKEN_FILE} not found - see setup steps in this file's docstring")
    mode = TOKEN_FILE.stat().st_mode & 0o777
    if mode & 0o077:
        raise YouTubeAgentError(f"{TOKEN_FILE} must not be group/world readable (chmod 600)")
    try:
        data = json.loads(TOKEN_FILE.read_text())
    except json.JSONDecodeError:
        raise YouTubeAgentError("Invalid token file") from None
    token, expires_at = data.get("access_token"), data.get("expires_at")
    if not isinstance(token, str) or not token:
        raise YouTubeAgentError("Invalid token file")
    if not isinstance(expires_at, (int, float)) or expires_at <= time.time():
        raise YouTubeAgentError("YOUTUBE_TOKEN_EXPIRED")
    return token


def run_snapshot(ledger, transport=None) -> list:
    """Fetch today's channel statistics and append them to the Ledger. Read-only end to end:
    no upload/publish/comment call exists anywhere in this path (youtube_stats.py's HOST+PATH
    are fixed constants, GET only)."""
    ledger.db.execute("""
        CREATE TABLE IF NOT EXISTS social_snapshots (
          seq INTEGER PRIMARY KEY, platform TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL,
          account_label TEXT NOT NULL, metrics_json TEXT NOT NULL, created_at REAL NOT NULL)
    """)
    token = load_token()
    today = time.strftime("%Y-%m-%d", time.gmtime())
    rows = youtube_stats.fetch_channel_snapshots(token, today, transport or youtube_stats.live_transport)
    now = time.time()
    for row in rows:
        validated = validate_row({k: row[k] for k in ("platform", "date", "source", "account_label", "metrics")})
        ledger.db.execute(
            "INSERT INTO social_snapshots (platform, date, source, account_label, metrics_json, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (validated["platform"], validated["date"], validated["source"], validated["account_label"],
             json.dumps(validated["metrics"]), now))
    return rows


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
    from apex.kernel.memory import Ledger
    root = Path(__file__).resolve().parents[2]
    try:
        with Ledger(root) as ledger:
            saved = run_snapshot(ledger)
        print(json.dumps({"saved": len(saved)}))
    except YouTubeAgentError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
