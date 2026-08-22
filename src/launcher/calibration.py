from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import NamedTuple

from sqlalchemy.orm import Session

from launcher.models import ParamVersion, PredictorModel, utcnow
from launcher.outcomes import (
    LauncherOutcomeRow,
    LauncherOutcomeSource,
    OutcomeRow,
    SyntheticLauncherOutcomeSource,
)
from launcher.predictor import MIN_EVENTS, active_model, train_predictor

MIN_EVIDENCE = 100
DRIFT_THRESHOLD = 0.20
MONTH = timedelta(days=30)


@dataclass(frozen=True)
class FlaggedVeto:
    rule_name: str
    winner_count: int


@dataclass(frozen=True)
class CalibrationReport:
    project_id: str
    calibrated: bool
    n_outcomes: int
    winner_share: float
    new_z_trigger: float | None = None
    flagged_vetoes: list[FlaggedVeto] = field(default_factory=list)
    retrained: bool = False
    reason: str = ""


class _LauncherAsTrainingSource:
    def __init__(self, rows: list[LauncherOutcomeRow]) -> None:
        self._rows = rows

    def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
        return [
            OutcomeRow(features=r.features, z60=r.z60, value_flag=r.value_flag)
            for r in self._rows
        ]


def should_retrain(
    session: Session,
    model: PredictorModel,
    rows: list[LauncherOutcomeRow],
) -> bool:
    if len(rows) < MIN_EVENTS:
        return False
    if utcnow() - model.trained_at >= MONTH:
        return True
    reference = model.training_winner_share or 0.5
    recent = sum(r.value_flag for r in rows) / len(rows)
    if reference <= 0.0:
        return recent > 0.0
    return abs(recent - reference) / reference > DRIFT_THRESHOLD


def _best_f1_threshold(rows: list[LauncherOutcomeRow]) -> tuple[float, float]:
    candidates = sorted({r.z60 for r in rows})
    best_t = 2.5
    best_f1 = -1.0
    for t in candidates:
        tp = fp = fn = 0
        for r in rows:
            pred = r.z60 >= t
            if pred and r.value_flag:
                tp += 1
            elif pred and not r.value_flag:
                fp += 1
            elif not pred and r.value_flag:
                fn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )
        if f1 > best_f1:
            best_f1 = f1
            best_t = t
    return round(best_t, 4), round(best_f1, 4)


def run_calibration(
    session: Session,
    project_id: str,
    source: LauncherOutcomeSource,
) -> CalibrationReport:
    rows = source.load_outcomes(project_id)

    if len(rows) < MIN_EVIDENCE:
        return CalibrationReport(
            project_id=project_id,
            calibrated=False,
            n_outcomes=len(rows),
            winner_share=(
                round(sum(r.value_flag for r in rows) / len(rows), 4) if rows else 0.0
            ),
            reason=f"insufficient evidence: {len(rows)} of {MIN_EVIDENCE} required outcomes",
        )

    winner_share = sum(r.value_flag for r in rows) / len(rows)

    new_trigger, _f1 = _best_f1_threshold(rows)
    pv = session.query(ParamVersion).filter_by(key="z.trigger").one()
    pv.value = new_trigger
    pv.status = "calibrated"
    pv.last_fit_at = utcnow()

    veto_winners: dict[str, int] = {}
    for r in rows:
        if r.value_flag:
            for name in r.fired_vetoes:
                veto_winners[name] = veto_winners.get(name, 0) + 1
    flagged = [
        FlaggedVeto(rule_name=name, winner_count=count)
        for name, count in sorted(veto_winners.items())
    ]

    retrained = False
    reason = "z.trigger refit on launcher outcomes"
    model = active_model(session, project_id)
    if model is not None and should_retrain(session, model, rows):
        train_predictor(session, project_id, _LauncherAsTrainingSource(rows))
        retrained = True
        reason += "; predictor retrained (drift or age threshold hit)"

    return CalibrationReport(
        project_id=project_id,
        calibrated=True,
        n_outcomes=len(rows),
        winner_share=round(winner_share, 4),
        new_z_trigger=new_trigger,
        flagged_vetoes=flagged,
        retrained=retrained,
        reason=reason,
    )
