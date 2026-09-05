from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.drafts import DraftScore, DraftStore, score_draft
from launcher.models import Draft
from launcher.outcomes import SyntheticOutcomeSource
from launcher.params import seed_params
from launcher.predictor import train_predictor
from launcher.rewriter import GenerationResult, rewrite_flow
from launcher.rules_seed import seed_rules


class FakeProvider:
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts

    def generate(self, draft_text: str, n: int) -> GenerationResult:
        return GenerationResult(texts=tuple(self._texts[:n]), usd=0.0, tokens_in=0, tokens_out=0)

    def estimate_cost(self, draft_text: str, n: int) -> float:
        return 0.0


TEXT = "Distribution beats marketing every single time. What would you add?"


def _seeded(session: Session, text: str = TEXT, **kwargs: object) -> Draft:
    seed_params(session)
    seed_rules(session)
    draft = Draft(text=text, **kwargs)
    session.add(draft)
    session.flush()
    session.commit()
    return draft


def test_score_draft_returns_gate_verdict_and_seam_score(session: Session) -> None:
    draft = _seeded(session)
    result = score_draft(session, draft.id)
    assert isinstance(result, DraftScore)
    assert result.report.verdict == "passed"
    assert result.scored.kind == "interim"
    assert result.scored.scorer == "interim"
    assert result.scored.band_width > 0


def test_score_draft_missing_raises(session: Session) -> None:
    with pytest.raises(ValueError):
        score_draft(session, 9999)


def test_store_resolve_returns_variant_without_refetch(session: Session) -> None:
    from launcher.models import DraftVariant

    draft = _seeded(session)
    variant = DraftVariant(draft_id=draft.id, text="A variant.", variant_index=0)
    session.add(variant)
    session.flush()
    session.commit()
    candidate = DraftStore(session).resolve_candidate(draft.id, variant.id)
    assert candidate.draft.id == draft.id
    assert candidate.text == "A variant."
    assert candidate.variant is not None
    assert candidate.variant.id == variant.id


def test_store_resolve_rejects_foreign_variant(session: Session) -> None:
    from launcher.models import DraftVariant

    first = _seeded(session)
    second = Draft(text="Other draft here.", project_id=None)
    session.add(second)
    session.flush()
    variant = DraftVariant(draft_id=second.id, text="Other variant.", variant_index=0)
    session.add(variant)
    session.flush()
    session.commit()
    with pytest.raises(ValueError):
        DraftStore(session).resolve_candidate(first.id, variant.id)


def test_score_draft_uses_predictor_when_model_exists(session: Session) -> None:
    seed_params(session)
    seed_rules(session)
    train_predictor(session, "proj", SyntheticOutcomeSource(n=300))
    draft = Draft(text=TEXT, project_id="proj")
    session.add(draft)
    session.flush()
    session.commit()
    result = score_draft(session, draft.id)
    assert result.scored.kind == "predicted"
    assert result.scored.scorer == "predictor"
    assert result.scored.model_id is not None
    assert result.scored.model_status == "pending"


def test_rewrite_flow_runs_in_same_harness(session: Session) -> None:
    draft = _seeded(session)
    result = rewrite_flow(
        session,
        draft.id,
        FakeProvider(["Fear was the constraint. What would you add?"]),
        n=1,
    )
    assert result.generated == 1
    assert len(result.top) == 1
