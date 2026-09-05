from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from launcher.features import extract
from launcher.gate import GateReport, load_engine
from launcher.models import Draft, DraftVariant
from launcher.scoring import ScoredScore, resolve_score


def get_draft_or_raise(session: Session, draft_id: int) -> Draft:
    return DraftStore(session).get_draft(draft_id)


def resolve_candidate_text(
    session: Session, draft_id: int, variant_id: int | None = None
) -> tuple[Draft, str]:
    candidate = DraftStore(session).resolve_candidate(draft_id, variant_id)
    return candidate.draft, candidate.text


@dataclass(frozen=True)
class CandidateText:
    draft: Draft
    variant: DraftVariant | None
    text: str


class DraftStore:
    """Draft persistence adapter: drafts and their variants behind one seam."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_draft(self, draft_id: int) -> Draft:
        draft = self._session.get(Draft, draft_id)
        if draft is None:
            raise ValueError(f"draft {draft_id} not found")
        return draft

    def resolve_candidate(
        self, draft_id: int, variant_id: int | None = None
    ) -> CandidateText:
        draft = self.get_draft(draft_id)
        variant: DraftVariant | None = None
        text = draft.text
        if variant_id is not None:
            variant = self._session.get(DraftVariant, variant_id)
            if variant is None or variant.draft_id != draft_id:
                raise ValueError(f"variant {variant_id} not found for draft {draft_id}")
            text = variant.text
        return CandidateText(draft=draft, variant=variant, text=text)


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
