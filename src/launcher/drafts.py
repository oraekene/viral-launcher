from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from launcher.features import extract
from launcher.gate import GateReport, load_engine
from launcher.models import Draft, DraftVariant
from launcher.scoring import ScoredScore, resolve_score


def get_draft_or_raise(session: Session, draft_id: int) -> Draft:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ValueError(f"draft {draft_id} not found")
    return draft


def resolve_candidate_text(
    session: Session, draft_id: int, variant_id: int | None = None
) -> tuple[Draft, str]:
    draft = get_draft_or_raise(session, draft_id)
    text = draft.text
    if variant_id is not None:
        variant = session.get(DraftVariant, variant_id)
        if variant is None or variant.draft_id != draft_id:
            raise ValueError(f"variant {variant_id} not found for draft {draft_id}")
        text = variant.text
    return draft, text


@dataclass(frozen=True)
class DraftScore:
    """Service-level score: gate verdict and seam score travel together."""

    report: GateReport
    scored: ScoredScore


def score_draft(session: Session, draft_id: int) -> DraftScore:
    """Score a draft without HTTP — the drafts-domain service entry point."""
    draft = get_draft_or_raise(session, draft_id)
    features = extract(
        draft.text,
        author_followers=draft.author_followers,
        mutuals_count=draft.mutuals_count,
        scheduled_at=draft.scheduled_at,
        allow_premium_length=draft.allow_premium_length,
    )
    return DraftScore(
        report=load_engine(session).evaluate(features),
        scored=resolve_score(session, draft.project_id, features, draft.text),
    )
