"""Bootstrap benchmark: simulated fixture tasks used ONLY until enough real ratings exist.

These are not observations. They encode what the owner has said he wants (in-person social,
singles and networking events on Friday evenings and weekends; not webinars or weekday-morning
sessions) plus a few deliberately awkward cases. A candidate that wins here has matched the
stated preferences, nothing more, and every proposal raised in this mode is labelled BOOTSTRAP.
"""
from __future__ import annotations

_LIKED = (
    ("london singles mixer shoreditch", True), ("speed dating over 35s soho", True),
    ("tech founders networking drinks", True), ("charity gala dinner mayfair", True),
    ("supper club social north london", True), ("rooftop summer party social", True),
    ("ai builders meetup networking king's cross", True), ("wine tasting singles evening", True),
    ("black tie gala fundraiser", True), ("members club open evening social", False),
    ("startup networking evening the city", False), ("investor and founders dinner", False),
    ("salsa social for beginners", True), ("art gallery late opening social", True),
    ("product leaders networking breakfast club annual party", True), ("board games social pub night", True),
)
_DISLIKED = (
    ("online webinar tech careers", False), ("virtual networking online", False),
    ("webinar: intro to cloud certification", False), ("online singles quiz zoom", True),
    ("tech talk online livestream", False), ("weekday morning compliance webinar", False),
    ("kids coding workshop", True), ("online social mixer discord", True),
    ("tech hackathon 48 hours", True), ("vendor sales webinar networking", False),
    ("remote founders online coffee chat", False), ("lunchtime procurement seminar", False),
    ("student society tech social", False), ("online speed dating", True),
    ("crypto trading signals networking", False), ("mlm business opportunity social", True),
)


def fixtures() -> list[dict]:
    rows = [(text, weekend, 1) for text, weekend in _LIKED] + [(text, weekend, 0) for text, weekend in _DISLIKED]
    return [{"features": {"text": text, "is_weekend_or_friday_evening": weekend}, "label": label} for text, weekend, label in rows]
