from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.outcomes import (
    RadarOutcomeSource,
    StagedLauncherOutcomeSource,
    SyntheticLauncherOutcomeSource,
    SyntheticOutcomeSource,
    outcome_source,
)


def test_factory_radar_training_source(session: Session) -> None:
    assert isinstance(outcome_source("radar", session, n=10), RadarOutcomeSource)


def test_factory_synthetic_training_source(session: Session) -> None:
    source = outcome_source("synthetic", session, n=10)
    assert isinstance(source, SyntheticOutcomeSource)
    assert len(source.load_outcomes("proj")) == 10


def test_factory_radar_calibration_source(session: Session) -> None:
    assert isinstance(
        outcome_source("radar", session, n=10, launcher=True),
        StagedLauncherOutcomeSource,
    )


def test_factory_synthetic_calibration_source(session: Session) -> None:
    source = outcome_source("synthetic", session, n=10, launcher=True)
    assert isinstance(source, SyntheticLauncherOutcomeSource)
    assert len(source.load_outcomes("proj")) == 10


def test_factory_unknown_source_raises(session: Session) -> None:
    with pytest.raises(ValueError):
        outcome_source("nope", session, n=10)
