from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, AsyncIterator, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from launcher import __version__
from launcher.config import Settings
from launcher.cost import BudgetExceeded
from launcher.features import extract
from launcher.gate import GateReport, load_engine
from launcher.calibration import CalibrationReport, run_calibration
from launcher.launches import (
    apply_snapshot,
    checklist_for,
    log_intervention,
    register_launch,
)
from launcher.labels import fresh_labels, label_warnings, record_label
from launcher.models import (
    AccountLabel,
    CostEvent,
    Draft,
    DraftVariant,
    GateRule,
    LaunchEvent,
    ParamVersion,
    PredictorModel,
    Swatch,
)
from launcher.params import ParamStore
from launcher.predictor import active_model, predict_z, train_predictor
from launcher.rewriter import (
    RewriteResult,
    VariantProvider,
    default_provider,
    rewrite_flow,
)
from launcher.seed import seed_all
from launcher.outcomes import (
    LauncherOutcomeSource,
    RadarOutcomeSource,
    StagedLauncherOutcomeSource,
    SyntheticLauncherOutcomeSource,
    SyntheticOutcomeSource,
    stage_radar_outcomes,
)
from launcher.similarity import max_swatch_similarity
from launcher.swipes import archive_swatch, list_swatches


class DraftIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    project_id: str | None = Field(default=None, max_length=64)
    author_followers: int | None = None
    mutuals_count: int | None = None
    scheduled_at: datetime | None = None
    allow_premium_length: bool = False


class GateLineOut(BaseModel):
    rule_id: str
    verdict: str
    detail: str
    source_note: str


class DraftOut(BaseModel):
    id: int
    text: str
    verdict: str | None
    gate_report: list[GateLineOut]
    label_warnings: list[str]
    created_at: datetime


class RuleOut(BaseModel):
    id: int
    name: str
    position: int
    param_ref: str | None
    source_note: str
    enabled: bool


class ParamOut(BaseModel):
    key: str
    value: float
    status: str
    source_note: str


class CostSummaryOut(BaseModel):
    total_usd: float
    events: int


class RewriteIn(BaseModel):
    n: int | None = Field(default=None, ge=1, le=50)


class RankedVariantOut(BaseModel):
    id: int
    text: str
    score: float
    reasons: list[str]
    gate_lines: list[GateLineOut]


class RewriteOut(BaseModel):
    draft_id: int
    top: list[RankedVariantOut]
    generated: int
    vetoed_count: int
    cost_usd: float
    error: str | None = None


class VariantRowOut(BaseModel):
    id: int
    text: str
    variant_index: int
    score: float
    reasons: list[str]
    gate_lines: list[GateLineOut]
    vetoed: bool


class CostEventOut(BaseModel):
    kind: str
    usd: float
    tokens_in: int
    tokens_out: int
    note: str | None


class BatchIn(BaseModel):
    items: list[DraftIn] = Field(min_length=1, max_length=100)
    rewrite: bool = False
    n: int | None = Field(default=None, ge=1, le=50)


class BatchResultOut(BaseModel):
    draft: DraftOut
    rewrite: RewriteOut | None


class BatchOut(BaseModel):
    results: list[BatchResultOut]


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


class ScoreOut(BaseModel):
    scorer: Literal["predictor", "interim"]
    predicted_z: float | None
    band_width: float | None = None
    model_id: int | None = None
    model_status: str | None = None


class LaunchIn(BaseModel):
    draft_id: int
    variant_id: int | None = None
    post_external_id: str | None = Field(default=None, max_length=64)


class SnapshotIn(BaseModel):
    actual_z_t10: float


class InterventionIn(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=256)


class LaunchOut(BaseModel):
    id: int
    draft_id: int
    variant_id: int | None
    post_external_id: str | None
    predicted_z: float
    band_width: float
    scorer: str
    actual_z_t10: float | None
    protocol_fired: str | None
    checklist: list[str]
    interventions: list[dict[str, str]]


class SwatchIn(BaseModel):
    draft_id: int
    variant_id: int | None = None
    actual_z: float | None = Field(default=None, ge=0.0)


class SwatchOut(BaseModel):
    id: int
    draft_id: int
    variant_id: int | None
    project_id: str | None
    text: str
    score: float
    score_kind: str
    actual_z: float | None
    gate_lines: list[GateLineOut]


class CalibrationIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=64)
    source: Literal["synthetic", "radar"] = "synthetic"
    n: int | None = Field(default=None, ge=100, le=100_000)
    winner_share: float | None = Field(default=None, gt=0.0, lt=1.0)


class OutcomeRowIn(BaseModel):
    features: dict[str, float]
    z60: float
    value_flag: bool
    fired_vetoes: list[str] = Field(default_factory=list, max_length=16)


class ImportIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=64)
    rows: list[OutcomeRowIn] = Field(min_length=1, max_length=10_000)


class LabelIn(BaseModel):
    label_name: str = Field(min_length=1, max_length=128)
    meaning: str | None = Field(default=None, max_length=512)


class LabelOut(BaseModel):
    id: int
    label_name: str
    meaning: str | None
    source: str
    observed_at: datetime


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


def _report_lines(report: GateReport) -> list[GateLineOut]:
    return [GateLineOut(**line.as_dict()) for line in report.lines]


def _draft_out(draft: Draft, label_warnings: list[str] | None = None) -> DraftOut:
    return DraftOut(
        id=draft.id,
        text=draft.text,
        verdict=draft.verdict,
        gate_report=[GateLineOut(**line) for line in (draft.gate_report or [])],
        label_warnings=label_warnings or [],
        created_at=draft.created_at,
    )


def create_app(
    session_factory: sessionmaker[Session],
    settings: Settings | None = None,
    provider: VariantProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with session_factory() as session:
            seed_all(session)
            session.commit()
        yield

    app = FastAPI(title="launcher", version=__version__, lifespan=lifespan)

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_provider(session: Session = Depends(get_session)) -> VariantProvider:
        if provider is not None:
            return provider
        return default_provider(resolved_settings, ParamStore(session))

    @app.post("/drafts", status_code=201, response_model=DraftOut)
    def create_draft(
        data: DraftIn, session: Session = Depends(get_session)
    ) -> DraftOut:
        engine = load_engine(session)
        features = extract(
            data.text,
            author_followers=data.author_followers,
            mutuals_count=data.mutuals_count,
            scheduled_at=data.scheduled_at,
            allow_premium_length=data.allow_premium_length,
        )
        report = engine.evaluate(features)
        draft = Draft(
            text=data.text,
            project_id=data.project_id,
            author_followers=data.author_followers,
            mutuals_count=data.mutuals_count,
            scheduled_at=data.scheduled_at,
            allow_premium_length=data.allow_premium_length,
            verdict=report.verdict,
            gate_report=[line.as_dict() for line in report.lines],
        )
        session.add(draft)
        session.flush()
        return _draft_out(draft, label_warnings(session))

    @app.get("/drafts/{draft_id}", response_model=DraftOut)
    def get_draft(draft_id: int, session: Session = Depends(get_session)) -> DraftOut:
        draft = session.get(Draft, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="draft not found")
        return _draft_out(draft, label_warnings(session))

    @app.get("/rules", response_model=list[RuleOut])
    def list_rules(session: Session = Depends(get_session)) -> list[RuleOut]:
        rules = session.query(GateRule).order_by(GateRule.position).all()
        return [
            RuleOut(
                id=r.id,
                name=r.name,
                position=r.position,
                param_ref=r.param_ref,
                source_note=r.source_note,
                enabled=r.enabled,
            )
            for r in rules
        ]

    @app.post("/rules/{rule_id}/toggle", response_model=RuleOut)
    def toggle_rule(rule_id: int, session: Session = Depends(get_session)) -> RuleOut:
        rule = session.get(GateRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="rule not found")
        rule.enabled = not rule.enabled
        return RuleOut(
            id=rule.id,
            name=rule.name,
            position=rule.position,
            param_ref=rule.param_ref,
            source_note=rule.source_note,
            enabled=rule.enabled,
        )

    @app.get("/params", response_model=list[ParamOut])
    def list_params(session: Session = Depends(get_session)) -> list[ParamOut]:
        rows = session.query(ParamVersion).order_by(ParamVersion.key).all()
        return [
            ParamOut(
                key=p.key, value=p.value, status=p.status, source_note=p.source_note
            )
            for p in rows
        ]

    @app.get("/costs", response_model=CostSummaryOut)
    def cost_summary(session: Session = Depends(get_session)) -> CostSummaryOut:
        events = session.query(CostEvent).all()
        return CostSummaryOut(
            total_usd=round(sum(e.usd for e in events), 6), events=len(events)
        )

    @app.post("/drafts/{draft_id}/rewrite", response_model=RewriteOut)
    def rewrite_draft(
        draft_id: int,
        data: RewriteIn,
        session: Session = Depends(get_session),
        variant_provider: VariantProvider = Depends(get_provider),
    ) -> RewriteOut:
        try:
            result = rewrite_flow(session, draft_id, variant_provider, n=data.n)
        except BudgetExceeded as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _rewrite_out(result)

    @app.get("/drafts/{draft_id}/variants", response_model=list[VariantRowOut])
    def list_variants(
        draft_id: int, session: Session = Depends(get_session)
    ) -> list[VariantRowOut]:
        if session.get(Draft, draft_id) is None:
            raise HTTPException(status_code=404, detail="draft not found")
        rows = (
            session.query(DraftVariant)
            .filter_by(draft_id=draft_id)
            .order_by(DraftVariant.variant_index)
            .all()
        )
        return [
            VariantRowOut(
                id=r.id,
                text=r.text,
                variant_index=r.variant_index,
                score=r.score,
                reasons=list(r.reasons or []),
                gate_lines=[GateLineOut(**line) for line in (r.gate_lines or [])],
                vetoed=r.vetoed,
            )
            for r in rows
        ]

    @app.get("/drafts/{draft_id}/costs", response_model=list[CostEventOut])
    def list_draft_costs(
        draft_id: int, session: Session = Depends(get_session)
    ) -> list[CostEventOut]:
        if session.get(Draft, draft_id) is None:
            raise HTTPException(status_code=404, detail="draft not found")
        events = (
            session.query(CostEvent).filter_by(draft_id=draft_id).order_by(CostEvent.id).all()
        )
        return [
            CostEventOut(
                kind=e.kind,
                usd=e.usd,
                tokens_in=e.tokens_in,
                tokens_out=e.tokens_out,
                note=e.note,
            )
            for e in events
        ]

    @app.post("/drafts/batch", response_model=BatchOut)
    def batch_drafts(
        data: BatchIn, session: Session = Depends(get_session)
    ) -> BatchOut:
        results: list[BatchResultOut] = []
        for item in data.items:
            draft_out = create_draft(item, session)
            rewrite_out: RewriteOut | None = None
            if data.rewrite:
                try:
                    result = rewrite_flow(
                        session, draft_out.id, get_provider(session), n=data.n
                    )
                    rewrite_out = _rewrite_out(result)
                except BudgetExceeded as exc:
                    rewrite_out = RewriteOut(
                        draft_id=draft_out.id,
                        top=[],
                        generated=0,
                        vetoed_count=0,
                        cost_usd=0.0,
                        error=str(exc),
                    )
            results.append(BatchResultOut(draft=draft_out, rewrite=rewrite_out))
        return BatchOut(results=results)

    @app.post("/models/train", status_code=201, response_model=ModelOut)
    def train_model(
        data: TrainIn, session: Session = Depends(get_session)
    ) -> ModelOut:
        if data.source == "radar":
            try:
                row = train_predictor(
                    session, data.project_id, RadarOutcomeSource(session)
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return _model_out(row)
        try:
            row = train_predictor(
                session,
                data.project_id,
                SyntheticOutcomeSource(n=data.n or 400),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _model_out(row)

    @app.get("/models", response_model=list[ModelOut])
    def list_models(
        project_id: str | None = None, session: Session = Depends(get_session)
    ) -> list[ModelOut]:
        query = session.query(PredictorModel).order_by(PredictorModel.id.desc())
        if project_id is not None:
            query = query.filter_by(project_id=project_id)
        return [_model_out(m) for m in query.limit(100).all()]

    @app.post("/drafts/{draft_id}/score", response_model=ScoreOut)
    def score_draft(draft_id: int, session: Session = Depends(get_session)) -> ScoreOut:
        draft = session.get(Draft, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="draft not found")
        features = extract(
            draft.text,
            author_followers=draft.author_followers,
            mutuals_count=draft.mutuals_count,
            allow_premium_length=draft.allow_premium_length,
        )
        prediction = predict_z(
            session,
            draft.project_id,
            features,
            swatch_similarity=max_swatch_similarity(session, draft.project_id, draft.text),
        )
        if prediction is None:
            return ScoreOut(scorer="interim", predicted_z=None)
        return ScoreOut(
            scorer="predictor",
            predicted_z=prediction.predicted_z,
            band_width=prediction.band_width,
            model_id=prediction.model_id,
            model_status=prediction.model_status,
        )

    @app.post("/launches", status_code=201, response_model=LaunchOut)
    def create_launch(data: LaunchIn, session: Session = Depends(get_session)) -> LaunchOut:
        try:
            event = register_launch(
                session, data.draft_id, data.post_external_id, data.variant_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _launch_out(event)

    @app.get("/launches/{launch_id}", response_model=LaunchOut)
    def get_launch(launch_id: int, session: Session = Depends(get_session)) -> LaunchOut:
        event = session.get(LaunchEvent, launch_id)
        if event is None:
            raise HTTPException(status_code=404, detail="launch not found")
        return _launch_out(event)

    @app.post("/launches/{launch_id}/snapshot", response_model=LaunchOut)
    def snapshot_launch(
        launch_id: int, data: SnapshotIn, session: Session = Depends(get_session)
    ) -> LaunchOut:
        try:
            event = apply_snapshot(session, launch_id, data.actual_z_t10)
        except ValueError as exc:
            if "already" in str(exc):
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _launch_out(event)

    @app.post(
        "/launches/{launch_id}/interventions",
        status_code=201,
        response_model=LaunchOut,
    )
    def add_intervention(
        launch_id: int,
        data: InterventionIn,
        session: Session = Depends(get_session),
    ) -> LaunchOut:
        try:
            event = log_intervention(session, launch_id, data.action, data.note)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _launch_out(event)

    @app.post("/swatches", status_code=201, response_model=SwatchOut)
    def create_swatch(data: SwatchIn, session: Session = Depends(get_session)) -> SwatchOut:
        try:
            swatch = archive_swatch(session, data.draft_id, data.variant_id, data.actual_z)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _swatch_out(swatch)

    @app.get("/swatches", response_model=list[SwatchOut])
    def get_swatches(
        project_id: str | None = None, session: Session = Depends(get_session)
    ) -> list[SwatchOut]:
        return [_swatch_out(s) for s in list_swatches(session, project_id)]

    @app.post("/calibration/run", response_model=CalibrationReportOut)
    def run_calibration_endpoint(
        data: CalibrationIn, session: Session = Depends(get_session)
    ) -> CalibrationReportOut:
        try:
            source: LauncherOutcomeSource
            if data.source == "radar":
                source = StagedLauncherOutcomeSource(session)
            else:
                source = SyntheticLauncherOutcomeSource(
                    n=data.n or 300, winner_share=data.winner_share or 0.25
                )
            report = run_calibration(session, data.project_id, source)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _calibration_report_out(report)

    @app.post("/outcomes/import", status_code=201)
    def import_outcomes(
        data: ImportIn, session: Session = Depends(get_session)
    ) -> dict[str, int]:
        try:
            imported = stage_radar_outcomes(
                session, data.project_id, [r.model_dump() for r in data.rows]
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"imported": imported}

    @app.get("/calibration/status", response_model=CalibrationStatusOut)
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

    @app.post("/labels", status_code=201)
    def create_label(data: LabelIn, session: Session = Depends(get_session)) -> LabelOut:
        label = record_label(session, data.label_name, data.meaning, "manual")
        return _label_out(label)

    @app.get("/labels", response_model=list[LabelOut])
    def get_labels(
        fresh_only: bool = False, session: Session = Depends(get_session)
    ) -> list[LabelOut]:
        if fresh_only:
            return [_label_out(l) for l in fresh_labels(session)]
        rows = (
            session.query(AccountLabel)
            .order_by(AccountLabel.observed_at.desc())
            .limit(500)
            .all()
        )
        return [_label_out(l) for l in rows]

    return app


def _label_out(label: AccountLabel) -> LabelOut:
    return LabelOut(
        id=label.id,
        label_name=label.label_name,
        meaning=label.meaning,
        source=label.source,
        observed_at=label.observed_at,
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


def _swatch_out(s: Swatch) -> SwatchOut:
    return SwatchOut(
        id=s.id,
        draft_id=s.draft_id,
        variant_id=s.variant_id,
        project_id=s.project_id,
        text=s.text,
        score=s.score,
        score_kind=s.score_kind,
        actual_z=s.actual_z,
        gate_lines=[GateLineOut(**line) for line in (s.gate_lines or [])],
    )


def _checklist_for(protocol_fired: str | None) -> list[str]:
    return checklist_for(protocol_fired)


def _launch_out(event: LaunchEvent) -> LaunchOut:
    return LaunchOut(
        id=event.id,
        draft_id=event.draft_id,
        variant_id=event.variant_id,
        post_external_id=event.post_external_id,
        predicted_z=event.predicted_z,
        band_width=event.band_width,
        scorer=event.scorer,
        actual_z_t10=event.actual_z_t10,
        protocol_fired=event.protocol_fired,
        checklist=_checklist_for(event.protocol_fired),
        interventions=list(event.interventions or []),
    )


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


def _rewrite_out(result: RewriteResult) -> RewriteOut:
    return RewriteOut(
        draft_id=result.draft_id,
        top=[
            RankedVariantOut(
                id=v.id,
                text=v.text,
                score=v.score,
                reasons=list(v.reasons),
                gate_lines=[GateLineOut(**line) for line in v.gate_lines],
            )
            for v in result.top
        ],
        generated=result.generated,
        vetoed_count=result.vetoed_count,
        cost_usd=result.cost_usd,
    )
