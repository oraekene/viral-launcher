from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.orm import Session

from launcher.metrics import precision_recall
from launcher.models import PredictorModel, utcnow
from launcher.outcomes import (
    OutcomeRow,
    OutcomeSource,
)
from launcher.predictor import MIN_EVENTS, active_model, train_predictor

MIN_EVIDENCE = 100
MAX_MODEL_AGE = timedelta(days=30)
DRIFT_THRESHOLD = 0.20


@dataclass(frozen=True)
class FlaggedVeto:
    rule_name: str
    winner_count: int


@dataclass(frozen=True)
class CalibrationReport:
    project_id: str
    calibrated: bool
    applied: bool
    n_outcomes: int
    winner_share: float
    new_z_trigger: float | None = None
    flagged_vetoes: list[FlaggedVeto] = field(default_factory=list)
    retrained: bool = False
    reason: str = ""


class _StaticSource:
    """In-memory rows as a source, for retraining on calibration evidence."""

    def __init__(self, rows: list[OutcomeRow]) -> None:
        self._rows = rows

    @property
    def provenance(self) -> str:
        return "memory"

    @property
    def is_trusted(self) -> bool:
        return False

    def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
        return list(self._rows)


def _model_age(model: PredictorModel) -> timedelta:
    trained_at = model.trained_at
    if trained_at.tzinfo is None:
        return utcnow().replace(tzinfo=None) - trained_at
    return utcnow() - trained_at


def should_retrain(
    model: PredictorModel,
    rows: list[OutcomeRow],
) -> bool:
    if len(rows) < MIN_EVENTS:
        return False
    if _model_age(model) >= MAX_MODEL_AGE:
        return True
    reference = model.training_winner_share or 0.5
    recent = sum(r.value_flag for r in rows) / len(rows)
    if reference <= 0.0:
        return recent > 0.0
    return abs(recent - reference) / reference > DRIFT_THRESHOLD


def _best_f1_threshold(rows: list[OutcomeRow]) -> tuple[float, float]:
    candidates = sorted({r.z60 for r in rows})
    best_t = 2.5
    best_f1 = -1.0
    flags = [r.value_flag for r in rows]
    for t in candidates:
        pred_flags = [r.z60 >= t for r in rows]
        precision, recall = precision_recall(pred_flags, flags)
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
    source: OutcomeSource,
) -> CalibrationReport:
    rows = source.load_outcomes(project_id)

    if len(rows) < MIN_EVIDENCE:
        winner_share = sum(r.value_flag for r in rows) / len(rows) if rows else 0.0
        return CalibrationReport(
            project_id=project_id,
            calibrated=False,
            applied=False,
            n_outcomes=len(rows),
            winner_share=round(winner_share, 4),
            reason=f"insufficient evidence: {len(rows)} of {MIN_EVIDENCE} required outcomes",
        )

    winner_share = sum(r.value_flag for r in rows) / len(rows)
    new_trigger, _f1 = _best_f1_threshold(rows)

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
    reason = "z.trigger refit computed on launcher outcomes"
    model = active_model(session, project_id)

    source_is_real = source.is_trusted
    applied = False

    if model is not None and should_retrain(model, rows):
        train_predictor(session, project_id, _StaticSource(rows))
        retrained = True
        reason += "; predictor retrained (drift or age threshold hit)"
        model = active_model(session, project_id)

    if source_is_real and model is not None:
        model.calibrated_z_trigger = new_trigger
        model.status = "calibrated"
        applied = True
        reason += "; written to the project's active model"

    return CalibrationReport(
        project_id=project_id,
        calibrated=True,
        applied=applied,
        n_outcomes=len(rows),
        winner_share=round(winner_share, 4),
        new_z_trigger=new_trigger,
        flagged_vetoes=flagged,
        retrained=retrained,
        reason=reason,
    )
