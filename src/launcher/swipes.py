from __future__ import annotations

from sqlalchemy.orm import Session

from launcher.models import Draft, DraftVariant, Swatch


def archive_swatch(
    session: Session, draft_id: int, variant_id: int | None = None
) -> Swatch:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ValueError(f"draft {draft_id} not found")

    text = draft.text
    gate_lines: list[dict[str, str]] = list(draft.gate_report or [])
    score = 0.0
    score_kind = "interim"

    if variant_id is not None:
        variant = session.get(DraftVariant, variant_id)
        if variant is None or variant.draft_id != draft_id:
            raise ValueError(f"variant {variant_id} not found for draft {draft_id}")
        text = variant.text
        gate_lines = list(variant.gate_lines or [])
        score = variant.score
        score_kind = "predicted" if any("predicted z" in r for r in (variant.reasons or [])) else "interim"

    swatch = Swatch(
        draft_id=draft_id,
        variant_id=variant_id,
        project_id=draft.project_id,
        text=text,
        score=score,
        score_kind=score_kind,
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
