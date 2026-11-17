"""Local model adapter: chat + embeddings from an Ollama server on this machine or LAN.

Switched on with APEX_LLM_PROVIDER=ollama. When it is on, every LLM call in this repo that
goes through apex.agents_research.call_anthropic or scripts/voice_api.call_anthropic is served
by the local model instead, and no Anthropic key is read. Nothing is sent to a public host:
the server URL must be loopback, a private address or a known container name, or the call is
refused before any request is made.

Environment:
  APEX_LLM_PROVIDER     "ollama" to enable (anything else = hosted API, the old behaviour)
  APEX_OLLAMA_URL       default http://127.0.0.1:11434
  APEX_OLLAMA_MODEL     default qwen3:4b   (fits a CPU-only 8 GB machine; see PROJECT_MEMORY.md)
  APEX_OLLAMA_EMBED     default bge-m3     (multilingual; Persian and English)
  APEX_OLLAMA_NUM_CTX   default 8192       (prompt window in tokens; RAM grows with it)
  APEX_OLLAMA_TIMEOUT   default 600        (seconds; CPU inference is slow)

Standard library only (urllib), same as the rest of the project.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

ALLOWED_NAMES = {"localhost", "host.docker.internal", "ollama"}
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)
MAX_EMBED_CHARS = 6000


class LocalLLMError(RuntimeError):
    pass


def enabled() -> bool:
    return os.environ.get("APEX_LLM_PROVIDER", "").strip().lower() == "ollama"


def model() -> str:
    return os.environ.get("APEX_OLLAMA_MODEL", "qwen3:4b")


def embed_model() -> str:
    return os.environ.get("APEX_OLLAMA_EMBED", "bge-m3")


def base_url() -> str:
    url = os.environ.get("APEX_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        raise LocalLLMError("LOCAL_URL_INVALID")
    if host not in ALLOWED_NAMES:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise LocalLLMError("LOCAL_URL_NOT_PRIVATE") from None
        if not (address.is_loopback or address.is_private):
            raise LocalLLMError("LOCAL_URL_NOT_PRIVATE")
    return url


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(os.environ.get(name, default)), high))
    except ValueError:
        return default


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(base_url() + path, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_int_env("APEX_OLLAMA_TIMEOUT", 600, 5, 3600)) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise LocalLLMError(f"LOCAL_MODEL_ERROR:{exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise LocalLLMError("LOCAL_MODEL_UNREACHABLE") from None
    except ValueError:
        raise LocalLLMError("LOCAL_MODEL_BAD_RESPONSE") from None


def chat(system: str, messages: list, max_tokens: int = 400) -> str:
    """messages: [{"role": "user"|"assistant", "content": str}, ...]. Returns the reply text."""
    body = {
        "model": model(), "stream": False,
        # Thinking off: at the small max_tokens values used here a reasoning model can spend the
        # whole budget thinking and return no visible text (the same failure agents_research.py
        # documents for the hosted API).
        "think": False,
        "messages": ([{"role": "system", "content": system}] if system else []) + list(messages),
        "options": {"num_predict": int(max_tokens), "temperature": 0.2,
                    "num_ctx": _int_env("APEX_OLLAMA_NUM_CTX", 8192, 2048, 262144)},
    }
    data = _post("/api/chat", body)
    try:
        text = data["message"]["content"]
    except (KeyError, TypeError):
        raise LocalLLMError("LOCAL_MODEL_BAD_RESPONSE") from None
    text = THINK_BLOCK.sub("", text or "").strip()
    if not text:
        raise LocalLLMError("LOCAL_MODEL_EMPTY_REPLY")
    return text


def complete(system: str, user_text: str, max_tokens: int = 400) -> str:
    return chat(system, [{"role": "user", "content": user_text}], max_tokens)


def embed(texts: list) -> list:
    """One float vector per input string."""
    if not texts:
        return []
    data = _post("/api/embed", {"model": embed_model(), "input": [str(t)[:MAX_EMBED_CHARS] for t in texts]})
    vectors = data.get("embeddings") if isinstance(data, dict) else None
    if (not isinstance(vectors, list) or len(vectors) != len(texts)
            or not all(isinstance(v, list) and v for v in vectors)):
        raise LocalLLMError("LOCAL_EMBED_BAD_RESPONSE")
    return vectors
