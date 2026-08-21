from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

BAIT_PATTERNS: tuple[str, ...] = (
    "like if",
    "rt if",
    "follow back",
    "follow me and",
    "tag someone",
    "tag 3",
    "tag three",
    "comment below",
    "reply with",
    "drop a comment",
    "drop your",
    "smash that",
)

MASS_REPLY_MARKERS: tuple[str, ...] = (
    "{name}",
    "{{name}}",
    "[first name]",
    "hey {",
    "dm me",
    "slide into",
)

POD_SIGNATURES: tuple[str, ...] = (
    "engagement pod",
    "pod post",
    "engagement group",
    "reply chain",
    "reciprocal engagement",
    "engagement thread",
)

CTA_PATTERNS: tuple[str, ...] = (
    "tell me",
    "let me know",
    "share your",
    "your take",
    "what would you add",
    "what do you think",
    "which side",
    "how do you handle",
    "what's your take",
    "am i wrong",
    "prove me wrong",
    "curious how",
)

_LINK_RE = re.compile(r"https?://\S+")
_HASHTAG_RE = re.compile(r"#\w+")
_MENTION_RE = re.compile(r"@\w+")
_THREAD_RE = re.compile(r"(?:^|\s)1/(?:\d+|\s)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class DraftFeatures:
    char_len: int
    word_count: int
    question_count: int
    has_question: bool
    has_cta: bool
    quotable_claim: bool
    link_count: int
    hashtag_count: int
    mention_count: int
    exclamation_count: int
    thread_marker: bool
    engagement_bait_hits: tuple[str, ...]
    mass_reply_markers: tuple[str, ...]
    pod_signature_hits: tuple[str, ...]
    author_followers: int | None
    mutuals_count: int | None
    scheduled_at: datetime | None
    allow_premium_length: bool


def extract(
    text: str,
    *,
    author_followers: int | None = None,
    mutuals_count: int | None = None,
    scheduled_at: datetime | None = None,
    allow_premium_length: bool = False,
) -> DraftFeatures:
    lowered = text.lower()
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    quotable = any(
        30 <= len(s) <= 160 and not _LINK_RE.search(s) and "?" not in s for s in sentences
    )
    return DraftFeatures(
        char_len=len(text),
        word_count=len(text.split()),
        question_count=text.count("?"),
        has_question="?" in text,
        has_cta=any(p in lowered for p in CTA_PATTERNS),
        quotable_claim=quotable,
        link_count=len(_LINK_RE.findall(text)),
        hashtag_count=len(_HASHTAG_RE.findall(text)),
        mention_count=len(_MENTION_RE.findall(text)),
        exclamation_count=text.count("!"),
        thread_marker=bool(_THREAD_RE.search(text)),
        engagement_bait_hits=tuple(p for p in BAIT_PATTERNS if p in lowered),
        mass_reply_markers=tuple(m for m in MASS_REPLY_MARKERS if m in lowered),
        pod_signature_hits=tuple(p for p in POD_SIGNATURES if p in lowered),
        author_followers=author_followers,
        mutuals_count=mutuals_count,
        scheduled_at=scheduled_at,
        allow_premium_length=allow_premium_length,
    )
