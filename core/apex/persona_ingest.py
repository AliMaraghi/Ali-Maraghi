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


# ---- chat archives: WhatsApp "Export chat" (.txt or .zip) and Instagram/Facebook message JSON ----
# Same rule as mail: only what the OWNER wrote is read. Other people's messages are skipped
# line by line and never stored, counted by name or sampled.
import io
import zipfile
from datetime import datetime

WA_LINE = re.compile(
    r"^‎?\[?(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4}),? (\d{1,2}):(\d{2})(?::\d{2})?(?:\s?[APap]\.?[Mm]\.?)?\]?(?: -)? ([^:]{1,60}): (.*)$")
WA_SKIP = re.compile(r"<Media omitted>|omitted$|^This message was deleted|^You deleted this message|^Missed (voice|video) call|"
                     r"^‎|^(image|video|audio|sticker|GIF|document) omitted|<attached:|^null$|^Messages and calls are end-to-end", re.I)
MAX_ARCHIVE_MEMBER = 80 * 1024 * 1024


def _whatsapp_turns(text: str, owner_names: set[str]):
    """Yields (year, text) for each run of consecutive owner messages (one 'turn')."""
    year, parts, mine, day = None, [], False, None
    for line in text.replace("\r", "").split("\n"):
        match = WA_LINE.match(line)
        if match:
            sender = match.group(6).strip().lower()
            is_owner = sender in owner_names
            this_day = match.group(1, 2, 3)
            if parts and not (is_owner and mine and this_day == day):       # someone else spoke, or a new day began
                yield year, " ".join(parts)
                parts = []
            mine, day = is_owner, this_day
            body = match.group(7).strip()
            if is_owner and body and not WA_SKIP.search(body):
                raw_year = int(match.group(3))
                year = raw_year + 2000 if raw_year < 100 else raw_year
                parts.append(body)
        elif mine and parts and line.strip() and not WA_SKIP.search(line):
            parts.append(line.strip())                         # continuation of the owner's own multi-line message
    if parts:
        yield year, " ".join(parts)


def _fix_meta(text: str) -> str:
    """Meta exports store UTF-8 as Latin-1 escapes; undo that when it applies."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _meta_turns(raw: bytes, owner_names: set[str]):
    try:
        data = json.loads(raw)
    except ValueError:
        return
    messages = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list):
        return
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            continue
        if _fix_meta(str(message.get("sender_name", ""))).strip().lower() not in owner_names:
            continue
        try:
            year = datetime.utcfromtimestamp(int(message.get("timestamp_ms", 0)) / 1000).year
        except (ValueError, OverflowError, OSError):
            continue
        yield year, _fix_meta(message["content"]).strip()


def _members(path: Path):
    """(name, bytes) for each readable chat file under a file, folder or .zip. Nothing is extracted to disk."""
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink())
    for file in files:
        suffix = file.suffix.lower()
        if suffix in (".txt", ".json") and file.stat().st_size <= MAX_ARCHIVE_MEMBER:
            yield file.name, file.read_bytes()
        elif suffix == ".zip":
            try:
                with zipfile.ZipFile(file) as archive:
                    for info in archive.infolist():
                        if info.filename.lower().endswith((".txt", ".json")) and 0 < info.file_size <= MAX_ARCHIVE_MEMBER:
                            yield info.filename, archive.read(info)
            except (zipfile.BadZipFile, OSError):
                continue


def analyse_chats(path: Path, owner_names: set[str], since_year: int = 2012, max_samples: int = 60,
                  red_lines: tuple[str, ...] = ()) -> tuple[dict, list[str]]:
    owners = {n.strip().lower() for n in owner_names if n.strip()}
    if not owners:
        raise ValueError("at least one owner display name is required (exactly as it appears in the export)")
    red = [term.lower() for term in red_lines]
    by_year: Counter = Counter()
    by_language: Counter = Counter()
    files = turns = 0
    lengths: list[int] = []
    candidates: dict[int, list[str]] = {}
    for name, raw in _members(Path(path)):
        source = _meta_turns(raw, owners) if name.lower().endswith(".json") else _whatsapp_turns(raw.decode("utf-8", errors="replace"), owners)
        found = False
        for year, text in source:
            if not year or year < since_year or not text:
                continue
            found = True
            turns += 1
            words = text.split()
            lengths.append(len(words))
            by_year[year] += 1
            by_language["fa" if len(PERSIAN.findall(text)) > 0.3 * len(text.replace(" ", "")) else "en"] += 1
            lowered = text.lower()
            if 8 <= len(words) <= 70 and not SENSITIVE.search(text) and not any(term in lowered for term in red):
                bucket = candidates.setdefault(year, [])
                if len(bucket) < 40:
                    bucket.append(" ".join(words))
        files += 1 if found else 0
    samples: list[str] = []
    years, index = sorted(candidates, reverse=True), 0
    while len(samples) < max_samples and any(index < len(candidates[y]) for y in years):
        for year in years:
            if index < len(candidates[year]) and len(samples) < max_samples:
                samples.append(candidates[year][index])
        index += 1
    stats = {"chat_files_with_your_messages": files, "your_turns_used": turns, "since_year": since_year,
             "by_year": dict(sorted(by_year.items())), "by_language": dict(by_language),
             "median_words_per_turn": sorted(lengths)[len(lengths) // 2] if lengths else 0, "samples_kept": len(samples)}
    return stats, samples


def write_chat_outputs(root: Path, stats: dict, samples: list[str]) -> tuple[Path, Path]:
    inbox = Path(root) / "runtime" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    stats_path, samples_path = inbox / "persona_stats_chat.json", inbox / "persona_samples_chat.md"
    for path, content in ((stats_path, json.dumps(stats, ensure_ascii=False, indent=2)),
                          (samples_path, "# Chat-register samples from messages you sent (generated; safe to delete)\n\n## Samples\n\n" + "\n\n".join(samples) + "\n")):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
    return stats_path, samples_path
