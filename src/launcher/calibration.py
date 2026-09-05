from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta, timezone

from sqlalchemy.orm import Session

from launcher.metrics import precision_recall
from launcher.models import PredictorModel, utcnow
from launcher.outcomes import (
    OutcomeRow,
    OutcomeSource,
)
from launcher.predictor import MIN_EVENTS, active_model, train_predictor


@dataclass(frozen=True)
class CalibrationConfig:
    min_evidence: int = 100
    min_train_events: int = MIN_EVENTS
    max_model_age: timedelta = timedelta(days=30)
    drift_threshold: float = 0.20


@dataclass(frozen=True)
class FlaggedVeto:
    rule_name: str
    winner_count: int


@dataclass(frozen=True)
class CalibrationDecision:
    """Pure policy outcome: deciding needs rows and plain values, never the DB."""

    calibrated: bool
    n_outcomes: int
    winner_share: float
    new_z_trigger: float | None = None
    flagged_vetoes: tuple[FlaggedVeto, ...] = ()
    retrain: bool = False
    writeback: bool = False
    reason: str = ""


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
        trained_at = trained_at.replace(tzinfo=timezone.utc)
    return utcnow() - trained_at


def decide_calibration(
    rows: list[OutcomeRow],
    *,
    model_age: timedelta | None,
    training_share: float | None,
    trusted: bool,
    config: CalibrationConfig = CalibrationConfig(),
) -> CalibrationDecision:
    """Pure calibration policy: evidence, drift, and writeback permission
    from rows and plain values. No session, no model row, no clock."""
    if len(rows) < config.min_evidence:
        winner_share = sum(r.value_flag for r in rows) / len(rows) if rows else 0.0
        return CalibrationDecision(
            calibrated=False,
            n_outcomes=len(rows),
            winner_share=round(winner_share, 4),
            reason=(
                f"insufficient evidence: {len(rows)} of "
                f"{config.min_evidence} required outcomes"
            ),
        )

    winner_share = sum(r.value_flag for r in rows) / len(rows)
    new_trigger, _f1 = _best_f1_threshold(rows)
    veto_winners: dict[str, int] = {}
    for r in rows:
        if r.value_flag:
            for name in r.fired_vetoes:
                veto_winners[name] = veto_winners.get(name, 0) + 1
    flagged = tuple(
        FlaggedVeto(rule_name=name, winner_count=count)
        for name, count in sorted(veto_winners.items())
    )

    retrain = False
    if model_age is not None and len(rows) >= config.min_train_events:
        if model_age >= config.max_model_age:
            retrain = True
        else:
            reference = training_share if training_share else 0.5
            recent = winner_share
            if reference <= 0.0:
                retrain = recent > 0.0
            else:
                retrain = abs(recent - reference) / reference > config.drift_threshold

    reason = "z.trigger refit computed on launcher outcomes"
    if retrain:
        reason += "; predictor retrained (drift or age threshold hit)"

    return CalibrationDecision(
        calibrated=True,
        n_outcomes=len(rows),
        winner_share=round(winner_share, 4),
        new_z_trigger=new_trigger,
        flagged_vetoes=flagged,
        retrain=retrain,
        writeback=trusted and model_age is not None,
        reason=reason,
    )


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
    config: CalibrationConfig = CalibrationConfig(),
) -> CalibrationReport:
    rows = source.load_outcomes(project_id)
    model = active_model(session, project_id)
    decision = decide_calibration(
        rows,
        model_age=_model_age(model) if model is not None else None,
        training_share=model.training_winner_share if model is not None else None,
        trusted=source.is_trusted,
        config=config,
    )
    if not decision.calibrated:
        return CalibrationReport(
            project_id=project_id,
            calibrated=False,
            applied=False,
            n_outcomes=decision.n_outcomes,
            winner_share=decision.winner_share,
            reason=decision.reason,
        )

    retrained = False
    if model is not None and decision.retrain:
        train_predictor(session, project_id, _StaticSource(rows))
        retrained = True
        model = active_model(session, project_id)

    applied = False
    reason = decision.reason
    if decision.writeback and model is not None:
        model.calibrated_z_trigger = decision.new_z_trigger
        model.status = "calibrated"
        applied = True
        reason += "; written to the project's active model"

    return CalibrationReport(
        project_id=project_id,
        calibrated=True,
        applied=applied,
        n_outcomes=decision.n_outcomes,
        winner_share=decision.winner_share,
        new_z_trigger=decision.new_z_trigger,
        flagged_vetoes=[
            FlaggedVeto(rule_name=f.rule_name, winner_count=f.winner_count)
            for f in decision.flagged_vetoes
        ],
        retrained=retrained,
        reason=reason,
    )
