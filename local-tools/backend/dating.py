"""Dating opener generator: paste a profile's text, get 3 respectful draft openers.

No browser, no login, no platform account, no automation of any dating app - this only ever
reads text pasted into this form and returns text. The person copies whichever draft (if any)
they want and sends it themselves, from their own device, inside the dating app. Nothing here
ever touches a dating platform's network, account, or Terms of Service surface.
"""
from __future__ import annotations

from anthropic_client import call

MAX_PROFILE_CHARS = 2000
TONE = ("Write 3 short, unique, respectful opening messages for a dating-app profile, based "
        "only on what the profile text below actually says - no generic pickup lines, no "
        "fabricated shared interests, nothing that assumes consent to anything beyond a first "
        "message. Number them 1/2/3, one line each.")


def generate_openers(profile_text: str) -> str:
    profile_text = (profile_text or "").strip()[:MAX_PROFILE_CHARS]
    if not profile_text:
        raise ValueError("Profile text is empty")
    return call(TONE, f"Profile:\n{profile_text}", max_tokens=200)
