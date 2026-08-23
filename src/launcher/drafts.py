from __future__ import annotations

from sqlalchemy.orm import Session

from launcher.models import Draft, DraftVariant


def get_draft_or_raise(session: Session, draft_id: int) -> Draft:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ValueError(f"draft {draft_id} not found")
    return draft


def resolve_candidate_text(
    session: Session, draft_id: int, variant_id: int | None = None
) -> tuple[Draft, str]:
    draft = get_draft_or_raise(session, draft_id)
    text = draft.text
    if variant_id is not None:
        variant = session.get(DraftVariant, variant_id)
        if variant is None or variant.draft_id != draft_id:
            raise ValueError(f"variant {variant_id} not found for draft {draft_id}")
        text = variant.text
    return draft, text
