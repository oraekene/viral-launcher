from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from launcher import __version__
from launcher.features import extract
from launcher.gate import GateReport, load_engine
from launcher.models import CostEvent, Draft, GateRule, ParamVersion
from launcher.seed import seed_all


class DraftIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
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


def _report_lines(report: GateReport) -> list[GateLineOut]:
    return [
        GateLineOut(
            rule_id=line.rule_id,
            verdict=line.verdict,
            detail=line.detail,
            source_note=line.source_note,
        )
        for line in report.lines
    ]


def _draft_out(draft: Draft) -> DraftOut:
    return DraftOut(
        id=draft.id,
        text=draft.text,
        verdict=draft.verdict,
        gate_report=[GateLineOut(**line) for line in (draft.gate_report or [])],
        created_at=draft.created_at,
    )


def create_app(session_factory: sessionmaker[Session]) -> FastAPI:
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
            author_followers=data.author_followers,
            mutuals_count=data.mutuals_count,
            scheduled_at=data.scheduled_at,
            allow_premium_length=data.allow_premium_length,
            verdict=report.verdict,
            gate_report=[line.model_dump() for line in _report_lines(report)],
        )
        session.add(draft)
        session.flush()
        return _draft_out(draft)

    @app.get("/drafts/{draft_id}", response_model=DraftOut)
    def get_draft(draft_id: int, session: Session = Depends(get_session)) -> DraftOut:
        draft = session.get(Draft, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="draft not found")
        return _draft_out(draft)

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

    return app
