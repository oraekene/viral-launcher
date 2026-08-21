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

    def ensure_budget(self, draft_id: int, cap_usd: float) -> None:
        if self.spent(draft_id) >= cap_usd - 1e-9:
            raise BudgetExceeded(
                f"draft {draft_id} spent ${self.spent(draft_id):.4f} "
                f"of its ${cap_usd:.4f} budget"
            )

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
