from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from launcher.models import VoiceBinding
from launcher.models_routes import CalibrationReportOut, FlaggedVetoOut
from launcher.relay import bind_voice, relay_sync


class VoiceIn(BaseModel):
    worker_user_id: str = Field(min_length=1, max_length=64)
    screen_name: str = Field(min_length=1, max_length=64)
    project_id: str = Field(min_length=1, max_length=64)


class VoiceOut(BaseModel):
    worker_user_id: str
    screen_name: str
    project_id: str


class RelayTweetIn(BaseModel):
    id: str
    text: str
    favorite_count: int
    retweet_count: int
    reply_count: int


class RelaySyncIn(BaseModel):
    worker_user_id: str = Field(min_length=1, max_length=64)
    screen_name: str = Field(min_length=1, max_length=64)
    tweets: list[RelayTweetIn] = Field(min_length=1, max_length=10_000)
    author_followers: int | None = Field(default=None, ge=0)
    mutuals_count: int | None = Field(default=None, ge=0)


class RelaySyncOut(BaseModel):
    project_id: str
    staged: int
    calibration: CalibrationReportOut


def _report_out(report: Any) -> CalibrationReportOut:
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


def build_relay_router(
    get_session: Callable[[], Iterator[Session]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/voices", status_code=201, response_model=VoiceOut)
    def bind_voice_endpoint(
        data: VoiceIn, session: Session = Depends(get_session)
    ) -> VoiceOut:
        try:
            row = bind_voice(
                session, data.worker_user_id, data.screen_name, data.project_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return VoiceOut(
            worker_user_id=row.worker_user_id,
            screen_name=row.screen_name,
            project_id=row.project_id,
        )

    @router.get("/voices", response_model=list[VoiceOut])
    def list_voices(
        worker_user_id: str | None = None, session: Session = Depends(get_session)
    ) -> list[VoiceOut]:
        query = session.query(VoiceBinding).order_by(VoiceBinding.id)
        if worker_user_id is not None:
            query = query.filter_by(worker_user_id=worker_user_id)
        return [
            VoiceOut(
                worker_user_id=r.worker_user_id,
                screen_name=r.screen_name,
                project_id=r.project_id,
            )
            for r in query.limit(500).all()
        ]

    @router.post("/outcomes/relay-sync", status_code=201, response_model=RelaySyncOut)
    def relay_sync_endpoint(
        data: RelaySyncIn, session: Session = Depends(get_session)
    ) -> RelaySyncOut:
        try:
            result = relay_sync(
                session,
                data.worker_user_id,
                data.screen_name,
                [t.model_dump() for t in data.tweets],
                author_followers=data.author_followers,
                mutuals_count=data.mutuals_count,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return RelaySyncOut(
            project_id=result.project_id,
            staged=result.staged,
            calibration=_report_out(result.report),
        )

    return router
