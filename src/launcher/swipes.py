from __future__ import annotations

from sqlalchemy.orm import Session

from launcher.drafts import resolve_candidate_text
from launcher.models import Swatch


def archive_swatch(
    session: Session,
    draft_id: int,
    variant_id: int | None = None,
    actual_z: float | None = None,
) -> Swatch:
    draft, text = resolve_candidate_text(session, draft_id, variant_id)

    score = 0.0
    score_kind = "interim"
    gate_lines: list[dict[str, str]] = list(draft.gate_report or [])

    if variant_id is not None:
        from launcher.models import DraftVariant

        variant = session.get(DraftVariant, variant_id)
        if variant is None:
            raise ValueError(f"variant {variant_id} not found for draft {draft_id}")
        score = variant.score
        score_kind = variant.score_kind or "interim"
        gate_lines = list(variant.gate_lines or [])

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
