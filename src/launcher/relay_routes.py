from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from launcher.models import VoiceBinding
from launcher.models_routes import CalibrationReportOut, calibration_report_out
from launcher.relay import VoiceKey, bind_voice, relay_sync
from launcher.tenancy import TenantId, require_owner
from launcher.tenancy import tenant_dep as make_tenant_dep


class VoiceIn(BaseModel):
    worker_user_id: str = Field(min_length=1, max_length=64)
    screen_name: str = Field(min_length=1, max_length=64)
    project_id: str = Field(min_length=1, max_length=64)
    viral_floor: float | None = Field(default=None, ge=0.0)
    viral_threshold: float | None = Field(default=None, gt=0.0)
    topics: list[str] | None = Field(default=None)


class VoiceOut(BaseModel):
    worker_user_id: str
    screen_name: str
    project_id: str
    viral_floor: float | None
    viral_threshold: float | None
    topics: list[str] | None


class RelayTweetIn(BaseModel):
    id: str
    author: str
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


def build_relay_router(
    get_session: Callable[[], Iterator[Session]],
    get_tenant: Callable[[], TenantId] | None = None,
) -> APIRouter:
    router = APIRouter()
    tenant_dep = make_tenant_dep(get_tenant)

    @router.post("/voices", status_code=201, response_model=VoiceOut)
    def bind_voice_endpoint(
        data: VoiceIn,
        session: Session = Depends(get_session),
        tenant: TenantId = Depends(tenant_dep),
    ) -> VoiceOut:
        require_owner(tenant, data.worker_user_id)
        for topic in data.topics or []:
            if not topic.strip() or len(topic) > 32:
                raise HTTPException(
                    status_code=422, detail="voice topics must be 1-32 chars each"
                )
        try:
            row = bind_voice(
                session,
                VoiceKey(data.worker_user_id, data.screen_name),
                data.project_id,
                viral_floor=data.viral_floor,
                viral_threshold=data.viral_threshold,
                topics=data.topics,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return VoiceOut(
            worker_user_id=row.worker_user_id,
            screen_name=row.screen_name,
            project_id=row.project_id,
            viral_floor=row.viral_floor,
            viral_threshold=row.viral_threshold,
            topics=row.topics,
        )

    @router.get("/voices", response_model=list[VoiceOut])
    def list_voices(
        worker_user_id: str | None = None,
        session: Session = Depends(get_session),
        tenant: TenantId = Depends(tenant_dep),
    ) -> list[VoiceOut]:
        if tenant is not None:
            worker_user_id = tenant
        query = session.query(VoiceBinding).order_by(VoiceBinding.id)
        if worker_user_id is not None:
            query = query.filter_by(worker_user_id=worker_user_id)
        return [
            VoiceOut(
                worker_user_id=r.worker_user_id,
                screen_name=r.screen_name,
                project_id=r.project_id,
                viral_floor=r.viral_floor,
                viral_threshold=r.viral_threshold,
                topics=r.topics,
            )
            for r in query.limit(500).all()
        ]

    @router.post("/outcomes/relay-sync", status_code=201, response_model=RelaySyncOut)
    def relay_sync_endpoint(
        data: RelaySyncIn,
        session: Session = Depends(get_session),
        tenant: TenantId = Depends(tenant_dep),
    ) -> RelaySyncOut:
        require_owner(tenant, data.worker_user_id)
        try:
            result = relay_sync(
                session,
                VoiceKey(data.worker_user_id, data.screen_name),
                [t.model_dump() for t in data.tweets],
                author_followers=data.author_followers,
                mutuals_count=data.mutuals_count,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return RelaySyncOut(
            project_id=result.project_id,
            staged=result.staged,
            calibration=calibration_report_out(result.report),
        )

    return router
