from __future__ import annotations

import re

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


def max_swatch_similarity(session: Session, project_id: str | None, text: str) -> float:
    if not project_id:
        return 0.0
    texts = (
        session.query(Swatch.text)
        .filter(Swatch.project_id == project_id)
        .limit(500)
        .all()
    )
    if not texts:
        return 0.0
    return max(format_similarity(text, t[0]) for t in texts)
