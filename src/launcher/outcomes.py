from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy.orm import Session

from launcher.features import DraftFeatures

if TYPE_CHECKING:
    from launcher.models import RadarOutcomeStage


def _draw_draft(rng: random.Random, bait: bool) -> tuple[DraftFeatures, float]:
    has_q = rng.random() < 0.4
    quotable = rng.random() < 0.5
    cta = has_q or rng.random() < 0.2
    links = 1 if rng.random() < 0.2 else 0
    hashtags = rng.randint(0, 4)
    followers = rng.choice([150, 400, 900, 2500, 8000, 20000])
    mutuals = rng.randint(0, 30)
    quality = (
        1.3 * has_q + 1.6 * quotable + 0.7 * cta - 0.9 * links - 0.15 * hashtags
    )
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
    return features, quality


@dataclass(frozen=True)
class OutcomeRow:
    features: dict[str, float]
    z60: float
    value_flag: bool
    fired_vetoes: tuple[str, ...] = ()


class OutcomeSource(Protocol):
    @property
    def provenance(self) -> str: ...

    @property
    def is_trusted(self) -> bool: ...

    def load_outcomes(self, project_id: str) -> list[OutcomeRow]: ...


class SyntheticOutcomeSource:
    def __init__(self, n: int = 400, winner_share: float = 0.25, seed: int = 7) -> None:
        if not 0.0 <= winner_share <= 1.0:
            raise ValueError(f"winner_share must be within [0, 1], got {winner_share}")
        self._n = n
        self._winner_share = winner_share
        self._seed = seed

    @property
    def provenance(self) -> str:
        return "synthetic"

    @property
    def is_trusted(self) -> bool:
        return False

    def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
        from launcher.predictor import FEATURE_NAMES, feature_vector

        rng = random.Random(f"synthetic:{project_id}:{self._seed}")
        # Rank-based winners: the top-k drafts by quality become winners, so
        # flags stay controllable via winner_share AND learnable from features
        # (a pure draw would be feature-invisible and untrainable).
        drafts = [_draw_draft(rng, bait=rng.random() < 0.08) for _ in range(self._n)]
        ranked = sorted(
            range(self._n),
            key=lambda i: drafts[i][1] + rng.gauss(0.0, 0.4),
            reverse=True,
        )
        winners = set(ranked[: round(self._n * self._winner_share)])
        rows: list[OutcomeRow] = []
        for i, (features, quality) in enumerate(drafts):
            winner = i in winners
            followers = features.author_followers or 0
            author_boost = 0.3 if followers <= 1000 else 0.0
            base = 3.5 if winner else 1.3
            z60 = max(0.0, base + 0.3 * quality + author_boost + rng.gauss(0.0, 0.2))

            fired: tuple[str, ...] = ()
            if winner and rng.random() < 0.05:
                fired = ("negative.engagement_bait",)
            elif (not winner) and rng.random() < 0.08:
                fired = ("negative.engagement_bait",)

            vector = dict(
                zip(FEATURE_NAMES, feature_vector(features, rng.random() * 0.6))
            )
            rows.append(
                OutcomeRow(
                    features=vector,
                    z60=round(z60, 3),
                    value_flag=winner,
                    fired_vetoes=fired,
                )
            )
        return rows


class _StageLoader:
    def __init__(self, session: Session) -> None:
        self._session = session

    def load(self, project_id: str) -> list[RadarOutcomeStage]:
        from launcher.models import RadarOutcomeStage

        rows = (
            self._session.query(RadarOutcomeStage)
            .filter_by(project_id=project_id)
            .order_by(RadarOutcomeStage.id)
            .all()
        )
        if not rows:
            raise ValueError(
                f"no radar outcomes imported for project {project_id!r}; "
                "POST them to /outcomes/import first"
            )
        return rows


class StagedOutcomeSource:
    def __init__(self, session: Session) -> None:
        self._loader = _StageLoader(session)

    @property
    def provenance(self) -> str:
        return "radar-staged"

    @property
    def is_trusted(self) -> bool:
        return True

    def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
        return [
            OutcomeRow(
                features=dict(r.features),
                z60=r.z60,
                value_flag=r.value_flag,
                fired_vetoes=tuple(r.fired_vetoes or ()),
            )
            for r in self._loader.load(project_id)
        ]


def outcome_source(
    source: str,
    session: Session,
    *,
    n: int,
    winner_share: float = 0.25,
) -> OutcomeSource:
    """Single factory for outcome sources: staged/real or synthetic.

    Both sources serve training and calibration through the one
    OutcomeSource contract; trust (synthetic rehearsal never writes,
    staged evidence may) travels on the source, not on its type.
    Raises ValueError for unknown names so routes map it to 422.
    """
    if source == "radar":
        return StagedOutcomeSource(session)
    if source == "synthetic":
        return SyntheticOutcomeSource(n=n, winner_share=winner_share)
    raise ValueError(f"unknown outcome source {source!r}")


def stage_radar_outcomes(
    session: Session,
    project_id: str,
    rows: list[dict[str, Any]],
) -> int:
    from launcher.models import RadarOutcomeStage
    from launcher.predictor import FEATURE_NAMES

    required = set(FEATURE_NAMES)
    staged: list[RadarOutcomeStage] = []
    for i, row in enumerate(rows):
        features = row.get("features")
        if not isinstance(features, dict):
            raise ValueError(f"row {i}: 'features' must be an object")
        keys = set(features.keys())
        if not required.issubset(keys):
            missing = sorted(required - keys)
            raise ValueError(f"row {i}: missing feature keys: {missing}")
        vetoes_raw = row.get("fired_vetoes") or []
        staged.append(
            RadarOutcomeStage(
                project_id=project_id,
                z60=float(row["z60"]),
                value_flag=bool(row["value_flag"]),
                fired_vetoes=[str(v) for v in vetoes_raw],
                features={k: float(features[k]) for k in required},
            )
        )
    session.add_all(staged)
    session.flush()
    return len(staged)
