from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.cost import CostMeter
from launcher.models import CostEvent, Draft


@pytest.fixture()
def draft(session: Session) -> Draft:
    d = Draft(text="Some draft text.")
    session.add(d)
    session.flush()
    return d


def test_spent_starts_at_zero(session: Session, draft: Draft) -> None:
    assert CostMeter(session).spent(draft.id) == 0.0


def test_record_accumulates(session: Session, draft: Draft) -> None:
    meter = CostMeter(session)
    meter.record(draft.id, kind="llm", usd=0.03, tokens_in=100, tokens_out=50)
    meter.record(draft.id, kind="llm", usd=0.04, tokens_in=120, tokens_out=60)
    session.commit()
    assert abs(CostMeter(session).spent(draft.id) - 0.07) < 1e-9
    assert session.query(CostEvent).count() == 2


def test_zero_cost_events_do_not_trigger_cap(session: Session, draft: Draft) -> None:
    meter = CostMeter(session)
    meter.record(draft.id, kind="heuristic", usd=0.0)
    session.commit()
    assert CostMeter(session).spent(draft.id) == 0.0
