from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

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

SAVE_CUE_PATTERNS: tuple[str, ...] = (
    "save this",
    "save for later",
    "send this to",
    "share this with",
    "bookmark this",
    "forward this",
)

FOLLOW_CUE_PATTERNS: tuple[str, ...] = (
    "follow for",
    "follow to",
    "follow if",
    "follow along",
)

_LINK_RE = re.compile(r"https?://\S+")
_HASHTAG_RE = re.compile(r"#\w+")
_MENTION_RE = re.compile(r"@\w+")
_THREAD_RE = re.compile(r"(?:^|\s)1/(?:\d+|\s)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


LaneStatus = Literal["undeclared", "overlap", "disjoint"]


def normalize_topics(topics: Sequence[str] | None) -> list[str]:
    """Lowercase lane names, dropping blanks (#8).

    Input paths reject blank topics with 422 before this runs; the
    filter keeps stored rows clean if one slips through.
    """
    return [t.strip().casefold() for t in (topics or []) if t.strip()]


def topic_lane(
    topics: Sequence[str], voice_topics: Sequence[str] | None
) -> LaneStatus:
    """One shared disjoint test for the gate wording and the score math."""
    if not topics or not voice_topics:
        return "undeclared"
    if set(topics) & set(voice_topics):
        return "overlap"
    return "disjoint"


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
    has_save_cue: bool = False
    has_follow_cue: bool = False
    media_types: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    voice_topics: tuple[str, ...] | None = None


def extract(
    text: str,
    *,
    author_followers: int | None = None,
    mutuals_count: int | None = None,
    scheduled_at: datetime | None = None,
    allow_premium_length: bool = False,
    media: Sequence[str] | None = None,
    topics: Sequence[str] | None = None,
    voice_topics: Sequence[str] | None = None,
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
        has_save_cue=any(p in lowered for p in SAVE_CUE_PATTERNS),
        has_follow_cue=any(p in lowered for p in FOLLOW_CUE_PATTERNS),
        media_types=tuple(media or ()),
        topics=tuple(topics or ()),
        voice_topics=tuple(voice_topics) if voice_topics is not None else None,
    )


def extract_for(
    session: Session,
    *,
    text: str,
    project_id: str | None,
    author_followers: int | None = None,
    mutuals_count: int | None = None,
    scheduled_at: datetime | None = None,
    allow_premium_length: bool = False,
    media: Sequence[str] | None = None,
    topics: Sequence[str] | None = None,
) -> DraftFeatures:
    """Draft features plus the owning voice's declared topic lanes (#8).

    Voice topics ride along so the topic-lane gate rule and the interim
    topic discount need no session of their own. Unbound voices and
    relay-observed posts get voice_topics=None: no discount, unchanged
    scoring.
    """
    from launcher.models import VoiceBinding

    voice_topics: tuple[str, ...] | None = None
    if project_id:
        binding = (
            session.query(VoiceBinding).filter_by(project_id=project_id).one_or_none()
        )
        if binding is not None and binding.topics:
            voice_topics = tuple(binding.topics)
    return extract(
        text,
        author_followers=author_followers,
        mutuals_count=mutuals_count,
        scheduled_at=scheduled_at,
        allow_premium_length=allow_premium_length,
        media=media,
        topics=topics,
        voice_topics=voice_topics,
    )
