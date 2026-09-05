from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.features import extract
from launcher.models import Draft, PredictorModel
from launcher.outcomes import SyntheticOutcomeSource
from launcher.params import seed_params
from launcher.predictor import active_model, predict_z, train_predictor
from launcher.rewriter import GenerationResult, HeuristicProvider, rewrite_flow
from launcher.rules_seed import seed_rules


@pytest.fixture()
def seeded(session: Session) -> Session:
    seed_params(session)
    seed_rules(session)
    session.commit()
    return session


def test_synthetic_source_honors_winner_share(seeded: Session) -> None:
    rows = SyntheticOutcomeSource(n=400, winner_share=0.5).load_outcomes("proj")
    assert len(rows) == 400
    share = sum(r.value_flag for r in rows) / len(rows)
    assert 0.35 < share < 0.65
    for row in rows[:5]:
        assert isinstance(row.features, dict)
        assert row.z60 >= 0.0


def test_train_persists_model_with_metrics(seeded: Session) -> None:
    model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=400))
    assert model.n_events == 400
    assert model.precision >= 0.6
    assert model.recall >= 0.6
    assert model.status == "pending"
    assert model.feature_importances
    assert abs(sum(model.feature_importances.values()) - 1.0) < 0.01


def test_train_is_per_project(seeded: Session) -> None:
    train_predictor(seeded, "proj-a", SyntheticOutcomeSource(n=300))
    train_predictor(seeded, "proj-b", SyntheticOutcomeSource(n=300))
    models = seeded.query(PredictorModel).order_by(PredictorModel.id).all()
    assert {m.project_id for m in models} == {"proj-a", "proj-b"}
    assert active_model(seeded, "proj-a") is not None
    assert active_model(seeded, "proj-b").project_id == "proj-b"


def test_active_model_none_when_untrained(seeded: Session) -> None:
    assert active_model(seeded, "nope") is None


def test_active_model_returns_latest(seeded: Session) -> None:
    first = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=250))
    second = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=350))
    assert active_model(seeded, "proj").id == second.id
    assert second.id != first.id


def test_predict_z_scores_draft_features(seeded: Session) -> None:
    train_predictor(seeded, "proj", SyntheticOutcomeSource(n=400))
    good = extract(
        "Distribution beats marketing every single time. What would you add?",
        author_followers=900,
        mutuals_count=5,
    )
    prediction = predict_z(seeded, "proj", good)
    assert prediction is not None
    assert prediction.predicted_z > 0.0
    assert prediction.band_width > 0.0
    assert prediction.model_status == "pending"


def test_predict_z_without_model_returns_none(seeded: Session) -> None:
    f = extract("Some text here.")
    assert predict_z(seeded, "ghost", f) is None


def test_rewriter_uses_predictor_when_model_exists(seeded: Session) -> None:
    d = Draft(text="Fear was the constraint.", project_id="proj")
    seeded.add(d)
    seeded.flush()
    train_predictor(seeded, "proj", SyntheticOutcomeSource(n=400))
    result = rewrite_flow(seeded, d.id, HeuristicProvider(), n=2)
    top_reasons = " ".join(r for v in result.top for r in v.reasons)
    assert "predicted z" in top_reasons


def test_rewriter_falls_back_to_interim_without_model(seeded: Session) -> None:
    d = Draft(text="Fear was the constraint.")
    seeded.add(d)
    seeded.flush()
    provider = GenerationResultProvider()
    result = rewrite_flow(seeded, d.id, provider, n=1)
    joined = " ".join(r for v in result.top for r in v.reasons)
    assert "predicted z" not in joined
    assert "weight." in joined or len(result.top) == 0


class GenerationResultProvider(HeuristicProvider):
    def generate(self, draft_text: str, n: int) -> GenerationResult:
        return GenerationResult(
            texts=(f"{draft_text.strip()} What would you add?",),
            usd=0.0,
            tokens_in=0,
            tokens_out=0,
        )

    def estimate_cost(self, draft_text: str, n: int) -> float:
        return 0.0
