"""Learn the owner's writing voice from a mail archive (Google Takeout .mbox). Offline, read-only.

Only messages the owner SENT are used: received mail is other people's writing and would teach
the twin the wrong voice. From each sent message the quoted reply text, forwarded blocks and
signature are removed, so what is measured is what the owner actually typed.

Outputs (both in runtime/inbox, private, never committed):
  persona_stats.json    counts by year and language, sentence rhythm, usual greetings/sign-offs
  persona_samples.md    a bounded set of short excerpts used as style samples by persona_twin

What is deliberately NOT done: no message is copied whole, nothing is sent anywhere, no
personality or psychological profile is inferred, and excerpts containing long numbers,
addresses, links, money amounts or any of the owner's red-line terms are skipped.
"""
from __future__ import annotations

import email.utils
import html
import json
import mailbox
import re
from collections import Counter
from email.header import decode_header, make_header
from pathlib import Path

from . import persona_twin

QUOTE_START = re.compile(
    r"^(>|On .{5,120} wrote:|-{2,} ?Original Message ?-{2,}|-{2,} ?Forwarded message ?-{2,}|From: .+|Sent from my |Get Outlook for |"
    r"در تاریخ .{5,80} نوشت|_{5,})", re.I)
SIGNATURE = re.compile(r"^(-- ?|—|Kind regards|Best regards|Regards|Best wishes|Many thanks|Thanks|Thank you|Cheers|Best|Sincerely|"
                       r"Yours sincerely|با احترام|با تشکر|ارادتمند|قربانت|مرسی)[,.! ]*$", re.I)
GREETING = re.compile(r"^(hi|hello|hey|dear|good (morning|afternoon|evening)|سلام|درود)\b[^\n]{0,40}$", re.I)
SENSITIVE = re.compile(r"\d{6,}|\b\d{2}-\d{2}-\d{2}\b|https?://|www\.|\S+@\S+|[£$€]\s?\d|\b(password|passcode|pin|iban|sort code)\b", re.I)
PERSIAN = re.compile(r"[؀-ۿ]")
TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
MAX_BODY = 200_000


def _text(message) -> str:
    """Best plain-text body: the first text/plain part, else text/html with the tags removed."""
    plain, rich = None, None
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_maintype() != "text" or part.get_filename():
            continue
        try:
            raw = part.get_payload(decode=True) or b""
            body = raw[:MAX_BODY].decode(part.get_content_charset() or "utf-8", errors="replace")
        except (LookupError, AttributeError):
            continue
        if part.get_content_subtype() == "plain" and plain is None:
            plain = body
        elif part.get_content_subtype() == "html" and rich is None:
            rich = html.unescape(TAG.sub(" ", re.sub(r"<(br|/p|/div)[^>]*>", "\n", body, flags=re.I)))
    return plain if plain is not None else (rich or "")


def own_words(body: str) -> tuple[str, str, str]:
    """(text the owner typed, greeting line or "", sign-off line or "")."""
    kept, greeting, signoff = [], "", ""
    for line in body.replace("\r", "").split("\n"):
        stripped = line.strip()
        if QUOTE_START.match(stripped):
            break
        if SIGNATURE.match(stripped):
            signoff = re.sub(r"[,.! ]+$", "", stripped).lower()
            break
        if not kept and stripped and GREETING.match(stripped):
            greeting = re.sub(r"[,.! ]+$", "", stripped.split()[0]).lower()
            continue
        kept.append(stripped)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), greeting, signoff


def _addresses(value) -> set[str]:
    try:
        value = str(make_header(decode_header(str(value or ""))))
    except Exception:
        value = str(value or "")
    return {addr.lower() for _, addr in email.utils.getaddresses([value]) if addr}


def analyse(mbox_path: Path, owner_addresses: set[str], since_year: int = 2012, max_samples: int = 60,
            red_lines: tuple[str, ...] = ()) -> tuple[dict, list[str]]:
    owners = {a.lower() for a in owner_addresses}
    if not owners:
        raise ValueError("at least one owner address is required")
    red = [term.lower() for term in red_lines]
    by_year: Counter = Counter()
    by_language: Counter = Counter()
    greetings: Counter = Counter()
    signoffs: Counter = Counter()
    seen = skipped_other = 0
    english_text: list[str] = []
    candidates: dict[int, list[str]] = {}
    box = mailbox.mbox(str(mbox_path), create=False)
    try:
        for message in box:
            seen += 1
            if not (_addresses(message.get("From")) & owners) or message.get("Auto-Submitted", "no").lower() != "no":
                skipped_other += 1
                continue
            try:
                year = email.utils.parsedate_to_datetime(message.get("Date")).year
            except (TypeError, ValueError):
                continue
            if year < since_year:
                continue
            text, greeting, signoff = own_words(_text(message))
            if len(text.split()) < 5:
                continue
            language = "fa" if len(PERSIAN.findall(text)) > 0.3 * len(text.replace(" ", "")) else "en"
            by_year[year] += 1
            by_language[language] += 1
            if greeting:
                greetings[greeting] += 1
            if signoff:
                signoffs[signoff] += 1
            if language == "en" and sum(len(t) for t in english_text) < 2_000_000:
                english_text.append(text)
            for paragraph in text.split("\n\n"):
                words = paragraph.split()
                lowered = paragraph.lower()
                if 15 <= len(words) <= 90 and not SENSITIVE.search(paragraph) and not any(term in lowered for term in red):
                    bucket = candidates.setdefault(year, [])
                    if len(bucket) < 40:
                        bucket.append(" ".join(words))
    finally:
        box.close()
    samples: list[str] = []
    years = sorted(candidates, reverse=True)                      # newest first, spread across years
    index = 0
    while len(samples) < max_samples and any(index < len(candidates[y]) for y in years):
        for year in years:
            if index < len(candidates[year]) and len(samples) < max_samples:
                samples.append(candidates[year][index])
        index += 1
    sig = persona_twin.signature("\n".join(english_text)) if english_text else None
    stats = {
        "messages_in_archive": seen, "sent_by_owner_used": sum(by_year.values()), "not_from_owner": skipped_other,
        "since_year": since_year, "by_year": dict(sorted(by_year.items())), "by_language": dict(by_language),
        "greetings": greetings.most_common(8), "sign_offs": signoffs.most_common(8),
        "english_rhythm": None if sig is None else {"mean_sentence_words": sig.mean_sentence_words, "sentence_words_stdev": sig.sentence_words_stdev,
                                                    "dashes_per_1000_chars": sig.dashes_per_1000_chars,
                                                    "exclamations_per_100_sentences": sig.exclamations_per_100_sentences},
        "samples_kept": len(samples),
    }
    return stats, samples


def write_outputs(root: Path, stats: dict, samples: list[str]) -> tuple[Path, Path]:
    inbox = Path(root) / "runtime" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    stats_path, samples_path = inbox / "persona_stats.json", inbox / "persona_samples.md"
    for path, content in ((stats_path, json.dumps(stats, ensure_ascii=False, indent=2)),
                          (samples_path, "# Style samples taken from mail you sent (generated; safe to delete)\n\n## Samples\n\n" + "\n\n".join(samples) + "\n")):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
    return stats_path, samples_path
