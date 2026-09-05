from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from launcher.calibration import (
    CalibrationConfig,
    CalibrationReport,
    decide_calibration,
    run_calibration,
)
from launcher.models import Base, ParamVersion, PredictorModel
from launcher.outcomes import OutcomeRow, StagedOutcomeSource, SyntheticOutcomeSource, stage_radar_outcomes
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
    report = run_calibration(seeded, "proj", SyntheticOutcomeSource(n=50))
    assert isinstance(report, CalibrationReport)
    assert report.calibrated is False
    assert report.applied is False
    assert report.n_outcomes == 50
    pv = seeded.query(ParamVersion).filter_by(key="z.trigger").one()
    assert pv.status == "pending"
    assert pv.value == 2.5


def test_staged_outcomes_flip_model_calibrated(seeded: Session) -> None:
    train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    rows = [
        {
            "features": r.features,
            "z60": r.z60,
            "value_flag": r.value_flag,
            "fired_vetoes": list(r.fired_vetoes),
        }
        for r in SyntheticOutcomeSource(n=250).load_outcomes("proj")
    ]
    stage_radar_outcomes(seeded, "proj", rows)

    report = run_calibration(
        seeded, "proj", StagedOutcomeSource(seeded)
    )
    assert report.calibrated is True
    assert report.applied is True
    model = seeded.query(PredictorModel).order_by(PredictorModel.id.desc()).first()
    assert model is not None
    assert model.status == "calibrated"
    assert model.calibrated_z_trigger == report.new_z_trigger
    pv = seeded.query(ParamVersion).filter_by(key="z.trigger").one()
    assert pv.status == "pending"


def test_synthetic_run_never_writes_calibrated(seeded: Session) -> None:
    train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    report = run_calibration(seeded, "proj", SyntheticOutcomeSource(n=400))
    assert report.calibrated is True
    assert report.applied is False
    model = seeded.query(PredictorModel).order_by(PredictorModel.id.desc()).first()
    assert model is not None
    assert model.status == "pending"
    assert model.calibrated_z_trigger is None


def test_veto_contradictions_flagged_not_silently_kept(seeded: Session) -> None:
    report = run_calibration(seeded, "proj", SyntheticOutcomeSource(n=400))
    assert isinstance(report.flagged_vetoes, list)
    for flag in report.flagged_vetoes:
        assert flag.rule_name.startswith("negative.")


def _policy_rows(n: int, winners: int) -> list[OutcomeRow]:
    return [
        OutcomeRow(features={}, z60=3.0 if i < winners else 1.0, value_flag=i < winners)
        for i in range(n)
    ]


def test_policy_retrains_on_drift() -> None:
    decision = decide_calibration(
        _policy_rows(300, 150),
        model_age=timedelta(days=1),
        training_share=0.25,
        trusted=False,
    )
    assert decision.retrain is True


def test_policy_holds_when_stable() -> None:
    decision = decide_calibration(
        _policy_rows(300, 75),
        model_age=timedelta(days=1),
        training_share=0.25,
        trusted=False,
    )
    assert decision.retrain is False


def test_calibration_report_counts(seeded: Session) -> None:
    report = run_calibration(seeded, "proj", SyntheticOutcomeSource(n=250))
    assert report.n_outcomes == 250
    assert 0.0 <= report.winner_share <= 1.0


def test_writeback_follows_source_trust_not_type(seeded: Session) -> None:
    class TrustedMemorySource:
        def __init__(self, rows: list[OutcomeRow]) -> None:
            self._rows = rows

        @property
        def provenance(self) -> str:
            return "test-trusted"

        @property
        def is_trusted(self) -> bool:
            return True

        def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
            return list(self._rows)

    train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    rows = SyntheticOutcomeSource(n=250, winner_share=0.4).load_outcomes("proj")
    report = run_calibration(seeded, "proj", TrustedMemorySource(rows))
    assert report.calibrated is True
    assert report.applied is True


def test_policy_decision_needs_no_database() -> None:
    config = CalibrationConfig()
    rows = _policy_rows(300, 75)
    settled = decide_calibration(
        rows,
        model_age=timedelta(days=1),
        training_share=0.25,
        trusted=False,
        config=config,
    )
    assert settled.calibrated is True
    assert settled.retrain is False
    assert settled.writeback is False
    assert settled.n_outcomes == 300

    thin = decide_calibration(
        _policy_rows(10, 3),
        model_age=timedelta(days=1),
        training_share=0.25,
        trusted=False,
        config=config,
    )
    assert thin.calibrated is False

    trusted = decide_calibration(
        rows,
        model_age=timedelta(days=1),
        training_share=0.25,
        trusted=True,
        config=config,
    )
    assert trusted.writeback is True

    drifted = decide_calibration(
        _policy_rows(300, 225),
        model_age=timedelta(days=1),
        training_share=0.25,
        trusted=False,
        config=config,
    )
    assert drifted.retrain is True

    stale = decide_calibration(
        rows,
        model_age=timedelta(days=60),
        training_share=0.25,
        trusted=False,
        config=config,
    )
    assert stale.retrain is True


def test_retrain_happens_during_run_when_drifted(seeded: Session) -> None:
    model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    ref = model.training_winner_share
    before = seeded.query(PredictorModel).count()
    report = run_calibration(
        seeded,
        "proj",
        SyntheticOutcomeSource(n=300, winner_share=min(ref * 2.0, 0.95)),
    )
    after = seeded.query(PredictorModel).count()
    assert report.retrained is True
    assert after > before