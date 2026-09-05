from __future__ import annotations

from sqlalchemy.orm import Session

from launcher.drafts import DraftStore
from launcher.models import Swatch


def archive_swatch(
    session: Session,
    draft_id: int,
    variant_id: int | None = None,
    actual_z: float | None = None,
) -> Swatch:
    candidate = DraftStore(session).resolve_candidate(draft_id, variant_id)
    draft, text = candidate.draft, candidate.text

    score = 0.0
    score_kind = "interim"
    gate_lines: list[dict[str, str]] = list(draft.gate_report or [])

    if candidate.variant is not None:
        score = candidate.variant.score
        score_kind = candidate.variant.score_kind or "interim"
        gate_lines = list(candidate.variant.gate_lines or [])

    swatch = Swatch(
        draft_id=draft_id,
        variant_id=variant_id,
        project_id=draft.project_id,
        text=text,
        score=score,
        score_kind=score_kind,
        actual_z=actual_z,
        gate_lines=gate_lines,
    )
    session.add(swatch)
    session.flush()
    return swatch


def list_swatches(session: Session, project_id: str | None = None) -> list[Swatch]:
    query = session.query(Swatch).order_by(Swatch.id.desc())
    if project_id is not None:
        query = query.filter_by(project_id=project_id)
    return list(query.limit(500).all())
