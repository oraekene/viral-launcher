from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from launcher.launches import (
    apply_snapshot,
    checklist_for,
    log_intervention,
    register_launch,
)
from launcher.models import LaunchEvent


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
        checklist=checklist_for(event.protocol_fired),
        interventions=list(event.interventions or []),
    )


def build_launches_router(
    get_session: Callable[[], Iterator[Session]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/launches", status_code=201, response_model=LaunchOut)
    def create_launch(data: LaunchIn, session: Session = Depends(get_session)) -> LaunchOut:
        try:
            event = register_launch(
                session, data.draft_id, data.post_external_id, data.variant_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _launch_out(event)

    @router.get("/launches/{launch_id}", response_model=LaunchOut)
    def get_launch(launch_id: int, session: Session = Depends(get_session)) -> LaunchOut:
        event = session.get(LaunchEvent, launch_id)
        if event is None:
            raise HTTPException(status_code=404, detail="launch not found")
        return _launch_out(event)

    @router.post("/launches/{launch_id}/snapshot", response_model=LaunchOut)
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

    @router.post(
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

    return router
