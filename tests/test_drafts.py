from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.drafts import DraftScore, score_draft
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
