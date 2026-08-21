from __future__ import annotations

from sqlalchemy.orm import Session

from launcher.params import seed_params
from launcher.rules_seed import seed_rules


def seed_all(session: Session) -> None:
    seed_params(session)
    seed_rules(session)
