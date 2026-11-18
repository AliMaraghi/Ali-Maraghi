"""Persona twin and Constitutional Critic: a deterministic pre-publication check on any draft.

The owner's style lives in runtime/inbox/persona_style.md (never committed; see
docs/persona_style.example.md for the format). From it this module builds a linguistic
signature (sentence length, rhythm, punctuation habits, spelling) and a list of hard boundaries.

`review()` is pure code - no model call - so it cannot be talked out of a finding:
  BLOCK    the draft contains something the owner said must never be disclosed, or an
           account/sort-code shaped number. Never auto-fixed; a person has to look.
  REWRITE  AI tropes or cliches, American spelling, or cadence far from the owner's samples.
  PASS     nothing found. PASS means "no known problem", not "this sounds like the owner".

`rewrite_until_pass()` may ask a model to redraft against the findings, but the same review
decides the result, and a BLOCK is never sent to a model for another try.
"""
from __future__ import annotations

import os
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

STYLE_FILE = ("runtime", "inbox", "persona_style.md")
AI_TROPES: tuple[str, ...] = (
    r"\bdelv(e|es|ing)\b", r"\btapestry\b", r"\btestament to\b", r"\bgame[- ]changer\b",
    r"\bin today'?s (fast[- ]paced|digital|ever[- ]changing) (world|landscape|age)\b",
    r"\bunlock(s|ing)? (the|your|its) (full )?potential\b", r"\bseamless(ly)?\b", r"\brobust\b",
    r"\bleverag(e|es|ing)\b", r"\bnavigat(e|ing) the (complex|ever)", r"\bat the end of the day\b",
    r"\bit'?s not (just|only) [^.]{1,60}[,;] it'?s\b", r"\bnot only [^.]{1,60} but also\b",
    r"\bi hope this (message|email|note) finds you well\b", r"\bas an ai\b", r"\blet'?s dive in\b",
    r"\bmoreover,|\bfurthermore,|\bin conclusion,|\bin summary,", r"\bembark(s|ing)? on\b",
    r"\bever[- ]evolving\b", r"\bthought leader", r"\bsynerg", r"\bparadigm shift\b",
    r"\bthrilled to (announce|share)\b", r"\bhumbled\b", r"\bexcited to share\b",
)
AMERICAN_TO_BRITISH: dict[str, str] = {
    "color": "colour", "favorite": "favourite", "organize": "organise", "organization": "organisation",
    "realize": "realise", "analyze": "analyse", "center": "centre", "behavior": "behaviour",
    "program": "programme", "traveling": "travelling", "defense": "defence", "license": "licence",
    "apologize": "apologise", "recognize": "recognise", "honor": "honour", "neighbor": "neighbour",
}
SENSITIVE_NUMBER = re.compile(r"\b\d{2}-\d{2}-\d{2}\b|\b\d{8}\b|\b(?:\d[ -]?){13,19}\b")
SENTENCE = re.compile(r"[^.!?\n]+[.!?]+|[^.!?\n]+$")
MAX_DRAFT_CHARS = 20_000
FLAG = "ENABLE_PERSONA_TWIN"
# Data classes (core/apex/agents_registry.py tags) that may never feed a draft leaving the system.
RESTRICTED_INPUT_CLASSES = frozenset({"dossier_2", "dossier_3", "dossier_4", "finance", "medical", "employer"})
# Platforms with no official posting/messaging API open to a personal account: draft only, a person sends.
DRAFT_ONLY_CHANNELS = frozenset({"hinge", "tinder", "bumble", "instagram-dm", "linkedin-dm", "whatsapp"})
MODES = frozenset({"draft", "official-api"})


def enabled() -> bool:
    """Style checks (REWRITE findings) are on unless ENABLE_PERSONA_TWIN is set to false/0/off.
    Privacy, data-class and platform checks (BLOCK findings) cannot be switched off."""
    return os.environ.get(FLAG, "true").strip().lower() not in ("false", "0", "off", "no")


@dataclass(frozen=True)
class Signature:
    sentences: int
    mean_sentence_words: float
    sentence_words_stdev: float
    dashes_per_1000_chars: float
    exclamations_per_100_sentences: float
    emoji_per_1000_chars: float


@dataclass(frozen=True)
class PersonaProfile:
    tone: tuple[str, ...] = ()
    vocabulary: tuple[str, ...] = ()
    rhythm: tuple[str, ...] = ()
    humour: tuple[str, ...] = ()
    never_say: tuple[str, ...] = ()
    never_disclose: tuple[str, ...] = ()
    british_spelling: bool = True
    samples: tuple[str, ...] = ()
    signature: Signature | None = None


@dataclass(frozen=True)
class Finding:
    severity: str              # "BLOCK" or "REWRITE"
    rule: str
    detail: str


@dataclass(frozen=True)
class Verdict:
    status: str                # "PASS" | "REWRITE" | "BLOCK"
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def rewrite_brief(self) -> str:
        return "; ".join(f"{f.rule}: {f.detail}" for f in self.findings if f.severity == "REWRITE")


