"""Minimal Anthropic Messages API client - no SDK dependency, stdlib urllib only.

Keeps the one real fix discovered in the parent project (2026-11-13): claude-haiku-5-5 emits
an internal "thinking" block by default, which at short max_tokens values consumes the entire
budget with no visible text left over. Thinking is disabled outright for these short, simple
tool calls - none of them need extended reasoning.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")


class AnthropicError(RuntimeError):
    pass


def load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise AnthropicError("ANTHROPIC_API_KEY is not set - put it in your .env file.")
    return key


def call(system: str, user_text: str, max_tokens: int = 300) -> str:
    api_key = load_api_key()
    payload = json.dumps({
        "model": MODEL, "max_tokens": max_tokens, "system": system,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": user_text}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise AnthropicError(f"Anthropic API error {exc.code}") from None
    except urllib.error.URLError as exc:
        raise AnthropicError(f"Could not reach Anthropic API: {exc.reason}") from None
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block["text"]
    raise AnthropicError("Anthropic response had no text content")
