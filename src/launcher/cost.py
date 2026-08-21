from __future__ import annotations

from sqlalchemy.orm import Session

from launcher.models import CostEvent


class BudgetExceeded(Exception):
    pass


class CostMeter:
    def __init__(self, session: Session) -> None:
        self._session = session

    def spent(self, draft_id: int) -> float:
        rows = self._session.query(CostEvent).filter_by(draft_id=draft_id).all()
        return sum(e.usd for e in rows)

    def record(
        self,
        draft_id: int,
        kind: str,
        usd: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
        note: str | None = None,
    ) -> CostEvent:
        event = CostEvent(
            draft_id=draft_id,
            kind=kind,
            usd=usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            note=note,
        )
        self._session.add(event)
        self._session.flush()
        return event
