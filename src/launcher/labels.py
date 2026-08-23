from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from launcher.models import AccountLabel, utcnow

LABEL_STALENESS = timedelta(days=30)


def record_label(
    session: Session,
    label_name: str,
    meaning: str | None,
    source: str = "manual",
) -> AccountLabel:
    label = AccountLabel(label_name=label_name, meaning=meaning, source=source)
    session.add(label)
    session.flush()
    return label


def fresh_labels(session: Session) -> list[AccountLabel]:
    cutoff = utcnow() - LABEL_STALENESS
    return (
        session.query(AccountLabel)
        .filter(AccountLabel.observed_at >= cutoff)
        .order_by(AccountLabel.observed_at.desc())
        .all()
    )


def label_warnings(session: Session) -> list[str]:
    return [
        f"account label {label.label_name!r}"
        + (f" ({label.meaning})" if label.meaning else "")
        + ": reach may be limited; check Under the Hood before investing in a post"
        for label in fresh_labels(session)
    ]
