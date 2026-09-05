from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.calibration import (
    CalibrationReport,
    run_calibration,
    should_retrain,
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


def test_retrain_on_drift(seeded: Session) -> None:
    model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    ref = model.training_winner_share
    drifted_share = min(ref * 2.0, 0.95)
    assert ref > 0.05
    drifted = SyntheticOutcomeSource(n=300, winner_share=drifted_share)
    assert should_retrain(model, drifted.load_outcomes("proj")) is True


def test_no_retrain_when_stable(seeded: Session) -> None:
    model = train_predictor(seeded, "proj", SyntheticOutcomeSource(n=300))
    ref = model.training_winner_share
    stable = SyntheticOutcomeSource(n=300, winner_share=max(ref * 0.99, 0.02))
    assert should_retrain(model, stable.load_outcomes("proj")) is False


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