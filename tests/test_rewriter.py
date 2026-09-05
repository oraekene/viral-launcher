from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.cost import BudgetExceeded, CostMeter
from launcher.models import Draft, DraftVariant
from launcher.params import seed_params
from launcher.rewriter import (
    GenerationResult,
    HeuristicProvider,
    RewriteResult,
    rank_candidates,
    rewrite_flow,
    try_rewrite_flow,
)
from launcher.rules_seed import seed_rules


class FakeProvider:
    def __init__(self, texts: list[str], usd: float = 0.0) -> None:
        self._texts = texts
        self._usd = usd

    def generate(self, draft_text: str, n: int) -> GenerationResult:
        return GenerationResult(
            texts=tuple(self._texts[:n]), usd=self._usd, tokens_in=0, tokens_out=0
        )

    def estimate_cost(self, draft_text: str, n: int) -> float:
        return self._usd


@pytest.fixture()
def seeded(session: Session) -> Session:
    seed_params(session)
    seed_rules(session)
    d = Draft(text="We cut onboarding from 14 days to 2. Fear was the constraint.")
    session.add(d)
    session.flush()
    session.commit()
    return session


def test_heuristic_provider_is_deterministic() -> None:
    text = "We just really cut onboarding from 14 days to 2. It was fear, actually."
    first = HeuristicProvider().generate(text, n=10)
    second = HeuristicProvider().generate(text, n=10)
    assert first.texts == second.texts
    assert len(first.texts) > 0


def test_heuristic_provider_costs_nothing() -> None:
    result = HeuristicProvider().generate("Some text here.", n=5)
    assert result.usd == 0.0


def test_flow_ranks_survivors_and_excludes_vetoed(seeded: Session) -> None:
    provider = FakeProvider(
        [
            "Like if you agree! Tag someone who needs this.",
            "Fear was the constraint. What would you add?",
        ]
    )
    draft = seeded.query(Draft).one()
    result = rewrite_flow(seeded, draft.id, provider, n=2)
    assert isinstance(result, RewriteResult)
    assert result.vetoed_count == 1
    assert all(v.text != "Like if you agree! Tag someone who needs this." for v in result.top)
    assert len(result.top) <= 3
    scores = [v.score for v in result.top]
    assert scores == sorted(scores, reverse=True)


def test_flow_scores_only_generated_variants(seeded: Session) -> None:
    provider = FakeProvider(
        [
            "Fear was the constraint. What would you add?",
            "Second variant with a real question?",
        ]
    )
    draft = seeded.query(Draft).one()
    result = rewrite_flow(seeded, draft.id, provider, n=2)
    assert result.generated == 2
    rows = seeded.query(DraftVariant).all()
    assert len(rows) == 2
    assert all(row.text != draft.text for row in rows)


def test_flow_never_ranks_original_as_candidate(seeded: Session) -> None:
    provider = FakeProvider([])
    draft = seeded.query(Draft).one()
    result = rewrite_flow(seeded, draft.id, provider, n=1)
    assert result.generated == 0
    assert result.top == ()
    assert seeded.query(DraftVariant).count() == 0


def test_flow_persists_variants_with_gate_lines(seeded: Session) -> None:
    provider = FakeProvider(["Fear was the constraint. What would you add?"])
    draft = seeded.query(Draft).one()
    rewrite_flow(seeded, draft.id, provider, n=1)
    rows = seeded.query(DraftVariant).order_by(DraftVariant.variant_index).all()
    assert len(rows) == 1
    for row in rows:
        assert row.gate_lines
        assert all("source_note" in line for line in row.gate_lines)


def test_flow_records_cost_event(seeded: Session) -> None:
    provider = FakeProvider(["A variant."], usd=0.02)
    draft = seeded.query(Draft).one()
    result = rewrite_flow(seeded, draft.id, provider, n=1)
    assert abs(result.cost_usd - 0.02) < 1e-9
    assert CostMeter(seeded).spent(draft.id) > 0


def test_per_draft_cap_blocks_repeat_paid_rewrite(seeded: Session) -> None:
    provider = FakeProvider(["A variant."], usd=0.06)
    draft = seeded.query(Draft).one()
    rewrite_flow(seeded, draft.id, provider, n=1)
    with pytest.raises(BudgetExceeded):
        rewrite_flow(seeded, draft.id, provider, n=1)


def test_missing_draft_raises(seeded: Session) -> None:
    with pytest.raises(ValueError):
        rewrite_flow(seeded, 9999, FakeProvider([]), n=1)


def test_rank_candidates_orders_scores_and_excludes_vetoed() -> None:
    idx = rank_candidates(
        ["a", "b", "c", "d"],
        [1.0, 3.0, 2.0, 5.0],
        [False, False, True, False],
    )
    assert idx == [3, 1, 0]


def test_rank_candidates_stable_on_ties_and_empty() -> None:
    assert rank_candidates(["a", "b", "c"], [2.0, 2.0, 1.0], [False] * 3) == [0, 1, 2]
    assert rank_candidates([], [], []) == []
    assert rank_candidates(["a"], [1.0], [True]) == []


def test_try_rewrite_returns_result_on_success(seeded: Session) -> None:
    provider = FakeProvider(["Fear was the constraint. What would you add?"])
    draft = seeded.query(Draft).one()
    attempt = try_rewrite_flow(seeded, draft.id, provider, n=1)
    assert attempt.error is None
    assert attempt.result is not None
    assert attempt.result.generated == 1


def test_try_rewrite_captures_budget_as_error(seeded: Session) -> None:
    provider = FakeProvider(["A variant."], usd=0.50)
    draft = seeded.query(Draft).one()
    attempt = try_rewrite_flow(seeded, draft.id, provider, n=1)
    assert attempt.result is None
    assert attempt.error is not None
    assert "cap" in attempt.error.lower()


def test_try_rewrite_reraises_missing_draft(seeded: Session) -> None:
    with pytest.raises(ValueError):
        try_rewrite_flow(seeded, 9999, FakeProvider([]), n=1)
