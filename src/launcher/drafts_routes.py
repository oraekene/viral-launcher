from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from launcher.cost import BudgetExceeded
from launcher.drafts import score_draft as score_draft_service
from launcher.features import extract
from launcher.gate import load_engine
from launcher.labels import label_warnings
from launcher.models import CostEvent, Draft, DraftVariant
from launcher.rewriter import RewriteResult, VariantProvider, rewrite_flow, try_rewrite_flow


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


class ScoreOut(BaseModel):
    scorer: Literal["predictor", "interim"]
    predicted_z: float | None
    band_width: float | None = None
    model_id: int | None = None
    model_status: str | None = None
    gate_verdict: str


def _draft_out(draft: Draft, warnings: list[str] | None = None) -> DraftOut:
    return DraftOut(
        id=draft.id,
        text=draft.text,
        verdict=draft.verdict,
        gate_report=[GateLineOut(**line) for line in (draft.gate_report or [])],
        label_warnings=warnings or [],
        created_at=draft.created_at,
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


def build_drafts_router(
    get_session: Callable[[], Iterator[Session]],
    get_provider: Callable[..., VariantProvider],
) -> APIRouter:
    router = APIRouter()

    @router.post("/drafts", status_code=201, response_model=DraftOut)
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

    @router.get("/drafts/{draft_id}", response_model=DraftOut)
    def get_draft(draft_id: int, session: Session = Depends(get_session)) -> DraftOut:
        draft = session.get(Draft, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="draft not found")
        return _draft_out(draft, label_warnings(session))

    @router.post("/drafts/{draft_id}/rewrite", response_model=RewriteOut)
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

    @router.get("/drafts/{draft_id}/variants", response_model=list[VariantRowOut])
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

    @router.get("/drafts/{draft_id}/costs", response_model=list[CostEventOut])
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

    @router.post("/drafts/batch", response_model=BatchOut)
    def batch_drafts(
        data: BatchIn, session: Session = Depends(get_session)
    ) -> BatchOut:
        results: list[BatchResultOut] = []
        for item in data.items:
            draft_out = create_draft(item, session)
            rewrite_out: RewriteOut | None = None
            if data.rewrite:
                attempt = try_rewrite_flow(
                    session, draft_out.id, get_provider(session), n=data.n
                )
                if attempt.result is not None:
                    rewrite_out = _rewrite_out(attempt.result)
                else:
                    rewrite_out = RewriteOut(
                        draft_id=draft_out.id,
                        top=[],
                        generated=0,
                        vetoed_count=0,
                        cost_usd=0.0,
                        error=attempt.error,
                    )
            results.append(BatchResultOut(draft=draft_out, rewrite=rewrite_out))
        return BatchOut(results=results)

    @router.post("/drafts/{draft_id}/score", response_model=ScoreOut)
    def score_draft(draft_id: int, session: Session = Depends(get_session)) -> ScoreOut:
        try:
            result = score_draft_service(session, draft_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        report, scored = result.report, result.scored
        if scored.kind == "interim":
            return ScoreOut(
                scorer="interim",
                predicted_z=None,
                band_width=scored.band_width,
                gate_verdict=report.verdict,
            )
        return ScoreOut(
            scorer="predictor",
            predicted_z=scored.score,
            band_width=scored.band_width,
            model_id=scored.model_id,
            model_status=scored.model_status,
            gate_verdict=report.verdict,
        )

    return router
