from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from launcher.models import Swatch

_TOKEN_RE = re.compile(r"[a-z']{3,}")


def tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def format_similarity(text_a: str, text_b: str) -> float:
    a = tokenize(text_a)
    b = tokenize(text_b)
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    union = len(a | b)
    return overlap / union


def load_swatch_texts(
    session: Session, project_id: str | None, limit: int = 500
) -> list[str]:
    if not project_id:
        return []
    rows = (
        session.query(Swatch.text)
        .filter(Swatch.project_id == project_id)
        .limit(limit)
        .all()
    )
    return [text for (text,) in rows]


class SwatchCorpus:
    """Similarity corpus with an injectable loader: pure scoring over any
    text list, DB-backed via from_session."""

    def __init__(self, load: Callable[[], Sequence[str]]) -> None:
        self._load = load

    @classmethod
    def from_session(
        cls, session: Session, project_id: str | None, limit: int = 500
    ) -> SwatchCorpus:
        return cls(lambda: load_swatch_texts(session, project_id, limit))

    def max_similarity(self, text: str) -> float:
        corpus = list(self._load())
        if not corpus:
            return 0.0
        return max(format_similarity(text, candidate) for candidate in corpus)


def max_swatch_similarity(session: Session, project_id: str | None, text: str) -> float:
    return SwatchCorpus.from_session(session, project_id).max_similarity(text)
