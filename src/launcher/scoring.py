from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from launcher.features import DraftFeatures
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
    kind: str


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

    if features.quotable_claim and features.link_count == 0 and features.char_len <= 200:
        w = store.get_float("weight.share")
        terms.append((w, "shareable standalone claim", "weight.share"))

    if features.thread_marker:
        w = store.get_float("weight.repost")
        terms.append((w, "thread structure invites follows", "weight.repost"))

    score = sum(w for w, _, _ in terms)
    reasons = tuple(f"x{w} {label} ({param}={w})" for w, label, param in terms)
    return ScoreResult(score=round(score, 4), reasons=reasons)


def resolve_score(
    session: Session,
    project_id: str | None,
    features: DraftFeatures,
    text: str,
) -> ScoredScore:
    store = ParamStore(session)
    sim = max_swatch_similarity(session, project_id, text)
    prediction = predict_z(session, project_id, features, swatch_similarity=sim)
    if prediction is not None:
        interim = interim_score(features, store)
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
        )
    result = interim_score(features, store)
    return ScoredScore(score=result.score, reasons=list(result.reasons), kind="interim")
