"""Cosmetic skincare suggestions from one selfie, on the local model only.

The photo is held in memory for the one call and never written to disk, logged or sent to any
hosted service: if the local model is not enabled this refuses instead of falling back to a
cloud API. The output is general cosmetic guidance from a small model looking at one picture -
not a skin assessment and not medical advice; the prompt forbids naming conditions.
"""
from __future__ import annotations

import base64
import binascii
import time

from . import local_llm
from . import scout_common as common
from .kernel.budget import BudgetDenied  # noqa: F401  (callers catch it)

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_B64 = 5_500_000
SYSTEM = ("The photo is a selfie the owner took of his own face and chose to share. Give general "
          "cosmetic skincare suggestions only: what you can plainly see (for example dryness, shine, "
          "uneven tone, fine lines), then a simple morning and evening routine using common "
          "over-the-counter ingredients such as SPF, a moisturiser, vitamin C or retinol, with one "
          "line on how to start each gently. Do not name or suggest any medical condition and do not "
          "estimate age or attractiveness. If something looks like it needs a professional, say only "
          "'worth showing to a pharmacist or GP'. Under 160 words, plain text, no headings.")


class SkinError(RuntimeError):
    pass


def suggest(budget, image_b64: str, media_type: str, now: float | None = None) -> str:
    if media_type not in IMAGE_TYPES or not isinstance(image_b64, str) or not 100 <= len(image_b64) <= MAX_IMAGE_B64:
        raise ValueError("Unsupported image")
    try:
        base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Unsupported image") from None
    if not local_llm.enabled():
        raise SkinError("LOCAL_MODEL_REQUIRED")
    key = f"skin.{int((time.time() if now is None else now) * 1000)}"
    budget.reserve(key, common.POOL, common.PROVIDER, common.SKU, 1)
    try:
        text = local_llm.chat(SYSTEM, [{"role": "user", "content": "Selfie attached.", "images": [image_b64]}], max_tokens=320)
    except Exception as exc:
        try:
            budget.release(key)
        except Exception:
            pass
        raise SkinError(type(exc).__name__) from None
    budget.settle(key, 1)
    text = " ".join(str(text or "").split())
    if not text:
        raise SkinError("EMPTY_REPLY")
    return text[:1500]
