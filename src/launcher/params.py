from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from sqlalchemy.orm import Session

from launcher.models import ParamVersion

_XALGO = (
    "xai-org/x-algorithm home-mixer/params/param.rs (released Aug 13 2026) — "
    "assumed: primary source not vendored in-repo, verify before citing"
)


class ParamSpec(NamedTuple):
    key: str
    value: float
    status: str
    source_note: str


PARAM_SEED: tuple[ParamSpec, ...] = (
    ParamSpec("weight.reply", 5.0, "assumed", _XALGO),
    ParamSpec("weight.quote", 5.0, "assumed", _XALGO),
    ParamSpec("weight.share", 2.0, "assumed", _XALGO),
    ParamSpec(
        "weight.share_dm",
        5.0,
        "assumed",
        "x-algorithm home-mixer/params/param.rs (ShareViaDmWeight 5.0), read 2026-09; not vendored; production experiments can move values without notice",
    ),
    ParamSpec(
        "weight.follow",
        4.0,
        "assumed",
        "x-algorithm home-mixer/params/param.rs (FollowAuthorWeight 4.0), read 2026-09; not vendored; production experiments can move values without notice",
    ),
    ParamSpec(
        "weight.open_link",
        0.2,
        "assumed",
        "x-algorithm home-mixer/params/param.rs (OpenLinkWeight 0.2), read 2026-09; not vendored; production experiments can move values without notice",
    ),
    ParamSpec("weight.repost", 1.0, "assumed", _XALGO),
    ParamSpec("weight.like", 0.5, "assumed", _XALGO),
    ParamSpec("weight.click", 0.4, "assumed", _XALGO),
    ParamSpec(
        "weight.photo_expand",
        0.05,
        "assumed",
        "x-algorithm home-mixer/params/param.rs (PhotoExpandWeight 0.05), read 2026-09-10; not vendored; production experiments can move values without notice",
    ),
    ParamSpec(
        "weight.video_open",
        0.05,
        "assumed",
        "x-algorithm home-mixer/params/param.rs (VideoOpenWeight 0.05 in pinned revs; head raw read 0.07 once), read 2026-09-10; not vendored; production experiments can move values without notice",
    ),
    ParamSpec(
        "oon.topic_discount",
        0.5,
        "pending",
        "house prior per issue #8 for topic-disjoint drafts; no verified production counterpart, confirm at next upstream recheck",
    ),
    ParamSpec("negative.report", -234.0, "assumed", _XALGO),
    ParamSpec("negative.mute", -58.8, "assumed", _XALGO),
    ParamSpec("negative.not_interested", -43.2, "assumed", _XALGO),
    ParamSpec("negative.block", -31.2, "assumed", _XALGO),
    ParamSpec("boost.bidirectional_reply", 15.0, "assumed", _XALGO),
    ParamSpec("oon.discount", 0.75, "assumed", _XALGO),
    ParamSpec("author.diversity_decay", 0.5, "assumed", _XALGO),
    ParamSpec("author.diversity_floor", 0.25, "assumed", _XALGO),
    ParamSpec("cold_start.follower_cap", 1000.0, "assumed", _XALGO),
    ParamSpec("age_filter.hours", 48.0, "assumed", _XALGO),
    ParamSpec(
        "half_life.minutes",
        80.0,
        "sourced",
        "arXiv:2302.09654 median tweet half-life 79.5 min (~80); "
        "excerpt vendored in docs/sources/2302.09654-half-life-excerpt.md",
    ),
    ParamSpec(
        "limit.standard_chars",
        280.0,
        "sourced",
        "X standard post length limit; premium tiers allow longer",
    ),
    ParamSpec(
        "z.trigger",
        2.5,
        "pending",
        "radar calibration harness; refit after >=100 outcome events",
    ),
    ParamSpec(
        "band.interim_width",
        1.5,
        "pending",
        "uncalibrated interim band width; superseded by model residual std once trained",
    ),
    ParamSpec(
        "min_delta_t.minutes",
        10.0,
        "pending",
        "radar scoring engine min-delta-t guard; calibrate with outcomes",
    ),
    ParamSpec("rewriter.default_n", 10.0, "pending", "spec default; tune after usage"),
    ParamSpec(
        "cost.per_draft_cap_usd",
        1.00,
        "pending",
        "spec default per-draft rewrite budget cap",
    ),
    ParamSpec(
        "llm.price_input_per_1k_usd",
        0.15,
        "pending",
        "placeholder price; set to match the configured provider",
    ),
    ParamSpec(
        "llm.price_output_per_1k_usd",
        0.60,
        "pending",
        "placeholder price; set to match the configured provider",
    ),
)


@dataclass(frozen=True)
class ParamValue:
    key: str
    value: float
    status: str
    source_note: str


def seed_params(session: Session) -> None:
    """Insert missing params; refresh provenance notes on existing ones.
    Value and status are operator/calibration state and never touched,
    except a one-time bump of untouched cost.per_draft_cap_usd rows
    from the old 0.10 default to the Q9 1.00 default."""
    existing = {row.key: row for row in session.query(ParamVersion).all()}
    for spec in PARAM_SEED:
        row = existing.get(spec.key)
        if row is None:
            session.add(
                ParamVersion(
                    key=spec.key,
                    value=spec.value,
                    status=spec.status,
                    source_note=spec.source_note,
                )
            )
        else:
            if (
                spec.key == "cost.per_draft_cap_usd"
                and row.status == "pending"
                and abs(row.value - 0.10) < 1e-9
            ):
                # ponytail: one-time default bump 0.10 -> 1.00 per Q9; customized values untouched
                row.value = spec.value
            if row.source_note != spec.source_note:
                row.source_note = spec.source_note


class ParamStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str) -> ParamValue:
        row = self._session.query(ParamVersion).filter_by(key=key).one_or_none()
        if row is None:
            raise KeyError(key)
        return ParamValue(key=row.key, value=row.value, status=row.status, source_note=row.source_note)

    def get_float(self, key: str) -> float:
        return self.get(key).value
