from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.outcomes import (
    StagedOutcomeSource,
    SyntheticOutcomeSource,
    outcome_source,
    stage_radar_outcomes,
)
from launcher.calibration import run_calibration
from launcher.params import seed_params
from launcher.predictor import train_predictor
from launcher.rules_seed import seed_rules


def test_factory_radar_returns_staged_source(session: Session) -> None:
    assert isinstance(outcome_source("radar", session, n=10), StagedOutcomeSource)


def test_factory_synthetic_returns_synthetic_source(session: Session) -> None:
    source = outcome_source("synthetic", session, n=10)
    assert isinstance(source, SyntheticOutcomeSource)
    assert len(source.load_outcomes("proj")) == 10


def test_factory_sources_carry_provenance_and_trust(session: Session) -> None:
    staged = outcome_source("radar", session, n=10)
    assert staged.provenance == "radar-staged"
    assert staged.is_trusted is True
    synthetic = outcome_source("synthetic", session, n=10)
    assert synthetic.provenance == "synthetic"
    assert synthetic.is_trusted is False


def test_factory_unknown_source_raises(session: Session) -> None:
    with pytest.raises(ValueError):
        outcome_source("nope", session, n=10)


def _seeded(session: Session) -> Session:
    seed_params(session)
    seed_rules(session)
    session.commit()
    return session


def test_unified_synthetic_source_serves_both_paths(session: Session) -> None:
    session = _seeded(session)
    source = SyntheticOutcomeSource(n=250, winner_share=0.4)
    model = train_predictor(session, "proj", source)
    report = run_calibration(session, "proj", source)
    assert model.n_events == 250
    assert report.n_outcomes == 250
    assert report.calibrated is True
    assert report.applied is False
    assert model.training_winner_share == pytest.approx(0.4, abs=0.1)


def test_unified_staged_source_serves_both_paths(session: Session) -> None:
    session = _seeded(session)
    staged = [
        {
            "features": r.features,
            "z60": r.z60,
            "value_flag": r.value_flag,
            "fired_vetoes": list(r.fired_vetoes),
        }
        for r in SyntheticOutcomeSource(n=250, winner_share=0.4).load_outcomes("proj")
    ]
    assert stage_radar_outcomes(session, "proj", staged) == 250
    source = StagedOutcomeSource(session)
    model = train_predictor(session, "proj", source)
    report = run_calibration(session, "proj", source)
    assert model.n_events == 250
    assert report.calibrated is True
    assert report.applied is True
    assert model.status == "calibrated"
