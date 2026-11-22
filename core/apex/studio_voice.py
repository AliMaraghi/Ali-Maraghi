"""Narration for the content factory: OpenAI's speech endpoint, one request per script line, so each line's real
audio length times its shot (sentence-level timing; no word timestamps are claimed).

The key is the owner's own, typed into his dashboard and kept in a private file. Spend is admitted through the existing
Budget (studio pool) before any call, and separately held under a voice-only monthly cap. The speech response carries
no usage figure, so cost is a deliberately high per-character estimate, settled as reserved.

Checked 22 Nov 2026 against developers.openai.com: POST /v1/audio/speech, models gpt-4o-mini-tts / tts-1; both are
marked deprecated with shutdown on 6 Jan 2027, so this adapter will need a successor model before then.
There is no free fallback: edge-tts drives Microsoft's consumer read-aloud service without a licence for published
commercial audio, so it is not used. Without a key or budget the film stays a silent draft.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://api.openai.com/v1/audio/speech"
MODEL, VOICE = "gpt-4o-mini-tts", "coral"
PROVIDER, SKU = "openai", "tts-char"
PRICE_MILLIPENCE_PER_CHAR = 5                                       # estimate, about twice the published per-minute average
VOICE_MONTHLY_CAP_PENCE = 500
KEY_SHAPE = re.compile(r"sk-[A-Za-z0-9_\-]{20,200}")
LANGUAGES = ("en", "es", "pt", "ar", "fr", "de", "hi", "ja", "ko", "fa")


class VoiceUnavailable(Exception):
    """Narration cannot be produced; the code says why. The caller falls back to a silent draft."""


def key_path(root) -> Path:
    return Path(root) / "runtime" / "inbox" / "openai-key"


def save_key(root, key) -> None:
    if not isinstance(key, str) or not KEY_SHAPE.fullmatch(key.strip()):
        raise ValueError("Not an OpenAI API key")
    path = key_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w") as out:
        out.write(key.strip() + "\n")
    os.chmod(path, 0o600)


def load_key(root):
    try:
        key = key_path(root).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return key if KEY_SHAPE.fullmatch(key) else None


def estimate_pence(chars: int) -> int:
    return -(-chars * PRICE_MILLIPENCE_PER_CHAR // 1000)


def admit(ledger, job_id: str, chars: int, now: float) -> str:
    """Reserve the estimated spend. Raises VoiceUnavailable when either cap would be passed."""
    from .kernel.budget import Budget, BudgetDenied
    budget = Budget(ledger)
    month = __import__("time").strftime("%Y-%m", __import__("time").gmtime(now))
    spent = ledger.db.execute("SELECT COALESCE(SUM(reserved_minor),0) FROM budget_reservations WHERE provider=? AND state!='RELEASED' "
                              "AND strftime('%Y-%m', created_at, 'unixepoch')=?", (PROVIDER, month)).fetchone()[0]
    if spent + estimate_pence(chars) > VOICE_MONTHLY_CAP_PENCE:
        raise VoiceUnavailable("VOICE_MONTHLY_CAP_REACHED")
    try:
        budget.price(PROVIDER, SKU, now)
    except BudgetDenied:
        budget.set_price(PROVIDER, SKU, PRICE_MILLIPENCE_PER_CHAR, now - 1, "estimate from OpenAI published TTS pricing, owner-authorised 22 Nov 2026")
    key = ("tts-" + job_id)[:48]
    try:
        budget.reserve(key, "studio", PROVIDER, SKU, chars)
    except BudgetDenied as exc:
        raise VoiceUnavailable("BUDGET_DENIED: " + str(exc)[:80])
    return key


def speak(api_key: str, text: str, language: str, out_path: Path, post=None) -> None:
    """One line of narration to a WAV file. post(url, headers, body) -> bytes is injectable for tests."""
    body = json.dumps({"model": MODEL, "voice": VOICE, "input": text, "response_format": "wav",
                       "instructions": f"Clear, warm documentary narration in language code {language}. Natural pace."}).encode()
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    if post is None:
        def post(url, headers, body):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method="POST"), timeout=40) as resp:
                    return resp.read(20_000_000)
            except urllib.error.HTTPError as exc:
                raise VoiceUnavailable({401: "AUTH_REQUIRED: the OpenAI key was rejected", 429: "RATE_LIMITED_OR_NO_CREDIT"}.get(exc.code, f"PROVIDER_HTTP_{exc.code}"))
            except (urllib.error.URLError, TimeoutError):
                raise VoiceUnavailable("PROVIDER_UNREACHABLE")
    audio = post(ENDPOINT, headers, body)
    if not isinstance(audio, bytes) or audio[:4] != b"RIFF" or len(audio) < 2000:
        raise VoiceUnavailable("PROVIDER_RETURNED_NO_AUDIO")
    out_path.write_bytes(audio)
