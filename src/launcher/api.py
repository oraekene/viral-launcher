from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from launcher import __version__
from launcher.config import Settings
from launcher.drafts_routes import GateLineOut, build_drafts_router
from launcher.labels import fresh_labels, record_label
from launcher.launches_routes import build_launches_router
from launcher.models import (
    AccountLabel,
    CostEvent,
    GateRule,
    ParamVersion,
    Swatch,
)
from launcher.params import ParamStore
from launcher.models_routes import build_models_router
from launcher.rewriter import (
    VariantProvider,
    default_provider,
)
from launcher.seed import seed_all
from launcher.outcomes import stage_radar_outcomes
from launcher.swipes import archive_swatch, list_swatches


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

    app.include_router(
        build_drafts_router(get_session=get_session, get_provider=get_provider)
    )
    app.include_router(build_models_router(get_session=get_session))
    app.include_router(build_launches_router(get_session=get_session))

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
