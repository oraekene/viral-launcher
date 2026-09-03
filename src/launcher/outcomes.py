from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

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


@dataclass(frozen=True)
class LauncherOutcomeRow:
    features: dict[str, float]
    z60: float
    value_flag: bool
    fired_vetoes: tuple[str, ...]


class OutcomeSource(Protocol):
    def load_outcomes(self, project_id: str) -> list[OutcomeRow]: ...


class LauncherOutcomeSource(Protocol):
    def load_outcomes(self, project_id: str) -> list[LauncherOutcomeRow]: ...


class SyntheticOutcomeSource:
    def __init__(self, n: int = 400, seed: int = 7) -> None:
        self._n = n
        self._seed = seed

    def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
        from launcher.predictor import FEATURE_NAMES, feature_vector

        rng = random.Random(f"{project_id}:{self._seed}")
        rows: list[OutcomeRow] = []
        for _ in range(self._n):
            features, quality = _draw_draft(rng, bait=rng.random() < 0.08)
            followers = features.author_followers or 0
            mutuals = features.mutuals_count or 0
            author_boost = 0.6 if followers <= 1000 else 0.0
            noise = rng.gauss(0.0, 0.8)
            z60 = max(0.0, 1.5 + quality + author_boost + 0.02 * mutuals + noise)

            vector = dict(
                zip(FEATURE_NAMES, feature_vector(features, rng.random() * 0.6))
            )
            rows.append(
                OutcomeRow(
                    features=vector,
                    z60=round(z60, 3),
                    value_flag=z60 >= 2.5,
                )
            )
        return rows


class SyntheticLauncherOutcomeSource:
    def __init__(
        self, n: int = 300, winner_share: float = 0.25, seed: int = 11
    ) -> None:
        self._n = n
        self._winner_share = winner_share
        self._seed = seed

    def load_outcomes(self, project_id: str) -> list[LauncherOutcomeRow]:
        from launcher.predictor import FEATURE_NAMES, feature_vector

        rng = random.Random(f"launcher:{project_id}:{self._seed}")
        rows: list[LauncherOutcomeRow] = []
        for _ in range(self._n):
            winner = rng.random() < self._winner_share
            features, quality = _draw_draft(rng, bait=False)

            fired: tuple[str, ...] = ()
            if winner and rng.random() < 0.05:
                fired = ("negative.engagement_bait",)
            elif (not winner) and rng.random() < 0.08:
                fired = ("negative.engagement_bait",)

            vector = dict(
                zip(FEATURE_NAMES, feature_vector(features, rng.random() * 0.6))
            )
            base = 2.6 if winner else 1.3
            z60 = max(0.0, base + quality * (0.5 if winner else 0.8) + rng.gauss(0.0, 0.7))
            rows.append(
                LauncherOutcomeRow(
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


class RadarOutcomeSource:
    def __init__(self, session: Session) -> None:
        self._loader = _StageLoader(session)

    def load_outcomes(self, project_id: str) -> list[OutcomeRow]:
        return [
            OutcomeRow(features=dict(r.features), z60=r.z60, value_flag=r.value_flag)
            for r in self._loader.load(project_id)
        ]


class StagedLauncherOutcomeSource:
    def __init__(self, session: Session) -> None:
        self._loader = _StageLoader(session)

    def load_outcomes(self, project_id: str) -> list[LauncherOutcomeRow]:
        return [
            LauncherOutcomeRow(
                features=dict(r.features),
                z60=r.z60,
                value_flag=r.value_flag,
                fired_vetoes=tuple(r.fired_vetoes or ()),
            )
            for r in self._loader.load(project_id)
        ]


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
