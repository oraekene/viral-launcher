from __future__ import annotations

from dataclasses import dataclass

from launcher.features import DraftFeatures
from launcher.params import ParamStore


@dataclass(frozen=True)
class ScoreResult:
    score: float
    reasons: tuple[str, ...]


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
