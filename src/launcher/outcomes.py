from __future__ import annotations

import random
from dataclasses import dataclass
from typing import NamedTuple, Protocol

from launcher.features import DraftFeatures


@dataclass(frozen=True)
class OutcomeRow:
    features: dict[str, float]
    z60: float
    value_flag: bool


class OutcomeSource(Protocol):
    def load_outcomes(self, project_id: str) -> list[OutcomeRow]: ...


class SyntheticOutcomeSource:
    def __init__(self, n: int = 400, seed: int = 7) -> None:
        self._n = n
        self._seed = seed

    def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
        from launcher.predictor import FEATURE_NAMES, feature_vector

        rng = random.Random(f"{project_id}:{self._seed}")
        rows: list[OutcomeRow] = []
        for _ in range(self._n):
            has_q = rng.random() < 0.4
            quotable = rng.random() < 0.5
            cta = has_q or rng.random() < 0.2
            links = 1 if rng.random() < 0.2 else 0
            hashtags = rng.randint(0, 4)
            followers = rng.choice([150, 400, 900, 2500, 8000, 20000])
            mutuals = rng.randint(0, 30)
            bait = rng.random() < 0.08

            quality = (
                1.3 * has_q
                + 1.6 * quotable
                + 0.7 * cta
                - 0.9 * links
                - 0.15 * hashtags
            )
            author_boost = 0.6 if followers <= 1000 else 0.0
            noise = rng.gauss(0.0, 0.8)
            z60 = max(0.0, 1.5 + quality + author_boost + 0.02 * mutuals + noise)

            features = DraftFeatures(
                char_len=rng.randint(40, 280),
                word_count=rng.randint(8, 55),
                question_count=int(has_q),
                has_question=has_q,
                has_cta=cta,
                quotable_claim=quotable,
                link_count=links,
                hashtag_count=hashtags,
                mention_count=0,
                exclamation_count=0,
                thread_marker=False,
                engagement_bait_hits=("bait",) if bait else (),
                mass_reply_markers=(),
                pod_signature_hits=(),
                author_followers=followers,
                mutuals_count=mutuals,
                scheduled_at=None,
                allow_premium_length=False,
            )
            vector = dict(zip(FEATURE_NAMES, feature_vector(features)))
            rows.append(
                OutcomeRow(
                    features=vector,
                    z60=round(z60, 3),
                    value_flag=z60 >= 2.5,
                )
            )
        return rows


class RadarOutcomeFields(NamedTuple):
    alert_id: int
    z60: float | None
    value_flag: bool | None


def radar_features_from_draft_features(f: DraftFeatures) -> dict[str, float]:
    from launcher.predictor import FEATURE_NAMES, feature_vector

    return dict(zip(FEATURE_NAMES, feature_vector(f)))


class RadarOutcomeSource:
    def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
        raise NotImplementedError(
            "radar outcome pipeline not connected yet; the radar build must "
            "expose alert_events x action_outcomes mapped into the canonical "
            "feature schema"
        )
