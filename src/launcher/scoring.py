from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from launcher.features import DraftFeatures, topic_lane
from launcher.params import ParamStore
from launcher.predictor import predict_z
from launcher.similarity import max_swatch_similarity


@dataclass(frozen=True)
class ScoreResult:
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScoredScore:
    score: float
    reasons: list[str]
    kind: Literal["predicted", "interim"]
    scorer: Literal["predictor", "interim"]
    band_width: float
    model_id: int | None
    model_status: str | None


def interim_score(features: DraftFeatures, store: ParamStore) -> ScoreResult:
    if (
        features.engagement_bait_hits
        or features.mass_reply_markers
        or features.pod_signature_hits
    ):
        return ScoreResult(score=0.0, reasons=("veto-class features present; unscored",))

    terms: list[tuple[float, str, str]] = []

    if features.has_question or features.has_cta:
        w = store.get_float("weight.reply")
        terms.append((w, "reply elicitor present", "weight.reply"))

    if features.quotable_claim:
        w = store.get_float("weight.quote")
        terms.append((w, "quotable claim present", "weight.quote"))

    if features.has_save_cue:
        w = store.get_float("weight.share_dm")
        terms.append((w, "DM/share elicitor present", "weight.share_dm"))

    if features.has_follow_cue:
        w = store.get_float("weight.follow")
        terms.append((w, "follow elicitor present", "weight.follow"))

    if features.link_count >= 1:
        w = store.get_float("weight.open_link")
        terms.append((w, "link open elicitor present", "weight.open_link"))

    if features.quotable_claim and features.link_count == 0 and features.char_len <= 200:
        w = store.get_float("weight.share")
        terms.append((w, "shareable standalone claim", "weight.share"))

    if features.thread_marker:
        w = store.get_float("weight.repost")
        terms.append((w, "thread structure invites follows", "weight.repost"))

    media = set(features.media_types)
    if "photo" in media:
        w = store.get_float("weight.photo_expand")
        terms.append((w, "photo attached, expansion elicitor", "weight.photo_expand"))
    if "video" in media or "gif" in media:
        w = store.get_float("weight.video_open")
        terms.append((w, "video attached, open elicitor", "weight.video_open"))

    score = sum(w for w, _, _ in terms)
    reasons = tuple(f"x{w} {label} ({param}={w})" for w, label, param in terms)
    return ScoreResult(score=round(score, 4), reasons=reasons)


def topic_factor(features: DraftFeatures, store: ParamStore) -> float:
    """Multiplicative interim discount for off-lane drafts (#8).

    Applies only when both sides declared topics and they are disjoint;
    overlap or either side undeclared scores unchanged. Predictor-path
    scores skip this: the trained model sees no topic features yet.
    """
    if not features.topics or not features.voice_topics:
        return 1.0
    if topic_lane(features.topics, features.voice_topics) == "disjoint":
        return store.get_float("oon.topic_discount")
    return 1.0


def resolve_score(
    session: Session,
    project_id: str | None,
    features: DraftFeatures,
    text: str,
) -> ScoredScore:
    """Single Score seam: predictor when a model exists, else interim.

    Owns the full fallback policy — score, kind, scorer identity, band
    width, and model identity travel together so callers never re-derive
    them. Gate-then-score ordering belongs to the caller.
    """
    store = ParamStore(session)
    sim = max_swatch_similarity(session, project_id, text)
    prediction = predict_z(session, project_id, features, swatch_similarity=sim)
    interim = interim_score(features, store)
    if prediction is not None:
        return ScoredScore(
            score=round(prediction.predicted_z, 4),
            reasons=[
                f"predicted z {prediction.predicted_z:.2f} "
                f"+-{prediction.band_width:.2f} (model {prediction.model_id}, "
                f"{prediction.model_status})",
                f"format similarity to archived winners: {sim:.2f}",
                f"interim gate score {interim.score}",
            ],
            kind="predicted",
            scorer="predictor",
            band_width=prediction.band_width,
            model_id=prediction.model_id,
            model_status=prediction.model_status,
        )
    factor = topic_factor(features, store)
    if factor == 1.0:
        return ScoredScore(
            score=interim.score,
            reasons=list(interim.reasons),
            kind="interim",
            scorer="interim",
            band_width=store.get_float("band.interim_width"),
            model_id=None,
            model_status=None,
        )
    return ScoredScore(
        score=round(interim.score * factor, 4),
        reasons=[
            *list(interim.reasons),
            f"off-lane topics {tuple(features.topics)} vs voice {tuple(features.voice_topics or ())}: x{factor} (oon.topic_discount)",
        ],
        kind="interim",
        scorer="interim",
        band_width=store.get_float("band.interim_width"),
        model_id=None,
        model_status=None,
    )
