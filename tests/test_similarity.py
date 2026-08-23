from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.features import extract
from launcher.models import PredictorModel, Swatch
from launcher.outcomes import SyntheticOutcomeSource
from launcher.params import seed_params
from launcher.predictor import (
    FEATURE_NAMES,
    feature_values,
    predict_z,
    train_predictor,
)
from launcher.rewriter import HeuristicProvider, rewrite_flow
from launcher.rules_seed import seed_rules
from launcher.similarity import format_similarity


@pytest.fixture()
def seeded(session: Session) -> Session:
    seed_params(session)
    seed_rules(session)
    session.commit()
    return session


def test_identical_texts_score_full_overlap() -> None:
    a = "distribution beats marketing every single time"
    assert format_similarity(a, a) == 1.0


def test_disjoint_texts_score_zero() -> None:
    assert format_similarity("cats sit on mats", "quantum flux capacitors") == 0.0


def test_partial_overlap_between_zero_and_one() -> None:
    s = format_similarity(
        "distribution beats marketing every single time",
        "distribution beats paid ads almost every time",
    )
    assert 0.0 < s < 1.0


def test_feature_values_include_swatch_similarity(seeded: Session) -> None:
    f = extract("Some text here.")
    values = feature_values(f, swatch_similarity=0.42)
    assert values["swatch_similarity"] == 0.42
    assert set(FEATURE_NAMES) == set(values.keys())


def test_similarity_against_archived_swatches(session: Session) -> None:
    from launcher.models import Draft
    from launcher.similarity import max_swatch_similarity
    from launcher.swipes import archive_swatch

    seed_params(session)
    draft_text = "Distribution beats marketing every single time. What would you add?"
    draft = Draft(text=draft_text, project_id="proj")
    session.add(draft)
    session.flush()
    archive_swatch(session, draft.id)

    near = max_swatch_similarity(session, "proj", draft_text)
    far = max_swatch_similarity(session, "proj", "totally unrelated words here")
    assert near > far
    assert far >= 0.0


def test_v2_model_trains_with_new_feature(seeded: Session) -> None:
    model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    assert "swatch_similarity" in model.feature_names
    assert model.algorithm.endswith(".v2")


def test_old_v1_artifact_still_scores(seeded: Session) -> None:
    import pickle

    from sklearn.ensemble import GradientBoostingRegressor

    rows = SyntheticOutcomeSource(n=300).load_outcomes("proj")
    legacy = [n for n in FEATURE_NAMES if n != "swatch_similarity"]
    X = [[row.features[n] for n in legacy] for row in rows]
    y = [row.z60 for row in rows]
    legacy_model = GradientBoostingRegressor(random_state=7)
    legacy_model.fit(X, y)

    model = seeded.query(PredictorModel).first()
    if model is None:
        model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    model.algorithm = "gradient_boosting_regressor.v1"
    model.feature_names = legacy
    model.model_blob = pickle.dumps(legacy_model)
    seeded.commit()

    f = extract("Great hooks win. What would you add?", author_followers=900)
    prediction = predict_z(seeded, "proj", f)
    assert prediction is not None


def test_rewriter_uses_similarity_when_swatches_exist(seeded: Session) -> None:
    from launcher.models import Draft
    from launcher.swipes import archive_swatch

    winner = Draft(text="Distribution beats marketing. What would you add?", project_id="proj")
    seeded.add(winner)
    seeded.flush()
    archive_swatch(seeded, winner.id)

    d = Draft(text="Distribution beats marketing every single day.", project_id="proj")
    seeded.add(d)
    seeded.flush()
    train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    result = rewrite_flow(seeded, d.id, HeuristicProvider(), n=2)
    assert result.top
