from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from launcher import __version__
from launcher.config import Settings
from launcher.cost import BudgetExceeded
from launcher.features import extract
from launcher.gate import GateReport, load_engine
from launcher.models import CostEvent, Draft, DraftVariant, GateRule, ParamVersion
from launcher.params import ParamStore
from launcher.rewriter import (
    RewriteResult,
    VariantProvider,
    default_provider,
    rewrite_flow,
)
from launcher.seed import seed_all


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


def _report_lines(report: GateReport) -> list[GateLineOut]:
    return [GateLineOut(**line.as_dict()) for line in report.lines]


def _draft_out(draft: Draft) -> DraftOut:
    return DraftOut(
        id=draft.id,
        text=draft.text,
        verdict=draft.verdict,
        gate_report=[GateLineOut(**line) for line in (draft.gate_report or [])],
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

    return app


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