class CriticRejected(PermissionError):
    def __init__(self, verdict: Verdict) -> None:
        super().__init__(f"{verdict.status}: " + "; ".join(f.rule for f in verdict.findings))
        self.verdict = verdict


def signature(text: str) -> Signature:
    sentences = [s.strip() for s in SENTENCE.findall(text) if len(s.split()) >= 2]
    lengths = [len(s.split()) for s in sentences] or [0]
    chars = max(len(text), 1)
    emoji = sum(1 for ch in text if ord(ch) >= 0x1F300)
    return Signature(
        sentences=len(sentences), mean_sentence_words=round(statistics.fmean(lengths), 2),
        sentence_words_stdev=round(statistics.pstdev(lengths), 2) if len(lengths) > 1 else 0.0,
        dashes_per_1000_chars=round(1000 * (text.count("—") + text.count(" - ")) / chars, 2),
        exclamations_per_100_sentences=round(100 * text.count("!") / max(len(sentences), 1), 1),
        emoji_per_1000_chars=round(1000 * emoji / chars, 2))


def parse_profile(markdown: str) -> PersonaProfile:
    """Sections: Tone, Vocabulary, Sentence rhythm, Humour, Never say, Hard red lines (or
    'Never disclose'), Spelling, Samples. Bullet lines are items; under Samples, paragraphs
    separated by blank lines are samples."""
    sections: dict[str, list[str]] = {}
    current = ""
    for line in markdown.splitlines():
        heading = re.match(r"#{1,3}\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)

    def bullets(*names: str) -> tuple[str, ...]:
        lines = [ln for name in names for ln in sections.get(name, [])]
        out = [re.sub(r"^\s*[-*]\s+", "", ln).strip() for ln in lines if re.match(r"\s*[-*]\s+\S", ln)]
        return tuple(item for item in out if 0 < len(item) <= 200 and not item.startswith("("))[:100]

    sample_text = "\n".join(sections.get("samples", []))
    samples = tuple(p.strip() for p in re.split(r"\n\s*\n", sample_text) if len(p.split()) >= 8)[:50]
    spelling = " ".join(sections.get("spelling", [])).lower()
    joined = "\n\n".join(samples)
    return PersonaProfile(tone=bullets("tone"), vocabulary=bullets("vocabulary"), rhythm=bullets("sentence rhythm", "rhythm"),
                          humour=bullets("humour", "humor"), never_say=bullets("never say"),
                          never_disclose=bullets("hard red lines", "never disclose"),
                          british_spelling="american" not in spelling, samples=samples,
                          signature=signature(joined) if samples else None)


def load_profile(root: Path, register: str = "written") -> PersonaProfile:
    """The owner's own style file, plus samples generated by persona_ingest if present.
    register "written" (default) uses mail samples; "chat" uses chat-message samples instead, so a
    short text message is not judged against the rhythm of an email, or the reverse."""
    texts = []
    for name in (STYLE_FILE[-1], "persona_samples_chat.md" if register == "chat" else "persona_samples.md"):
        path = Path(root).joinpath(*STYLE_FILE[:-1], name)
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 400_000:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    return parse_profile("\n\n".join(texts)) if texts else PersonaProfile()


def system_context(profile: PersonaProfile) -> str:
    """Text for the local model's system prompt so it drafts in the owner's voice. Protected
    terms are deliberately NOT included: the model is told the rule, never the secrets."""
    parts = ["Write as the owner would: first person, British English." if profile.british_spelling else "Write as the owner would: first person."]
    for label, items in (("Tone", profile.tone), ("Vocabulary", profile.vocabulary), ("Sentence rhythm", profile.rhythm),
                         ("Humour", profile.humour), ("Never use these phrases", profile.never_say)):
        if items:
            parts.append(f"{label}: " + "; ".join(items[:12]))
    if profile.signature is not None:
        parts.append(f"Typical sentence: about {profile.signature.mean_sentence_words:.0f} words, with real variation in length.")
    for sample in profile.samples[:3]:
        parts.append("Example of the owner's writing: " + sample[:400])
    parts.append("Never name the owner's employer, colleagues, clients, address, health or money details. "
                 "No stock AI phrases, no hashtags, no emoji unless the examples use them.")
    return "\n".join(parts)[:4000]


def review(draft: str, profile: PersonaProfile, channel: str | None = None, mode: str = "draft",
           input_classes: tuple[str, ...] = (), critic: Callable[[str], list[str]] | None = None) -> Verdict:
    """`channel`/`mode`: where the text is headed and how. `input_classes`: registry data-class
    tags of everything that fed the draft. `critic`: optional local-model second opinion; it can
    only ADD rewrite findings, never clear one."""
    if not isinstance(draft, str) or not draft.strip():
        return Verdict("BLOCK", (Finding("BLOCK", "empty-draft", "nothing to review"),))
    if len(draft) > MAX_DRAFT_CHARS:
        return Verdict("BLOCK", (Finding("BLOCK", "too-long", f"over {MAX_DRAFT_CHARS} characters"),))
    findings: list[Finding] = []
    lowered = draft.lower()
    leaked = sorted(RESTRICTED_INPUT_CLASSES.intersection(input_classes))
    if leaked:
        findings.append(Finding("BLOCK", "restricted-data-class", "built from " + ", ".join(leaked)))
    if mode not in MODES:
        findings.append(Finding("BLOCK", "platform-mode", "only 'draft' or 'official-api' delivery is allowed"))
    elif channel is not None and channel.lower() in DRAFT_ONLY_CHANNELS and mode != "draft":
        findings.append(Finding("BLOCK", "platform-draft-only", f"{channel} has no permitted sending route; a person sends it"))
    for term in profile.never_disclose:
        if term.lower() in lowered:
            findings.append(Finding("BLOCK", "unauthorised-disclosure", f"mentions a protected term ({len(term)} characters)"))
    if SENSITIVE_NUMBER.search(draft):
        findings.append(Finding("BLOCK", "sensitive-number", "contains a number shaped like an account, sort code or card"))
    style_from = len(findings)
    for pattern in AI_TROPES:
        hit = re.search(pattern, draft, re.I)
        if hit:
            findings.append(Finding("REWRITE", "ai-trope", f'"{hit.group(0).strip()}"'))
    for phrase in profile.never_say:
        if phrase.lower() in lowered:
            findings.append(Finding("REWRITE", "owner-banned-phrase", f'"{phrase}"'))
    if profile.british_spelling:
        for american, british in AMERICAN_TO_BRITISH.items():
            if re.search(rf"\b{american}(s|d|ed|ing)?\b", lowered):
                findings.append(Finding("REWRITE", "american-spelling", f'"{american}" -> "{british}"'))
    sig = signature(draft)
    if sig.emoji_per_1000_chars > 4:
        findings.append(Finding("REWRITE", "emoji-heavy", f"{sig.emoji_per_1000_chars} per 1000 characters"))
    if draft.count("#") >= 4:
        findings.append(Finding("REWRITE", "hashtag-stuffing", f"{draft.count('#')} hashtags"))
    ref = profile.signature
    if ref is not None and ref.sentences >= 10 and sig.sentences >= 4:
        if abs(sig.mean_sentence_words - ref.mean_sentence_words) > max(8.0, 0.6 * ref.mean_sentence_words):
            findings.append(Finding("REWRITE", "cadence-sentence-length",
                                    f"averages {sig.mean_sentence_words} words a sentence; the owner's samples average {ref.mean_sentence_words}"))
        if sig.dashes_per_1000_chars > ref.dashes_per_1000_chars + 3:
            findings.append(Finding("REWRITE", "cadence-dashes", f"{sig.dashes_per_1000_chars} dashes per 1000 characters vs {ref.dashes_per_1000_chars}"))
        if sig.exclamations_per_100_sentences > ref.exclamations_per_100_sentences + 25:
            findings.append(Finding("REWRITE", "cadence-exclamations", "far more exclamation marks than the owner's samples"))
        if ref.sentence_words_stdev >= 4 and sig.sentence_words_stdev < 0.35 * ref.sentence_words_stdev:
            findings.append(Finding("REWRITE", "cadence-monotone", "sentences are all about the same length; the owner's vary"))
    if any(f.severity == "BLOCK" for f in findings):
        return Verdict("BLOCK", tuple(findings))
    if not enabled():
        del findings[style_from:]
    elif critic is not None:
        try:
            for note in list(critic(draft))[:5]:
                findings.append(Finding("REWRITE", "model-critic", str(note)[:200]))
        except Exception:
            pass                              # the deterministic result stands if the model is unavailable
    return Verdict("REWRITE" if findings else "PASS", tuple(findings))


def gate(draft: str, profile: PersonaProfile, **context) -> Verdict:
    """Pre-publication hook: returns the PASS verdict or raises CriticRejected."""
    verdict = review(draft, profile, **context)
    if verdict.status != "PASS":
        raise CriticRejected(verdict)
    return verdict


def rewrite_until_pass(draft: str, profile: PersonaProfile, redraft: Callable[[str, str], str],
                       max_rounds: int = 2, **context) -> tuple[str, Verdict, int]:
    """`redraft(current_text, brief) -> new_text` is the caller's budget-gated model call.
    Returns (final_text, final_verdict, rounds_used). A BLOCK is returned at once, untouched."""
    text, rounds = draft, 0
    max_rounds = min(max_rounds, 2)
    verdict = review(text, profile, **context)
    while verdict.status == "REWRITE" and rounds < max_rounds:
        rounds += 1
        text = str(redraft(text, verdict.rewrite_brief))[:MAX_DRAFT_CHARS]
        verdict = review(text, profile, **context)
    return text, verdict, rounds
