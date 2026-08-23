from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from launcher.features import extract
from launcher.models import Draft, DraftVariant, LaunchEvent
from launcher.params import ParamStore
from launcher.predictor import predict_z
from launcher.scoring import interim_score
from launcher.similarity import max_swatch_similarity

DOUBLE_DOWN_CHECKLIST: tuple[str, ...] = (
    "Self-reply with a new angle or the data behind the claim",
    "Reply to every early commenter within the first hour",
    "Quote your own post into a fresh conversational lane",
)

ESCALATE_CHECKLIST: tuple[str, ...] = (
    "Publish a thread follow-up while momentum holds",
    "Answer every reply to keep velocity compounding",
    "Prepare a follow-on post for the next window",
)

HOLD_CHECKLIST: tuple[str, ...] = (
    "Track without intervening; re-check at t=60",
    "Stay available for replies",
)


@dataclass(frozen=True)
class ProtocolCard:
    protocol: str
    checklist: tuple[str, ...]


def register_launch(
    session: Session,
    draft_id: int,
    post_external_id: str | None = None,
    variant_id: int | None = None,
) -> LaunchEvent:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ValueError(f"draft {draft_id} not found")

    text = draft.text
    if variant_id is not None:
        variant = session.get(DraftVariant, variant_id)
        if variant is None or variant.draft_id != draft_id:
            raise ValueError(f"variant {variant_id} not found for draft {draft_id}")
        text = variant.text

    features = extract(
        text,
        author_followers=draft.author_followers,
        mutuals_count=draft.mutuals_count,
        allow_premium_length=draft.allow_premium_length,
    )
    store = ParamStore(session)
    similarity = max_swatch_similarity(session, draft.project_id, text)
    prediction = predict_z(session, draft.project_id, features, swatch_similarity=similarity)
    if prediction is not None:
        predicted_z = prediction.predicted_z
        band_width = prediction.band_width
        scorer = "predictor"
    else:
        predicted_z = interim_score(features, store).score
        band_width = store.get_float("band.interim_width")
        scorer = "interim"

    event = LaunchEvent(
        draft_id=draft_id,
        variant_id=variant_id,
        post_external_id=post_external_id,
        predicted_z=predicted_z,
        band_width=band_width,
        scorer=scorer,
    )
    session.add(event)
    session.flush()
    return event


def evaluate_protocol(predicted_z: float, band_width: float, actual_z: float) -> ProtocolCard:
    if actual_z < predicted_z - band_width:
        return ProtocolCard("double_down", DOUBLE_DOWN_CHECKLIST)
    if actual_z > predicted_z + band_width:
        return ProtocolCard("escalate", ESCALATE_CHECKLIST)
    return ProtocolCard("hold", HOLD_CHECKLIST)


def apply_snapshot(session: Session, launch_id: int, actual_z_t10: float) -> LaunchEvent:
    event = session.get(LaunchEvent, launch_id)
    if event is None:
        raise ValueError(f"launch {launch_id} not found")
    if event.actual_z_t10 is not None:
        raise ValueError(f"launch {launch_id} already has a t=10 snapshot")
    card = evaluate_protocol(event.predicted_z, event.band_width, actual_z_t10)
    event.actual_z_t10 = round(actual_z_t10, 4)
    event.protocol_fired = card.protocol
    session.flush()
    return event


def log_intervention(
    session: Session, launch_id: int, action: str, note: str | None = None
) -> LaunchEvent:
    from launcher.models import utcnow

    event = session.get(LaunchEvent, launch_id)
    if event is None:
        raise ValueError(f"launch {launch_id} not found")
    interventions = list(event.interventions or [])
    interventions.append(
        {
            "action": action,
            "note": note or "",
            "at": utcnow().isoformat(),
        }
    )
    event.interventions = interventions
    session.flush()
    return event
