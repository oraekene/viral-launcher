from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.calibration import (
    CalibrationReport,
    SyntheticLauncherOutcomeSource,
    run_calibration,
    should_retrain,
)
from launcher.models import Base, ParamVersion, PredictorModel
from launcher.outcomes import SyntheticOutcomeSource
from launcher.params import seed_params
from launcher.predictor import train_predictor
from launcher.rules_seed import seed_rules


@pytest.fixture()
def seeded(session: Session) -> Session:
    seed_params(session)
    seed_rules(session)
    session.commit()
    return session


def test_refuses_to_calibrate_without_evidence(seeded: Session) -> None:
    report = run_calibration(seeded, "proj", SyntheticLauncherOutcomeSource(n=50))
    assert isinstance(report, CalibrationReport)
    assert report.calibrated is False
    assert report.n_outcomes == 50
    pv = seeded.query(ParamVersion).filter_by(key="z.trigger").one()
    assert pv.status == "pending"


def test_z_trigger_refits_and_flips_calibrated(seeded: Session) -> None:
    report = run_calibration(seeded, "proj", SyntheticLauncherOutcomeSource(n=400))
    assert report.calibrated is True
    pv = seeded.query(ParamVersion).filter_by(key="z.trigger").one()
    assert pv.status == "calibrated"
    assert pv.last_fit_at is not None
    assert 1.0 <= pv.value <= 4.0
    assert report.new_z_trigger is not None


def test_veto_contradictions_flagged_not_silently_kept(seeded: Session) -> None:
    report = run_calibration(seeded, "proj", SyntheticLauncherOutcomeSource(n=400))
    assert isinstance(report.flagged_vetoes, list)
    for flag in report.flagged_vetoes:
        assert flag.rule_name.startswith("negative.")


def test_retrain_on_drift(seeded: Session) -> None:
    model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    ref = model.training_winner_share
    drifted_share = min(ref * 2.0, 0.95)
    assert ref > 0.05
    drifted = SyntheticLauncherOutcomeSource(n=300, winner_share=drifted_share)
    assert should_retrain(seeded, model, drifted.load_outcomes("proj")) is True


def test_no_retrain_when_stable(seeded: Session) -> None:
    model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    ref = model.training_winner_share
    stable = SyntheticLauncherOutcomeSource(n=300, winner_share=max(ref * 0.99, 0.02))
    assert should_retrain(seeded, model, stable.load_outcomes("proj")) is False


def test_calibration_report_counts(seeded: Session) -> None:
    report = run_calibration(seeded, "proj", SyntheticLauncherOutcomeSource(n=250))
    assert report.n_outcomes == 250
    assert 0.0 <= report.winner_share <= 1.0


def test_retrain_happens_during_run_when_drifted(seeded: Session) -> None:
    model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    ref = model.training_winner_share
    before = seeded.query(PredictorModel).count()
    report = run_calibration(
        seeded,
        "proj",
        SyntheticLauncherOutcomeSource(n=300, winner_share=min(ref * 2.0, 0.95)),
    )
    after = seeded.query(PredictorModel).count()
    assert report.retrained is True
    assert after > before