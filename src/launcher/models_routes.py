from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from launcher.calibration import CalibrationReport, run_calibration
from launcher.models import ParamVersion, PredictorModel
from launcher.outcomes import outcome_source
from launcher.predictor import active_model, train_predictor


class TrainIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=64)
    source: Literal["synthetic", "radar"] = "synthetic"
    n: int | None = Field(default=None, ge=200, le=100_000)


class ModelOut(BaseModel):
    id: int
    project_id: str
    trained_at: datetime
    n_events: int
    precision: float
    recall: float
    band_width: float
    status: str
    algorithm: str
    source: str
    feature_importances: dict[str, float]
    calibrated_z_trigger: float | None


class CalibrationIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=64)
    source: Literal["synthetic", "radar"] = "synthetic"
    n: int | None = Field(default=None, ge=100, le=100_000)
    winner_share: float | None = Field(default=None, gt=0.0, lt=1.0)


class FlaggedVetoOut(BaseModel):
    rule_name: str
    winner_count: int


class CalibrationReportOut(BaseModel):
    project_id: str
    calibrated: bool
    applied: bool
    n_outcomes: int
    winner_share: float
    new_z_trigger: float | None
    flagged_vetoes: list[FlaggedVetoOut]
    retrained: bool
    reason: str


class CalibrationStatusParam(BaseModel):
    key: str
    value: float
    status: str
    last_fit_at: datetime | None


class CalibrationStatusOut(BaseModel):
    project_id: str
    params: list[CalibrationStatusParam]
    active_model: ModelOut | None


def _model_out(m: PredictorModel) -> ModelOut:
    return ModelOut(
        id=m.id,
        project_id=m.project_id,
        trained_at=m.trained_at,
        n_events=m.n_events,
        precision=m.precision,
        recall=m.recall,
        band_width=m.band_width,
        status=m.status,
        algorithm=m.algorithm,
        source=m.source,
        feature_importances=dict(m.feature_importances or {}),
        calibrated_z_trigger=m.calibrated_z_trigger,
    )


def _calibration_report_out(report: CalibrationReport) -> CalibrationReportOut:
    return CalibrationReportOut(
        project_id=report.project_id,
        calibrated=report.calibrated,
        applied=report.applied,
        n_outcomes=report.n_outcomes,
        winner_share=report.winner_share,
        new_z_trigger=report.new_z_trigger,
        flagged_vetoes=[
            FlaggedVetoOut(rule_name=f.rule_name, winner_count=f.winner_count)
            for f in report.flagged_vetoes
        ],
        retrained=report.retrained,
        reason=report.reason,
    )


def build_models_router(
    get_session: Callable[[], Iterator[Session]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/models/train", status_code=201, response_model=ModelOut)
    def train_model(
        data: TrainIn, session: Session = Depends(get_session)
    ) -> ModelOut:
        try:
            row = train_predictor(
                session,
                data.project_id,
                outcome_source(data.source, session, n=data.n or 400),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _model_out(row)

    @router.get("/models", response_model=list[ModelOut])
    def list_models(
        project_id: str | None = None, session: Session = Depends(get_session)
    ) -> list[ModelOut]:
        query = session.query(PredictorModel).order_by(PredictorModel.id.desc())
        if project_id is not None:
            query = query.filter_by(project_id=project_id)
        return [_model_out(m) for m in query.limit(100).all()]

    @router.post("/calibration/run", response_model=CalibrationReportOut)
    def run_calibration_endpoint(
        data: CalibrationIn, session: Session = Depends(get_session)
    ) -> CalibrationReportOut:
        try:
            report = run_calibration(
                session,
                data.project_id,
                outcome_source(
                    data.source,
                    session,
                    n=data.n or 300,
                    winner_share=data.winner_share or 0.25,
                    launcher=True,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _calibration_report_out(report)

    @router.get("/calibration/status", response_model=CalibrationStatusOut)
    def calibration_status(
        project_id: str, session: Session = Depends(get_session)
    ) -> CalibrationStatusOut:
        keys = ("z.trigger", "band.interim_width")
        rows = (
            session.query(ParamVersion)
            .filter(ParamVersion.key.in_(keys))
            .order_by(ParamVersion.key)
            .all()
        )
        model = active_model(session, project_id)
        return CalibrationStatusOut(
            project_id=project_id,
            params=[
                CalibrationStatusParam(
                    key=r.key,
                    value=r.value,
                    status=r.status,
                    last_fit_at=r.last_fit_at,
                )
                for r in rows
            ],
            active_model=_model_out(model) if model is not None else None,
        )

    return router
